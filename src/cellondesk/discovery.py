"""Unified discovery orchestration; no Qt dependency or automatic asset probes."""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from typing import Any

from .catalog_cache import SearchBudget, SearchStats
from .modality import PROFILE_LABELS
from .models import DatasetRecord
from .sources.cellxgene_discover import CellxGeneDiscoverClient
from .sources.hubmap import HuBMAPClient
from .sources.ucsc_cellbrowser import UCSCCellBrowserClient

SOURCES = {"hubmap": "HuBMAP", "cellxgene": "CELLxGENE Discover", "ucsc": "UCSC Cell Browser"}


@dataclass(frozen=True)
class SearchQuery:
    keyword: str = ""
    tissue: str = ""
    organism: str = ""
    assay: str = ""
    sources: tuple[str, ...] = tuple(SOURCES)
    limit: int = 100
    refresh: bool = False
    disease: str = ""
    cell_type: str = ""
    hubmap_status: str = "Published"
    modalities: tuple[str, ...] = ()


@dataclass
class SourceOutcome:
    source: str
    records: list[DatasetRecord] = field(default_factory=list)
    stats: SearchStats = field(default_factory=SearchStats)
    elapsed_seconds: float = 0
    error: str | None = None
    notices: list[str] = field(default_factory=list)


class DiscoveryService:
    def __init__(
        self,
        *,
        factories: dict[str, Callable[[SearchBudget], Any]] | None = None,
        timeout: float = 30,
    ):
        self.factories = (
            factories
            if factories is not None
            else {
                "hubmap": lambda budget: HuBMAPClient(budget=budget),
                "cellxgene": lambda budget: CellxGeneDiscoverClient(budget=budget),
                "ucsc": lambda budget: UCSCCellBrowserClient(budget=budget),
            }
        )
        self.timeout = timeout

    def _source(
        self, source: str, query: SearchQuery, cancelled: Callable[[], bool]
    ) -> SourceOutcome:
        outcome = SourceOutcome(source)
        started = time.monotonic()
        client = None
        try:
            budget = SearchBudget(self.timeout, cancelled)
            budget.remaining()
            with self.factories[source](budget) as client:
                common = {
                    "query": query.keyword or None,
                    "organism": query.organism or None,
                    "limit": query.limit,
                    "modalities": query.modalities,
                }
                if source == "hubmap":
                    outcome.records = client.search_datasets(
                        **common,
                        organ=query.tissue or None,
                        dataset_type=query.assay or None,
                        status=query.hubmap_status or None,
                    )
                elif source == "cellxgene":
                    outcome.records = client.search_datasets(
                        **common,
                        tissue=query.tissue or None,
                        assay=query.assay or None,
                        disease=query.disease or None,
                        cell_type=query.cell_type or None,
                        refresh=query.refresh,
                    )
                else:
                    outcome.records = client.search_datasets(
                        **common,
                        organ=query.tissue or None,
                        assay=query.assay or None,
                        refresh=query.refresh,
                    )
        except Exception as exc:  # noqa: BLE001 - each adapter is an independent failure boundary
            outcome.error = f"{type(exc).__name__}: {exc}"
        finally:
            if client is not None:
                outcome.stats = client.last_search
            if outcome.error:
                outcome.stats.complete = False
            outcome.elapsed_seconds = time.monotonic() - started
        if source != "cellxgene" and (query.disease or query.cell_type):
            outcome.notices.append("Disease and cell-type filters apply only to CELLxGENE.")
        if query.modalities:
            outcome.notices.append(
                "Modality facet uses source assay hints; unclassified assays are excluded. Remote file contents remain unverified."
            )
        if source == "hubmap":
            outcome.notices.append(
                "Organ/assay aliases use exact HuBMAP values; unknown labels are exact searches."
            )
            if query.organism:
                outcome.notices.append(
                    "Organism matches only explicitly reported organism metadata."
                )
            if "snrna" in query.assay.casefold():
                outcome.notices.append(
                    "HuBMAP RNAseq covers cells and nuclei; nuclei-only selection is not established by this assay field."
                )
        for record in outcome.records:
            record.provenance["search"] = {
                "query": asdict(query),
                "coverage_complete": outcome.stats.complete,
                "display_limited": outcome.stats.truncated,
                "warnings": outcome.stats.warnings,
                "filter_notices": outcome.notices,
            }
        return outcome

    def search(
        self,
        query: SearchQuery,
        *,
        cancelled: Callable[[], bool] = lambda: False,
        on_source: Callable[[SourceOutcome], None] | None = None,
    ) -> list[SourceOutcome]:
        sources = tuple(dict.fromkeys(query.sources))
        if not sources or any(source not in SOURCES for source in sources):
            raise ValueError("Select at least one supported source.")
        if set(query.modalities) - PROFILE_LABELS.keys():
            raise ValueError("Unknown scientific modality facet.")
        if not query.modalities and not any(
            value.strip()
            for value in (
                query.keyword,
                query.tissue,
                query.organism,
                query.assay,
                query.disease,
                query.cell_type,
            )
        ):
            raise ValueError("Enter at least one scientific search filter.")
        outcomes = {}
        # At most three simultaneous source jobs, each with an independent budget.
        with ThreadPoolExecutor(max_workers=len(sources), thread_name_prefix="discovery") as pool:
            futures = {
                pool.submit(self._source, source, query, cancelled): source for source in sources
            }
            for future in as_completed(futures):
                outcome = future.result()
                outcomes[outcome.source] = outcome
                if on_source:
                    on_source(outcome)
        return [outcomes[source] for source in sources]


def access_summary(record: DatasetRecord) -> str:
    availability = {
        "not_checked": "Files not yet checked",
        "advertised": "Files advertised; not verified",
        "verified": "Direct download verified",
        "transfer_only": "Transfer only (source reported)",
        "checked_no_direct": "No direct file found; coverage limited",
    }.get(record.asset_status, record.asset_status)
    return f"{record.access_level or 'Access not reported'} · {availability}"

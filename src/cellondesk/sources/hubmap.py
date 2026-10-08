from __future__ import annotations

import os
import time
from collections.abc import Mapping
from itertools import zip_longest
from typing import Any

import httpx
from typing_extensions import Self

from cellondesk.assets import probe_asset
from cellondesk.catalog_cache import SearchBudget, SearchStats, SearchStopped, read_json
from cellondesk.models import DataAsset, DatasetRecord
from cellondesk.search_metadata import organism_matches, reported_count

SEARCH_URL = "https://search.api.hubmapconsortium.org/v3/param-search/datasets"
PORTAL_DATASET_URL = "https://portal.hubmapconsortium.org/browse/dataset/{uuid}"
ASSET_ROOT_URL = "https://assets.hubmapconsortium.org"

# A short, scientist-facing list for the editable desktop assay selector.
SPATIAL_DATASET_TYPES = (
    "Visium (no probes)",
    "Visium (with probes)",
    "Slide-seq",
    "MERFISH",
    "CODEX",
    "MIBI",
    "IMC",
    "MALDI IMS",
    "scRNA-seq / snRNA-seq",
)

# A bounded fallback for oversized parameter-search responses. This static list
# cannot establish exhaustive assay coverage; fallback results are marked partial.
HUBMAP_DATASET_TYPES = (
    "RNAseq",
    "RNAseq (with probes)",
    "Visium (no probes)",
    "Visium (with probes)",
    "Slideseq",
    "MERFISH",
    "CODEX",
    "MIBI",
    "2D Imaging Mass Cytometry",
    "3D Imaging Mass Cytometry",
    "MALDI",
    "10X Multiome",
    "ATACseq",
    "Auto-fluorescence",
    "DESI",
    "GeoMx (NGS)",
    "HiFi-Slide",
    "Histology",
    "LC-MS",
    "Light Sheet",
    "MUSIC",
    "PhenoCycler",
    "SIMS",
    "SNARE-seq2",
    "Second Harmonic Generation (SHG)",
    "seqFISH",
    "Thick section Multiphoton MxIF",
    "WGS",
)

# Common processed HuBMAP single-cell products. Availability is verified before
# a product is shown to the user; these are candidates, not promises.
H5AD_PRODUCT_CANDIDATES: tuple[tuple[str, str], ...] = (
    ("expr.h5ad", "Raw gene expression"),
    ("raw_expr.h5ad", "Raw gene expression"),
    ("secondary_analysis.h5ad", "Normalized expression with analysis metadata"),
    ("scvelo_annotated.h5ad", "RNA velocity analysis"),
)

ORGAN_ALIASES: dict[str, tuple[str, ...]] = {
    "kidney": ("LK", "RK"),
    "left kidney": ("LK",),
    "kidney left": ("LK",),
    "right kidney": ("RK",),
    "kidney right": ("RK",),
    "kidney (left)": ("LK",),
    "kidney (right)": ("RK",),
    "kidneys": ("LK", "RK"),
    "renal": ("LK", "RK"),
    "spleen": ("SP",),
    "adipose tissue": ("AD",),
    "bladder": ("BL",),
    "blood": ("BD",),
    "blood vasculature": ("BV",),
    "bone marrow": ("BM",),
    "brain": ("BR",),
    "heart": ("HT",),
    "intervertebral disc": ("ID",),
    "large intestine": ("LI",),
    "liver": ("LV",),
    "larynx": ("LA",),
    "lymph node": ("LY",),
    "lymphatic vasculature": ("VL",),
    "pancreas": ("PA",),
    "placenta": ("PL",),
    "prostate": ("PR",),
    "skin": ("SK",),
    "small intestine": ("SI",),
    "spinal cord": ("SC",),
    "sternum": ("ST",),
    "thymus": ("TH",),
    "trachea": ("TR",),
    "uterus": ("UT",),
    "lung": ("LL", "RL"),
    "eye": ("LE", "RE"),
    "bronchus": ("LB", "RB"),
    "ovary": ("LO", "RO"),
    "fallopian tube": ("LF", "RF"),
    "tonsil": ("LT", "RT"),
    "ureter": ("LU", "RU"),
    "mammary gland": ("ML", "MR"),
    "knee": ("LN", "RN"),
    "mouth": ("MH",),
    "pelvis": ("PV",),
    "manubrium": ("MB",),
}

# Names/codes from the HuBMAP ontology organ list; keep side-specific queries exact.
for _name, _codes in tuple(ORGAN_ALIASES.items()):
    if len(_codes) == 2:
        for _side, _code in zip(("left", "right"), _codes):
            for _label in (f"{_side} {_name}", f"{_name} {_side}", f"{_name} ({_side})"):
                ORGAN_ALIASES.setdefault(_label, (_code,))
    for _code in _codes:
        ORGAN_ALIASES[_code.casefold()] = (_code,)

ASSAY_ALIASES: dict[str, tuple[str, ...]] = {
    "scrna-seq / snrna-seq": (
        "RNAseq",
        "scRNA-seq",
        "snRNA-seq",
        "snRNAseq",
    ),
    "scrna-seq": ("RNAseq", "scRNA-seq"),
    "snrna-seq": ("RNAseq", "snRNA-seq", "snRNAseq"),
    "rna-seq": ("RNAseq", "RNAseq (with probes)", "scRNA-seq", "snRNA-seq", "snRNAseq"),
    "merfish": ("MERFISH", "MERFISH [Salmon]"),
    "slide-seq": ("Slideseq", "Slide-seq"),
    "slideseq": ("Slideseq", "Slide-seq"),
    "maldi ims": ("MALDI", "MALDI IMS", "MALDI-IMS"),
    "maldi": ("MALDI", "MALDI IMS", "MALDI-IMS"),
    "imc": ("2D Imaging Mass Cytometry", "3D Imaging Mass Cytometry", "IMC"),
}


def resolve_organ_filters(value: str | None) -> tuple[str | None, ...]:
    if not value or not value.strip():
        return (None,)
    text = value.strip()
    return ORGAN_ALIASES.get(text.casefold(), (text,))


def resolve_dataset_type_filters(value: str | None) -> tuple[str | None, ...]:
    if not value or not value.strip():
        return (None,)
    text = value.strip()
    return ASSAY_ALIASES.get(text.casefold(), (text,))


class HuBMAPClient:
    """Synchronous client for HuBMAP search and public data-product discovery."""

    def __init__(
        self,
        token: str | None = None,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
        budget: SearchBudget | None = None,
    ) -> None:
        self.budget = budget
        self.timeout = timeout
        self.last_search = SearchStats()
        headers = {"Accept": "application/json"}
        token = token or os.getenv("HUBMAP_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(
            headers=headers,
            timeout=timeout,
            transport=transport,
            follow_redirects=False,
        )
        self._asset_client = httpx.Client(
            timeout=timeout,
            transport=transport,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()
        self._asset_client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _search_once(
        self,
        *,
        dataset_type: str | None,
        organ: str | None,
        status: str | None,
    ) -> list[DatasetRecord]:
        params: dict[str, Any] = {}
        if dataset_type:
            params["dataset_type"] = dataset_type
        if organ:
            params["origin_samples.organ"] = organ
        if status:
            params["status"] = status
        if not params:
            raise ValueError("HuBMAP parameterized search requires at least one filter")

        stats = self.last_search
        stats.requests += 1
        with self._client.stream(
            "GET", SEARCH_URL, params=params, timeout=min(10, self._budget.remaining())
        ) as response:
            if response.status_code == 303:
                location = response.headers.get("location")
                if not location:
                    self._incomplete_search = True
                    return []
                # Never forward the authenticated search client's headers to redirects.
                stats.requests += 1
                with self._asset_client.stream(
                    "GET",
                    str(response.url.join(location)),
                    timeout=min(10, self._budget.remaining()),
                ) as redirected:
                    redirected.raise_for_status()
                    payload = read_json(redirected, self._budget, stats)
            elif response.status_code == 404:
                return []
            elif response.status_code == 504:
                self._incomplete_search = True
                return []
            else:
                response.raise_for_status()
                payload = read_json(response, self._budget, stats)
        if not isinstance(payload, list) and not (
            isinstance(payload, Mapping)
            and (
                isinstance(payload.get("results"), list)
                or isinstance(payload.get("hits"), list)
                or isinstance(payload.get("hits"), Mapping)
                and isinstance(payload["hits"].get("hits"), list)
            )
        ):
            raise TypeError("HuBMAP returned an unexpected search payload")
        return [_normalize_hit(hit) for hit in _extract_hits(payload)]

    def search_datasets(
        self,
        *,
        dataset_type: str | None = None,
        organ: str | None = None,
        status: str | None = "Published",
        limit: int = 100,
        query: str | None = None,
        organism: str | None = None,
    ) -> list[DatasetRecord]:
        """Query every alias before limiting; interleave alias groups fairly.

        No result-limit early exit: a full left-kidney response must not hide the
        right kidney. Timeouts/fallback coverage and truncation are explicit.
        """
        stats = self.last_search = SearchStats()
        self._budget = self.budget or SearchBudget(self.timeout)
        bounded_limit = max(1, min(limit, 1000))
        groups: list[list[DatasetRecord]] = []
        seen: set[str] = set()
        fallback_organs = []
        fatal = None
        successful = 0

        def collect(assay: str | None, organ_value: str | None) -> None:
            nonlocal successful, fatal
            self._budget.remaining()
            self._incomplete_search = False
            try:
                records = self._search_once(dataset_type=assay, organ=organ_value, status=status)
                successful += 1
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                fatal = exc
                stats.warn(f"Alias {organ_value or 'all organs'} / {assay or 'all assays'}: {exc}")
                return
            if self._incomplete_search:
                if assay is None:
                    fallback_organs.append(organ_value)
                else:
                    stats.warn(f"No usable response for {organ_value} / {assay}.")
            bucket = []
            for record in records:
                self._budget.remaining()
                stats.scanned += 1
                if stats.scanned > 100000:
                    raise SearchStopped("HuBMAP candidate limit reached (100,000 records).")
                if not organism_matches(record.organism, organism):
                    continue
                haystack = " ".join(
                    str(value or "")
                    for value in (
                        record.title,
                        record.dataset_id,
                        record.raw.get("hubmap_id"),
                        record.dataset_type,
                        record.organ,
                        record.organism,
                    )
                ).casefold()
                if query and query.strip().casefold() not in haystack:
                    continue
                if not record.dataset_id:
                    stats.warn("HuBMAP entry without a source identifier omitted.")
                    continue
                if record.dataset_id in seen:
                    continue
                seen.add(record.dataset_id)
                if len(bucket) < bounded_limit:
                    bucket.append(record)
            # Retain at most the displayed limit across previous groups, plus this
            # bounded bucket. Adding another alias cannot grow old group quotas.
            groups.append(bucket)
            keep = {record.dataset_id for record in _interleave(groups, bounded_limit)}
            for group in groups:
                group[:] = [record for record in group if record.dataset_id in keep]

        try:
            for assay in resolve_dataset_type_filters(dataset_type):
                for organ_value in resolve_organ_filters(organ):
                    collect(assay, organ_value)
            if fallback_organs:
                stats.warn(
                    "Broad HuBMAP response unavailable; static assay fallback is not exhaustive."
                )
                for assay in HUBMAP_DATASET_TYPES:
                    for organ_value in fallback_organs:
                        collect(assay, organ_value)
        except SearchStopped as exc:
            stats.warn(str(exc))
        if fatal is not None and not successful:
            raise fatal
        results = _interleave(groups, bounded_limit)
        stats.matched = len(seen)
        stats.returned = len(results)
        stats.truncated = stats.matched > stats.returned
        for record in results:
            record.provenance = {
                "metadata_url": SEARCH_URL,
                "fetched_at": time.time(),
                "organ_aliases": list(resolve_organ_filters(organ)),
                "assay_filter": dataset_type,
                "status_filter": status,
                "coverage": stats.scope(),
            }
        return results

    def resolve_assets(self, record: DatasetRecord) -> list[DataAsset]:
        """Find public H5AD products and an official CLT-manifest fallback."""
        dataset_ids = _candidate_dataset_ids(record)
        assets: list[DataAsset] = []
        seen_urls: set[str] = set()
        for dataset_id in dataset_ids:
            for name, description in H5AD_PRODUCT_CANDIDATES:
                url = f"{ASSET_ROOT_URL}/{dataset_id}/{name}"
                if url in seen_urls:
                    continue
                probe = self._probe_asset(url)
                if probe is None:
                    continue
                size_bytes, final_url = probe
                seen_urls.add(url)
                assets.append(
                    DataAsset(
                        source="HuBMAP",
                        dataset_id=dataset_id,
                        name=name,
                        download_url=final_url,
                        size_bytes=size_bytes,
                        description=description,
                        format="h5ad",
                        access_level="public",
                        is_h5ad=True,
                        raw={"requested_from": record.dataset_id},
                    )
                )

        manifest = _clt_manifest_asset(record)
        if manifest is not None:
            assets.append(manifest)
        return assets

    def _probe_asset(self, url: str) -> tuple[int | None, str] | None:
        return probe_asset(self._asset_client, url)


def _interleave(groups: list[list[DatasetRecord]], limit: int) -> list[DatasetRecord]:
    results = []
    for row in zip_longest(*groups):
        for record in row:
            if record is not None:
                results.append(record)
                if len(results) == limit:
                    return results
    return results


def _clt_manifest_asset(record: DatasetRecord) -> DataAsset | None:
    """Create a SearchAPI URL that returns a one-dataset CLT manifest."""
    hubmap_id = record.raw.get("hubmap_id")
    if not hubmap_id and record.dataset_id.upper().startswith("HBM"):
        hubmap_id = record.dataset_id
    if not hubmap_id:
        return None
    hubmap_id = str(hubmap_id).strip()
    manifest_url = str(
        httpx.URL(
            SEARCH_URL,
            params={
                "hubmap_id": hubmap_id,
                "produce-clt-manifest": "true",
            },
        )
    )
    return DataAsset(
        source="HuBMAP",
        dataset_id=record.dataset_id,
        name=f"{hubmap_id}-clt-manifest.txt",
        download_url=manifest_url,
        description=(
            "Official HuBMAP bulk-transfer manifest. Use with hubmap-clt + "
            "Globus Connect Personal; this file is not the dataset itself."
        ),
        format="text/plain",
        access_level=record.access_level,
        is_h5ad=False,
        raw={"hubmap_id": hubmap_id, "transfer_method": "HuBMAP CLT / Globus"},
    )


def _candidate_dataset_ids(record: DatasetRecord) -> list[str]:
    candidates = [record.dataset_id]
    for key in (
        "descendant_ids",
        "descendants",
        "immediate_descendants",
        "processed_dataset_ids",
    ):
        candidates.extend(_ids(record.raw.get(key)))
    return list(dict.fromkeys(value for value in candidates if value))


def _ids(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        # Only identifiers and explicit relationship containers, not title,
        # status, assay names, or every other string in descendant metadata.
        own = value.get("uuid") or value.get("id")
        values = [str(own)] if own else []
        for key in ("descendants", "immediate_descendants", "descendant_ids"):
            values.extend(_ids(value.get(key)))
        return values
    if isinstance(value, list):
        values: list[str] = []
        for nested in value:
            values.extend(_ids(nested))
        return values
    return []


def _extract_hits(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, Mapping)]
    if not isinstance(payload, Mapping):
        return []
    if isinstance(payload.get("hits"), list):
        return [x for x in payload["hits"] if isinstance(x, Mapping)]
    nested = payload.get("hits")
    if isinstance(nested, Mapping) and isinstance(nested.get("hits"), list):
        return [x.get("_source", x) for x in nested["hits"] if isinstance(x, Mapping)]
    if isinstance(payload.get("results"), list):
        return [x for x in payload["results"] if isinstance(x, Mapping)]
    return []


def _normalize_hit(hit: Mapping[str, Any]) -> DatasetRecord:
    source = hit.get("_source", hit)
    if not isinstance(source, Mapping):
        source = hit
    dataset_uuid = str(source.get("uuid") or "")
    hubmap_id = str(source.get("hubmap_id") or "")
    dataset_id = dataset_uuid or hubmap_id or str(source.get("id") or "")
    title = str(
        source.get("title")
        or source.get("dataset_info")
        or source.get("description")
        or hubmap_id
        or dataset_id
        or "Untitled HuBMAP dataset"
    )
    donor = source.get("donor")
    donor_id = donor.get("hubmap_id") if isinstance(donor, Mapping) else source.get("donor_id")
    origin_samples = source.get("origin_samples")
    organ = source.get("organ")
    if not organ and isinstance(origin_samples, list):
        organ_values = [
            sample.get("organ")
            for sample in origin_samples
            if isinstance(sample, Mapping) and sample.get("organ")
        ]
        organ = organ_values
    return DatasetRecord(
        source="HuBMAP",
        dataset_id=dataset_id,
        title=title,
        dataset_type=_text(source.get("dataset_type")),
        status=_text(source.get("status")),
        organ=_text(organ),
        donor_id=_text(donor_id),
        access_level=_text(source.get("data_access_level")),
        doi_url=_text(source.get("doi_url") or source.get("registered_doi")),
        portal_url=PORTAL_DATASET_URL.format(uuid=dataset_id) if dataset_id else None,
        organism=_text(source.get("organism")),
        reported_cell_count=reported_count(source.get("cell_count")),
        cell_count_basis="HuBMAP cell_count"
        if reported_count(source.get("cell_count")) is not None
        else None,
        acquisition_methods=["HuBMAP CLT / Globus"] if hubmap_id else [],
        raw=dict(source),
    )


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return ", ".join(str(x) for x in value)
    return str(value)


__all__ = [
    "ASSAY_ALIASES",
    "ASSET_ROOT_URL",
    "H5AD_PRODUCT_CANDIDATES",
    "HUBMAP_DATASET_TYPES",
    "ORGAN_ALIASES",
    "SPATIAL_DATASET_TYPES",
    "HuBMAPClient",
    "resolve_dataset_type_filters",
    "resolve_organ_filters",
]

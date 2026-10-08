from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx
from typing_extensions import Self

from cellondesk.catalog_cache import CatalogCache, SearchBudget, SearchStats, default_cache_dir
from cellondesk.models import DataAsset, DatasetRecord
from cellondesk.search_metadata import organism_matches, reported_count

# This is the same public dataset feed used by the official CELLxGENE Census
# builder. Unlike the lightweight /dp/v1/datasets/index endpoint, it includes
# the published asset list (including the source H5AD URL and filesize).
DATASET_INDEX_URL = "https://api.cellxgene.cziscience.com/curation/v1/datasets"
DISCOVER_DATASET_URL = "https://cellxgene.cziscience.com/datasets/{dataset_id}"


class CellxGeneDiscoverClient:
    """Read-only client for public CZ CELLxGENE Discover datasets and assets."""

    def __init__(
        self,
        timeout: float = 45.0,
        transport: httpx.BaseTransport | None = None,
        cache: CatalogCache | None = None,
        budget: SearchBudget | None = None,
    ) -> None:
        self.cache = cache or CatalogCache(None if transport else default_cache_dir())
        self.budget = budget
        self.timeout = timeout
        self.last_search = SearchStats()
        self._client = httpx.Client(
            headers={"Accept": "application/json"},
            timeout=timeout,
            transport=transport,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def search_datasets(
        self,
        *,
        tissue: str | None = None,
        disease: str | None = None,
        organism: str | None = None,
        cell_type: str | None = None,
        query: str | None = None,
        assay: str | None = None,
        refresh: bool = False,
        limit: int = 50,
    ) -> list[DatasetRecord]:
        """Fetch the public dataset feed once, filter locally, and normalize records."""
        if not any(
            value and value.strip()
            for value in (tissue, disease, organism, cell_type, query, assay)
        ):
            raise ValueError(
                "Provide at least one CELLxGENE filter: tissue, assay, organism or text."
            )
        stats = self.last_search = SearchStats()
        budget = self.budget or SearchBudget(self.timeout)
        payload = self.cache.get(
            self._client, DATASET_INDEX_URL, budget=budget, stats=stats, refresh=refresh
        )
        if not isinstance(payload, list):
            raise TypeError("CELLxGENE Discover returned an unexpected dataset payload")
        filtered = []
        seen: set[str] = set()
        for item in payload:
            budget.remaining()
            if not isinstance(item, Mapping):
                stats.warn("Non-object catalog entry omitted.")
                continue
            stats.scanned += 1
            if any(
                value and value.strip().casefold() not in ", ".join(_labels(item, field)).casefold()
                for field, value in (
                    ("tissue", tissue),
                    ("disease", disease),
                    ("cell_type", cell_type),
                    ("assay", assay),
                )
            ):
                continue
            if not organism_matches(", ".join(_labels(item, "organism")), organism):
                continue
            if query and query.strip().casefold() not in _search_text(item):
                continue
            if not item.get("dataset_id") and not item.get("id"):
                stats.warn("Catalog entry without a source identifier omitted.")
                continue
            identifier = str(item.get("dataset_id") or item.get("id"))
            if identifier in seen:
                stats.warn(
                    "Duplicate CELLxGENE identifier omitted; first matching record retained."
                )
                continue
            seen.add(identifier)
            filtered.append(item)
        filtered.sort(
            key=lambda item: (
                -(reported_count(item.get("cell_count")) or 0),
                str(item.get("dataset_id") or item.get("id")),
            )
        )
        stats.matched = len(filtered)
        records = [_normalize(item) for item in filtered[: max(1, min(limit, 500))]]
        stats.returned = len(records)
        stats.truncated = stats.matched > stats.returned
        for record in records:
            record.provenance = {
                "metadata_url": DATASET_INDEX_URL,
                "fetched_at": stats.metadata_timestamps[DATASET_INDEX_URL],
                "coverage": stats.scope(),
            }
        return records

    def resolve_assets(self, record: DatasetRecord) -> list[DataAsset]:
        """Normalize published file assets from the CELLxGENE dataset feed."""
        raw_assets = record.raw.get("assets")
        if isinstance(raw_assets, Mapping):
            entries: list[tuple[str | None, Mapping[str, Any]]] = [
                (str(key), value) for key, value in raw_assets.items() if isinstance(value, Mapping)
            ]
        elif isinstance(raw_assets, list):
            entries = [(None, value) for value in raw_assets if isinstance(value, Mapping)]
        else:
            entries = []

        assets: list[DataAsset] = []
        for key, asset in entries:
            url = _first_text(asset, "url", "download_url", "uri")
            if not url:
                continue
            filetype = _first_text(asset, "filetype", "file_type", "type", "format") or key
            name = _first_text(asset, "filename", "name") or _filename_from_url(url)
            is_h5ad = _looks_h5ad(filetype, name, url)
            if not name:
                name = f"{record.dataset_id}.h5ad" if is_h5ad else "dataset asset"
            size = _first_int(asset, "filesize", "file_size", "size", "size_bytes")
            assets.append(
                DataAsset(
                    source="CELLxGENE Discover",
                    dataset_id=record.dataset_id,
                    name=name,
                    download_url=url,
                    size_bytes=size,
                    description=(
                        "Published source H5AD from CZ CELLxGENE Discover"
                        if is_h5ad
                        else _first_text(asset, "description")
                    ),
                    format="h5ad" if is_h5ad else filetype,
                    access_level="public",
                    is_h5ad=is_h5ad,
                    raw=dict(asset),
                )
            )
        # Put the reusable source H5AD first when the API also advertises other assets.
        assets.sort(key=lambda asset: (not asset.is_h5ad, asset.name.casefold()))
        return assets


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [entry for entry in value if isinstance(entry, Mapping)]


def _labels(item: Mapping[str, Any], field: str) -> list[str]:
    return [
        str(entry.get("label")) for entry in _mapping_list(item.get(field)) if entry.get("label")
    ]


def _search_text(item: Mapping[str, Any]) -> str:
    values: list[str] = [
        str(item.get("title") or item.get("name") or ""),
        str(item.get("dataset_id") or item.get("id") or ""),
        str(item.get("collection_id") or ""),
        str(item.get("collection_name") or ""),
    ]
    for field in ("tissue", "disease", "organism", "cell_type", "assay"):
        values.extend(_labels(item, field))
    return " ".join(values).casefold()


def _first_text(item: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _first_int(item: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = item.get(key)
        if reported_count(value) is not None:
            return reported_count(value)
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _filename_from_url(url: str) -> str:
    return url.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]


def _looks_h5ad(*values: str | None) -> bool:
    return any("h5ad" in (value or "").casefold() for value in values)


def _advertises_downloads(item: Mapping[str, Any]) -> bool:
    assets = item.get("assets")
    entries = assets.values() if isinstance(assets, Mapping) else assets
    if not isinstance(entries, (list, tuple)) and not isinstance(assets, Mapping):
        return False
    return any(
        isinstance(asset, Mapping)
        and (_first_text(asset, "url", "download_url", "uri") or "").startswith(
            ("https://", "http://")
        )
        for asset in entries
    )


def _normalize(item: Mapping[str, Any]) -> DatasetRecord:
    dataset_id = str(item.get("dataset_id") or item.get("id") or "")
    title = str(item.get("title") or item.get("name") or dataset_id or "CELLxGENE dataset")
    tissues = _labels(item, "tissue")
    assays = _labels(item, "assay")
    organisms = _labels(item, "organism")
    diseases = _labels(item, "disease")
    explorer_url = item.get("explorer_url")
    portal_url = (
        str(explorer_url) if explorer_url else DISCOVER_DATASET_URL.format(dataset_id=dataset_id)
    )
    raw = dict(item)
    raw["normalized_tissues"] = tissues
    raw["normalized_organisms"] = organisms
    raw["normalized_diseases"] = diseases
    return DatasetRecord(
        source="CELLxGENE Discover",
        dataset_id=dataset_id,
        title=title,
        dataset_type=", ".join(assays) or None,
        organism=", ".join(organisms) or None,
        reported_cell_count=reported_count(item.get("cell_count")),
        cell_count_basis="CELLxGENE cell_count"
        if reported_count(item.get("cell_count")) is not None
        else None,
        asset_status="advertised" if _advertises_downloads(item) else "not_checked",
        acquisition_methods=["Direct download (advertised)"] if _advertises_downloads(item) else [],
        status="Published",
        organ=", ".join(tissues) or None,
        access_level="public",
        portal_url=portal_url,
        raw=raw,
    )


__all__ = ["DATASET_INDEX_URL", "CellxGeneDiscoverClient"]

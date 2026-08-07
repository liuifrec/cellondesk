from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx
from typing_extensions import Self

from cellondesk.models import DataAsset, DatasetRecord

DATASET_INDEX_URL = "https://api.cellxgene.cziscience.com/dp/v1/datasets/index"
DISCOVER_DATASET_URL = "https://cellxgene.cziscience.com/datasets/{dataset_id}"


class CellxGeneDiscoverClient:
    """Read-only client for the public CZ CELLxGENE Discover dataset index."""

    def __init__(
        self,
        timeout: float = 45.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
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
        limit: int = 50,
    ) -> list[DatasetRecord]:
        """Fetch the public index once, filter locally, and return normalized records."""
        if not any(value and value.strip() for value in (tissue, disease, organism, cell_type, query)):
            raise ValueError(
                "Provide at least one CELLxGENE filter: tissue, disease, organism, cell type, or text."
            )
        response = self._client.get(DATASET_INDEX_URL)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise TypeError("CELLxGENE Discover returned an unexpected dataset-index payload")

        filtered = [item for item in payload if isinstance(item, Mapping)]
        for field, value in (
            ("tissue", tissue),
            ("disease", disease),
            ("organism", organism),
            ("cell_type", cell_type),
        ):
            if value and value.strip():
                needle = value.strip().casefold()
                filtered = [
                    item
                    for item in filtered
                    if any(
                        needle in str(entry.get("label") or "").casefold()
                        for entry in _mapping_list(item.get(field))
                    )
                ]

        if query and query.strip():
            needle = query.strip().casefold()
            filtered = [item for item in filtered if needle in _search_text(item)]

        filtered.sort(key=lambda item: int(item.get("cell_count") or 0), reverse=True)
        bounded_limit = max(1, min(limit, 500))
        return [_normalize(item) for item in filtered[:bounded_limit]]

    def resolve_assets(self, record: DatasetRecord) -> list[DataAsset]:
        """Normalize public file assets already published in the Discover index."""
        raw_assets = record.raw.get("assets")
        if isinstance(raw_assets, Mapping):
            entries: list[tuple[str | None, Mapping[str, Any]]] = [
                (str(key), value)
                for key, value in raw_assets.items()
                if isinstance(value, Mapping)
            ]
        elif isinstance(raw_assets, list):
            entries = [
                (None, value)
                for value in raw_assets
                if isinstance(value, Mapping)
            ]
        else:
            entries = []

        assets: list[DataAsset] = []
        for key, asset in entries:
            url = _first_text(asset, "url", "download_url", "uri")
            if not url:
                continue
            filetype = _first_text(asset, "filetype", "file_type", "type", "format") or key
            name = _first_text(asset, "filename", "name") or _filename_from_url(url)
            if not name:
                name = f"{record.dataset_id}.h5ad" if _looks_h5ad(filetype, url) else "dataset asset"
            size = _first_int(asset, "filesize", "file_size", "size", "size_bytes")
            is_h5ad = _looks_h5ad(filetype, name, url)
            assets.append(
                DataAsset(
                    source="CELLxGENE Discover",
                    dataset_id=record.dataset_id,
                    name=name,
                    download_url=url,
                    size_bytes=size,
                    description=_first_text(asset, "description"),
                    format="h5ad" if is_h5ad else filetype,
                    access_level="public",
                    is_h5ad=is_h5ad,
                    raw=dict(asset),
                )
            )
        return assets


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [entry for entry in value if isinstance(entry, Mapping)]


def _labels(item: Mapping[str, Any], field: str) -> list[str]:
    return [
        str(entry.get("label"))
        for entry in _mapping_list(item.get(field))
        if entry.get("label")
    ]


def _search_text(item: Mapping[str, Any]) -> str:
    values: list[str] = [
        str(item.get("name") or ""),
        str(item.get("id") or item.get("dataset_id") or ""),
        str(item.get("collection_id") or ""),
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
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _filename_from_url(url: str) -> str:
    return url.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]


def _looks_h5ad(*values: str | None) -> bool:
    return any("h5ad" in (value or "").casefold() for value in values)


def _normalize(item: Mapping[str, Any]) -> DatasetRecord:
    dataset_id = str(item.get("id") or item.get("dataset_id") or "")
    title = str(item.get("name") or item.get("title") or dataset_id or "CELLxGENE dataset")
    tissues = _labels(item, "tissue")
    assays = _labels(item, "assay")
    organisms = _labels(item, "organism")
    diseases = _labels(item, "disease")
    explorer_url = item.get("explorer_url")
    portal_url = str(explorer_url) if explorer_url else DISCOVER_DATASET_URL.format(dataset_id=dataset_id)
    raw = dict(item)
    raw["normalized_tissues"] = tissues
    raw["normalized_organisms"] = organisms
    raw["normalized_diseases"] = diseases
    return DatasetRecord(
        source="CELLxGENE Discover",
        dataset_id=dataset_id,
        title=title,
        dataset_type=", ".join(assays) or "single-cell",
        status="Published",
        organ=", ".join(tissues) or None,
        access_level="public",
        portal_url=portal_url,
        raw=raw,
    )


__all__ = ["DATASET_INDEX_URL", "CellxGeneDiscoverClient"]

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

import httpx
from typing_extensions import Self

from cellondesk.models import DataAsset, DatasetRecord

DATASET_INDEX_URL = "https://api.cellxgene.cziscience.com/dp/v1/datasets/index"
DISCOVER_DATASET_URL = "https://cellxgene.cziscience.com/datasets/{dataset_id}"
CENSUS_RELEASE_DIRECTORY_URL = (
    "https://census.cellxgene.cziscience.com/cellxgene-census/v1/release.json"
)
CENSUS_MIRRORS_DIRECTORY_URL = (
    "https://census.cellxgene.cziscience.com/cellxgene-census/v1/mirrors.json"
)


class CellxGeneDiscoverClient:
    """Read-only client for public CZ CELLxGENE Discover metadata and source H5ADs."""

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
        """Resolve public Discover assets, then fall back to the Census source H5AD store."""
        assets = self._assets_from_index(record)
        if any(asset.is_h5ad for asset in assets):
            return assets

        census_asset = self._resolve_census_source_h5ad(record)
        if census_asset is not None and census_asset.download_url not in {
            asset.download_url for asset in assets
        }:
            assets.append(census_asset)
        return assets

    def _assets_from_index(self, record: DatasetRecord) -> list[DataAsset]:
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

    def _resolve_census_source_h5ad(self, record: DatasetRecord) -> DataAsset | None:
        if not record.dataset_id:
            return None
        try:
            directory_response = self._client.get(CENSUS_RELEASE_DIRECTORY_URL)
            directory_response.raise_for_status()
            directory = directory_response.json()
            if not isinstance(directory, Mapping):
                return None
            description = _resolve_alias(directory, "stable")
            if not isinstance(description, Mapping):
                return None
            h5ads = description.get("h5ads")
            if not isinstance(h5ads, Mapping):
                return None
            base_uri, region = self._resolve_locator(h5ads)
            if not base_uri:
                return None
            relative_path = str(
                record.raw.get("dataset_h5ad_path") or f"{record.dataset_id}.h5ad"
            ).lstrip("/")
            source_uri = f"{base_uri.rstrip('/')}/{relative_path}"
            url = _public_uri_to_https(source_uri, region)
            if not url:
                return None
            probe = self._probe_public_file(url)
            if probe is None:
                return None
            size_bytes, final_url = probe
        except (httpx.HTTPError, TypeError, ValueError):
            return None

        release_build = description.get("release_build")
        description_text = "Original source H5AD from the CELLxGENE Census public store"
        if release_build:
            description_text += f" (stable release {release_build})"
        return DataAsset(
            source="CELLxGENE Discover",
            dataset_id=record.dataset_id,
            name=f"{record.dataset_id}.h5ad",
            download_url=final_url,
            size_bytes=size_bytes,
            description=description_text,
            format="h5ad",
            access_level="public",
            is_h5ad=True,
            raw={
                "census_release": release_build,
                "source_uri": source_uri,
            },
        )

    def _resolve_locator(self, locator: Mapping[str, Any]) -> tuple[str | None, str | None]:
        uri = _first_text(locator, "uri")
        if uri:
            return uri, _first_text(locator, "s3_region", "region")
        relative_uri = _first_text(locator, "relative_uri")
        if not relative_uri:
            return None, None
        mirrors_response = self._client.get(CENSUS_MIRRORS_DIRECTORY_URL)
        mirrors_response.raise_for_status()
        mirrors = mirrors_response.json()
        if not isinstance(mirrors, Mapping):
            return None, None
        default_name = mirrors.get("default")
        mirror = mirrors.get(default_name) if isinstance(default_name, str) else None
        if not isinstance(mirror, Mapping):
            return None, None
        base_uri = _first_text(mirror, "base_uri")
        if not base_uri:
            return None, None
        return (
            f"{base_uri.rstrip('/')}/{relative_uri.lstrip('/')}",
            _first_text(mirror, "region"),
        )

    def _probe_public_file(self, url: str) -> tuple[int | None, str] | None:
        response = self._client.head(url)
        if response.status_code in {403, 405}:
            response = self._client.get(url, headers={"Range": "bytes=0-0"})
        if response.status_code in {401, 403, 404}:
            return None
        response.raise_for_status()
        return _response_size(response), str(response.url)


def _resolve_alias(directory: Mapping[str, Any], name: str) -> Any:
    value: Any = directory.get(name)
    seen: set[str] = set()
    while isinstance(value, str) and value not in seen:
        seen.add(value)
        value = directory.get(value)
    return value


def _public_uri_to_https(uri: str, region: str | None) -> str | None:
    parsed = urlparse(uri)
    if parsed.scheme in {"http", "https"}:
        return uri
    if parsed.scheme != "s3" or not parsed.netloc:
        return None
    region = region or "us-west-2"
    key = parsed.path.lstrip("/")
    return f"https://{parsed.netloc}.s3.{region}.amazonaws.com/{key}"


def _response_size(response: httpx.Response) -> int | None:
    content_range = response.headers.get("content-range")
    if content_range and "/" in content_range:
        total = content_range.rsplit("/", 1)[-1]
        if total.isdigit():
            return int(total)
    content_length = response.headers.get("content-length")
    if content_length and content_length.isdigit() and response.status_code != 206:
        return int(content_length)
    return None


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


__all__ = [
    "CENSUS_MIRRORS_DIRECTORY_URL",
    "CENSUS_RELEASE_DIRECTORY_URL",
    "DATASET_INDEX_URL",
    "CellxGeneDiscoverClient",
]

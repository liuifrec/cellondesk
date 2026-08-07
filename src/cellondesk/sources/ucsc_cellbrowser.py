from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

import httpx
from typing_extensions import Self

from cellondesk.models import DataAsset, DatasetRecord

ROOT_URL = "https://cells.ucsc.edu"
CATALOG_URL = f"{ROOT_URL}/dataset.json"
_DOWNLOAD_SUFFIXES = (
    ".h5ad",
    ".loom",
    ".mtx",
    ".mtx.gz",
    ".tsv",
    ".tsv.gz",
    ".csv",
    ".csv.gz",
    ".txt",
    ".txt.gz",
)
_CONVENTIONAL_FILES = ("exprMatrix.tsv.gz", "meta.tsv")


class UCSCCellBrowserClient:
    """Small read-only adapter for the public UCSC Cell Browser catalog."""

    def __init__(
        self,
        timeout: float = 30.0,
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

    def _json(self, path: str = "") -> Mapping[str, Any]:
        suffix = f"/{path.strip('/')}" if path.strip("/") else ""
        response = self._client.get(f"{ROOT_URL}{suffix}/dataset.json")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, Mapping):
            raise TypeError("UCSC Cell Browser returned an unexpected catalog payload")
        return payload

    def search_datasets(
        self,
        *,
        query: str | None = None,
        organ: str | None = None,
        organism: str | None = None,
        limit: int = 100,
    ) -> list[DatasetRecord]:
        """Search public Cell Browser collections and expand matching collections."""
        bounded_limit = max(1, min(limit, 500))
        root = self._json()
        top = root.get("datasets", [])
        if not isinstance(top, list):
            return []

        candidates = [
            item
            for item in top
            if isinstance(item, Mapping)
            and _matches(item, query=query, organ=organ, organism=organism)
        ]
        records: list[DatasetRecord] = []
        seen: set[str] = set()
        for item in candidates:
            name = str(item.get("name") or "").strip("/")
            if not name:
                continue
            try:
                payload = self._json(name)
            except (httpx.HTTPError, TypeError):
                payload = {}
            children = payload.get("datasets", []) if isinstance(payload, Mapping) else []
            if isinstance(children, list) and children:
                for child in children:
                    if not isinstance(child, Mapping):
                        continue
                    merged = dict(item)
                    merged.update(child)
                    child_name = str(child.get("name") or "").strip("/")
                    path = f"{name}/{child_name}" if child_name else name
                    if not _matches(merged, query=query, organ=organ, organism=organism):
                        continue
                    record = _normalize(merged, path)
                    if record.dataset_id not in seen:
                        records.append(record)
                        seen.add(record.dataset_id)
                    if len(records) >= bounded_limit:
                        return records
            else:
                merged = dict(item)
                merged.update(payload)
                record = _normalize(merged, name)
                if record.dataset_id not in seen:
                    records.append(record)
                    seen.add(record.dataset_id)
                if len(records) >= bounded_limit:
                    return records
        return records

    def resolve_assets(self, record: DatasetRecord) -> list[DataAsset]:
        """Resolve public matrix/metadata files from Cell Browser dataset metadata."""
        names = _candidate_files(record.raw)
        names.extend(_CONVENTIONAL_FILES)
        names = list(dict.fromkeys(name for name in names if name))
        base = record.dataset_id.strip("/")
        assets: list[DataAsset] = []
        for name in names:
            if not _looks_downloadable(name):
                continue
            url = f"{ROOT_URL}/{base}/{name.lstrip('/')}"
            size = self._probe(url)
            if size is False:
                continue
            is_h5ad = name.casefold().endswith(".h5ad")
            assets.append(
                DataAsset(
                    source="UCSC Cell Browser",
                    dataset_id=record.dataset_id,
                    name=name.rsplit("/", 1)[-1],
                    download_url=url,
                    size_bytes=size if isinstance(size, int) else None,
                    description=_ucsc_description(name),
                    format="h5ad" if is_h5ad else name.rsplit(".", 1)[-1],
                    access_level="public",
                    is_h5ad=is_h5ad,
                    raw={"relative_path": name},
                )
            )
        assets.sort(key=lambda asset: _asset_priority(asset.name))
        return assets

    def _probe(self, url: str) -> int | bool | None:
        try:
            response = self._client.head(url)
            if response.status_code == 405:
                response = self._client.get(url, headers={"Range": "bytes=0-0"})
            if response.status_code == 404:
                return False
            response.raise_for_status()
        except httpx.HTTPError:
            return False
        content_range = response.headers.get("content-range")
        if content_range and "/" in content_range:
            total = content_range.rsplit("/", 1)[-1]
            if total.isdigit():
                return int(total)
        length = response.headers.get("content-length")
        return int(length) if length and length.isdigit() and response.status_code != 206 else None


def _values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        values: list[str] = []
        for nested in value.values():
            values.extend(_values(nested))
        return values
    if isinstance(value, (list, tuple, set)):
        values = []
        for nested in value:
            values.extend(_values(nested))
        return values
    return [str(value)]


def _field(item: Mapping[str, Any], *names: str) -> str | None:
    for name in names:
        if name not in item:
            continue
        values = [text.strip() for text in _values(item.get(name)) if text.strip()]
        if values:
            return ", ".join(dict.fromkeys(values))
    return None


def _haystack(item: Mapping[str, Any]) -> str:
    interesting = (
        "name",
        "shortLabel",
        "label",
        "title",
        "tags",
        "diseases",
        "organisms",
        "body_parts",
        "bodyParts",
        "projects",
        "sources",
        "assays",
    )
    return " ".join(
        text.casefold()
        for key in interesting
        for text in _values(item.get(key))
    )


def _matches(
    item: Mapping[str, Any],
    *,
    query: str | None,
    organ: str | None,
    organism: str | None,
) -> bool:
    haystack = _haystack(item)
    if query and query.strip().casefold() not in haystack:
        return False
    if organ and organ.strip().casefold() not in haystack:
        return False
    return not (organism and organism.strip().casefold() not in haystack)


def _candidate_files(item: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("hasFiles", "files", "downloads", "exprMatrix", "meta", "coords"):
        values.extend(_values(item.get(key)))
    return [value.strip() for value in values if _looks_downloadable(value.strip())]


def _looks_downloadable(value: str) -> bool:
    lower = value.casefold().split("?", 1)[0]
    return lower.endswith(_DOWNLOAD_SUFFIXES)


def _asset_priority(name: str) -> tuple[int, str]:
    """Put analysis-ready/expression files before metadata and coordinates."""
    lower = name.casefold()
    if lower.endswith(".h5ad"):
        return 0, lower
    if "exprmatrix" in lower or lower.endswith((".mtx", ".mtx.gz", ".loom")):
        return 1, lower
    if "meta" in lower:
        return 2, lower
    if "coord" in lower or "umap" in lower or "tsne" in lower:
        return 3, lower
    return 4, lower


def _ucsc_description(name: str) -> str:
    lower = name.casefold()
    if "exprmatrix" in lower or ".mtx" in lower:
        return "Expression matrix"
    if "meta" in lower:
        return "Cell metadata"
    if "coord" in lower or "umap" in lower or "tsne" in lower:
        return "Cell coordinates"
    return "UCSC Cell Browser data file"


def _normalize(item: Mapping[str, Any], path: str) -> DatasetRecord:
    title = _field(item, "shortLabel", "label", "title") or path
    assay = _field(item, "assays", "assay")
    organ = _field(item, "body_parts", "bodyParts", "organ")
    organism = _field(item, "organisms", "organism")
    if organism:
        title = f"{title} [{organism}]"
    encoded = quote(path, safe="/")
    portal = f"{ROOT_URL}/?ds={encoded}"
    return DatasetRecord(
        source="UCSC Cell Browser",
        dataset_id=path,
        title=title,
        dataset_type=assay,
        status="Public",
        organ=organ,
        access_level="public",
        portal_url=portal,
        raw=dict(item),
    )


__all__ = ["UCSCCellBrowserClient"]

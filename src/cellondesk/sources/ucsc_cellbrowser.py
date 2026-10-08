from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote, unquote, urljoin, urlsplit

import httpx
from typing_extensions import Self

from cellondesk.assets import probe_asset
from cellondesk.catalog_cache import (
    CatalogCache,
    SearchBudget,
    SearchStats,
    SearchStopped,
    default_cache_dir,
)
from cellondesk.models import DataAsset, DatasetRecord
from cellondesk.search_metadata import organism_matches, reported_count

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
        cache: CatalogCache | None = None,
        budget: SearchBudget | None = None,
        max_nodes: int = 2000,
    ) -> None:
        self.cache = cache or CatalogCache(None if transport else default_cache_dir())
        self.budget = budget
        self.timeout = timeout
        self.max_nodes = max_nodes
        self.last_search = SearchStats()
        self._budget = budget or SearchBudget(timeout)
        self._refresh = False
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
        payload = self.cache.get(
            self._client,
            f"{ROOT_URL}{suffix}/dataset.json",
            budget=self._budget,
            stats=self.last_search,
            refresh=self._refresh,
        )
        if not isinstance(payload, Mapping):
            raise TypeError("UCSC Cell Browser returned an unexpected catalog payload")
        return payload

    def search_datasets(
        self,
        *,
        query: str | None = None,
        organ: str | None = None,
        organism: str | None = None,
        assay: str | None = None,
        limit: int = 100,
        refresh: bool = False,
    ) -> list[DatasetRecord]:
        """Traverse collections before filtering leaves, including unmatched parents.

        Known leaves use their published catalog summary. Unknown/legacy nodes
        are hydrated to distinguish a dataset from a nested collection. Parent
        biological metadata and observation counts never become child metadata.
        """
        stats = self.last_search = SearchStats()
        self._budget = self.budget or SearchBudget(self.timeout)
        self._refresh = refresh
        bounded_limit = max(1, min(limit, 500))
        root = self._json()
        if not isinstance(root.get("datasets"), list):
            raise TypeError("UCSC catalog has no dataset list")
        pending = [(item, "", (), 0, CATALOG_URL) for item in reversed(root["datasets"])]
        records = []
        seen = set()
        try:
            while pending:
                self._budget.remaining()
                if len(seen) >= self.max_nodes:
                    raise SearchStopped(f"UCSC catalog node limit reached ({self.max_nodes}).")
                item, parent, lineage, depth, listing_url = pending.pop()
                if not isinstance(item, Mapping) or not item.get("name"):
                    stats.warn("UCSC catalog entry without a source identifier omitted.")
                    continue
                name = str(item["name"]).strip("/")
                path = _dataset_path(parent, name) if parent else name
                if path in seen:
                    if path in (*lineage, parent):
                        stats.warn(f"Cyclic UCSC catalog reference omitted: {path}.")
                    continue
                if (
                    depth > 12
                    or any(part in {".", "..", ""} for part in path.split("/"))
                    or any(char in path for char in ("\\", "?", "#", ":"))
                ):
                    stats.warn("Invalid or excessively nested UCSC catalog path omitted.")
                    continue
                seen.add(path)
                metadata = dict(item)
                is_collection = bool(
                    item.get("isCollection")
                    or "datasets" in item
                    or item.get("datasetCount")
                    or item.get("collectionCount")
                )
                url = f"{ROOT_URL}/{quote(path, safe='/')}/dataset.json"
                # sampleCount identifies leaf summaries in the UCSC catalog schema.
                if is_collection or "sampleCount" not in item:
                    try:
                        metadata.update(self._json(quote(path, safe="/")))
                        listing_url = url
                    except (httpx.HTTPError, ValueError, TypeError) as exc:
                        stats.warn(f"Could not read {path}: {exc}")
                if "datasets" in metadata or is_collection:
                    children = metadata.get("datasets")
                    if not isinstance(children, list):
                        stats.warn(f"Collection {path} has no readable child list.")
                        continue
                    available = max(0, self.max_nodes - len(pending) - len(seen))
                    if len(children) > available:
                        stats.warn("UCSC pending catalog node limit reached.")
                    pending.extend(
                        (child, path, (*lineage, path), depth + 1, listing_url)
                        for child in reversed(children[:available])
                    )
                    continue
                stats.scanned += 1
                if not _matches(metadata, query=query, organ=organ, organism=organism, assay=assay):
                    continue
                stats.matched += 1
                if len(records) < bounded_limit:
                    record = _normalize(metadata, path)
                    record.provenance = {
                        "metadata_url": listing_url,
                        "dataset_metadata_url": url,
                        "fetched_at": stats.metadata_timestamps.get(listing_url),
                        "lineage": list(lineage),
                        "scope": "published catalog leaf metadata",
                    }
                    records.append(record)
        except SearchStopped as exc:
            stats.warn(str(exc))
        stats.returned = len(records)
        stats.truncated = stats.matched > stats.returned
        for record in records:
            record.provenance["coverage"] = stats.scope()
        return records

    def resolve_assets(self, record: DatasetRecord) -> list[DataAsset]:
        """Resolve public matrix/metadata files from Cell Browser dataset metadata."""
        self._budget = self.budget or SearchBudget(self.timeout)
        self._refresh = False
        # Child catalogue entries may omit the file inventory; hydrate the leaf.
        metadata = dict(record.raw)
        try:
            metadata.update(self._json(record.dataset_id))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
        names = _candidate_files(metadata)
        names.extend(_CONVENTIONAL_FILES)
        names = list(dict.fromkeys(name for name in names if name))
        base = record.dataset_id.strip("/")
        assets: list[DataAsset] = []
        seen: set[str] = set()
        for name in names:
            if not _looks_downloadable(name):
                continue
            url = _asset_url(base, name)
            if url is None or url in seen:
                continue
            seen.add(url)
            size = self._probe(url)
            if size is False:
                continue
            filename = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
            is_h5ad = filename.casefold().endswith(".h5ad")
            assets.append(
                DataAsset(
                    source="UCSC Cell Browser",
                    dataset_id=record.dataset_id,
                    name=filename,
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
        result = probe_asset(self._client, url)
        return False if result is None else result[0]


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
        facets = item.get("facets")
        value = item.get(name)
        if value is None and isinstance(facets, Mapping):
            value = facets.get(name)
        values = [text.strip() for text in _values(value) if text.strip()]
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
        "facets",
    )
    return " ".join(text.casefold() for key in interesting for text in _values(item.get(key)))


def _matches(
    item: Mapping[str, Any],
    *,
    query: str | None,
    organ: str | None,
    organism: str | None,
    assay: str | None = None,
) -> bool:
    if query and query.strip().casefold() not in _haystack(item):
        return False
    if (
        organ
        and organ.strip().casefold()
        not in (_field(item, "body_parts", "bodyParts", "organ", "tissue") or "").casefold()
    ):
        return False
    if assay and assay.strip().casefold() not in (_field(item, "assays", "assay") or "").casefold():
        return False
    return organism_matches(_field(item, "organisms", "organism"), organism)


def _candidate_files(item: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for key in (
        "hasFiles",
        "files",
        "downloads",
        "exprMatrix",
        "matrixFile",
        "meta",
        "metaFile",
        "coords",
    ):
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
        organism=organism,
        reported_cell_count=reported_count(item.get("sampleCount")),
        cell_count_basis="UCSC sampleCount (matrix observations; may include spots)"
        if reported_count(item.get("sampleCount")) is not None
        else None,
        asset_status="advertised" if _candidate_files(item) else "not_checked",
        acquisition_methods=["Direct download (advertised)"] if _candidate_files(item) else [],
        organ=organ,
        access_level="public",
        portal_url=portal,
        raw=dict(item),
    )


__all__ = ["UCSCCellBrowserClient"]


def _dataset_path(parent: str, child: str) -> str:
    """A catalogue child can already include its full collection path."""
    parent, child = parent.strip("/"), child.strip("/")
    if not child:
        return parent
    if child == parent or child.startswith(parent + "/"):
        return child
    return f"{parent}/{child}"


def _asset_url(dataset_path: str, filename: str) -> str | None:
    """Resolve advertised relative, root-relative, and absolute asset URLs."""
    parts = urlsplit(filename)
    if parts.scheme and parts.scheme not in {"http", "https"}:
        return None
    if parts.username or parts.password:
        return None
    path = unquote(parts.path).replace("\\", "/")
    if any(part == ".." for part in path.split("/")):
        return None
    if (
        not parts.scheme
        and not parts.netloc
        and not path.startswith("/")
        and path.startswith(dataset_path.strip("/") + "/")
    ):
        filename = "/" + filename
    base = f"{ROOT_URL}/{quote(dataset_path.strip('/'), safe='/')}/"
    return urljoin(base, filename)

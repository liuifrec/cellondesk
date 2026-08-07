from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

import httpx
from typing_extensions import Self

from cellondesk.models import DataAsset, DatasetRecord

SEARCH_URL = "https://search.api.hubmapconsortium.org/v3/param-search/datasets"
PORTAL_DATASET_URL = "https://portal.hubmapconsortium.org/browse/dataset/{uuid}"
ASSET_ROOT_URL = "https://assets.hubmapconsortium.org"
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
    "spleen": ("SP",),
}

ASSAY_ALIASES: dict[str, tuple[str, ...]] = {
    "scrna-seq / snrna-seq": (
        "RNAseq",
        "scRNA-seq",
        "snRNA-seq",
        "snRNAseq",
    ),
    "scrna-seq": ("RNAseq", "scRNA-seq"),
    "snrna-seq": ("snRNA-seq", "snRNAseq"),
    "merfish": ("MERFISH", "MERFISH [Salmon]"),
    "maldi ims": ("MALDI IMS", "MALDI-IMS"),
    "maldi": ("MALDI IMS", "MALDI-IMS"),
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
    ) -> None:
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

        response = self._client.get(SEARCH_URL, params=params)
        if response.status_code == 303:
            location = response.headers.get("location")
            # The live parameter-search service occasionally emits an empty 303
            # for a no-match branch of a multi-alias query. Treat it as no hits
            # instead of failing the whole friendly-organ search.
            if not location:
                return []
            response = self._client.get(location)
        if response.status_code == 404:
            return []
        response.raise_for_status()
        return [_normalize_hit(hit) for hit in _extract_hits(response.json())]

    def search_datasets(
        self,
        *,
        dataset_type: str | None = None,
        organ: str | None = None,
        status: str | None = "Published",
        limit: int = 100,
    ) -> list[DatasetRecord]:
        """Search HuBMAP, accepting friendly organ and common assay aliases."""
        bounded_limit = max(1, min(limit, 1000))
        assay_filters = resolve_dataset_type_filters(dataset_type)
        organ_filters = resolve_organ_filters(organ)
        merged: list[DatasetRecord] = []
        seen: set[str] = set()

        for assay_value in assay_filters:
            for organ_value in organ_filters:
                for record in self._search_once(
                    dataset_type=assay_value,
                    organ=organ_value,
                    status=status,
                ):
                    key = record.dataset_id or record.portal_url or record.title
                    if key in seen:
                        continue
                    seen.add(key)
                    merged.append(record)
                    if len(merged) >= bounded_limit:
                        return merged
        return merged[:bounded_limit]

    def resolve_assets(self, record: DatasetRecord) -> list[DataAsset]:
        """Find verified public H5AD products for a HuBMAP record and descendants."""
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
        return assets

    def _probe_asset(self, url: str) -> tuple[int | None, str] | None:
        try:
            response = self._asset_client.head(url)
            if response.status_code in {403, 405}:
                response = self._asset_client.get(url, headers={"Range": "bytes=0-0"})
            if response.status_code in {401, 403, 404}:
                return None
            response.raise_for_status()
        except httpx.HTTPError:
            return None
        size = _response_size(response)
        return size, str(response.url)


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
        own = value.get("uuid") or value.get("id")
        values = [str(own)] if own else []
        for nested in value.values():
            values.extend(_ids(nested))
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
        return [
            x.get("_source", x)
            for x in nested["hits"]
            if isinstance(x, Mapping)
        ]
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
    donor_id = (
        donor.get("hubmap_id")
        if isinstance(donor, Mapping)
        else source.get("donor_id")
    )
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
    "ORGAN_ALIASES",
    "SPATIAL_DATASET_TYPES",
    "HuBMAPClient",
    "resolve_dataset_type_filters",
    "resolve_organ_filters",
]

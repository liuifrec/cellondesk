from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

import httpx
from typing_extensions import Self

from cellondesk.models import DatasetRecord

SEARCH_URL = "https://search.api.hubmapconsortium.org/v3/param-search/datasets"
PORTAL_DATASET_URL = "https://portal.hubmapconsortium.org/browse/dataset/{uuid}"
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

# HuBMAP exposes compact organ codes in its search index. Keep the API codes in
# one place so desktop users can search with ordinary anatomical names.
ORGAN_ALIASES: dict[str, tuple[str, ...]] = {
    "kidney": ("LK", "RK"),
    "left kidney": ("LK",),
    "kidney left": ("LK",),
    "right kidney": ("RK",),
    "kidney right": ("RK",),
    "spleen": ("SP",),
}

# A friendly label can map to several HuBMAP dataset_type values. Exact values
# are still accepted unchanged, which keeps this adapter compatible with new
# assay names appearing in the portal.
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
    """Synchronous client for HuBMAP parameterized dataset search."""

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

    def close(self) -> None:
        self._client.close()

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
            if not location:
                raise httpx.HTTPStatusError(
                    "HuBMAP returned a redirect without a location",
                    request=response.request,
                    response=response,
                )
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
    "ORGAN_ALIASES",
    "SPATIAL_DATASET_TYPES",
    "HuBMAPClient",
    "resolve_dataset_type_filters",
    "resolve_organ_filters",
]

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

import httpx

from cellondesk.models import DatasetRecord

SEARCH_URL = "https://search.api.hubmapconsortium.org/v3/param-search"
PORTAL_DATASET_URL = "https://portal.hubmapconsortium.org/browse/dataset/{uuid}"
SPATIAL_DATASET_TYPES = (
    "Visium (no probes)", "Visium (with probes)", "Slide-seq", "MERFISH",
    "CODEX", "MIBI", "IMC", "MALDI IMS",
)


class HuBMAPClient:
    """Synchronous client for HuBMAP parameterized dataset search."""

    def __init__(self, token: str | None = None, timeout: float = 30.0,
                 transport: httpx.BaseTransport | None = None) -> None:
        headers = {"Accept": "application/json"}
        token = token or os.getenv("HUBMAP_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(headers=headers, timeout=timeout, transport=transport)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HuBMAPClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def search_datasets(self, *, dataset_type: str | None = None,
                        organ: str | None = None, status: str | None = "Published",
                        limit: int = 100) -> list[DatasetRecord]:
        params: dict[str, Any] = {"entity_type": "Dataset", "size": max(1, min(limit, 1000))}
        if dataset_type:
            params["dataset_type"] = dataset_type
        if organ:
            params["organ"] = organ
        if status:
            params["status"] = status
        response = self._client.get(SEARCH_URL, params=params)
        response.raise_for_status()
        return [_normalize_hit(hit) for hit in _extract_hits(response.json())[:limit]]


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
    dataset_id = str(source.get("uuid") or source.get("hubmap_id") or source.get("id") or "")
    title = str(source.get("title") or source.get("dataset_info") or source.get("description")
                or source.get("hubmap_id") or dataset_id or "Untitled HuBMAP dataset")
    donor = source.get("donor")
    donor_id = donor.get("hubmap_id") if isinstance(donor, Mapping) else source.get("donor_id")
    return DatasetRecord(
        source="HuBMAP", dataset_id=dataset_id, title=title,
        dataset_type=_text(source.get("dataset_type")), status=_text(source.get("status")),
        organ=_text(source.get("organ")), donor_id=_text(donor_id),
        doi_url=_text(source.get("doi_url") or source.get("doi")),
        portal_url=PORTAL_DATASET_URL.format(uuid=dataset_id) if dataset_id else None,
        raw=dict(source),
    )


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return ", ".join(str(x) for x in value)
    return str(value)

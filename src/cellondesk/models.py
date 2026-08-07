from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DataAsset(BaseModel):
    """A directly downloadable file exposed by a public data source."""

    source: str
    dataset_id: str
    name: str
    download_url: str | None = None
    size_bytes: int | None = None
    description: str | None = None
    format: str | None = None
    access_level: str | None = None
    is_h5ad: bool = False
    raw: dict[str, Any] = Field(default_factory=dict, repr=False)


class DatasetRecord(BaseModel):
    """Normalized metadata shared by portal adapters."""

    source: str
    dataset_id: str
    title: str
    dataset_type: str | None = None
    status: str | None = None
    organ: str | None = None
    donor_id: str | None = None
    access_level: str | None = None
    doi_url: str | None = None
    portal_url: str | None = None
    download_url: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict, repr=False)


__all__ = ["DataAsset", "DatasetRecord"]

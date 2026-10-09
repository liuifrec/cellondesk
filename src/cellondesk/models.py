from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .modality import ModalityEvidence


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
    organism: str | None = None
    reported_cell_count: int | None = None
    cell_count_basis: str | None = None
    # Publication status and access_level remain independent of file availability.
    asset_status: str = "not_checked"
    acquisition_methods: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    reported_modalities: list[str] = Field(default_factory=list)
    modality_evidence: list[ModalityEvidence] = Field(default_factory=list)
    file_verified_modalities: list[str] = Field(default_factory=list)
    local_inspection_support: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict, repr=False)


__all__ = ["DataAsset", "DatasetRecord"]

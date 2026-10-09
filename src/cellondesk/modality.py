"""Scientific profile contracts. Claims, data and display choices are distinct."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

PROFILE_LABELS = {
    "rna": "RNA / transcriptomics",
    "atac": "ATAC / chromatin accessibility",
    "spatial_transcriptomics": "Spatial transcriptomics",
    "spatial_proteomics": "Spatial proteomics / imaging",
    "multiomics": "Multiomics",
    "spatial_metabolomics": "Spatial metabolomics / molecular ions",
}


class ModalityEvidence(BaseModel):
    profile: str
    origin: Literal["file_annotation", "file_structure", "source_assay", "manual"]
    path: str
    value: str
    scope: str


class ProfileActivation(BaseModel):
    profile: str
    state: Literal["supported", "suggested", "manual"]
    reason: str


class Capability(BaseModel):
    key: str
    title: str
    profiles: list[str] = Field(default_factory=list)
    state: Literal["available", "missing", "unsupported", "invalid"]
    reason: str
    paths: list[str] = Field(default_factory=list)


class FeaturePreview(BaseModel):
    matrix_path: str
    name: str
    feature_index: int
    family: str = "unclassified"
    row_indices: list[int]
    total_rows: int
    values: list[float | None]
    units: str | None = None


class SpatialPreview(BaseModel):
    path: str
    row_indices: list[int]
    total_rows: int
    points: list[list[float]]
    frame: str | None = None
    units: str | None = None
    exclusions: int = 0


class RecordedMetric(BaseModel):
    path: str
    name: str
    row_indices: list[int]
    total_rows: int
    values: list[float | None]


class ImagePreview(BaseModel):
    path: str
    original_shape: list[int]
    preview_shape: list[int]
    data_url: str
    note: str
    frame: str | None = None


class CorrespondenceCheck(BaseModel):
    axis: str
    module: str
    state: Literal["verified", "sample_consistent", "invalid", "unverified"]
    checked: int = 0
    total: int = 0
    present: int = 0
    absent: int = 0
    mismatched: int = 0
    reason: str


class ModuleInventory(BaseModel):
    name: str
    observations: int
    features: int
    profiles: list[str] = Field(default_factory=list)


class ModalityReport(BaseModel):
    schema_version: int = 1
    evidence: list[ModalityEvidence] = Field(default_factory=list)
    profiles: list[ProfileActivation] = Field(default_factory=list)
    capabilities: list[Capability] = Field(default_factory=list)
    feature_previews: list[FeaturePreview] = Field(default_factory=list)
    spatial_previews: list[SpatialPreview] = Field(default_factory=list)
    images: list[ImagePreview] = Field(default_factory=list)
    recorded_metrics: list[RecordedMetric] = Field(default_factory=list)
    correspondence: list[CorrespondenceCheck] = Field(default_factory=list)
    modules: list[ModuleInventory] = Field(default_factory=list)
    manual_overrides: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limits: dict[str, int] = Field(default_factory=dict)


# Display declarations, not computation recipes. Each adapter supplies evidence
# for availability; a profile name alone cannot satisfy a panel's requirements.
PANEL_REGISTRY = {
    "rna_values": (
        "Stored gene-expression features",
        ("rna", "spatial_transcriptomics", "multiomics"),
    ),
    "accessibility": ("Stored peak/accessibility features", ("atac", "multiomics")),
    "protein_values": ("Stored protein / marker features", ("spatial_proteomics", "multiomics")),
    "ion_values": ("Stored molecular-ion features", ("spatial_metabolomics",)),
    "rna_qc": ("Recorded count / feature-detection metadata", ("rna", "spatial_transcriptomics")),
    "atac_qc": ("Recorded TSS, FRiP and fragment metadata", ("atac",)),
    "gene_activity": ("Gene activity", ("atac", "multiomics")),
    "spatial_coordinates": (
        "Spatial coordinates",
        ("spatial_transcriptomics", "spatial_proteomics", "spatial_metabolomics"),
    ),
    "tissue_image": ("Embedded image preview", ("spatial_transcriptomics", "spatial_proteomics")),
    "image_overlay": (
        "Registered image overlay",
        ("spatial_transcriptomics", "spatial_proteomics"),
    ),
    "segmentation": ("Segmentation geometry", ("spatial_proteomics",)),
    "neighborhoods": ("Cellular neighborhoods", ("spatial_proteomics",)),
    "joint_views": ("Cross-modality comparisons", ("multiomics",)),
    "mass_spectra": ("Mass spectra / ion identification", ("spatial_metabolomics",)),
}


def assay_profiles(assay: str | None) -> list[str]:
    """Conservative hints from assay metadata only; never title/tissue guesses."""
    value = (assay or "").casefold()
    profiles = set()
    if re.search(r"rna.?seq|transcriptom|gene expression|10x\s+[35]['′]|cite.?seq", value):
        profiles.add("rna")
    if "atac" in value or "chromatin accessibility" in value:
        profiles.add("atac")
    if any(
        term in value
        for term in (
            "visium",
            "merfish",
            "seqfish",
            "xenium",
            "slide-seq",
            "slideseq",
            "spatial transcript",
        )
    ):
        profiles.update(("rna", "spatial_transcriptomics"))
    if (
        any(
            term in value
            for term in (
                "codex",
                "mibi",
                "imaging mass cytometry",
                "cycif",
                "phenocycler",
                "spatial proteom",
            )
        )
        or value.strip() == "imc"
    ):
        profiles.add("spatial_proteomics")
    if any(term in value for term in ("spatial metabol", "maldi ims", "maldi-ims", "desi imaging")):
        profiles.add("spatial_metabolomics")
    if "multiome" in value or "multiomic" in value:
        profiles.add("multiomics")
    if re.search(r"cite.?seq", value) or ("rna" in profiles and "atac" in profiles):
        profiles.add("multiomics")
    return [key for key in PROFILE_LABELS if key in profiles]


def apply_overrides(report: ModalityReport, overrides: list[str] | tuple[str, ...] | None) -> None:
    choices = list(dict.fromkeys(overrides or []))
    unknown = set(choices) - PROFILE_LABELS.keys()
    if unknown:
        raise ValueError(f"Unknown scientific profiles: {', '.join(sorted(unknown))}")
    report.manual_overrides = choices
    for key in choices:
        report.evidence.append(
            ModalityEvidence(
                profile=key,
                origin="manual",
                path="inspection options",
                value=key,
                scope="User interpretation; does not verify measurements or enable missing data",
            )
        )
        if not any(p.profile == key for p in report.profiles):
            report.profiles.append(
                ProfileActivation(
                    profile=key,
                    state="manual",
                    reason="Manual interpretation; file evidence remains unchanged.",
                )
            )


def capability(key: str, state: str, reason: str, paths: list[str] | None = None) -> Capability:
    title, profiles = PANEL_REGISTRY[key]
    return Capability(
        key=key, title=title, profiles=list(profiles), state=state, reason=reason, paths=paths or []
    )

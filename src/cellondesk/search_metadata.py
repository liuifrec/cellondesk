"""Conservative scientific normalization shared by discovery adapters."""

from __future__ import annotations

from typing import Any


def reported_count(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    if isinstance(value, str) and value.isascii() and value.isdigit():
        return int(value)
    return None


def organism_matches(value: str | None, query: str | None) -> bool:
    if not query or not query.strip():
        return True
    aliases = {
        "human": "homo sapiens",
        "9606": "homo sapiens",
        "human (h. sapiens)": "homo sapiens",
        "h. sapiens": "homo sapiens",
        "mouse": "mus musculus",
        "10090": "mus musculus",
        "mouse (m. musculus)": "mus musculus",
        "m. musculus": "mus musculus",
    }
    needle = aliases.get(query.strip().casefold(), query.strip().casefold())
    # Repository labels can themselves be common names.
    values = [part.strip().casefold() for part in (value or "").split(",")]
    return any(needle in aliases.get(part, part) for part in values)


def annotate_modalities(record):
    """Source assay hints and advertised format support, never file verification."""
    from .modality import ModalityEvidence, assay_profiles
    from .scientific_formats import inspection_support

    record.reported_modalities = assay_profiles(record.dataset_type)
    record.modality_evidence = [
        ModalityEvidence(
            profile=profile,
            origin="source_assay",
            path="repository assay metadata",
            value=record.dataset_type or "",
            scope="Assay-derived discovery hint; remote file measurements/capabilities not verified",
        )
        for profile in record.reported_modalities
    ]
    filenames = []
    assets = record.raw.get("assets", [])
    if isinstance(assets, dict):
        assets = list(assets.values())
    if isinstance(assets, list):
        for asset in assets:
            if isinstance(asset, dict):
                for key in ("url", "filename", "name", "download_url"):
                    if isinstance(asset.get(key), str):
                        filenames.append(asset[key])
                if isinstance(asset.get("filetype"), str):
                    filenames.append("asset." + asset["filetype"].lower())
    for key in ("hasFiles", "files"):
        values = record.raw.get(key)
        if isinstance(values, list):
            filenames.extend(value for value in values if isinstance(value, str))
    record.local_inspection_support = inspection_support(filenames)
    return record

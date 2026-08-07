from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .models import DatasetRecord


def _hubmap_transfer_id(record: DatasetRecord) -> str | None:
    """Return the public HuBMAP ID expected by CLT manifests when available."""
    raw: Mapping[str, Any] = record.raw
    hubmap_id = raw.get("hubmap_id")
    if hubmap_id and str(hubmap_id).strip():
        return str(hubmap_id).strip()
    # Some callers may already normalize dataset_id to the HBM identifier.
    if record.dataset_id.upper().startswith("HBM"):
        return record.dataset_id
    return None


def hubmap_manifest_lines(
    records: Iterable[DatasetRecord], resource_path: str = "/"
) -> list[str]:
    path = resource_path if resource_path.startswith("/") else f"/{resource_path}"
    lines: list[str] = []
    seen: set[str] = set()
    for record in records:
        if record.source != "HuBMAP":
            continue
        transfer_id = _hubmap_transfer_id(record)
        if not transfer_id:
            continue
        line = f"{transfer_id}\t{path}"
        if line not in seen:
            lines.append(line)
            seen.add(line)
    return lines


def write_hubmap_manifest(
    records: Iterable[DatasetRecord],
    destination: str | Path,
    resource_path: str = "/",
) -> Path:
    destination = Path(destination)
    lines = hubmap_manifest_lines(records, resource_path)
    destination.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return destination


__all__ = ["hubmap_manifest_lines", "write_hubmap_manifest"]

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .models import DatasetRecord


def hubmap_manifest_lines(records: Iterable[DatasetRecord], resource_path: str = "/") -> list[str]:
    path = resource_path if resource_path.startswith("/") else f"/{resource_path}"
    lines: list[str] = []
    seen: set[str] = set()
    for record in records:
        if record.source != "HuBMAP" or not record.dataset_id:
            continue
        line = f"{record.dataset_id}\t{path}"
        if line not in seen:
            lines.append(line)
            seen.add(line)
    return lines


def write_hubmap_manifest(records: Iterable[DatasetRecord], destination: str | Path,
                           resource_path: str = "/") -> Path:
    destination = Path(destination)
    lines = hubmap_manifest_lines(records, resource_path)
    destination.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return destination

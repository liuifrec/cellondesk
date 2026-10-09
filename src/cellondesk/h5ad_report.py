"""Assemble packaged dashboard components into a single portable HTML document."""

from __future__ import annotations

import html
import json
from importlib.resources import files
from pathlib import Path
from string import Template
from typing import Any

from ._version import __version__
from .inspection import H5ADInspection
from .modality_report import scientific_markup


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _format_bytes(value: int) -> str:
    amount = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(amount) < 1024 or unit == "TiB":
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{value} B"


def _format_number(value: float | None) -> str:
    return "Not available" if value is None else f"{value:,.5g}"


def _column_rows(columns: list[Any]) -> str:
    rows = []
    for column in columns:
        top = ", ".join(
            f"{'∅ missing' if item.is_missing else item.value} ({item.count:,})"
            for item in column.top_values[:5]
        )
        detail = (
            f"median {_format_number(column.numeric.median)}; "
            f"p05–p95 {_format_number(column.numeric.p05)}–"
            f"{_format_number(column.numeric.p95)}"
            if column.numeric
            else top or "No non-missing values"
        )
        coverage = "Sampled" if column.sampled else "All rows"
        if column.sampled_values is not None:
            coverage += f" · {column.sampled_values:,} / {column.total_values:,}"
        else:
            coverage += " · count not recorded"
        rows.append(
            "<tr>"
            + "".join(
                f"<td>{_escape(value)}</td>"
                for value in (
                    column.name,
                    column.dtype,
                    column.encoding,
                    coverage,
                    column.missing_values if column.missing_values is not None else "Not recorded",
                    detail,
                )
            )
            + "</tr>"
        )
    return "".join(rows) or '<tr><td colspan="6">No detailed columns available.</td></tr>'


def _kv(rows: list[tuple[str, object]]) -> str:
    return "".join(
        f'<tr><th scope="row">{_escape(key)}</th><td>{_escape(value)}</td></tr>'
        for key, value in rows
    )


def render_h5ad_report(
    inspection: H5ADInspection,
    *,
    title: str | None = None,
) -> str:
    """Render offline HTML without reading or modifying the source H5AD."""
    if title is None:
        title = f"CellOnDesk {inspection.storage_format} Summary"
    resources = files("cellondesk").joinpath("report_assets", "h5ad")
    template = Template(resources.joinpath("shell.html").read_text(encoding="utf-8"))
    # Escape all markup delimiters, including script endings and HTML comments.
    payload = json.dumps(
        inspection.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    for char, escaped in (
        ("&", "\\u0026"),
        ("<", "\\u003c"),
        (">", "\\u003e"),
        ("\u2028", "\\u2028"),
        ("\u2029", "\\u2029"),
    ):
        payload = payload.replace(char, escaped)
    matrix, provenance = inspection.matrix, inspection.provenance
    sample = inspection.obs_sample
    coverage = (
        f"{'Sampled' if len(sample.row_indices) < inspection.n_obs else 'All rows'}: "
        f"{len(sample.row_indices):,} / {inspection.n_obs:,} observations for metadata charts. "
        "Missing values remain in composition denominators."
        if sample
        else "Metadata chart coverage was not recorded by this older inspection."
    )
    notes = list(inspection.warnings)
    if inspection.scientific:
        notes.extend(inspection.scientific.warnings)
        notes.extend(c.reason for c in inspection.scientific.capabilities if c.state == "invalid")
    warnings = "".join(f"<li>{_escape(note)}</li>" for note in dict.fromkeys(notes))
    warnings = warnings or "<li>No issues detected within the bounded inspection scope.</li>"
    matrix_rows = _kv(
        [
            ("Shape", f"{matrix.shape[0]:,} × {matrix.shape[1]:,}"),
            ("Encoding / dtype", f"{matrix.encoding} / {matrix.dtype or 'not recorded'}"),
            ("Stored entries", f"{matrix.nnz:,}" if matrix.nnz is not None else "Not available"),
            (
                "Stored-entry ratio" if matrix.nnz is not None else "Finite block nonzero fraction",
                f"{100 * matrix.density:.3f}%" if matrix.density is not None else "Not available",
            ),
            (
                "Finite values in X sample",
                matrix.sample_total if matrix.sample_total is not None else "Not available",
            ),
            (
                "Sample range",
                (
                    f"{_format_number(matrix.sample_minimum)} to "
                    f"{_format_number(matrix.sample_maximum)}"
                ),
            ),
            ("Sample mean", _format_number(matrix.sample_mean)),
            ("Sampling scope", matrix.sample_scope),
        ]
    )
    structures = _kv(
        [
            ("Detected annotation", inspection.likely_annotation or "Not detected"),
            ("Layers", ", ".join(inspection.layers) or "None"),
            ("obsm", ", ".join(inspection.obsm) or "None"),
            ("uns keys", ", ".join(inspection.uns) or "None"),
            ("raw", "Present (not summarized)" if inspection.has_raw else "Absent"),
        ]
    )
    provenance_rows: list[tuple[str, object]] = [
        ("Source path", inspection.source_path),
        ("Source size", f"{inspection.file_size_bytes:,} bytes"),
        ("Report renderer", f"CellOnDesk {__version__}"),
        ("Report schema", inspection.schema_version),
        ("Reader", "Direct HDF5; source opened read-only; full X never loaded"),
    ]
    if provenance:
        provenance_rows.extend(
            [
                ("Inspection generator", f"CellOnDesk {provenance.generator_version}"),
                ("Inspected at (UTC)", provenance.inspected_at),
                ("Source mtime (ns since epoch)", provenance.source_mtime_ns),
                (
                    "Source stat comparison",
                    "Size, mtime and identity unchanged during inspection"
                    if provenance.source_stat_unchanged
                    else "CHANGED during inspection",
                ),
                ("H5AD encoding", f"{provenance.encoding_type} / {provenance.encoding_version}"),
                ("Dependencies", "; ".join(f"{k} {v}" for k, v in provenance.dependencies.items())),
                (
                    "Configured limits",
                    "; ".join(f"{k}={v:,}" for k, v in provenance.limits.items()),
                ),
                ("Integrity scope", provenance.integrity_scope),
            ]
        )
    else:
        provenance_rows.append(("Inspection provenance", "Not recorded by this older inspection"))
    return template.substitute(
        title=_escape(title),
        file_name=_escape(inspection.file_name),
        version=__version__,
        css=resources.joinpath("dashboard.css").read_text(encoding="utf-8"),
        scripts="\n".join(
            resources.joinpath(name).read_text(encoding="utf-8")
            for name in (
                "core.js",
                "embeddings.js",
                "composition.js",
                "qc.js",
                "modalities.js",
                "dashboard.js",
            )
        ),
        payload=payload,
        storage_format=_escape(inspection.storage_format),
        scientific_markup=scientific_markup(inspection.scientific),
        n_obs=f"{inspection.n_obs:,}",
        n_vars=f"{inspection.n_vars:,}",
        file_size=_format_bytes(inspection.file_size_bytes),
        sample_count=f"{len(sample.row_indices):,}" if sample else "Not recorded",
        coverage=_escape(coverage),
        sampling_note=(
            "Row sampling is deterministic, not random; rare populations may be missed."
            if sample and len(sample.row_indices) < sample.total_rows
            else "Each view states its coverage and any exclusions; metadata and embedding "
            "samples can differ."
        ),
        matrix_rows=matrix_rows,
        structures=structures,
        warnings=warnings,
        provenance_rows=_kv(provenance_rows),
        obs_count=len(inspection.obs_column_names),
        var_count=len(inspection.var_column_names),
        obs_shown=len(inspection.obs_columns),
        var_shown=len(inspection.var_columns),
        obs_rows=_column_rows(inspection.obs_columns),
        var_rows=_column_rows(inspection.var_columns),
    )


def write_h5ad_report(
    inspection: H5ADInspection,
    destination: str | Path,
    *,
    title: str | None = None,
) -> Path:
    destination = validate_export_destination(inspection, destination)
    destination.write_text(render_h5ad_report(inspection, title=title), encoding="utf-8")
    return destination


def validate_export_destination(inspection: H5ADInspection, destination: str | Path) -> Path:
    """Protect the source, including symlink/hardlink aliases, for HTML and JSON exports."""
    destination = Path(destination)
    source = Path(inspection.source_path).expanduser().resolve()
    if destination.resolve() == source or (
        destination.exists() and source.exists() and destination.samefile(source)
    ):
        raise ValueError("Export destination must not overwrite the source H5AD")
    if destination.suffix.lower() in {".h5ad", ".h5mu", ".zarr", ".imzml", ".ibd", ".tif", ".tiff"}:
        raise ValueError("Export destination must not have an .h5ad or other scientific source extension")
    return destination

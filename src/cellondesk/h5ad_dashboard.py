"""Bounded dashboard data preparation, independent of HTML rendering."""

from __future__ import annotations

from typing import Any

from .h5ad_access import _encoding, _field
from .inspection import (
    ColumnSummary,
    Histogram,
    ObservationColumn,
    ObservationSample,
    _node_length,
    _read_node_values,
    _shape_from_node,
    _summarize_column,
)


def numeric_histogram(finite: Any, np: Any) -> Histogram:
    """Equal-width finite-value bins, with a closed final right edge."""
    low, high = float(np.min(finite)), float(np.max(finite))
    if low == high:
        # A degenerate single bin avoids invented ranges for constant metadata.
        return Histogram(edges=[low, high], counts=[int(finite.size)])
    bins = min(30, max(1, int(np.ceil(np.sqrt(finite.size)))))
    # The convex combination avoids overflow in high - low for extreme metadata.
    weights = np.linspace(0.0, 1.0, bins + 1)
    edges = np.unique(low * (1.0 - weights) + high * weights)
    edges[0], edges[-1] = low, high
    counts, edges = np.histogram(finite, bins=edges)
    return Histogram(edges=edges.tolist(), counts=counts.tolist())


def _validate_column(node: Any, total: int) -> None:
    if _node_length(node) != total:
        raise ValueError(f"row count {_node_length(node)} does not match axis length {total}")
    if hasattr(node, "dtype"):
        if len(_shape_from_node(node)) != 1:
            raise ValueError("metadata must be one-dimensional")
        if node.dtype.kind not in "biufOSU":
            raise ValueError(f"unsupported metadata dtype {node.dtype}")
    elif hasattr(node, "keys"):
        if _encoding(node).startswith("nullable") and "mask" not in node:
            raise ValueError("nullable metadata is missing its mask")
        for key in ("codes", "values", "mask"):
            if key in node and _shape_from_node(node[key]) != (total,):
                raise ValueError(f"{key} shape does not match the metadata axis")
        if "categories" in node and len(_shape_from_node(node["categories"])) != 1:
            raise ValueError("category dictionary must be one-dimensional")
        if "mask" in node and node["mask"].dtype.kind != "b":
            raise ValueError("nullable mask must be boolean")
        if "values" in node and node["values"].dtype.kind not in "biufOSU":
            raise ValueError("unsupported nullable value dtype")


def observation_sample(
    table: Any,
    names: list[str],
    *,
    total: int,
    indices: Any,
    np: Any,
    warnings: list[str],
    axis: str = "obs",
) -> tuple[ObservationSample, list[ColumnSummary]]:
    columns: list[ObservationColumn] = []
    summaries: list[ColumnSummary] = []
    for name in names:
        try:
            node = _field(table, name)
            _validate_column(node, total)
            values = _read_node_values(node, indices, np)
            if len(values) != len(indices):
                raise ValueError("sample length does not match row identities")
            if _encoding(node) != "categorical" and any(
                isinstance(value, int) and abs(value) > 2**53 - 1 for value in values
            ):
                raise ValueError("integer values exceed exact browser numeric precision (2^53−1)")
            summary = _summarize_column(
                name,
                node,
                max_values=max(1, len(indices)),
                max_top_values=12,
                np=np,
                values=values,
            )
            numeric = summary.numeric is not None
            clean = []
            for value in values:
                if value is None or (
                    isinstance(value, (float, np.floating)) and not np.isfinite(value)
                ):
                    clean.append(None)
                else:
                    clean.append(float(value) if numeric else str(value))
            columns.append(
                ObservationColumn(
                    name=name,
                    kind="numeric" if numeric else "categorical",
                    values=clean,
                )
            )
            summaries.append(summary)
        except (KeyError, TypeError, ValueError, IndexError, OSError, OverflowError) as exc:
            warnings.append(f"Skipped {axis} field {name!r}: {exc}.")
    return ObservationSample(
        total_rows=total,
        row_indices=indices.tolist(),
        columns=columns,
    ), summaries


def matrix_warnings(handle: Any, shape: tuple[int, int]) -> list[str]:
    """Cheap structural checks only; never scan all sparse entries/pointers."""
    warnings: list[str] = []
    if "X" not in handle:
        return ["Expression matrix X is absent; no expression statistics are available."]
    node = handle["X"]
    if _shape_from_node(node) != shape:
        warnings.append("X shape does not match the obs/var axis lengths.")
    if hasattr(node, "keys") and "data" in node:
        encoding = _encoding(node)
        if encoding not in {"csr_matrix", "csc_matrix"}:
            warnings.append("Sparse X encoding is unrecognized; stored-entry statistics only.")
        for key in ("data", "indices", "indptr"):
            if key not in node or len(_shape_from_node(node[key])) != 1:
                warnings.append(f"Sparse X has a missing or non-vector {key} array.")
                return warnings
        nnz = len(node["data"])
        if len(node["indices"]) != nnz:
            warnings.append("Sparse X data and indices lengths differ.")
        major = shape[1] if encoding == "csc_matrix" else shape[0]
        pointers = node["indptr"]
        if len(pointers) != major + 1:
            warnings.append("Sparse X indptr length does not match its major axis.")
        if len(pointers) and (pointers[0] != 0 or pointers[-1] != nnz):
            warnings.append("Sparse X indptr endpoints do not match stored entries.")
        if node["indices"].dtype.kind not in "iu" or pointers.dtype.kind not in "iu":
            warnings.append("Sparse X indices/pointers are not integer arrays.")
    return warnings

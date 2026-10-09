from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .modality import ModalityReport


class ValueCount(BaseModel):
    value: str
    count: int
    is_missing: bool = False


class Histogram(BaseModel):
    edges: list[float] = Field(default_factory=list)
    counts: list[int] = Field(default_factory=list)
    # All bins are [left, right), except the final bin, which includes right.
    last_bin_closed: bool = True


class NumericSummary(BaseModel):
    count: int
    missing: int
    minimum: float | None = None
    maximum: float | None = None
    mean: float | None = None
    p05: float | None = None
    median: float | None = None
    p95: float | None = None
    histogram: Histogram | None = None


class ColumnSummary(BaseModel):
    name: str
    dtype: str
    encoding: str
    sampled: bool = False
    non_null: int | None = None
    unique: int | None = None
    top_values: list[ValueCount] = Field(default_factory=list)
    numeric: NumericSummary | None = None
    total_values: int | None = None
    sampled_values: int | None = None
    missing_values: int | None = None


class MatrixSummary(BaseModel):
    shape: tuple[int, int]
    encoding: str
    dtype: str | None = None
    nnz: int | None = None
    density: float | None = None
    sample_nonzero: int | None = None
    sample_total: int | None = None
    sample_minimum: float | None = None
    sample_maximum: float | None = None
    sample_mean: float | None = None
    sample_scope: str = "Not recorded by this inspection"
    sampled_entries: int | None = None
    nonfinite_entries: int | None = None


class ObservationColumn(BaseModel):
    name: str
    kind: Literal["categorical", "numeric"]
    values: list[float | str | None] = Field(default_factory=list)


class ObservationSample(BaseModel):
    total_rows: int
    row_indices: list[int] = Field(default_factory=list)
    columns: list[ObservationColumn] = Field(default_factory=list)
    method: str = "Deterministic evenly spaced rows; not a random sample"


class InspectionProvenance(BaseModel):
    generator_version: str
    inspected_at: str
    source_mtime_ns: int
    source_stat_unchanged: bool
    encoding_type: str
    encoding_version: str
    limits: dict[str, int] = Field(default_factory=dict)
    dependencies: dict[str, str] = Field(default_factory=dict)
    read_only: bool = True
    integrity_scope: str = (
        "Bounded structural and sampled-value checks only; no checksum, full sparse "
        "pointer/index validation or exhaustive scan of unsampled values. "
        "Unchanged file size/mtime is not proof of content integrity."
    )


class EmbeddingPreview(BaseModel):
    key: str
    total_points: int
    dimensions: int
    sampled_points: list[list[float]] = Field(default_factory=list)
    color_field: str | None = None
    color_values: list[str] = Field(default_factory=list)
    row_indices: list[int] = Field(default_factory=list)
    candidate_points: int | None = None
    dropped_nonfinite: int | None = None


class H5ADInspection(BaseModel):
    source_path: str
    file_name: str
    file_size_bytes: int
    n_obs: int
    n_vars: int
    matrix: MatrixSummary
    obs_column_names: list[str] = Field(default_factory=list)
    var_column_names: list[str] = Field(default_factory=list)
    obs_columns: list[ColumnSummary] = Field(default_factory=list)
    var_columns: list[ColumnSummary] = Field(default_factory=list)
    layers: list[str] = Field(default_factory=list)
    obsm: list[str] = Field(default_factory=list)
    uns: list[str] = Field(default_factory=list)
    has_raw: bool = False
    likely_annotation: str | None = None
    embeddings: list[EmbeddingPreview] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    schema_version: int = 2
    obs_sample: ObservationSample | None = None
    embedding_metadata: ObservationSample | None = None
    provenance: InspectionProvenance | None = None
    storage_format: str = "H5AD"
    scientific: ModalityReport | None = None


_ANNOTATION_CANDIDATES = (
    "cell_type",
    "celltype",
    "cell_type_ontology_term_id",
    "cell_type_annotation",
    "annotation",
    "major_cell_type",
    "celltype_l2",
    "cluster",
    "leiden",
    "louvain",
)


def _require_data_dependencies() -> tuple[Any, Any]:
    try:
        import h5py
        import numpy as np
    except ImportError as exc:  # pragma: no cover - optional environment
        raise RuntimeError('Install H5AD support with: pip install "cellondesk[data]"') from exc
    return h5py, np


def _decode_scalar(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if hasattr(value, "item"):
        try:
            return value.item()
        except ValueError:
            pass
    return value


def _decode_array(values: Any) -> list[Any]:
    return [_decode_scalar(value) for value in values]


def _encoding(node: Any) -> str:
    from .h5ad_access import _encoding as encoding

    return encoding(node)


def _shape_from_node(node: Any) -> tuple[int, ...]:
    if hasattr(node, "shape"):
        return tuple(int(value) for value in (node.shape or ()))
    shape = node.attrs.get("shape", node.attrs.get("h5sparse_shape"))
    if shape is not None:
        return tuple(int(value) for value in shape)
    return ()


def _axis_column_names(group: Any) -> list[str]:
    from .h5ad_access import _axis_column_names as column_names

    return column_names(group)


def _axis_length(group: Any) -> int:
    from .h5ad_access import _axis_length as axis_length

    return axis_length(group)


def _node_length(node: Any) -> int:
    shape = _shape_from_node(node)
    if shape:
        return shape[0]
    if hasattr(node, "keys") and "codes" in node:
        shape = _shape_from_node(node["codes"])
        return shape[0] if shape else 0
    if hasattr(node, "keys") and "values" in node:
        shape = _shape_from_node(node["values"])
        return shape[0] if shape else 0
    return 0


def _sample_indices(length: int, maximum: int, np: Any) -> Any:
    if length <= 0:
        return np.asarray([], dtype=int)
    if length <= maximum:
        return np.arange(length, dtype=int)
    return np.unique(np.linspace(0, length - 1, maximum, dtype=int))


def _read_categories(categories: Any, codes: Any, np: Any) -> list[Any]:
    """Read only category labels needed by the sampled codes."""
    if not np.issubdtype(codes.dtype, np.integer):
        raise ValueError("Categorical codes must be integers")
    if np.any(codes < -1) or np.any(codes >= len(categories)):
        raise ValueError("Categorical codes are outside the category dictionary")
    wanted = np.unique(codes[codes >= 0]).astype(np.int64)
    labels = _decode_array(categories[wanted]) if len(wanted) else []
    lookup = dict(zip(wanted.tolist(), labels))
    return [lookup[int(code)] if int(code) >= 0 else None for code in codes]


def _read_node_values(node: Any, indices: Any, np: Any) -> list[Any]:
    encoding = _encoding(node)
    if encoding == "categorical" or (hasattr(node, "keys") and "codes" in node):
        codes = np.asarray(node["codes"][indices])
        return _read_categories(node["categories"], codes, np)
    if hasattr(node, "keys") and "values" in node:
        values = np.asarray(node["values"][indices])
        mask = np.asarray(node["mask"][indices]) if "mask" in node else None
        result: list[Any] = []
        for position, value in enumerate(values):
            if mask is not None and bool(mask[position]):
                result.append(None)
            else:
                result.append(_decode_scalar(value))
        return result
    if hasattr(node, "dtype"):
        return _decode_array(node[indices])
    raise ValueError(f"Unsupported metadata encoding: {encoding}")


def _finite_mean(finite: Any, np: Any) -> float | None:
    if not finite.size:
        return None
    with np.errstate(over="ignore", invalid="ignore"):
        mean = float(np.mean(finite))
    if not np.isfinite(mean):
        scale = float(np.max(np.abs(finite)))
        mean = float(np.mean(finite / scale) * scale) if scale else 0.0
    return mean


def _summarize_column(
    name: str,
    node: Any,
    *,
    max_values: int,
    max_top_values: int,
    np: Any,
    values: list[Any] | None = None,
) -> ColumnSummary:
    length = _node_length(node)
    indices = _sample_indices(length, max_values, np)
    if values is None:
        values = _read_node_values(node, indices, np)
    sampled = len(values) < length
    dtype = "unknown"
    if hasattr(node, "dtype"):
        dtype = str(node.dtype)
    elif hasattr(node, "keys") and "codes" in node:
        dtype = "category"
    elif hasattr(node, "keys") and "values" in node:
        dtype = str(node["values"].dtype)

    # NaN/Inf are missing for numeric summaries, not distinct category values.
    non_missing = [
        value
        for value in values
        if value is not None
        and not (isinstance(value, (float, np.floating)) and not np.isfinite(value))
    ]
    non_null = len(non_missing)
    encoding = _encoding(node)
    coverage = {
        "total_values": length,
        "sampled_values": len(values),
        "missing_values": len(values) - non_null,
    }

    numeric_values: list[float] = []
    numeric = encoding != "categorical" and dtype != "category"
    for value in non_missing if numeric else []:
        if isinstance(value, (bool, str, bytes)):
            numeric = False
            break
        try:
            numeric_values.append(float(value))
        except (TypeError, ValueError):
            numeric = False
            break

    if numeric and (numeric_values or dtype.startswith(("float", "int", "uint"))):
        array = np.asarray(numeric_values, dtype=float)
        finite = array[np.isfinite(array)]
        if finite.size:
            with np.errstate(over="ignore", invalid="ignore"):
                quantiles = np.quantile(finite, [0.05, 0.5, 0.95])
            if not np.isfinite(quantiles).all():
                scale = float(np.max(np.abs(finite)))
                quantiles = np.quantile(finite / scale, [0.05, 0.5, 0.95]) * scale
            from .h5ad_dashboard import numeric_histogram

            numeric_summary = NumericSummary(
                count=int(finite.size),
                missing=len(values) - int(finite.size),
                minimum=float(np.min(finite)),
                maximum=float(np.max(finite)),
                mean=_finite_mean(finite, np),
                p05=float(quantiles[0]),
                median=float(quantiles[1]),
                p95=float(quantiles[2]),
                histogram=numeric_histogram(finite, np),
            )
        else:
            numeric_summary = NumericSummary(count=0, missing=len(values))
        return ColumnSummary(
            name=name,
            dtype=dtype,
            encoding=encoding,
            sampled=sampled,
            non_null=non_null,
            unique=len(set(numeric_values)),
            numeric=numeric_summary,
            **coverage,
        )

    labels = [str(value) for value in non_missing]
    counts = Counter(labels)
    unique = len(counts)
    top_values = [
        ValueCount(value=value, count=count) for value, count in counts.most_common(max_top_values)
    ]
    if len(non_missing) < len(values):
        top_values.append(
            ValueCount(
                value="Missing",
                count=len(values) - len(non_missing),
                is_missing=True,
            )
        )
    return ColumnSummary(
        name=name,
        dtype=dtype,
        encoding=encoding,
        sampled=sampled,
        non_null=non_null,
        unique=unique,
        top_values=top_values,
        **coverage,
    )


def _matrix_summary(handle: Any, n_obs: int, n_vars: int, np: Any) -> MatrixSummary:
    if "X" not in handle:
        return MatrixSummary(shape=(n_obs, n_vars), encoding="missing")
    node = handle["X"]
    encoding = _encoding(node)
    shape = _shape_from_node(node)
    if shape and (len(shape) != 2 or any(size < 0 for size in shape)):
        raise ValueError("X shape must have two nonnegative dimensions")
    matrix_shape = (
        int(shape[0]) if len(shape) >= 1 else n_obs,
        int(shape[1]) if len(shape) >= 2 else n_vars,
    )
    total = matrix_shape[0] * matrix_shape[1]
    if hasattr(node, "keys") and "data" in node:
        data = node["data"]
        if len(_shape_from_node(data)) != 1 or data.dtype.kind not in "biuf":
            raise ValueError("Sparse X data must be a numeric vector")
        nnz = int(data.shape[0])
        sample = np.asarray(data[: min(nnz, 10000)], dtype=float)
        finite = sample[np.isfinite(sample)] if sample.size else sample
        return MatrixSummary(
            shape=matrix_shape,
            encoding=encoding,
            dtype=str(data.dtype),
            nnz=nnz,
            density=(nnz / total) if total else None,
            sample_nonzero=int(np.count_nonzero(finite)),
            sample_total=int(finite.size),
            sample_minimum=float(np.min(finite)) if finite.size else None,
            sample_maximum=float(np.max(finite)) if finite.size else None,
            sample_mean=_finite_mean(finite, np),
            sample_scope=(
                "First 10,000 stored entries at most; includes explicit zeros, "
                "excludes implicit zeros. Mean/range describe these stored values only."
            ),
            sampled_entries=int(sample.size),
            nonfinite_entries=int(sample.size - finite.size),
        )
    if hasattr(node, "dtype") and len(shape) == 2:
        if node.dtype.kind not in "biuf":
            raise ValueError("Dense X must contain real numeric values")
        rows = min(matrix_shape[0], 128)
        columns = min(matrix_shape[1], 128)
        sample = np.asarray(node[:rows, :columns], dtype=float)
        finite = sample[np.isfinite(sample)]
        nonzero = int(np.count_nonzero(finite))
        return MatrixSummary(
            shape=matrix_shape,
            encoding=encoding,
            dtype=str(node.dtype),
            sample_nonzero=nonzero,
            sample_total=int(finite.size),
            density=(nonzero / finite.size) if finite.size else None,
            sample_minimum=float(np.min(finite)) if finite.size else None,
            sample_maximum=float(np.max(finite)) if finite.size else None,
            sample_mean=_finite_mean(finite, np),
            sample_scope="Leading block of at most 128 × 128 entries; not a random sample.",
            sampled_entries=int(sample.size),
            nonfinite_entries=int(sample.size - finite.size),
        )
    return MatrixSummary(shape=matrix_shape, encoding=encoding)


def _choose_annotation(column_names: list[str], requested: str | None) -> str | None:
    if requested:
        return requested if requested in column_names else None
    for candidate in _ANNOTATION_CANDIDATES:
        if candidate in column_names:
            return candidate
    for candidate in _ANNOTATION_CANDIDATES:
        for name in column_names:
            if name.casefold() == candidate.casefold():
                return name
    for name in column_names:
        lowered = name.casefold()
        if "cell" in lowered and "type" in lowered:
            return name
    return None


def inspect_h5ad(
    path: str | Path,
    *,
    max_points: int = 5000,
    annotation: str | None = None,
    max_column_values: int = 20000,
    max_obs_columns: int = 50,
    max_var_columns: int = 30,
    modality_override: list[str] | tuple[str, ...] | None = None,
) -> H5ADInspection:
    """Inspect modern and legacy H5AD files through the shared bounded reader."""
    from .h5ad_compat import inspect_h5ad as inspect

    return inspect(
        path,
        max_points=max_points,
        annotation=annotation,
        max_column_values=max_column_values,
        max_obs_columns=max_obs_columns,
        max_var_columns=max_var_columns,
        modality_override=modality_override,
    )

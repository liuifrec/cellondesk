from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ValueCount(BaseModel):
    value: str
    count: int


class NumericSummary(BaseModel):
    count: int
    missing: int
    minimum: float | None = None
    maximum: float | None = None
    mean: float | None = None
    p05: float | None = None
    median: float | None = None
    p95: float | None = None


class ColumnSummary(BaseModel):
    name: str
    dtype: str
    encoding: str
    sampled: bool = False
    non_null: int | None = None
    unique: int | None = None
    top_values: list[ValueCount] = Field(default_factory=list)
    numeric: NumericSummary | None = None


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


class EmbeddingPreview(BaseModel):
    key: str
    total_points: int
    dimensions: int
    sampled_points: list[list[float]] = Field(default_factory=list)
    color_field: str | None = None
    color_values: list[str] = Field(default_factory=list)


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
        raise RuntimeError(
            'Install H5AD support with: pip install "cellondesk[data]"'
        ) from exc
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
    value = node.attrs.get("encoding-type")
    if value is not None:
        return str(_decode_scalar(value))
    return "dataset" if hasattr(node, "dtype") else "group"


def _shape_from_node(node: Any) -> tuple[int, ...]:
    if hasattr(node, "shape"):
        return tuple(int(value) for value in node.shape)
    shape = node.attrs.get("shape")
    if shape is not None:
        return tuple(int(value) for value in shape)
    return ()


def _axis_column_names(group: Any) -> list[str]:
    order = group.attrs.get("column-order")
    if order is not None:
        return [str(value) for value in _decode_array(order)]
    index_name = str(_decode_scalar(group.attrs.get("_index", "_index")))
    return sorted(
        key
        for key in group
        if key not in {index_name, "__categories"} and not key.startswith("_")
    )


def _axis_length(group: Any) -> int:
    index_name = str(_decode_scalar(group.attrs.get("_index", "_index")))
    if index_name in group:
        return _node_length(group[index_name])
    for key in _axis_column_names(group):
        if key in group:
            return _node_length(group[key])
    return 0


def _node_length(node: Any) -> int:
    shape = _shape_from_node(node)
    if shape:
        return shape[0]
    if "codes" in node:
        return int(node["codes"].shape[0])
    if "values" in node:
        return int(node["values"].shape[0])
    return 0


def _sample_indices(length: int, maximum: int, np: Any) -> Any:
    if length <= 0:
        return np.asarray([], dtype=int)
    if length <= maximum:
        return np.arange(length, dtype=int)
    return np.unique(np.linspace(0, length - 1, maximum, dtype=int))


def _read_node_values(node: Any, indices: Any, np: Any) -> list[Any]:
    encoding = _encoding(node)
    if encoding == "categorical" or (hasattr(node, "keys") and "codes" in node):
        categories = _decode_array(node["categories"][...])
        codes = np.asarray(node["codes"][indices])
        return [categories[int(code)] if int(code) >= 0 else None for code in codes]
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
    return []


def _summarize_column(
    name: str,
    node: Any,
    *,
    max_values: int,
    max_top_values: int,
    np: Any,
) -> ColumnSummary:
    length = _node_length(node)
    indices = _sample_indices(length, max_values, np)
    values = _read_node_values(node, indices, np)
    sampled = len(indices) < length
    dtype = "unknown"
    if hasattr(node, "dtype"):
        dtype = str(node.dtype)
    elif hasattr(node, "keys") and "codes" in node:
        dtype = "category"
    elif hasattr(node, "keys") and "values" in node:
        dtype = str(node["values"].dtype)

    non_missing = [value for value in values if value is not None]
    non_null = len(non_missing)
    encoding = _encoding(node)

    numeric_values: list[float] = []
    numeric = True
    for value in non_missing:
        if isinstance(value, (bool, str, bytes)):
            numeric = False
            break
        try:
            numeric_values.append(float(value))
        except (TypeError, ValueError):
            numeric = False
            break

    if numeric and numeric_values:
        array = np.asarray(numeric_values, dtype=float)
        finite = array[np.isfinite(array)]
        if finite.size:
            quantiles = np.quantile(finite, [0.05, 0.5, 0.95])
            numeric_summary = NumericSummary(
                count=int(finite.size),
                missing=len(values) - int(finite.size),
                minimum=float(np.min(finite)),
                maximum=float(np.max(finite)),
                mean=float(np.mean(finite)),
                p05=float(quantiles[0]),
                median=float(quantiles[1]),
                p95=float(quantiles[2]),
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
        )

    labels = ["Missing" if value is None else str(value) for value in values]
    counts = Counter(labels)
    return ColumnSummary(
        name=name,
        dtype=dtype,
        encoding=encoding,
        sampled=sampled,
        non_null=non_null,
        unique=len(counts) - int("Missing" in counts),
        top_values=[
            ValueCount(value=value, count=count)
            for value, count in counts.most_common(max_top_values)
        ],
    )


def _matrix_summary(handle: Any, n_obs: int, n_vars: int, np: Any) -> MatrixSummary:
    if "X" not in handle:
        return MatrixSummary(shape=(n_obs, n_vars), encoding="missing")
    node = handle["X"]
    encoding = _encoding(node)
    shape = _shape_from_node(node)
    matrix_shape = (
        int(shape[0]) if len(shape) >= 1 else n_obs,
        int(shape[1]) if len(shape) >= 2 else n_vars,
    )
    total = matrix_shape[0] * matrix_shape[1]
    if hasattr(node, "keys") and "data" in node:
        data = node["data"]
        nnz = int(data.shape[0])
        sample = np.asarray(data[: min(nnz, 10000)], dtype=float)
        finite = sample[np.isfinite(sample)] if sample.size else sample
        return MatrixSummary(
            shape=matrix_shape,
            encoding=encoding,
            dtype=str(data.dtype),
            nnz=nnz,
            density=(nnz / total) if total else None,
            sample_nonzero=int(finite.size),
            sample_total=int(finite.size),
            sample_minimum=float(np.min(finite)) if finite.size else None,
            sample_maximum=float(np.max(finite)) if finite.size else None,
            sample_mean=float(np.mean(finite)) if finite.size else None,
        )
    if hasattr(node, "dtype") and len(matrix_shape) == 2:
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
            sample_mean=float(np.mean(finite)) if finite.size else None,
        )
    return MatrixSummary(shape=matrix_shape, encoding=encoding)


def _choose_annotation(column_names: list[str], requested: str | None) -> str | None:
    if requested:
        return requested if requested in column_names else None
    lowercase = {name.lower(): name for name in column_names}
    for candidate in _ANNOTATION_CANDIDATES:
        if candidate in lowercase:
            return lowercase[candidate]
    for name in column_names:
        lowered = name.lower()
        if "cell" in lowered and "type" in lowered:
            return name
    return None


def _embedding_previews(
    handle: Any,
    *,
    n_obs: int,
    annotation: str | None,
    max_points: int,
    np: Any,
) -> tuple[list[EmbeddingPreview], list[str]]:
    warnings: list[str] = []
    if "obsm" not in handle:
        return [], warnings
    obsm = handle["obsm"]
    keys = list(obsm.keys())
    priority = {"X_umap": 0, "spatial": 1, "X_tsne": 2, "X_pca": 3}
    keys.sort(key=lambda key: (priority.get(key, 10), key))
    indices = _sample_indices(n_obs, max_points, np)
    color_values: list[str] = []
    if annotation and "obs" in handle and annotation in handle["obs"]:
        raw_colors = _read_node_values(handle["obs"][annotation], indices, np)
        color_values = ["Missing" if value is None else str(value) for value in raw_colors]

    previews: list[EmbeddingPreview] = []
    for key in keys:
        node = obsm[key]
        shape = _shape_from_node(node)
        if not hasattr(node, "dtype") or len(shape) != 2 or shape[1] < 2:
            warnings.append(f"Skipped unsupported embedding {key!r} with shape {shape or 'unknown'}.")
            continue
        try:
            coordinates = np.asarray(node[indices, :2], dtype=float)
        except (TypeError, ValueError, IndexError) as exc:
            warnings.append(f"Could not sample embedding {key!r}: {exc}")
            continue
        finite_rows = np.isfinite(coordinates).all(axis=1)
        coordinates = coordinates[finite_rows]
        colors = (
            [
                color
                for color, keep in zip(color_values, finite_rows, strict=False)
                if bool(keep)
            ]
            if color_values
            else []
        )
        previews.append(
            EmbeddingPreview(
                key=key,
                total_points=int(shape[0]),
                dimensions=int(shape[1]),
                sampled_points=coordinates.tolist(),
                color_field=annotation if colors else None,
                color_values=colors,
            )
        )
        if len(previews) >= 4:
            break
    return previews, warnings


def inspect_h5ad(
    path: str | Path,
    *,
    max_points: int = 5000,
    annotation: str | None = None,
    max_column_values: int = 20000,
    max_obs_columns: int = 50,
    max_var_columns: int = 30,
) -> H5ADInspection:
    """Inspect a standard AnnData H5AD file without loading its expression matrix."""
    h5py, np = _require_data_dependencies()
    source = Path(path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    if source.suffix.lower() != ".h5ad":
        raise ValueError(f"Expected an .h5ad file, received: {source.name}")
    if max_points < 1:
        raise ValueError("max_points must be positive")

    warnings: list[str] = []
    with h5py.File(source, "r") as handle:
        obs_group = handle.get("obs")
        var_group = handle.get("var")
        n_obs = _axis_length(obs_group) if obs_group is not None else 0
        n_vars = _axis_length(var_group) if var_group is not None else 0
        matrix = _matrix_summary(handle, n_obs, n_vars, np)
        if not n_obs:
            n_obs = matrix.shape[0]
        if not n_vars:
            n_vars = matrix.shape[1]

        obs_names = _axis_column_names(obs_group) if obs_group is not None else []
        var_names = _axis_column_names(var_group) if var_group is not None else []
        likely_annotation = _choose_annotation(obs_names, annotation)
        if annotation and likely_annotation is None:
            warnings.append(f"Requested annotation column {annotation!r} was not found.")

        selected_obs_names = obs_names[:max_obs_columns]
        if likely_annotation and likely_annotation not in selected_obs_names:
            selected_obs_names.append(likely_annotation)
        obs_columns = (
            [
                _summarize_column(
                    name,
                    obs_group[name],
                    max_values=max_column_values,
                    max_top_values=12,
                    np=np,
                )
                for name in selected_obs_names
                if name in obs_group
            ]
            if obs_group is not None
            else []
        )
        var_columns = (
            [
                _summarize_column(
                    name,
                    var_group[name],
                    max_values=max_column_values,
                    max_top_values=12,
                    np=np,
                )
                for name in var_names[:max_var_columns]
                if name in var_group
            ]
            if var_group is not None
            else []
        )

        embeddings, embedding_warnings = _embedding_previews(
            handle,
            n_obs=n_obs,
            annotation=likely_annotation,
            max_points=max_points,
            np=np,
        )
        warnings.extend(embedding_warnings)

        if len(obs_names) > max_obs_columns:
            warnings.append(
                f"Detailed summaries were limited to {max_obs_columns} of {len(obs_names)} obs columns."
            )
        if len(var_names) > max_var_columns:
            warnings.append(
                f"Detailed summaries were limited to {max_var_columns} of {len(var_names)} var columns."
            )
        if not embeddings:
            warnings.append("No two-dimensional previewable embedding was found in obsm.")

        return H5ADInspection(
            source_path=str(source),
            file_name=source.name,
            file_size_bytes=source.stat().st_size,
            n_obs=n_obs,
            n_vars=n_vars,
            matrix=matrix,
            obs_column_names=obs_names,
            var_column_names=var_names,
            obs_columns=obs_columns,
            var_columns=var_columns,
            layers=sorted(handle["layers"].keys()) if "layers" in handle else [],
            obsm=sorted(handle["obsm"].keys()) if "obsm" in handle else [],
            uns=sorted(handle["uns"].keys()) if "uns" in handle else [],
            has_raw="raw" in handle,
            likely_annotation=likely_annotation,
            embeddings=embeddings,
            warnings=warnings,
        )

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class GeneExpressionPreview(BaseModel):
    requested_gene: str
    matched_gene: str
    matched_field: str
    matrix_source: str
    feature_index: int
    total_observations: int
    sampled_observations: int
    nonzero_sampled: int
    minimum: float | None = None
    maximum: float | None = None
    mean: float | None = None
    p95: float | None = None
    values: list[float | None] = Field(default_factory=list)
    embedding_values: dict[str, list[float | None]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


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


def _decode_values(values: Iterable[Any]) -> list[Any]:
    return [_decode_scalar(value) for value in values]


def _encoding(node: Any) -> str:
    value = node.attrs.get("encoding-type")
    if value is not None:
        return str(_decode_scalar(value))
    return "array" if hasattr(node, "dtype") else "group"


def _shape(node: Any) -> tuple[int, ...]:
    if hasattr(node, "shape"):
        return tuple(int(value) for value in node.shape)
    value = node.attrs.get("shape")
    if value is None:
        return ()
    return tuple(int(item) for item in value)


def _sample_indices(length: int, maximum: int, np: Any) -> Any:
    if length <= 0:
        return np.asarray([], dtype=np.int64)
    if length <= maximum:
        return np.arange(length, dtype=np.int64)
    return np.unique(np.linspace(0, length - 1, maximum, dtype=np.int64))


def _node_length(node: Any) -> int:
    shape = _shape(node)
    if shape:
        return int(shape[0])
    if hasattr(node, "keys") and "codes" in node:
        return int(node["codes"].shape[0])
    if hasattr(node, "keys") and "values" in node:
        return int(node["values"].shape[0])
    return 0


def _read_value_block(node: Any, start: int, stop: int, np: Any) -> list[Any]:
    encoding = _encoding(node)
    if encoding == "categorical" or (hasattr(node, "keys") and "codes" in node):
        categories = _decode_values(node["categories"][...])
        codes = np.asarray(node["codes"][start:stop])
        return [categories[int(code)] if int(code) >= 0 else None for code in codes]
    if hasattr(node, "keys") and "values" in node:
        values = np.asarray(node["values"][start:stop])
        mask = np.asarray(node["mask"][start:stop]) if "mask" in node else None
        result: list[Any] = []
        for position, value in enumerate(values):
            if mask is not None and bool(mask[position]):
                result.append(None)
            else:
                result.append(_decode_scalar(value))
        return result
    if hasattr(node, "dtype"):
        return _decode_values(node[start:stop])
    return []


def _candidate_feature_nodes(var_group: Any) -> list[tuple[str, Any]]:
    index_name = str(_decode_scalar(var_group.attrs.get("_index", "_index")))
    names = (
        index_name,
        "feature_name",
        "gene_symbol",
        "gene_symbols",
        "gene_name",
    )
    result: list[tuple[str, Any]] = []
    seen: set[str] = set()
    for name in names:
        if name in seen or name not in var_group:
            continue
        seen.add(name)
        result.append((name, var_group[name]))
    return result


def _find_feature(var_group: Any, gene: str, np: Any) -> tuple[int, str, str, bool]:
    requested = gene.strip()
    if not requested:
        raise ValueError("gene must not be empty")
    requested_lower = requested.casefold()
    case_insensitive: tuple[int, str, str, bool] | None = None
    for field, node in _candidate_feature_nodes(var_group):
        length = _node_length(node)
        for start in range(0, length, 65536):
            values = _read_value_block(node, start, min(start + 65536, length), np)
            for offset, value in enumerate(values):
                if value is None:
                    continue
                label = str(value)
                if label == requested:
                    return start + offset, label, field, False
                if case_insensitive is None and label.casefold() == requested_lower:
                    case_insensitive = (start + offset, label, field, True)
    if case_insensitive is not None:
        return case_insensitive
    raise ValueError(
        f"Gene {gene!r} was not found in the variable index or common feature-name columns."
    )


def _matrix_node(handle: Any, layer: str | None) -> tuple[Any, str]:
    if layer:
        if "layers" not in handle or layer not in handle["layers"]:
            raise ValueError(f"Layer {layer!r} was not found in this H5AD file.")
        return handle["layers"][layer], f"layers/{layer}"
    if "X" not in handle:
        raise ValueError("The H5AD file does not contain an X matrix.")
    return handle["X"], "X"


def _read_csr_gene(node: Any, feature_index: int, sampled_indices: Any, np: Any) -> Any:
    values = np.zeros(len(sampled_indices), dtype=float)
    if len(sampled_indices) == 0:
        return values
    starts = np.asarray(node["indptr"][sampled_indices], dtype=np.int64)
    ends = np.asarray(node["indptr"][sampled_indices + 1], dtype=np.int64)
    index_dataset = node["indices"]
    data_dataset = node["data"]
    for position, (start, end) in enumerate(zip(starts, ends, strict=False)):
        if end <= start:
            continue
        columns = np.asarray(index_dataset[int(start) : int(end)], dtype=np.int64)
        hits = np.flatnonzero(columns == feature_index)
        if hits.size:
            data = np.asarray(data_dataset[int(start) : int(end)], dtype=float)
            values[position] = float(np.sum(data[hits]))
    return values


def _read_csc_gene(node: Any, feature_index: int, sampled_indices: Any, np: Any) -> Any:
    values = np.zeros(len(sampled_indices), dtype=float)
    if len(sampled_indices) == 0:
        return values
    start = int(node["indptr"][feature_index])
    end = int(node["indptr"][feature_index + 1])
    if end <= start:
        return values
    rows = np.asarray(node["indices"][start:end], dtype=np.int64)
    data = np.asarray(node["data"][start:end], dtype=float)
    positions = np.searchsorted(sampled_indices, rows)
    valid = positions < len(sampled_indices)
    valid_positions = positions[valid]
    valid_rows = rows[valid]
    exact = sampled_indices[valid_positions] == valid_rows
    for target, value in zip(valid_positions[exact], data[valid][exact], strict=False):
        values[int(target)] += float(value)
    return values


def _read_dense_gene(node: Any, feature_index: int, sampled_indices: Any, np: Any) -> Any:
    if len(sampled_indices) == 0:
        return np.asarray([], dtype=float)
    return np.asarray(node[sampled_indices, feature_index], dtype=float).reshape(-1)


def _read_gene_values(node: Any, feature_index: int, sampled_indices: Any, np: Any) -> Any:
    encoding = _encoding(node)
    if encoding in {"csr_matrix", "csr"}:
        return _read_csr_gene(node, feature_index, sampled_indices, np)
    if encoding in {"csc_matrix", "csc"}:
        return _read_csc_gene(node, feature_index, sampled_indices, np)
    if hasattr(node, "dtype") and len(_shape(node)) == 2:
        return _read_dense_gene(node, feature_index, sampled_indices, np)
    raise ValueError(f"Unsupported matrix encoding for gene preview: {encoding!r}")


def _embedding_masks(
    handle: Any,
    embedding_keys: Iterable[str],
    sampled_indices: Any,
    np: Any,
) -> dict[str, Any]:
    masks: dict[str, Any] = {}
    if "obsm" not in handle:
        return masks
    for key in embedding_keys:
        if key not in handle["obsm"]:
            continue
        node = handle["obsm"][key]
        shape = _shape(node)
        if not hasattr(node, "dtype") or len(shape) != 2 or shape[1] < 2:
            continue
        coordinates = np.asarray(node[sampled_indices, :2], dtype=float)
        masks[key] = np.isfinite(coordinates).all(axis=1)
    return masks


def inspect_gene_expression(
    path: str | Path,
    gene: str,
    *,
    max_points: int = 5000,
    layer: str | None = None,
    embedding_keys: Iterable[str] = (),
) -> GeneExpressionPreview:
    """Read one gene for sampled observations without materializing the full matrix."""
    h5py, np = _require_data_dependencies()
    source = Path(path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    if max_points < 1:
        raise ValueError("max_points must be positive")

    warnings: list[str] = []
    with h5py.File(source, "r") as handle:
        if "var" not in handle:
            raise ValueError("The H5AD file does not contain a var dataframe.")
        feature_index, matched_gene, matched_field, case_insensitive = _find_feature(
            handle["var"], gene, np
        )
        if case_insensitive:
            warnings.append(f"Matched {gene!r} case-insensitively to {matched_gene!r}.")
        node, matrix_source = _matrix_node(handle, layer)
        shape = _shape(node)
        if len(shape) != 2:
            raise ValueError(
                f"Matrix {matrix_source!r} has no two-dimensional shape metadata."
            )
        n_obs, n_vars = int(shape[0]), int(shape[1])
        if feature_index >= n_vars:
            raise ValueError(
                f"Feature index {feature_index} exceeds matrix width {n_vars} for {matrix_source}."
            )
        sampled_indices = _sample_indices(n_obs, max_points, np)
        raw_values = _read_gene_values(node, feature_index, sampled_indices, np)
        finite = np.isfinite(raw_values)
        values: list[float | None] = [
            float(value) if bool(keep) else None
            for value, keep in zip(raw_values, finite, strict=False)
        ]
        finite_values = raw_values[finite]
        embedding_values: dict[str, list[float | None]] = {}
        for key, mask in _embedding_masks(
            handle, embedding_keys, sampled_indices, np
        ).items():
            embedding_values[key] = [
                value
                for value, keep in zip(values, mask, strict=False)
                if bool(keep)
            ]

    if finite_values.size:
        minimum = float(np.min(finite_values))
        maximum = float(np.max(finite_values))
        mean = float(np.mean(finite_values))
        p95 = float(np.quantile(finite_values, 0.95))
        nonzero = int(np.count_nonzero(finite_values))
    else:
        minimum = maximum = mean = p95 = None
        nonzero = 0
        warnings.append("No finite expression values were found in the sampled observations.")

    return GeneExpressionPreview(
        requested_gene=gene,
        matched_gene=matched_gene,
        matched_field=matched_field,
        matrix_source=matrix_source,
        feature_index=feature_index,
        total_observations=n_obs,
        sampled_observations=len(values),
        nonzero_sampled=nonzero,
        minimum=minimum,
        maximum=maximum,
        mean=mean,
        p95=p95,
        values=values,
        embedding_values=embedding_values,
        warnings=warnings,
    )

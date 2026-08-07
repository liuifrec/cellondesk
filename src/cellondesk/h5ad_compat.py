from __future__ import annotations

from pathlib import Path
from typing import Any

from . import expression as _expression
from . import inspection as _core
from .inspection import EmbeddingPreview, H5ADInspection


class _LegacyCategoricalProxy:
    """Present pandas-era AnnData category codes as a modern categorical node."""

    def __init__(self, codes: Any, categories: Any) -> None:
        self._codes = codes
        self._categories = categories
        self.attrs = {"encoding-type": "categorical"}

    def keys(self) -> tuple[str, str]:
        return ("codes", "categories")

    def __contains__(self, key: object) -> bool:
        return key in {"codes", "categories"}

    def __getitem__(self, key: str) -> Any:
        if key == "codes":
            return self._codes
        if key == "categories":
            return self._categories
        raise KeyError(key)


def _attribute_strings(value: Any) -> list[str]:
    """Flatten scalar, array, tuple, and structured HDF5 attributes to strings."""
    result: list[str] = []
    pending = [value]
    seen: set[int] = set()
    while pending:
        current = pending.pop(0)
        marker = id(current)
        if marker in seen:
            continue
        seen.add(marker)
        if current is None:
            continue
        if isinstance(current, bytes):
            result.append(current.decode("utf-8", errors="replace"))
            continue
        if isinstance(current, str):
            result.append(current)
            continue
        if isinstance(current, (tuple, list)):
            pending[0:0] = list(current)
            continue
        if hasattr(current, "tolist"):
            try:
                converted = current.tolist()
            except (TypeError, ValueError):
                converted = current
            if converted is not current:
                pending.insert(0, converted)
                continue
        if hasattr(current, "item"):
            try:
                converted = current.item()
            except (TypeError, ValueError):
                converted = current
            if converted is not current:
                pending.insert(0, converted)
                continue
        result.append(str(current))
    return result


def _structured_names(node: Any) -> list[str]:
    dtype = getattr(node, "dtype", None)
    names = getattr(dtype, "names", None)
    return list(names or ())


def _axis_index_name(table: Any) -> str:
    attrs = getattr(table, "attrs", {})
    values = _attribute_strings(attrs.get("_index", "_index"))
    candidates = values or ["_index"]
    available = _structured_names(table)
    if available:
        for candidate in candidates:
            if candidate in available:
                return candidate
        for candidate in ("_index", "index"):
            if candidate in available:
                return candidate
        return available[0]
    return candidates[0]


def _contains_field(table: Any, name: str) -> bool:
    names = _structured_names(table)
    if names:
        return name in names
    return name in table


def _legacy_category_node(table: Any, name: str) -> Any | None:
    if not hasattr(table, "keys") or "__categories" not in table:
        return None
    categories = table["__categories"]
    if not hasattr(categories, "keys") or name not in categories:
        return None
    return categories[name]


def _field(table: Any, name: str) -> Any:
    node = table[name]
    categories = _legacy_category_node(table, name)
    if categories is not None and hasattr(node, "dtype"):
        return _LegacyCategoricalProxy(node, categories)
    return node


def _encoding(node: Any) -> str:
    attrs = getattr(node, "attrs", None)
    if attrs is not None:
        value = attrs.get("encoding-type")
        if value is not None:
            values = _attribute_strings(value)
            if values:
                return values[0]
    return "array" if hasattr(node, "dtype") else "group"


def _axis_column_names(table: Any) -> list[str]:
    structured = _structured_names(table)
    index_name = _axis_index_name(table)
    if structured:
        return [name for name in structured if name != index_name]
    order = table.attrs.get("column-order")
    if order is not None:
        names = [name for name in _attribute_strings(order) if _contains_field(table, name)]
        if names:
            return names
    return sorted(
        key
        for key in table
        if key not in {index_name, "__categories"} and not key.startswith("_")
    )


def _axis_length(table: Any) -> int:
    shape = getattr(table, "shape", ())
    if _structured_names(table) and shape:
        return int(shape[0])
    index_name = _axis_index_name(table)
    if _contains_field(table, index_name):
        return _core._node_length(_field(table, index_name))
    for key in _axis_column_names(table):
        if _contains_field(table, key):
            return _core._node_length(_field(table, key))
    return 0


def _candidate_feature_nodes(var_table: Any) -> list[tuple[str, Any]]:
    names = (
        _axis_index_name(var_table),
        "feature_name",
        "gene_symbol",
        "gene_symbols",
        "gene_name",
        "hugo_symbol",
    )
    result: list[tuple[str, Any]] = []
    seen: set[str] = set()
    for name in names:
        if name in seen or not _contains_field(var_table, name):
            continue
        seen.add(name)
        result.append((name, _field(var_table, name)))
    return result


def _container_keys(node: Any) -> list[str]:
    structured = _structured_names(node)
    if structured:
        return sorted(structured)
    if hasattr(node, "keys"):
        return sorted(node.keys())
    return []


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
    keys = _container_keys(obsm)
    priority = {"X_umap": 0, "spatial": 1, "X_tsne": 2, "X_pca": 3}
    keys.sort(key=lambda key: (priority.get(key, 10), key))
    indices = _core._sample_indices(n_obs, max_points, np)

    color_values: list[str] = []
    if annotation and "obs" in handle:
        obs = handle["obs"]
        if _contains_field(obs, annotation):
            raw_colors = _core._read_node_values(_field(obs, annotation), indices, np)
            color_values = ["Missing" if value is None else str(value) for value in raw_colors]

    previews: list[EmbeddingPreview] = []
    for key in keys:
        node = _field(obsm, key)
        shape = _core._shape_from_node(node)
        if not hasattr(node, "dtype") or len(shape) != 2 or shape[1] < 2:
            warnings.append(
                f"Skipped unsupported embedding {key!r} with shape {shape or 'unknown'}."
            )
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


def install_legacy_h5ad_compatibility() -> None:
    """Install robust dataframe metadata helpers in the shared readers."""
    _core._encoding = _encoding
    _core._axis_column_names = _axis_column_names
    _core._axis_length = _axis_length
    _core._embedding_previews = _embedding_previews
    _expression._encoding = _encoding
    _expression._candidate_feature_nodes = _candidate_feature_nodes


install_legacy_h5ad_compatibility()


def inspect_h5ad(
    path: str | Path,
    *,
    max_points: int = 5000,
    annotation: str | None = None,
    max_column_values: int = 20000,
    max_obs_columns: int = 50,
    max_var_columns: int = 30,
) -> H5ADInspection:
    """Inspect modern and legacy AnnData H5AD layouts with bounded reads."""
    h5py, np = _core._require_data_dependencies()
    source = Path(path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    if source.suffix.lower() != ".h5ad":
        raise ValueError(f"Expected an .h5ad file, received: {source.name}")
    if max_points < 1:
        raise ValueError("max_points must be positive")

    warnings: list[str] = []
    with h5py.File(source, "r") as handle:
        obs_table = handle.get("obs")
        var_table = handle.get("var")
        n_obs = _axis_length(obs_table) if obs_table is not None else 0
        n_vars = _axis_length(var_table) if var_table is not None else 0
        matrix = _core._matrix_summary(handle, n_obs, n_vars, np)
        if not n_obs:
            n_obs = matrix.shape[0]
        if not n_vars:
            n_vars = matrix.shape[1]

        obs_names = _axis_column_names(obs_table) if obs_table is not None else []
        var_names = _axis_column_names(var_table) if var_table is not None else []
        likely_annotation = _core._choose_annotation(obs_names, annotation)
        if annotation and likely_annotation is None:
            warnings.append(f"Requested annotation column {annotation!r} was not found.")

        selected_obs_names = obs_names[:max_obs_columns]
        if likely_annotation and likely_annotation not in selected_obs_names:
            selected_obs_names.append(likely_annotation)
        obs_columns = (
            [
                _core._summarize_column(
                    name,
                    _field(obs_table, name),
                    max_values=max_column_values,
                    max_top_values=12,
                    np=np,
                )
                for name in selected_obs_names
                if _contains_field(obs_table, name)
            ]
            if obs_table is not None
            else []
        )
        var_columns = (
            [
                _core._summarize_column(
                    name,
                    _field(var_table, name),
                    max_values=max_column_values,
                    max_top_values=12,
                    np=np,
                )
                for name in var_names[:max_var_columns]
                if _contains_field(var_table, name)
            ]
            if var_table is not None
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
                f"Detailed summaries were limited to {max_obs_columns} of "
                f"{len(obs_names)} obs columns."
            )
        if len(var_names) > max_var_columns:
            warnings.append(
                f"Detailed summaries were limited to {max_var_columns} of "
                f"{len(var_names)} var columns."
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
            layers=_container_keys(handle["layers"]) if "layers" in handle else [],
            obsm=_container_keys(handle["obsm"]) if "obsm" in handle else [],
            uns=_container_keys(handle["uns"]) if "uns" in handle else [],
            has_raw="raw" in handle,
            likely_annotation=likely_annotation,
            embeddings=embeddings,
            warnings=warnings,
        )


__all__ = ["H5ADInspection", "inspect_h5ad"]

"""Bounded field adapters for modern and pandas-era H5AD layouts."""

from __future__ import annotations

import math
from typing import Any

from .inspection import _node_length


class _CompoundFieldProxy:
    """Select rows before materializing a field, including array-valued obsm fields."""

    def __init__(self, table: Any, name: str) -> None:
        self._view = table.fields(name)
        field_dtype = table.dtype.fields[name][0]
        self.dtype = field_dtype.base
        self.shape = table.shape + field_dtype.shape
        self.attrs: dict[str, Any] = {}

    def __len__(self) -> int:
        return self.shape[0]

    def __getitem__(self, selection: Any) -> Any:
        if isinstance(selection, tuple):
            import numpy as np

            rows, *dimensions = selection
            if isinstance(rows, slice):
                rows = range(*rows.indices(self.shape[0]))
            if not len(rows):
                return self._view[rows][(slice(None), *dimensions)]
            # HDF5 compound subarray fields cannot select inner dimensions on disk.
            # Bound the temporary field materialization to a block (or one wide row).
            block = max(1, 16384 // max(1, math.prod(self.shape[1:])))
            return np.concatenate(
                [
                    self._view[rows[start : start + block]][(slice(None), *dimensions)].copy()
                    for start in range(0, len(rows), block)
                ]
            )
        return self._view[selection]


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
    return hasattr(table, "keys") and name in table


def _legacy_category_node(table: Any, name: str) -> Any | None:
    if not hasattr(table, "keys") or "__categories" not in table:
        return None
    categories = table["__categories"]
    if not hasattr(categories, "keys") or name not in categories:
        return None
    return categories[name]


def _field(table: Any, name: str) -> Any:
    node = _CompoundFieldProxy(table, name) if _structured_names(table) else table[name]
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
        sparse_format = _attribute_strings(attrs.get("h5sparse_format"))
        if sparse_format and sparse_format[0] in {"csr", "csc"}:
            return sparse_format[0] + "_matrix"
    return "array" if hasattr(node, "dtype") else "group"


def _axis_column_names(table: Any) -> list[str]:
    structured = _structured_names(table)
    index_name = _axis_index_name(table)
    if structured:
        return [name for name in structured if name != index_name]
    if not hasattr(table, "keys"):
        return []
    order = table.attrs.get("column-order")
    if order is not None:
        names = [name for name in _attribute_strings(order) if _contains_field(table, name)]
        if names:
            return names
    return sorted(
        key for key in table if key not in {index_name, "__categories"} and not key.startswith("_")
    )


def _axis_length(table: Any) -> int:
    shape = getattr(table, "shape", ())
    if _structured_names(table) and shape:
        return int(shape[0])
    if not hasattr(table, "keys"):
        return int(shape[0]) if shape else 0
    index_name = _axis_index_name(table)
    if _contains_field(table, index_name):
        return _node_length(_field(table, index_name))
    for key in _axis_column_names(table):
        if _contains_field(table, key):
            return _node_length(_field(table, key))
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

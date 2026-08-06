from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from . import inspection as _core
from .inspection import H5ADInspection


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


def _axis_index_name(group: Any) -> str:
    values = _attribute_strings(group.attrs.get("_index", "_index"))
    return values[0] if values else "_index"


def _axis_column_names(group: Any) -> list[str]:
    order = group.attrs.get("column-order")
    if order is not None:
        names = [name for name in _attribute_strings(order) if name in group]
        if names:
            return names
    index_name = _axis_index_name(group)
    return sorted(
        key
        for key in group
        if key not in {index_name, "__categories"} and not key.startswith("_")
    )


def _axis_length(group: Any) -> int:
    index_name = _axis_index_name(group)
    if index_name in group:
        return _core._node_length(group[index_name])
    for key in _axis_column_names(group):
        if key in group:
            return _core._node_length(group[key])
    return 0


def install_legacy_h5ad_compatibility() -> None:
    """Install robust dataframe metadata helpers in the shared inspector module."""
    _core._axis_column_names = _axis_column_names
    _core._axis_length = _axis_length


install_legacy_h5ad_compatibility()


def inspect_h5ad(
    path: str | Any,
    *,
    max_points: int = 5000,
    annotation: str | None = None,
    max_column_values: int = 20000,
    max_obs_columns: int = 50,
    max_var_columns: int = 30,
) -> H5ADInspection:
    return _core.inspect_h5ad(
        path,
        max_points=max_points,
        annotation=annotation,
        max_column_values=max_column_values,
        max_obs_columns=max_obs_columns,
        max_var_columns=max_var_columns,
    )


__all__: Iterable[str] = ("H5ADInspection", "inspect_h5ad")

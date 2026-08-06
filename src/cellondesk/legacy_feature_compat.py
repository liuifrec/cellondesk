from __future__ import annotations

from typing import Any

from . import expression as _expression
from .h5ad_compat import (
    _axis_column_names,
    _axis_index_name,
    _contains_field,
    _encoding,
    _field,
)


def _is_string_like(node: Any) -> bool:
    encoding = _encoding(node)
    if encoding in {"categorical", "string-array", "nullable-string"}:
        return True
    dtype = getattr(node, "dtype", None)
    kind = getattr(dtype, "kind", None)
    return kind in {"O", "S", "U"}


def _candidate_feature_nodes(var_table: Any) -> list[tuple[str, Any]]:
    preferred = (
        _axis_index_name(var_table),
        "feature_name",
        "gene_symbol",
        "gene_symbols",
        "gene_name",
        "gene_names",
        "symbol",
        "name",
    )
    result: list[tuple[str, Any]] = []
    seen: set[str] = set()

    for name in preferred:
        if name in seen or not _contains_field(var_table, name):
            continue
        seen.add(name)
        result.append((name, _field(var_table, name)))

    for name in _axis_column_names(var_table):
        if name in seen or not _contains_field(var_table, name):
            continue
        node = _field(var_table, name)
        if _is_string_like(node):
            seen.add(name)
            result.append((name, node))
    return result


_expression._candidate_feature_nodes = _candidate_feature_nodes

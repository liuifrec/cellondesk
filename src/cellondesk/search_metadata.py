"""Conservative scientific normalization shared by discovery adapters."""

from __future__ import annotations

from typing import Any


def reported_count(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    if isinstance(value, str) and value.isascii() and value.isdigit():
        return int(value)
    return None


def organism_matches(value: str | None, query: str | None) -> bool:
    if not query or not query.strip():
        return True
    aliases = {
        "human": "homo sapiens",
        "9606": "homo sapiens",
        "human (h. sapiens)": "homo sapiens",
        "h. sapiens": "homo sapiens",
        "mouse": "mus musculus",
        "10090": "mus musculus",
        "mouse (m. musculus)": "mus musculus",
        "m. musculus": "mus musculus",
    }
    needle = aliases.get(query.strip().casefold(), query.strip().casefold())
    # Repository labels can themselves be common names.
    values = [part.strip().casefold() for part in (value or "").split(",")]
    return any(needle in aliases.get(part, part) for part in values)

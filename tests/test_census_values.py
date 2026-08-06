from __future__ import annotations

import pandas as pd
import pytest

from cellondesk.sources.census import list_census_values


class _FrameResult:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame

    def concat(self) -> _FrameResult:
        return self

    def to_pandas(self) -> pd.DataFrame:
        return self.frame


class _Table:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame

    def read(self) -> _FrameResult:
        return _FrameResult(self.frame)


class _Context:
    def __init__(self, value: object) -> None:
        self.value = value

    def __enter__(self) -> object:
        return self.value

    def __exit__(self, *args: object) -> None:
        return None


class _FakeCensus:
    def get_census_version_description(self, requested: str) -> dict[str, str]:
        return {"release_build": "2026-07-01"}

    def open_soma(self, *, census_version: str) -> _Context:
        assert census_version == "stable"
        frame = pd.DataFrame(
            {
                "organism": ["Homo sapiens", "Homo sapiens", "Mus musculus"],
                "category": ["cell_type", "cell_type", "cell_type"],
                "label": ["T cell", "B cell", "T cell"],
                "ontology_term_id": ["CL:0000084", "CL:0000236", "CL:0000084"],
                "total_cell_count": [120, 80, 500],
                "unique_cell_count": [100, 70, 450],
            }
        )
        return _Context({"census_info": {"summary_cell_counts": _Table(frame)}})


def test_list_census_values_filters_and_sorts() -> None:
    result = list_census_values(
        "cell_type",
        contains="cell",
        limit=2,
        census_module=_FakeCensus(),
    )

    assert result.resolved_census_version == "2026-07-01"
    assert [item.label for item in result.values] == ["T cell", "B cell"]
    assert result.values[0].total_cell_count == 120
    assert result.values[0].ontology_term_id == "CL:0000084"


def test_list_census_values_rejects_unknown_field() -> None:
    with pytest.raises(ValueError, match="Unsupported Census field"):
        list_census_values("unknown", census_module=_FakeCensus())

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from cellondesk.sources.census import (
    CensusQuery,
    build_obs_value_filter,
    build_var_value_filter,
    preview_census_gene,
)


class _Context:
    def __init__(self, value: object) -> None:
        self.value = value

    def __enter__(self) -> object:
        return self.value

    def __exit__(self, *args: object) -> None:
        return None


class _FakeCensus:
    def __init__(self) -> None:
        self.opened_version: str | None = None
        self.get_anndata_kwargs: dict[str, object] = {}

    def open_soma(self, *, census_version: str) -> _Context:
        self.opened_version = census_version
        return _Context(object())

    def get_obs(self, census: object, organism: str, **kwargs: object) -> pd.DataFrame:
        assert census is not None
        assert organism == "Homo sapiens"
        return pd.DataFrame(
            {
                "soma_joinid": [11, 12, 13],
                "cell_type": ["T cell", "T cell", "T cell"],
                "tissue_general": ["lung", "lung", "lung"],
                "disease": ["normal", "normal", "normal"],
                "assay": ["10x 3' v3", "10x 3' v3", "10x 3' v3"],
                "dataset_id": ["d1", "d1", "d2"],
            }
        )

    def get_anndata(self, census: object, **kwargs: object) -> object:
        assert census is not None
        self.get_anndata_kwargs = kwargs
        return SimpleNamespace(
            n_obs=2,
            n_vars=1,
            X=np.asarray([[0.0], [3.0]], dtype=float),
            obs=pd.DataFrame(
                {
                    "soma_joinid": [11, 12],
                    "cell_type": ["T cell", "T cell"],
                    "tissue_general": ["lung", "lung"],
                    "disease": ["normal", "normal"],
                    "assay": ["10x 3' v3", "10x 3' v3"],
                    "dataset_id": ["d1", "d1"],
                }
            ),
            var=pd.DataFrame({"feature_id": ["ENSG1"], "feature_name": ["CD3D"]}),
            __getitem__=lambda self, item: self,
        )


def test_filter_builders_escape_values() -> None:
    query = CensusQuery(
        gene="CD3D",
        tissue="lung",
        cell_type="T cell",
        disease="Crohn's disease",
    )
    obs_filter = build_obs_value_filter(query)
    assert "is_primary_data == True" in obs_filter
    assert "tissue_general == 'lung'" in obs_filter
    assert "cell_type == 'T cell'" in obs_filter
    assert "disease == 'Crohn''s disease'" in obs_filter
    assert build_var_value_filter("CD3D") == (
        "feature_name == 'CD3D' or feature_id == 'CD3D'"
    )


def test_preview_census_gene_limits_coordinates() -> None:
    fake = _FakeCensus()
    result = preview_census_gene(
        CensusQuery(gene="CD3D", tissue="lung", max_cells=2),
        census_module=fake,
    )

    assert fake.opened_version == "stable"
    assert fake.get_anndata_kwargs["obs_coords"] == [11, 12]
    assert result.total_matching_cells == 3
    assert result.sampled_cells == 2
    assert result.nonzero_sampled == 1
    assert result.matched_gene == "CD3D"
    assert result.feature_id == "ENSG1"
    assert result.values == [0.0, 3.0]
    assert result.warnings


def test_empty_gene_is_rejected() -> None:
    with pytest.raises(ValueError, match="gene must not be empty"):
        build_var_value_filter("  ")

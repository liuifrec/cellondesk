from pathlib import Path

import h5py
import numpy as np

from cellondesk.h5ad_report import render_h5ad_report, write_h5ad_report
from cellondesk.inspection import _choose_annotation, inspect_h5ad


def _string_dataset(group: h5py.Group, name: str, values: list[str]) -> h5py.Dataset:
    dataset = group.create_dataset(
        name,
        data=np.asarray(values, dtype=h5py.string_dtype("utf-8")),
    )
    dataset.attrs["encoding-type"] = "string-array"
    dataset.attrs["encoding-version"] = "0.2.0"
    return dataset


def _write_example_h5ad(path: Path) -> None:
    with h5py.File(path, "w") as handle:
        handle.attrs["encoding-type"] = "anndata"
        handle.attrs["encoding-version"] = "0.1.0"

        x = handle.create_group("X")
        x.attrs["encoding-type"] = "csr_matrix"
        x.attrs["encoding-version"] = "0.1.0"
        x.attrs["shape"] = np.asarray([6, 4], dtype=np.int64)
        x.create_dataset("data", data=np.asarray([1, 2, 3, 4, 5, 6], dtype=np.float32))
        x.create_dataset("indices", data=np.asarray([0, 2, 1, 3, 0, 2], dtype=np.int32))
        x.create_dataset("indptr", data=np.asarray([0, 1, 2, 3, 4, 5, 6], dtype=np.int32))

        obs = handle.create_group("obs")
        obs.attrs["encoding-type"] = "dataframe"
        obs.attrs["encoding-version"] = "0.2.0"
        obs.attrs["_index"] = "_index"
        obs.attrs["column-order"] = np.asarray(
            ["cell_type", "n_genes_by_counts"],
            dtype=h5py.string_dtype("utf-8"),
        )
        _string_dataset(obs, "_index", [f"cell-{index}" for index in range(6)])
        cell_type = obs.create_group("cell_type")
        cell_type.attrs["encoding-type"] = "categorical"
        cell_type.attrs["encoding-version"] = "0.2.0"
        cell_type.attrs["ordered"] = False
        cell_type.create_dataset(
            "codes",
            data=np.asarray([0, 0, 1, 1, 2, -1], dtype=np.int8),
        )
        _string_dataset(cell_type, "categories", ["T cell", "B cell", "Myeloid"])
        qc = obs.create_dataset(
            "n_genes_by_counts",
            data=np.asarray([100, 200, 150, 250, 300, 175], dtype=np.int32),
        )
        qc.attrs["encoding-type"] = "array"
        qc.attrs["encoding-version"] = "0.2.0"

        var = handle.create_group("var")
        var.attrs["encoding-type"] = "dataframe"
        var.attrs["encoding-version"] = "0.2.0"
        var.attrs["_index"] = "_index"
        var.attrs["column-order"] = np.asarray(
            ["highly_variable"],
            dtype=h5py.string_dtype("utf-8"),
        )
        _string_dataset(var, "_index", [f"gene-{index}" for index in range(4)])
        highly_variable = var.create_dataset(
            "highly_variable",
            data=np.asarray([True, False, True, False]),
        )
        highly_variable.attrs["encoding-type"] = "array"
        highly_variable.attrs["encoding-version"] = "0.2.0"

        obsm = handle.create_group("obsm")
        umap = obsm.create_dataset(
            "X_umap",
            data=np.asarray(
                [[0, 0], [1, 0], [0, 1], [1, 1], [2, 1], [2, 2]],
                dtype=np.float32,
            ),
        )
        umap.attrs["encoding-type"] = "array"
        spatial = obsm.create_dataset(
            "spatial",
            data=np.asarray(
                [[10, 20], [15, 21], [22, 30], [25, 31], [32, 40], [36, 45]],
                dtype=np.float32,
            ),
        )
        spatial.attrs["encoding-type"] = "array"

        handle.create_group("layers")
        uns = handle.create_group("uns")
        uns.create_group("spatial")


def test_inspects_sparse_h5ad_without_loading_matrix(tmp_path: Path) -> None:
    source = tmp_path / "example.h5ad"
    _write_example_h5ad(source)

    result = inspect_h5ad(source, max_points=4)

    assert result.n_obs == 6
    assert result.n_vars == 4
    assert result.matrix.encoding == "csr_matrix"
    assert result.matrix.nnz == 6
    assert result.matrix.density == 0.25
    assert result.likely_annotation == "cell_type"
    assert [item.key for item in result.embeddings] == ["X_umap", "spatial"]
    assert len(result.embeddings[0].sampled_points) == 4
    assert result.embeddings[0].color_field == "cell_type"
    assert result.uns == ["spatial"]


def test_annotation_choice_prefers_exact_name_in_messy_files() -> None:
    columns = ["Cell_Type", "Cell_type", "cell_type", "leiden"]
    assert _choose_annotation(columns, None) == "cell_type"
    assert _choose_annotation(columns, "Cell_Type") == "Cell_Type"


def test_h5ad_report_is_self_contained(tmp_path: Path) -> None:
    source = tmp_path / "example.h5ad"
    _write_example_h5ad(source)
    result = inspect_h5ad(source)

    output = render_h5ad_report(result)
    assert "<!doctype html>" in output.lower()
    assert 'id="inspection-data"' in output
    assert "X_umap" in output
    assert "cell_type" in output
    assert "cdn." not in output

    destination = write_h5ad_report(result, tmp_path / "summary.html")
    assert destination.exists()
    assert destination.stat().st_size > 5000

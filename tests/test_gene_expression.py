from pathlib import Path

import h5py
import numpy as np
import pytest

from cellondesk.expression import inspect_gene_expression
from cellondesk.gene_report import render_gene_expression_report
from cellondesk.inspection import EmbeddingPreview, H5ADInspection, MatrixSummary


def _strings(group: h5py.Group, name: str, values: list[str]) -> None:
    dataset = group.create_dataset(
        name,
        data=np.asarray(values, dtype=h5py.string_dtype("utf-8")),
    )
    dataset.attrs["encoding-type"] = "string-array"


def _write_example(path: Path, encoding: str) -> None:
    with h5py.File(path, "w") as handle:
        obs = handle.create_group("obs")
        obs.attrs["_index"] = "_index"
        _strings(obs, "_index", [f"cell-{index}" for index in range(6)])
        var = handle.create_group("var")
        var.attrs["_index"] = "_index"
        _strings(var, "_index", [f"ENSG{index}" for index in range(4)])
        _strings(var, "feature_name", ["CD3D", "MS4A1", "LYZ", "MKI67"])
        obsm = handle.create_group("obsm")
        coordinates = obsm.create_dataset(
            "X_umap",
            data=np.asarray(
                [[0, 0], [1, 0], [0, 1], [1, 1], [2, 1], [2, 2]],
                dtype=np.float32,
            ),
        )
        coordinates.attrs["encoding-type"] = "array"
        matrix = handle.create_group("X")
        matrix.attrs["encoding-type"] = encoding
        matrix.attrs["shape"] = np.asarray([6, 4], dtype=np.int64)
        if encoding == "csr_matrix":
            matrix.create_dataset(
                "data", data=np.asarray([1, 2, 3, 4, 5, 6], dtype=np.float32)
            )
            matrix.create_dataset(
                "indices", data=np.asarray([0, 2, 1, 3, 0, 2], dtype=np.int32)
            )
            matrix.create_dataset(
                "indptr", data=np.asarray([0, 1, 2, 3, 4, 5, 6], dtype=np.int32)
            )
        else:
            matrix.create_dataset(
                "data", data=np.asarray([1, 5, 3, 2, 6, 4], dtype=np.float32)
            )
            matrix.create_dataset(
                "indices", data=np.asarray([0, 4, 2, 1, 5, 3], dtype=np.int32)
            )
            matrix.create_dataset(
                "indptr", data=np.asarray([0, 2, 3, 5, 6], dtype=np.int32)
            )


def test_reads_csr_gene_by_feature_name(tmp_path: Path) -> None:
    source = tmp_path / "csr.h5ad"
    _write_example(source, "csr_matrix")
    result = inspect_gene_expression(
        source,
        "MS4A1",
        max_points=6,
        embedding_keys=["X_umap"],
    )
    assert result.feature_index == 1
    assert result.matched_field == "feature_name"
    assert result.values == [0.0, 0.0, 3.0, 0.0, 0.0, 0.0]
    assert result.embedding_values["X_umap"] == result.values


def test_reads_csc_gene_case_insensitively(tmp_path: Path) -> None:
    source = tmp_path / "csc.h5ad"
    _write_example(source, "csc_matrix")
    result = inspect_gene_expression(source, "lyz", max_points=6)
    assert result.values == [0.0, 2.0, 0.0, 0.0, 0.0, 6.0]
    assert result.nonzero_sampled == 2
    assert result.warnings


def test_missing_gene_has_clear_error(tmp_path: Path) -> None:
    source = tmp_path / "csr.h5ad"
    _write_example(source, "csr_matrix")
    with pytest.raises(ValueError, match="not found"):
        inspect_gene_expression(source, "NOT_A_GENE")


def test_expression_report_is_self_contained(tmp_path: Path) -> None:
    source = tmp_path / "csr.h5ad"
    _write_example(source, "csr_matrix")
    expression = inspect_gene_expression(
        source,
        "CD3D",
        max_points=6,
        embedding_keys=["X_umap"],
    )
    inspection = H5ADInspection(
        source_path=str(source),
        file_name=source.name,
        file_size_bytes=source.stat().st_size,
        n_obs=6,
        n_vars=4,
        matrix=MatrixSummary(shape=(6, 4), encoding="csr_matrix"),
        embeddings=[
            EmbeddingPreview(
                key="X_umap",
                total_points=6,
                dimensions=2,
                sampled_points=[[0, 0], [1, 0], [0, 1], [1, 1], [2, 1], [2, 2]],
            )
        ],
    )
    report = render_gene_expression_report(inspection, expression)
    assert "<!doctype html>" in report.lower()
    assert 'id="report-data"' in report
    assert "CD3D" in report
    assert "cdn." not in report

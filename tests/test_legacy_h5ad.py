from pathlib import Path

import h5py
import numpy as np

from cellondesk import inspect_h5ad
from cellondesk.expression import inspect_gene_expression


def _strings(group: h5py.Group, name: str, values: list[str]) -> None:
    dataset = group.create_dataset(
        name,
        data=np.asarray(values, dtype=h5py.string_dtype("utf-8")),
    )
    dataset.attrs["encoding-type"] = "string-array"


def _matrix(handle: h5py.File) -> None:
    matrix = handle.create_group("X")
    matrix.attrs["encoding-type"] = "csr_matrix"
    matrix.attrs["shape"] = np.asarray([2, 2], dtype=np.int64)
    matrix.create_dataset("data", data=np.asarray([2.0, 3.0], dtype=np.float32))
    matrix.create_dataset("indices", data=np.asarray([0, 1], dtype=np.int32))
    matrix.create_dataset("indptr", data=np.asarray([0, 1, 2], dtype=np.int32))


def _assert_legacy_file(source: Path) -> None:
    inspection = inspect_h5ad(source, max_points=2)
    expression = inspect_gene_expression(source, "CD3D", max_points=2)
    assert inspection.n_obs == 2
    assert inspection.n_vars == 2
    assert expression.matched_gene == "CD3D"
    assert expression.values == [2.0, 0.0]


def test_structured_dataframe_index_metadata(tmp_path: Path) -> None:
    source = tmp_path / "legacy-groups.h5ad"
    structured_index = np.asarray((b"_index",), dtype=[("name", "S16")])[()]
    with h5py.File(source, "w") as handle:
        obs = handle.create_group("obs")
        obs.attrs["_index"] = structured_index
        _strings(obs, "_index", ["cell-a", "cell-b"])

        var = handle.create_group("var")
        var.attrs["_index"] = structured_index
        _strings(var, "_index", ["CD3D", "MS4A1"])
        _matrix(handle)

    _assert_legacy_file(source)


def test_compound_dataframe_datasets(tmp_path: Path) -> None:
    source = tmp_path / "legacy-compound.h5ad"
    obs_dtype = np.dtype([("_index", "S16"), ("cell_type", "S16")])
    var_dtype = np.dtype([("_index", "S16"), ("highly_variable", "?")])
    with h5py.File(source, "w") as handle:
        handle.create_dataset(
            "obs",
            data=np.asarray(
                [(b"cell-a", b"T cell"), (b"cell-b", b"B cell")],
                dtype=obs_dtype,
            ),
        )
        handle.create_dataset(
            "var",
            data=np.asarray([(b"CD3D", True), (b"MS4A1", True)], dtype=var_dtype),
        )
        _matrix(handle)

    _assert_legacy_file(source)

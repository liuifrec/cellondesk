import h5py
import numpy as np

from cellondesk.h5ad_compat import inspect_h5ad


def _strings(values: list[str]) -> np.ndarray:
    return np.asarray(values, dtype=h5py.string_dtype(encoding="utf-8"))


def test_legacy_categories_are_decoded_for_metadata_and_embedding_colors(tmp_path):
    path = tmp_path / "legacy-categorical.h5ad"
    with h5py.File(path, "w") as handle:
        handle.create_dataset("X", data=np.asarray([[1.0, 0.0], [0.0, 2.0], [3.0, 0.0]]))

        obs = handle.create_group("obs")
        obs.attrs["_index"] = "_index"
        obs.attrs["column-order"] = _strings(["leiden"])
        obs.create_dataset("_index", data=_strings(["cell-a", "cell-b", "cell-c"]))
        obs.create_dataset("leiden", data=np.asarray([0, 1, 0], dtype=np.int8))
        obs_categories = obs.create_group("__categories")
        obs_categories.create_dataset("leiden", data=_strings(["B cell", "T cell"]))

        var = handle.create_group("var")
        var.attrs["_index"] = "_index"
        var.attrs["column-order"] = _strings(["hugo_symbol"])
        var.create_dataset("_index", data=_strings(["ENSG1", "ENSG2"]))
        var.create_dataset("hugo_symbol", data=np.asarray([0, 1], dtype=np.int16))
        var_categories = var.create_group("__categories")
        var_categories.create_dataset("hugo_symbol", data=_strings(["CD3D", "MS4A1"]))

        obsm = handle.create_group("obsm")
        obsm.create_dataset(
            "X_umap",
            data=np.asarray([[0.0, 0.0], [1.0, 0.5], [0.25, 1.0]], dtype=np.float32),
        )

    result = inspect_h5ad(path, max_points=3)

    assert result.likely_annotation == "leiden"
    leiden = next(column for column in result.obs_columns if column.name == "leiden")
    assert leiden.dtype == "category"
    assert leiden.numeric is None
    assert [(value.value, value.count) for value in leiden.top_values] == [
        ("B cell", 2),
        ("T cell", 1),
    ]

    hugo = next(column for column in result.var_columns if column.name == "hugo_symbol")
    assert hugo.dtype == "category"
    assert hugo.numeric is None
    assert {value.value for value in hugo.top_values} == {"CD3D", "MS4A1"}

    assert result.embeddings[0].color_field == "leiden"
    assert result.embeddings[0].color_values == ["B cell", "T cell", "B cell"]

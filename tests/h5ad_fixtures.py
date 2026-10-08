"""Deterministic synthetic H5AD layouts; no AnnData runtime or real cell data."""

from pathlib import Path

import h5py
import numpy as np


def strings(group, name, values):
    node = group.create_dataset(name, data=np.asarray(values, dtype=h5py.string_dtype("utf-8")))
    node.attrs["encoding-type"] = "string-array"
    node.attrs["encoding-version"] = "0.2.0"
    return node


def categorical(group, name, codes, categories, *, legacy=False):
    if legacy:
        group.create_dataset(name, data=np.asarray(codes, dtype="i4"))
        strings(group.require_group("__categories"), name, categories)
    else:
        node = group.create_group(name)
        node.attrs.update(
            {"encoding-type": "categorical", "encoding-version": "0.2.0", "ordered": False}
        )
        node.create_dataset("codes", data=np.asarray(codes, dtype="i4"))
        strings(node, "categories", categories)


def dashboard_fixture(path: Path, *, layout="modern", matrix="dense", rows=12):
    """Modern, legacy category or compound obs/var/obsm; dense, CSR or CSC X."""
    cell_codes = np.resize([0, 0, 1, 1, 2, -1, 0, 1, 2, 0, 1, -1], rows)
    sample_codes = np.resize([0, 0, 0, 1, 1, 1, 2, 2, -1, 2, 0, 1], rows)
    labels = ["T cell", "B cell", "Missing"]
    samples = ["sample-A", "sample-B", "sample-C"]
    scores = np.resize(
        [0.0, 10.0, 20.0, np.nan, 40.0, np.inf, 60.0, 70.0, 80.0, 90.0, 100.0, 110.0], rows
    )
    coords = np.column_stack((np.arange(rows) % 4, np.arange(rows) // 4)).astype(float)
    if rows > 8:
        coords[3, 0], coords[8, 1] = np.nan, np.inf
    with h5py.File(path, "w") as f:
        f.attrs.update({"encoding-type": "anndata", "encoding-version": "0.1.0"})
        if matrix == "dense":
            f.create_dataset("X", data=np.arange(rows * 3, dtype=float).reshape(rows, 3))
        else:
            node = f.create_group("X")
            node.attrs.update({"encoding-type": matrix + "_matrix", "shape": [rows, 3]})
            # One stored entry per row, including explicit zeros. No SciPy required.
            order = (
                np.arange(rows)
                if matrix == "csr"
                else np.argsort(np.arange(rows) % 3, kind="stable")
            )
            node.create_dataset("data", data=(np.arange(rows) % 4).astype(float)[order])
            node.create_dataset("indices", data=(np.arange(rows) % 3 if matrix == "csr" else order))
            pointers = (
                np.arange(rows + 1)
                if matrix == "csr"
                else np.r_[0, np.cumsum(np.bincount(np.arange(rows) % 3, minlength=3))]
            )
            node.create_dataset("indptr", data=pointers)
        if layout == "compound":
            obs = np.empty(
                rows,
                dtype=[
                    ("_index", "S20"),
                    ("cell_type", "S30"),
                    ("sample_id", "S30"),
                    ("score", "f8"),
                ],
            )
            obs["_index"] = [f"cell-{i}".encode() for i in range(rows)]
            obs["cell_type"] = [labels[c].encode() if c >= 0 else b"" for c in cell_codes]
            obs["sample_id"] = [samples[c].encode() if c >= 0 else b"" for c in sample_codes]
            obs["score"] = scores
            f.create_dataset("obs", data=obs)
            f.create_dataset(
                "var", data=np.array([(b"G1",), (b"G2",), (b"G3",)], dtype=[("_index", "S8")])
            )
            obsm = np.empty(rows, dtype=[("X_umap", "f8", (2,))])
            obsm["X_umap"] = coords
            f.create_dataset("obsm", data=obsm)
        else:
            obs = f.create_group("obs")
            names = [
                "cell_type",
                "sample_id",
                "score",
                "total_counts",
                "n_genes_by_counts",
                "all_missing",
                "constant",
                "flag",
                "numeric_category",
                "unique_id",
            ]
            obs.attrs.update(
                {
                    "encoding-type": "dataframe",
                    "encoding-version": "0.2.0",
                    "_index": "_index",
                    "column-order": names,
                }
            )
            strings(obs, "_index", [f"cell-{i}" for i in range(rows)])
            categorical(obs, "cell_type", cell_codes, labels, legacy=layout == "legacy")
            categorical(obs, "sample_id", sample_codes, samples, legacy=layout == "legacy")
            obs.create_dataset("score", data=scores)
            obs.create_dataset("total_counts", data=np.arange(1, rows + 1) * 10)
            nullable = obs.create_group("n_genes_by_counts")
            nullable.attrs["encoding-type"] = "nullable-integer"
            nullable.attrs["encoding-version"] = "0.1.0"
            nullable.create_dataset("values", data=np.arange(1, rows + 1))
            nullable.create_dataset("mask", data=(np.arange(rows) % 4 == 3))
            obs.create_dataset("all_missing", data=np.full(rows, np.nan))
            obs.create_dataset("constant", data=np.full(rows, 7.0))
            obs.create_dataset("flag", data=np.arange(rows) % 2 == 0)
            numeric_category = obs.create_group("numeric_category")
            numeric_category.attrs["encoding-type"] = "categorical"
            numeric_category.attrs["encoding-version"] = "0.2.0"
            numeric_category.attrs["ordered"] = False
            numeric_category.create_dataset("codes", data=np.arange(rows) % 2)
            numeric_category.create_dataset("categories", data=[10, 20])
            strings(obs, "unique_id", [f"unique-{i}" for i in range(rows)])
            var = f.create_group("var")
            var.attrs.update(
                {
                    "_index": "_index",
                    "encoding-type": "dataframe",
                    "encoding-version": "0.2.0",
                    "column-order": np.asarray([], dtype=h5py.string_dtype("utf-8")),
                }
            )
            strings(var, "_index", ["G1", "G2", "G3"])
            obsm = f.create_group("obsm")
            obsm.create_dataset("X_umap", data=coords)
            obsm.create_dataset("X_tsne", data=np.column_stack((np.arange(rows), -np.arange(rows))))
        f.create_group("layers")
        f.create_group("uns")
        if layout == "modern":

            def encode_node(name, node):
                if "encoding-type" not in node.attrs:
                    node.attrs["encoding-type"] = (
                        "array" if isinstance(node, h5py.Dataset) else "dict"
                    )
                if "encoding-version" not in node.attrs:
                    node.attrs["encoding-version"] = (
                        "0.2.0" if isinstance(node, h5py.Dataset) else "0.1.0"
                    )

            f.visititems(encode_node)
    return path

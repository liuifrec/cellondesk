"""Small deterministic scientific layouts. Values/relationships are synthetic."""

import json
from pathlib import Path

import h5py
import numpy as np
from h5ad_fixtures import categorical, strings


def axis(group, names):
    group.attrs.update(
        {"_index": "_index", "encoding-type": "dataframe", "encoding-version": "0.2.0"}
    )
    strings(group, "_index", names)
    group.attrs["column-order"] = np.asarray([], dtype=h5py.string_dtype())
    return group


def matrix(group, values, layout="dense"):
    values = np.asarray(values, dtype=float)
    if layout == "dense":
        group.create_dataset("X", data=values)
        return
    x = group.create_group("X")
    x.attrs.update({"encoding-type": layout + "_matrix", "shape": values.shape})
    oriented = values if layout == "csr" else values.T
    rows, cols = np.nonzero(oriented)
    x.create_dataset("data", data=oriented[rows, cols])
    x.create_dataset("indices", data=cols)
    x.create_dataset("indptr", data=np.r_[0, np.cumsum(np.bincount(rows, minlength=len(oriented)))])


def scientific_group(
    group, families, *, layout="dense", legacy=False, spatial=False, image=False, rows=12, qc=True
):
    group.attrs.update({"encoding-type": "anndata", "encoding-version": "0.1.0"})
    obs = axis(group.create_group("obs"), [f"barcode-{i}" for i in range(rows)])
    categorical(obs, "region", np.arange(rows) % 2, ["A", "B"], legacy=legacy)
    obs.attrs["column-order"] = ["region"]
    if qc:
        metrics = {"total_counts": np.arange(rows) * 10.0} if "Gene Expression" in families else {}
        if "Peaks" in families:
            metrics.update(
                {
                    "TSS_enrichment": np.arange(rows) / 2.0,
                    "FRiP": np.linspace(0.1, 0.9, rows),
                    "n_fragments": np.arange(rows) * 100,
                }
            )
        for key, values in metrics.items():
            obs.create_dataset(key, data=values)
        obs.attrs["column-order"] = ["region", *metrics]
    features = [
        f"chr1:{100 + i * 50}-{150 + i * 50}" if family == "Peaks" else f"feature-{i}"
        for i, family in enumerate(families)
    ]
    var = axis(group.create_group("var"), features)
    if families and any(families):
        categories = list(dict.fromkeys(families))
        categorical(
            var,
            "feature_types",
            [categories.index(value) for value in families],
            categories,
            legacy=legacy,
        )
        var.attrs["column-order"] = ["feature_types"]
    values = np.arange(rows * len(families), dtype=float).reshape(rows, len(families)) % 11
    matrix(group, values, layout)
    if spatial:
        group.create_group("obsm").create_dataset(
            "spatial", data=np.column_stack((np.arange(rows), np.arange(rows) % 3))
        )
    if image:
        group.require_group("uns/spatial/library/images").create_dataset(
            "lowres", data=np.arange(20 * 30 * 3, dtype="u1").reshape(20, 30, 3)
        )
    return values


def scientific_fixture(path, families=("Gene Expression", "Gene Expression"), **kwargs):
    with h5py.File(path, "w") as handle:
        scientific_group(handle, list(families), **kwargs)
    return path


def multiome_fixture(path, *, rows=12):
    with h5py.File(path, "w") as handle:
        handle.attrs.update({"encoding-type": "MuData", "encoding-version": "0.1.0", "axis": 0})
        axis(handle.create_group("obs"), [f"barcode-{i}" for i in range(rows)])
        axis(handle.create_group("var"), ["feature-0", "feature-1", "chr1:100-150", "chr1:150-200"])
        for name, family, mapping in (
            ("rna", "Gene Expression", [1, 2, 0, 0]),
            ("atac", "Peaks", [0, 0, 1, 2]),
        ):
            scientific_group(
                handle.require_group(f"mod/{name}"),
                [family, family],
                rows=rows,
                layout="csr",
                spatial=True,
            )
            handle.require_group("obsmap").create_dataset(
                name, data=np.arange(1, rows + 1, dtype="u4")
            )
            handle.require_group("varmap").create_dataset(
                name, data=np.asarray(mapping, dtype="u4")
            )
    return path


PUBLIC = Path(__file__).parent / "fixtures" / "public_modalities"


def public_fixture(path, name):
    """Rehydrate explicitly selected public observations/features, without annotation inference."""
    excerpt = json.loads((PUBLIC / f"{name}.json").read_text())
    with h5py.File(path, "w") as handle:
        handle.attrs.update({"encoding-type": "anndata", "encoding-version": "0.1.0"})
        obs = axis(handle.create_group("obs"), excerpt["obs_ids"])
        for key, values in excerpt.get("obs", {}).items():
            obs.create_dataset(key, data=values)
        obs.attrs["column-order"] = list(excerpt.get("obs", {}))
        var = axis(handle.create_group("var"), excerpt["feature_ids"])
        if "feature_types" in excerpt:
            strings(var, "feature_types", excerpt["feature_types"])
            var.attrs["column-order"] = ["feature_types"]
        matrix(handle, excerpt["values"], "csr" if name != "imaging" else "dense")
        if "spatial" in excerpt:
            handle.create_group("obsm").create_dataset("spatial", data=excerpt["spatial"])
        if "image" in excerpt:
            handle.require_group("uns/spatial/public_excerpt/images").create_dataset(
                "lowres", data=np.asarray(excerpt["image"], dtype="f4")
            )
        # Retain excerpt provenance as declared provenance, never modality verification.
        strings(
            handle.require_group("uns"), "excerpt_provenance", [json.dumps(excerpt["provenance"])]
        )
    return path

"""Regenerate tiny deterministic public excerpts from locally downloaded originals.

No networking, normalization, inferred feature types, or writes to originals.
See tests/fixtures/public_modalities/README.md for URLs and extraction scope.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np

from cellondesk.h5ad_access import _axis_index_name, _field
from cellondesk.inspection import _read_node_values
from cellondesk.modality_h5ad import _preview_values

URLS = {
    "multiome.h5": "https://cf.10xgenomics.com/samples/cell-arc/2.0.0/pbmc_granulocyte_sorted_3k/pbmc_granulocyte_sorted_3k_filtered_feature_bc_matrix.h5",
    "visium.h5ad": "https://exampledata.scverse.org/squidpy/visium_hne_adata_crop.h5ad",
    "imc.h5ad": "https://exampledata.scverse.org/squidpy/imc.h5ad",
}


def decoded(values):
    return [value.decode() if isinstance(value, bytes) else str(value) for value in values]


def provenance(path, shape, method):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {
        "source_url": URLS[path.name],
        "source_sha256": digest.hexdigest(),
        "original_observations": int(shape[0]),
        "original_features": int(shape[1]),
        "extraction": method,
        "scope": "Selected public values; not representative or complete. No QC/identities inferred.",
        "license": "Original data-provider terms apply; no license assertion inferred from the file.",
    }


def save(directory, name, data):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.json").write_text(
        json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    )


def extract_tenx(source, directory):
    with h5py.File(source, "r") as handle:
        m = handle["matrix"]
        features, observations = map(int, m["shape"][:])
        rows = np.arange(min(32, observations))
        # Inspect only the first 32 sparse barcode columns, bounded to 2M entries.
        end = int(m["indptr"][len(rows)])
        if end > 2_000_000:
            raise ValueError("Public extraction entry budget exceeded")
        idx, values, pointers = m["indices"][:end], m["data"][:end], m["indptr"][: len(rows) + 1]
        observed = np.unique(idx[values != 0])
        if len(observed) > 200_000:
            raise ValueError("Public extraction feature budget exceeded")
        types = decoded(m["features/feature_type"][observed])
        rna = [int(i) for i, kind in zip(observed, types) if kind == "Gene Expression"][:12]
        atac = [int(i) for i, kind in zip(observed, types) if kind == "Peaks"][:12]
        for name, cols in (("rna", rna), ("atac", atac), ("multiome", rna + atac)):
            selection = {feature: i for i, feature in enumerate(cols)}
            array = np.zeros((len(rows), len(cols)), dtype=float)
            for row in rows:
                start, stop = pointers[row : row + 2]
                for feature, value in zip(idx[start:stop], values[start:stop]):
                    if int(feature) in selection:
                        array[row, selection[int(feature)]] += value
            prov = provenance(
                source,
                (observations, features),
                "First 32 barcode columns; first 12 nonzero observed features per selected annotated family. "
                "10x feature-by-barcode CSC transposed to observation-by-feature; duplicate entries summed; no normalization.",
            )
            prov["source_assay_context"] = (
                "10x PBMC granulocyte-sorted 3k RNA+ATAC multiome; RNA/ATAC excerpts are from this same experiment."
            )
            save(
                directory,
                name,
                {
                    "provenance": prov,
                    "source_obs_indices": rows.tolist(),
                    "source_feature_indices": cols,
                    "obs_ids": decoded(m["barcodes"][rows]),
                    "feature_ids": decoded(m["features/id"][cols]),
                    "feature_types": decoded(m["features/feature_type"][cols]),
                    "values": array.tolist(),
                },
            )


def extract_h5ad(source, directory, name):
    with h5py.File(source, "r") as handle:
        n_obs = len(_field(handle["obs"], _axis_index_name(handle["obs"])))
        n_vars = len(_field(handle["var"], _axis_index_name(handle["var"])))
        rows, cols = np.arange(min(32, n_obs)), np.arange(min(12, n_vars))
        data = {
            "provenance": provenance(
                source,
                (n_obs, n_vars),
                "First 32 observations and first 12 features; exact stored matrix/coordinates. "
                "If present, embedded lowres image sampled every ceil(max image side/24) pixels; preview has no registration transform.",
            ),
            "source_obs_indices": rows.tolist(),
            "source_feature_indices": cols.tolist(),
            "obs_ids": _read_node_values(
                _field(handle["obs"], _axis_index_name(handle["obs"])), rows, np
            ),
            "feature_ids": _read_node_values(
                _field(handle["var"], _axis_index_name(handle["var"])), cols, np
            ),
            "values": _preview_values(
                handle["X"], rows, cols.tolist(), (n_obs, n_vars), np
            ).tolist(),
            "spatial": handle["obsm/spatial"][rows].tolist(),
        }
        if "feature_types" in handle["var"]:
            data["feature_types"] = _read_node_values(
                _field(handle["var"], "feature_types"), cols, np
            )
        data["obs"] = {
            key: handle[f"obs/{key}"][rows].tolist()
            for key in ("total_counts", "pct_counts_mt", "n_genes_by_counts")
            if f"obs/{key}" in handle and hasattr(handle[f"obs/{key}"], "dtype")
        }
        if "uns/spatial" in handle:
            for library in handle["uns/spatial"]:
                image = handle[f"uns/spatial/{library}/images/lowres"]
                step = max(1, int(np.ceil(max(image.shape[:2]) / 24)))
                data["image"] = image[::step, ::step].tolist()
                data["provenance"]["image"] = {
                    "source_path": image.name,
                    "original_shape": list(image.shape),
                    "pixel_stride": step,
                }
                break
        save(directory, name, data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("originals", type=Path)
    parser.add_argument("--output", type=Path, default=Path("tests/fixtures/public_modalities"))
    args = parser.parse_args()
    extract_tenx(args.originals / "multiome.h5", args.output)
    extract_h5ad(args.originals / "visium.h5ad", args.output, "visium")
    extract_h5ad(args.originals / "imc.h5ad", args.output, "imaging")


if __name__ == "__main__":
    main()

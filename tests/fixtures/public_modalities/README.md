# Public measurement excerpts

These small, checked-in JSON excerpts contain real stored values. Tests rehydrate
them as temporary H5ADs using `tests/modality_fixtures.py`; they require no network.
The synthetic fixtures in that module are separate and are not public data.
Original downloads live under ignored `build/modality-public/`.

| Excerpt | Public source | Original observations × features | Selected observations × features |
| --- | --- | --- | --- |
| `rna.json` | 10x PBMC granulocyte-sorted 3k RNA+ATAC multiome, RNA partition | 2,711 × 134,920 (combined) | 32 × 12 |
| `atac.json` | Same experiment, peak partition | 2,711 × 134,920 (combined) | 32 × 12 |
| `multiome.json` | Same experiment, both partitions on the actual shared barcode axis | 2,711 × 134,920 | 32 × 24 |
| `visium.json` | Squidpy cropped 10x V1 adult mouse brain Visium H&E example | 684 × 18,078 | 32 × 12 |
| `imaging.json` | Squidpy IMC example from Jackson et al. | 4,668 × 34 | 32 × 12 |

The RNA and ATAC fixtures are **partitions of a multiome experiment**, not
independent experiments, donors or replicates. They test RNA/accessibility
measurement structure. They do not establish separate scRNA/scATAC cohorts.

Original files and SHA-256:

- [10x filtered feature-barcode matrix](https://cf.10xgenomics.com/samples/cell-arc/2.0.0/pbmc_granulocyte_sorted_3k/pbmc_granulocyte_sorted_3k_filtered_feature_bc_matrix.h5):
  `5fbff5a4d85e0df345f6502e966ec787a8a4c429fd6b88a8772c43fd915cf3ff`
- [Squidpy Visium H5AD](https://exampledata.scverse.org/squidpy/visium_hne_adata_crop.h5ad):
  `9c9b277bde9f34a022df7f3e35b35ce7ecc80f006d6640b0786f4ace6f6eb5dd`
- [Squidpy IMC H5AD](https://exampledata.scverse.org/squidpy/imc.h5ad):
  `950c44c785ea86c4262140b0229e0b4f77110a765c3b6874cdb5e0e52973c6fe`

The Squidpy hashes match its [official dataset registry](https://github.com/scverse/squidpy/blob/main/src/squidpy/datasets/datasets.yaml).
Study context: [10x Visium adult mouse brain](https://support.10xgenomics.com/spatial-gene-expression/datasets/1.1.0/V1_Adult_Mouse_Brain)
and [Jackson et al., Nature 2020](https://www.nature.com/articles/s41586-019-1876-x).
Original data-provider terms apply. The H5ADs do not establish a redistribution
license; no license or participant consent is inferred from public availability.

## Extraction and interpretation

Run `python scripts/extract_modality_public_fixtures.py build/modality-public`
after placing the originals at `multiome.h5`, `visium.h5ad` and `imc.h5ad` there.
The script opens originals read-only, streams their hashes and records source
URLs, original dimensions, selected indices and methods in every excerpt.
It performs no networking, normalization or QC computation.

- 10x: first 32 barcodes; first 12 features with stored nonzero values from each
  requested annotated family. Transpose the native feature × barcode CSC layout;
  sum duplicate sparse coordinates. Preserve feature IDs, types and barcodes.
- H5AD: first 32 observations and first 12 features, original coordinates and
  selected existing numeric QC fields. Visium values are already transformed in
  the public input; tests never label them raw counts.
- Visium image: sample actual low-resolution pixels with stride 8, producing
  23 × 23 RGB pixels. The original 180 × 180 shape and stride are in provenance.
  No spatial registration transform is supplied. This is a small test image,
  not an analysis-quality tissue representation.
- IMC has marker names and spatial coordinates but **no feature-type annotation**.
  Its default profile remains unclassified; the manual spatial-proteomics test
  records an interpretation while typed-protein capabilities remain unavailable.
- These are biased excerpts, not representative samples or complete datasets.
  Report denominators describe the rehydrated excerpt, while this manifest and
  `uns/excerpt_provenance` retain the original selection scope.

Native H5MU axis maps, invalid barcodes, mismatched coordinate frames and absent
images are deterministic synthetic cases; no synthetic correspondence is
attributed to the public experiments. Segmentation, calibrated image overlays,
neighborhoods and native MS spectra are not validated by these fixtures.

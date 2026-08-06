# CellOnDesk

**CellOnDesk** is an experimental, local-first desktop browser for public single-cell and spatial-omics datasets. It is designed to let biologists discover public data, prepare source-native downloads, and inspect large local files without first writing analysis code or loading a complete expression matrix into memory.

> **Status:** pre-alpha (`0.3.0`). HuBMAP search and compact metadata dashboards work. The current data-reading milestone adds direct, bounded-memory structural inspection of local `.h5ad` files with sampled UMAP and spatial previews.

## Current capabilities

- Search published HuBMAP datasets with exact assay and organ filters.
- Inspect normalized dataset metadata and provenance.
- Export HuBMAP Command Line Transfer manifests.
- Export a compact, self-contained HTML summary of search results.
- Inspect local H5AD files directly through HDF5 without loading the complete expression matrix.
- Report matrix shape, sparse encoding, exact sparse non-zero count and density, layers, embeddings, metadata columns, and raw-data presence.
- Sample a fixed number of UMAP, spatial, t-SNE, or PCA points for an offline interactive HTML preview.
- Automatically detect a likely cell-type or cluster annotation column, or use a user-selected column.
- Run on Python 3.10+; CI covers Ubuntu, Windows, and macOS.

CellOnDesk does **not** yet perform clustering, differential expression, integration, segmentation, or full expression visualization.

## Install

Search and metadata export only:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
```

Local H5AD inspection:

```bash
pip install -e ".[data]"
```

Desktop GUI:

```bash
pip install -e ".[gui,data]"
cellondesk-gui
```

## HuBMAP search and compact HTML export

```bash
cellondesk search \
  --dataset-type CODEX \
  --organ SP \
  --status Published \
  --limit 50 \
  --json results.json \
  --manifest hubmap-manifest.txt \
  --html hubmap-search.html
```

Use the resulting manifest with the official HuBMAP Command Line Transfer tool:

```bash
hubmap-clt login
hubmap-clt transfer hubmap-manifest.txt
```

## Inspect a downloaded H5AD file

```bash
cellondesk inspect-h5ad path/to/expr.h5ad \
  --html expr-summary.html \
  --json expr-summary.json
```

Choose a specific observation column for preview coloring:

```bash
cellondesk inspect-h5ad path/to/secondary_analysis.h5ad \
  --annotation cell_type \
  --max-points 10000 \
  --html spatial-summary.html
```

The resulting HTML is a single offline file. It contains headline dimensions, matrix storage information, metadata previews, warnings, and sampled two-dimensional embeddings when available.

## Memory behavior

The H5AD inspector reads the standard AnnData HDF5 structure directly with `h5py`:

- Sparse `X` density is calculated from its on-disk `data` length and declared shape.
- Dense `X` is represented by a small bounded sample.
- Metadata columns are sampled up to a fixed limit for summaries.
- Embedding previews contain at most `--max-points` points per view.
- `uns` values and spatial image pyramids are not loaded; only their top-level keys are listed.

This is a preview workflow, not a replacement for full Scanpy/scverse analysis. Sampled summaries are labeled as such.

## Planned architecture

```text
cellondesk/
├── sources/          # HuBMAP, CELLxGENE, UCSC adapters
├── inspection.py     # bounded-memory H5AD structural reader
├── h5ad_report.py    # offline local-data dashboard
├── models.py         # normalized cross-source metadata
├── manifest.py       # source-native download plans
├── storage/          # planned local review/full pack writer
├── gui.py            # thin desktop client
└── cli.py            # scriptable interface
```

Near-term milestones:

1. Add the H5AD inspector to the Qt GUI.
2. Preview selected genes from sparse H5AD matrices without loading all of `X`.
3. Read Visium/SpatialData image and coordinate metadata safely.
4. Add CELLxGENE and UCSC Cell Browser source adapters.
5. Package signed Windows and macOS application bundles.

## Development

```bash
pip install -e ".[dev]"
ruff check .
pytest
mypy src/cellondesk
```

## Data-transfer note

HuBMAP public downloads use the HuBMAP CLT and Globus Connect Personal. CellOnDesk creates compatible manifests but does not install, authenticate, or control Globus.

## Citation

Until an archived release or software paper is available, cite the software using [`CITATION.cff`](CITATION.cff). Dataset users must also cite the original dataset, associated publication, and source portal.

## License

BSD 3-Clause License. See [LICENSE](LICENSE).

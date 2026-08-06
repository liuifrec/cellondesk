# CellOnDesk

**CellOnDesk** is an experimental, local-first desktop browser for public single-cell and spatial-omics datasets. It is designed to let biologists discover public data, prepare source-native downloads, and inspect large local files without first writing analysis code or loading a complete expression matrix into memory.

> **Status:** pre-alpha (`0.4.0`). HuBMAP discovery, compact metadata dashboards, bounded-memory H5AD inspection, and sampled single-gene expression previews are implemented.

## Current capabilities

- Search published HuBMAP datasets with exact assay and organ filters.
- Inspect normalized dataset metadata and provenance.
- Export HuBMAP Command Line Transfer manifests.
- Export a compact, self-contained HTML summary of search results.
- Inspect local H5AD files directly through HDF5 without loading the complete expression matrix.
- Report matrix shape, sparse encoding, exact sparse non-zero count and density, layers, embeddings, metadata columns, and raw-data presence.
- Sample UMAP, spatial, t-SNE, or PCA coordinates for an offline interactive HTML preview.
- Read one selected gene from dense, CSR, or CSC AnnData matrices using bounded memory.
- Render continuous gene-expression coloring on aligned sampled embeddings.
- Run on Python 3.10+; CI covers Ubuntu, Windows, and macOS.

CellOnDesk does **not** yet perform clustering, differential expression, integration, segmentation, or tissue-image overlay.

## Install

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install --upgrade pip
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

## Preview one gene

```bash
cellondesk preview-gene path/to/expr.h5ad CD3D \
  --max-points 10000 \
  --html CD3D-preview.html \
  --json CD3D-preview.json
```

Use `--layer counts` to read from a named AnnData layer instead of `X`. Gene lookup checks the variable index and common symbol fields. The generated HTML is self-contained and uses only sampled observations.

See [`docs/GENE_PREVIEW.md`](docs/GENE_PREVIEW.md) for supported encodings and memory behavior.

## Memory behavior

The H5AD tools read the standard AnnData HDF5 structure directly with `h5py`:

- Sparse matrix density is calculated from on-disk shape and non-zero storage.
- Dense matrices use bounded samples for structural summaries.
- Metadata columns are summarized from bounded samples.
- Embedding previews contain at most `--max-points` points per view.
- A gene preview reads only one feature from dense, CSR, or CSC storage.
- `uns` values and spatial image pyramids are not loaded.
- Source files are never modified.

These are preview workflows, not replacements for full Scanpy/scverse analysis. Sampled results are labeled as such.

## Planned architecture

```text
cellondesk/
├── sources/          # HuBMAP, CELLxGENE, UCSC adapters
├── inspection.py     # bounded-memory H5AD structural reader
├── expression.py     # bounded-memory single-gene reader
├── h5ad_report.py    # offline structural dashboard
├── gene_report.py    # offline expression dashboard
├── models.py         # normalized cross-source metadata
├── manifest.py       # source-native download plans
├── storage/          # planned local review/full pack writer
├── gui.py            # thin desktop client
└── cli.py            # scriptable interface
```

Near-term milestones:

1. Add H5AD inspection and gene preview controls to the Qt GUI.
2. Read Visium/SpatialData image and coordinate metadata safely.
3. Add CELLxGENE and UCSC Cell Browser source adapters.
4. Package signed Windows and macOS application bundles.

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

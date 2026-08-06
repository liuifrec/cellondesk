# CellOnDesk

**CellOnDesk** is a local-first browser and command-line toolkit for discovering public single-cell and spatial-omics datasets, inspecting large local H5AD files with bounded memory, and producing portable offline review reports.

> **Status:** technical alpha (`0.7.0` release candidate). The CLI workflows are suitable for regular internal exploratory use. Public release hardening and broader real-dataset validation are in progress.

## Current capabilities

- Search published HuBMAP datasets and export source-native transfer manifests.
- Produce self-contained HuBMAP metadata dashboards.
- Inspect local H5AD structure without loading the full expression matrix.
- Preview sampled embeddings and one selected gene from dense, CSR, or CSC AnnData matrices.
- Query one exact gene from CELLxGENE Census/SOMA with bounded cell materialization.
- Export Census JSON and offline HTML reports with resolved Census provenance and contributing dataset attribution.
- Run on Python 3.10+; CI covers Ubuntu, Windows, and macOS.

CellOnDesk is a preview and review tool. It does not replace Scanpy/scverse workflows for clustering, differential expression, integration, trajectory analysis, or statistical inference.

## Install for routine use

From a checked-out release candidate:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[all]"
cellondesk doctor
```

Minimal feature sets:

```bash
pip install -e ".[data]"       # local H5AD inspection and gene previews
pip install -e ".[census]"     # CELLxGENE Census/SOMA queries
pip install -e ".[gui,data]"   # desktop GUI plus local H5AD support
```

The `cellondesk doctor` command reports installed optional components and versions. Use `--json diagnostics.json` when sharing an environment report with a coworker.

## HuBMAP discovery

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

## Inspect a local H5AD file

```bash
cellondesk inspect-h5ad path/to/expr.h5ad \
  --annotation cell_type \
  --max-points 10000 \
  --html expr-summary.html \
  --json expr-summary.json
```

## Preview one local gene

```bash
cellondesk preview-gene path/to/expr.h5ad CD3D \
  --max-points 10000 \
  --html CD3D-preview.html \
  --json CD3D-preview.json
```

Use `--layer counts` to read a named AnnData layer instead of `X`.

## Query CELLxGENE Census

```bash
cellondesk census-preview CD3D \
  --organism "Homo sapiens" \
  --tissue lung \
  --cell-type "T cell" \
  --disease normal \
  --max-cells 5000 \
  --json CD3D-census.json \
  --html CD3D-census.html
```

Census outputs record:

- the requested and resolved Census versions,
- the CellOnDesk version and UTC generation time,
- exact query filters and feature identifiers,
- bounded sampling limits,
- contributing dataset IDs and available source citation strings.

For manuscript-grade reproducibility, prefer an explicit dated Census release rather than the moving `stable` alias.

## Memory behavior

- Sparse H5AD density is calculated from on-disk shape and non-zero storage.
- Dense matrices and metadata use bounded samples.
- Embedding previews contain at most `--max-points` observations.
- A local gene preview reads one feature from dense, CSR, or CSC storage.
- A Census preview materializes one feature and at most `--max-cells` observations.
- `uns` values and spatial image pyramids are not loaded.
- Source files are never modified.

## Development

```bash
pip install -e ".[dev]"
ruff check .
pytest
mypy src/cellondesk
python -m build
python -m twine check dist/*
```

CI validates both editable development installs and a rebuilt/reinstalled wheel.

## Citation

Use [`CITATION.cff`](CITATION.cff) for the software citation. Census reports also list the contributing source datasets represented in each bounded slice; those original datasets and associated publications must be cited separately.

An archived DOI-backed release is planned after the `0.7.0` release candidate passes the real-data validation checklist.

## License

BSD 3-Clause License. See [LICENSE](LICENSE).

# CellOnDesk

**CellOnDesk** is a local-first browser and command-line toolkit for discovering public single-cell and spatial-omics datasets, inspecting large local H5AD files with bounded memory, and producing portable offline review reports.

> **Status:** technical alpha (`0.11.0` internal Windows desktop preview). The desktop now exposes HuBMAP, UCSC Cell Browser, CELLxGENE entry points, and local H5AD inspection. Real-machine testing, source-vocabulary validation, public release hardening, and broader real-dataset validation are still in progress.

## Current capabilities

- Search published HuBMAP datasets with friendly organ aliases such as `kidney` as well as source-native codes such as `LK` and `RK`.
- Show HuBMAP publication status separately from reported data access level, open selected records in the portal, and export CLT transfer manifests or self-contained HTML summaries.
- Search the public UCSC Cell Browser catalog by keyword, organ, and organism, then open the selected dataset at its browser/download page.
- Expose CELLxGENE Discover from the Windows desktop and retain optional native CELLxGENE Census/SOMA bounded gene previews when the Census dependency is installed.
- Inspect local H5AD structure without loading the full expression matrix.
- Preview sampled embeddings and one selected gene from dense, CSR, or CSC AnnData matrices.
- Discover exact CELLxGENE Census metadata labels and precomputed cell counts from Python environments with Census support.
- Query one exact gene from CELLxGENE Census/SOMA with bounded cell materialization and export provenance-rich JSON or offline HTML reports.
- Run on Python 3.10+; CI covers Ubuntu, Windows, and macOS and validates a rebuilt wheel.

CellOnDesk is a preview and review tool. It does not replace Scanpy/scverse workflows for clustering, differential expression, integration, trajectory analysis, or statistical inference.

## Windows desktop preview

The Windows installer is designed for per-user installation without requiring Python, Git, or administrator privileges. The current desktop has four workspaces:

1. **HuBMAP** — search, inspect access metadata, open selected records, export CLT manifests, and export HTML search summaries.
2. **CELLxGENE** — open CELLxGENE Discover for dataset search/download; when `cellxgene-census` is available, run bounded Census gene previews directly.
3. **UCSC Cell Browser** — search the public catalog and open a selected dataset at its browser/download page.
4. **Local H5AD** — inspect real AnnData files with bounded memory and export HTML/JSON structural reports.

The packaged native Windows preview intentionally does **not** bundle `cellxgene-census` because the SOMA dependency stack is not a normal native-Windows deployment target. The CELLxGENE tab therefore remains visible and useful: use **Open CELLxGENE Discover** to search/download an H5AD, then inspect that file in **Local H5AD**. Native Census controls activate automatically in environments where the optional Census dependency is available.

## Install for routine Python use

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

`cellondesk doctor --json diagnostics.json` produces an environment report that can be shared with coworkers.

## HuBMAP discovery

The Python/CLI interface accepts the source-native filters, while the desktop additionally resolves common friendly aliases. For example, desktop organ `kidney` searches both left (`LK`) and right (`RK`) kidney records.

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

A CLT manifest describes transfer targets; it is **not** itself the dataset. In the desktop, **Get data / transfer** opens the current HuBMAP dataset page so the portal can show the live access/download options and any authorization requirements.

## UCSC Cell Browser discovery

The desktop adapter reads the public Cell Browser catalog and expands matching collections one level to find datasets. Use ordinary search terms such as `kidney`, an organism such as `Human`, or project/assay keywords. Opening a result takes you to the UCSC Cell Browser dataset page, where the portal exposes its current **Info & Download / Data Download** options.

This adapter is intentionally conservative during the alpha: it does not scrape or guess direct matrix URLs when the portal does not advertise them in the catalog metadata.

## Inspect a local H5AD file

```bash
cellondesk inspect-h5ad path/to/expr.h5ad \
  --annotation cell_type \
  --max-points 10000 \
  --html expr-summary.html \
  --json expr-summary.json
```

The inspector tolerates many real-world AnnData layouts and prefers exact annotation-name matches before case-insensitive fallbacks, which helps when messy files contain several fields such as `cell_type`, `Cell_type`, and `Cell_Type`.

## Preview one local gene

```bash
cellondesk preview-gene path/to/expr.h5ad CD3D \
  --max-points 10000 \
  --html CD3D-preview.html \
  --json CD3D-preview.json
```

Use `--layer counts` to read a named AnnData layer instead of `X`.

## Discover Census filter values

Census filters require exact metadata labels. Discover them before running a gene query:

```bash
cellondesk census-values tissue_general --contains lung --limit 20
cellondesk census-values cell_type --contains "T cell" --json t-cell-values.json
cellondesk census-values assay --organism "Homo sapiens"
```

The command reads the compact Census summary count table and reports labels, ontology identifiers, cell counts, and the resolved Census release. See [`docs/CENSUS_VALUES.md`](docs/CENSUS_VALUES.md).

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

Census outputs record the requested and resolved Census versions, CellOnDesk version, UTC generation time, exact filters, feature identifiers, bounded sampling limits, and contributing dataset citations. For manuscript-grade reproducibility, use an explicit dated Census release rather than the moving `stable` alias.

## Memory behavior

- Sparse H5AD density is calculated from on-disk shape and non-zero storage.
- Dense matrices and metadata use bounded samples.
- Embedding previews contain at most `--max-points` observations.
- A local gene preview reads one feature from dense, CSR, or CSC storage.
- A Census preview materializes one feature and at most `--max-cells` observations.
- Census metadata discovery uses the precomputed summary table rather than scanning cell observations.
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

## Citation

Use [`CITATION.cff`](CITATION.cff) for the software citation. Portal reports preserve source metadata/provenance; original datasets and associated publications must be cited separately.

An archived DOI-backed public release is planned after the desktop preview passes the real-data validation checklist.

## License

BSD 3-Clause License. See [LICENSE](LICENSE).

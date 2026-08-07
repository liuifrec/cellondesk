# CellOnDesk

**CellOnDesk** is a local-first browser and command-line toolkit for discovering public single-cell and spatial-omics datasets, acquiring useful source files, inspecting large local H5AD files with bounded memory, and producing portable offline review reports.

> **Status:** technical alpha (`0.11.1` internal Windows desktop preview). Real-machine testing, source-vocabulary validation, public-release hardening, and broader real-dataset validation are still in progress.

## Current capabilities

- Search published HuBMAP datasets with friendly organ aliases such as `kidney` as well as source-native codes such as `LK` and `RK`.
- Allow broad HuBMAP organ-only discovery: if the live service cannot return the oversized broad response, CellOnDesk retries across source-native assay types and merges the results.
- Separate HuBMAP publication status from data access level, resolve verified public H5AD products when available, and offer an official HuBMAP CLT manifest as the bulk-transfer fallback.
- Search the public CELLxGENE Discover dataset feed used by the official Census builder and expose its published H5AD assets directly on native Windows, without requiring the SOMA stack.
- Search the public UCSC Cell Browser catalog by keyword, organ, and organism and resolve available matrix, metadata, coordinate, and H5AD-like files when the source advertises them.
- Stream public downloads to disk in bounded chunks with progress, cancellation, and partial-file cleanup.
- Send a downloaded H5AD directly into the Local H5AD workspace for optional immediate inspection.
- Inspect local H5AD structure without loading the full expression matrix, including modern and older AnnData layouts.
- Decode legacy AnnData categorical metadata stored as integer codes plus `__categories`, avoiding misleading numeric summaries for fields such as cluster labels or gene symbols.
- Preview sampled embeddings and one selected gene from dense, CSR, or CSC AnnData matrices.
- Retain optional CELLxGENE Census/SOMA bounded gene previews in Python environments where `cellxgene-census` is installed.
- Run on Python 3.10+; CI covers Ubuntu, Windows, and macOS and validates a rebuilt wheel.

CellOnDesk is a preview, acquisition, and review tool. It does not replace Scanpy/scverse workflows for clustering, differential expression, integration, trajectory analysis, or statistical inference.

## Windows desktop preview

The Windows installer is designed for per-user installation without requiring Python, Git, or administrator privileges. The desktop has four workspaces:

1. **HuBMAP** — search by ordinary organ name or assay, inspect access metadata, find direct H5AD products, save an official CLT bulk-transfer manifest when direct files are not available, open the portal, and export HTML summaries.
2. **CELLxGENE** — search Discover by tissue, disease, organism, cell type, or text and download the published source H5AD advertised by the official dataset feed. Optional Census/SOMA gene previews remain available only when the extra Census dependency is installed.
3. **UCSC Cell Browser** — search the public catalog and download verified matrix/metadata files where available, with the browser page retained as a fallback.
4. **Local H5AD** — inspect real AnnData files with bounded memory and export HTML/JSON structural reports.

The packaged native Windows preview intentionally does **not** bundle `cellxgene-census` because the SOMA dependency stack is not a normal native-Windows deployment target. CELLxGENE dataset discovery and H5AD acquisition do not require that dependency; the optional native Census analysis controls activate automatically in compatible Python environments.

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

## HuBMAP discovery and acquisition

The Python/CLI interface accepts source-native filters, while the desktop additionally resolves common friendly aliases. For example, desktop organ `kidney` searches both left (`LK`) and right (`RK`) kidney records. Leaving assay blank asks CellOnDesk for datasets across assays rather than requiring the user to know the HuBMAP dataset type in advance.

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

A HuBMAP CLT manifest describes transfer targets; it is **not** itself the dataset. In the desktop, **Find data products** prefers verified directly downloadable H5AD products. When those are not exposed, the product list can still offer an official one-dataset CLT manifest generated by HuBMAP SearchAPI. Bulk transfer then requires the external HuBMAP CLT, Globus Connect Personal, and the login/access required by HuBMAP.

## CELLxGENE discovery and acquisition

The Windows desktop uses the public CELLxGENE Discover dataset feed also consumed by the official CELLxGENE Census builder. That feed includes published assets, and the Census builder expects a source H5AD asset with its direct URL and filesize for each included dataset. CellOnDesk normalizes those H5AD assets and sends a downloaded file directly into the Local H5AD workspace.

This acquisition path is distinct from the optional Census/SOMA analytical interface: downloading an H5AD does not require `cellxgene-census` in the Windows installer.

## UCSC Cell Browser discovery

The desktop adapter reads the public Cell Browser catalog and expands matching collections to datasets. Use ordinary search terms such as `kidney`, an organism such as `Human`, or project/assay keywords. CellOnDesk resolves and verifies conventional matrix, metadata, coordinate, and H5AD-like resources when possible; otherwise **Open portal** remains available.

## Inspect a local H5AD file

```bash
cellondesk inspect-h5ad path/to/expr.h5ad \
  --annotation cell_type \
  --max-points 10000 \
  --html expr-summary.html \
  --json expr-summary.json
```

The inspector tolerates many real-world AnnData layouts and prefers exact annotation-name matches before case-insensitive fallbacks. It also decodes older pandas/AnnData categorical storage where values are stored as integer codes and labels live under `__categories`.

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

- Public file downloads are streamed to disk rather than buffered in full memory.
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

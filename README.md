# CellOnDesk

**CellOnDesk** is a local-first browser and command-line toolkit for discovering public single-cell and spatial-omics datasets, acquiring useful source files, inspecting large local H5AD files with bounded memory, and producing portable offline review reports.

## Unified discovery (0.12.0 development milestone)

The new **Discovery** tab searches HuBMAP, CELLxGENE Discover and UCSC Cell Browser
with distinct keyword, tissue, organism, assay and scientific-modality controls. Results arrive
independently, with source errors, coverage limits and cache/timing information.
Sort and filter locally, inspect source metadata, then find files or export a
HuBMAP CLT manifest for the selected dataset. Publication, public access,
advertised files and verified direct downloads remain separate states.

CELLxGENE and UCSC public metadata use a 24-hour disk cache with an explicit
refresh control. HuBMAP evaluates organ/assay aliases before limiting results;
UCSC traverses collections even when only a child matches. Existing source tabs,
advanced functionality and the H5AD dashboard remain available.

See [discovery architecture, measured latency and remaining limits](docs/DISCOVERY_ARCHITECTURE.md).

## Modality-aware dashboards (0.12.0 development milestone)

The general report now adds evidence-based scientific profiles and a panel
capability registry. Typed RNA, ATAC, protein and molecular-ion features can
coexist. Scientific modules show bounded stored feature values, recorded QC,
spatial coordinates and embedded images when those data exist. Unknown files
remain unclassified. Coordinates preserve their numeric geometry; images are
previewed independently because registration has not been validated.

Native H5MU inspection retains module matrices and checks explicit observation
and feature maps. It does not construct a joint matrix or infer biological
pairing. Manual profiles record an interpretation without supplying missing data.
Search modality facets use **assay-derived repository hints**; advertised local
format support and file-verified evidence remain separate.

```bash
cellondesk inspect-scientific sample.h5mu --html sample.html --json sample.json
cellondesk inspect-h5ad ambiguous.h5ad --modality spatial_proteomics --html report.html
```

The desktop **Local H5AD / H5MU** workspace supports the same reader and optional
manual profiles. Export remains one self-contained offline HTML file. SpatialData,
Zarr, OME imaging and imzML readers, calibrated overlays, segmentation,
neighborhoods and joint multiomic analyses are planned, not implemented here.
See the [capability matrix, phases and validation](docs/MODALITY_ARCHITECTURE.md)
and [public fixture provenance](tests/fixtures/public_modalities/README.md).

## H5AD dashboard (0.12.0 development milestone)

Local H5AD reports now include a dataset overview, interactive categorical and
numeric embedding colors, observation-composition bars and sample cross-tabulations,
histograms of existing numeric metadata, and explicit provenance and integrity
limits. HTML, CSS and JavaScript are maintained separately and exported as one
offline HTML file; no network access or browser-side dependencies are required.

Reads remain bounded and support modern and legacy AnnData layouts. Every chart
states its sample denominator, missing values remain visible, and invalid
coordinates retain their original row identities for metadata alignment. No QC
metrics are invented or computed from X. The source H5AD is opened read-only.

See the [architecture and phased implementation](docs/H5AD_DASHBOARD_ARCHITECTURE.md)
for sampling contracts, validation commands and the remaining milestones.

## Reliability update (0.11.3 preview)

This pass hardens acquisition rather than adding another analysis backend:

- Blocking searches, file discovery, downloads and H5AD inspection run in a worker thread. The modal progress view keeps Qt responsive and prevents overlapping actions. Downloads support cooperative cancellation; searches finish their current bounded operation before closing.
- File probes never consume response bodies, even when a server ignores HTTP Range. Network failures are reported separately from missing files. Downloads use unique temporary files, reject HTML login pages and partial responses, check available byte counts and finalize atomically. The Python download API now requires `overwrite=True` to replace an existing file; the GUI still asks through its Save dialog.
- UCSC paths are normalized without duplicated collection prefixes, and a selected leaf's metadata is refreshed to find its advertised files. Matrices remain separate from metadata and coordinates; no automatic H5AD conversion is claimed.
- NaN/Inf values no longer inflate numeric non-null or distinct-value counts. Category dictionaries are sampled by referenced codes. Velocity vector fields remain listed under `obsm` but are not mislabeled as position embeddings.
- Package and installer versions derive from `src/cellondesk/_version.py`. Windows artifacts include `build-info.json`, a versioned installer filename, and a real GUI launch/worker smoke test. Standard PyInstaller Qt hooks replace the blanket collection of all PySide6 modules.

See [the repository audit](docs/RELIABILITY_AUDIT.md) for tests and remaining gaps.

> **Status:** technical alpha (`0.12.0` development milestone, not a published release). Real-machine testing, source-vocabulary validation, public-release hardening, and broader real-dataset validation are still in progress.

## Current capabilities

- Search published HuBMAP datasets with friendly organ aliases such as `kidney` as well as source-native codes such as `LK` and `RK`.
- Allow broad HuBMAP organ-only discovery: if the live service cannot return the oversized broad response, CellOnDesk retries across source-native assay types and merges the results.
- Separate HuBMAP publication status from data access level, resolve verified public H5AD products when available, and offer an official HuBMAP CLT manifest as the bulk-transfer fallback.
- Search the public CELLxGENE Discover dataset feed used by the official Census builder and expose its published H5AD assets directly on native Windows, without requiring the SOMA stack.
- Search the public UCSC Cell Browser catalog by keyword, organ, and organism and resolve available matrix, metadata, coordinate, and H5AD-like files when the source advertises them.
- Prioritize UCSC H5AD/expression matrices ahead of metadata and coordinate files in the desktop download chooser.
- Reset search selections when result sets change so the visible details pane always tracks the newly selected dataset.
- Stream public downloads to disk in bounded chunks with progress, cancellation, and partial-file cleanup.
- Send a downloaded H5AD directly into the Local H5AD workspace for optional immediate inspection.
- Inspect local H5AD structure without loading the full expression matrix, including modern and older AnnData layouts.
- Decode legacy AnnData categorical metadata stored as integer codes plus `__categories`, avoiding misleading numeric summaries for fields such as cluster labels or gene symbols.
- Preview sampled embeddings and one selected gene from dense, CSR, or CSC AnnData matrices.
- Retain optional CELLxGENE Census/SOMA bounded gene previews in Python environments where `cellxgene-census` is installed.
- Run on Python 3.10+; CI covers Ubuntu, Windows, and macOS and validates a rebuilt wheel.

CellOnDesk is a preview, acquisition, and review tool. It does not replace Scanpy/scverse workflows for clustering, differential expression, integration, trajectory analysis, or statistical inference.

## Windows desktop preview

The Windows installer is designed for per-user installation without requiring Python, Git, or administrator privileges. The desktop has five workspaces:

1. **Discovery** — common scientific filters, independent source progress/errors, cached public catalogs, normalized results, local sorting/filtering and selected-dataset acquisition.
2. **HuBMAP** — search by ordinary organ name or assay, inspect access metadata, find direct H5AD products, save an official CLT bulk-transfer manifest, open the portal, and export HTML summaries.
3. **CELLxGENE** — search Discover by tissue, disease, organism, cell type, or text and download the published source H5AD advertised by the official dataset feed. Optional Census/SOMA gene previews remain available only when the extra Census dependency is installed.
4. **UCSC Cell Browser** — search the public catalog and download verified matrix/metadata files where available, with analysis-ready H5AD/expression resources listed before metadata and coordinate-only files and the browser page retained as a fallback.
5. **Local H5AD / H5MU** — inspect native files with bounded memory, review scientific capabilities, record optional profile interpretations, and export offline HTML/JSON reports.

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

A HuBMAP CLT manifest describes transfer targets; it is **not** itself the dataset. In the desktop, **Find data products** prefers verified directly downloadable H5AD products. When those are not exposed, the product list can still offer an official one-dataset CLT manifest generated by HuBMAP SearchAPI. A line such as `HBM123.ABCD.456 /` means the selected HuBMAP dataset at its root resource path; it does not enumerate every file. Bulk transfer then requires the external HuBMAP CLT, Globus Connect Personal, and the login/access required by HuBMAP.

## CELLxGENE discovery and acquisition

The Windows desktop uses the public CELLxGENE Discover dataset feed also consumed by the official CELLxGENE Census builder. That feed includes published assets, and the Census builder expects a source H5AD asset with its direct URL and filesize for each included dataset. CellOnDesk normalizes those H5AD assets and sends a downloaded file directly into the Local H5AD workspace.

This acquisition path is distinct from the optional Census/SOMA analytical interface: downloading an H5AD does not require `cellxgene-census` in the Windows installer.

## UCSC Cell Browser discovery

The desktop adapter reads the public Cell Browser catalog and traverses nested collections before filtering leaves, including matches absent from parent metadata. Use ordinary search terms such as `kidney`, an organism such as `Human`, or project/assay keywords. Explicit selected-file lookup resolves and verifies matrix, metadata, coordinate, and H5AD-like resources. Because UCSC collections do not universally provide a canonical AnnData file, the desktop prioritizes H5AD/expression matrices first, then metadata, then coordinate-only resources; otherwise **Open portal** remains available.

A future UCSC import workflow can build on this by downloading a recommended expression/metadata/coordinate bundle and converting recognized layouts into a local H5AD. That conversion is intentionally separate from simple file acquisition because Cell Browser datasets use heterogeneous formats.

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
- A Census preview limits expression materialization to one feature and `--max-cells` cells. The current optional Census implementation still fetches all matching observation metadata before sampling; its total memory use is not yet bounded by `--max-cells`.
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

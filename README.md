# CellOnDesk

**CellOnDesk** is an experimental, local-first desktop browser for public single-cell and spatial-omics datasets. The goal is to let biologists discover, inspect, download, and later open large public datasets on ordinary Windows and macOS computers without first writing analysis code or loading a complete expression matrix into memory.

> **Status:** pre-alpha (`0.1.0`). The first working slice supports HuBMAP spatial dataset search and HuBMAP Command Line Transfer manifest export. It does not yet convert or visualize expression matrices.

## Why this project exists

Public atlases are scientifically valuable but fragmented across portals, metadata conventions, and download systems. CellOnDesk aims to provide one desktop workflow:

1. Search public sources.
2. Inspect normalized metadata and provenance.
3. Select datasets or files.
4. Download through the source's supported mechanism.
5. Convert data into a documented, memory-friendly local pack.
6. Review embeddings, gene expression, tissue images, and spatial coordinates locally.

The long-term plan includes adapters for HuBMAP, CELLxGENE Discover, and UCSC Cell Browser. The internal source-adapter layer is intentionally separate from the GUI so that search and conversion can also be used from Python or the command line.

## Implemented in 0.1.0

- Cross-platform Qt desktop interface using PySide6.
- HuBMAP spatial assay presets based on current HuBMAP ingest schemas.
- Exact-match HuBMAP parameterized search.
- Normalized dataset table and raw metadata inspection.
- Dataset portal links and DOI display.
- Selection or result-set export as a HuBMAP CLT manifest.
- Scriptable command-line interface.
- Unit tests and GitHub Actions CI.
- Manual Windows and macOS application builds through GitHub Actions.

## Install from source

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[gui]"
cellondesk-gui
```

The core search client can be installed without Qt:

```bash
pip install -e .
cellondesk search --dataset-type "Visium (no probes)" --organ LK --limit 25
```

## Search and export a download manifest

```bash
cellondesk search \
  --dataset-type "Visium (no probes)" \
  --status Published \
  --limit 50 \
  --json results.json \
  --manifest hubmap-manifest.txt
```

The generated manifest is intended for the official HuBMAP Command Line Transfer tool:

```bash
hubmap-clt login
hubmap-clt transfer hubmap-manifest.txt
```

HuBMAP uses its Search API for metadata discovery and Globus/HuBMAP CLT for bulk data transfer. CellOnDesk currently preserves that official division of responsibilities rather than scraping portal download links.

## HuBMAP query behavior

The HuBMAP parameterized search endpoint performs exact matching and combines filters with logical AND. An organ filter therefore expects a HuBMAP organ code. Dataset type values can be edited in the GUI; the preset list is derived from current HuBMAP spatial, imaging, and multiplex assay schemas.

Set a token only when access to a protected operation requires one:

```bash
# Windows PowerShell
$env:HUBMAP_TOKEN="..."

# macOS/Linux
export HUBMAP_TOKEN="..."
```

Do not commit tokens to the repository.

## Planned architecture

```text
cellondesk/
├── sources/          # HuBMAP, CELLxGENE, UCSC adapters
├── models.py         # normalized cross-source metadata
├── manifest.py       # source-native download plans
├── storage/          # planned local CellPack/AtlasPack writer
├── gui.py            # thin desktop client
└── cli.py            # scriptable interface
```

The planned local format will be open and documented, using interoperable components such as Parquet and Zarr rather than an opaque proprietary container. A review pack and a full analysis pack will be distinguished explicitly; reductions such as gene selection or cell downsampling will never be silent.

See [docs/ROADMAP.md](docs/ROADMAP.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Development

```bash
pip install -e ".[dev]"
ruff check .
pytest
mypy src/cellondesk
```

GUI development:

```bash
pip install -e ".[gui,dev]"
cellondesk-gui
```

## Data transfer note

HuBMAP public downloads use the HuBMAP CLT and Globus Connect Personal. A manifest can select an entire dataset (`/`) or a specific resource such as `/expr.h5ad`. CellOnDesk 0.1.0 creates manifests but does not install, authenticate, or control Globus.

Official references:

- HuBMAP APIs: https://docs.hubmapconsortium.org/apis.html
- Parameterized search: https://docs.hubmapconsortium.org/param-search/
- Manifest generation: https://docs.hubmapconsortium.org/clt/generate-manifest.html
- HuBMAP CLT: https://docs.hubmapconsortium.org/clt/
- Current assay schemas: https://hubmapconsortium.github.io/ingest-validation-tools/current.html

## Citation

Until a software paper or archived release is available, cite the software using [`CITATION.cff`](CITATION.cff). Dataset users must also cite the original dataset, associated publication, and source portal as appropriate.

## License

BSD 3-Clause License. See [LICENSE](LICENSE).

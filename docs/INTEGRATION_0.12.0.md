# CellOnDesk 0.12.0 integration verification

Validation date: 2026-10-09. Integration branch:
`agent/integrated-cellondesk-0.12.0`. No merge, release, tag or main-branch
modification is authorized by this report. This work integrates the three
existing milestones; it adds validation tooling, not new scientific features.

## Preservation and commit provenance

The audit inspected all local/remote refs, reflogs, worktrees, stashes, staged
changes, working-tree diffs, untracked files and ignored build outputs. There was
one worktree, no stash and an empty index. The modality branch still pointed to
the discovery commit: its name did **not** mean the modality work was committed.
All 39 modified/untracked source, test, fixture and documentation files were
reviewed as the modality milestone before any branch switch.

Local preservation directory (ignored, never committed):
`build/integration-audit/2026-10-09-before-integration/`. It contains exact copies
of those files, their SHA-256 manifest, refs/status, staged/unstaged patches and a
Git bundle of all existing refs. The hashes were rechecked before staging an
explicit filename list. Existing generated datasets, screenshots, caches and
packages were preserved in place and excluded from commits.

| Order | Commit | Verified feature and dependency |
| --- | --- | --- |
| Base | `662b58a67a2d09fcacde4c335a376e6947510191` | Local main and fetched origin/main agree; all older remote feature refs are ancestors |
| 1 | `83e23ce889d1541d48afc5c433aab290750620e1` | H5AD scientific dashboard; already a coherent commit based on main |
| 2 | `9082fff4fe3f63a72ad45869e1878907b29cf887` | Unified discovery; already a coherent commit based on the dashboard |
| 3 | `69457f271151f4450d39c647bb2fb09133f6b0c3` | Previously uncommitted modality milestone, preserved and committed on its feature branch |
| 4 | `e95e649bcc19f78570bd27f549131e70b5665d8c` | Integration verification and Windows packaging/diagnostics checks |

The integration branch was created from main, then each milestone was integrated
in this order with `git merge --ff-only`. No conflict resolution or history
rewriting was necessary. Its feature tree matched the completed modality branch
exactly. Follow-up integration changes align `CITATION.cff` with the existing
0.12.0 package version, retain package metadata in the Windows executable, require
successful desktop dependency/version diagnostics, and add the reproducible
real-file GUI validation script.

## Verified application surface

The actual desktop starts with five tabs: Discovery, HuBMAP, CELLxGENE, UCSC Cell
Browser, and Local H5AD / H5MU. Existing direct-product downloads and HuBMAP CLT
manifest actions remain wired to their source-specific acquisition paths.
Acquisition failure/overwrite protections, asset selection and manifest handling
are covered by the existing tests. Integration verification does not claim that
all live assets were downloaded or a Globus transfer was performed.

- Discovery combines three independent source jobs, common scientific filters,
  modality facets, cached public catalogs, local sort/filter and identity-based
  selection. Advanced source tabs and optional Census controls remain present.
- H5AD retains overview, categorical/numeric embedding coloring, composition and
  sample cross-tabs, existing numeric QC, provenance and sampling warnings.
- H5MU preserves native module matrices and explicit axis maps. RNA/accessibility,
  spatial coordinates and images render only with corresponding data evidence.
  Joint biological analysis and registered image overlays remain unavailable.
- Remote assay/modality hints, publication/access state, advertised acquisition
  options and supported filename formats do not become file-verified capabilities.
  Manual interpretations remain explicitly manual and create no missing data.
- Eight HTML/CSS/JS assets are assembled into one offline HTML file. Exports need
  neither the original file nor a web service; source datasets remain unchanged.

The detailed contracts and unsupported filters remain in
[H5AD architecture](H5AD_DASHBOARD_ARCHITECTURE.md),
[discovery architecture](DISCOVERY_ARCHITECTURE.md), and
[modality architecture/capability matrix](MODALITY_ARCHITECTURE.md).

## Local engineering and scientific checks

Environment: Linux x86-64, Python 3.10.20, NumPy 2.2.6, h5py 3.16.0,
PySide6 6.11.2 and headless Google Chrome via Playwright.

| Check | Outcome |
| --- | --- |
| Ruff and whitespace checks | Passed |
| Complete pytest suite with browser tests enabled | **212 passed**, including all 12 offline browser cases; no skipped tests |
| Desktop startup | Source and installed-wheel Qt startup/worker smoke passed |
| Browser correctness | Categorical/numeric coloring, composition, QC, selection, legacy layouts, hostile labels, hybrid modules, native H5MU and spatial geometry passed |
| Scientific fixtures | Dense/CSR/CSC, modern/legacy categories, missing values, malformed dimensions/pointers, sampling denominators, absent images, mismatched coordinate frames and invalid/missing/reordered H5MU maps passed |
| Public measurement excerpts | RNA and ATAC partitions, shared-barcode multiome, Visium and IMC passed; their scope/provenance is retained |
| Wheel/sdist | Both built; Twine passed for both |
| Installed-wheel resources | Eight assets present, old/new report envelopes render, native format lookup and Qt startup pass; imports verified from isolated wheel target |
| Distribution hygiene | Neither archive contains generated build trees or original H5AD/H5MU downloads |
| Original file integrity | Full SHA-256 before/after inspection/export agrees for all six real-file GUI cases |

Public excerpts are documented in the
[fixture provenance manifest](../tests/fixtures/public_modalities/README.md).
RNA and ATAC excerpts are partitions of one public multiome experiment, not
independent donors or biological replicates. Native H5MU map fault cases and the
20,000-observation benchmark below are synthetic. The map interpretation is
consistent with the [MuData format specification](https://mudata.scverse.org/stable/io/spec.html):
positive integer indices refer to module axes and zero denotes absence.
Checks never infer experimental pairing or a feature-to-feature biological link.

## Real-file measurements

`scripts/validate_integrated_gui.py` drives the actual desktop inspection and
HTML-export slots in a fresh process. It asserts that inspection runs off the GUI
thread, instruments individual matrix reads, independently checks bounded stored
feature values where exported, validates coordinate/row alignment and map scope,
hashes sources before/after and records a 10 ms GUI heartbeat. Hashing warms the
filesystem cache. Peak RSS covers the Qt process, inspection, serialization and
validation; browser memory is separate. These are single-run observations on this
machine, not cold-disk throughput, hard memory bounds or a performance SLA.

| Input | Observations × features | File bytes | Reader / complete inspect slot (s) | Export (s) | Peak GUI RSS (MiB) | HTML bytes | Largest GUI event gap (s) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Public 4i imaging | 270,876 × 43 | 181,531,300 | 0.219 / 0.827 | 0.036 | 203.7 | 2,486,477 | 0.613 |
| Public MERFISH | 73,655 × 161 | 51,577,387 | 0.361 / 1.080 | 0.056 | 241.1 | 3,604,956 | 0.721 |
| Public mouse cortex | 21,697 × 36,826 | 3,254,624,804 | 1.219 / 2.468 | 0.099 | 349.0 | 6,496,232 | 1.250 |
| Public cropped Visium | 684 × 18,078 | 94,259,482 | 0.613 / 0.683 | 0.011 | 172.7 | 618,377 | 0.075 |
| Public IMC | 4,668 × 34 | 1,574,836 | 0.015 / 0.091 | 0.008 | 142.3 | 631,304 | 0.080 |
| Synthetic RNA+ATAC H5MU | 20,000 × 4 global axes | 6,023,168 | 0.070 / 0.089 | 0.002 | 140.1 | 142,545 | 0.021 |

The three larger H5ADs retain only 20,000 metadata rows; H5MU retains 5,000 global
metadata rows. Scientific previews use at most 256 observations. H5MU obsmap
checks inspect 4,096/20,000 global entries and say **sample-consistent**, never
fully verified. Global counts are not sums of module counts. The largest single
matrix selection across these inspections was 13,910 elements. The H5MU check
independently verified 1,024 sparse stored values; IMC, 4i, MERFISH and Visium
each verified 512. The additional sparse-value checks run outside the GUI timing
measurement and do not claim a second performance sample.

The mouse-cortex sparse preview reaches its scan budget and exports no partial
feature values. It reports this explicitly. Its missing feature-type annotations
also leave the scientific profile unclassified despite the public study context.
The general dashboard still works. Marker names alone likewise do not classify
the IMC data as protein measurements. Source names in this table provide study
context, not additional verified file annotations.

All six exported reports were opened with the browser offline: zero HTTP requests
and JavaScript errors. Load times were 0.047–0.155 s; tested tab interactions took
0.023–0.070 s. Each case has `metrics.json`, `dashboard.html`, `desktop.png`,
`browser-embeddings.png` and `browser-scientific.png` under the corresponding
ignored `build/integrated-0.12.0/{four-i,merfish,mouse-cortex,visium,imc,h5mu}/`.

Full-file sources: the
[official Squidpy registry](https://github.com/scverse/squidpy/blob/main/src/squidpy/datasets/datasets.yaml),
Git blob `138dec65438af680e67717bb979f843b36d950a8`, records the shapes and hashes.
Original public files were downloaded from these URLs and opened read-only:

| Source | SHA-256 |
| --- | --- |
| [four_i.h5ad](https://exampledata.scverse.org/squidpy/four_i.h5ad) | `894e54af155c8ce94bbeeac1056431de9cc0e86460e49cd38ca1a5f952e32124` |
| [merfish.h5ad](https://exampledata.scverse.org/squidpy/merfish.h5ad) | `371723d48413ba76aba49ccf7ea24867b1db940529216fe2902484f5c2a48904` |
| [sc_mouse_cortex.h5ad](https://exampledata.scverse.org/squidpy/sc_mouse_cortex.h5ad) | `3e0a26e1af06c1ea8f53a808ee683bf950de8cc03ee48bd291f95eeca6056aac` |
| [Visium crop](https://exampledata.scverse.org/squidpy/visium_hne_adata_crop.h5ad) | `9c9b277bde9f34a022df7f3e35b35ce7ecc80f006d6640b0786f4ace6f6eb5dd` |
| [imc.h5ad](https://exampledata.scverse.org/squidpy/imc.h5ad) | `950c44c785ea86c4262140b0229e0b4f77110a765c3b6874cdb5e0e52973c6fe` |

## Discovery latency, cache and coverage

The deterministic kidney/no-assay regression retained all expected 6 HuBMAP,
1 CELLxGENE and 1 child-only UCSC match on both passes. CELLxGENE requests fell
from 1 to 0, UCSC from 4 to 0, and HuBMAP stayed at 2. Mock transport timings are
not network performance measurements.

A separate live metadata-only kidney/no-assay run used a new cache and a 30 s
budget per source. No assets were probed or acquired.

| Source | Cold → warm time (s) | Requests | Matched → displayed | Coverage |
| --- | --- | --- | --- | --- |
| HuBMAP | 28.576 → 30.002 | 58 → 46 | 1,053 → 100 cold; 1,050 → 100 warm | Partial on both runs: broad query fallback; warm deadline also reached |
| CELLxGENE | 10.177 → 0.084 | 1 → 0 | 188 → 100 both runs | Entire fetched catalog searched; display truncated |
| UCSC | 30.002 → 14.183 | 220 → 102, with 219 warm cache hits | 15 → 15 cold; 25 → 25 warm | Cold traversal timed out; warm traversal completed within published-summary scope |

Cold UCSC downloaded 606,849 bytes; the warm run downloaded 204,681 additional
bytes to finish catalog discovery. CELLxGENE downloaded 9,739,428 bytes cold and
zero warm. Complete means the adapter's documented catalog scope, not all
repository content or unindexed portal metadata. Full statistics, warnings and
source identifiers are in ignored `discovery-{synthetic,live}.json` artifacts.

## Remaining limitations and RC review points

- File reading runs in workers, but formatting/displaying detailed inspection
  JSON and HTML export still run on the GUI thread. The largest measured display
  pause was **1.25 s**; fully smooth large-report rendering is not claimed.
- HDF5 decompression, variable-length strings and Python object overhead prevent
  selection bounds from being universal process-memory guarantees.
- Unknown assays/annotations remain unknown. Existing QC is descriptive only;
  no quality verdicts, thresholds, donor counts or biological pairing are inferred.
- Sparse scan limits may suppress feature previews. Only supported X layouts are
  previewed; raw/layers, gene activity, fragments and arbitrary protein obsm arrays
  need explicit future adapters.
- No verified image registration, physical scale, segmentation, neighborhoods,
  cross-module joint views or peak-to-gene links. Images are independent previews.
  SpatialData/Zarr, OME and imzML remain planned adapters, not implemented readers.
- Native H5MU is validated with synthetic containers/maps. Public multiome values
  come from the separately documented 10x shared-barcode excerpts; this report
  does not represent a public native-H5MU benchmark.
- Live HuBMAP fallback remains incomplete; cold UCSC can exhaust its source
  budget. Timeouts, cache state and result truncation remain visible independently.
- Catalog access, advertised files, point-in-time endpoint verification and
  successful local content inspection remain distinct states.

## GitHub validation and screenshots

[Draft PR #16](https://github.com/liuifrec/cellondesk/pull/16) targets main and
remains unmerged. The first [CI run](https://github.com/liuifrec/cellondesk/actions/runs/37870334742)
identified two portability issues: test-side default-encoding reads of UTF-8
reports failed on Windows, and the Ubuntu Qt runner lacked `libEGL.so.1`.
The report readers in those tests now specify UTF-8; the Qt CI job installs
`libegl1` and `libopengl0`. Product rendering and scientific semantics are unchanged.
The first Windows packaging job stopped at the same encoding tests, before
building an executable. Successful replacement runs and artifacts are recorded
below when available; a started job is not counted as validation.

Local reviewed screenshot sets:

- `build/integrated-0.12.0/screenshots/discovery-workspace.png` — Qt sorting,
  normalized results, modality controls and selection/details.
- `build/integrated-0.12.0/browser-tests/` — overview, categorical/numeric
  embeddings, composition, QC, legacy layouts, spatial and native multiome views.
- Per-public-file directories listed above — actual exported report and desktop
  screenshots. CI retains its own browser and Windows GUI screenshot artifacts.

## Reproduction

Install development, data, GUI, browser and packaging tools in an isolated Python
environment; install a Playwright Chromium browser or set its executable path.

```bash
python -m ruff check .
QT_QPA_PLATFORM=offscreen CELLONDESK_BROWSER_TESTS=1 python -m pytest -q
QT_QPA_PLATFORM=offscreen python -m cellondesk.desktop --smoke-test-gui
python -m build
python -m twine check dist/cellondesk-0.12.0*
python -I scripts/check_h5ad_package.py  # after installing the built wheel
python scripts/benchmark_discovery.py --cache-dir build/new-cache --output build/discovery.json
python scripts/benchmark_discovery.py --live --timeout 30 --cache-dir build/new-live-cache --output build/live.json
python scripts/validate_integrated_gui.py INPUT.h5ad --output-dir build/case \
  --expected-shape N_OBS N_VARS --expected-sha256 SOURCE_SHA256 \
  --source-url SOURCE_URL --browser-executable /path/to/chromium
```

Run each performance case separately; retain its exact source URL/hash and
environment alongside the output. Do not commit generated reports, datasets,
screenshots, caches, installer executables or distribution archives.

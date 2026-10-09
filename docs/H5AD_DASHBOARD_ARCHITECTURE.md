# H5AD dashboard for 0.12.0

## Review and phased implementation

The 0.11.3 public API, CLI and desktop use `h5ad_compat.inspect_h5ad`, while
`inspection.inspect_h5ad` contains a second implementation. Compatibility is
installed through module mutations. The report is a single Python f-string
containing markup, styles and plotting logic. Embeddings carry only one label
column, and lose row identities when non-finite coordinates are removed.
Compound legacy fields are materialized before slicing. Existing matrix reads
are bounded but their sampled statistics need clearer scope labels.

1. **Milestone 1 (this branch):** one inspection implementation; bounded modern
   and legacy field adapters; additive, versioned report data; explicit row
   identities and coverage; overview, interactive categorical/numeric embedding
   colors, composition/cross-tabs, existing-metadata histograms and provenance.
   Separate packaged HTML/CSS/JS components are assembled into one offline file.
   Synthetic fixtures, scientific assertions, browser interactions/screenshots,
   and distribution-resource checks protect this contract.
2. **Milestone 2:** optional streamed full-axis aggregates with progress and
   cancellation; coordinated filters and selection exports. Full-population
   results require an explicit complete scan, not extrapolation of this sample.
3. **Milestone 3:** broader public-file compatibility corpus, accessibility and
   performance review, native desktop/frozen-package validation, release review.
   This branch does not merge, publish or release anything.

## Boundaries and contracts

- `h5ad_access.py`: layout adapters only. Compound fields select rows on disk;
  category dictionaries read only referenced labels; nullable masks are retained.
- `inspection.py`: backward-compatible Pydantic models and bounded summary
  helpers. `inspect_h5ad` delegates to the shared reader.
- `h5ad_compat.py`: compatibility entry point and shared inspection orchestration;
  expression compatibility hooks remain for existing gene preview callers.
- `h5ad_dashboard.py`: observation samples, histograms, integrity observations and
  provenance. Neither this module nor the report calculates new biological QC.
- `h5ad_report.py`: safe JSON/HTML serialization and resource assembly only.
- `report_assets/h5ad/`: HTML shell, CSS, shared JS utilities, embedding,
  composition, QC and navigation components. No network libraries, fonts, fetches,
  servers or runtime dependencies are needed by the exported file.

The schema additions have defaults: old serialized inspections still render,
and old model constructors and import paths remain usable. Legacy single-column
embedding colors remain available when aligned metadata was not recorded.
Keep the existing deterministic `linspace` embedding sample for gene-preview
alignment. A separate deterministic observation sample drives composition,
cross-tabs and numeric summaries. Each embedding retains original row indices
after coordinate filtering; colors join by those indices. The two sample
denominators must never be silently interchanged.

## Scientific and resource limits

Default bounds are 5,000 embedding candidates, 20,000 values per metadata column,
50 observation fields (plus a detected/requested annotation if needed), 30
variable fields, four embeddings and the first two coordinate dimensions.
Dense X reads cover at most the leading 128 × 128 block; sparse X reads cover
at most the first 10,000 **stored entries**, including explicit zeros and
excluding implicit zeros. The sparse stored-entry ratio is not a verified
biological nonzero fraction. Sampling is deterministic and evenly spaced in row
order; it is not a random or representative sample. Rare categories can be missed.
Memory depends on configured limits, selected field widths/string lengths and
HDF5 chunk decompression, not the full matrix/axis length. HDF5 metadata listings
and a single exceptionally large value/chunk are not byte-bounded.

Charts include missing values in composition denominators and cross-tabs.
High-cardinality categories beyond the display limit are pooled into an explicit
Other group with its count. Histograms use finite stored metadata values only;
NaN/Inf/masked values are separately counted. The final bin includes its right
edge. No normalization, mitochondrial fraction, count totals, quality thresholds,
biological quality verdict or inferential significance is invented.

The report records tool/dependency versions, UTC inspection time, source path,
file size/mtime, HDF5 encoding and sampling limits. It opens H5AD read-only and
compares source stat information before/after inspection. This is not a checksum
or complete integrity validation: sparse pointers/indices and unsampled values
are not exhaustively scanned. Structural mismatches, omitted fields/embeddings,
invalid sampled values and unsupported layouts are visible warnings.

## Validation

Use `pip install -e '.[dev,browser]'` and `pip install build twine`, then
`ruff check .`, `pytest`, and
`python -m build` / `python -m twine check dist/*`. The browser tests run with
`CELLONDESK_BROWSER_TESTS=1 pytest tests/test_h5ad_browser.py`; set
`CELLONDESK_BROWSER_EXECUTABLE` to a local Chromium executable or install Chromium
with Playwright. `CELLONDESK_BROWSER_ARTIFACTS` selects the screenshot/report
directory. Tests generate deterministic modern dense, CSR/CSC, legacy category,
compound-table, malformed and empty fixtures; no downloaded patient data is used.
Screenshots are review artifacts, while DOM, canvas and count assertions check
scientific behavior without relying on platform-specific pixel baselines.

Local milestone verification (2026-10-08, Python 3.10 / Linux):

- Ruff and `git diff --check` passed.
- Pytest: 113 passed; six opt-in browser tests and one Qt module skipped in the
  default run. All six browser tests passed separately in offline Chromium.
- Browser screenshots and standalone examples are generated under
  `build/h5ad-dashboard/` (ignored build artifacts).
- Wheel and sdist built with `python -m build --no-isolation`; Twine accepted
  both. An isolated import from the installed wheel rendered the report and
  verified all seven packaged assets.
- Source hashes and mtimes stayed unchanged in inspection/export tests.
  The deliberate concurrent-stat-change fixture produced an integrity warning.
- Qt was not installed locally and the native Windows installer was not run.
  CI now collects report assets into the frozen desktop, checks their presence
  in its existing startup smoke test, and uploads browser screenshots separately.

The first milestone performs no complete sparse-index or observation-identity
validation, and does not claim that sampled counts represent the population.

Format references: [AnnData on-disk specification](https://anndata.readthedocs.io/en/stable/fileformat-prose.html)
and [h5py dataset selections](https://docs.h5py.org/en/stable/high/dataset.html).

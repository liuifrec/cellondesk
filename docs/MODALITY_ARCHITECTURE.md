# Modality-aware scientific dashboards — 0.12.0

## Architecture and capability matrix (implementation contract)

The existing bounded H5AD overview, metadata, composition, embeddings, stored-QC
histograms and provenance remain the common foundation. Observation rows are not
automatically cells; X is a measurement matrix, not automatically RNA expression.
Tissue, organism, assay, measurement modality, spatial context and file format are
different concepts. A dataset may support several profiles at once.

| Scientific profile | Positive file evidence | First-phase panels | Required evidence for later panels |
| --- | --- | --- | --- |
| RNA / single-cell RNA-seq | Explicit gene-expression feature annotations or file assay declaration (declarations alone remain tentative) | Common foundation; bounded stored gene-feature values when a readable matrix and feature identity exist; existing RNA QC fields | Normalization/raw-count semantics and observation units must be supplied, not guessed |
| ATAC / accessibility | Peak/accessibility feature annotations; interval names and ATAC QC are supporting clues | Peak/feature inventory, bounded stored accessibility values; recorded TSS enrichment, FRiP and fragment metrics | Fragment file, reference assembly and definitions for computed accessibility/QC; explicit gene-activity matrix for that view |
| Spatial transcriptomics | RNA evidence plus row-aligned spatial coordinates; spatial assay declarations are separate evidence | Spatial coordinate preview, embedded image preview when readable, existing region metadata and spatial QC | Verified coordinate frame, orientation, image transform and library correspondence before overlays |
| Spatial proteomics / imaging | Protein/channel evidence plus spatial coordinates | Stored marker/channel values, spatial coordinates, image inventory/preview | Explicit segmentation labels and object correspondence; calibrated geometry for neighborhoods |
| Multiomics | At least two observed measurement families | Simultaneous modules; shared-X feature partitions or H5MU modality inventory and bounded obsmap/varmap checks | Validated alignment for joint comparisons; no peak-to-gene or protein-to-gene relationships inferred |
| Spatial metabolomics | Explicit molecular-ion/mass feature metadata plus spatial coordinates | Evidence/inventory; generic stored feature previews where representable | imzML/MS adapters, m/z/charge/adduct/polarity definitions and calibration; no metabolite identities inferred from mass alone |

Panel states are **available**, **missing**, **unsupported**, or **invalid**.
Only available panels draw data. All other states explain the missing evidence
or implementation boundary. A declaration or manual profile selection never
creates data or promotes an unavailable capability.

## Layers

1. `modality.py`: versioned evidence, profile, feature-preview, spatial-resource
   and correspondence models; profile/panel registry and conservative source
   assay classification. Evidence records its origin, path, value and scope.
2. `modality_h5ad.py`: bounded positive-evidence extraction from an already-open
   read-only HDF5 group. Validate axes before sampling values. Reuse legacy field
   readers; preserve original feature names and row identities.
3. `scientific_formats.py`: format registry and dispatch. H5AD and H5MU have
   distinct readers. H5MU retains per-modality matrices and explicit 1-based
   maps (zero means absent); it is not flattened or converted to AnnData.
4. `inspection.py`: additive scientific-profile data in the inspection envelope.
   Older JSON/constructors remain valid. The legacy H5AD APIs remain supported.
5. `report_assets/h5ad/modalities.js` and report helpers: evidence/capability
   inventory, supported modules and bounded previews, assembled into the same
   self-contained offline HTML. Rendering never reopens the source.
6. Discovery: source-reported modality facets are derived only from assay/feature
   metadata, not tissue or title guesses. Multiple selections mean any selected
   modality. Filtering happens before the source result limit. Local inspection
   support describes supported formats, not verified contents of remote files.

Manual overrides are explicit, persisted with the inspection and visually marked.
They choose profile interpretation only. Source claims, file annotations,
validated structure and user choices remain separate evidence origins. An
unclassified H5AD keeps its general dashboard and is never silently called RNA.

## Phases and format boundaries

**Phase 1, this feature branch:** additive models/registry; H5AD profiles and
bounded data-backed panels; conservative H5MU inventory/correspondence adapter;
CLI/desktop profile override; discovery modality facet and inspection-support
labels; scientific, Qt, offline browser and packaging regression checks.

**Phase 2:** richer H5MU per-modality navigation and selected-feature queries;
complete streamed correspondence verification; SpatialData/Zarr metadata and
lazy element adapters with explicit coordinate-system graphs. Do not assume two
elements share a frame merely because they have coordinates of the same shape.

**Phase 3:** tiled OME-TIFF/OME-Zarr and segmentation adapters, validated overlays,
neighborhoods and region relations; imzML plus paired binary spectra, molecular
ion maps and MS metadata. Geometry and spectra stay in their native models.
SpatialData/Zarr, OME images, raw fragments and imzML are recognized boundaries,
not advertised as implemented full analysis support in phase 1.

## Scientific guardrails

- Bounded positive evidence does not prove that an unobserved modality is absent.
  All sampled feature/observation checks report the inspected denominator.
- Feature labels and file assay declarations are evidence of annotations, not
  independent validation of the experimental assay or count normalization.
- QC values must already exist. No TSS, FRiP, fragments, mitochondrial fractions,
  segmentation quality scores, thresholds or biological verdicts are invented.
- Spatial coordinates alone provide no physical units, image orientation or
  transform. Embedded images can be previewed independently; image overlays are
  withheld without validated mappings. No inferred pixel-to-micron conversion.
- Shared H5AD observation axes describe storage correspondence, not independently
  verified biological pairing. H5MU obsmap and varmap checks retain their own
  denominators; mismatches/duplicates/out-of-range entries disable joint views.
  Different feature families are never treated as the same biological features.
- Source files are opened read-only. Exports cannot overwrite source files.
  Sampling, resource limits, source stat checks and integrity limitations remain
  visible. No runtime CDNs, external images or network calls in exported HTML.

Format references: [AnnData](https://anndata.readthedocs.io/en/stable/fileformat-prose.html),
[MuData maps and axes](https://mudata.scverse.org/stable/io/spec.html),
[SpatialData transformations](https://spatialdata.scverse.org/en/stable/api/transformations.html).

## Validation plan

Generate deterministic RNA, ATAC, Visium-like, spatial-protein and RNA+ATAC/CITE
fixtures, including modern/sparse/legacy layouts. Preserve a separate provenance
manifest for public-data excerpts; do not relabel synthetic examples as public
measurements. Test absent/incomplete annotations, absent images, bad coordinate
axes, missing transforms, incompatible frames, mismatched barcodes, invalid maps,
unsupported formats and unsupported modality claims. Exercise profile selection,
hybrid modules and feature controls in offline Chromium, and modality filtering
and selection in Qt. Run Ruff, pytest, wheel/sdist and installed-asset checks.

## Implemented first-phase contracts

`H5ADInspection` adds optional `scientific` (schema 1) and `storage_format`
without removing existing fields or changing the common schema 2. Old inspection
JSON still renders. `ContainerInspection` reuses that report envelope only;
H5MU global dimensions describe axes and its matrix explicitly says
`container; no joint X`. No AnnData or MuData runtime dependency is introduced.

| Bound | Per H5AD or inspected native module |
| --- | --- |
| Feature evidence | Up to 4,096 evenly spaced var rows |
| Stored X previews | Up to 256 evenly spaced observations; first two observed features per annotated family, eight features maximum |
| Sparse scan | 2,000,000 stored entries, in chunks of at most 16,384; abort the entire feature preview when exceeded |
| Spatial coordinates | `obsm/spatial` and `obsm/X_spatial`, first two axes and up to 256 rows; retain source row positions after non-finite exclusions |
| Embedded images | First two library groups, one supported gray/RGB/RGBA image per library; prefer lowres, sample to at most 384 pixels per side |
| Native H5MU | First four direct modules; up to 4,096 global entries per obsmap/varmap |

These are selected-element bounds, not a hard process-RSS guarantee. HDF5 chunk
decompression, group inventories and individual variable-length strings have
format-level overhead. The existing general metadata/embedding bounds are
unchanged and are additional to the scientific preview bounds. Increasing GUI
"Max points" does not increase these fixed scientific limits.

Typed features use `var/feature_types`, `feature_type` or `modality` annotations:
gene expression/RNA; peaks/chromatin accessibility; antibody capture/protein;
molecular ions/mass-to-charge/metabolites. Interval-like names alone only
suggest ATAC. Scalar `uns/assay`, `modality` and `technology` declarations are
suggestions, not measurement verification. Unknown feature families retain a
generic stored-values preview. Previews come from X only: raw, layers,
arbitrary obsm protein matrices, fragments and gene-activity matrices require
future explicit adapters. Normalization and units are not inferred.

Recorded numeric TSS enrichment/score, FRiP, reads-in-peaks and fragment fields
are displayed as stored, alongside count/detected-feature metadata. Matching a
field name does not validate its definition, units or a QC threshold. Other
numeric metadata remains available in the common QC tab. No new QC metric is
calculated from X.

Spatial previews preserve numeric aspect ratio and use x-right/y-up display
axes, explicitly without a claimed tissue orientation. Optional
`uns/cellondesk_spatial/{coordinate_frame,image_frame,units}` scalar declarations
are retained literally; these are optional explicit application annotations,
not fields required by AnnData or assumed from Visium. Different reported
frames mark overlays invalid. Missing transforms and ordinary Visium scale
factors leave overlays unsupported: this adapter does not validate registration,
library-to-observation correspondence or orientation. No image is downloaded.

H5MU maps are read as 1-based integer vectors, zero meaning absent. Range,
duplicate-target and identifier agreement checks report inspected/total counts.
Full inspected maps can be `verified`, sampled maps only `sample_consistent`;
neither establishes experimental pairing. Renamed identifiers cannot be resolved
without explicit evidence and are treated as inconsistent. Global counts are
never summed from modules. Shared-cell coloring across module matrices is
disabled, even when their row counts match. Root metadata uses the common
foundation; richer per-module composition/embeddings and nested containers are
deferred.

Source assay hints remain in discovery records; file annotations and structural
evidence remain in local reports. Automatic persistence/linking of those two
records is deferred. The desktop accepts comma-separated manual profile IDs;
the CLI accepts repeated `--modality`. Overrides add a visibly manual
interpretation and preserve contradictory file evidence. They do not change
capability availability or write to the source.

## Reproducible scientific validation

`tests/modality_fixtures.py` creates synthetic modern, legacy, dense, CSR and CSC
layouts, hybrid feature axes and native H5MU maps. Tests include typed molecular
ions, CITE-like RNA/protein, malformed annotations, missing images, mismatched
spatial rows, non-finite values, incompatible frames, sparse duplicates and
invalid pointers, absent/out-of-range/duplicate maps and mismatched barcodes.

[Public excerpts and exact provenance](../tests/fixtures/public_modalities/README.md)
cover RNA and ATAC partitions of a 10x multiome, the combined shared-barcode
matrix, Visium and IMC. The IMC file deliberately remains unclassified without a
manual interpretation: its marker names alone are insufficient evidence.
Public fixture extraction is reproducible and separate from offline tests.

Real-data review scenarios:

1. Open the complete public Visium H5AD: RNA plus spatial profiles, actual stored
   QC and an independent image preview; verify the 256/684 scientific sample and
   4,096/18,078 feature-evidence warning. Never call stored transformed X raw counts.
2. Open the complete IMC H5AD: generic markers and coordinates, no automatic RNA
   or protein claim. Record `spatial_proteomics` manually; protein typing and
   segmentation remain unavailable.
3. Inspect a native multiome H5MU with shuffled module barcodes and explicit
   maps. Correct maps may agree even when row orders differ. Change one mapped
   barcode: it must report inconsistency and keep joint views disabled.
4. Search kidney with no assay, then with RNA/ATAC facets. Compare source matched
   versus returned counts, independent errors, cache request counters and
   unclassified exclusions. Advertised H5AD support must not become verified access.
5. Select Visium, MERFISH, CODEX/IMC, CITE-seq and generic multiomics assay labels;
   verify the distinct hints, then inspect actual files independently. Cold-cache
   latency/coverage remains source-dependent; do not infer full coverage from a
   fast warm-cache result.

## Validation results — 2026-10-09

On `agent/modality-dashboard-0.12.0`, Python 3.10.20, NumPy 2.2.6,
h5py 3.16.0, PySide6 6.11.2 and headless Chromium:

- Ruff: passed.
- Pytest: **200 passed, 12 skipped**; skipped cases are opt-in browser tests.
- Explicit offline Chromium run: **12 passed**, including six existing dashboard
  cases and six scientific-module cases. No HTTP requests or JavaScript errors.
  Checks include spatial geometry, row/color alignment, image separation,
  native-module isolation, manual interpretation, hostile labels and screenshots.
- Qt: selection, sorting/filtering, modality controls, independent source errors,
  worker-thread behavior and screenshots pass in the main suite.
- Wheel and sdist built; Twine checks passed. Archive inspection confirms all
  scientific reader modules and offline assets, small public excerpts in the
  sdist and exclusion of original public downloads. Installed-wheel report
  rendering, format-support lookup and Qt launch/worker smoke tests passed.
- Native Windows installer execution remains a Windows CI / real-machine check;
  this Linux run does not claim to validate an installed Windows executable.

Complete public-file smoke measurements (one local run, not a performance SLA):

| Input | Observations × features | Inspection | Scientific row sample | Result |
| --- | --- | --- | --- | --- |
| Visium cropped H5AD | 684 × 18,078 | 0.652 s | 256 | RNA + spatial profiles; one embedded image; 618 KB HTML |
| IMC H5AD | 4,668 × 34 | 0.021 s | 256 | Unclassified markers + spatial coordinates; no image; 631 KB HTML |

Full source SHA-256 values matched before and after inspection/export. Hashing
was performed by the validation harness, outside the inspector's bounded
stat-based integrity check. Reports and measurements are under ignored
`build/modality-dashboard/`; fixture source hashes are checked into the public
provenance manifest.

The deterministic kidney + RNA-facet benchmark retained 6/1/1 HuBMAP/CELLxGENE/
UCSC expected matches on both passes. CELLxGENE requests fell from 1 to 0 and
UCSC from 4 to 0; HuBMAP made 2 on each pass. Source times were approximately
4.0/1.2/1.5 ms cold and 1.9/1.0/1.4 ms warm. These timings exercise mocked
catalog transport, not repository network latency. Earlier live measurements
and partial-coverage limits remain in `DISCOVERY_ARCHITECTURE.md`.

Reproduce from an environment with the data, GUI, development and browser extras:

```bash
python -m ruff check .
QT_QPA_PLATFORM=offscreen python -m pytest -q
CELLONDESK_BROWSER_TESTS=1 CELLONDESK_BROWSER_ARTIFACTS=build/modality-dashboard \
  python -m pytest tests/test_h5ad_browser.py tests/test_modality_browser.py -v
python scripts/benchmark_discovery.py --modality rna \
  --cache-dir build/modality-benchmark-cache --output build/modality-benchmark.json
python -m build
python -m twine check dist/*
# After installing the wheel, outside an editable source import:
python -I scripts/check_h5ad_package.py
```

For a system Chrome installation, set `CELLONDESK_BROWSER_EXECUTABLE` to its
executable. Screenshots and exported reports are local review artifacts; no
release, deployment or merge is performed by these commands.

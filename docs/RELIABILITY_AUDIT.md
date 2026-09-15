# CellOnDesk reliability audit: 0.11.3 preview

Reviewed baseline: `dae014427d714d17fe7e2bc303d963c763e067cd` (merged PR #14, 0.11.2).
The matching 0.11.2 source distribution was obtained from the repository's CI artifact for local regression testing. No user datasets or exported HTML reports are included in this change.

## Findings and changes

| Finding in the source | Impact | Implemented correction |
| --- | --- | --- |
| Fallback file probes use a non-streaming GET | A Range-ignoring server can send an entire large dataset into memory during discovery | Shared header-only probe, streaming fallback closed without consuming the body; network/server errors are not treated as absence |
| A HuBMAP redirect is fetched with the authenticated search client | An external redirect can receive the bearer token | Fetch redirected results with the unauthenticated asset client |
| HuBMAP descendant parsing recursively treats every string as an ID | Titles/statuses can become bogus download probes | Extract only ID fields and explicit relationship containers |
| A complete small HuBMAP response triggers all assay fallbacks | Unnecessary requests and slow searches | Fall back only when the service returned an unusable locationless redirect |
| A single predictable `.part` path and unverified finalization | Transfers can conflict; truncated data can replace a good file | Unique temporary files, byte-count verification, HTML/partial-response rejection, explicit overwrite, atomic finalization and cancellation cleanup |
| Network/file work executes in the GUI event thread | Frozen window; manual processEvents permits re-entry | Dedicated worker, queued progress and modal input isolation; worker errors returned to the UI |
| UCSC child names can already be collection-qualified | Duplicate paths, failed file lookup | Normalize relative versus qualified paths and hydrate selected leaf metadata |
| UCSC direct URLs are prefixed as if they were filenames | Broken advertised asset links | Handle absolute/root-relative/relative URLs, reject traversal, deduplicate |
| NaN values count as non-null and unique | Misleading summary statistics | Finite numeric counts and distinct values; numerical category labels remain categorical |
| Every categorical read loads its entire dictionary | High-cardinality metadata defeats sampled inspection | Read only dictionary entries referenced by sampled codes |
| `velocity_umap` is treated as a coordinate embedding | Misleading position plot of displacement vectors | Keep it in the structure inventory, exclude it from coordinate previews with a note |
| Source-checkout Census provenance falls back to 0.11.0 | Incorrect software version in reports | One `_version.py`, used by runtime and Hatch packaging |
| Installer smoke tests only run diagnostics | Successful CI does not prove the GUI opens | Offscreen GUI/worker tests and actual packaged and installed GUI startup smoke |
| Packaging collects all PySide6 modules | Unnecessarily broad bundle scope | Use PyInstaller's normal Qt hooks; final size savings must be measured after the build |
| Push and PR CI overlap; no superseded-run cancellation | Redundant builds and notifications | Main pushes + PR validation, concurrency cancellation and pip caching |

## Validation

Local baseline: **42 passed, 1 failed**. The failure reproduced the stale 0.11.0 source-checkout provenance fallback (an installed wheel masks this specific failure).

Local patched tests: **69 passed, 1 skipped module** at the initial audit checkpoint. The skipped module contains the three Qt-specific tests because PySide6 is not installed in the local review runtime. The Windows packaging job installs PySide6 and runs those tests rather than skipping them. See the PR checks for the final, authoritative cross-platform/installer result.

New deterministic tests cover body-free probing against a Range-ignoring server, external-redirect credential isolation, download truncation, cancellation after the last chunk, preservation of existing/other writers' files, transport compression, invalid schemes, numerical missingness, bounded category dictionaries, vector-field exclusion, UCSC path forms and leaf inventories.

No claim of live HuBMAP/UCSC/CELLxGENE endpoint validation is made from the offline local runtime. Remote smoke tests are separate checks. No claim of a smaller installer is made before an artifact is measured.

## Remaining release work (not implemented here)

1. **HuBMAP product coverage:** metadata/file-inventory-based resolution and provenance traversal remain preferable to the current known-H5AD-filename probes. An offered CLT manifest is not a completed transfer. CLT/Globus authorization and execution remain external.
2. **UCSC bundle import:** expression, metadata and coordinates need explicit cell-ID alignment, matrix orientation validation, and bounded conversion before an H5AD can be created safely. Catalog traversal is still shallow and can miss child-only search terms.
3. **Optional Census total memory:** expression output is bounded, but `get_obs` still retrieves all matching observation metadata before sampling. Do not describe total Census RAM as bounded by `max_cells`; streaming observation selection is a separate task.
4. **HTTP polish:** no resume/range-restart, retry/backoff, service catalogue cache, download queue, or durable acquisition receipt yet. Byte-count verification does not replace provider checksums or complete H5AD validation.
5. **H5AD architecture:** the compatibility layer still patches shared reader helpers at import time. Consolidating these helpers and adding stricter sparse-layout checks would reduce maintenance risk. Sampling is deterministic, not a statistically representative sampling design.
6. **Release governance:** signed installers, locked packaging dependencies, protected-branch required checks, privacy/licensing review, and a written real-Windows acceptance record are still needed. This PR does not change account settings or merge itself.

## Next real-machine checks

Use only the successful **0.11.3** installer from this PR's Windows artifact. Confirm the version in the window title and the commit in `build-info.json`. Repeat a CELLxGENE H5AD download; cancel a second download and confirm no destination replacement. Try a nested UCSC dataset. Open a legacy scVelo file and check that velocity arrays remain listed but are not offered as position embeddings. Verify the window repaints during reads. Keep the existing source H5AD files unchanged.

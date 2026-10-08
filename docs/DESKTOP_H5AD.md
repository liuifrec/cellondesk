# Local H5AD desktop workspace

CellOnDesk provides bounded local H5AD inspection in the desktop application.
The 0.12.0 development milestone adds an offline scientific dashboard; see the
[architecture and validation guide](H5AD_DASHBOARD_ARCHITECTURE.md).

## Workflow

1. Open CellOnDesk and select the **Local H5AD** tab.
2. Choose an `.h5ad` file.
3. Optionally enter an observation annotation column such as `cell_type`.
4. Set the maximum number of sampled embedding points.
5. Select **Inspect**.
6. Export the result as a self-contained HTML report or JSON inspection record.

The HTML opens locally in a browser. Use **Embeddings** to choose a supplied
coordinate representation and color it by a categorical or numeric obs field.
**Cell composition** shows counts, percentages and sample cross-tabulations.
**QC & metadata** shows histograms only for existing numeric fields; none are
calculated from expression values. **Provenance** records reader versions,
sampling limits, file size/mtime and the scope of integrity checks.

Default metadata charts inspect at most 20,000 evenly spaced rows, separately
from the embedding point limit. These are deterministic samples, not population
estimates. Missing values are included in composition denominators and excluded
from finite-value histograms with explicit counts. Both HTML and JSON export
reject destinations that would overwrite the inspected source H5AD.

## Reported information

The workspace reports:

- observation and variable counts,
- matrix encoding, shape, and sparse non-zero count when available,
- layers and `obsm` keys,
- likely annotation column,
- bounded column summaries,
- up to four sampled two-dimensional embeddings,
- compatibility and sampling warnings.

## Memory behavior

The desktop workspace uses the same direct-HDF5 bounded reader as the command-line `inspect-h5ad` workflow. It does not load the full expression matrix, `uns` payloads, or spatial image pyramids. Source files are opened read-only and are never modified.

## Current limits

- The GUI does not yet draw the sampled embedding directly; the exported HTML report provides the interactive view.
- Single-gene expression preview remains available through the command line and is planned for the desktop workspace.
- Very unusual or non-standard AnnData encodings may be reported as unsupported rather than loaded eagerly.

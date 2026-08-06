# Local H5AD desktop workspace

CellOnDesk 0.10.0 adds bounded local H5AD inspection to the desktop application.

## Workflow

1. Open CellOnDesk and select the **Local H5AD** tab.
2. Choose an `.h5ad` file.
3. Optionally enter an observation annotation column such as `cell_type`.
4. Set the maximum number of sampled embedding points.
5. Select **Inspect**.
6. Export the result as a self-contained HTML report or JSON inspection record.

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

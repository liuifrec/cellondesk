# Bounded-memory gene expression preview

CellOnDesk 0.4.0 can read one gene from a local AnnData `.h5ad` file without loading the complete expression matrix.

```bash
pip install -e ".[data]"

cellondesk preview-gene dataset.h5ad CD3D \
  --max-points 10000 \
  --html CD3D-preview.html \
  --json CD3D-preview.json
```

Use `--layer counts` to read from a named AnnData layer instead of `X`.

## Supported storage

- Dense two-dimensional HDF5 arrays
- AnnData CSR sparse matrices
- AnnData CSC sparse matrices

Gene lookup checks the variable index and common symbol fields including `feature_name`, `gene_symbol`, `gene_symbols`, and `gene_name`. Exact matching is preferred; a case-insensitive fallback is reported as a warning.

## Memory behavior

- The variable axis is searched in bounded chunks.
- Only one feature column is read.
- CSR files read only the sampled observation rows.
- CSC files read only the selected feature column.
- The number of observations embedded in the report is capped by `--max-points`.
- The source file is never modified.

The HTML report is self-contained and can be shared or opened offline. It presents sampled expression, not full-dataset inferential statistics.

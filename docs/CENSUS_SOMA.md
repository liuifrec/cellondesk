# CELLxGENE Census / SOMA previews

CellOnDesk can query a bounded single-gene slice from the CELLxGENE Census without downloading a complete source H5AD file.

Install the optional backend:

```bash
pip install -e ".[census]"
```

Example:

```bash
cellondesk census-preview CD3D \
  --organism "Homo sapiens" \
  --tissue lung \
  --cell-type "T cell" \
  --disease normal \
  --max-cells 5000 \
  --json cd3d-lung-tcells.json
```

The command first queries observation metadata through the Census API, counts matching cells, selects at most `--max-cells` `soma_joinid` coordinates, and then requests only the selected cells and one exact feature from the `raw` RNA layer.

Supported filters:

- `organism`
- `tissue_general`
- `cell_type`
- `disease`
- `assay`
- `dataset_id`
- primary-data-only filtering, enabled by default
- Census release version, defaulting to `stable`

The resulting JSON includes the exact query, matched feature name and ID, total matching-cell count, sampled-cell count, sampled expression values, selected cell metadata, summary statistics, and truncation warnings.

## Design limits

- One exact gene symbol or feature ID per query.
- At most 50,000 cells are materialized.
- Sampling currently uses the first matching SOMA coordinates, not randomized sampling.
- The initial Census path produces JSON rather than an embedding dashboard.
- Census access remains optional and does not change local H5AD or HuBMAP dependencies.

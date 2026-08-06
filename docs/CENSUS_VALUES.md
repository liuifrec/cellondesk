# CELLxGENE Census metadata discovery

Use `census-values` before `census-preview` to discover exact metadata labels and their precomputed Census cell counts.

```bash
cellondesk census-values tissue_general --contains lung --limit 20
cellondesk census-values cell_type --contains "T cell" --json t-cell-values.json
cellondesk census-values assay --organism "Homo sapiens"
```

Supported fields:

- `assay`
- `cell_type`
- `development_stage`
- `disease`
- `self_reported_ethnicity`
- `sex`
- `suspension_type`
- `tissue`
- `tissue_general`

The command reads the Census `summary_cell_counts` table rather than scanning all observations. Results include the requested and resolved Census releases, ontology identifiers when available, total cell counts, unique cell counts when available, generation time, and CellOnDesk version.

A typical workflow is:

```bash
cellondesk census-values tissue_general --contains lung
cellondesk census-values cell_type --contains "T cell"
cellondesk census-preview CD3D \
  --tissue lung \
  --cell-type "T cell" \
  --census-version 2026-07-01 \
  --html CD3D-lung-t-cells.html \
  --json CD3D-lung-t-cells.json
```

For manuscript-grade work, use the resolved dated Census release from `census-values` as the explicit `--census-version` in the final query.

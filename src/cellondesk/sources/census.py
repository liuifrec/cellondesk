from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field


class CensusQuery(BaseModel):
    organism: str = "Homo sapiens"
    gene: str
    tissue: str | None = None
    cell_type: str | None = None
    disease: str | None = None
    assay: str | None = None
    dataset_id: str | None = None
    primary_only: bool = True
    census_version: str = "stable"
    max_cells: int = Field(default=5000, ge=1, le=50000)


class CensusGenePreview(BaseModel):
    query: CensusQuery
    matched_gene: str
    feature_id: str | None = None
    total_matching_cells: int
    sampled_cells: int
    nonzero_sampled: int
    minimum: float | None = None
    maximum: float | None = None
    mean: float | None = None
    p95: float | None = None
    cell_metadata: list[dict[str, Any]] = Field(default_factory=list)
    values: list[float] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_obs_value_filter(query: CensusQuery) -> str:
    clauses: list[str] = []
    if query.primary_only:
        clauses.append("is_primary_data == True")
    fields = {
        "tissue_general": query.tissue,
        "cell_type": query.cell_type,
        "disease": query.disease,
        "assay": query.assay,
        "dataset_id": query.dataset_id,
    }
    for field, value in fields.items():
        if value:
            clauses.append(f"{field} == {_quote(value)}")
    return " and ".join(clauses)


def build_var_value_filter(gene: str) -> str:
    gene = gene.strip()
    if not gene:
        raise ValueError("gene must not be empty")
    quoted = _quote(gene)
    return f"feature_name == {quoted} or feature_id == {quoted}"


def _require_census() -> Any:
    try:
        import cellxgene_census
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            'Install Census support with: pip install "cellondesk[census]"'
        ) from exc
    return cellxgene_census


def _to_records(frame: Any, columns: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for _, row in frame[columns].iterrows():
        records.append({column: row[column] for column in columns})
    return records


def preview_census_gene(
    query: CensusQuery,
    *,
    census_module: Any | None = None,
) -> CensusGenePreview:
    """Retrieve a bounded single-gene slice from CELLxGENE Census.

    The function delegates filtering to the Census/SOMA service and materializes only
    one requested feature plus selected observation metadata.
    """
    census = census_module or _require_census()
    obs_filter = build_obs_value_filter(query)
    var_filter = build_var_value_filter(query.gene)
    obs_columns = [
        "soma_joinid",
        "cell_type",
        "tissue_general",
        "disease",
        "assay",
        "dataset_id",
    ]

    adata = census.get_anndata(
        census_version=query.census_version,
        organism=query.organism,
        measurement_name="RNA",
        X_name="raw",
        obs_value_filter=obs_filter or None,
        var_value_filter=var_filter,
        obs_column_names=obs_columns,
    )
    total = int(adata.n_obs)
    if int(adata.n_vars) < 1:
        raise ValueError(f"Gene {query.gene!r} was not found in CELLxGENE Census.")

    sampled = min(total, query.max_cells)
    subset = adata[:sampled, :1]
    matrix = subset.X
    if hasattr(matrix, "toarray"):
        values = matrix.toarray().reshape(-1)
    else:
        values = matrix.reshape(-1)

    import numpy as np

    values = np.asarray(values, dtype=float)
    matched_gene = str(subset.var.iloc[0].get("feature_name", query.gene))
    feature_id_value = subset.var.iloc[0].get("feature_id")
    feature_id = None if feature_id_value is None else str(feature_id_value)
    finite = values[np.isfinite(values)]
    nonzero = int(np.count_nonzero(finite))
    warnings: list[str] = []
    if total > sampled:
        warnings.append(
            f"Preview limited to the first {sampled:,} of {total:,} matching cells."
        )

    metadata_columns = [column for column in obs_columns if column in subset.obs.columns]
    metadata = _to_records(subset.obs, metadata_columns)
    return CensusGenePreview(
        query=query,
        matched_gene=matched_gene,
        feature_id=feature_id,
        total_matching_cells=total,
        sampled_cells=sampled,
        nonzero_sampled=nonzero,
        minimum=float(np.min(finite)) if finite.size else None,
        maximum=float(np.max(finite)) if finite.size else None,
        mean=float(np.mean(finite)) if finite.size else None,
        p95=float(np.percentile(finite, 95)) if finite.size else None,
        cell_metadata=metadata,
        values=[float(value) for value in values],
        warnings=warnings,
    )


__all__ = [
    "CensusGenePreview",
    "CensusQuery",
    "build_obs_value_filter",
    "build_var_value_filter",
    "preview_census_gene",
]

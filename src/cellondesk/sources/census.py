from __future__ import annotations

from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
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


class DatasetCitation(BaseModel):
    dataset_id: str
    citation: str | None = None


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
    requested_census_version: str | None = None
    resolved_census_version: str | None = None
    generated_at_utc: str | None = None
    cellondesk_version: str | None = None
    dataset_citations: list[DatasetCitation] = Field(default_factory=list)
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


def _to_python(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value


def _to_records(frame: Any, columns: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for _, row in frame[columns].iterrows():
        records.append({column: _to_python(row[column]) for column in columns})
    return records


def _cellondesk_version() -> str:
    try:
        return version("cellondesk")
    except PackageNotFoundError:  # pragma: no cover - source checkout
        return "0.7.0"


def _resolve_census_version(census: Any, requested: str) -> str:
    describe = getattr(census, "get_census_version_description", None)
    if describe is None:
        return requested
    try:
        description = describe(requested)
    except Exception:  # pragma: no cover - remote metadata failure
        return requested
    if isinstance(description, dict):
        for key in ("release_build", "release_date", "census_version"):
            value = description.get(key)
            if value:
                return str(value)
    return requested


def _dataset_citations(census_object: Any, dataset_ids: list[str]) -> list[DatasetCitation]:
    unique_ids = sorted(set(dataset_ids))
    if not unique_ids:
        return []
    try:
        table = census_object["census_info"]["datasets"]
        frame = table.read(column_names=["dataset_id", "citation"]).concat().to_pandas()
        citations = {
            str(row["dataset_id"]): str(row["citation"])
            for _, row in frame.iterrows()
            if row.get("citation")
        }
    except Exception:  # pragma: no cover - schema/API compatibility fallback
        citations = {}
    return [
        DatasetCitation(dataset_id=dataset_id, citation=citations.get(dataset_id))
        for dataset_id in unique_ids
    ]


def preview_census_gene(
    query: CensusQuery,
    *,
    census_module: Any | None = None,
) -> CensusGenePreview:
    """Retrieve a bounded, provenance-rich single-gene slice from CELLxGENE Census."""
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
    resolved_version = _resolve_census_version(census, query.census_version)

    with census.open_soma(census_version=query.census_version) as census_object:
        obs = census.get_obs(
            census_object,
            query.organism,
            value_filter=obs_filter or None,
            column_names=obs_columns,
        )
        total = int(len(obs))
        if total == 0:
            raise ValueError("No Census cells matched the requested filters.")

        sampled = min(total, query.max_cells)
        sampled_obs = obs.iloc[:sampled].copy()
        obs_coords = sampled_obs["soma_joinid"].tolist()
        adata = census.get_anndata(
            census_object,
            organism=query.organism,
            measurement_name="RNA",
            X_name="raw",
            obs_coords=obs_coords,
            var_value_filter=var_filter,
            obs_column_names=obs_columns,
            var_column_names=["feature_id", "feature_name"],
        )
        dataset_ids = [str(value) for value in adata.obs.get("dataset_id", [])]
        citations = _dataset_citations(census_object, dataset_ids)

    if int(adata.n_vars) < 1:
        raise ValueError(f"Gene {query.gene!r} was not found in CELLxGENE Census.")
    if int(adata.n_vars) > 1:
        raise ValueError(
            f"Gene query {query.gene!r} matched more than one Census feature. "
            "Use an exact feature ID."
        )

    matrix = adata.X
    if hasattr(matrix, "toarray"):
        values = matrix.toarray().reshape(-1)
    else:
        values = matrix.reshape(-1)

    import numpy as np

    values = np.asarray(values, dtype=float)
    matched_gene = str(adata.var.iloc[0].get("feature_name", query.gene))
    feature_id_value = adata.var.iloc[0].get("feature_id")
    feature_id = None if feature_id_value is None else str(feature_id_value)
    finite = values[np.isfinite(values)]
    nonzero = int(np.count_nonzero(finite))
    warnings: list[str] = []
    if total > sampled:
        warnings.append(
            f"Preview limited to the first {sampled:,} of {total:,} matching cells."
        )
    if any(item.citation is None for item in citations):
        warnings.append(
            "Some contributing Census datasets did not expose a citation string; "
            "their dataset IDs are retained for manual attribution."
        )

    metadata_columns = [column for column in obs_columns if column in adata.obs.columns]
    metadata = _to_records(adata.obs, metadata_columns)
    return CensusGenePreview(
        query=query,
        matched_gene=matched_gene,
        feature_id=feature_id,
        total_matching_cells=total,
        sampled_cells=int(adata.n_obs),
        nonzero_sampled=nonzero,
        minimum=float(np.min(finite)) if finite.size else None,
        maximum=float(np.max(finite)) if finite.size else None,
        mean=float(np.mean(finite)) if finite.size else None,
        p95=float(np.percentile(finite, 95)) if finite.size else None,
        cell_metadata=metadata,
        values=[float(value) for value in values],
        requested_census_version=query.census_version,
        resolved_census_version=resolved_version,
        generated_at_utc=datetime.now(UTC).isoformat(),
        cellondesk_version=_cellondesk_version(),
        dataset_citations=citations,
        warnings=warnings,
    )


__all__ = [
    "CensusGenePreview",
    "CensusQuery",
    "DatasetCitation",
    "build_obs_value_filter",
    "build_var_value_filter",
    "preview_census_gene",
]

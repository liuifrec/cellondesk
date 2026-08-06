from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from .census_report import write_census_report
from .expression import inspect_gene_expression
from .gene_report import write_gene_expression_report
from .h5ad_compat import inspect_h5ad as inspect_h5ad_file
from .h5ad_report import write_h5ad_report
from .manifest import write_hubmap_manifest
from .report import write_html_report
from .sources.census import CensusQuery, preview_census_gene
from .sources.hubmap import HuBMAPClient

app = typer.Typer(help="Search, inspect, and prepare public single-cell and spatial omics data.")


@app.command()
def search(
    dataset_type: Annotated[str | None, typer.Option(help="Exact HuBMAP dataset type")] = None,
    organ: Annotated[str | None, typer.Option(help="Exact HuBMAP organ code")] = None,
    status: Annotated[str | None, typer.Option(help="Dataset status")] = "Published",
    limit: Annotated[int, typer.Option(min=1, max=1000)] = 50,
    json_output: Annotated[Path | None, typer.Option("--json", help="Write normalized JSON")] = None,
    manifest: Annotated[Path | None, typer.Option(help="Write HuBMAP CLT manifest")] = None,
    html_report: Annotated[
        Path | None,
        typer.Option("--html", help="Write a self-contained HTML dashboard"),
    ] = None,
) -> None:
    with HuBMAPClient() as client:
        records = client.search_datasets(
            dataset_type=dataset_type,
            organ=organ,
            status=status,
            limit=limit,
        )
    for record in records:
        typer.echo(f"{record.dataset_id}\t{record.dataset_type or ''}\t{record.title}")
    if json_output:
        json_output.write_text(
            json.dumps(
                [record.model_dump() for record in records],
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    if manifest:
        write_hubmap_manifest(records, manifest)
    if html_report:
        write_html_report(
            records,
            html_report,
            query={
                "source": "HuBMAP",
                "dataset_type": dataset_type,
                "organ": organ,
                "status": status,
                "limit": limit,
            },
        )


@app.command("inspect-h5ad")
def inspect_h5ad_command(
    path: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True),
    ],
    html_report: Annotated[
        Path | None,
        typer.Option("--html", help="Write a self-contained local H5AD dashboard"),
    ] = None,
    json_output: Annotated[
        Path | None,
        typer.Option("--json", help="Write the structural inspection as JSON"),
    ] = None,
    annotation: Annotated[
        str | None,
        typer.Option(help="Observation column used to color embedding previews"),
    ] = None,
    max_points: Annotated[
        int,
        typer.Option(min=1, max=50000, help="Maximum sampled points per embedding"),
    ] = 5000,
) -> None:
    inspection = inspect_h5ad_file(
        path,
        max_points=max_points,
        annotation=annotation,
    )
    typer.echo(
        f"{inspection.file_name}: {inspection.n_obs:,} observations x "
        f"{inspection.n_vars:,} variables; {len(inspection.embeddings)} embeddings"
    )
    if json_output:
        json_output.write_text(
            inspection.model_dump_json(indent=2),
            encoding="utf-8",
        )
    if html_report:
        write_h5ad_report(inspection, html_report)
        typer.echo(f"Wrote {html_report}")


@app.command("preview-gene")
def preview_gene_command(
    path: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True),
    ],
    gene: Annotated[str, typer.Argument(help="Gene identifier or symbol")],
    html_report: Annotated[
        Path,
        typer.Option("--html", help="Write a self-contained expression dashboard"),
    ] = Path("gene-expression.html"),
    json_output: Annotated[
        Path | None,
        typer.Option("--json", help="Write sampled expression values as JSON"),
    ] = None,
    layer: Annotated[
        str | None,
        typer.Option(help="Read from a named layer instead of X"),
    ] = None,
    max_points: Annotated[
        int,
        typer.Option(min=1, max=50000, help="Maximum sampled observations"),
    ] = 5000,
) -> None:
    inspection = inspect_h5ad_file(path, max_points=max_points)
    expression = inspect_gene_expression(
        path,
        gene,
        max_points=max_points,
        layer=layer,
        embedding_keys=[item.key for item in inspection.embeddings],
    )
    write_gene_expression_report(inspection, expression, html_report)
    typer.echo(
        f"{expression.matched_gene}: {expression.nonzero_sampled:,} non-zero values "
        f"among {expression.sampled_observations:,} sampled observations"
    )
    typer.echo(f"Wrote {html_report}")
    if json_output:
        json_output.write_text(expression.model_dump_json(indent=2), encoding="utf-8")


@app.command("census-preview")
def census_preview_command(
    gene: Annotated[str, typer.Argument(help="Exact gene symbol or feature ID")],
    organism: Annotated[str, typer.Option(help="Census organism label")] = "Homo sapiens",
    tissue: Annotated[str | None, typer.Option(help="Exact tissue_general value")] = None,
    cell_type: Annotated[str | None, typer.Option(help="Exact cell_type value")] = None,
    disease: Annotated[str | None, typer.Option(help="Exact disease value")] = None,
    assay: Annotated[str | None, typer.Option(help="Exact assay value")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Exact CELLxGENE dataset ID")] = None,
    census_version: Annotated[str, typer.Option(help="Census version or stable alias")] = "stable",
    max_cells: Annotated[
        int,
        typer.Option(min=1, max=50000, help="Maximum cells materialized from SOMA"),
    ] = 5000,
    include_non_primary: Annotated[
        bool,
        typer.Option("--include-non-primary", help="Include duplicated/non-primary cells"),
    ] = False,
    json_output: Annotated[
        Path | None,
        typer.Option("--json", help="Write the bounded Census preview as JSON"),
    ] = Path("census-gene-preview.json"),
    html_report: Annotated[
        Path | None,
        typer.Option("--html", help="Write a self-contained Census expression dashboard"),
    ] = Path("census-gene-preview.html"),
) -> None:
    result = preview_census_gene(
        CensusQuery(
            organism=organism,
            gene=gene,
            tissue=tissue,
            cell_type=cell_type,
            disease=disease,
            assay=assay,
            dataset_id=dataset_id,
            primary_only=not include_non_primary,
            census_version=census_version,
            max_cells=max_cells,
        )
    )
    if json_output:
        json_output.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        typer.echo(f"Wrote {json_output}")
    if html_report:
        write_census_report(result, html_report)
        typer.echo(f"Wrote {html_report}")
    typer.echo(
        f"{result.matched_gene}: {result.nonzero_sampled:,} non-zero values among "
        f"{result.sampled_cells:,} sampled cells ({result.total_matching_cells:,} matched)"
    )

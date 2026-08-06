from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from .manifest import write_hubmap_manifest
from .sources.hubmap import HuBMAPClient

app = typer.Typer(help="Search and prepare public single-cell and spatial omics datasets.")


@app.command()
def search(
    dataset_type: Annotated[str | None, typer.Option(help="Exact HuBMAP dataset type")] = None,
    organ: Annotated[str | None, typer.Option(help="Exact HuBMAP organ code")] = None,
    status: Annotated[str | None, typer.Option(help="Dataset status")] = "Published",
    limit: Annotated[int, typer.Option(min=1, max=1000)] = 50,
    json_output: Annotated[Path | None, typer.Option("--json", help="Write normalized JSON")] = None,
    manifest: Annotated[Path | None, typer.Option(help="Write HuBMAP CLT manifest")] = None,
) -> None:
    with HuBMAPClient() as client:
        records = client.search_datasets(dataset_type=dataset_type, organ=organ,
                                         status=status, limit=limit)
    for record in records:
        typer.echo(f"{record.dataset_id}\t{record.dataset_type or ''}\t{record.title}")
    if json_output:
        json_output.write_text(
            json.dumps([r.model_dump() for r in records], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    if manifest:
        write_hubmap_manifest(records, manifest)

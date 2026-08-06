from __future__ import annotations

import json
import tempfile
from pathlib import Path

from cellondesk.report import write_html_report
from cellondesk.sources.hubmap import HuBMAPClient


def main() -> None:
    query = {
        "source": "HuBMAP",
        "dataset_type": "CODEX",
        "organ": "SP",
        "status": "Published",
        "limit": 3,
    }
    with HuBMAPClient(timeout=45.0) as client:
        records = client.search_datasets(
            dataset_type="CODEX",
            organ="SP",
            status="Published",
            limit=3,
        )

    if not records:
        raise SystemExit("HuBMAP returned no published spleen CODEX datasets")
    if any(not record.dataset_id for record in records):
        raise SystemExit("At least one live HuBMAP record has no dataset identifier")

    with tempfile.TemporaryDirectory() as tmpdir:
        destination = Path(tmpdir) / "hubmap-live-summary.html"
        write_html_report(records, destination, query=query)
        html = destination.read_text(encoding="utf-8")
        checks = {
            "doctype": "<!doctype html>" in html.lower(),
            "records_embedded": 'id="records-data"' in html,
            "first_dataset_embedded": records[0].dataset_id in html,
            "offline_assets": "cdn." not in html and "https://unpkg.com" not in html,
            "spatial_assay": all(record.dataset_type == "CODEX" for record in records),
            "published": all(record.status == "Published" for record in records),
        }
        if not all(checks.values()):
            raise SystemExit(f"HTML smoke checks failed: {json.dumps(checks)}")
        print(
            json.dumps(
                {
                    "dataset_count": len(records),
                    "dataset_ids": [record.dataset_id for record in records],
                    "html_bytes": destination.stat().st_size,
                    "checks": checks,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()

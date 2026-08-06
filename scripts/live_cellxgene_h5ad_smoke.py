from __future__ import annotations

import json
import tempfile
import urllib.request
from pathlib import Path

from cellondesk.expression import inspect_gene_expression
from cellondesk.gene_report import write_gene_expression_report
from cellondesk.inspection import inspect_h5ad

SOURCE_URL = "https://cellxgene-example-data.czi.technology/pbmc3k.h5ad"


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        source = Path(tmpdir) / "pbmc3k.h5ad"
        report_path = Path(tmpdir) / "pbmc3k-cd3d.html"
        urllib.request.urlretrieve(SOURCE_URL, source)

        inspection = inspect_h5ad(source, max_points=1000)
        expression = inspect_gene_expression(
            source,
            "CD3D",
            max_points=1000,
            embedding_keys=[item.key for item in inspection.embeddings],
        )
        write_gene_expression_report(inspection, expression, report_path)
        report = report_path.read_text(encoding="utf-8")

        checks = {
            "observations": inspection.n_obs > 1000,
            "variables": inspection.n_vars > 1000,
            "gene_match": expression.matched_gene.upper() == "CD3D",
            "sampled_expression": expression.sampled_observations == 1000,
            "nonzero_expression": expression.nonzero_sampled > 0,
            "embedding": bool(expression.embedding_values),
            "offline_html": "cdn." not in report and "https://unpkg.com" not in report,
            "embedded_payload": 'id="report-data"' in report and "CD3D" in report,
        }
        if not all(checks.values()):
            raise SystemExit(f"Live CELLxGENE H5AD smoke failed: {json.dumps(checks)}")

        print(
            json.dumps(
                {
                    "source": SOURCE_URL,
                    "file_bytes": source.stat().st_size,
                    "observations": inspection.n_obs,
                    "variables": inspection.n_vars,
                    "embeddings": [item.key for item in inspection.embeddings],
                    "matched_gene": expression.matched_gene,
                    "nonzero_sampled": expression.nonzero_sampled,
                    "report_bytes": report_path.stat().st_size,
                    "checks": checks,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()

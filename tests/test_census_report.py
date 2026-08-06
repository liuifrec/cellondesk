from __future__ import annotations

from cellondesk.census_report import render_census_report
from cellondesk.sources.census import CensusGenePreview, CensusQuery


def test_census_report_is_self_contained() -> None:
    preview = CensusGenePreview(
        query=CensusQuery(
            organism="Homo sapiens",
            gene="CD3D",
            tissue="lung",
            cell_type="T cell",
            max_cells=4,
        ),
        matched_gene="CD3D",
        feature_id="ENSG00000167286",
        total_matching_cells=10,
        sampled_cells=4,
        nonzero_sampled=3,
        minimum=0.0,
        maximum=7.0,
        mean=2.75,
        p95=6.4,
        cell_metadata=[
            {
                "soma_joinid": 1,
                "cell_type": "T cell",
                "tissue_general": "lung",
                "disease": "normal",
                "assay": "10x 3' v3",
                "dataset_id": "dataset-a",
            },
            {
                "soma_joinid": 2,
                "cell_type": "T cell",
                "tissue_general": "lung",
                "disease": "normal",
                "assay": "10x 3' v3",
                "dataset_id": "dataset-a",
            },
            {
                "soma_joinid": 3,
                "cell_type": "T cell",
                "tissue_general": "lung",
                "disease": "normal",
                "assay": "10x 5' v2",
                "dataset_id": "dataset-b",
            },
            {
                "soma_joinid": 4,
                "cell_type": "T cell",
                "tissue_general": "lung",
                "disease": "normal",
                "assay": "10x 5' v2",
                "dataset_id": "dataset-b",
            },
        ],
        values=[0.0, 1.0, 3.0, 7.0],
        warnings=["Preview limited to four cells."],
    )

    report = render_census_report(preview)

    assert "CellOnDesk Census Gene Preview" in report
    assert "CD3D" in report
    assert "dataset-a" in report
    assert 'id="report-data"' in report
    assert "https://" not in report
    assert "cdn." not in report
    assert "Preview limited to four cells." in report

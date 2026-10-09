import httpx
import pytest

from cellondesk.catalog_cache import CatalogCache
from cellondesk.discovery import DiscoveryService, SearchQuery
from cellondesk.modality import assay_profiles
from cellondesk.models import DatasetRecord
from cellondesk.search_metadata import annotate_modalities
from cellondesk.sources.cellxgene_discover import CellxGeneDiscoverClient
from cellondesk.sources.hubmap import HuBMAPClient
from cellondesk.sources.ucsc_cellbrowser import UCSCCellBrowserClient


@pytest.mark.parametrize(
    "assay,expected",
    [
        ("RNAseq", ["rna"]),
        ("snATAC-seq", ["atac"]),
        ("Visium", ["rna", "spatial_transcriptomics"]),
        ("MERFISH", ["rna", "spatial_transcriptomics"]),
        ("CODEX", ["spatial_proteomics"]),
        ("IMC", ["spatial_proteomics"]),
        ("RNA-seq + ATAC-seq", ["rna", "atac", "multiomics"]),
        ("CITE-seq", ["rna", "multiomics"]),
        ("multiomics", ["multiomics"]),
        ("MALDI-IMS", ["spatial_metabolomics"]),
        (None, []),
        ("unknown", []),
        ("kidney", []),
    ],
)
def test_assay_hints_are_conservative_multivalued_and_not_file_verification(assay, expected):
    assert assay_profiles(assay) == expected
    record = annotate_modalities(
        DatasetRecord(
            source="Example",
            dataset_id="original-id",
            title="Visium RNA multiome atlas",
            organ="kidney",
            dataset_type=assay,
        )
    )
    assert record.reported_modalities == expected
    assert not record.file_verified_modalities
    assert all(
        e.origin == "source_assay" and "not verified" in e.scope for e in record.modality_evidence
    )


def test_advertised_formats_preserve_acquisition_and_do_not_probe_assets():
    record = annotate_modalities(
        DatasetRecord(
            source="Example",
            dataset_id="id",
            title="Title",
            dataset_type="ATAC-seq",
            asset_status="advertised",
            acquisition_methods=["Direct download (advertised)"],
            raw={"assets": [{"filetype": "H5MU"}, {"url": "https://invalid.test/native.ome.zarr"}]},
        )
    )
    assert any(
        "MuData" in value and "not checked" in value for value in record.local_inspection_support
    )
    assert any("Planned" in value for value in record.local_inspection_support)
    assert record.asset_status == "advertised"
    assert record.acquisition_methods == ["Direct download (advertised)"]


@pytest.mark.parametrize("source", ["hubmap", "cellxgene", "ucsc"])
def test_modality_matches_after_earlier_nonmatching_results_before_limit_and_cache(
    tmp_path, source
):
    assays = ["unclassified", "RNAseq", "ATAC-seq", "CODEX", "RNA-seq + ATAC-seq"]
    requests = []

    def handler(request):
        requests.append(request)
        assert request.method == "GET"
        if source == "hubmap":
            data = [
                {"uuid": f"id-{i}", "dataset_type": assay, "status": "Published"}
                for i, assay in enumerate(assays)
            ]
        elif source == "cellxgene":
            data = [
                {"dataset_id": f"id-{i}", "title": assay, "assay": [{"label": assay}]}
                for i, assay in enumerate(assays)
            ]
        elif request.url.path == "/dataset.json":
            data = {
                "datasets": [
                    {"name": "parent", "isCollection": True, "facets": {"assays": ["RNAseq"]}}
                ]
            }
        else:
            data = {
                "datasets": [
                    {
                        "name": f"id-{i}",
                        "shortLabel": assay,
                        "facets": {"assays": [assay]},
                        "sampleCount": 10,
                    }
                    for i, assay in enumerate(assays)
                ]
            }
        return httpx.Response(200, json=data)

    common = {"transport": httpx.MockTransport(handler)}
    if source != "hubmap":
        common["cache"] = CatalogCache(tmp_path)
    factory = {
        "hubmap": HuBMAPClient,
        "cellxgene": CellxGeneDiscoverClient,
        "ucsc": UCSCCellBrowserClient,
    }[source]
    service = DiscoveryService(factories={source: lambda budget: factory(**common, budget=budget)})
    query = SearchQuery(modalities=("atac", "spatial_proteomics"), sources=(source,), limit=1)
    first = service.search(query)[0]
    assert not first.error
    assert first.stats.matched == 3 and first.stats.truncated
    assert first.records[0].dataset_id.endswith("id-2")
    assert first.records[0].reported_modalities == ["atac"]
    assert "unclassified" in " ".join(first.notices).lower()
    count = len(requests)
    second = service.search(query)[0]
    assert second.stats.matched == 3
    if source != "hubmap":
        assert len(requests) == count
        assert second.stats.requests == 0 and second.stats.cache_hits > 0

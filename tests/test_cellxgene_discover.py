import httpx
import pytest

from cellondesk.models import DatasetRecord
from cellondesk.sources.cellxgene_discover import (
    CENSUS_RELEASE_DIRECTORY_URL,
    DATASET_INDEX_URL,
    CellxGeneDiscoverClient,
)


def _payload():
    return [
        {
            "id": "kidney-1",
            "name": "Human kidney atlas",
            "collection_id": "collection-a",
            "cell_count": 120000,
            "tissue": [{"label": "kidney"}],
            "disease": [{"label": "normal"}],
            "organism": [{"label": "Homo sapiens"}],
            "cell_type": [{"label": "endothelial cell"}],
            "assay": [{"label": "10x 3' v3"}],
            "explorer_url": "https://cellxgene.cziscience.com/e/kidney-1.cxg/",
            "assets": {
                "dataset_h5ad": {
                    "url": "https://example.test/kidney-1.h5ad",
                    "filesize": 123456,
                    "filetype": "H5AD",
                }
            },
        },
        {
            "id": "brain-1",
            "name": "Mouse brain atlas",
            "collection_id": "collection-b",
            "cell_count": 50000,
            "tissue": [{"label": "brain"}],
            "disease": [{"label": "normal"}],
            "organism": [{"label": "Mus musculus"}],
            "cell_type": [{"label": "neuron"}],
            "assay": [{"label": "Smart-seq2"}],
        },
    ]


def test_cellxgene_discover_filters_public_index():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == DATASET_INDEX_URL
        return httpx.Response(200, json=_payload())

    client = CellxGeneDiscoverClient(transport=httpx.MockTransport(handler))
    records = client.search_datasets(tissue="kidney", organism="Homo sapiens")
    client.close()

    assert len(records) == 1
    assert records[0].dataset_id == "kidney-1"
    assert records[0].organ == "kidney"
    assert records[0].dataset_type == "10x 3' v3"
    assert records[0].access_level == "public"
    assert records[0].portal_url.endswith("kidney-1.cxg/")


def test_cellxgene_discover_resolves_h5ad_assets():
    client = CellxGeneDiscoverClient(transport=httpx.MockTransport(lambda _request: httpx.Response(200)))
    record = DatasetRecord(
        source="CELLxGENE Discover",
        dataset_id="kidney-1",
        title="Human kidney atlas",
        raw=_payload()[0],
    )
    assets = client.resolve_assets(record)
    client.close()

    assert len(assets) == 1
    assert assets[0].name == "kidney-1.h5ad"
    assert assets[0].size_bytes == 123456
    assert assets[0].is_h5ad is True


def test_cellxgene_discover_falls_back_to_census_source_h5ad():
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == CENSUS_RELEASE_DIRECTORY_URL:
            return httpx.Response(
                200,
                json={
                    "stable": "2025-01-30",
                    "2025-01-30": {
                        "release_build": "2025-01-30",
                        "h5ads": {
                            "uri": (
                                "s3://cellxgene-census-public-us-west-2/"
                                "cell-census/2025-01-30/h5ads/"
                            ),
                            "s3_region": "us-west-2",
                        },
                    },
                },
            )
        if (
            request.method == "HEAD"
            and request.url.host == "cellxgene-census-public-us-west-2.s3.us-west-2.amazonaws.com"
            and request.url.path.endswith("/brain-1.h5ad")
        ):
            return httpx.Response(200, headers={"content-length": "4096"})
        return httpx.Response(404)

    client = CellxGeneDiscoverClient(transport=httpx.MockTransport(handler))
    record = DatasetRecord(
        source="CELLxGENE Discover",
        dataset_id="brain-1",
        title="Mouse brain atlas",
        raw=_payload()[1],
    )
    assets = client.resolve_assets(record)
    client.close()

    assert len(assets) == 1
    assert assets[0].name == "brain-1.h5ad"
    assert assets[0].size_bytes == 4096
    assert assets[0].is_h5ad is True
    assert assets[0].raw["census_release"] == "2025-01-30"


def test_cellxgene_discover_text_search_and_cell_count_sorting():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_payload())

    client = CellxGeneDiscoverClient(transport=httpx.MockTransport(handler))
    records = client.search_datasets(query="atlas", limit=2)
    client.close()
    assert [record.dataset_id for record in records] == ["kidney-1", "brain-1"]


def test_cellxgene_discover_requires_filter():
    client = CellxGeneDiscoverClient(transport=httpx.MockTransport(lambda _request: httpx.Response(200)))
    with pytest.raises(ValueError, match="Provide at least one CELLxGENE filter"):
        client.search_datasets()
    client.close()

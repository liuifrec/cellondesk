import httpx
import pytest

from cellondesk.models import DatasetRecord
from cellondesk.sources.cellxgene_discover import DATASET_INDEX_URL, CellxGeneDiscoverClient


def _payload():
    return [
        {
            "dataset_id": "kidney-1",
            "dataset_version_id": "kidney-version-1",
            "title": "Human kidney atlas",
            "collection_id": "collection-a",
            "collection_name": "Kidney collection",
            "cell_count": 120000,
            "tissue": [{"label": "kidney"}],
            "disease": [{"label": "normal"}],
            "organism": [{"label": "Homo sapiens"}],
            "cell_type": [{"label": "endothelial cell"}],
            "assay": [{"label": "10x 3' v3"}],
            "explorer_url": "https://cellxgene.cziscience.com/e/kidney-1.cxg/",
            "assets": [
                {
                    "url": "https://datasets.cellxgene.cziscience.com/kidney-version-1.h5ad",
                    "filesize": 123456,
                    "filetype": "H5AD",
                }
            ],
        },
        {
            "dataset_id": "brain-1",
            "dataset_version_id": "brain-version-1",
            "title": "Mouse brain atlas",
            "collection_id": "collection-b",
            "collection_name": "Brain collection",
            "cell_count": 50000,
            "tissue": [{"label": "brain"}],
            "disease": [{"label": "normal"}],
            "organism": [{"label": "Mus musculus"}],
            "cell_type": [{"label": "neuron"}],
            "assay": [{"label": "Smart-seq2"}],
            "assets": [
                {
                    "url": "https://datasets.cellxgene.cziscience.com/brain-version-1.h5ad",
                    "filesize": 654321,
                    "filetype": "H5AD",
                }
            ],
        },
    ]


def test_cellxgene_discover_filters_public_dataset_feed():
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


def test_cellxgene_discover_resolves_published_h5ad_asset():
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
    assert assets[0].name == "kidney-version-1.h5ad"
    assert assets[0].size_bytes == 123456
    assert assets[0].is_h5ad is True
    assert assets[0].download_url.endswith("kidney-version-1.h5ad")


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

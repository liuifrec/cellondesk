import httpx
import pytest

from cellondesk.sources.cellxgene_discover import DATASET_INDEX_URL, CellxGeneDiscoverClient


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

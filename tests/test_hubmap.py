import httpx

from cellondesk.sources.hubmap import HuBMAPClient, _extract_hits


def test_extracts_elasticsearch_hits():
    payload = {"hits": {"hits": [{"_source": {"uuid": "abc"}}]}}
    assert _extract_hits(payload) == [{"uuid": "abc"}]


def test_search_normalizes_dataset():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["entity_type"] == "Dataset"
        return httpx.Response(200, json=[{"uuid": "123", "hubmap_id": "HBM123",
            "dataset_type": "Visium (no probes)", "status": "Published", "organ": "LK"}])

    client = HuBMAPClient(transport=httpx.MockTransport(handler))
    records = client.search_datasets(dataset_type="Visium (no probes)", organ="LK")
    client.close()
    assert records[0].dataset_id == "123"
    assert records[0].portal_url.endswith("/123")

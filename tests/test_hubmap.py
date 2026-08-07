import httpx

from cellondesk.sources.hubmap import (
    HuBMAPClient,
    _extract_hits,
    resolve_dataset_type_filters,
    resolve_organ_filters,
)


def test_extracts_elasticsearch_hits():
    payload = {"hits": {"hits": [{"_source": {"uuid": "abc"}}]}}
    assert _extract_hits(payload) == [{"uuid": "abc"}]


def test_friendly_filter_aliases():
    assert resolve_organ_filters("kidney") == ("LK", "RK")
    assert resolve_organ_filters("left kidney") == ("LK",)
    assert resolve_organ_filters("UT") == ("UT",)
    assert "MERFISH" in resolve_dataset_type_filters("MERFISH")
    assert "RNAseq" in resolve_dataset_type_filters("scRNA-seq")


def test_search_normalizes_dataset():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/v3/param-search/datasets")
        assert request.url.params["dataset_type"] == "Visium (no probes)"
        assert request.url.params["origin_samples.organ"] == "LK"
        assert request.url.params["status"] == "Published"
        return httpx.Response(
            200,
            json=[
                {
                    "uuid": "123",
                    "hubmap_id": "HBM123",
                    "dataset_type": "Visium (no probes)",
                    "status": "Published",
                    "data_access_level": "protected",
                    "origin_samples": [{"organ": "LK"}],
                }
            ],
        )

    client = HuBMAPClient(transport=httpx.MockTransport(handler))
    records = client.search_datasets(dataset_type="Visium (no probes)", organ="LK")
    client.close()
    assert records[0].dataset_id == "123"
    assert records[0].organ == "LK"
    assert records[0].access_level == "protected"
    assert records[0].portal_url.endswith("/123")


def test_kidney_alias_searches_both_sides_and_deduplicates():
    def handler(request: httpx.Request) -> httpx.Response:
        organ = request.url.params["origin_samples.organ"]
        return httpx.Response(
            200,
            json=[
                {
                    "uuid": f"{organ}-1",
                    "dataset_type": "CODEX",
                    "status": "Published",
                    "origin_samples": [{"organ": organ}],
                }
            ],
        )

    client = HuBMAPClient(transport=httpx.MockTransport(handler))
    records = client.search_datasets(dataset_type="CODEX", organ="kidney")
    client.close()
    assert {record.organ for record in records} == {"LK", "RK"}


def test_search_follows_large_response_redirect():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "example-bucket.test":
            return httpx.Response(
                200,
                json=[
                    {
                        "uuid": "redirected",
                        "dataset_type": "CODEX",
                        "status": "Published",
                    }
                ],
            )
        return httpx.Response(
            303,
            headers={"location": "https://example-bucket.test/results.json"},
        )

    client = HuBMAPClient(transport=httpx.MockTransport(handler))
    records = client.search_datasets(dataset_type="CODEX")
    client.close()
    assert records[0].dataset_id == "redirected"

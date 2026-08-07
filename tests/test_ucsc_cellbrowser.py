import httpx

from cellondesk.sources.ucsc_cellbrowser import UCSCCellBrowserClient


def test_ucsc_search_expands_matching_collection():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/dataset.json":
            return httpx.Response(
                200,
                json={
                    "datasets": [
                        {
                            "name": "kidney-atlas",
                            "shortLabel": "Kidney atlas",
                            "body_parts": ["kidney"],
                            "organisms": ["Human (H. sapiens)"],
                            "assays": ["10x"],
                        }
                    ]
                },
            )
        if path == "/kidney-atlas/dataset.json":
            return httpx.Response(
                200,
                json={
                    "datasets": [
                        {
                            "name": "sample-a",
                            "shortLabel": "Kidney sample A",
                            "body_parts": ["kidney cortex"],
                            "organisms": ["Human (H. sapiens)"],
                            "assays": ["10x 3'"],
                        }
                    ]
                },
            )
        return httpx.Response(404)

    client = UCSCCellBrowserClient(transport=httpx.MockTransport(handler))
    records = client.search_datasets(organ="kidney", organism="Human")
    client.close()

    assert len(records) == 1
    assert records[0].dataset_id == "kidney-atlas/sample-a"
    assert records[0].access_level == "public"
    assert records[0].organ == "kidney cortex"
    assert "ds=kidney-atlas/sample-a" in records[0].portal_url


def test_ucsc_search_returns_no_unmatched_collection():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "datasets": [
                    {
                        "name": "brain-atlas",
                        "shortLabel": "Brain atlas",
                        "body_parts": ["brain"],
                    }
                ]
            },
        )

    client = UCSCCellBrowserClient(transport=httpx.MockTransport(handler))
    records = client.search_datasets(organ="kidney")
    client.close()
    assert records == []

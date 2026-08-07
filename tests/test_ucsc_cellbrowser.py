import httpx

from cellondesk.models import DatasetRecord
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
                            "hasFiles": ["exprMatrix.tsv.gz", "meta.tsv"],
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


def test_ucsc_resolves_verified_matrix_and_metadata_files():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD" and request.url.path.endswith("/exprMatrix.tsv.gz"):
            return httpx.Response(200, headers={"content-length": "4096"})
        if request.method == "HEAD" and request.url.path.endswith("/meta.tsv"):
            return httpx.Response(200, headers={"content-length": "1024"})
        return httpx.Response(404)

    client = UCSCCellBrowserClient(transport=httpx.MockTransport(handler))
    record = DatasetRecord(
        source="UCSC Cell Browser",
        dataset_id="kidney-atlas/sample-a",
        title="Kidney sample A",
        raw={"hasFiles": ["exprMatrix.tsv.gz", "meta.tsv"]},
    )
    assets = client.resolve_assets(record)
    client.close()

    assert [asset.name for asset in assets] == ["exprMatrix.tsv.gz", "meta.tsv"]
    assert assets[0].size_bytes == 4096
    assert assets[1].description == "Cell metadata"


def test_ucsc_prioritizes_expression_before_coordinates():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(200, headers={"content-length": "1024"})
        return httpx.Response(404)

    client = UCSCCellBrowserClient(transport=httpx.MockTransport(handler))
    record = DatasetRecord(
        source="UCSC Cell Browser",
        dataset_id="covid19-autoimmune-pbmc",
        title="COVID-19 Autoimmunity PBMCs",
        raw={
            "hasFiles": [
                "UMAP.coords.tsv.gz",
                "meta.tsv",
                "exprMatrix.tsv.gz",
            ]
        },
    )
    assets = client.resolve_assets(record)
    client.close()

    assert [asset.name for asset in assets[:3]] == [
        "exprMatrix.tsv.gz",
        "meta.tsv",
        "UMAP.coords.tsv.gz",
    ]


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

import httpx

from cellondesk.models import DatasetRecord
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
    assert "Slideseq" in resolve_dataset_type_filters("Slide-seq")
    assert "MALDI" in resolve_dataset_type_filters("MALDI IMS")


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


def test_lazy_organ_search_falls_back_to_narrow_assay_queries():
    def handler(request: httpx.Request) -> httpx.Response:
        assay = request.url.params.get("dataset_type")
        organ = request.url.params.get("origin_samples.organ")
        if assay is None:
            return httpx.Response(303)
        if assay == "RNAseq" and organ == "LK":
            return httpx.Response(
                200,
                json=[
                    {
                        "uuid": "rna-lk",
                        "hubmap_id": "HBM111.ABCD.222",
                        "dataset_type": "RNAseq",
                        "status": "Published",
                        "origin_samples": [{"organ": "LK"}],
                    }
                ],
            )
        return httpx.Response(404)

    client = HuBMAPClient(transport=httpx.MockTransport(handler))
    records = client.search_datasets(organ="kidney", limit=1)
    client.close()

    assert len(records) == 1
    assert records[0].dataset_id == "rna-lk"
    assert records[0].dataset_type == "RNAseq"
    assert records[0].organ == "LK"


def test_locationless_redirect_is_treated_as_empty_branch():
    client = HuBMAPClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(303))
    )
    records = client.search_datasets(dataset_type="CODEX")
    client.close()
    assert records == []


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


def test_resolve_assets_checks_record_and_descendant_products():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD" and request.url.path.endswith("/child/expr.h5ad"):
            return httpx.Response(200, headers={"content-length": "2048"})
        return httpx.Response(404)

    client = HuBMAPClient(transport=httpx.MockTransport(handler))
    record = DatasetRecord(
        source="HuBMAP",
        dataset_id="parent",
        title="Protected parent",
        access_level="protected",
        raw={"descendant_ids": ["child"]},
    )
    assets = client.resolve_assets(record)
    client.close()

    assert len(assets) == 1
    assert assets[0].dataset_id == "child"
    assert assets[0].name == "expr.h5ad"
    assert assets[0].size_bytes == 2048
    assert assets[0].is_h5ad is True


def test_resolve_assets_always_offers_official_clt_manifest_when_hubmap_id_exists():
    client = HuBMAPClient(transport=httpx.MockTransport(lambda _request: httpx.Response(404)))
    record = DatasetRecord(
        source="HuBMAP",
        dataset_id="0123456789abcdef0123456789abcdef",
        title="Visium dataset",
        dataset_type="Visium (no probes)",
        access_level="protected",
        raw={"hubmap_id": "HBM123.ABCD.456"},
    )
    assets = client.resolve_assets(record)
    client.close()

    assert len(assets) == 1
    manifest = assets[0]
    assert manifest.name == "HBM123.ABCD.456-clt-manifest.txt"
    assert manifest.format == "text/plain"
    assert manifest.is_h5ad is False
    assert "produce-clt-manifest=true" in manifest.download_url
    assert "hubmap_id=HBM123.ABCD.456" in manifest.download_url

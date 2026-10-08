import json
from dataclasses import asdict

import httpx
import pytest
from discovery_fixtures import CELLXGENE, CatalogFixture

from cellondesk.catalog_cache import CatalogCache, SearchBudget, SearchStats, SearchStopped
from cellondesk.discovery import DiscoveryService, SearchQuery, access_summary
from cellondesk.models import DatasetRecord
from cellondesk.sources.cellxgene_discover import DATASET_INDEX_URL, CellxGeneDiscoverClient
from cellondesk.sources.hubmap import (
    HuBMAPClient,
    resolve_dataset_type_filters,
    resolve_organ_filters,
)
from cellondesk.sources.ucsc_cellbrowser import UCSCCellBrowserClient


def test_ucsc_child_only_matches_and_cache_reuse(tmp_path):
    fixture = CatalogFixture()
    factory = fixture.factories(tmp_path)["ucsc"]
    with factory(SearchBudget()) as client:
        found = client.search_datasets(organ="kidney", organism="human", assay="RNAseq")
        assert [r.dataset_id for r in found] == ["unexpected-parent/nested/kidney-child"]
        record = found[0]
        assert record.reported_cell_count == 321
        assert record.organ == "kidney cortex"
        assert record.status is None  # publicly indexed does not establish publication
        assert record.asset_status == "advertised"
        assert record.provenance["lineage"] == ["unexpected-parent", "unexpected-parent/nested"]
        assert client.last_search.complete
    count = len(fixture.requests)
    with factory(SearchBudget()) as client:
        results = client.search_datasets(query="No child biology")
        assert results[0].organ is None
        assert results[0].reported_cell_count is None
        assert client.last_search.cache_hits == 4
    assert len(fixture.requests) == count


def test_hubmap_limit_does_not_skip_kidney_aliases_or_filter_late():
    fixture = CatalogFixture()
    with HuBMAPClient(transport=httpx.MockTransport(fixture.handler)) as client:
        results = client.search_datasets(organ="kidney", limit=2)
        assert [r.dataset_id for r in results] == ["LK-0", "RK-0"]
        assert client.last_search.matched == 6
        assert client.last_search.truncated
        assert client.last_search.complete
        assert all(r.reported_cell_count is None for r in results)
        assert results[0].donor_id == "HBM-DONOR"
        assert "not yet checked" in access_summary(results[0])
        assert results[0].acquisition_methods == ["HuBMAP CLT / Globus"]
        results = client.search_datasets(organ="kidney", query="RK-2", limit=1)
        assert results[0].dataset_id == "RK-2"
    assert {r.url.params["origin_samples.organ"] for r in fixture.requests} == {"LK", "RK"}


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Kidneys", ("LK", "RK")),
        ("Kidney (Left)", ("LK",)),
        ("rk", ("RK",)),
        ("lung", ("LL", "RL")),
        ("left lung", ("LL",)),
        ("liver", ("LV",)),
    ],
)
def test_hubmap_organ_aliases(name, expected):
    assert resolve_organ_filters(name) == expected
    assert "RNAseq" in resolve_dataset_type_filters("snRNA-seq")


def test_hubmap_broad_fallback_does_not_stop_at_first_assay():
    calls = []

    def handler(request):
        params = request.url.params
        calls.append(dict(params))
        if "dataset_type" not in params:
            return httpx.Response(303)
        assay = params["dataset_type"]
        return httpx.Response(200, json=[{"uuid": assay, "dataset_type": assay}])

    with HuBMAPClient(transport=httpx.MockTransport(handler)) as client:
        client.search_datasets(organ="kidney", limit=2)
        assert any(call.get("dataset_type") == "WGS" for call in calls)
        assert not client.last_search.complete
        assert client.last_search.matched > 2
        assert "not exhaustive" in " ".join(client.last_search.warnings)


def test_cellxgene_persistent_cache_ttl_refresh_and_no_stale_on_error(tmp_path):
    now = [1000.0]
    calls = []
    failing = [False]

    def handler(request):
        calls.append(request)
        if failing[0]:
            return httpx.Response(503)
        if request.headers.get("If-None-Match"):
            return httpx.Response(304)
        return httpx.Response(200, json=CELLXGENE, headers={"ETag": '"v1"'})

    cache = CatalogCache(tmp_path, ttl=60, clock=lambda: now[0])
    for query in ("kidney", "brain"):
        with CellxGeneDiscoverClient(transport=httpx.MockTransport(handler), cache=cache) as client:
            client.search_datasets(tissue=query)
    assert len(calls) == 1
    now[0] += 61
    with CellxGeneDiscoverClient(transport=httpx.MockTransport(handler), cache=cache) as client:
        result = client.search_datasets(tissue="kidney")
        assert client.last_search.revalidated == 1
        assert result[0].provenance["fetched_at"] == now[0]
        client.search_datasets(tissue="kidney", refresh=True)
        assert len(calls) == 3
        failing[0] = True
        with pytest.raises(httpx.HTTPStatusError):
            client.search_datasets(tissue="kidney", refresh=True)


def test_cache_recovers_corruption_and_enforces_response_bound(tmp_path, monkeypatch):
    cache = CatalogCache(tmp_path)
    path = cache._path(DATASET_INDEX_URL)
    path.write_text("invalid JSON")
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=CELLXGENE))
    ) as client:
        assert cache.get(client, DATASET_INDEX_URL, budget=SearchBudget(), stats=SearchStats())
        monkeypatch.setattr("cellondesk.catalog_cache.MAX_JSON_BYTES", 4)
        with pytest.raises(SearchStopped, match="safety limit"):
            cache.get(
                client, DATASET_INDEX_URL, budget=SearchBudget(), stats=SearchStats(), refresh=True
            )


def test_partial_source_failures_preserve_other_results_and_notices(tmp_path):
    fixture = CatalogFixture()
    factories = fixture.factories(tmp_path)
    factories["ucsc"] = lambda budget: UCSCCellBrowserClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(503)), budget=budget
    )
    updates = []
    results = DiscoveryService(factories=factories).search(
        SearchQuery(tissue="kidney", disease="normal"), on_source=updates.append
    )
    assert len(updates) == 3
    assert [len(result.records) for result in results] == [6, 1, 0]
    assert "503" in results[2].error
    assert not results[2].stats.complete
    assert results[0].notices[0].startswith("Disease")


def test_cold_warm_latency_cache_and_completeness_measurements(tmp_path):
    fixture = CatalogFixture()
    service = DiscoveryService(factories=fixture.factories(tmp_path / "cache"))
    cold = service.search(SearchQuery(tissue="kidney"))
    warm = service.search(SearchQuery(tissue="kidney"))
    expected = [
        {"LK-0", "LK-1", "LK-2", "RK-0", "RK-1", "RK-2"},
        {"cxg-kidney"},
        {"unexpected-parent/nested/kidney-child"},
    ]
    for results in (cold, warm):
        for outcome, identifiers in zip(results, expected):
            assert not outcome.error
            assert outcome.stats.complete
            assert {record.dataset_id for record in outcome.records} == identifiers
            assert outcome.elapsed_seconds >= 0
    assert sum(o.stats.requests for o in cold) == 7
    assert sum(o.stats.requests for o in warm) == 2  # HuBMAP is never catalog-cached
    assert sum(o.stats.cache_hits for o in warm) == 5
    artifact = {
        label: [
            {"source": o.source, "seconds": o.elapsed_seconds, **asdict(o.stats)} for o in results
        ]
        for label, results in (("cold", cold), ("warm", warm))
    }
    (tmp_path / "metrics.json").write_text(json.dumps(artifact, indent=2))


@pytest.mark.parametrize("bad_count", [None, -1, True, 2.5, "unknown"])
def test_missing_counts_not_fabricated(bad_count):
    payload = [{"dataset_id": "unknown", "title": "kidney", "cell_count": bad_count}]
    with CellxGeneDiscoverClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload))
    ) as client:
        record = client.search_datasets(query="kidney")[0]
    assert record.reported_cell_count is None
    assert record.dataset_type is None
    assert record.organism is None
    assert record.asset_status == "not_checked"
    assert DatasetRecord.model_validate(record.model_dump()) == record


def test_ucsc_limits_and_failed_branches_are_explicit(tmp_path):
    fixture = CatalogFixture()
    with UCSCCellBrowserClient(
        transport=httpx.MockTransport(fixture.handler), max_nodes=1
    ) as client:
        assert client.search_datasets(organ="kidney") == []
        assert not client.last_search.complete
        assert client.last_search.warnings


def test_cancelled_source_is_not_reported_as_complete(tmp_path):
    fixture = CatalogFixture()
    outcomes = DiscoveryService(factories=fixture.factories(tmp_path)).search(
        SearchQuery(tissue="kidney"), cancelled=lambda: True
    )
    assert all(outcome.error and not outcome.stats.complete for outcome in outcomes)
    assert fixture.requests == []


def test_source_deadline_is_not_a_complete_empty_result():
    budget = SearchBudget(seconds=-1)
    with HuBMAPClient(
        transport=httpx.MockTransport(lambda r: pytest.fail("network after deadline")),
        budget=budget,
    ) as client:
        assert client.search_datasets(organ="kidney") == []
        assert client.last_search.complete is False
        assert "time budget" in client.last_search.warnings[0]


def test_malformed_hubmap_payload_is_an_error():
    with HuBMAPClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"error": "oops"}))
    ) as client, pytest.raises(TypeError, match="unexpected"):
        client.search_datasets(organ="LK")


def test_duplicate_catalog_ids_and_missing_asset_urls_are_explicit():
    payload = [{"dataset_id": "one", "title": "Kidney", "assets": [{"format": "h5ad"}]}] * 2
    with CellxGeneDiscoverClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload))
    ) as client:
        records = client.search_datasets(query="kidney")
        assert len(records) == 1
        assert records[0].asset_status == "not_checked"
        assert not client.last_search.complete
        assert records[0].provenance["coverage"]["complete"] is False


def test_ucsc_catalog_cycles_terminate_with_an_integrity_warning():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"datasets": [{"name": "loop", "isCollection": True}]})

    with UCSCCellBrowserClient(transport=httpx.MockTransport(handler)) as client:
        assert client.search_datasets(organ="kidney") == []
        assert len(calls) == 2
        assert not client.last_search.complete
        assert "Cyclic" in client.last_search.warnings[0]


def test_cache_eviction_and_cached_byte_budget(tmp_path):
    cache = CatalogCache(tmp_path, max_disk_bytes=300)
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"label": "value"}))
    with httpx.Client(transport=transport) as client:
        for i in range(3):
            cache.get(
                client, f"https://example.org/{i}", budget=SearchBudget(), stats=SearchStats()
            )
        assert sum(path.stat().st_size for path in tmp_path.glob("*.json")) <= 300
        budget = SearchBudget()
        budget.metadata_bytes = 128 * 1024 * 1024
        with pytest.raises(SearchStopped, match="128 MiB"):
            cache.get(client, "https://example.org/2", budget=budget, stats=SearchStats())


def test_dataset_html_report_retains_discovery_scope_warning():
    from cellondesk.report import render_html_report

    record = DatasetRecord(
        source="HuBMAP",
        dataset_id="one",
        title="Kidney",
        provenance={"coverage": {"complete": False, "truncated": True}},
    )
    html = render_html_report([record])
    assert "Search coverage is partial" in html
    assert "distributions describe returned records only" in html

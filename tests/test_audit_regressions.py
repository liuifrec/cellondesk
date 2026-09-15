import h5py
import httpx
import numpy as np

from cellondesk.h5ad_compat import inspect_h5ad
from cellondesk.inspection import _read_categories, _summarize_column
from cellondesk.models import DatasetRecord
from cellondesk.sources.hubmap import HuBMAPClient, _candidate_dataset_ids
from cellondesk.sources.ucsc_cellbrowser import UCSCCellBrowserClient, _asset_url, _dataset_path


def test_valid_small_hubmap_result_does_not_fan_out_across_assays():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=[{"uuid": "one", "dataset_type": "RNAseq"}])

    with HuBMAPClient(transport=httpx.MockTransport(handler)) as client:
        records = client.search_datasets(organ="LK", limit=50)
    assert len(records) == 1
    assert len(calls) == 1


def test_hubmap_external_redirect_does_not_leak_bearer_token():
    def handler(request):
        if request.url.host == "search.api.hubmapconsortium.org":
            assert request.headers["Authorization"] == "Bearer example-token"
            return httpx.Response(303, headers={"location": "https://example.test/results.json"})
        assert "Authorization" not in request.headers
        return httpx.Response(200, json=[])

    with HuBMAPClient(token="example-token", transport=httpx.MockTransport(handler)) as client:
        assert client.search_datasets(dataset_type="CODEX") == []


def test_descendant_titles_and_statuses_are_not_ids():
    record = DatasetRecord(source="HuBMAP", dataset_id="parent", title="example", raw={
        "descendants": [{"uuid": "child", "title": "not an id", "status": "Published"}],
    })
    assert _candidate_dataset_ids(record) == ["parent", "child"]


def test_ucsc_full_child_path_is_not_prefixed_twice():
    assert _dataset_path("atlas", "atlas/t-cells") == "atlas/t-cells"
    assert _dataset_path("atlas", "t-cells") == "atlas/t-cells"
    assert _dataset_path("atlas", "atlas2/t-cells") == "atlas/atlas2/t-cells"


def test_ucsc_asset_url_forms_and_traversal():
    assert _asset_url("atlas/a", "matrix.tsv.gz") == "https://cells.ucsc.edu/atlas/a/matrix.tsv.gz"
    assert _asset_url("atlas/a", "/shared/meta.tsv") == "https://cells.ucsc.edu/shared/meta.tsv"
    assert _asset_url("atlas/a", "atlas/a/meta.tsv") == "https://cells.ucsc.edu/atlas/a/meta.tsv"
    assert _asset_url("atlas/a", "https://example.test/data.h5ad") == "https://example.test/data.h5ad"
    assert _asset_url("atlas/a", "../private.tsv") is None
    assert _asset_url("atlas/a", "%2e%2e/private.tsv") is None
    assert _asset_url("atlas/a", "file:///private.tsv") is None


def test_ucsc_hydrates_leaf_file_metadata():
    def handler(request):
        if request.method == "GET" and request.url.path == "/atlas/a/dataset.json":
            return httpx.Response(200, json={"matrixFile": "custom.tsv.gz"})
        if request.method == "HEAD" and request.url.path == "/atlas/a/custom.tsv.gz":
            return httpx.Response(200, headers={"content-length": "100"})
        return httpx.Response(404)

    record = DatasetRecord(source="UCSC Cell Browser", dataset_id="atlas/a", title="a")
    with UCSCCellBrowserClient(transport=httpx.MockTransport(handler)) as client:
        result = client.resolve_assets(record)
    assert [item.name for item in result] == ["custom.tsv.gz"]


def test_missing_numeric_values_are_not_counted_as_non_null(tmp_path):
    with h5py.File(tmp_path / "test.h5", "w") as f:
        node = f.create_dataset("score", data=[1., 1., np.nan, np.nan, np.inf])
        result = _summarize_column("score", node, max_values=10, max_top_values=10, np=np)
    assert result.non_null == 2
    assert result.unique == 1
    assert result.numeric.count == 2
    assert result.numeric.missing == 3


def test_numeric_category_labels_stay_categorical(tmp_path):
    with h5py.File(tmp_path / "test.h5", "w") as f:
        node = f.create_group("cluster")
        node.attrs["encoding-type"] = "categorical"
        node.create_dataset("codes", data=[0, 1, 0, -1])
        node.create_dataset("categories", data=[10, 20])
        result = _summarize_column("cluster", node, max_values=10, max_top_values=10, np=np)
    assert result.numeric is None
    assert result.unique == 2
    assert result.non_null == 3


def test_category_dictionary_is_sampled_not_loaded_in_full():
    class Categories:
        def __len__(self):
            return 10_000_000

        def __getitem__(self, indices):
            assert list(indices) == [2, 5]
            return np.asarray(["B", "T"])

    assert _read_categories(Categories(), np.asarray([5, -1, 2, 5]), np) == ["T", None, "B", "T"]


def test_velocity_vectors_are_not_position_embeddings(tmp_path):
    path = tmp_path / "example.h5ad"
    with h5py.File(path, "w") as f:
        f.create_dataset("X", data=np.zeros((3, 2)))
        obsm = f.create_group("obsm")
        obsm.create_dataset("X_umap", data=np.zeros((3, 2)))
        obsm.create_dataset("X_spatial", data=np.zeros((3, 2)))
        obsm.create_dataset("velocity_umap", data=np.zeros((3, 2)))
        obsm.create_dataset("bad_rows", data=np.zeros((2, 2)))
    result = inspect_h5ad(path)
    assert [item.key for item in result.embeddings] == ["X_umap", "X_spatial"]
    assert "velocity_umap" in result.obsm
    assert any("vector field" in warning for warning in result.warnings)
    assert any("row count" in warning for warning in result.warnings)

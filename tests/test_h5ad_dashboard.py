import hashlib
import json
import re
from collections import Counter

import h5py
import numpy as np
import pytest
from h5ad_fixtures import dashboard_fixture, strings

from cellondesk import H5ADInspection, inspect_h5ad
from cellondesk.h5ad_access import _field
from cellondesk.h5ad_report import render_h5ad_report, write_h5ad_report
from cellondesk.inspection import MatrixSummary
from cellondesk.inspection import inspect_h5ad as historical_inspect


def column(sample, name):
    return next(c for c in sample.columns if c.name == name)


def summary(result, name):
    return next(c for c in result.obs_columns if c.name == name)


@pytest.mark.parametrize("layout", ["modern", "legacy", "compound"])
@pytest.mark.parametrize("matrix", ["dense", "csr", "csc"])
def test_layouts_read_only_alignment_and_public_paths(tmp_path, layout, matrix):
    path = dashboard_fixture(tmp_path / "source.h5ad", layout=layout, matrix=matrix)
    original = hashlib.sha256(path.read_bytes()).hexdigest()
    original_stat = path.stat()
    result = inspect_h5ad(path, max_points=12, max_column_values=5)
    historical = historical_inspect(path, max_points=12, max_column_values=5)
    assert historical.obs_sample == result.obs_sample
    assert result.n_obs == 12 and result.n_vars == 3
    assert result.obs_sample.row_indices == [0, 2, 5, 8, 11]
    embedding = result.embeddings[0]
    assert embedding.row_indices == [0, 1, 2, 4, 5, 6, 7, 9, 10, 11]
    assert embedding.candidate_points == 12 and embedding.dropped_nonfinite == 2
    assert (
        len(embedding.sampled_points) == len(embedding.color_values) == len(embedding.row_indices)
    )
    lookup = dict(
        zip(
            result.embedding_metadata.row_indices,
            column(result.embedding_metadata, "cell_type").values,
        )
    )
    assert embedding.color_values == [
        str(lookup[r]) if lookup[r] is not None else "Missing" for r in embedding.row_indices
    ]
    assert result.provenance.source_stat_unchanged and result.provenance.read_only
    assert result.provenance.limits["max_column_values"] == 5
    assert result.provenance.dependencies["h5py"] == h5py.__version__
    assert any("not population totals" in warning for warning in result.warnings)
    assert any("non-finite coordinates" in warning for warning in result.warnings)
    write_h5ad_report(result, tmp_path / "report.html")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == original
    assert (path.stat().st_size, path.stat().st_mtime_ns) == (
        original_stat.st_size,
        original_stat.st_mtime_ns,
    )


def test_finite_histograms_missing_masks_and_real_missing_category(tmp_path):
    result = inspect_h5ad(dashboard_fixture(tmp_path / "data.h5ad"))
    score = summary(result, "score")
    finite = np.array([0, 10, 20, 40, 60, 70, 80, 90, 100, 110], dtype=float)
    assert score.sampled_values == score.total_values == 12
    assert score.numeric.count == score.non_null == 10
    assert score.numeric.missing == score.missing_values == 2
    assert score.numeric.mean == np.mean(finite)
    assert [score.numeric.p05, score.numeric.median, score.numeric.p95] == pytest.approx(
        np.quantile(finite, [0.05, 0.5, 0.95])
    )
    hist = score.numeric.histogram
    assert sum(hist.counts) == 10
    assert hist.edges[0] == 0 and hist.edges[-1] == 110
    assert hist.counts == np.histogram(finite, bins=hist.edges)[0].tolist()
    assert hist.last_bin_closed
    nullable = summary(result, "n_genes_by_counts")
    assert nullable.numeric.count == 9 and nullable.numeric.missing == 3
    assert column(result.obs_sample, "n_genes_by_counts").values[3] is None
    constant = summary(result, "constant").numeric.histogram
    assert constant.edges == [7.0, 7.0] and constant.counts == [12]
    assert summary(result, "all_missing").numeric.count == 0
    assert summary(result, "all_missing").numeric.histogram is None
    assert summary(result, "flag").numeric is None
    assert summary(result, "numeric_category").numeric is None
    counts = Counter(column(result.obs_sample, "cell_type").values)
    assert counts == {"T cell": 4, "B cell": 4, "Missing": 2, None: 2}
    missing_entries = [v for v in summary(result, "cell_type").top_values if v.value == "Missing"]
    assert {(v.is_missing, v.count) for v in missing_entries} == {(True, 2), (False, 2)}
    assert "pct_counts_mt" not in result.obs_column_names


def test_sampling_histograms_and_dropped_coordinates_have_independent_denominators(tmp_path):
    result = inspect_h5ad(
        dashboard_fixture(tmp_path / "data.h5ad"), max_points=4, max_column_values=6
    )
    assert result.obs_sample.row_indices == [0, 2, 4, 6, 8, 11]
    assert result.embedding_metadata.row_indices == [0, 3, 7, 11]
    assert result.embeddings[0].row_indices == [0, 7, 11]
    score = summary(result, "score")
    assert score.sampled and score.sampled_values == 6 and score.total_values == 12
    assert sum(score.numeric.histogram.counts) == 6
    assert column(result.obs_sample, "score").values == [0, 20, 40, 60, 80, 110]


@pytest.mark.parametrize("matrix", ["csr", "csc"])
def test_sparse_statistics_are_stored_entries_not_whole_matrix(tmp_path, matrix):
    result = inspect_h5ad(dashboard_fixture(tmp_path / "data.h5ad", matrix=matrix))
    assert result.matrix.nnz == 12
    assert result.matrix.density == 1 / 3
    assert result.matrix.sample_nonzero == 9
    assert result.matrix.sample_mean == 1.5  # excludes implicit zeros; whole matrix mean is 0.5
    assert "excludes implicit zeros" in result.matrix.sample_scope
    assert not any("Sparse X" in warning for warning in result.warnings)


def test_malformed_fields_and_shapes_are_visible_without_stopping_valid_data(tmp_path):
    path = dashboard_fixture(tmp_path / "bad.h5ad", matrix="csr")
    with h5py.File(path, "a") as f:
        f["obs/cell_type/codes"][1] = 99
        del f["obs/n_genes_by_counts/mask"]
        f["obs/n_genes_by_counts"].create_dataset("mask", data=[False])
        del f["obs/score"]
        f["obs"].create_dataset("score", data=[2.0, 4.0])
        f["obsm"].create_dataset("bad_rows", data=np.zeros((2, 2)))
        f["obsm"].create_dataset("velocity_umap", data=np.zeros((12, 2)))
        f["X/indptr"][-1] = 90
        f["X"].attrs["shape"] = [13, 3]
    result = inspect_h5ad(path)
    names = [c.name for c in result.obs_sample.columns]
    assert not {"cell_type", "score", "n_genes_by_counts"} & set(names)
    assert "total_counts" in names
    warnings = " ".join(result.warnings)
    for expected in [
        "category dictionary",
        "mask shape",
        "row count",
        "vector field",
        "indptr endpoints",
        "X shape",
    ]:
        assert expected in warnings


def test_column_limit_retains_annotation_and_warns(tmp_path):
    result = inspect_h5ad(
        dashboard_fixture(tmp_path / "data.h5ad"), max_obs_columns=1, annotation="sample_id"
    )
    assert [c.name for c in result.obs_columns] == ["cell_type", "sample_id"]
    assert [c.name for c in result.obs_sample.columns] == ["cell_type", "sample_id"]
    assert any("2 of 10 obs columns" in w for w in result.warnings)


@pytest.mark.parametrize(
    "limit", ["max_points", "max_column_values", "max_obs_columns", "max_var_columns"]
)
@pytest.mark.parametrize("value", [-1, True, 2.5])
def test_invalid_limits_rejected(tmp_path, limit, value):
    path = dashboard_fixture(tmp_path / "data.h5ad")
    with pytest.raises(ValueError, match=f"{limit} must be a .* integer"):
        inspect_h5ad(path, **{limit: value})


def test_empty_dataset_and_absent_metadata_do_not_invent_qc(tmp_path):
    path = dashboard_fixture(tmp_path / "empty.h5ad", rows=0)
    result = inspect_h5ad(path)
    assert result.n_obs == 0
    assert result.obs_sample.row_indices == []
    assert all(not c.values for c in result.obs_sample.columns)
    assert result.embeddings[0].dropped_nonfinite == 0
    assert "No QC metrics are computed from X" in render_h5ad_report(result)
    path = tmp_path / "missing.h5ad"
    with h5py.File(path, "w") as f:
        f.create_dataset("X", shape=(7, 3), dtype="f4")
    result = inspect_h5ad(path)
    assert result.n_obs == 7 and not result.obs_columns
    assert any("obs is absent" in w for w in result.warnings)


def test_compound_field_selection_is_lazy_and_reads_only_requested_rows():
    class View:
        def __getitem__(self, selection):
            assert list(selection) == [2, 7, 999_999]
            return np.array([b"a", b"b", b"c"])

    class Table:
        dtype = np.dtype([("_index", "S20"), ("cell_type", "S10")])
        shape = (1_000_000,)

        def __getitem__(self, key):
            raise AssertionError("Must not materialize a whole compound column")

        def fields(self, name):
            assert name == "cell_type"
            return View()

    node = _field(Table(), "cell_type")
    assert node.shape == (1_000_000,)
    assert node[np.array([2, 7, 999_999])].tolist() == [b"a", b"b", b"c"]


def test_large_logical_h5ad_reads_are_bounded(tmp_path, monkeypatch):
    path = tmp_path / "large.h5ad"
    with h5py.File(path, "w") as f:
        f.create_dataset("X", shape=(1_000_000, 30_000), dtype="f4", chunks=(64, 64))
        obs = f.create_group("obs")
        obs.create_dataset("_index", shape=(1_000_000,), dtype="i8", chunks=True)
        obs.create_dataset("score", shape=(1_000_000,), dtype="f8", chunks=True)
        obs.create_dataset("cell_type", shape=(1_000_000,), dtype="S8", chunks=True)
        var = f.create_group("var")
        var.create_dataset("_index", shape=(30_000,), dtype="i8", chunks=True)
        f.create_group("obsm").create_dataset(
            "X_umap", shape=(1_000_000, 2), dtype="f4", chunks=True
        )
    original = h5py.Dataset.__getitem__
    reads = []

    def bounded_read(node, selection, *args, **kwargs):
        result = original(node, selection, *args, **kwargs)
        size = np.size(result)
        assert size <= 128 * 128, (node.name, selection, size)
        reads.append((node.name, size))
        return result

    monkeypatch.setattr(h5py.Dataset, "__getitem__", bounded_read)
    result = inspect_h5ad(path, max_points=7, max_column_values=11)
    assert result.n_obs == 1_000_000
    assert len(result.obs_sample.row_indices) == 11
    assert len(result.embeddings[0].sampled_points) == 7
    assert ("/X", 16_384) in reads
    assert path.stat().st_size < 100_000


def test_safe_serialization_old_models_and_source_overwrite_guard(tmp_path):
    path = dashboard_fixture(tmp_path / "source.h5ad")
    dangerous = "</script><script>window.injected=true</script><!--&\u2028"
    with h5py.File(path, "a") as f:
        strings(f["obs"], dangerous, [dangerous] * 12)
        f["obs"].attrs["column-order"] = [*f["obs"].attrs["column-order"], dangerous]
    result = inspect_h5ad(path)
    text = render_h5ad_report(result, title=dangerous)
    payload = json.loads(re.search(r'id="inspection-data">(.*?)</script>', text, re.DOTALL)[1])
    assert dangerous in payload["obs_column_names"]
    assert "</script><script>window.injected" not in text
    assert "<script src=" not in text and "<link " not in text
    with pytest.raises(ValueError, match="overwrite"):
        write_h5ad_report(result, path)
    alias = tmp_path / "alias.html"
    alias.hardlink_to(path)
    with pytest.raises(ValueError, match="overwrite"):
        write_h5ad_report(result, alias)
    old = H5ADInspection(
        source_path="old.h5ad",
        file_name="old.h5ad",
        file_size_bytes=0,
        n_obs=0,
        n_vars=0,
        matrix=MatrixSummary(shape=(0, 0), encoding="missing"),
    )
    assert old.obs_sample is None
    assert "Not recorded by this older inspection" in render_h5ad_report(old)


def test_zero_column_limits_remain_compatible(tmp_path):
    result = inspect_h5ad(
        dashboard_fixture(tmp_path / "limits.h5ad"), max_obs_columns=0, max_var_columns=0
    )
    # The historical reader retained a detected annotation even beyond the column cap.
    assert [c.name for c in result.obs_columns] == ["cell_type"]
    assert result.var_columns == []
    for limit in ["max_column_values", "max_points"]:
        with pytest.raises(ValueError, match="positive integer"):
            inspect_h5ad(tmp_path / "limits.h5ad", **{limit: 0})


def test_extreme_finite_numeric_values_remain_finite_in_json(tmp_path):
    path = dashboard_fixture(tmp_path / "extreme.h5ad")
    with h5py.File(path, "a") as f:
        f["obs/score"][:] = [-1e308, 1e308] * 6
        f["X"][:] = 1e308
    result = inspect_h5ad(path)
    numeric = summary(result, "score").numeric
    assert numeric.mean == 0
    assert numeric.median == 0
    assert sum(numeric.histogram.counts) == 12
    assert np.isfinite(numeric.histogram.edges).all()
    assert result.matrix.sample_mean == 1e308
    render_h5ad_report(result)  # strict JSON serialization rejects non-finite numbers


def test_legacy_sparse_shape_and_encoding_attributes(tmp_path):
    path = dashboard_fixture(tmp_path / "old-sparse.h5ad", matrix="csr", layout="legacy")
    with h5py.File(path, "a") as f:
        f["X"].attrs["h5sparse_shape"] = f["X"].attrs["shape"]
        f["X"].attrs["h5sparse_format"] = "csr"
        del f["X"].attrs["shape"]
        del f["X"].attrs["encoding-type"]
    result = inspect_h5ad(path)
    assert result.matrix.encoding == "csr_matrix"
    assert result.matrix.shape == (12, 3)
    assert not any("Sparse X" in w or "X shape" in w for w in result.warnings)


def test_unsafe_integers_and_malformed_nullable_values_are_not_silently_changed(tmp_path):
    path = dashboard_fixture(tmp_path / "unsafe.h5ad")
    with h5py.File(path, "a") as f:
        f["obs/total_counts"][0] = 2**53 + 1
        del f["obs/n_genes_by_counts/mask"]
    result = inspect_h5ad(path)
    assert "total_counts" not in [c.name for c in result.obs_sample.columns]
    assert any("browser numeric precision" in w for w in result.warnings)
    assert any("missing its mask" in w for w in result.warnings)


def test_wide_legacy_embedding_fields_use_bounded_blocks():
    class View:
        def __getitem__(self, selection):
            assert len(selection) <= 1  # one row already has 20,000 coordinates
            return np.tile(np.arange(20_000), (len(selection), 1))

    class Table:
        dtype = np.dtype([("X_pca", "f8", (20_000,))])
        shape = (1_000_000,)

        def __getitem__(self, key):
            raise AssertionError("Do not materialize entire compound fields")

        def fields(self, name):
            assert name == "X_pca"
            return View()

    values = _field(Table(), "X_pca")[np.array([0, 10, 99_999]), :2]
    assert values.tolist() == [[0, 1], [0, 1], [0, 1]]


@pytest.mark.parametrize("output", ["--html", "--json"])
def test_cli_export_cannot_overwrite_source(tmp_path, output):
    from typer.testing import CliRunner

    from cellondesk.cli import app

    path = dashboard_fixture(tmp_path / "source.h5ad")
    before = path.read_bytes()
    result = CliRunner().invoke(app, ["inspect-h5ad", str(path), output, str(path)])
    assert result.exit_code != 0
    assert path.read_bytes() == before


def test_cli_html_and_json_export_share_the_inspection(tmp_path):
    from typer.testing import CliRunner

    from cellondesk.cli import app

    source = dashboard_fixture(tmp_path / "source.h5ad")
    html_path, json_path = tmp_path / "report.html", tmp_path / "report.json"
    result = CliRunner().invoke(
        app,
        [
            "inspect-h5ad",
            str(source),
            "--html",
            str(html_path),
            "--json",
            str(json_path),
            "--max-points",
            "4",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = H5ADInspection.model_validate_json(json_path.read_text(encoding="utf-8"))
    assert payload.provenance.generator_version == "0.12.0"
    assert payload.embeddings[0].candidate_points == 4
    assert "Sample × annotation" in html_path.read_text(encoding="utf-8")


def test_nullable_strings_and_booleans_use_masks_not_literal_na(tmp_path):
    path = dashboard_fixture(tmp_path / "nullable.h5ad")
    with h5py.File(path, "a") as f:
        obs = f["obs"]
        for name, values, encoding in [
            ("nullable_text", ["NA", "value"] * 6, "nullable-string-array"),
            ("nullable_bool", [True, False] * 6, "nullable-boolean"),
        ]:
            node = obs.create_group(name)
            node.attrs["encoding-type"] = encoding
            if name == "nullable_text":
                strings(node, "values", values)
            else:
                node.create_dataset("values", data=values)
            node.create_dataset("mask", data=np.arange(12) % 3 == 1)
            obs.attrs["column-order"] = [*obs.attrs["column-order"], name]
    result = inspect_h5ad(path)
    for name in ["nullable_text", "nullable_bool"]:
        c = column(result.obs_sample, name)
        assert c.kind == "categorical"
        assert c.values.count(None) == 4
        assert summary(result, name).numeric is None
    assert column(result.obs_sample, "nullable_text").values[0] == "NA"


def test_embedding_limits_and_nonreal_values_are_explicit(tmp_path):
    path = dashboard_fixture(tmp_path / "coordinates.h5ad")
    with h5py.File(path, "a") as f:
        f["obsm/X_umap"][:] = np.nan
        f["obsm"].create_dataset("X_pca", shape=(12, 2), dtype="c16")
        for index in range(4):
            f["obsm"].create_dataset(f"extra_{index}", data=np.zeros((12, 2)))
    result = inspect_h5ad(path)
    assert result.embeddings[0].sampled_points == []
    assert result.embeddings[0].dropped_nonfinite == 12
    assert len(result.obs_sample.row_indices) == 12
    assert len(result.embeddings) == 4
    assert any("real numeric dtype" in w for w in result.warnings)
    assert any("four-preview limit" in w for w in result.warnings)


def test_plain_array_axis_is_not_iterated_as_a_metadata_group(tmp_path, monkeypatch):
    path = tmp_path / "unsupported-axis.h5ad"
    with h5py.File(path, "w") as f:
        f.create_dataset("obs", shape=(1_000_000,), dtype="i8", chunks=True)
        f.create_dataset("X", shape=(1_000_000, 2), dtype="f4", chunks=True)
    original = h5py.Dataset.__getitem__

    def read(node, selection, *args, **kwargs):
        assert node.name != "/obs", "Unsupported obs must never be iterated for membership"
        return original(node, selection, *args, **kwargs)

    monkeypatch.setattr(h5py.Dataset, "__getitem__", read)
    result = inspect_h5ad(path)
    assert result.n_obs == 1_000_000
    assert result.obs_sample.columns == []
    assert any("Unsupported obs table" in w for w in result.warnings)


def test_stat_change_is_recorded_as_warning_not_integrity_success(tmp_path, monkeypatch):
    import os

    from cellondesk import h5ad_compat

    path = dashboard_fixture(tmp_path / "changed.h5ad")
    actual_stat = path.stat()
    original = h5ad_compat.observation_sample

    def sample(*args, **kwargs):
        # Simulate a concurrent writer changing stat data during the read.
        result = original(*args, **kwargs)
        os.utime(path, ns=(actual_stat.st_atime_ns, actual_stat.st_mtime_ns + 1000))
        return result

    monkeypatch.setattr(h5ad_compat, "observation_sample", sample)
    result = inspect_h5ad(path)
    assert not result.provenance.source_stat_unchanged
    assert any("changed during inspection" in w for w in result.warnings)


def test_legacy_feature_lookup_still_finds_nonstandard_symbol_columns(tmp_path):
    from cellondesk import inspect_gene_expression

    path = dashboard_fixture(tmp_path / "symbols.h5ad", layout="legacy")
    with h5py.File(path, "a") as f:
        strings(f["var"], "custom_symbols", ["CD3D", "MS4A1", "LYZ"])
        f["var"].attrs["column-order"] = ["custom_symbols"]
    result = inspect_gene_expression(path, "CD3D", max_points=4)
    assert result.matched_field == "custom_symbols"
    assert result.values == [0, 9, 21, 33]

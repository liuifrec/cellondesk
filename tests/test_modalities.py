import hashlib
import json

import h5py
import numpy as np
import pytest
from modality_fixtures import PUBLIC, multiome_fixture, public_fixture, scientific_fixture
from typer.testing import CliRunner

from cellondesk import H5ADInspection, inspect_h5ad
from cellondesk.cli import app
from cellondesk.h5ad_report import write_h5ad_report
from cellondesk.modality_h5ad import LIMITS
from cellondesk.scientific_formats import inspect_scientific


def states(report):
    return {profile.profile: profile.state for profile in report.profiles}


def caps(report):
    return {cap.key: cap.state for cap in report.capabilities}


@pytest.mark.parametrize("layout", ["dense", "csr", "csc"])
@pytest.mark.parametrize("legacy", [False, True])
def test_shared_axis_multiome_has_exact_typed_values_and_no_inferred_relationships(
    tmp_path, layout, legacy
):
    path = scientific_fixture(
        tmp_path / "mixed.h5ad",
        ("Gene Expression", "Peaks", "Antibody Capture"),
        layout=layout,
        legacy=legacy,
    )
    before = hashlib.sha256(path.read_bytes()).digest()
    result = inspect_h5ad(path)
    scientific = result.scientific
    assert states(scientific) == {
        "rna": "supported",
        "atac": "supported",
        "multiomics": "supported",
    }
    expected = np.arange(36).reshape(12, 3) % 11
    for preview in scientific.feature_previews:
        assert preview.values == expected[:, preview.feature_index].tolist()
        assert preview.row_indices == list(range(12))
        assert preview.units is None
    assert {p.family for p in scientific.feature_previews} == {"rna", "atac", "protein"}
    assert caps(scientific)["joint_views"] == "unsupported"
    assert caps(scientific)["gene_activity"] == "unsupported"
    assert not scientific.correspondence
    assert any("Storage correspondence only" in e.scope for e in scientific.evidence)
    assert hashlib.sha256(path.read_bytes()).digest() == before
    assert H5ADInspection.model_validate_json(result.model_dump_json()).scientific == scientific


@pytest.mark.parametrize(
    "family,profile",
    [
        ("Gene Expression", "spatial_transcriptomics"),
        ("Antibody Capture", "spatial_proteomics"),
        ("Molecular ions", "spatial_metabolomics"),
    ],
)
def test_spatial_profiles_require_typed_features_and_aligned_coordinates(tmp_path, family, profile):
    path = scientific_fixture(tmp_path / "spatial.h5ad", (family, family), spatial=True)
    result = inspect_h5ad(path).scientific
    assert states(result)[profile] == "supported"
    assert result.spatial_previews[0].units is None
    assert result.spatial_previews[0].frame is None
    assert caps(result)["tissue_image"] == "missing"
    assert caps(result)["image_overlay"] == "unsupported"
    assert caps(result)["segmentation"] == caps(result)["mass_spectra"] == "unsupported"
    with h5py.File(path, "a") as f:
        del f["obsm/spatial"]
        f["obsm"].create_dataset("spatial", data=np.zeros((3, 2)))
    invalid = inspect_h5ad(path).scientific
    assert profile not in states(invalid)
    assert caps(invalid)["spatial_coordinates"] == "missing"
    assert any("axes do not match" in warning for warning in invalid.warnings)


def test_image_preview_is_separate_from_unvalidated_or_incompatible_transform(tmp_path):
    path = scientific_fixture(tmp_path / "visium.h5ad", spatial=True, image=True)
    report = inspect_h5ad(path).scientific
    image = report.images[0]
    assert image.data_url.startswith("data:image/png;base64,iVBOR")
    assert image.original_shape == image.preview_shape == [20, 30, 3]
    assert caps(report)["image_overlay"] == "unsupported"
    with h5py.File(path, "a") as f:
        f.require_group("uns/spatial/library/scalefactors").create_dataset(
            "tissue_lowres_scalef", data=0.1
        )
        g = f.require_group("uns/cellondesk_spatial")
        g.create_dataset("coordinate_frame", data="stage")
        g.create_dataset("image_frame", data="camera")
    report = inspect_h5ad(path).scientific
    assert caps(report)["image_overlay"] == "invalid"
    assert "stage vs camera" in next(
        c.reason for c in report.capabilities if c.key == "image_overlay"
    )


def test_manual_and_declared_profiles_do_not_create_values_or_qc(tmp_path):
    path = scientific_fixture(tmp_path / "unknown.h5ad", ("", ""), spatial=True, qc=False)
    result = inspect_h5ad(path).scientific
    assert not result.profiles
    assert {p.family for p in result.feature_previews} == {"unclassified"}
    with h5py.File(path, "a") as f:
        f.require_group("uns").create_dataset("assay", data="Visium")
    result = inspect_h5ad(path, modality_override=["spatial_proteomics"]).scientific
    assert states(result)["spatial_transcriptomics"] == "suggested"
    assert states(result)["spatial_proteomics"] == "manual"
    assert result.manual_overrides == ["spatial_proteomics"]
    assert caps(result)["rna_values"] == caps(result)["protein_values"] == "missing"
    assert caps(result)["rna_qc"] == caps(result)["atac_qc"] == "missing"
    assert not result.recorded_metrics
    assert any(e.origin == "manual" for e in result.evidence)
    with pytest.raises(ValueError, match="Unknown scientific profiles"):
        inspect_h5ad(path, modality_override=["unsupported_magic"])


def test_qc_preserves_actual_stored_scale_and_nonfinite_exclusions(tmp_path):
    path = scientific_fixture(tmp_path / "atac.h5ad", ("Peaks", "Peaks"))
    with h5py.File(path, "a") as f:
        f["obs/FRiP"][2] = np.nan
        f["obs/FRiP"][3] = np.inf
    report = inspect_h5ad(path).scientific
    metrics = {m.name: m for m in report.recorded_metrics}
    assert metrics["FRiP"].values[:4] == [0.1, pytest.approx(0.1 + 0.8 / 11), None, None]
    assert metrics["TSS_enrichment"].values == (np.arange(12) / 2).tolist()
    assert set(metrics) == {"FRiP", "TSS_enrichment", "n_fragments"}
    assert caps(report)["rna_qc"] == "missing"


def test_bounded_reads_and_abort_instead_of_inventing_sparse_zeros(tmp_path, monkeypatch):
    path = scientific_fixture(
        tmp_path / "bounded.h5ad", ("Gene Expression",) * 12, rows=500, layout="csr"
    )
    monkeypatch.setitem(LIMITS, "preview_rows", 4)
    monkeypatch.setitem(LIMITS, "feature_annotations", 4)
    report = inspect_h5ad(path).scientific
    assert all(len(p.values) == 4 and p.total_rows == 500 for p in report.feature_previews)
    assert any("4 / 12" in warning for warning in report.warnings)
    assert report.feature_previews[0].row_indices == [0, 166, 332, 499]
    monkeypatch.setitem(LIMITS, "matrix_entries", 1)
    report = inspect_h5ad(path).scientific
    assert not report.feature_previews
    assert caps(report)["rna_values"] == "missing"
    assert any("no partial feature values" in warning for warning in report.warnings)


@pytest.mark.parametrize(
    "fault", ["duplicate", "out_of_range", "mismatched_barcode", "missing", "sampled"]
)
def test_native_h5mu_explicit_correspondence_failures_and_scope(tmp_path, monkeypatch, fault):
    path = multiome_fixture(tmp_path / "multiome.h5mu")
    with h5py.File(path, "a") as f:
        if fault == "duplicate":
            f["obsmap/atac"][1] = 1
        elif fault == "out_of_range":
            f["obsmap/atac"][0] = 100
        elif fault == "mismatched_barcode":
            f["mod/atac/obs/_index"][0] = "different-biological-unit"
        elif fault == "missing":
            del f["obsmap/atac"]
        else:
            monkeypatch.setitem(LIMITS, "correspondence_rows", 4)
    before = hashlib.sha256(path.read_bytes()).digest()
    report = inspect_scientific(path)
    assert report.storage_format == "H5MU"
    assert report.matrix.encoding == "container; no joint X"
    check = next(
        c for c in report.scientific.correspondence if c.module == "atac" and c.axis == "obs"
    )
    assert check.state == {"missing": "unverified", "sampled": "sample_consistent"}.get(
        fault, "invalid"
    )
    if fault == "sampled":
        assert check.checked == 4 and check.total == 12
    assert {p.matrix_path for p in report.scientific.feature_previews} == {
        "/mod/rna/X",
        "/mod/atac/X",
    }
    assert caps(report.scientific)["joint_views"] != "available"
    assert hashlib.sha256(path.read_bytes()).digest() == before


def test_native_h5mu_absent_maps_are_not_zero_measurements(tmp_path):
    path = multiome_fixture(tmp_path / "partial.h5mu")
    with h5py.File(path, "a") as f:
        f["obsmap/atac"][2] = 0
    result = inspect_scientific(path).scientific
    check = next(c for c in result.correspondence if c.module == "atac" and c.axis == "obs")
    assert check.state == "verified" and check.absent == 1 and check.present == 11
    # Native ATAC values retain their actual rows; absent global mapping never injects zeros.
    preview = next(p for p in result.feature_previews if p.matrix_path == "/mod/atac/X")
    assert preview.values[2] == 4


@pytest.mark.parametrize(
    "name,expected",
    [
        ("rna", {"rna"}),
        ("atac", {"atac"}),
        ("multiome", {"rna", "atac", "multiomics"}),
        ("visium", {"rna", "spatial_transcriptomics"}),
        ("imaging", set()),
    ],
)
def test_public_measurements_preserve_types_values_and_provenance(tmp_path, name, expected):
    excerpt = json.loads((PUBLIC / f"{name}.json").read_text())
    path = public_fixture(tmp_path / f"{name}.h5ad", name)
    result = inspect_h5ad(path).scientific
    assert set(states(result)) == expected
    assert len(excerpt["provenance"]["source_sha256"]) == 64
    assert excerpt["provenance"]["original_observations"] > 32
    for preview in result.feature_previews:
        assert preview.name == excerpt["feature_ids"][preview.feature_index]
        assert preview.values == [row[preview.feature_index] for row in excerpt["values"]]
    if name == "imaging":
        assert result.spatial_previews and not result.images
        assert not result.recorded_metrics
        overridden = inspect_h5ad(path, modality_override=["spatial_proteomics"]).scientific
        assert states(overridden)["spatial_proteomics"] == "manual"
        assert caps(overridden)["protein_values"] == "missing"
    if name == "visium":
        assert result.images
        assert result.spatial_previews[0].points == excerpt["spatial"]
        assert caps(result)["image_overlay"] == "unsupported"


def test_format_dispatch_cli_and_source_export_protection(tmp_path):
    path = multiome_fixture(tmp_path / "native.h5mu")
    target = tmp_path / "native.html"
    result = CliRunner().invoke(
        app, ["inspect-scientific", str(path), "--html", str(target), "--modality", "multiomics"]
    )
    assert result.exit_code == 0, result.output
    assert "H5MU" in target.read_text()
    report = inspect_scientific(path)
    with pytest.raises(ValueError, match="source|H5AD|h5ad"):
        write_h5ad_report(report, path)
    with pytest.raises(ValueError, match="No AnnData conversion"):
        inspect_scientific(tmp_path / "imaging.zarr")


def test_dense_preview_read_budget_and_image_dimensions(tmp_path, monkeypatch):
    path = scientific_fixture(tmp_path / "bounded-dense.h5ad", rows=500, image=True)
    monkeypatch.setitem(LIMITS, "image_side", 8)
    original = h5py.Dataset.__getitem__
    shapes = []

    def tracked(node, selection):
        result = original(node, selection)
        if node.name == "/X":
            shapes.append(np.asarray(result).shape)
            assert np.asarray(result).size <= 256 * 2
        return result

    monkeypatch.setattr(h5py.Dataset, "__getitem__", tracked)
    report = inspect_h5ad(path).scientific
    assert shapes and all(len(p.values) == 256 for p in report.feature_previews)
    assert report.images[0].preview_shape == [5, 8, 3]
    assert report.images[0].original_shape == [20, 30, 3]
    assert "Every 4th pixel" in report.images[0].note


@pytest.mark.parametrize("fault", ["duplicate_entries", "invalid_index", "nonmonotonic_pointer"])
def test_sparse_preview_duplicate_sums_and_invalid_storage(tmp_path, fault):
    path = scientific_fixture(tmp_path / "sparse.h5ad", ("Peaks",), rows=1)
    with h5py.File(path, "a") as f:
        del f["X"]
        x = f.create_group("X")
        x.attrs.update({"encoding-type": "csr_matrix", "shape": [1, 1]})
        x.create_dataset("data", data=[2.0, 3.0])
        x.create_dataset("indices", data=[0, 5 if fault == "invalid_index" else 0])
        x.create_dataset("indptr", data=[2, 1] if fault == "nonmonotonic_pointer" else [0, 2])
    report = inspect_h5ad(path).scientific
    if fault == "duplicate_entries":
        assert report.feature_previews[0].values == [5.0]
    else:
        assert not report.feature_previews
        assert any("Invalid" in warning for warning in report.warnings)


def test_invalid_feature_annotations_preserve_general_dashboard(tmp_path):
    path = scientific_fixture(tmp_path / "incomplete.h5ad")
    with h5py.File(path, "a") as f:
        del f["var/feature_types"]
        f["var"].create_dataset("feature_types", data=[1, 2, 3, 4])
    result = inspect_h5ad(path)
    assert result.n_obs == 12 and result.obs_sample
    assert not result.scientific.profiles
    assert any(
        "Feature annotation evidence unavailable" in note for note in result.scientific.warnings
    )


def test_native_module_limits_and_unknown_annotations(tmp_path, monkeypatch):
    path = multiome_fixture(tmp_path / "bounded.h5mu")
    monkeypatch.setitem(LIMITS, "modules", 1)
    result = inspect_scientific(path, max_points=3, annotation="unavailable")
    assert len(result.scientific.modules) == 1
    assert len(result.obs_sample.row_indices) == 3
    assert any("Only 1 / 2" in note for note in result.scientific.warnings)
    assert any("Requested global annotation" in note for note in result.warnings)
    assert any("3 / 12" in note for note in result.warnings)
    with pytest.raises(ValueError, match="positive integer"):
        inspect_scientific(path, max_points=0)


@pytest.mark.parametrize("fault", ["all_absent", "missing_identifier", "reordered"])
def test_maps_require_observed_identifiers_and_use_explicit_order(tmp_path, fault):
    path = multiome_fixture(tmp_path / "maps.h5mu")
    with h5py.File(path, "a") as f:
        if fault == "all_absent":
            f["obsmap/atac"][:] = 0
        elif fault == "missing_identifier":
            f["obs/_index"][0] = f["mod/atac/obs/_index"][0] = ""
        else:
            f["mod/atac/obs/_index"][:] = f["mod/atac/obs/_index"][:][::-1]
            f["obsmap/atac"][:] = np.arange(12, 0, -1)
    result = inspect_scientific(path).scientific
    check = next(c for c in result.correspondence if c.module == "atac" and c.axis == "obs")
    assert check.state == ("verified" if fault == "reordered" else "unverified")
    assert caps(result)["joint_views"] != "available"

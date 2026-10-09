"""Offline scientific modules: controls, frame guards, provenance and screenshots."""

import os

import h5py
import numpy as np
import pytest
from modality_fixtures import multiome_fixture, public_fixture, scientific_fixture
from test_h5ad_browser import artifact_dir, screenshot
from test_h5ad_browser import browser_page as _browser_page

from cellondesk import inspect_h5ad
from cellondesk.h5ad_report import write_h5ad_report
from cellondesk.scientific_formats import inspect_scientific

pytestmark = pytest.mark.skipif(
    os.environ.get("CELLONDESK_BROWSER_TESTS") != "1",
    reason="Set CELLONDESK_BROWSER_TESTS=1 to run offline Chromium tests",
)

# Re-export the shared pytest fixture without shadowing an unused import.
browser_page = _browser_page


def open_scientific(page, result, tmp_path, name):
    path = write_h5ad_report(result, artifact_dir(tmp_path) / f"{name}.html")
    page.goto(path.as_uri())
    page.get_by_role("tab", name="Scientific modules", exact=True).click()


def test_hybrid_features_qc_and_profile_evidence(browser_page, tmp_path):
    path = scientific_fixture(
        tmp_path / "hybrid.h5ad",
        ("Gene Expression", "Peaks", "Antibody Capture"),
        rows=300,
        layout="csc",
    )
    with h5py.File(path, "a") as f:
        f["obs/FRiP"][0] = np.nan
    page = browser_page
    open_scientific(page, inspect_h5ad(path), tmp_path, "hybrid-modules")
    assert all(
        name in page.locator("#scientific-profiles").inner_text()
        for name in ("RNA", "ATAC", "Multiomics")
    )
    assert "Sampled: 256 / 300" in page.locator("#feature-scope").inner_text()
    assert page.locator("#feature-select option").count() == 3
    before = page.locator("#feature-chart").inner_html()
    page.locator("#feature-select").select_option(index=1)
    assert "atac" in page.locator("#feature-scope").inner_text()
    assert before != page.locator("#feature-chart").inner_html()
    assert (
        sum(
            page.locator("#feature-chart rect").evaluate_all(
                "bars => bars.map(b => +b.dataset.count)"
            )
        )
        == 256
    )
    page.locator("#metric-select").select_option(label="/obs/FRiP")
    assert "255 finite values; 1 missing/non-finite" in page.locator("#metric-scope").inner_text()
    assert (
        sum(
            page.locator("#metric-chart rect").evaluate_all(
                "bars => bars.map(b => +b.dataset.count)"
            )
        )
        == 255
    )
    page.get_by_text("Panel capabilities ·", exact=False).click()
    assert (
        page.locator('[data-capability="gene_activity"]').get_attribute("data-state")
        == "unsupported"
    )
    screenshot(page, tmp_path, "hybrid-modules")


def test_spatial_points_keep_row_identity_and_images_never_imply_registration(
    browser_page, tmp_path
):
    path = scientific_fixture(tmp_path / "spatial.h5ad", spatial=True, image=True)
    with h5py.File(path, "a") as f:
        coords = f["obsm/spatial"][:].astype(float)
        coords[1, 0] = np.nan
        del f["obsm/spatial"]
        f["obsm"].create_dataset("spatial", data=coords)
        f.require_group("uns/cellondesk_spatial").create_dataset("coordinate_frame", data="stage")
        f["uns/cellondesk_spatial"].create_dataset("image_frame", data="camera")
    page = browser_page
    page.add_init_script("""window.spatialPlot = [];
      const arc = CanvasRenderingContext2D.prototype.arc;
      CanvasRenderingContext2D.prototype.arc = function(...args) {
        if (this.canvas.id === 'spatial-canvas') window.spatialPlot.push(args.slice(0, 2));
        return arc.apply(this, args);
      };""")
    open_scientific(page, inspect_h5ad(path), tmp_path, "spatial-modules")
    assert (
        "11 / 12 observations plotted; 1 sampled rows excluded"
        in page.locator("#spatial-scope").inner_text()
    )
    assert "Units: not reported" in page.locator("#spatial-scope").inner_text()
    assert page.locator("#spatial-canvas").get_attribute("data-points") == "11"
    positions = page.evaluate("window.spatialPlot")
    # Original rows 0, 2, 3 after excluding row 1: equal units on both axes
    # must occupy equal pixel distances despite their different value ranges.
    assert (positions[2][0] - positions[0][0]) / 3 == pytest.approx(
        (positions[0][1] - positions[1][1]) / 2
    )
    plain = page.locator("#spatial-canvas").evaluate("c => c.toDataURL()")
    page.locator("#spatial-color").select_option(index=1)
    assert page.locator("#spatial-canvas").evaluate("c => c.toDataURL()") != plain
    assert page.locator("#scientific-images img").count() == 1
    assert page.locator("#scientific-images img").evaluate(
        "i => i.complete && i.naturalWidth === 30"
    )
    assert "registration has not been established" in page.locator("#image-panel").inner_text()
    assert (
        page.locator('[data-capability="image_overlay"]').get_attribute("data-state") == "invalid"
    )
    screenshot(page, tmp_path, "spatial-modules")
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_native_modules_never_color_other_module_rows_even_when_counts_match(
    browser_page, tmp_path
):
    path = multiome_fixture(tmp_path / "native.h5mu")
    with h5py.File(path, "a") as f:
        f["mod/atac/obs/_index"][0] = "mismatched"
    page = browser_page
    open_scientific(page, inspect_scientific(path), tmp_path, "native-multiome")
    assert "invalid" in page.locator("#correspondence-table").inner_text()
    assert "H5MU" in page.locator("header").inner_text()
    page.locator("#spatial-select").select_option(label="/mod/atac/obsm/spatial")
    assert page.locator("#spatial-color option").all_text_contents() == [
        "No feature color",
        "chr1:100-150",
        "chr1:150-200",
    ]
    page.locator("#spatial-select").select_option(label="/mod/rna/obsm/spatial")
    assert page.locator("#spatial-color option").all_text_contents() == [
        "No feature color",
        "feature-0",
        "feature-1",
    ]
    screenshot(page, tmp_path, "native-multiome")


@pytest.mark.parametrize("name", ["visium", "imaging"])
def test_public_spatial_examples_and_explicit_ambiguous_override(browser_page, tmp_path, name):
    path = public_fixture(tmp_path / f"{name}.h5ad", name)
    overrides = ["spatial_proteomics"] if name == "imaging" else None
    page = browser_page
    open_scientific(
        page, inspect_h5ad(path, modality_override=overrides), tmp_path, f"public-{name}"
    )
    assert "32 / 32 observations plotted" in page.locator("#spatial-scope").inner_text()
    if name == "imaging":
        assert "manual" in page.locator("#scientific-profiles").inner_text()
        assert "spatial_proteomics" in page.locator("#manual-profile-note").inner_text()
        assert (
            page.locator('[data-capability="protein_values"]').get_attribute("data-state")
            == "missing"
        )
        assert page.locator("#scientific-images img").count() == 0
    else:
        assert "Spatial transcriptomics" in page.locator("#scientific-profiles").inner_text()
        assert page.locator("#scientific-images img").count() == 1
    screenshot(page, tmp_path, f"public-{name}")


def test_untrusted_profile_and_feature_labels_cannot_create_external_content(
    browser_page, tmp_path
):
    path = scientific_fixture(tmp_path / "labels.h5ad", ("", ""), qc=False)
    hostile = '</script><img src="https://invalid.test/remote" onerror="window.injected=true">'
    with h5py.File(path, "a") as f:
        f["var/_index"][0] = hostile
        f.require_group("uns").create_dataset("assay", data=hostile)
    page = browser_page
    open_scientific(page, inspect_h5ad(path), tmp_path, "modality-untrusted-labels")
    assert (
        page.locator("#feature-select option")
        .first.inner_text()
        .startswith("unclassified · </script>")
    )
    assert page.locator("img").count() == 0
    assert page.evaluate("window.injected") is None
    assert page.locator("#recorded-metric-panel").is_hidden()
    assert page.locator("#spatial-panel").is_hidden()

"""Opt-in offline Chromium interactions and reviewable screenshot artifacts."""

import os
from pathlib import Path

import h5py
import numpy as np
import pytest
from h5ad_fixtures import dashboard_fixture, strings

from cellondesk import H5ADInspection, inspect_h5ad
from cellondesk.h5ad_report import write_h5ad_report
from cellondesk.inspection import EmbeddingPreview, MatrixSummary

pytestmark = pytest.mark.skipif(
    os.environ.get("CELLONDESK_BROWSER_TESTS") != "1",
    reason="Set CELLONDESK_BROWSER_TESTS=1 to run offline Chromium tests",
)


@pytest.fixture
def browser_page(tmp_path):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        executable = os.environ.get("CELLONDESK_BROWSER_EXECUTABLE")
        browser = playwright.chromium.launch(
            executable_path=executable, headless=True, timeout=15000
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 1100},
            offline=True,
            device_scale_factor=1,
            reduced_motion="reduce",
        )
        page = context.new_page()
        errors, network = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "request",
            lambda request: (
                network.append(request.url) if request.url.startswith(("http:", "https:")) else None
            ),
        )
        yield page
        assert not errors, errors
        assert not network, network
        context.close()
        browser.close()


def artifact_dir(tmp_path):
    path = Path(os.environ.get("CELLONDESK_BROWSER_ARTIFACTS", str(tmp_path)))
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def screenshot(page, tmp_path, name):
    path = artifact_dir(tmp_path) / f"{name}.png"
    page.evaluate("window.scrollTo(0, 0)")
    page.screenshot(path=str(path), full_page=True, animations="disabled")
    assert path.read_bytes().startswith(b"\x89PNG") and path.stat().st_size > 10_000


def report(tmp_path, name="modern", **kwargs):
    source = dashboard_fixture(tmp_path / f"{name}.h5ad", **kwargs)
    inspection = inspect_h5ad(source)
    return write_h5ad_report(inspection, artifact_dir(tmp_path) / f"{name}.html")


def test_offline_overview_coloring_composition_qc_and_screenshots(browser_page, tmp_path):
    page = browser_page
    page.goto(report(tmp_path).as_uri())
    assert page.title() == "CellOnDesk H5AD Summary"
    assert "All rows: 12 / 12" in page.locator("#coverage-banner").inner_text()
    screenshot(page, tmp_path, "overview")
    page.get_by_role("tab", name="Embeddings", exact=True).click()
    assert "10 plotted / 12 total" in page.locator("#point-count").inner_text()
    assert "2 non-finite coordinates excluded" in page.locator("#point-count").inner_text()
    assert "Missing · 1" in page.locator("#legend").inner_text()  # row 8 is not plotted
    assert "∅ Missing metadata · 2" in page.locator("#legend").inner_text()
    categorical_pixels = page.locator("#embedding-canvas").evaluate(
        "(canvas) => canvas.toDataURL()"
    )
    page.locator("#color-select").select_option(label="score · numeric")
    assert "Missing/non-finite: 1" in page.locator("#color-note").inner_text()
    assert page.locator(".scale-label").all_text_contents() == ["0", "110"]
    assert page.locator("#embedding-canvas").evaluate("(c) => c.toDataURL()") != categorical_pixels
    screenshot(page, tmp_path, "embedding-numeric")
    page.locator("#color-select").select_option(label="all_missing · numeric")
    assert "No finite plotted values" in page.locator("#color-note").inner_text()
    assert page.locator(".color-scale").count() == 0
    page.locator("#color-select").select_option(label="constant · numeric")
    assert "constant value" in page.locator("#color-note").inner_text()
    page.locator("#color-select").select_option(label="cell_type · categorical")
    page.locator("#legend button").first.click()
    assert page.locator("#legend button[aria-pressed=true]").count() == 1
    page.locator("#reset-highlight").click()
    assert page.locator("#legend button[aria-pressed=true]").count() == 0
    screenshot(page, tmp_path, "embedding-categorical")
    page.locator("#embedding-select").select_option(index=1)
    assert "12 plotted / 12 total" in page.locator("#point-count").inner_text()
    page.get_by_role("tab", name="Cell composition", exact=True).click()
    counts = page.locator("#composition-table tbody tr").evaluate_all(
        "(rows) => Object.fromEntries(rows.map(r => [r.cells[0].textContent, Number(r.cells[1].textContent)]))"
    )
    assert counts == {"T cell": 4, "B cell": 4, "Missing": 2, "∅ Missing metadata": 2}
    cross = page.locator("#cross-table tbody tr").evaluate_all(
        "(rows) => Object.fromEntries(rows.map(r => [r.cells[0].textContent, [...r.cells].slice(1).map(c => Number(c.textContent))]))"
    )
    assert cross == {
        "sample-A": [2, 2, 0, 0, 4],
        "sample-B": [1, 0, 1, 2, 4],
        "sample-C": [1, 2, 0, 0, 3],
        "∅ Missing metadata": [0, 0, 1, 0, 1],
    }
    page.locator("#composition-mode").select_option("percent")
    page.locator("#cross-mode").select_option("percent")
    assert page.locator("#cross-table tbody tr").first.locator("td").first.inner_text() == "50.00%"
    assert page.locator("#cross-table tfoot tr").locator("td").last.inner_text() == "12"
    screenshot(page, tmp_path, "composition")
    page.get_by_role("tab", name="QC & metadata", exact=True).click()
    page.locator("#qc-field").select_option(label="score")
    assert "finite: 10 · missing/non-finite: 2" in page.locator("#qc-scope").inner_text()
    counts = page.locator("#qc-chart rect").evaluate_all(
        "(bars) => bars.map(b => Number(b.dataset.count))"
    )
    assert sum(counts) == 10
    screenshot(page, tmp_path, "qc")
    page.locator("#qc-field").select_option(label="all_missing")
    assert "No finite values" in page.locator("#qc-chart").inner_text()
    assert page.locator("#qc-chart rect").count() == 0
    page.locator("#qc-field").select_option(label="constant")
    assert page.locator("#qc-chart rect").count() == 1
    assert page.locator("#qc-chart rect").get_attribute("data-count") == "12"
    page.get_by_role("tab", name="Provenance", exact=True).click()
    assert "no checksum" in page.locator("#provenance").inner_text()
    screenshot(page, tmp_path, "provenance")
    page.get_by_role("tab", name="Provenance", exact=True).focus()
    page.keyboard.press("Home")
    assert (
        page.get_by_role("tab", name="Overview", exact=True).get_attribute("aria-selected")
        == "true"
    )
    page.keyboard.press("ArrowRight")
    assert page.locator("#embeddings").is_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    screenshot(page, tmp_path, "mobile-embedding")


def test_sampled_report_uses_matching_rows_and_denominators(browser_page, tmp_path):
    source = dashboard_fixture(tmp_path / "sampled.h5ad")
    result = inspect_h5ad(source, max_points=4, max_column_values=6)
    path = write_h5ad_report(result, artifact_dir(tmp_path) / "sampled.html")
    page = browser_page
    page.goto(path.as_uri())
    assert "Sampled: 6 / 12" in page.locator("#coverage-banner").inner_text()
    page.get_by_role("tab", name="Embeddings", exact=True).click()
    assert "3 plotted / 12 total" in page.locator("#point-count").inner_text()
    page.locator("#color-select").select_option(label="score · numeric")
    assert "Missing/non-finite: 0" in page.locator("#color-note").inner_text()
    # Verify colors at the actual canvas point centers: original rows 0, 7, 11.
    pixels = page.locator("#embedding-canvas").evaluate("""canvas => {
      const c = canvas.getContext('2d');
      return [[163,568],[937,310],[937,52]].map(([x,y]) => Array.from(c.getImageData(x,y,1,1).data));
    }""")
    assert len({tuple(p) for p in pixels}) == 3
    page.get_by_role("tab", name="Cell composition", exact=True).click()
    assert "Sampled: 6 / 12" in page.locator("#composition-scope").inner_text()
    assert page.locator("#cross-table tfoot td").last.inner_text() == "6"
    page.get_by_role("tab", name="QC & metadata", exact=True).click()
    page.locator("#qc-field").select_option(label="score")
    assert "Sampled: 6 / 12" in page.locator("#qc-scope").inner_text()
    assert (
        sum(
            page.locator("#qc-chart rect").evaluate_all("(bars) => bars.map(b => +b.dataset.count)")
        )
        == 6
    )
    screenshot(page, tmp_path, "sampled-qc")


@pytest.mark.parametrize("layout", ["legacy", "compound"])
def test_legacy_layout_browser(browser_page, tmp_path, layout):
    page = browser_page
    page.goto(report(tmp_path, name=layout, layout=layout, matrix="csr").as_uri())
    page.get_by_role("tab", name="Embeddings", exact=True).click()
    assert "10 plotted" in page.locator("#point-count").inner_text()
    page.locator("#color-select").select_option(label="score · numeric")
    assert page.locator(".scale-label").all_text_contents() == ["0", "110"]
    screenshot(page, tmp_path, layout)


def test_empty_and_older_inspections_are_honest(browser_page, tmp_path):
    page = browser_page
    page.goto(report(tmp_path, name="empty", rows=0).as_uri())
    page.get_by_role("tab", name="Embeddings", exact=True).click()
    assert "0 plotted / 0 total" in page.locator("#point-count").inner_text()
    page.get_by_role("tab", name="Cell composition", exact=True).click()
    assert "No categorical observation values" in page.locator("#composition-bars").inner_text()
    page.get_by_role("tab", name="QC & metadata", exact=True).click()
    assert "No finite values" in page.locator("#qc-chart").inner_text()
    old = H5ADInspection(
        source_path="old.h5ad",
        file_name="old.h5ad",
        file_size_bytes=0,
        n_obs=2,
        n_vars=3,
        matrix=MatrixSummary(shape=(2, 3), encoding="array"),
        embeddings=[
            EmbeddingPreview(
                key="X_umap",
                total_points=2,
                dimensions=2,
                sampled_points=[[0, 0], [1, 1]],
                color_field="cell_type",
                color_values=["T", "B"],
            )
        ],
    )
    path = write_h5ad_report(old, artifact_dir(tmp_path) / "old-inspection.html")
    page.goto(path.as_uri())
    page.get_by_role("tab", name="Embeddings", exact=True).click()
    assert "candidate count not recorded" in page.locator("#point-count").inner_text()
    assert "T · 1" in page.locator("#legend").inner_text()
    page.get_by_role("tab", name="Cell composition", exact=True).click()
    assert "not recorded" in page.locator("#composition-scope").inner_text()
    screenshot(page, tmp_path, "old-inspection")


def test_high_cardinality_and_hostile_labels_keep_totals_and_do_not_execute(browser_page, tmp_path):
    path = dashboard_fixture(tmp_path / "labels.h5ad", rows=80)
    hostile = '</script><img src="https://invalid.test/x" onerror="window.injected=true">'
    with h5py.File(path, "a") as f:
        strings(f["obs"], hostile, [hostile] * 80)
        f["obs"].attrs["column-order"] = [*f["obs"].attrs["column-order"], hostile]
        f["obs/unique_id"][0] = "Σ Other categories (pooled)"
        f["obs/cell_type/categories"][0] = "∅ Missing metadata"
        f["obs/cell_type/categories"][1] = "Σ Other categories (pooled)"
        f["obs/all_missing"][...] = np.nan
    result = inspect_h5ad(path)
    target = write_h5ad_report(result, artifact_dir(tmp_path) / "labels.html", title=hostile)
    page = browser_page
    page.goto(target.as_uri())
    assert page.title() == hostile
    assert page.evaluate("window.injected") is None
    page.get_by_role("tab", name="Cell composition", exact=True).click()
    labels = page.locator("#composition-table tbody th").all_text_contents()
    assert "∅ Missing metadata (literal category)" in labels
    assert "∅ Missing metadata" in labels
    assert "Σ Other categories (pooled) (literal category)" in labels
    page.locator("#composition-field").select_option(label="unique_id")
    assert "60 categories beyond" in page.locator("#composition-note").inner_text()
    assert (
        sum(
            page.locator("#composition-table tbody tr").evaluate_all(
                "(rows) => rows.map(r => +r.cells[1].textContent)"
            )
        )
        == 80
    )
    assert page.locator("#cross-table tfoot td").last.inner_text() == "80"
    page.locator("#sample-field").select_option(label="unique_id")
    assert "60 sample values are pooled" in page.locator("#cross-note").inner_text()
    assert page.locator("#cross-table tfoot td").last.inner_text() == "80"
    page.locator("#composition-field").select_option(label=hostile)
    assert page.locator("#composition-table tbody th").first.inner_text() == hostile
    assert page.locator("img").count() == 0
    screenshot(page, tmp_path, "hostile-labels")

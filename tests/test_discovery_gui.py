import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from discovery_fixtures import CatalogFixture
from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtWidgets import QApplication

from cellondesk.catalog_cache import SearchStats
from cellondesk.discovery import DiscoveryService, SourceOutcome
from cellondesk.discovery_gui import DiscoveryWidget
from cellondesk.models import DatasetRecord


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def widget(app):
    widget = DiscoveryWidget()
    widget.resize(1440, 900)
    widget.show()
    app.processEvents()
    yield widget
    widget.shutdown()
    widget.close()


def records():
    return [
        DatasetRecord(
            source="HuBMAP",
            dataset_id="uuid-one",
            title="First kidney",
            organ="LK",
            raw={"hubmap_id": "HBM.ONE"},
            reported_cell_count=9,
            status="Published",
            access_level="public",
            acquisition_methods=["HuBMAP CLT / Globus"],
        ),
        DatasetRecord(
            source="CELLxGENE Discover",
            dataset_id="uuid-two",
            title="Second kidney",
            reported_cell_count=1200,
            asset_status="advertised",
            access_level="public",
            acquisition_methods=["Direct download (advertised)"],
        ),
        DatasetRecord(source="UCSC Cell Browser", dataset_id="uuid-three", title="Third brain"),
    ]


def test_selection_tracks_source_model_after_numeric_sort_and_filter(widget, app):
    widget.set_records(records())
    widget.table.sortByColumn(5, Qt.SortOrder.DescendingOrder)
    widget.table.selectRow(0)
    assert widget.selected_record().dataset_id == "uuid-two"
    assert "uuid-two" in widget.details.toPlainText()
    assert not widget.manifest_button.isEnabled()
    clicked = []
    widget.resolve_requested.connect(clicked.append)
    widget.resolve_button.click()
    assert clicked[0].dataset_id == "uuid-two"
    widget.table.sortByColumn(1, Qt.SortOrder.AscendingOrder)
    assert widget.selected_record().dataset_id == "uuid-two"
    widget.local_text.setText("brain")
    assert widget.proxy.rowCount() == 1
    assert widget.selected_record() is None
    assert widget.details.toPlainText() == ""
    assert not widget.resolve_button.isEnabled()
    widget.local_text.clear()
    widget.table.selectRow(0)
    assert widget.selected_record().dataset_id == "uuid-one"
    assert widget.manifest_button.isEnabled()
    widget.local_source.setCurrentIndex(2)  # CELLxGENE
    assert widget.selected_record() is None
    assert not widget.manifest_button.isEnabled()


def test_result_updates_preserve_identity_and_clear_removed_selection(widget):
    results = records()
    widget.set_records(results[:1])
    widget.table.selectRow(0)
    widget.set_records(list(reversed(results)))
    assert widget.selected_record().dataset_id == "uuid-one"
    assert "uuid-one" in widget.details.toPlainText()
    widget.set_records(results[1:])
    assert widget.selected_record() is None
    assert widget.details.toPlainText() == ""


def _finish(app, widget):
    deadline = time.monotonic() + 5
    while widget.worker.isRunning() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.002)
    assert not widget.worker.isRunning()
    app.processEvents()


def test_network_off_gui_thread_and_independent_source_errors(widget, app, tmp_path):
    fixture = CatalogFixture()
    handler = fixture.handler
    threads = []

    def checked(request):
        threads.append(QThread.currentThread())
        assert QThread.currentThread() != app.thread()
        time.sleep(0.015)
        if request.url.host == "cells.ucsc.edu":
            raise RuntimeError("UCSC offline in test")
        return handler(request)

    fixture.handler = checked
    widget.service = DiscoveryService(factories=fixture.factories(tmp_path))
    ticks = []
    timer = QTimer()
    timer.setInterval(1)
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start()
    widget.inputs["tissue"].setText("kidney")
    widget.search_button.click()
    assert widget.progress.isVisible()
    assert not widget.search_button.isEnabled()
    _finish(app, widget)
    timer.stop()
    assert ticks and threads
    assert widget.model.rowCount() == 7
    assert "ERROR" in widget.status_labels["ucsc"].text()
    assert "complete" in widget.status_labels["cellxgene"].text()
    assert widget.search_button.isEnabled()
    assert not widget.progress.isVisible()
    widget.inputs["tissue"].setText("brain")
    assert "tissue: kidney" in widget.query_label.text()
    # Sorting/filtering do not make network calls.
    requests = len(fixture.requests)
    widget.local_text.setText("RK")
    widget.table.sortByColumn(1, Qt.SortOrder.AscendingOrder)
    assert len(fixture.requests) == requests


def test_advanced_filters_are_explicit_and_hidden_filters_inactive(widget, app):
    queries = []

    class Service:
        def search(self, query, **kwargs):
            queries.append(query)
            return []

    widget.service = Service()
    widget.inputs["tissue"].setText("kidney")
    widget.disease.setText("normal")
    widget.search_button.click()
    _finish(app, widget)
    assert queries[-1].disease == ""
    widget.advanced_toggle.setChecked(True)
    widget.refresh_button.click()
    _finish(app, widget)
    assert queries[-1].disease == "normal"
    assert queries[-1].refresh


def test_discovery_screenshot_and_partial_scope(widget, app, tmp_path):
    fixture = CatalogFixture()
    widget.resize(1680, 900)
    widget.service = DiscoveryService(factories=fixture.factories(tmp_path))
    widget.inputs["tissue"].setText("kidney")
    widget.search_button.click()
    _finish(app, widget)
    widget.accept_outcome(
        SourceOutcome(
            "hubmap",
            records=widget.outcomes["hubmap"].records,
            stats=SearchStats(
                returned=6,
                matched=6,
                scanned=6,
                complete=False,
                warnings=["Synthetic demonstration: source deadline reached."],
            ),
        )
    )
    widget.table.sortByColumn(5, Qt.SortOrder.DescendingOrder)
    widget.table.selectRow(0)
    app.processEvents()
    assert "PARTIAL" in widget.status_labels["hubmap"].text()
    directory = Path(os.environ.get("CELLONDESK_GUI_ARTIFACTS", str(tmp_path)))
    directory.mkdir(parents=True, exist_ok=True)
    screenshot = directory / "discovery-workspace.png"
    assert widget.grab().save(str(screenshot))
    assert screenshot.stat().st_size > 10000


def test_validation_returns_controls_to_ready_state(widget, app):
    widget.search_button.click()
    _finish(app, widget)
    assert widget.search_button.isEnabled()
    assert "filter" in widget.count_label.text()
    assert widget.selected_record() is None


def test_modality_facets_and_details_remain_distinct_from_assay_and_verified_files(widget, app, tmp_path):
    fixture = CatalogFixture()
    widget.service = DiscoveryService(factories=fixture.factories(tmp_path))
    widget.sources["hubmap"].setChecked(False)
    widget.sources["ucsc"].setChecked(False)
    widget.modalities["rna"].setChecked(True)
    widget.modalities["atac"].setChecked(True)
    widget.search_button.click()
    _finish(app, widget)
    assert widget.worker.query.modalities == ("rna", "atac")
    assert widget.worker.query.assay == ""
    assert widget.model.rowCount() == 1
    widget.table.sortByColumn(9, Qt.SortOrder.DescendingOrder)
    widget.table.selectRow(0)
    assert widget.selected_record().dataset_id == "cxg-kidney"
    details = widget.details.toPlainText()
    assert "Assay-derived modality hints (unverified): rna" in details
    assert "File-verified modalities: File not inspected" in details
    assert "Bounded H5AD" in details
    requests = len(fixture.requests)
    widget.local_text.setText("transcriptomics")
    assert widget.proxy.rowCount() == 1
    assert widget.selected_record().dataset_id == "cxg-kidney"
    widget.local_text.setText("chromatin")
    assert widget.selected_record() is None and not widget.details.toPlainText()
    assert len(fixture.requests) == requests

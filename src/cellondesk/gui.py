from __future__ import annotations

import importlib.util
import json
import sys
import webbrowser
from pathlib import Path

import httpx

from .assets import format_bytes, iter_download
from .census_report import write_census_report
from .h5ad_compat import H5ADInspection, inspect_h5ad
from .h5ad_report import write_h5ad_report
from .manifest import write_hubmap_manifest
from .models import DataAsset, DatasetRecord
from .report import write_html_report
from .sources.cellxgene_discover import CellxGeneDiscoverClient
from .sources.census import CensusGenePreview, CensusQuery, preview_census_gene
from .sources.hubmap import SPATIAL_DATASET_TYPES, HuBMAPClient
from .sources.ucsc_cellbrowser import UCSCCellBrowserClient

CELLXGENE_DISCOVER_URL = "https://cellxgene.cziscience.com/datasets"
CELLXGENE_CENSUS_URL = "https://chanzuckerberg.github.io/cellxgene-census/"


def main() -> None:
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QApplication,
            QComboBox,
            QFileDialog,
            QFormLayout,
            QHBoxLayout,
            QInputDialog,
            QLabel,
            QLineEdit,
            QMainWindow,
            QMessageBox,
            QProgressDialog,
            QPushButton,
            QSpinBox,
            QSplitter,
            QTableWidget,
            QTableWidgetItem,
            QTabWidget,
            QTextEdit,
            QVBoxLayout,
            QWidget,
        )
    except ImportError as exc:
        raise SystemExit('Install GUI dependencies with: pip install "cellondesk[gui]"') from exc

    class Window(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("CellOnDesk")
            self.resize(1380, 840)
            self.records: list[DatasetRecord] = []
            self.cellxgene_records: list[DatasetRecord] = []
            self.ucsc_records: list[DatasetRecord] = []
            self.census_preview: CensusGenePreview | None = None
            self.h5ad_inspection: H5ADInspection | None = None
            self.h5ad_path: Path | None = None

            self.tabs = QTabWidget()
            self.tabs.addTab(self._build_hubmap_tab(), "HuBMAP")
            self.tabs.addTab(self._build_cellxgene_tab(), "CELLxGENE")
            self.tabs.addTab(self._build_ucsc_tab(), "UCSC Cell Browser")
            self.tabs.addTab(self._build_h5ad_tab(), "Local H5AD")
            self.setCentralWidget(self.tabs)
            self.statusBar().showMessage("Ready")

        def _build_hubmap_tab(self) -> QWidget:
            root = QWidget()
            layout = QVBoxLayout(root)
            helper = QLabel(
                "Search published HuBMAP datasets. Ordinary organ names such as kidney are mapped "
                "to HuBMAP codes. Use Find data products to resolve verified public files and "
                "download them directly into CellOnDesk."
            )
            helper.setWordWrap(True)
            layout.addWidget(helper)

            controls = QHBoxLayout()
            self.dataset_type = QComboBox()
            self.dataset_type.setEditable(True)
            self.dataset_type.addItem("")
            self.dataset_type.addItems(SPATIAL_DATASET_TYPES)
            self.organ = QLineEdit()
            self.organ.setPlaceholderText("kidney, spleen, LK, RK, ...")
            self.limit = QSpinBox()
            self.limit.setRange(1, 1000)
            self.limit.setValue(50)
            search_button = QPushButton("Search HuBMAP")
            products_button = QPushButton("Find data products")
            open_button = QPushButton("Open portal")
            manifest_button = QPushButton("Export CLT manifest")
            report_button = QPushButton("Export HTML summary")
            for widget in (
                QLabel("Assay"),
                self.dataset_type,
                QLabel("Organ"),
                self.organ,
                QLabel("Limit"),
                self.limit,
                search_button,
                products_button,
                open_button,
                manifest_button,
                report_button,
            ):
                controls.addWidget(widget)
            layout.addLayout(controls)

            splitter = QSplitter(Qt.Orientation.Vertical)
            self.table = QTableWidget(0, 6)
            self.table.setHorizontalHeaderLabels(
                ["HuBMAP ID", "Type", "Organ", "Status", "Access", "Title"]
            )
            self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
            self.details = QTextEdit()
            self.details.setReadOnly(True)
            splitter.addWidget(self.table)
            splitter.addWidget(self.details)
            layout.addWidget(splitter)

            search_button.clicked.connect(self.search_hubmap)
            products_button.clicked.connect(self.download_hubmap_product)
            open_button.clicked.connect(self.open_selected_hubmap)
            manifest_button.clicked.connect(self.export_manifest)
            report_button.clicked.connect(self.export_report)
            self.table.itemSelectionChanged.connect(self.show_hubmap_details)
            self.table.itemDoubleClicked.connect(lambda _item: self.download_hubmap_product())
            return root

        def _build_cellxgene_tab(self) -> QWidget:
            root = QWidget()
            layout = QVBoxLayout(root)
            helper = QLabel(
                "Search the public CELLxGENE Discover index directly. For datasets whose public "
                "index exposes downloadable assets, CellOnDesk can download the H5AD itself and "
                "send it straight to Local H5AD."
            )
            helper.setWordWrap(True)
            layout.addWidget(helper)

            filter_row = QHBoxLayout()
            self.cxg_tissue = QLineEdit()
            self.cxg_tissue.setPlaceholderText("kidney, lung, blood, ...")
            self.cxg_disease = QLineEdit()
            self.cxg_disease.setPlaceholderText("normal, cancer, ...")
            self.cxg_organism = QLineEdit()
            self.cxg_organism.setPlaceholderText("Homo sapiens, Mus musculus, ...")
            self.cxg_cell_type = QLineEdit()
            self.cxg_cell_type.setPlaceholderText("T cell, endothelial cell, ...")
            for widget in (
                QLabel("Tissue"),
                self.cxg_tissue,
                QLabel("Disease"),
                self.cxg_disease,
                QLabel("Organism"),
                self.cxg_organism,
                QLabel("Cell type"),
                self.cxg_cell_type,
            ):
                filter_row.addWidget(widget)
            layout.addLayout(filter_row)

            action_row = QHBoxLayout()
            self.cxg_query = QLineEdit()
            self.cxg_query.setPlaceholderText("Optional text search")
            self.cxg_limit = QSpinBox()
            self.cxg_limit.setRange(1, 500)
            self.cxg_limit.setValue(50)
            search_button = QPushButton("Search CELLxGENE")
            products_button = QPushButton("Find / download data")
            portal_button = QPushButton("Open Discover")
            for widget in (
                QLabel("Text"),
                self.cxg_query,
                QLabel("Limit"),
                self.cxg_limit,
                search_button,
                products_button,
                portal_button,
            ):
                action_row.addWidget(widget)
            layout.addLayout(action_row)

            self.cxg_table = QTableWidget(0, 5)
            self.cxg_table.setHorizontalHeaderLabels(
                ["Dataset", "Assay", "Tissue", "Access", "Title"]
            )
            self.cxg_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            self.cxg_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
            self.cxg_details = QTextEdit()
            self.cxg_details.setReadOnly(True)
            cxg_splitter = QSplitter(Qt.Orientation.Vertical)
            cxg_splitter.addWidget(self.cxg_table)
            cxg_splitter.addWidget(self.cxg_details)
            layout.addWidget(cxg_splitter)

            census_available = importlib.util.find_spec("cellxgene_census") is not None
            census_status = QLabel(
                "Optional Census/SOMA gene preview is available in this environment."
                if census_available
                else "Optional native Census/SOMA is not bundled in the Windows installer. "
                "Discover search and public file downloads do not require it."
            )
            census_status.setWordWrap(True)
            layout.addWidget(census_status)

            census_query = QWidget()
            census_form = QFormLayout(census_query)
            self.census_gene = QLineEdit()
            self.census_gene.setPlaceholderText("Gene, e.g. CD3D")
            self.census_tissue = QLineEdit()
            self.census_tissue.setPlaceholderText("Optional exact tissue label")
            self.census_cell_type = QLineEdit()
            self.census_cell_type.setPlaceholderText("Optional exact cell type")
            self.census_max_cells = QSpinBox()
            self.census_max_cells.setRange(100, 50000)
            self.census_max_cells.setValue(5000)
            census_form.addRow("Census gene", self.census_gene)
            census_form.addRow("Census tissue", self.census_tissue)
            census_form.addRow("Census cell type", self.census_cell_type)
            census_form.addRow("Max cells", self.census_max_cells)
            layout.addWidget(census_query)

            census_controls = QHBoxLayout()
            preview_button = QPushButton("Run bounded Census preview")
            export_button = QPushButton("Export Census HTML")
            docs_button = QPushButton("Census documentation")
            preview_button.setEnabled(census_available)
            export_button.setEnabled(census_available)
            census_controls.addWidget(preview_button)
            census_controls.addWidget(export_button)
            census_controls.addWidget(docs_button)
            census_controls.addStretch(1)
            layout.addLayout(census_controls)

            self.census_details = QTextEdit()
            self.census_details.setReadOnly(True)
            self.census_details.setMaximumHeight(130)
            layout.addWidget(self.census_details)

            search_button.clicked.connect(self.search_cellxgene)
            products_button.clicked.connect(self.download_cellxgene_product)
            portal_button.clicked.connect(lambda: webbrowser.open(CELLXGENE_DISCOVER_URL))
            preview_button.clicked.connect(self.run_census_preview)
            export_button.clicked.connect(self.export_census_html)
            docs_button.clicked.connect(lambda: webbrowser.open(CELLXGENE_CENSUS_URL))
            self.cxg_table.itemSelectionChanged.connect(self.show_cellxgene_details)
            self.cxg_table.itemDoubleClicked.connect(lambda _item: self.download_cellxgene_product())
            return root

        def _build_ucsc_tab(self) -> QWidget:
            root = QWidget()
            layout = QVBoxLayout(root)
            helper = QLabel(
                "Search the UCSC Cell Browser public catalog. CellOnDesk resolves available matrix, "
                "metadata and coordinate files and downloads them directly when possible."
            )
            helper.setWordWrap(True)
            layout.addWidget(helper)

            controls = QHBoxLayout()
            self.ucsc_query = QLineEdit()
            self.ucsc_query.setPlaceholderText("Keyword, project, assay, disease, ...")
            self.ucsc_organ = QLineEdit()
            self.ucsc_organ.setPlaceholderText("kidney, brain, blood, ...")
            self.ucsc_organism = QLineEdit()
            self.ucsc_organism.setPlaceholderText("Human, mouse, ...")
            self.ucsc_limit = QSpinBox()
            self.ucsc_limit.setRange(1, 500)
            self.ucsc_limit.setValue(50)
            search_button = QPushButton("Search UCSC")
            products_button = QPushButton("Find / download data")
            portal_button = QPushButton("Open portal")
            for widget in (
                QLabel("Search"),
                self.ucsc_query,
                QLabel("Organ"),
                self.ucsc_organ,
                QLabel("Organism"),
                self.ucsc_organism,
                QLabel("Limit"),
                self.ucsc_limit,
                search_button,
                products_button,
                portal_button,
            ):
                controls.addWidget(widget)
            layout.addLayout(controls)

            splitter = QSplitter(Qt.Orientation.Vertical)
            self.ucsc_table = QTableWidget(0, 5)
            self.ucsc_table.setHorizontalHeaderLabels(
                ["Dataset", "Assay", "Organ", "Access", "Title"]
            )
            self.ucsc_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            self.ucsc_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
            self.ucsc_details = QTextEdit()
            self.ucsc_details.setReadOnly(True)
            splitter.addWidget(self.ucsc_table)
            splitter.addWidget(self.ucsc_details)
            layout.addWidget(splitter)

            search_button.clicked.connect(self.search_ucsc)
            products_button.clicked.connect(self.download_ucsc_product)
            portal_button.clicked.connect(self.open_selected_ucsc)
            self.ucsc_table.itemSelectionChanged.connect(self.show_ucsc_details)
            self.ucsc_table.itemDoubleClicked.connect(lambda _item: self.download_ucsc_product())
            return root

        def _build_h5ad_tab(self) -> QWidget:
            root = QWidget()
            layout = QVBoxLayout(root)
            controls = QHBoxLayout()
            self.h5ad_file_label = QLineEdit()
            self.h5ad_file_label.setReadOnly(True)
            self.h5ad_file_label.setPlaceholderText("Choose or download a local .h5ad file")
            self.h5ad_annotation = QLineEdit()
            self.h5ad_annotation.setPlaceholderText("Optional obs annotation, e.g. cell_type")
            self.h5ad_max_points = QSpinBox()
            self.h5ad_max_points.setRange(100, 50000)
            self.h5ad_max_points.setValue(5000)
            choose_button = QPushButton("Choose H5AD")
            inspect_button = QPushButton("Inspect")
            html_button = QPushButton("Export HTML")
            json_button = QPushButton("Export JSON")
            for widget in (
                choose_button,
                self.h5ad_file_label,
                QLabel("Annotation"),
                self.h5ad_annotation,
                QLabel("Max points"),
                self.h5ad_max_points,
                inspect_button,
                html_button,
                json_button,
            ):
                controls.addWidget(widget)
            layout.addLayout(controls)

            summary = QWidget()
            summary_form = QFormLayout(summary)
            self.h5ad_shape_label = QLabel("—")
            self.h5ad_matrix_label = QLabel("—")
            self.h5ad_layers_label = QLabel("—")
            self.h5ad_embeddings_label = QLabel("—")
            self.h5ad_annotation_label = QLabel("—")
            summary_form.addRow("Shape", self.h5ad_shape_label)
            summary_form.addRow("Matrix", self.h5ad_matrix_label)
            summary_form.addRow("Layers", self.h5ad_layers_label)
            summary_form.addRow("Embeddings", self.h5ad_embeddings_label)
            summary_form.addRow("Detected annotation", self.h5ad_annotation_label)
            layout.addWidget(summary)

            self.h5ad_details = QTextEdit()
            self.h5ad_details.setReadOnly(True)
            layout.addWidget(self.h5ad_details)

            choose_button.clicked.connect(self.choose_h5ad)
            inspect_button.clicked.connect(self.inspect_h5ad_file)
            html_button.clicked.connect(self.export_h5ad_html)
            json_button.clicked.connect(self.export_h5ad_json)
            return root

        def search_hubmap(self) -> None:
            try:
                with HuBMAPClient() as client:
                    self.records = client.search_datasets(
                        dataset_type=self.dataset_type.currentText().strip() or None,
                        organ=self.organ.text().strip() or None,
                        status="Published",
                        limit=self.limit.value(),
                    )
            except (httpx.HTTPError, ValueError) as exc:
                QMessageBox.critical(self, "HuBMAP search failed", str(exc))
                return
            self.table.setRowCount(len(self.records))
            for row, record in enumerate(self.records):
                self._set_row(
                    self.table,
                    row,
                    [
                        record.dataset_id,
                        record.dataset_type or "",
                        record.organ or "",
                        record.status or "",
                        record.access_level or "Not reported",
                        record.title,
                    ],
                )
            self.table.resizeColumnsToContents()
            self.statusBar().showMessage(f"Found {len(self.records)} HuBMAP datasets")

        def selected_records(self) -> list[DatasetRecord]:
            rows = sorted({index.row() for index in self.table.selectedIndexes()})
            return [self.records[row] for row in rows] if rows else self.records

        def _selected_record(self, table: QTableWidget, records: list[DatasetRecord], source: str) -> DatasetRecord | None:
            rows = sorted({index.row() for index in table.selectedIndexes()})
            if not rows:
                QMessageBox.information(self, "No dataset selected", f"Select a {source} row first.")
                return None
            return records[rows[0]]

        def open_selected_hubmap(self) -> None:
            record = self._selected_record(self.table, self.records, "HuBMAP")
            if record and record.portal_url:
                webbrowser.open(record.portal_url)

        def download_hubmap_product(self) -> None:
            record = self._selected_record(self.table, self.records, "HuBMAP")
            if record is None:
                return
            self.statusBar().showMessage("Resolving HuBMAP data products…")
            QApplication.processEvents()
            try:
                with HuBMAPClient() as client:
                    assets = client.resolve_assets(record)
            except httpx.HTTPError as exc:
                QMessageBox.critical(self, "HuBMAP product lookup failed", str(exc))
                return
            if not assets:
                self._no_assets(record, "No verified public direct files were found for this record or its indexed descendants.")
                return
            self._download_asset_choice(assets, "HuBMAP data products")

        def export_manifest(self) -> None:
            if not self.records:
                QMessageBox.information(self, "Nothing to export", "Run a search first.")
                return
            filename, _ = QFileDialog.getSaveFileName(
                self, "Export HuBMAP CLT manifest", "hubmap-manifest.txt", "Text files (*.txt)"
            )
            if filename:
                write_hubmap_manifest(self.selected_records(), Path(filename))
                self.statusBar().showMessage(f"Wrote {filename}")

        def export_report(self) -> None:
            if not self.records:
                QMessageBox.information(self, "Nothing to export", "Run a search first.")
                return
            filename, _ = QFileDialog.getSaveFileName(
                self, "Export CellOnDesk HTML summary", "web_summary.html", "HTML files (*.html)"
            )
            if filename:
                write_html_report(
                    self.selected_records(),
                    Path(filename),
                    query={
                        "source": "HuBMAP",
                        "dataset_type": self.dataset_type.currentText().strip() or None,
                        "organ": self.organ.text().strip() or None,
                        "status": "Published",
                        "limit": self.limit.value(),
                    },
                )
                self.statusBar().showMessage(f"Wrote {filename}")

        def show_hubmap_details(self) -> None:
            self._show_record_details(self.table, self.records, self.details)

        def search_cellxgene(self) -> None:
            try:
                with CellxGeneDiscoverClient() as client:
                    self.cellxgene_records = client.search_datasets(
                        tissue=self.cxg_tissue.text().strip() or None,
                        disease=self.cxg_disease.text().strip() or None,
                        organism=self.cxg_organism.text().strip() or None,
                        cell_type=self.cxg_cell_type.text().strip() or None,
                        query=self.cxg_query.text().strip() or None,
                        limit=self.cxg_limit.value(),
                    )
            except (httpx.HTTPError, TypeError, ValueError) as exc:
                QMessageBox.critical(self, "CELLxGENE Discover search failed", str(exc))
                return
            self.cxg_table.setRowCount(len(self.cellxgene_records))
            for row, record in enumerate(self.cellxgene_records):
                self._set_row(
                    self.cxg_table,
                    row,
                    [
                        record.dataset_id,
                        record.dataset_type or "",
                        record.organ or "",
                        record.access_level or "public",
                        record.title,
                    ],
                )
            self.cxg_table.resizeColumnsToContents()
            self.statusBar().showMessage(f"Found {len(self.cellxgene_records)} CELLxGENE datasets")

        def download_cellxgene_product(self) -> None:
            record = self._selected_record(self.cxg_table, self.cellxgene_records, "CELLxGENE")
            if record is None:
                return
            with CellxGeneDiscoverClient() as client:
                assets = client.resolve_assets(record)
            if not assets:
                self._no_assets(
                    record,
                    "The public dataset index did not expose a direct file asset for this dataset. "
                    "The Discover page remains available as a fallback.",
                )
                return
            self._download_asset_choice(assets, "CELLxGENE data products")

        def show_cellxgene_details(self) -> None:
            self._show_record_details(self.cxg_table, self.cellxgene_records, self.cxg_details)

        def run_census_preview(self) -> None:
            gene = self.census_gene.text().strip()
            if not gene:
                QMessageBox.information(self, "Gene required", "Enter a gene first.")
                return
            query = CensusQuery(
                gene=gene,
                tissue=self.census_tissue.text().strip() or None,
                cell_type=self.census_cell_type.text().strip() or None,
                max_cells=self.census_max_cells.value(),
            )
            try:
                self.census_preview = preview_census_gene(query)
            except (RuntimeError, ValueError, OSError) as exc:
                QMessageBox.critical(self, "CELLxGENE Census preview failed", str(exc))
                return
            self.census_details.setPlainText(self.census_preview.model_dump_json(indent=2))

        def export_census_html(self) -> None:
            if self.census_preview is None:
                QMessageBox.information(self, "Nothing to export", "Run a Census preview first.")
                return
            filename, _ = QFileDialog.getSaveFileName(
                self, "Export CELLxGENE Census HTML", "cellxgene-census-summary.html", "HTML files (*.html)"
            )
            if filename:
                write_census_report(self.census_preview, Path(filename))

        def search_ucsc(self) -> None:
            if not any(
                (
                    self.ucsc_query.text().strip(),
                    self.ucsc_organ.text().strip(),
                    self.ucsc_organism.text().strip(),
                )
            ):
                QMessageBox.information(self, "Add a filter", "Enter a keyword, organ or organism first.")
                return
            try:
                with UCSCCellBrowserClient() as client:
                    self.ucsc_records = client.search_datasets(
                        query=self.ucsc_query.text().strip() or None,
                        organ=self.ucsc_organ.text().strip() or None,
                        organism=self.ucsc_organism.text().strip() or None,
                        limit=self.ucsc_limit.value(),
                    )
            except (httpx.HTTPError, TypeError, ValueError) as exc:
                QMessageBox.critical(self, "UCSC Cell Browser search failed", str(exc))
                return
            self.ucsc_table.setRowCount(len(self.ucsc_records))
            for row, record in enumerate(self.ucsc_records):
                self._set_row(
                    self.ucsc_table,
                    row,
                    [
                        record.dataset_id,
                        record.dataset_type or "",
                        record.organ or "",
                        record.access_level or "public",
                        record.title,
                    ],
                )
            self.ucsc_table.resizeColumnsToContents()
            self.statusBar().showMessage(f"Found {len(self.ucsc_records)} UCSC datasets")

        def download_ucsc_product(self) -> None:
            record = self._selected_record(self.ucsc_table, self.ucsc_records, "UCSC")
            if record is None:
                return
            self.statusBar().showMessage("Resolving UCSC data files…")
            QApplication.processEvents()
            with UCSCCellBrowserClient() as client:
                assets = client.resolve_assets(record)
            if not assets:
                self._no_assets(record, "No directly downloadable matrix or metadata files were verified.")
                return
            self._download_asset_choice(assets, "UCSC Cell Browser files")

        def open_selected_ucsc(self) -> None:
            record = self._selected_record(self.ucsc_table, self.ucsc_records, "UCSC")
            if record and record.portal_url:
                webbrowser.open(record.portal_url)

        def show_ucsc_details(self) -> None:
            self._show_record_details(self.ucsc_table, self.ucsc_records, self.ucsc_details)

        def _download_asset_choice(self, assets: list[DataAsset], title: str) -> None:
            labels = [
                f"{asset.name} — {format_bytes(asset.size_bytes)}"
                + (f" — {asset.description}" if asset.description else "")
                for asset in assets
            ]
            choice, ok = QInputDialog.getItem(self, title, "Choose a file to download:", labels, 0, False)
            if not ok or not choice:
                return
            asset = assets[labels.index(choice)]
            filename, _ = QFileDialog.getSaveFileName(
                self,
                f"Save {asset.name}",
                asset.name,
                "H5AD files (*.h5ad);;All files (*)" if asset.is_h5ad else "All files (*)",
            )
            if not filename:
                return
            destination = Path(filename)
            progress = QProgressDialog(f"Downloading {asset.name}…", "Cancel", 0, 100, self)
            progress.setWindowTitle("CellOnDesk download")
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setMinimumDuration(0)
            iterator = iter_download(asset, destination)
            try:
                for downloaded, total in iterator:
                    if progress.wasCanceled():
                        iterator.close()
                        self.statusBar().showMessage("Download cancelled")
                        return
                    if total:
                        percent = min(100, int(downloaded * 100 / total))
                        progress.setValue(percent)
                        progress.setLabelText(
                            f"Downloading {asset.name}: {format_bytes(downloaded)} / {format_bytes(total)}"
                        )
                    else:
                        progress.setValue(0)
                        progress.setLabelText(
                            f"Downloading {asset.name}: {format_bytes(downloaded)}"
                        )
                    QApplication.processEvents()
            except (httpx.HTTPError, OSError, ValueError) as exc:
                progress.close()
                QMessageBox.critical(self, "Download failed", str(exc))
                return
            progress.setValue(100)
            self.statusBar().showMessage(f"Downloaded {destination}")
            if asset.is_h5ad or destination.suffix.casefold() == ".h5ad":
                self._use_downloaded_h5ad(destination)
            else:
                QMessageBox.information(self, "Download complete", f"Saved:\n{destination}")

        def _use_downloaded_h5ad(self, path: Path) -> None:
            self.h5ad_path = path
            self.h5ad_file_label.setText(str(path))
            self.h5ad_inspection = None
            self.h5ad_details.clear()
            self.tabs.setCurrentIndex(3)
            answer = QMessageBox.question(
                self,
                "H5AD downloaded",
                f"Saved {path.name}. Inspect it now with bounded memory?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self.inspect_h5ad_file()

        def _no_assets(self, record: DatasetRecord, reason: str) -> None:
            message = f"{reason}\n\nOpen the source portal instead?"
            answer = QMessageBox.question(
                self,
                "No direct data product",
                message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes and record.portal_url:
                webbrowser.open(record.portal_url)

        def _set_row(self, table: QTableWidget, row: int, values: list[str]) -> None:
            for col, value in enumerate(values):
                table.setItem(row, col, QTableWidgetItem(value))

        def _show_record_details(
            self,
            table: QTableWidget,
            records: list[DatasetRecord],
            details: QTextEdit,
        ) -> None:
            rows = sorted({index.row() for index in table.selectedIndexes()})
            if rows:
                details.setPlainText(
                    json.dumps(records[rows[0]].model_dump(), indent=2, ensure_ascii=False)
                )
            else:
                details.clear()

        def choose_h5ad(self) -> None:
            filename, _ = QFileDialog.getOpenFileName(
                self, "Choose an H5AD file", "", "AnnData files (*.h5ad);;All files (*)"
            )
            if not filename:
                return
            self.h5ad_path = Path(filename)
            self.h5ad_file_label.setText(filename)
            self.h5ad_inspection = None
            self.h5ad_details.clear()

        def inspect_h5ad_file(self) -> None:
            if self.h5ad_path is None:
                QMessageBox.information(self, "No file selected", "Choose or download an H5AD first.")
                return
            try:
                self.h5ad_inspection = inspect_h5ad(
                    self.h5ad_path,
                    annotation=self.h5ad_annotation.text().strip() or None,
                    max_points=self.h5ad_max_points.value(),
                )
            except (OSError, RuntimeError, ValueError) as exc:
                QMessageBox.critical(self, "H5AD inspection failed", str(exc))
                return

            result = self.h5ad_inspection
            self.h5ad_shape_label.setText(
                f"{result.n_obs:,} observations × {result.n_vars:,} variables"
            )
            matrix = result.matrix
            matrix_text = f"{matrix.encoding}; shape {matrix.shape[0]:,} × {matrix.shape[1]:,}"
            if matrix.nnz is not None:
                matrix_text += f"; {matrix.nnz:,} non-zero"
            self.h5ad_matrix_label.setText(matrix_text)
            self.h5ad_layers_label.setText(", ".join(result.layers) or "None")
            self.h5ad_embeddings_label.setText(", ".join(result.obsm) or "None")
            self.h5ad_annotation_label.setText(result.likely_annotation or "None detected")
            self.h5ad_details.setPlainText(result.model_dump_json(indent=2))
            self.statusBar().showMessage(
                f"Inspected {result.file_name}: {len(result.embeddings)} previewable embeddings"
            )

        def _require_h5ad_inspection(self) -> H5ADInspection | None:
            if self.h5ad_inspection is None:
                QMessageBox.information(self, "Nothing to export", "Inspect an H5AD file first.")
            return self.h5ad_inspection

        def export_h5ad_html(self) -> None:
            result = self._require_h5ad_inspection()
            if result is None:
                return
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Export H5AD HTML report",
                f"{Path(result.file_name).stem}-summary.html",
                "HTML files (*.html)",
            )
            if filename:
                write_h5ad_report(result, Path(filename))

        def export_h5ad_json(self) -> None:
            result = self._require_h5ad_inspection()
            if result is None:
                return
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Export H5AD JSON inspection",
                f"{Path(result.file_name).stem}-summary.json",
                "JSON files (*.json)",
            )
            if filename:
                Path(filename).write_text(result.model_dump_json(indent=2), encoding="utf-8")

    app = QApplication(sys.argv)
    window = Window()
    window.show()
    raise SystemExit(app.exec())

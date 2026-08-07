from __future__ import annotations

import importlib.util
import json
import sys
import webbrowser
from pathlib import Path

import httpx

from .census_report import write_census_report
from .h5ad_compat import H5ADInspection, inspect_h5ad
from .h5ad_report import write_h5ad_report
from .manifest import write_hubmap_manifest
from .models import DatasetRecord
from .report import write_html_report
from .sources.census import CensusGenePreview, CensusQuery, preview_census_gene
from .sources.hubmap import SPATIAL_DATASET_TYPES, HuBMAPClient
from .sources.ucsc_cellbrowser import UCSCCellBrowserClient

CELLXGENE_DISCOVER_URL = "https://cellxgene.cziscience.com/datasets"
CELLXGENE_CENSUS_URL = "https://cellxgene.cziscience.com/census-models"


def main() -> None:
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QApplication,
            QComboBox,
            QFileDialog,
            QFormLayout,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QMainWindow,
            QMessageBox,
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
            self.resize(1320, 820)
            self.records: list[DatasetRecord] = []
            self.ucsc_records: list[DatasetRecord] = []
            self.census_preview: CensusGenePreview | None = None
            self.h5ad_inspection: H5ADInspection | None = None
            self.h5ad_path: Path | None = None

            tabs = QTabWidget()
            tabs.addTab(self._build_hubmap_tab(), "HuBMAP")
            tabs.addTab(self._build_cellxgene_tab(), "CELLxGENE")
            tabs.addTab(self._build_ucsc_tab(), "UCSC Cell Browser")
            tabs.addTab(self._build_h5ad_tab(), "Local H5AD")
            self.setCentralWidget(tabs)
            self.statusBar().showMessage("Ready")

        def _build_hubmap_tab(self) -> QWidget:
            root = QWidget()
            layout = QVBoxLayout(root)
            helper = QLabel(
                "Search published HuBMAP datasets. You can type ordinary organ names such as "
                "kidney; CellOnDesk maps them to HuBMAP organ codes."
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
            open_button = QPushButton("Open selected")
            get_data_button = QPushButton("Get data / transfer")
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
                open_button,
                get_data_button,
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
            self.details.setPlaceholderText(
                "Select a dataset to inspect normalized metadata and source metadata."
            )
            splitter.addWidget(self.table)
            splitter.addWidget(self.details)
            layout.addWidget(splitter)

            search_button.clicked.connect(self.search)
            open_button.clicked.connect(self.open_selected_hubmap)
            get_data_button.clicked.connect(self.get_hubmap_data)
            manifest_button.clicked.connect(self.export_manifest)
            report_button.clicked.connect(self.export_report)
            self.table.itemSelectionChanged.connect(self.show_details)
            self.table.itemDoubleClicked.connect(lambda _item: self.open_selected_hubmap())
            return root

        def _build_cellxgene_tab(self) -> QWidget:
            root = QWidget()
            layout = QVBoxLayout(root)
            census_available = importlib.util.find_spec("cellxgene_census") is not None
            if census_available:
                status_text = (
                    "Native CELLxGENE Census support is available in this environment. "
                    "Use the bounded gene preview below or open Discover for full dataset downloads."
                )
            else:
                status_text = (
                    "This Windows desktop package does not bundle the native CELLxGENE Census/SOMA "
                    "stack. Dataset discovery and download remain available through CELLxGENE Discover; "
                    "download an H5AD there and inspect it in the Local H5AD tab."
                )
            status = QLabel(status_text)
            status.setWordWrap(True)
            layout.addWidget(status)

            portal_controls = QHBoxLayout()
            discover_button = QPushButton("Open CELLxGENE Discover")
            census_button = QPushButton("Open Census documentation")
            portal_controls.addWidget(discover_button)
            portal_controls.addWidget(census_button)
            portal_controls.addStretch(1)
            layout.addLayout(portal_controls)

            query = QWidget()
            query_form = QFormLayout(query)
            self.census_gene = QLineEdit()
            self.census_gene.setPlaceholderText("Gene, e.g. CD3D")
            self.census_tissue = QLineEdit()
            self.census_tissue.setPlaceholderText("Optional tissue, e.g. kidney")
            self.census_cell_type = QLineEdit()
            self.census_cell_type.setPlaceholderText("Optional exact cell type")
            self.census_max_cells = QSpinBox()
            self.census_max_cells.setRange(100, 50000)
            self.census_max_cells.setValue(5000)
            query_form.addRow("Gene", self.census_gene)
            query_form.addRow("Tissue", self.census_tissue)
            query_form.addRow("Cell type", self.census_cell_type)
            query_form.addRow("Max cells", self.census_max_cells)
            layout.addWidget(query)

            census_controls = QHBoxLayout()
            preview_button = QPushButton("Run bounded Census preview")
            export_button = QPushButton("Export Census HTML")
            preview_button.setEnabled(census_available)
            export_button.setEnabled(census_available)
            census_controls.addWidget(preview_button)
            census_controls.addWidget(export_button)
            census_controls.addStretch(1)
            layout.addLayout(census_controls)

            self.census_details = QTextEdit()
            self.census_details.setReadOnly(True)
            self.census_details.setPlaceholderText(
                "Census preview statistics, provenance and warnings will appear here when the "
                "optional native Census dependency is available."
            )
            layout.addWidget(self.census_details)

            discover_button.clicked.connect(lambda: webbrowser.open(CELLXGENE_DISCOVER_URL))
            census_button.clicked.connect(lambda: webbrowser.open(CELLXGENE_CENSUS_URL))
            preview_button.clicked.connect(self.run_census_preview)
            export_button.clicked.connect(self.export_census_html)
            return root

        def _build_ucsc_tab(self) -> QWidget:
            root = QWidget()
            layout = QVBoxLayout(root)
            helper = QLabel(
                "Search the UCSC Cell Browser public catalog. Search text can match collection, "
                "project, assay or other catalog metadata; organ accepts ordinary names such as kidney."
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
            open_button = QPushButton("Open / download selected")
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
                open_button,
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
            open_button.clicked.connect(self.open_selected_ucsc)
            self.ucsc_table.itemSelectionChanged.connect(self.show_ucsc_details)
            self.ucsc_table.itemDoubleClicked.connect(lambda _item: self.open_selected_ucsc())
            return root

        def _build_h5ad_tab(self) -> QWidget:
            root = QWidget()
            layout = QVBoxLayout(root)
            controls = QHBoxLayout()
            self.h5ad_file_label = QLineEdit()
            self.h5ad_file_label.setReadOnly(True)
            self.h5ad_file_label.setPlaceholderText("Choose a local .h5ad file")
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
            self.h5ad_details.setPlaceholderText(
                "Bounded structural inspection results and warnings will appear here."
            )
            layout.addWidget(self.h5ad_details)

            choose_button.clicked.connect(self.choose_h5ad)
            inspect_button.clicked.connect(self.inspect_h5ad_file)
            html_button.clicked.connect(self.export_h5ad_html)
            json_button.clicked.connect(self.export_h5ad_json)
            return root

        def search(self) -> None:
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
                values = [
                    record.dataset_id,
                    record.dataset_type or "",
                    record.organ or "",
                    record.status or "",
                    record.access_level or "Not reported",
                    record.title,
                ]
                for col, value in enumerate(values):
                    self.table.setItem(row, col, QTableWidgetItem(value))
            self.table.resizeColumnsToContents()
            if self.records:
                self.statusBar().showMessage(f"Found {len(self.records)} HuBMAP datasets")
            else:
                self.statusBar().showMessage(
                    "No HuBMAP matches. This can mean the portal uses a different assay label, "
                    "or no published datasets match the filters."
                )

        def selected_records(self) -> list[DatasetRecord]:
            rows = sorted({index.row() for index in self.table.selectedIndexes()})
            return [self.records[row] for row in rows] if rows else self.records

        def _selected_hubmap_record(self) -> DatasetRecord | None:
            rows = sorted({index.row() for index in self.table.selectedIndexes()})
            if not rows:
                QMessageBox.information(self, "No dataset selected", "Select a HuBMAP row first.")
                return None
            return self.records[rows[0]]

        def open_selected_hubmap(self) -> None:
            record = self._selected_hubmap_record()
            if record and record.portal_url:
                webbrowser.open(record.portal_url)

        def get_hubmap_data(self) -> None:
            record = self._selected_hubmap_record()
            if record is None:
                return
            access = (record.access_level or "not reported").lower()
            message = (
                f"Access level reported by HuBMAP: {record.access_level or 'not reported'}.\n\n"
                "CellOnDesk will open the dataset page where HuBMAP shows the current download or "
                "transfer options. The CLT manifest export is for command-line transfer workflows; "
                "it is not itself a downloaded dataset."
            )
            if access == "protected":
                message += "\n\nThis record is protected and may require authorization."
            QMessageBox.information(self, "HuBMAP data access", message)
            if record.portal_url:
                webbrowser.open(record.portal_url)

        def export_manifest(self) -> None:
            if not self.records:
                QMessageBox.information(self, "Nothing to export", "Run a search first.")
                return
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Export HuBMAP CLT manifest",
                "hubmap-manifest.txt",
                "Text files (*.txt)",
            )
            if filename:
                write_hubmap_manifest(self.selected_records(), Path(filename))
                self.statusBar().showMessage(f"Wrote {filename}")

        def export_report(self) -> None:
            if not self.records:
                QMessageBox.information(self, "Nothing to export", "Run a search first.")
                return
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Export CellOnDesk HTML summary",
                "web_summary.html",
                "HTML files (*.html)",
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

        def show_details(self) -> None:
            rows = sorted({index.row() for index in self.table.selectedIndexes()})
            if rows:
                self.details.setPlainText(
                    json.dumps(
                        self.records[rows[0]].model_dump(),
                        indent=2,
                        ensure_ascii=False,
                    )
                )
            else:
                self.details.clear()

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
            self.statusBar().showMessage(
                f"CELLxGENE Census: {self.census_preview.sampled_cells:,} sampled cells"
            )

        def export_census_html(self) -> None:
            if self.census_preview is None:
                QMessageBox.information(
                    self, "Nothing to export", "Run a CELLxGENE Census preview first."
                )
                return
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Export CELLxGENE Census HTML",
                "cellxgene-census-summary.html",
                "HTML files (*.html)",
            )
            if filename:
                write_census_report(self.census_preview, Path(filename))
                self.statusBar().showMessage(f"Wrote {filename}")

        def search_ucsc(self) -> None:
            if not any(
                (
                    self.ucsc_query.text().strip(),
                    self.ucsc_organ.text().strip(),
                    self.ucsc_organism.text().strip(),
                )
            ):
                QMessageBox.information(
                    self,
                    "Add a filter",
                    "Enter a keyword, organ or organism to avoid downloading the entire UCSC catalog.",
                )
                return
            try:
                with UCSCCellBrowserClient() as client:
                    self.ucsc_records = client.search_datasets(
                        query=self.ucsc_query.text().strip() or None,
                        organ=self.ucsc_organ.text().strip() or None,
                        organism=self.ucsc_organism.text().strip() or None,
                        limit=self.ucsc_limit.value(),
                    )
            except (httpx.HTTPError, ValueError) as exc:
                QMessageBox.critical(self, "UCSC Cell Browser search failed", str(exc))
                return
            self.ucsc_table.setRowCount(len(self.ucsc_records))
            for row, record in enumerate(self.ucsc_records):
                values = [
                    record.dataset_id,
                    record.dataset_type or "",
                    record.organ or "",
                    record.access_level or "public",
                    record.title,
                ]
                for col, value in enumerate(values):
                    self.ucsc_table.setItem(row, col, QTableWidgetItem(value))
            self.ucsc_table.resizeColumnsToContents()
            self.statusBar().showMessage(
                f"Found {len(self.ucsc_records)} UCSC Cell Browser datasets"
            )

        def _selected_ucsc_record(self) -> DatasetRecord | None:
            rows = sorted({index.row() for index in self.ucsc_table.selectedIndexes()})
            if not rows:
                QMessageBox.information(self, "No dataset selected", "Select a UCSC row first.")
                return None
            return self.ucsc_records[rows[0]]

        def open_selected_ucsc(self) -> None:
            record = self._selected_ucsc_record()
            if record is None:
                return
            QMessageBox.information(
                self,
                "UCSC data access",
                "The UCSC Cell Browser page provides an Info & Download/Data Download panel with "
                "the matrix, metadata and coordinate files available for that dataset.",
            )
            if record.portal_url:
                webbrowser.open(record.portal_url)

        def show_ucsc_details(self) -> None:
            rows = sorted({index.row() for index in self.ucsc_table.selectedIndexes()})
            if rows:
                self.ucsc_details.setPlainText(
                    json.dumps(
                        self.ucsc_records[rows[0]].model_dump(),
                        indent=2,
                        ensure_ascii=False,
                    )
                )
            else:
                self.ucsc_details.clear()

        def choose_h5ad(self) -> None:
            filename, _ = QFileDialog.getOpenFileName(
                self,
                "Choose an H5AD file",
                "",
                "AnnData files (*.h5ad);;All files (*)",
            )
            if not filename:
                return
            self.h5ad_path = Path(filename)
            self.h5ad_file_label.setText(filename)
            self.h5ad_inspection = None
            self.h5ad_details.clear()
            self.statusBar().showMessage(f"Selected {self.h5ad_path.name}")

        def inspect_h5ad_file(self) -> None:
            if self.h5ad_path is None:
                QMessageBox.information(self, "No file selected", "Choose an H5AD file first.")
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
                QMessageBox.information(
                    self,
                    "Nothing to export",
                    "Choose and inspect an H5AD file first.",
                )
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
                self.statusBar().showMessage(f"Wrote {filename}")

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
                self.statusBar().showMessage(f"Wrote {filename}")

    app = QApplication(sys.argv)
    window = Window()
    window.show()
    raise SystemExit(app.exec())

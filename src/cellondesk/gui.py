from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

from .h5ad_compat import H5ADInspection, inspect_h5ad
from .h5ad_report import write_h5ad_report
from .manifest import write_hubmap_manifest
from .models import DatasetRecord
from .report import write_html_report
from .sources.hubmap import SPATIAL_DATASET_TYPES, HuBMAPClient


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
            QTabWidget,
            QTableWidget,
            QTableWidgetItem,
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
            self.resize(1220, 780)
            self.records: list[DatasetRecord] = []
            self.h5ad_inspection: H5ADInspection | None = None
            self.h5ad_path: Path | None = None

            tabs = QTabWidget()
            tabs.addTab(self._build_hubmap_tab(), "HuBMAP search")
            tabs.addTab(self._build_h5ad_tab(), "Local H5AD")
            self.setCentralWidget(tabs)
            self.statusBar().showMessage("Ready")

        def _build_hubmap_tab(self) -> QWidget:
            root = QWidget()
            layout = QVBoxLayout(root)
            controls = QHBoxLayout()
            self.dataset_type = QComboBox()
            self.dataset_type.setEditable(True)
            self.dataset_type.addItem("")
            self.dataset_type.addItems(SPATIAL_DATASET_TYPES)
            self.organ = QLineEdit()
            self.organ.setPlaceholderText("Organ code, e.g. LK")
            self.limit = QSpinBox()
            self.limit.setRange(1, 1000)
            self.limit.setValue(50)
            search_button = QPushButton("Search HuBMAP")
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
                manifest_button,
                report_button,
            ):
                controls.addWidget(widget)
            layout.addLayout(controls)

            splitter = QSplitter(Qt.Orientation.Vertical)
            self.table = QTableWidget(0, 5)
            self.table.setHorizontalHeaderLabels(
                ["HuBMAP ID", "Type", "Organ", "Status", "Title"]
            )
            self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
            self.details = QTextEdit()
            self.details.setReadOnly(True)
            splitter.addWidget(self.table)
            splitter.addWidget(self.details)
            layout.addWidget(splitter)

            search_button.clicked.connect(self.search)
            manifest_button.clicked.connect(self.export_manifest)
            report_button.clicked.connect(self.export_report)
            self.table.itemSelectionChanged.connect(self.show_details)
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
                    record.title,
                ]
                for col, value in enumerate(values):
                    self.table.setItem(row, col, QTableWidgetItem(value))
            self.table.resizeColumnsToContents()
            self.statusBar().showMessage(f"Found {len(self.records)} datasets")

        def selected_records(self) -> list[DatasetRecord]:
            rows = sorted({index.row() for index in self.table.selectedIndexes()})
            return [self.records[row] for row in rows] if rows else self.records

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
            self.h5ad_shape_label.setText(f"{result.n_obs:,} observations × {result.n_vars:,} variables")
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

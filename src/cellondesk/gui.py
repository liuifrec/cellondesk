from __future__ import annotations

import json
import sys
from pathlib import Path

from .manifest import write_hubmap_manifest
from .models import DatasetRecord
from .report import write_html_report
from .sources.hubmap import HuBMAPClient, SPATIAL_DATASET_TYPES


def main() -> None:
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QApplication, QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
            QMainWindow, QMessageBox, QPushButton, QSpinBox, QSplitter, QTableWidget,
            QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
        )
    except ImportError as exc:
        raise SystemExit('Install GUI dependencies with: pip install "cellondesk[gui]"') from exc

    class Window(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("CellOnDesk - HuBMAP spatial search")
            self.resize(1200, 760)
            self.records: list[DatasetRecord] = []
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
                QLabel("Assay"), self.dataset_type, QLabel("Organ"), self.organ,
                QLabel("Limit"), self.limit, search_button, manifest_button, report_button,
            ):
                controls.addWidget(widget)
            layout.addLayout(controls)
            splitter = QSplitter(Qt.Orientation.Vertical)
            self.table = QTableWidget(0, 5)
            self.table.setHorizontalHeaderLabels(["HuBMAP ID", "Type", "Organ", "Status", "Title"])
            self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
            self.details = QTextEdit()
            self.details.setReadOnly(True)
            splitter.addWidget(self.table)
            splitter.addWidget(self.details)
            layout.addWidget(splitter)
            self.setCentralWidget(root)
            search_button.clicked.connect(self.search)
            manifest_button.clicked.connect(self.export_manifest)
            report_button.clicked.connect(self.export_report)
            self.table.itemSelectionChanged.connect(self.show_details)

        def search(self) -> None:
            try:
                with HuBMAPClient() as client:
                    self.records = client.search_datasets(
                        dataset_type=self.dataset_type.currentText().strip() or None,
                        organ=self.organ.text().strip() or None,
                        status="Published",
                        limit=self.limit.value(),
                    )
            except Exception as exc:
                QMessageBox.critical(self, "HuBMAP search failed", str(exc))
                return
            self.table.setRowCount(len(self.records))
            for row, record in enumerate(self.records):
                values = [record.dataset_id, record.dataset_type or "", record.organ or "",
                          record.status or "", record.title]
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
                self, "Export HuBMAP CLT manifest", "hubmap-manifest.txt", "Text files (*.txt)")
            if filename:
                write_hubmap_manifest(self.selected_records(), Path(filename))
                self.statusBar().showMessage(f"Wrote {filename}")

        def export_report(self) -> None:
            if not self.records:
                QMessageBox.information(self, "Nothing to export", "Run a search first.")
                return
            filename, _ = QFileDialog.getSaveFileName(
                self, "Export CellOnDesk HTML summary", "web_summary.html", "HTML files (*.html)")
            if filename:
                write_html_report(
                    self.selected_records(), Path(filename),
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
                self.details.setPlainText(json.dumps(
                    self.records[rows[0]].model_dump(), indent=2, ensure_ascii=False))
            else:
                self.details.clear()

    app = QApplication(sys.argv)
    window = Window()
    window.show()
    raise SystemExit(app.exec())

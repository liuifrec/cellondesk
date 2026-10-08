"""Qt discovery workspace. Adapters and orchestration remain independently testable."""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
    QThread,
    Signal,
    Slot,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from .discovery import SOURCES, DiscoveryService, SearchQuery, SourceOutcome, access_summary
from .models import DatasetRecord

COLUMNS = (
    "Source",
    "Title",
    "Tissue / organ",
    "Assay",
    "Organism",
    "Reported cells / obs.",
    "Publication",
    "Access / files",
    "Acquisition",
)


def _key(record: DatasetRecord) -> tuple[str, str]:
    return record.source, record.dataset_id


def _values(record: DatasetRecord) -> tuple:
    return (
        record.source,
        record.title,
        record.organ,
        record.dataset_type,
        record.organism,
        record.reported_cell_count,
        record.status,
        access_summary(record),
        "; ".join(record.acquisition_methods) or "Not yet checked",
    )


class ResultModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.records: list[DatasetRecord] = []

    def rowCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self.records)

    def columnCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return COLUMNS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        record = self.records[index.row()]
        value = _values(record)[index.column()]
        if role == Qt.ItemDataRole.UserRole:
            return (
                (value if value is not None else -1)
                if index.column() == 5
                else str(value or "").casefold()
            )
        if role == Qt.ItemDataRole.DisplayRole:
            return f"{value:,}" if isinstance(value, int) else (value or "Not reported")
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{record.dataset_id}\n{record.cell_count_basis or 'No cell count reported'}"
        return None

    def replace(self, records: list[DatasetRecord]):
        self.beginResetModel()
        self.records = records
        self.endResetModel()


class ResultProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.text = ""
        self.source = ""
        self.availability = ""
        self.setSortRole(Qt.ItemDataRole.UserRole)

    def filterAcceptsRow(self, row, parent):
        record = self.sourceModel().records[row]
        if self.source and record.source != self.source:
            return False
        if self.availability and record.asset_status != self.availability:
            return False
        haystack = " ".join(
            str(value or "") for value in (*_values(record), record.dataset_id)
        ).casefold()
        return self.text.casefold() in haystack


class SearchWorker(QThread):
    source_ready = Signal(object)
    failed = Signal(str)

    def __init__(self, service: DiscoveryService, query: SearchQuery, parent=None):
        super().__init__(parent)
        self.service, self.query = service, query
        self.cancelled = threading.Event()

    def run(self):
        try:
            self.service.search(
                self.query, cancelled=self.cancelled.is_set, on_source=self.source_ready.emit
            )
        except Exception as exc:  # noqa: BLE001 - never let a worker exception abort Qt
            self.failed.emit(str(exc))


class DiscoveryWidget(QWidget):
    resolve_requested = Signal(object)
    manifest_requested = Signal(object)
    portal_requested = Signal(object)

    def __init__(self, parent=None, *, service: DiscoveryService | None = None):
        super().__init__(parent)
        self.service = service or DiscoveryService()
        self.worker: SearchWorker | None = None
        self._search_active = False
        self.outcomes: dict[str, SourceOutcome] = {}
        self._changing = False
        layout = QVBoxLayout(self)
        heading = QLabel("Discover scientific datasets")
        heading.setStyleSheet("font-size: 22px; font-weight: 600; margin: 8px 0;")
        layout.addWidget(heading)
        hint = QLabel(
            "Search repository metadata together. Counts are source-reported observations, "
            "not donors or biological replicates. Advanced source tabs and Local H5AD remain available."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        form = QHBoxLayout()
        self.inputs = {}
        for name, label in (
            ("keyword", "Keyword"),
            ("tissue", "Tissue / organ"),
            ("organism", "Organism"),
            ("assay", "Assay"),
        ):
            group = QFormLayout()
            edit = QLineEdit()
            edit.setPlaceholderText(
                {
                    "tissue": "e.g. kidney",
                    "organism": "e.g. human",
                    "assay": "e.g. RNAseq",
                    "keyword": "Title or source ID",
                }[name]
            )
            edit.returnPressed.connect(self.start_search)
            self.inputs[name] = edit
            group.addRow(label, edit)
            form.addLayout(group)
        layout.addLayout(form)
        controls = QHBoxLayout()
        self.sources = {}
        for key, name in SOURCES.items():
            box = QCheckBox(name)
            box.setChecked(True)
            self.sources[key] = box
            controls.addWidget(box)
        controls.addStretch()
        controls.addWidget(QLabel("Limit per source"))
        self.limit = QSpinBox()
        self.limit.setRange(1, 500)
        self.limit.setValue(100)
        controls.addWidget(self.limit)
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.start_search)
        controls.addWidget(self.search_button)
        self.refresh_button = QPushButton("Refresh catalogs + search")
        self.refresh_button.setToolTip(
            "Revalidate CELLxGENE and UCSC public metadata, even within the 24-hour cache TTL."
        )
        self.refresh_button.clicked.connect(lambda: self.start_search(refresh=True))
        controls.addWidget(self.refresh_button)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_search)
        controls.addWidget(self.cancel_button)
        layout.addLayout(controls)
        advanced_toggle = QCheckBox("Optional advanced filters")
        layout.addWidget(advanced_toggle)
        self.advanced = QGroupBox("Source-specific filters (only apply to the named source)")
        advanced_layout = QFormLayout(self.advanced)
        self.disease, self.cell_type = QLineEdit(), QLineEdit()
        self.hubmap_status = QComboBox()
        self.hubmap_status.addItems(
            ["Published", "QA", "New", "Processing", "All reported statuses"]
        )
        advanced_layout.addRow("CELLxGENE disease", self.disease)
        advanced_layout.addRow("CELLxGENE cell type", self.cell_type)
        advanced_layout.addRow("HuBMAP publication status", self.hubmap_status)
        layout.addWidget(self.advanced)
        self.advanced.hide()
        # Collapsing never leaves invisible active filters.
        advanced_toggle.toggled.connect(self.advanced.setVisible)
        self.advanced_toggle = advanced_toggle
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(5)
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.query_label = QLabel("No search run yet")
        self.query_label.setTextFormat(Qt.TextFormat.PlainText)
        self.query_label.setWordWrap(True)
        layout.addWidget(self.query_label)
        self.status_labels = {}
        for key, name in SOURCES.items():
            label = QLabel(f"{name}: ready")
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.PlainText)
            self.status_labels[key] = label
            layout.addWidget(label)
        local = QHBoxLayout()
        local.addWidget(QLabel("Filter displayed results"))
        self.local_text = QLineEdit()
        self.local_text.setPlaceholderText("Local text filter · no network request")
        local.addWidget(self.local_text)
        self.local_source = QComboBox()
        self.local_source.addItem("All sources", "")
        for name in SOURCES.values():
            self.local_source.addItem(name, name)
        local.addWidget(self.local_source)
        self.local_availability = QComboBox()
        for label, value in (
            ("All file states", ""),
            ("Not checked", "not_checked"),
            ("Advertised", "advertised"),
            ("Direct verified", "verified"),
            ("Transfer only", "transfer_only"),
            ("No direct file found", "checked_no_direct"),
        ):
            self.local_availability.addItem(label, value)
        local.addWidget(self.local_availability)
        layout.addLayout(local)
        self.model = ResultModel(self)
        self.proxy = ResultProxy(self)
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for column, width in enumerate((150, 290, 125, 130, 150, 155, 105, 300, 190)):
            self.table.setColumnWidth(column, width)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText(
            "Select a result to inspect its identifier, access state and original metadata."
        )
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.table)
        splitter.addWidget(self.details)
        splitter.setSizes([400, 180])
        layout.addWidget(splitter, 1)
        actions = QHBoxLayout()
        self.count_label = QLabel("0 displayed")
        actions.addWidget(self.count_label)
        actions.addStretch()
        self.portal_button = QPushButton("Open repository")
        self.resolve_button = QPushButton("Find files for selected dataset")
        self.manifest_button = QPushButton("Export selected HuBMAP CLT manifest")
        for button in (self.portal_button, self.resolve_button, self.manifest_button):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.portal_button.clicked.connect(lambda: self._emit_selected(self.portal_requested))
        self.resolve_button.clicked.connect(lambda: self._emit_selected(self.resolve_requested))
        self.manifest_button.clicked.connect(lambda: self._emit_selected(self.manifest_requested))
        self.local_text.textChanged.connect(self.filter_results)
        self.local_source.currentIndexChanged.connect(self.filter_results)
        self.local_availability.currentIndexChanged.connect(self.filter_results)
        self.table.selectionModel().selectionChanged.connect(self.show_details)
        self.show_details()

    def selected_record(self) -> DatasetRecord | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        index = self.proxy.mapToSource(rows[0])
        return self.model.records[index.row()] if index.isValid() else None

    def _emit_selected(self, signal):
        record = self.selected_record()
        if record:
            signal.emit(record)

    def show_details(self, *_):
        if self._changing:
            return
        record = self.selected_record()
        self.portal_button.setEnabled(bool(record and record.portal_url))
        self.resolve_button.setEnabled(record is not None)
        self.manifest_button.setEnabled(
            bool(
                record
                and record.source == "HuBMAP"
                and (record.raw.get("hubmap_id") or record.dataset_id.startswith("HBM"))
            )
        )
        if record is None:
            self.details.clear()
            return
        fetched = record.provenance.get("fetched_at")
        timestamp = (
            datetime.fromtimestamp(fetched, timezone.utc).isoformat() if fetched else "Not reported"
        )
        text = (
            f"{record.title}\n{record.source} · {record.dataset_id}\n"
            f"Publication: {record.status or 'Not reported'}\n{access_summary(record)}\n"
            f"Acquisition: {'; '.join(record.acquisition_methods) or 'Not yet checked'}\n"
            f"Count basis: {record.cell_count_basis or 'No cell count reported'}\n"
            f"Metadata fetched: {timestamp}\n\nOriginal metadata and provenance:\n"
        )
        payload = record.model_dump_json(indent=2)
        if len(payload) > 100000:
            payload = (
                payload[:100000]
                + "\n[Detail display truncated; complete metadata retained in result.]"
            )
        self.details.setPlainText(text + payload)

    def _restore(self, key):
        self.table.clearSelection()
        self.table.setCurrentIndex(QModelIndex())
        if key:
            for row, record in enumerate(self.model.records):
                if _key(record) == key:
                    index = self.proxy.mapFromSource(self.model.index(row, 0))
                    if index.isValid():
                        self.table.selectRow(index.row())
                    break
        self._changing = False
        self.show_details()
        self.count_label.setText(
            f"{self.proxy.rowCount()} displayed / {self.model.rowCount()} returned · limits may apply"
        )

    def set_records(self, records):
        selected = self.selected_record()
        self._changing = True
        self.model.replace(records)
        self._restore(_key(selected) if selected else None)

    def filter_results(self, *_):
        selected = self.selected_record()
        self._changing = True
        self.proxy.text = self.local_text.text()
        self.proxy.source = self.local_source.currentData()
        self.proxy.availability = self.local_availability.currentData()
        self.proxy.invalidate()
        self._restore(_key(selected) if selected else None)

    def start_search(self, _checked=False, *, refresh=False):
        # Wait for queued outcomes AND finished(), not merely the native thread,
        # before allowing Return/another click to start a new query.
        if self._search_active:
            return
        self._search_active = True
        sources = tuple(key for key, box in self.sources.items() if box.isChecked())
        filters = {name: edit.text().strip() for name, edit in self.inputs.items()}
        advanced = self.advanced_toggle.isChecked()
        query = SearchQuery(
            **filters,
            sources=sources,
            limit=self.limit.value(),
            refresh=refresh,
            disease=self.disease.text().strip() if advanced else "",
            cell_type=self.cell_type.text().strip() if advanced else "",
            hubmap_status=(
                self.hubmap_status.currentText() if self.hubmap_status.currentIndex() != 4 else ""
            )
            if advanced
            else "Published",
        )
        summary = [f"{name}: {value}" for name, value in filters.items() if value]
        if query.disease:
            summary.append(f"CELLxGENE disease: {query.disease}")
        if query.cell_type:
            summary.append(f"CELLxGENE cell type: {query.cell_type}")
        self.query_label.setText("Results for submitted query — " + "; ".join(summary))
        self.outcomes.clear()
        self.set_records([])
        for key, label in self.status_labels.items():
            label.setText(
                f"{SOURCES[key]}: {'loading metadata…' if key in sources else 'not selected'}"
            )
        self.search_button.setEnabled(False)
        self.refresh_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.show()
        if self.worker is not None:
            self.worker.deleteLater()
        self.worker = SearchWorker(self.service, query, self)
        self.worker.source_ready.connect(self.accept_outcome)
        self.worker.failed.connect(self.search_failed)
        self.worker.finished.connect(self.search_finished)
        self.worker.start()

    @Slot(object)
    def accept_outcome(self, outcome: SourceOutcome):
        self.outcomes[outcome.source] = outcome
        stats = outcome.stats
        if outcome.error:
            state = f"ERROR — {outcome.error}"
        else:
            scope = "catalog/query traversal complete" if stats.complete else "PARTIAL coverage"
            state = f"{stats.returned} returned / {stats.matched} matched / {stats.scanned} inspected; {scope}"
            if stats.truncated:
                state += "; display limit applied"
        state += (
            f" · {outcome.elapsed_seconds:.2f}s · {stats.cache_hits} cache hits / "
            f"{stats.requests} requests / {stats.revalidated} revalidated"
        )
        notices = [*stats.warnings, *outcome.notices]
        if notices:
            state += "\n" + notices[0][:500]
            if len(notices) > 1:
                state += f" (+{len(notices) - 1} more notices; hover for details)"
        self.status_labels[outcome.source].setToolTip("\n".join(notices))
        self.status_labels[outcome.source].setText(f"{SOURCES[outcome.source]}: {state}")
        self.set_records(
            [
                record
                for source in SOURCES
                if source in self.outcomes
                for record in self.outcomes[source].records
            ]
        )

    @Slot(str)
    def search_failed(self, message):
        for label in self.status_labels.values():
            if "loading metadata" in label.text():
                label.setText(message)
        self.count_label.setText(message)

    @Slot()
    def search_finished(self):
        self._search_active = False
        self.progress.hide()
        self.search_button.setEnabled(True)
        self.refresh_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    def cancel_search(self):
        if self.worker:
            self.worker.cancelled.set()
            self.cancel_button.setEnabled(False)
            self.count_label.setText("Cancelling after the current bounded metadata request…")

    def shutdown(self):
        # Keep the parent alive until the bounded source jobs have exited.
        if self.worker and self.worker.isRunning():
            self.worker.cancelled.set()
            self.worker.wait()

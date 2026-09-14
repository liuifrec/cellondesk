"""Run blocking work outside Qt's GUI thread with a modal progress view.

Only plain Python values cross the thread boundary. The worker owns its network
clients and HDF5 handles. Qt widgets are read/updated exclusively on the GUI
thread; the modal view prevents a second operation from changing its inputs.
"""
from __future__ import annotations

from collections.abc import Callable
from threading import Event
from typing import Any, TypeVar

from .assets import format_bytes

T = TypeVar("T")
Progress = Callable[[int, int | None], None]


def run_task(
    parent: Any,
    title: str,
    operation: Callable[[Callable[[], bool], Progress], T],
    *,
    cancellable: bool = False,
) -> T:
    from PySide6.QtCore import Qt, QThread, QTimer, Signal
    from PySide6.QtWidgets import QDialog, QLabel, QProgressBar, QPushButton, QVBoxLayout

    cancelled = Event()

    class Worker(QThread):
        progress = Signal(object, object)  # Python integers, including files >2 GB.

        def run(self) -> None:
            try:
                self.result = operation(cancelled.is_set, self.progress.emit)
            except Exception as exc:  # noqa: BLE001 - re-raised on the calling GUI thread
                self.error = exc

    class ProgressView(QDialog):
        def reject(self) -> None:
            # Never destroy a running QThread or leave its transfer unattended.
            if cancellable:
                cancelled.set()
                label.setText("Cancelling; waiting for the current I/O operation to return...")
                cancel.setEnabled(False)

    dialog = ProgressView(parent)
    dialog.setWindowTitle(title)
    dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
    dialog.resize(460, 130)
    layout = QVBoxLayout(dialog)
    label = QLabel(title)
    label.setWordWrap(True)
    layout.addWidget(label)
    bar = QProgressBar()
    bar.setRange(0, 0)
    layout.addWidget(bar)
    cancel = QPushButton("Cancel")
    cancel.setVisible(cancellable)
    cancel.clicked.connect(dialog.reject)
    layout.addWidget(cancel)
    worker = Worker(dialog)
    worker.result = None
    worker.error = None

    def update_progress(done: int, total: int | None) -> None:
        if cancelled.is_set():
            return
        if total:
            bar.setRange(0, 100)
            # 100% is reserved for validation and atomic finalization.
            bar.setValue(min(99, int(done * 100 / total)))
            label.setText(f"{format_bytes(done)} / {format_bytes(total)}")
        else:
            label.setText(f"{format_bytes(done)} downloaded")

    worker.progress.connect(update_progress, Qt.ConnectionType.QueuedConnection)
    worker.finished.connect(dialog.accept)
    QTimer.singleShot(0, worker.start)
    dialog.exec()
    worker.wait()
    result, error = worker.result, worker.error
    dialog.deleteLater()
    if error is not None:
        raise error
    return result


def run_read_task(parent: Any, title: str, operation: Callable[[], T]) -> T:
    """Run one bounded read; no misleading cancellation of non-cooperative I/O."""
    return run_task(parent, title, lambda _cancelled, _progress: operation())

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6.QtCore import QThread, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cellondesk.desktop_tasks import run_read_task, run_task  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_read_runs_off_gui_thread_and_gui_keeps_processing_events(app):
    ticks = []
    timer = QTimer()
    timer.setInterval(2)
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start()

    def operation():
        assert QThread.currentThread() != app.thread()
        time.sleep(0.05)
        return 42

    assert run_read_task(None, "Test read", operation) == 42
    timer.stop()
    assert ticks


def test_worker_error_reaches_caller_without_aborting_gui(app):
    def operation():
        raise ValueError("bad remote response")

    with pytest.raises(ValueError, match="bad remote response"):
        run_read_task(None, "Test error", operation)


def test_large_download_progress_preserves_python_integers(app):
    def operation(cancelled, progress):
        progress(4 * 1024**3, 9 * 1024**3)
        return "done"

    assert run_task(None, "Test progress", operation, cancellable=True) == "done"

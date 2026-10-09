"""Measure the actual desktop inspection/export slots against a local scientific file.

Run each case in a fresh process. Inputs are read-only; screenshots, timings and
the report go under --output-dir. No network or automatic downloads. Linux peak
RSS includes Qt, validation and rendering; source hashing warms filesystem caches.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import traceback
from pathlib import Path
from unittest.mock import patch


def checksum(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_values(source, result, np, h5py):
    """Compare bounded previews with native values; never materialize full X."""
    checked = 0
    with h5py.File(source, "r") as handle:
        for preview in result.scientific.feature_previews:
            matrix = handle[preview.matrix_path]
            assert len(preview.values) == len(preview.row_indices) <= 256
            if isinstance(matrix, h5py.Dataset):
                expected = matrix[preview.row_indices, preview.feature_index].astype(float)
            else:
                encoding = matrix.attrs.get("encoding-type")
                assert encoding in {"csr_matrix", "csc_matrix"}
                expected = np.zeros(len(preview.row_indices))
                scanned = 0
                major_indices = (
                    preview.row_indices if encoding == "csr_matrix" else [preview.feature_index]
                )
                for position, major in enumerate(major_indices):
                    start, stop = map(int, matrix["indptr"][major : major + 2])
                    scanned += stop - start
                    assert scanned <= 2_000_000, "Verification exceeds sparse scan budget"
                    for offset in range(start, stop, 16384):
                        end = min(stop, offset + 16384)
                        indices = matrix["indices"][offset:end]
                        values = matrix["data"][offset:end].astype(float)
                        if encoding == "csr_matrix":
                            expected[position] += values[indices == preview.feature_index].sum()
                        else:
                            for row_position, row in enumerate(preview.row_indices):
                                expected[row_position] += values[indices == row].sum()
            actual = np.asarray([np.nan if v is None else v for v in preview.values])
            expected[~np.isfinite(expected)] = np.nan
            np.testing.assert_allclose(actual, expected, equal_nan=True)
            checked += len(actual)
        for preview in result.scientific.spatial_previews:
            expected = handle[preview.path][preview.row_indices, :2]
            np.testing.assert_allclose(preview.points, expected)
            assert np.isfinite(expected).all()
        if result.obs_sample:
            assert len(result.obs_sample.row_indices) <= 20000
            assert result.obs_sample.total_rows == result.n_obs
        for check in result.scientific.correspondence:
            assert check.checked <= 4096
            if check.checked < check.total:
                assert check.state != "verified"
        assert all(
            c.state != "available"
            for c in result.scientific.capabilities
            if c.key in {"joint_views", "image_overlay", "neighborhoods"}
        )
    return checked


def browser_check(report_path, directory, executable):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        context = browser.new_context(offline=True, viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        errors, requests = [], []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on(
            "request",
            lambda r: requests.append(r.url) if r.url.startswith(("http:", "https:")) else None,
        )
        start = time.perf_counter()
        page.goto(report_path.resolve().as_uri())
        loaded = time.perf_counter() - start
        timings = {}
        for tab in (
            "Embeddings",
            "Observation composition",
            "QC & metadata",
            "Scientific modules",
            "Provenance",
        ):
            start = time.perf_counter()
            page.get_by_role("tab", name=tab, exact=True).click()
            timings[tab] = time.perf_counter() - start
            if tab in {"Embeddings", "Scientific modules"}:
                page.screenshot(
                    path=str(directory / ("browser-" + tab.split()[0].lower() + ".png")),
                    full_page=True,
                )
        assert not errors, errors
        assert not requests, requests
        context.close()
        browser.close()
        return {
            "offline_load_seconds": loaded,
            "tab_seconds": timings,
            "http_requests": len(requests),
            "javascript_errors": errors,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-url")
    parser.add_argument("--expected-sha256")
    parser.add_argument("--expected-shape", nargs=2, type=int)
    parser.add_argument("--browser-executable")
    args = parser.parse_args()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import h5py
    import numpy as np
    from PySide6.QtCore import QThread, QTimer
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

    from cellondesk import gui

    args.output_dir.mkdir(parents=True, exist_ok=True)
    digest = checksum(args.source)
    if args.expected_sha256:
        assert digest == args.expected_sha256, "Public source checksum differs from the registry"
    info = {
        "source": str(args.source.resolve()),
        "source_url": args.source_url,
        "sha256": digest,
        "file_bytes": args.source.stat().st_size,
        "python": sys.version.split()[0],
        "measurement_scope": "Fresh process; source hashing warms filesystem cache; Qt inspection and export slots exercised.",
    }
    timings = {}
    result_holder, failures = [], []
    actual_inspect, actual_exec, actual_read = (
        gui.inspect_scientific,
        QApplication.exec,
        h5py.Dataset.__getitem__,
    )
    maximum = [0]

    def inspected(*pos, **kw):
        assert QThread.currentThread() != QApplication.instance().thread()
        started = time.perf_counter()
        value = actual_inspect(*pos, **kw)
        timings["reader_seconds"] = time.perf_counter() - started
        return value

    def read(node, key):
        value = actual_read(node, key)
        if node.name.endswith("/X") or "/X/" in node.name:
            size = int(np.asarray(value).size)
            maximum[0] = max(maximum[0], size)
            assert size <= 1_000_000, "Unexpected unbounded X selection during inspection"
        return value

    def dialog_error(_parent, title, message, *_args, **_kwargs):
        raise RuntimeError(f"{title}: {message}")

    report_path = args.output_dir / "dashboard.html"

    def event_loop(app):
        window = next(w for w in app.topLevelWidgets() if hasattr(w, "h5ad_path"))
        assert [window.tabs.tabText(i) for i in range(window.tabs.count())] == [
            "Discovery",
            "HuBMAP",
            "CELLxGENE",
            "UCSC Cell Browser",
            "Local H5AD / H5MU",
        ]
        phase = ["inspection"]
        samples = {"inspection": [], "export": []}
        timer = QTimer(window)
        timer.setInterval(10)
        timer.timeout.connect(lambda: samples[phase[0]].append(time.perf_counter()))

        def run():
            try:
                window.h5ad_path = args.source.resolve()
                window.h5ad_file_label.setText(str(args.source.resolve()))
                window.tabs.setCurrentIndex(4)
                samples["inspection"].append(time.perf_counter())
                timer.start()
                start = time.perf_counter()
                window.inspect_h5ad_file()
                timings["inspection_slot_seconds"] = time.perf_counter() - start
                app.processEvents()
                samples["inspection"].append(time.perf_counter())
                result = window.h5ad_inspection
                assert result is not None
                if args.expected_shape:
                    assert [result.n_obs, result.n_vars] == args.expected_shape
                phase[0] = "export"
                samples["export"].append(time.perf_counter())
                start = time.perf_counter()
                window.export_h5ad_html()
                timings["export_slot_seconds"] = time.perf_counter() - start
                app.processEvents()
                samples["export"].append(time.perf_counter())
                timer.stop()
                assert window.grab().save(str(args.output_dir / "desktop.png"))
                result_holder.append(result)
                info["heartbeat"] = {
                    key: {
                        "timer_events": max(0, len(stamps) - 2),
                        "max_gap_seconds": float(np.max(np.diff(stamps))),
                        "p95_gap_seconds": float(np.quantile(np.diff(stamps), 0.95)),
                    }
                    for key, stamps in samples.items()
                }
            except Exception:  # noqa: BLE001 - surface asynchronous Qt callback failures
                failures.append(traceback.format_exc())
            finally:
                timer.stop()
                window.close()
                app.quit()

        QTimer.singleShot(0, run)
        return actual_exec()

    with (
        patch.object(gui, "inspect_scientific", inspected),
        patch.object(QApplication, "exec", event_loop),
        patch.object(h5py.Dataset, "__getitem__", read),
        patch.object(QMessageBox, "critical", dialog_error),
        patch.object(QFileDialog, "getSaveFileName", return_value=(str(report_path), "HTML")),
    ):
        try:
            gui.main()
        except SystemExit as exc:
            assert not exc.code
    assert not failures, "\n".join(failures)
    result = result_holder[0]
    info.update(
        timings=timings,
        observations=result.n_obs,
        features=result.n_vars,
        matrix_encoding=result.matrix.encoding,
        max_x_selection_elements=maximum[0],
        metadata_rows=len(result.obs_sample.row_indices),
        profiles=[p.model_dump() for p in result.scientific.profiles],
        correspondence=[c.model_dump() for c in result.scientific.correspondence],
        warnings=[*result.warnings, *result.scientific.warnings],
        checked_stored_feature_values=validate_values(args.source, result, np, h5py),
        html_bytes=report_path.stat().st_size,
    )
    assert checksum(args.source) == digest, "Source was modified"
    info["source_unchanged"] = True
    if sys.platform.startswith("linux"):
        import resource

        info["gui_process_peak_rss_mib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    if args.browser_executable:
        info["browser"] = browser_check(report_path, args.output_dir, args.browser_executable)
    (args.output_dir / "metrics.json").write_text(json.dumps(info, indent=2) + "\n")
    print(
        json.dumps(
            {
                key: value
                for key, value in info.items()
                if key not in {"warnings", "correspondence", "profiles"}
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

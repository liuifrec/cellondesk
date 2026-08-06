from __future__ import annotations

from cellondesk.diagnostics import run_diagnostics


def test_diagnostics_report_core_environment() -> None:
    report = run_diagnostics()
    names = {item.name for item in report.checks}

    assert report.python
    assert report.platform
    assert "cellondesk" in names
    assert "numpy" in names
    assert "cellxgene-census" in names

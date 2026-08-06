from __future__ import annotations

import importlib.util
import platform
import sys
from importlib.metadata import PackageNotFoundError, version

from pydantic import BaseModel


class DiagnosticCheck(BaseModel):
    name: str
    ok: bool
    detail: str


class DiagnosticReport(BaseModel):
    python: str
    platform: str
    checks: list[DiagnosticCheck]

    @property
    def ok(self) -> bool:
        return all(item.ok for item in self.checks)


def _package_check(distribution: str, import_name: str | None = None) -> DiagnosticCheck:
    import_name = import_name or distribution.replace("-", "_")
    available = importlib.util.find_spec(import_name) is not None
    try:
        installed_version = version(distribution)
    except PackageNotFoundError:
        installed_version = "not installed"
    return DiagnosticCheck(
        name=distribution,
        ok=available,
        detail=installed_version,
    )


def run_diagnostics() -> DiagnosticReport:
    return DiagnosticReport(
        python=sys.version.split()[0],
        platform=platform.platform(),
        checks=[
            _package_check("cellondesk"),
            _package_check("h5py"),
            _package_check("numpy"),
            _package_check("cellxgene-census", "cellxgene_census"),
            _package_check("PySide6"),
        ],
    )


__all__ = ["DiagnosticCheck", "DiagnosticReport", "run_diagnostics"]

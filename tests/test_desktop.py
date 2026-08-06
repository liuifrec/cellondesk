from __future__ import annotations

import json
import sys
from pathlib import Path

from cellondesk.desktop import main


def test_desktop_diagnostics_mode_writes_json(tmp_path: Path, monkeypatch) -> None:
    destination = tmp_path / "desktop-diagnostics.json"
    monkeypatch.setattr(sys, "argv", ["cellondesk-desktop", "--diagnostics", str(destination)])

    main()

    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["python"]
    assert payload["platform"]
    assert payload["checks"]

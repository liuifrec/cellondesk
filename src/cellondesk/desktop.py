from __future__ import annotations

import argparse
from pathlib import Path

from .diagnostics import run_diagnostics


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CellOnDesk desktop launcher")
    parser.add_argument(
        "--diagnostics",
        type=Path,
        metavar="PATH",
        help="Write environment diagnostics as JSON and exit without opening the GUI",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.diagnostics:
        report = run_diagnostics()
        args.diagnostics.parent.mkdir(parents=True, exist_ok=True)
        args.diagnostics.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return

    from .gui import main as gui_main

    gui_main()


if __name__ == "__main__":
    main()

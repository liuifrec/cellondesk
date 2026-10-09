"""Validate required native desktop dependencies; Census remains optional."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("diagnostics", type=Path)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    report = json.loads(args.diagnostics.read_text(encoding="utf-8"))
    checks = {item["name"]: item for item in report["checks"]}
    for name in ("cellondesk", "h5py", "numpy", "PySide6"):
        assert name in checks and checks[name]["ok"], f"Missing required desktop component: {name}"
    assert checks["cellondesk"]["detail"] == args.version, checks["cellondesk"]
    assert report["python"] and report["platform"]
    print(f"Required desktop diagnostics and version {args.version} verified: {args.diagnostics}")


if __name__ == "__main__":
    main()

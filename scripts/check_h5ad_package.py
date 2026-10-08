"""Run with python -I after installing the wheel to verify bundled report assets."""

from importlib.metadata import version
from importlib.resources import files

import cellondesk
from cellondesk.h5ad_report import render_h5ad_report
from cellondesk.inspection import H5ADInspection, MatrixSummary


def main() -> None:
    assert cellondesk.__version__ == version("cellondesk")
    assets = files("cellondesk").joinpath("report_assets", "h5ad")
    for name in (
        "shell.html",
        "dashboard.css",
        "core.js",
        "embeddings.js",
        "composition.js",
        "qc.js",
        "dashboard.js",
    ):
        assert assets.joinpath(name).read_text(encoding="utf-8")
    old_record = H5ADInspection(
        source_path="package-smoke.h5ad",
        file_name="package-smoke.h5ad",
        file_size_bytes=0,
        n_obs=0,
        n_vars=0,
        matrix=MatrixSummary(shape=(0, 0), encoding="missing"),
    )
    rendered = render_h5ad_report(old_record)
    assert 'id="inspection-data"' in rendered
    assert "function drawComposition" in rendered and "function drawQC" in rendered
    assert "$scripts" not in rendered and "<script src=" not in rendered
    print(f"CellOnDesk {cellondesk.__version__}: installed report resources/rendering passed")
    print(f"Imported from {cellondesk.__file__}")


if __name__ == "__main__":
    main()

"""Run with python -I after installing the wheel to verify bundled report assets."""

from importlib.metadata import version
from importlib.resources import files

import cellondesk
from cellondesk.h5ad_report import render_h5ad_report
from cellondesk.inspection import H5ADInspection, MatrixSummary
from cellondesk.modality import ModalityReport, apply_overrides
from cellondesk.scientific_formats import ContainerInspection, inspection_support


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
        "modalities.js",
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
    scientific = ModalityReport()
    apply_overrides(scientific, ["atac"])
    native = ContainerInspection(
        **old_record.model_dump(exclude={"storage_format", "scientific"}), scientific=scientific
    )
    rendered = render_h5ad_report(native)
    assert "CellOnDesk H5MU Summary" in rendered
    assert "initializeScientific" in rendered and "Manual interpretation: atac" in rendered
    assert "not checked" in inspection_support(["native.h5mu"])[0]
    print(f"CellOnDesk {cellondesk.__version__}: installed report resources/rendering passed")
    print(f"Imported from {cellondesk.__file__}")


if __name__ == "__main__":
    main()

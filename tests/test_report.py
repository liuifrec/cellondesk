from pathlib import Path

from cellondesk.models import DatasetRecord
from cellondesk.report import render_html_report, write_html_report


def test_report_is_self_contained_and_escapes_content():
    record = DatasetRecord(
        source="HuBMAP",
        dataset_id="abc",
        title="Kidney <script>alert(1)</script>",
        dataset_type="Visium (no probes)",
        organ="LK",
        status="Published",
        access_level="protected",
        portal_url="https://example.org/dataset/abc",
    )
    output = render_html_report([record], query={"organ": "LK"})
    assert "<!doctype html>" in output.lower()
    assert "Kidney &lt;script&gt;alert(1)&lt;/script&gt;" in output
    assert "https://example.org/dataset/abc" in output
    assert "cdn." not in output
    assert "1 dataset records" in output
    assert "protected" in output
    assert "1 public dataset records" not in output


def test_report_writes_html_file(tmp_path: Path):
    record = DatasetRecord(source="HuBMAP", dataset_id="abc", title="Example")
    destination = write_html_report([record], tmp_path / "web_summary.html")
    assert destination.exists()
    assert "CellOnDesk Web Summary" in destination.read_text(encoding="utf-8")

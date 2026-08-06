from cellondesk.manifest import hubmap_manifest_lines
from cellondesk.models import DatasetRecord


def test_manifest_deduplicates_and_normalizes_path():
    record = DatasetRecord(source="HuBMAP", dataset_id="abc", title="Example")
    assert hubmap_manifest_lines([record, record], "expr.h5ad") == ["abc\t/expr.h5ad"]


def test_manifest_ignores_non_hubmap_records():
    record = DatasetRecord(source="Other", dataset_id="abc", title="Example")
    assert hubmap_manifest_lines([record]) == []

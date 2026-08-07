from cellondesk.manifest import hubmap_manifest_lines
from cellondesk.models import DatasetRecord


def test_manifest_uses_hubmap_id_deduplicates_and_normalizes_path():
    record = DatasetRecord(
        source="HuBMAP",
        dataset_id="0123456789abcdef0123456789abcdef",
        title="Example",
        raw={"hubmap_id": "HBM123.ABCD.456"},
    )
    assert hubmap_manifest_lines([record, record], "expr.h5ad") == [
        "HBM123.ABCD.456\t/expr.h5ad"
    ]


def test_manifest_accepts_hbm_dataset_id_fallback():
    record = DatasetRecord(source="HuBMAP", dataset_id="HBM123.ABCD.456", title="Example")
    assert hubmap_manifest_lines([record]) == ["HBM123.ABCD.456\t/"]


def test_manifest_ignores_uuid_without_public_hubmap_id():
    record = DatasetRecord(source="HuBMAP", dataset_id="abc", title="Example")
    assert hubmap_manifest_lines([record]) == []


def test_manifest_ignores_non_hubmap_records():
    record = DatasetRecord(source="Other", dataset_id="abc", title="Example")
    assert hubmap_manifest_lines([record]) == []

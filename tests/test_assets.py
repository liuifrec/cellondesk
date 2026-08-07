from pathlib import Path

import httpx

from cellondesk.assets import format_bytes, iter_download
from cellondesk.models import DataAsset


def test_format_bytes() -> None:
    assert format_bytes(None) == "Unknown size"
    assert format_bytes(1024) == "1.00 KB"
    assert format_bytes(1024 * 1024) == "1.00 MB"


def test_iter_download_streams_to_partial_then_final_path(tmp_path: Path) -> None:
    payload = b"abcdef" * 1024

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload, headers={"content-length": str(len(payload))})

    asset = DataAsset(
        source="test",
        dataset_id="d1",
        name="expr.h5ad",
        download_url="https://example.test/expr.h5ad",
        is_h5ad=True,
    )
    destination = tmp_path / "expr.h5ad"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        updates = list(iter_download(asset, destination, chunk_size=128, client=client))

    assert destination.read_bytes() == payload
    assert not (tmp_path / "expr.h5ad.part").exists()
    assert updates[-1] == (len(payload), len(payload))

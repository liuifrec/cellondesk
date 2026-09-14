import gzip

import httpx
import pytest

from cellondesk.assets import DownloadCancelled, iter_download, probe_asset
from cellondesk.models import DataAsset


def asset(**kwargs):
    return DataAsset(source="test", dataset_id="d", name="x.h5ad",
                     download_url="https://example.test/x.h5ad", **kwargs)


def client_for(response):
    return httpx.Client(transport=httpx.MockTransport(lambda _: response))


def test_existing_file_requires_explicit_overwrite(tmp_path):
    target = tmp_path / "x.h5ad"
    target.write_bytes(b"original")
    with (
        client_for(httpx.Response(200, content=b"new")) as client,
        pytest.raises(FileExistsError),
    ):
        list(iter_download(asset(), target, client=client))
    assert target.read_bytes() == b"original"


@pytest.mark.parametrize("headers,metadata", [({"content-length": "20"}, None), ({}, 20)])
def test_truncation_does_not_replace_existing_file(tmp_path, headers, metadata):
    target = tmp_path / "x.h5ad"
    target.write_bytes(b"original")
    with (
        client_for(httpx.Response(200, content=b"short", headers=headers)) as client,
        pytest.raises(ValueError, match="Incomplete"),
    ):
        list(iter_download(asset(size_bytes=metadata), target, client=client, overwrite=True))
    assert target.read_bytes() == b"original"
    assert not list(tmp_path.glob("*.part"))


def test_close_cleans_only_owned_temporary_file(tmp_path):
    target = tmp_path / "x.h5ad"
    unrelated = tmp_path / "x.h5ad.part"
    unrelated.write_bytes(b"someone else's partial file")
    with client_for(httpx.Response(200, content=b"a" * 64)) as client:
        iterator = iter_download(asset(), target, client=client, chunk_size=8)
        next(iterator)
        assert len(list(tmp_path.glob("*.part"))) == 2
        iterator.close()
    assert not target.exists()
    assert list(tmp_path.glob("*.part")) == [unrelated]


def test_cancellation_after_last_chunk_prevents_commit(tmp_path):
    cancelled = False
    target = tmp_path / "x.h5ad"
    with client_for(httpx.Response(200, content=b"abc")) as client:
        iterator = iter_download(asset(), target, client=client, cancelled=lambda: cancelled)
        next(iterator)
        cancelled = True
        with pytest.raises(DownloadCancelled):
            next(iterator)
    assert not target.exists()
    assert not list(tmp_path.iterdir())


def test_mid_transfer_destination_race_never_overwrites(tmp_path):
    target = tmp_path / "x.h5ad"
    with client_for(httpx.Response(200, content=b"abc")) as client:
        iterator = iter_download(asset(), target, client=client)
        next(iterator)
        target.write_bytes(b"other writer")
        with pytest.raises(FileExistsError):
            next(iterator)
    assert target.read_bytes() == b"other writer"


@pytest.mark.parametrize("status,headers", [(200, {"content-type": "text/html"}), (206, {})])
def test_login_and_partial_responses_are_not_saved(tmp_path, status, headers):
    target = tmp_path / "x.h5ad"
    with (
        client_for(httpx.Response(status, content=b"not a complete file", headers=headers)) as client,
        pytest.raises(ValueError, match="complete data file"),
    ):
        list(iter_download(asset(), target, client=client))
    assert not target.exists()


def test_gzip_transport_length_is_not_file_length(tmp_path):
    body = b"hello" * 1024
    encoded = gzip.compress(body)
    response = httpx.Response(200, content=encoded,
                             headers={"content-encoding": "gzip", "content-length": str(len(encoded))})
    with client_for(response) as client:
        list(iter_download(asset(size_bytes=len(body)), tmp_path / "out", client=client))
    assert (tmp_path / "out").read_bytes() == body


class UnreadableBody(httpx.SyncByteStream):
    closed = False

    def __iter__(self):
        raise AssertionError("Probe consumed a potentially multi-GB body")
        yield b""  # pragma: no cover

    def close(self):
        self.closed = True


@pytest.mark.parametrize("status", [403, 405, 501])
def test_range_ignoring_server_is_not_buffered(status):
    body = UnreadableBody()

    def handler(request):
        if request.method == "HEAD":
            return httpx.Response(status)
        assert request.headers["Range"] == "bytes=0-0"
        return httpx.Response(200, stream=body, headers={"content-length": str(9 * 1024**3)})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        size, url = probe_asset(client, "https://example.test/x.h5ad")
    assert size == 9 * 1024**3
    assert url.endswith("x.h5ad")
    assert body.closed


def test_probe_server_failure_is_not_no_files():
    with (
        client_for(httpx.Response(503)) as client,
        pytest.raises(httpx.HTTPStatusError),
    ):
        probe_asset(client, "https://example.test/x.h5ad")


@pytest.mark.parametrize("url", ["file:///etc/passwd", "https://user:password@example.test/a"])
def test_unsupported_or_credentialed_download_url_is_rejected(tmp_path, url):
    obj = asset().model_copy(update={"download_url": url})
    with pytest.raises(ValueError, match="HTTP"):
        list(iter_download(obj, tmp_path / "out"))


def test_chunk_size_is_validated_before_transfer(tmp_path):
    with pytest.raises(ValueError, match="chunk_size"):
        list(iter_download(asset(), tmp_path / "out", chunk_size=0))

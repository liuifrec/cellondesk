from __future__ import annotations

import os
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import BinaryIO

import httpx

from .models import DataAsset

_CHUNK_SIZE = 1024 * 1024


class DownloadCancelled(Exception):
    """A transfer was cancelled before the destination was committed."""


def format_bytes(size: int | None) -> str:
    """Return a compact human-readable byte size."""
    if size is None:
        return "Unknown size"
    value = float(size)
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.2f} {unit}"
        value /= 1024
    return f"{size} B"


def _check_url(url: str) -> None:
    parsed = httpx.URL(url)
    if parsed.scheme not in {"http", "https"} or not parsed.host or parsed.userinfo:
        raise ValueError("A public download requires an HTTP(S) URL without credentials")


def response_size(response: httpx.Response) -> int | None:
    """Size of the representation, not of a one-byte range response."""
    content_range = response.headers.get("content-range", "")
    total = content_range.rsplit("/", 1)[-1] if "/" in content_range else ""
    if total.isdigit():
        return int(total)
    length = response.headers.get("content-length", "")
    if length.isdigit() and response.status_code != 206:
        return int(length)
    return None


def _is_html(response: httpx.Response) -> bool:
    return response.headers.get("content-type", "").split(";", 1)[0].strip().lower() in {
        "text/html", "application/xhtml+xml",
    }


def probe_asset(client: httpx.Client, url: str) -> tuple[int | None, str] | None:
    """Check a file without consuming its body, even when a server ignores Range.

    Missing/protected files return None. Network and server failures propagate:
    an unavailable service is not evidence that a dataset contains no files.
    """
    _check_url(url)
    response = client.head(url, follow_redirects=True)
    if response.status_code in {403, 405, 501}:
        with client.stream(
            "GET", url, headers={"Range": "bytes=0-0", "Accept-Encoding": "identity"},
            follow_redirects=True,
        ) as response:
            return _probe_result(response)
    return _probe_result(response)


def _probe_result(response: httpx.Response) -> tuple[int | None, str] | None:
    if response.status_code in {401, 403, 404, 410}:
        return None
    response.raise_for_status()
    if response.status_code not in {200, 206} or _is_html(response):
        return None
    return response_size(response), str(response.url)


def iter_download(
    asset: DataAsset,
    destination: str | Path,
    *,
    timeout: float = 120.0,
    chunk_size: int = _CHUNK_SIZE,
    client: httpx.Client | None = None,
    overwrite: bool = False,
    cancelled: Callable[[], bool] | None = None,
) -> Iterator[tuple[int, int | None]]:
    """Stream to a unique temporary file, verify lengths, then commit atomically.

    Existing destinations are preserved unless overwrite=True is explicit.
    Failure, cancellation, and generator.close() remove only our own temporary
    file. Metadata sizes are checked against decoded file bytes; HTTP lengths
    are checked only without transport Content-Encoding.
    """
    if not asset.download_url:
        raise ValueError(f"{asset.name} has no direct download URL")
    _check_url(asset.download_url)
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    if asset.size_bytes is not None and asset.size_bytes < 0:
        raise ValueError("Asset size cannot be negative")
    target = Path(destination)
    if target.is_dir():
        raise IsADirectoryError(target)
    if target.exists() and not overwrite:
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    own_client = client is None
    http = client or httpx.Client(timeout=timeout, follow_redirects=True)

    def check_cancelled() -> None:
        if cancelled is not None and cancelled():
            raise DownloadCancelled("Download cancelled")

    try:
        check_cancelled()
        with http.stream(
            "GET", asset.download_url, headers={"Accept-Encoding": "identity"},
            follow_redirects=True,
        ) as response:
            response.raise_for_status()
            if response.status_code != 200 or _is_html(response):
                raise ValueError("The server did not return a complete data file (possibly a login page)")
            encoded = response.headers.get("content-encoding", "identity").lower() != "identity"
            expected_http = None if encoded else response_size(response)
            total = asset.size_bytes if asset.size_bytes is not None else expected_http
            downloaded = 0
            fd, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".part", dir=target.parent)
            temporary = Path(name)
            with os.fdopen(fd, "wb") as handle:
                for chunk in response.iter_bytes(chunk_size=chunk_size):
                    check_cancelled()
                    if not chunk:
                        continue
                    handle.write(chunk)
                    downloaded += len(chunk)
                    yield downloaded, total
                handle.flush()
                os.fsync(handle.fileno())
            check_cancelled()
            for expected in (asset.size_bytes, expected_http):
                if expected is not None and downloaded != expected:
                    raise ValueError(f"Incomplete download: expected {expected} bytes, received {downloaded}")
            if not downloaded and total != 0:
                raise ValueError("The server returned an empty file")
        check_cancelled()
        if overwrite:
            os.replace(temporary, target)
        else:
            # Atomic no-clobber commit, including a destination created mid-transfer.
            os.link(temporary, target)
            temporary.unlink()
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if own_client:
            http.close()


def download_asset(
    asset: DataAsset,
    destination: str | Path,
    *,
    progress: Callable[[int, int | None], None] | None = None,
    overwrite: bool = False,
    cancelled: Callable[[], bool] | None = None,
) -> Path:
    """Download one asset without loading it into memory."""
    iterator = iter_download(asset, destination, overwrite=overwrite, cancelled=cancelled)
    try:
        for downloaded, total in iterator:
            if progress:
                progress(downloaded, total)
    finally:
        iterator.close()
    return Path(destination)


def copy_stream(source: BinaryIO, destination: BinaryIO, *, chunk_size: int = _CHUNK_SIZE) -> int:
    """Copy a binary stream in bounded chunks."""
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    copied = 0
    while chunk := source.read(chunk_size):
        destination.write(chunk)
        copied += len(chunk)
    return copied


__all__ = ["DownloadCancelled", "download_asset", "format_bytes", "iter_download", "probe_asset"]

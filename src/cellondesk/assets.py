from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import BinaryIO

import httpx

from .models import DataAsset

_CHUNK_SIZE = 1024 * 1024


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


def iter_download(
    asset: DataAsset,
    destination: str | Path,
    *,
    timeout: float = 120.0,
    chunk_size: int = _CHUNK_SIZE,
    client: httpx.Client | None = None,
) -> Iterator[tuple[int, int | None]]:
    """Stream a public asset to disk and yield downloaded/total byte counts.

    The partial file is removed if the transfer fails or the generator is closed
    before completion. Callers can therefore cancel safely by closing the
    generator.
    """
    if not asset.download_url:
        raise ValueError(f"{asset.name} has no direct download URL")
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.part")
    own_client = client is None
    http = client or httpx.Client(timeout=timeout, follow_redirects=True)
    completed = False
    try:
        with http.stream("GET", asset.download_url) as response:
            response.raise_for_status()
            total = asset.size_bytes
            if total is None:
                content_length = response.headers.get("content-length")
                if content_length and content_length.isdigit():
                    total = int(content_length)
            downloaded = 0
            with temporary.open("wb") as handle:
                for chunk in response.iter_bytes(chunk_size=chunk_size):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    downloaded += len(chunk)
                    yield downloaded, total
        temporary.replace(target)
        completed = True
    finally:
        if own_client:
            http.close()
        if not completed and temporary.exists():
            temporary.unlink()


def download_asset(
    asset: DataAsset,
    destination: str | Path,
    *,
    progress: Callable[[int, int | None], None] | None = None,
) -> Path:
    """Download one asset without loading it into memory."""
    for downloaded, total in iter_download(asset, destination):
        if progress:
            progress(downloaded, total)
    return Path(destination)


def copy_stream(source: BinaryIO, destination: BinaryIO, *, chunk_size: int = _CHUNK_SIZE) -> int:
    """Copy a binary stream in bounded chunks; useful for tests and future adapters."""
    copied = 0
    while chunk := source.read(chunk_size):
        destination.write(chunk)
        copied += len(chunk)
    return copied


__all__ = ["download_asset", "format_bytes", "iter_download"]

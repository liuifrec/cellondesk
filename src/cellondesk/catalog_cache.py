"""Bounded, expiring public JSON metadata cache (never caches credentials or assets)."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

MAX_JSON_BYTES = 64 * 1024 * 1024


class SearchStopped(RuntimeError):
    pass


@dataclass
class SearchStats:
    requests: int = 0
    cache_hits: int = 0
    revalidated: int = 0
    downloaded_bytes: int = 0
    scanned: int = 0
    matched: int = 0
    returned: int = 0
    complete: bool = True
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)
    metadata_timestamps: dict[str, float] = field(default_factory=dict)

    def scope(self) -> dict[str, Any]:
        return {
            "complete": self.complete,
            "truncated": self.truncated,
            "inspected": self.scanned,
            "matched": self.matched,
            "returned": self.returned,
            "warnings": list(self.warnings),
        }

    def warn(self, message: str) -> None:
        self.complete = False
        if message not in self.warnings and len(self.warnings) < 20:
            self.warnings.append(message)


class SearchBudget:
    """Cooperative total deadline, also applied to each HTTP operation/chunk."""

    def __init__(self, seconds: float = 30, cancelled: Callable[[], bool] = lambda: False):
        self.deadline = time.monotonic() + seconds
        self.cancelled = cancelled
        self.metadata_bytes = 0

    def consume(self, size: int) -> None:
        self.remaining()
        self.metadata_bytes += size
        if self.metadata_bytes > 128 * 1024 * 1024:
            raise SearchStopped("Source metadata budget reached (128 MiB); coverage is incomplete.")

    def remaining(self) -> float:
        if self.cancelled():
            raise SearchStopped("Search cancelled; results may be incomplete.")
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise SearchStopped("Source time budget reached; results may be incomplete.")
        return max(0.001, remaining)


def read_json(response: httpx.Response, budget: SearchBudget, stats: SearchStats) -> Any:
    """Cap decompressed bytes, not just the server's optional Content-Length."""
    data = bytearray()
    for chunk in response.iter_bytes(chunk_size=65536):
        budget.remaining()
        stats.downloaded_bytes += len(chunk)
        if len(data) + len(chunk) > MAX_JSON_BYTES:
            raise SearchStopped("Metadata response exceeded the 64 MiB safety limit.")
        budget.consume(len(chunk))
        data.extend(chunk)
    budget.remaining()
    return json.loads(data)


def default_cache_dir() -> Path:
    custom = os.environ.get("CELLONDESK_CACHE_DIR")
    if custom:
        return Path(custom)
    root = os.environ.get("LOCALAPPDATA") if os.name == "nt" else os.environ.get("XDG_CACHE_HOME")
    return (Path(root) if root else Path.home() / ".cache") / "cellondesk" / "catalogs-v1"


class CatalogCache:
    """Atomic on-disk entries; TTL refresh uses HTTP validators when available.

    ``directory=None`` disables persistence (useful for injected transports).
    Expired entries are never silently used when their refresh fails.
    """

    def __init__(
        self,
        directory: Path | None,
        *,
        ttl: float = 86400,
        max_disk_bytes: int = 256 * 1024 * 1024,
        clock: Callable[[], float] = time.time,
    ):
        self.directory = directory
        self.ttl = ttl
        self.max_disk_bytes = max_disk_bytes
        self.clock = clock

    def _path(self, url: str) -> Path | None:
        if self.directory is None:
            return None
        return self.directory / (hashlib.sha256(url.encode()).hexdigest() + ".json")

    def _load(self, url: str, budget: SearchBudget) -> dict[str, Any] | None:
        path = self._path(url)
        if path is None:
            return None
        try:
            size = path.stat().st_size
            if size > MAX_JSON_BYTES + 4096:
                return None
            budget.consume(size)
            entry = json.loads(path.read_bytes())
            if (
                entry.get("url") == url
                and entry.get("version") == 1
                and isinstance(entry.get("fetched_at"), (int, float))
                and "payload" in entry
            ):
                return entry
        except (OSError, ValueError, AttributeError):
            pass
        return None

    def _save(self, url: str, entry: dict[str, Any]) -> None:
        path = self._path(url)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(entry, ensure_ascii=True, separators=(",", ":")).encode()
        if len(encoded) > min(MAX_JSON_BYTES + 4096, self.max_disk_bytes):
            return
        # Prune only our hashed JSON entries. A failed cache write never prevents a search.
        files = sorted(
            path.parent.glob("[0-9a-f]" * 64 + ".json"), key=lambda item: item.stat().st_mtime
        )
        total = sum(item.stat().st_size for item in files)
        for item in files:
            if total + len(encoded) <= self.max_disk_bytes:
                break
            total -= item.stat().st_size
            item.unlink(missing_ok=True)
        temp: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=path.parent, suffix=".tmp", delete=False
            ) as stream:
                temp = stream.name
                stream.write(encoded)
            os.replace(temp, path)
        finally:
            if temp:
                Path(temp).unlink(missing_ok=True)

    def get(
        self,
        client: httpx.Client,
        url: str,
        *,
        budget: SearchBudget,
        stats: SearchStats,
        refresh: bool = False,
    ) -> Any:
        budget.remaining()
        entry = self._load(url, budget)
        now = self.clock()
        if entry and not refresh and 0 <= now - entry["fetched_at"] < self.ttl:
            stats.cache_hits += 1
            stats.metadata_timestamps[url] = entry["fetched_at"]
            return entry["payload"]
        headers = {}
        if entry:
            if entry.get("etag"):
                headers["If-None-Match"] = entry["etag"]
            if entry.get("last_modified"):
                headers["If-Modified-Since"] = entry["last_modified"]
        stats.requests += 1
        with client.stream(
            "GET", url, headers=headers, timeout=min(10, budget.remaining())
        ) as resp:
            if resp.status_code == 304 and entry:
                stats.revalidated += 1
                entry["fetched_at"] = now
            else:
                resp.raise_for_status()
                entry = {
                    "version": 1,
                    "url": url,
                    "fetched_at": now,
                    "etag": resp.headers.get("etag"),
                    "last_modified": resp.headers.get("last-modified"),
                    "payload": read_json(resp, budget, stats),
                }
        try:
            self._save(url, entry)
        except OSError:
            if "Public metadata cache could not be written." not in stats.warnings:
                stats.warnings.append("Public metadata cache could not be written.")
        stats.metadata_timestamps[url] = entry["fetched_at"]
        return entry["payload"]

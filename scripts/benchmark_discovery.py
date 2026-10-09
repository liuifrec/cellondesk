"""Measure cold/warm discovery. Live mode reads metadata only, never data assets."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from cellondesk.catalog_cache import CatalogCache
from cellondesk.discovery import DiscoveryService, SearchQuery
from cellondesk.modality import PROFILE_LABELS
from cellondesk.sources.cellxgene_discover import CellxGeneDiscoverClient
from cellondesk.sources.hubmap import HuBMAPClient
from cellondesk.sources.ucsc_cellbrowser import UCSCCellBrowserClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Contact the real public repositories")
    parser.add_argument("--tissue", default="kidney")
    parser.add_argument("--modality", action="append", choices=list(PROFILE_LABELS), default=[])
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=("hubmap", "cellxgene", "ucsc"),
        default=["hubmap", "cellxgene", "ucsc"],
    )
    parser.add_argument(
        "--cache-dir", type=Path, required=True, help="Use a new directory for a cold run"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.live:
        cache = CatalogCache(args.cache_dir)
        factories = {
            "hubmap": lambda budget: HuBMAPClient(budget=budget),
            "cellxgene": lambda budget: CellxGeneDiscoverClient(budget=budget, cache=cache),
            "ucsc": lambda budget: UCSCCellBrowserClient(budget=budget, cache=cache),
        }
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
        from discovery_fixtures import CatalogFixture

        fixture = CatalogFixture()
        factories = fixture.factories(args.cache_dir)
    service = DiscoveryService(factories=factories, timeout=args.timeout)
    query = SearchQuery(
        tissue=args.tissue, sources=tuple(args.sources), modalities=tuple(args.modality)
    )
    preexisting = args.cache_dir.exists() and any(args.cache_dir.glob("*.json"))
    report = {
        "mode": "live metadata" if args.live else "synthetic catalog",
        "utc": datetime.now(timezone.utc).isoformat(),
        "query": asdict(query),
        "cache_dir": str(args.cache_dir),
        "cache_preexisting": preexisting,
        "runs": {},
    }
    for label in ("cached_start" if preexisting else "cold", "warm"):
        started = time.monotonic()
        outcomes = service.search(query)
        report["runs"][label] = {
            "wall_seconds": time.monotonic() - started,
            "sources": [
                {
                    "source": o.source,
                    "seconds": o.elapsed_seconds,
                    "error": o.error,
                    "stats": asdict(o.stats),
                    "notices": o.notices,
                    "identifiers": [r.dataset_id for r in o.records],
                }
                for o in outcomes
            ],
        }
        print(
            label,
            json.dumps(
                [
                    {
                        key: value
                        for key, value in source.items()
                        if key not in {"identifiers", "notices", "stats"}
                    }
                    | {
                        "stats": {
                            key: value
                            for key, value in source["stats"].items()
                            if key != "metadata_timestamps"
                        }
                    }
                    for source in report["runs"][label]["sources"]
                ]
            ),
            flush=True,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if all(source["error"] for source in report["runs"]["warm"]["sources"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

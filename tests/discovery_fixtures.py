"""Small public-catalog analogues with explicit expected discovery coverage."""

from __future__ import annotations

import httpx

from cellondesk.catalog_cache import CatalogCache
from cellondesk.sources.cellxgene_discover import CellxGeneDiscoverClient
from cellondesk.sources.hubmap import HuBMAPClient
from cellondesk.sources.ucsc_cellbrowser import UCSCCellBrowserClient

CELLXGENE = [
    {
        "dataset_id": "cxg-kidney",
        "title": "Kidney atlas",
        "cell_count": 1200,
        "tissue": [{"label": "kidney"}],
        "organism": [{"label": "Homo sapiens"}],
        "assay": [{"label": "RNAseq"}],
        "disease": [{"label": "normal"}],
        "assets": [{"url": "https://example.org/kidney.h5ad", "filetype": "H5AD"}],
    },
    {
        "dataset_id": "cxg-brain",
        "title": "Brain atlas",
        "cell_count": 24,
        "tissue": [{"label": "brain"}],
        "organism": [{"label": "Mus musculus"}],
    },
]
UCSC = {
    "/dataset.json": {
        "datasets": [
            {
                "name": "unexpected-parent",
                "shortLabel": "Multi-organ collection",
                "isCollection": True,
                "body_parts": ["brain"],
                "sampleCount": 99999,
            },
            {"name": "brain", "shortLabel": "Brain", "sampleCount": 15, "body_parts": ["brain"]},
        ]
    },
    "/unexpected-parent/dataset.json": {
        "datasets": [{"name": "nested", "isCollection": True, "body_parts": ["lung"]}]
    },
    "/unexpected-parent/nested/dataset.json": {
        "datasets": [
            {
                "name": "kidney-child",
                "shortLabel": "Child-only match",
                "sampleCount": 321,
                "facets": {
                    "body_parts": ["kidney cortex"],
                    "organisms": ["Human (H. sapiens)"],
                    "assays": ["RNAseq"],
                },
                "hasFiles": ["expr.h5ad"],
            },
            {"name": "unreported", "shortLabel": "No child biology"},
        ]
    },
    "/unexpected-parent/nested/unreported/dataset.json": {"name": "unreported"},
}


class CatalogFixture:
    def __init__(self):
        self.requests: list[httpx.Request] = []

    def handler(self, request):
        self.requests.append(request)
        assert request.method == "GET", "Search must not probe dataset assets"
        if "cellxgene" in request.url.host:
            return httpx.Response(200, json=CELLXGENE, headers={"ETag": '"v1"'})
        if request.url.host == "cells.ucsc.edu":
            return httpx.Response(200, json=UCSC[request.url.path])
        organ = request.url.params.get("origin_samples.organ")
        return httpx.Response(
            200,
            json=[
                {
                    "uuid": f"{organ}-{i}",
                    "hubmap_id": f"HBM{organ}.{i}",
                    "title": f"Kidney {organ} {i}",
                    "origin_samples": [{"organ": organ}],
                    "dataset_type": "RNAseq",
                    "status": "Published",
                    "data_access_level": "public",
                    "organism": "Homo sapiens",
                    "donor": {"hubmap_id": "HBM-DONOR"},
                }
                for i in range(3)
            ],
        )

    def factories(self, directory):
        transport = httpx.MockTransport(self.handler)
        cache = CatalogCache(directory)
        return {
            "hubmap": lambda budget: HuBMAPClient(transport=transport, budget=budget),
            "cellxgene": lambda budget: CellxGeneDiscoverClient(
                transport=transport, cache=cache, budget=budget
            ),
            "ucsc": lambda budget: UCSCCellBrowserClient(
                transport=transport, cache=cache, budget=budget
            ),
        }

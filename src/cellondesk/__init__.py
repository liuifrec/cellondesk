"""CellOnDesk public API."""

from . import legacy_feature_compat as _legacy_feature_compat  # noqa: F401
from .census_report import render_census_report, write_census_report
from .diagnostics import DiagnosticCheck, DiagnosticReport, run_diagnostics
from .expression import GeneExpressionPreview, inspect_gene_expression
from .h5ad_compat import H5ADInspection, inspect_h5ad
from .models import DatasetRecord
from .sources.cellxgene_discover import CellxGeneDiscoverClient
from .sources.census import (
    SUPPORTED_CENSUS_VALUE_FIELDS,
    CensusGenePreview,
    CensusQuery,
    CensusValueCount,
    CensusValueResult,
    DatasetCitation,
    list_census_values,
    preview_census_gene,
)
from .sources.ucsc_cellbrowser import UCSCCellBrowserClient

__all__ = [
    "SUPPORTED_CENSUS_VALUE_FIELDS",
    "CellxGeneDiscoverClient",
    "CensusGenePreview",
    "CensusQuery",
    "CensusValueCount",
    "CensusValueResult",
    "DatasetCitation",
    "DatasetRecord",
    "DiagnosticCheck",
    "DiagnosticReport",
    "GeneExpressionPreview",
    "H5ADInspection",
    "UCSCCellBrowserClient",
    "inspect_gene_expression",
    "inspect_h5ad",
    "list_census_values",
    "preview_census_gene",
    "render_census_report",
    "run_diagnostics",
    "write_census_report",
]
__version__ = "0.11.0"

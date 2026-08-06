"""CellOnDesk public API."""

from . import legacy_feature_compat as _legacy_feature_compat  # noqa: F401
from .census_report import render_census_report, write_census_report
from .expression import GeneExpressionPreview, inspect_gene_expression
from .h5ad_compat import H5ADInspection, inspect_h5ad
from .models import DatasetRecord
from .sources.census import CensusGenePreview, CensusQuery, preview_census_gene

__all__ = [
    "CensusGenePreview",
    "CensusQuery",
    "DatasetRecord",
    "GeneExpressionPreview",
    "H5ADInspection",
    "inspect_gene_expression",
    "inspect_h5ad",
    "preview_census_gene",
    "render_census_report",
    "write_census_report",
]
__version__ = "0.6.0"

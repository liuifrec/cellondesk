"""CellOnDesk public API."""

from . import legacy_feature_compat as _legacy_feature_compat  # noqa: F401
from .expression import GeneExpressionPreview, inspect_gene_expression
from .h5ad_compat import H5ADInspection, inspect_h5ad
from .models import DatasetRecord

__all__ = [
    "DatasetRecord",
    "GeneExpressionPreview",
    "H5ADInspection",
    "inspect_gene_expression",
    "inspect_h5ad",
]
__version__ = "0.4.0"

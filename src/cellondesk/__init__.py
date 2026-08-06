"""CellOnDesk public API."""

from .inspection import H5ADInspection, inspect_h5ad
from .models import DatasetRecord

__all__ = ["DatasetRecord", "H5ADInspection", "inspect_h5ad"]
__version__ = "0.3.0"

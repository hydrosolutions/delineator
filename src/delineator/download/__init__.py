"""
Download module for MERIT-Hydro and MERIT-Basins data.

This module provides utilities to programmatically download the data required
for watershed delineation from various sources:
- MERIT-Hydro rasters from mghydro.com
- MERIT-Basins vectors from Google Drive (ReachHydro)
- Simplified catchments from mghydro.com
"""

from .basin_selector import get_all_basin_codes, get_basins_for_bbox, validate_basin_codes
from .downloader import DownloadResult, download_data
from .gdrive_client import (
    DataSource,
    download_basin_vectors,
    download_catchments,
    download_rivers,
    list_available_files,
)
from .http_client import (
    download_basin_rasters,
    download_raster,
    download_simplified_catchments,
)

__all__ = [
    "get_basins_for_bbox",
    "get_all_basin_codes",
    "validate_basin_codes",
    "download_raster",
    "download_simplified_catchments",
    "download_basin_rasters",
    "download_data",
    "DownloadResult",
    "DataSource",
    "download_catchments",
    "download_rivers",
    "download_basin_vectors",
    "list_available_files",
]

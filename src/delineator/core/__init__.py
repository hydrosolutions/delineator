"""
Core utilities for watershed delineation.

This module contains core functionality for:
- Watershed delineation logic
- Data availability checking and validation
- MERIT-Hydro raster operations for detailed delineation
- Polygon dissolve and hole-filling operations
- Country extraction via reverse geocoding
- Output writing for delineation results
"""

from .country import get_country
from .data_check import (
    DataAvailability,
    check_data_availability,
    ensure_data_available,
    get_required_basins,
)
from .delineate import (
    BasinData,
    DelineatedWatershed,
    DelineationError,
    collect_upstream_comids,
    delineate_outlet,
    get_area,
    load_basin_data,
)
from .dissolve import close_holes, dissolve_geopandas, fill_geopandas
from .merit import compute_snap_threshold, split_catchment
from .output_writer import FailedOutlet, OutputFormat, OutputWriter

__all__ = [
    # Data availability
    "DataAvailability",
    "check_data_availability",
    "ensure_data_available",
    "get_required_basins",
    # Delineation
    "BasinData",
    "DelineatedWatershed",
    "DelineationError",
    "collect_upstream_comids",
    "delineate_outlet",
    "get_area",
    "load_basin_data",
    # Raster operations
    "compute_snap_threshold",
    "split_catchment",
    # Dissolve operations
    "dissolve_geopandas",
    "fill_geopandas",
    "close_holes",
    # Country extraction
    "get_country",
    # Output writing
    "FailedOutlet",
    "OutputFormat",
    "OutputWriter",
]

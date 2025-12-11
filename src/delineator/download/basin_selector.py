"""
Basin selector for MERIT-Hydro data downloads.

This module provides functions to determine which Pfafstetter Level 2 basins
intersect a given bounding box. This is used to determine which data files
to download for watershed delineation.

The global MERIT-Hydro dataset is organized into 61 continental-scale basins
identified by Pfafstetter Level 2 codes (2-digit integers from 11 to 91).
"""

import logging
from functools import lru_cache
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

# Default path to the Level 2 basins shapefile
# Use absolute path relative to module location for portability
_MODULE_DIR = Path(__file__).parent
_PROJECT_ROOT = _MODULE_DIR.parent.parent.parent
DEFAULT_BASINS_SHAPEFILE = str(_PROJECT_ROOT / "data" / "shp" / "basins_level2" / "merit_hydro_vect_level2.shp")

# Set up logging
logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_basins_gdf(basins_shapefile: str) -> gpd.GeoDataFrame:
    """
    Load and cache the basins GeoDataFrame.

    This function uses LRU cache to avoid re-reading the shapefile on
    subsequent calls with the same path.

    Args:
        basins_shapefile: Path to the Level 2 basins shapefile

    Returns:
        GeoDataFrame containing basin polygons

    Raises:
        FileNotFoundError: If the shapefile doesn't exist
    """
    basins_path = Path(basins_shapefile)

    if not basins_path.exists():
        raise FileNotFoundError(f"Basins shapefile not found: {basins_shapefile}")

    logger.info(f"Loading basins from: {basins_shapefile}")
    gdf = gpd.read_file(basins_shapefile)

    # Ensure WGS84 CRS
    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        logger.debug("Converting basins to EPSG:4326 (WGS84)")
        gdf = gdf.to_crs("EPSG:4326")

    # Validate that we loaded the correct shapefile
    if "BASIN" not in gdf.columns:
        raise ValueError(
            f"Shapefile {basins_shapefile} does not contain 'BASIN' column. Available columns: {gdf.columns.tolist()}"
        )

    return gdf


def get_basins_for_bbox(
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    basins_shapefile: str | Path | None = None,
) -> list[int]:
    """
    Get list of Pfafstetter Level 2 basin codes that intersect a bounding box.

    This function creates a bounding box from the provided coordinates and
    performs a spatial intersection with the Level 2 basins shapefile to
    determine which basins need to be downloaded.

    Supports point queries (when min_lon == max_lon and/or min_lat == max_lat)
    by applying a small buffer around the point.

    Args:
        min_lon: Western boundary (longitude in decimal degrees)
        min_lat: Southern boundary (latitude in decimal degrees)
        max_lon: Eastern boundary (longitude in decimal degrees)
        max_lat: Northern boundary (latitude in decimal degrees)
        basins_shapefile: Path to Level 2 basins shapefile. If None, uses default.

    Returns:
        List of basin codes (integers like 11, 42, 45) that intersect the bbox,
        sorted in ascending order.

    Raises:
        ValueError: If bbox coordinates are invalid (min > max)
        FileNotFoundError: If shapefile doesn't exist

    Example:
        >>> # Get basins for Iceland
        >>> basins = get_basins_for_bbox(-25, 63, -13, 67)
        >>> print(basins)
        [41]
    """
    # Handle point/line queries by adding buffer (~111 meters at equator)
    POINT_BUFFER = 0.001

    if min_lon == max_lon:
        min_lon -= POINT_BUFFER
        max_lon += POINT_BUFFER

    if min_lat == max_lat:
        min_lat -= POINT_BUFFER
        max_lat += POINT_BUFFER

    # Clamp to valid coordinate ranges
    min_lon = max(-180.0, min_lon)
    max_lon = min(180.0, max_lon)
    min_lat = max(-90.0, min_lat)
    max_lat = min(90.0, max_lat)

    # Validate bounding box - only reject inverted coordinates
    if min_lon > max_lon:
        raise ValueError(f"Invalid bbox: min_lon ({min_lon}) must be <= max_lon ({max_lon})")
    if min_lat > max_lat:
        raise ValueError(f"Invalid bbox: min_lat ({min_lat}) must be <= max_lat ({max_lat})")

    # Use default shapefile if none provided
    basins_shapefile = DEFAULT_BASINS_SHAPEFILE if basins_shapefile is None else str(basins_shapefile)

    # Load basins (cached)
    basins_gdf = _load_basins_gdf(basins_shapefile)

    # Create bbox geometry
    bbox_geom = box(min_lon, min_lat, max_lon, max_lat)

    logger.debug(f"Finding basins intersecting bbox: ({min_lon}, {min_lat}, {max_lon}, {max_lat})")

    # Find intersecting basins
    intersecting = basins_gdf[basins_gdf.geometry.intersects(bbox_geom)]

    # Extract basin codes and convert to int
    basin_codes = intersecting["BASIN"].astype(int).tolist()

    # Sort for consistent output
    basin_codes.sort()

    logger.info(f"Found {len(basin_codes)} basin(s): {basin_codes}")

    return basin_codes


def get_all_basin_codes() -> list[int]:
    """
    Return all valid Pfafstetter Level 2 basin codes.

    This function reads the basins shapefile and extracts all unique basin codes.
    Useful for operations that need to work with all available basins.

    Returns:
        List of all basin codes (integers), sorted in ascending order.

    Example:
        >>> all_basins = get_all_basin_codes()
        >>> len(all_basins)
        61
        >>> all_basins[0]
        11
    """
    basins_gdf = _load_basins_gdf(DEFAULT_BASINS_SHAPEFILE)

    # Get all unique basin codes
    basin_codes = basins_gdf["BASIN"].astype(int).unique().tolist()
    basin_codes.sort()

    logger.info(f"Total basins available: {len(basin_codes)}")

    return basin_codes


def validate_basin_codes(codes: list[int]) -> list[int]:
    """
    Validate that basin codes exist in the basins shapefile.

    This function checks that all provided basin codes are valid Level 2
    Pfafstetter basin codes. Invalid codes will raise an error.

    Args:
        codes: List of basin codes to validate

    Returns:
        The same list of basin codes (unchanged) if all are valid

    Raises:
        ValueError: If any basin code is invalid

    Example:
        >>> validate_basin_codes([11, 42])
        [11, 42]
        >>> validate_basin_codes([11, 99])  # doctest: +SKIP
        ValueError: Invalid basin codes: [99]. Valid codes range from 11 to 91.
    """
    all_codes = get_all_basin_codes()
    all_codes_set = set(all_codes)

    # Check for invalid codes
    invalid_codes = [code for code in codes if code not in all_codes_set]

    if invalid_codes:
        min_code = min(all_codes)
        max_code = max(all_codes)
        raise ValueError(f"Invalid basin codes: {invalid_codes}. Valid codes range from {min_code} to {max_code}.")

    logger.debug(f"Validated {len(codes)} basin code(s)")

    return codes

"""
Dependency injection and caching utilities for the delineator API.

Provides:
- Environment-based configuration (data directory)
- LRU-cached basin data loading
- Basin lookup for geographic points
"""

import os
from functools import lru_cache
from pathlib import Path

from delineator.core.delineate import BasinData


def get_data_dir() -> Path:
    """
    Get the MERIT-Hydro data directory from environment.

    Returns:
        Path to data directory
    """
    return Path(os.getenv("MERIT_DATA_DIR", "/data/merit-hydro"))


@lru_cache(maxsize=5)
def _load_basin_cached(basin: int, data_dir_str: str) -> BasinData:
    """
    Load basin data with LRU caching.

    Note: Uses string path to make it hashable for lru_cache.

    Args:
        basin: Basin code to load
        data_dir_str: String path to MERIT-Hydro data directory

    Returns:
        BasinData for the specified basin
    """
    from delineator.core.delineate import load_basin_data

    return load_basin_data(basin, Path(data_dir_str))


def get_basin_for_point(lat: float, lng: float) -> BasinData:
    """
    Determine which basin contains the point and load its data.

    Args:
        lat: Latitude in decimal degrees
        lng: Longitude in decimal degrees

    Returns:
        BasinData for the basin containing the point

    Raises:
        ValueError: If point doesn't fall in any basin (e.g., ocean)
        FileNotFoundError: If basin data files are missing
    """
    from delineator.download import get_basins_for_bbox
    from delineator.download.basin_selector import _get_basins_shapefile_path

    data_dir = get_data_dir()
    basins_shapefile = _get_basins_shapefile_path(data_dir)

    # Get basins that intersect the point (usually just one)
    basins = get_basins_for_bbox(lng, lat, lng, lat, basins_shapefile=basins_shapefile)

    if not basins:
        raise ValueError(f"Point ({lat}, {lng}) does not fall within any known basin")

    # Use first basin (should be the only one for a point)
    basin_code = basins[0]

    return _load_basin_cached(basin_code, str(data_dir))


def get_basin_cache_info() -> dict:
    """Get LRU cache statistics for the basin loader."""
    info = _load_basin_cached.cache_info()
    return {
        "hits": info.hits,
        "misses": info.misses,
        "maxsize": info.maxsize,
        "currsize": info.currsize,
    }

"""
Default values and environment variables for delineator configuration.

This module centralizes all default values, environment variable names,
and path configurations used throughout the delineator CLI.
"""

# Default values for master configuration
DEFAULT_MAX_FAILS = None  # unlimited
DEFAULT_OUTPUT_DIR = "./output"
DEFAULT_DATA_DIR = "data"

# Environment variable names for data paths
ENV_DATA_DIR = "DELINEATOR_DATA_DIR"
ENV_FDIR_DIR = "DELINEATOR_FDIR_DIR"
ENV_ACCUM_DIR = "DELINEATOR_ACCUM_DIR"
ENV_CATCHMENTS_DIR = "DELINEATOR_CATCHMENTS_DIR"
ENV_RIVERS_DIR = "DELINEATOR_RIVERS_DIR"

# Default data paths (relative to data dir)
DEFAULT_FDIR_PATH = "raster/flowdir_basins"
DEFAULT_ACCUM_PATH = "raster/accum_basins"
DEFAULT_CATCHMENTS_PATH = "shp/merit_catchments"
DEFAULT_RIVERS_PATH = "shp/merit_rivers"
DEFAULT_SIMPLIFIED_PATH = "shp/catchments_simplified"

# Default outlet field name
DEFAULT_GAUGE_NAME = ""

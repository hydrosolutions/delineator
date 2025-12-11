"""
Configuration management for the delineator CLI.

This module provides Pydantic-based configuration schemas for validating
and loading TOML configuration files used by the delineator CLI.

Key exports:
- MasterConfig: Root configuration from delineate.toml
- RegionConfig: Configuration for a single region
- OutletConfig: Configuration for a single outlet point
- load_config(): Load and validate master configuration
- load_outlets(): Load and validate outlets from a region file
"""

from .defaults import (
    DEFAULT_ACCUM_PATH,
    DEFAULT_CATCHMENTS_PATH,
    DEFAULT_DATA_DIR,
    DEFAULT_FDIR_PATH,
    DEFAULT_GAUGE_NAME,
    DEFAULT_MAX_FAILS,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_RIVERS_PATH,
    DEFAULT_SIMPLIFIED_PATH,
    ENV_ACCUM_DIR,
    ENV_CATCHMENTS_DIR,
    ENV_FDIR_DIR,
    ENV_RIVERS_DIR,
)
from .schema import (
    MasterConfig,
    OutletConfig,
    OutletFileConfig,
    RegionConfig,
    SettingsConfig,
    load_config,
    load_outlets,
)

__all__ = [
    # Main models
    "MasterConfig",
    "RegionConfig",
    "OutletConfig",
    "OutletFileConfig",
    "SettingsConfig",
    # Loaders
    "load_config",
    "load_outlets",
    # Defaults
    "DEFAULT_OUTPUT_DIR",
    "DEFAULT_MAX_FAILS",
    "DEFAULT_DATA_DIR",
    "DEFAULT_GAUGE_NAME",
    "DEFAULT_FDIR_PATH",
    "DEFAULT_ACCUM_PATH",
    "DEFAULT_CATCHMENTS_PATH",
    "DEFAULT_RIVERS_PATH",
    "DEFAULT_SIMPLIFIED_PATH",
    # Environment variables
    "ENV_FDIR_DIR",
    "ENV_ACCUM_DIR",
    "ENV_CATCHMENTS_DIR",
    "ENV_RIVERS_DIR",
]

"""
Pydantic models for delineator configuration files.

This module defines the configuration schema for the delineator CLI using
Pydantic v2. It validates TOML configuration files and provides type-safe
access to configuration values.

The configuration hierarchy:
- MasterConfig (delineate.toml): Top-level configuration with global settings and regions
- RegionConfig: Configuration for a single region (name + path to outlets file)
- OutletConfig (region.toml): Individual outlet points with coordinates
"""

import logging
import re
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator

from .defaults import DEFAULT_FILL_THRESHOLD, DEFAULT_GAUGE_NAME, DEFAULT_MAX_FAILS, DEFAULT_OUTPUT_DIR

logger = logging.getLogger(__name__)


class OutletConfig(BaseModel):
    """
    Configuration for a single outlet point within a region.

    Each outlet represents a point (typically a stream gauge) for which
    a watershed will be delineated. Coordinates must be in WGS84 (EPSG:4326).
    """

    gauge_id: str = Field(..., description="Unique identifier for this outlet within the region")
    lat: float = Field(..., ge=-90, le=90, description="Latitude in decimal degrees (WGS84)")
    lng: float = Field(..., ge=-180, le=180, description="Longitude in decimal degrees (WGS84)")
    gauge_name: str = Field(default=DEFAULT_GAUGE_NAME, description="Human-readable name for the outlet")

    @field_validator("gauge_id")
    @classmethod
    def validate_gauge_id(cls, v: str) -> str:
        """Ensure gauge_id is not empty."""
        if not v or not v.strip():
            raise ValueError("gauge_id cannot be empty")
        return v.strip()

    @field_validator("gauge_name")
    @classmethod
    def validate_gauge_name(cls, v: str) -> str:
        """Normalize gauge_name by stripping whitespace."""
        return v.strip()


class RegionConfig(BaseModel):
    """
    Configuration for a region containing multiple outlets.

    Each region has a name (used for hive partitioning in output) and
    a path to a TOML file containing outlet configurations.
    """

    name: str = Field(..., description="Region name for organizing outputs (used in hive partitioning)")
    outlets: str = Field(..., description="Path to TOML file containing outlet configurations")

    @field_validator("name")
    @classmethod
    def validate_region_name(cls, v: str) -> str:
        """
        Validate region name is a valid identifier.

        Region names should be valid identifiers (alphanumeric + underscores)
        to work well with file systems and partitioning schemes.
        """
        if not v or not v.strip():
            raise ValueError("Region name cannot be empty")

        v = v.strip()

        # Check for valid identifier pattern
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9_]*$", v):
            raise ValueError(
                f"Region name '{v}' must be a valid identifier "
                "(start with letter, contain only letters, numbers, and underscores)"
            )

        return v

    @field_validator("outlets")
    @classmethod
    def validate_outlets_path(cls, v: str) -> str:
        """Ensure outlets path is not empty."""
        if not v or not v.strip():
            raise ValueError("Outlets path cannot be empty")
        return v.strip()


class OutletFileConfig(BaseModel):
    """
    Configuration structure for an outlets TOML file.

    This is the root model for region-specific TOML files that contain
    lists of outlet points.
    """

    outlets: list[OutletConfig] = Field(..., description="List of outlet configurations")

    @model_validator(mode="after")
    def validate_unique_gauge_ids(self) -> "OutletFileConfig":
        """Ensure all gauge_ids are unique within the region."""
        gauge_ids = [outlet.gauge_id for outlet in self.outlets]
        duplicates = [gid for gid in set(gauge_ids) if gauge_ids.count(gid) > 1]

        if duplicates:
            raise ValueError(f"Duplicate gauge_ids found in outlets file: {duplicates}")

        return self


class SettingsConfig(BaseModel):
    """
    Global settings for the delineation process.

    These settings apply across all regions and control overall behavior
    of the delineation workflow.
    """

    output_dir: str = Field(default=DEFAULT_OUTPUT_DIR, description="Base directory for all outputs")
    data_dir: str | None = Field(
        default=None, description="Directory containing MERIT-Hydro data (overrides DELINEATOR_DATA_DIR env var)"
    )
    max_fails: int | None = Field(default=DEFAULT_MAX_FAILS, description="Stop after N failures (None = unlimited)")
    fill_threshold: int = Field(
        default=DEFAULT_FILL_THRESHOLD,
        ge=0,
        description="Fill polygon holes smaller than N pixels (0 = fill all)"
    )

    @field_validator("output_dir")
    @classmethod
    def validate_output_dir(cls, v: str) -> str:
        """Validate output directory path is not empty."""
        if not v or not v.strip():
            raise ValueError("output_dir cannot be empty")
        return v.strip()

    @field_validator("max_fails")
    @classmethod
    def validate_max_fails(cls, v: int | None) -> int | None:
        """Ensure max_fails is positive if provided."""
        if v is not None and v <= 0:
            raise ValueError(f"max_fails must be positive, got {v}")
        return v


class MasterConfig(BaseModel):
    """
    Master configuration for the delineator CLI.

    This is the root configuration loaded from delineate.toml. It contains
    global settings and a list of regions to process.
    """

    settings: SettingsConfig = Field(default_factory=SettingsConfig, description="Global settings")
    regions: list[RegionConfig] = Field(..., description="List of regions to process")

    @model_validator(mode="after")
    def validate_unique_region_names(self) -> "MasterConfig":
        """Ensure all region names are unique."""
        region_names = [region.name for region in self.regions]
        duplicates = [name for name in set(region_names) if region_names.count(name) > 1]

        if duplicates:
            raise ValueError(f"Duplicate region names found: {duplicates}")

        return self

    @model_validator(mode="after")
    def validate_at_least_one_region(self) -> "MasterConfig":
        """Ensure at least one region is configured."""
        if not self.regions:
            raise ValueError("At least one region must be configured")

        return self


def load_config(config_path: Path) -> MasterConfig:
    """
    Load and validate a master configuration file.

    This function reads a TOML configuration file, validates it using Pydantic,
    and resolves relative paths for outlet files relative to the config file location.

    Args:
        config_path: Path to the master configuration TOML file (delineate.toml)

    Returns:
        Validated MasterConfig instance with resolved paths

    Raises:
        FileNotFoundError: If the config file doesn't exist
        tomllib.TOMLDecodeError: If the TOML file is malformed
        pydantic.ValidationError: If the configuration is invalid

    Example:
        >>> config = load_config(Path("delineate.toml"))
        >>> print(config.settings.output_dir)
        ./output
        >>> print(config.regions[0].name)
        camels_us
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    logger.info(f"Loading configuration from: {config_path}")

    # Read TOML file
    try:
        with config_path.open("rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"Invalid TOML in configuration file: {e}") from e

    # Parse with Pydantic
    config = MasterConfig.model_validate(data)

    # Resolve relative paths for outlet files
    config_dir = config_path.parent
    for region in config.regions:
        outlets_path = Path(region.outlets)

        # Make relative paths absolute relative to config file location
        if not outlets_path.is_absolute():
            resolved_path = (config_dir / outlets_path).resolve()
            region.outlets = str(resolved_path)
            logger.debug(f"Resolved outlets path for region '{region.name}': {resolved_path}")

    logger.info(f"Successfully loaded configuration with {len(config.regions)} region(s)")

    return config


def load_outlets(outlets_path: Path) -> list[OutletConfig]:
    """
    Load and validate an outlets configuration file.

    This function reads a region-specific TOML file containing outlet
    configurations and validates them.

    Args:
        outlets_path: Path to the outlets TOML file (e.g., camels_us.toml)

    Returns:
        List of validated OutletConfig instances

    Raises:
        FileNotFoundError: If the outlets file doesn't exist
        tomllib.TOMLDecodeError: If the TOML file is malformed
        pydantic.ValidationError: If the configuration is invalid

    Example:
        >>> outlets = load_outlets(Path("camels_us.toml"))
        >>> print(len(outlets))
        671
        >>> print(outlets[0].gauge_id)
        us_001
    """
    if not outlets_path.exists():
        raise FileNotFoundError(f"Outlets file not found: {outlets_path}")

    logger.info(f"Loading outlets from: {outlets_path}")

    # Read TOML file
    with outlets_path.open("rb") as f:
        data = tomllib.load(f)

    # Parse with Pydantic
    outlets_config = OutletFileConfig.model_validate(data)

    logger.info(f"Successfully loaded {len(outlets_config.outlets)} outlet(s)")

    return outlets_config.outlets

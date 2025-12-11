---
module: config
description: Configuration management using Pydantic schemas for TOML-based configuration files used by the delineator CLI.
---

## Files

- `schema.py` - Pydantic models for configuration validation and loading
- `defaults.py` - Default values and environment variable names
- `__init__.py` - Public API exports

## Key Interfaces

### Models

- `MasterConfig` - Root configuration from delineate.toml containing settings and regions
- `RegionConfig` - Configuration for a single region (name + outlets file path)
- `OutletConfig` - Configuration for a single outlet point with coordinates
- `OutletFileConfig` - Root model for outlets TOML files
- `SettingsConfig` - Global settings (output_dir, max_fails)

### Functions

- `load_config(path: Path) -> MasterConfig` - Load and validate master configuration
- `load_outlets(path: Path) -> list[OutletConfig]` - Load and validate outlets from region file

## Configuration Structure

### Master Configuration (delineate.toml)

```toml
[settings]
output_dir = "./output"
max_fails = 100

[[regions]]
name = "camels_us"
outlets = "camels_us.toml"
```

### Outlets Configuration (region.toml)

```toml
[[outlets]]
gauge_id = "us_001"
lat = 40.5416
lng = -105.2083
gauge_name = "Cache la Poudre River"
```

## Validation Rules

- All coordinates must be WGS84 (EPSG:4326): lat [-90, 90], lng [-180, 180]
- gauge_id must be unique within a region
- Region names must be valid identifiers (alphanumeric + underscores, start with letter)
- max_fails must be positive if provided
- Relative outlet paths are resolved relative to master config location

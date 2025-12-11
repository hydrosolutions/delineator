"""
Tests for the configuration module.

This module tests the Pydantic configuration schema for:
- Master configuration (delineate.toml)
- Outlets configuration (region.toml)
- Validation rules and error handling
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from delineator.config import (
    MasterConfig,
    OutletConfig,
    OutletFileConfig,
    RegionConfig,
    SettingsConfig,
    load_config,
    load_outlets,
)


class TestOutletConfig:
    """Tests for OutletConfig validation."""

    def test_valid_outlet(self):
        """Test valid outlet configuration."""
        outlet = OutletConfig(
            gauge_id="test_001",
            lat=40.5,
            lng=-105.2,
            gauge_name="Test Gauge",
        )
        assert outlet.gauge_id == "test_001"
        assert outlet.lat == 40.5
        assert outlet.lng == -105.2
        assert outlet.gauge_name == "Test Gauge"

    def test_outlet_without_name(self):
        """Test outlet with default empty name."""
        outlet = OutletConfig(gauge_id="test_001", lat=40.5, lng=-105.2)
        assert outlet.gauge_name == ""

    def test_outlet_coordinates_validation(self):
        """Test coordinate bounds validation."""
        # Valid coordinates at boundaries
        OutletConfig(gauge_id="test_001", lat=90, lng=180)
        OutletConfig(gauge_id="test_002", lat=-90, lng=-180)

        # Invalid latitude
        with pytest.raises(ValidationError, match="lat"):
            OutletConfig(gauge_id="test_003", lat=91, lng=0)

        with pytest.raises(ValidationError, match="lat"):
            OutletConfig(gauge_id="test_004", lat=-91, lng=0)

        # Invalid longitude
        with pytest.raises(ValidationError, match="lng"):
            OutletConfig(gauge_id="test_005", lat=0, lng=181)

        with pytest.raises(ValidationError, match="lng"):
            OutletConfig(gauge_id="test_006", lat=0, lng=-181)

    def test_empty_gauge_id(self):
        """Test that empty gauge_id is rejected."""
        with pytest.raises(ValidationError, match="gauge_id cannot be empty"):
            OutletConfig(gauge_id="", lat=40.5, lng=-105.2)

        with pytest.raises(ValidationError, match="gauge_id cannot be empty"):
            OutletConfig(gauge_id="   ", lat=40.5, lng=-105.2)

    def test_gauge_id_whitespace_stripped(self):
        """Test that gauge_id whitespace is stripped."""
        outlet = OutletConfig(gauge_id="  test_001  ", lat=40.5, lng=-105.2)
        assert outlet.gauge_id == "test_001"


class TestRegionConfig:
    """Tests for RegionConfig validation."""

    def test_valid_region(self):
        """Test valid region configuration."""
        region = RegionConfig(name="camels_us", outlets="camels_us.toml")
        assert region.name == "camels_us"
        assert region.outlets == "camels_us.toml"

    def test_region_name_validation(self):
        """Test region name identifier validation."""
        # Valid names
        RegionConfig(name="camels_us", outlets="test.toml")
        RegionConfig(name="CamelsUS", outlets="test.toml")
        RegionConfig(name="region_123", outlets="test.toml")
        RegionConfig(name="a", outlets="test.toml")

        # Invalid names - must start with letter
        with pytest.raises(ValidationError, match="must be a valid identifier"):
            RegionConfig(name="123_region", outlets="test.toml")

        # Invalid names - special characters
        with pytest.raises(ValidationError, match="must be a valid identifier"):
            RegionConfig(name="camels-us", outlets="test.toml")

        with pytest.raises(ValidationError, match="must be a valid identifier"):
            RegionConfig(name="camels.us", outlets="test.toml")

        # Empty name
        with pytest.raises(ValidationError, match="Region name cannot be empty"):
            RegionConfig(name="", outlets="test.toml")

    def test_empty_outlets_path(self):
        """Test that empty outlets path is rejected."""
        with pytest.raises(ValidationError, match="Outlets path cannot be empty"):
            RegionConfig(name="test", outlets="")


class TestOutletFileConfig:
    """Tests for OutletFileConfig validation."""

    def test_unique_gauge_ids(self):
        """Test that duplicate gauge_ids are rejected."""
        outlets = [
            OutletConfig(gauge_id="test_001", lat=40.5, lng=-105.2),
            OutletConfig(gauge_id="test_002", lat=39.7, lng=-105.0),
        ]
        OutletFileConfig(outlets=outlets)

        # Duplicate gauge_ids should fail
        outlets_dup = [
            OutletConfig(gauge_id="test_001", lat=40.5, lng=-105.2),
            OutletConfig(gauge_id="test_001", lat=39.7, lng=-105.0),
        ]
        with pytest.raises(ValidationError, match="Duplicate gauge_ids"):
            OutletFileConfig(outlets=outlets_dup)


class TestSettingsConfig:
    """Tests for SettingsConfig validation."""

    def test_default_settings(self):
        """Test default settings values."""
        settings = SettingsConfig()
        assert settings.output_dir == "./output"
        assert settings.max_fails is None

    def test_custom_settings(self):
        """Test custom settings values."""
        settings = SettingsConfig(output_dir="/custom/output", max_fails=50)
        assert settings.output_dir == "/custom/output"
        assert settings.max_fails == 50

    def test_invalid_max_fails(self):
        """Test that negative or zero max_fails is rejected."""
        with pytest.raises(ValidationError, match="max_fails must be positive"):
            SettingsConfig(max_fails=0)

        with pytest.raises(ValidationError, match="max_fails must be positive"):
            SettingsConfig(max_fails=-1)

    def test_empty_output_dir(self):
        """Test that empty output_dir is rejected."""
        with pytest.raises(ValidationError, match="output_dir cannot be empty"):
            SettingsConfig(output_dir="")


class TestMasterConfig:
    """Tests for MasterConfig validation."""

    def test_valid_master_config(self):
        """Test valid master configuration."""
        config = MasterConfig(
            settings=SettingsConfig(),
            regions=[
                RegionConfig(name="camels_us", outlets="camels_us.toml"),
                RegionConfig(name="camels_br", outlets="camels_br.toml"),
            ],
        )
        assert len(config.regions) == 2
        assert config.settings.output_dir == "./output"

    def test_unique_region_names(self):
        """Test that duplicate region names are rejected."""
        with pytest.raises(ValidationError, match="Duplicate region names"):
            MasterConfig(
                regions=[
                    RegionConfig(name="camels_us", outlets="file1.toml"),
                    RegionConfig(name="camels_us", outlets="file2.toml"),
                ]
            )

    def test_at_least_one_region(self):
        """Test that at least one region is required."""
        with pytest.raises(ValidationError, match="At least one region must be configured"):
            MasterConfig(regions=[])


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_valid_config(self, tmp_path: Path):
        """Test loading a valid configuration file."""
        # Create master config
        config_path = tmp_path / "delineate.toml"
        config_path.write_text("""
[settings]
output_dir = "./output"
max_fails = 100

[[regions]]
name = "test_region"
outlets = "outlets.toml"
""")

        # Load config
        config = load_config(config_path)
        assert config.settings.output_dir == "./output"
        assert config.settings.max_fails == 100
        assert len(config.regions) == 1
        assert config.regions[0].name == "test_region"

    def test_resolve_relative_paths(self, tmp_path: Path):
        """Test that relative outlet paths are resolved."""
        # Create config in a subdirectory
        config_dir = tmp_path / "configs"
        config_dir.mkdir()
        config_path = config_dir / "delineate.toml"

        config_path.write_text("""
[[regions]]
name = "test"
outlets = "outlets/test.toml"
""")

        config = load_config(config_path)

        # Path should be absolute and resolved relative to config file
        outlets_path = Path(config.regions[0].outlets)
        assert outlets_path.is_absolute()
        assert outlets_path == (config_dir / "outlets/test.toml").resolve()

    def test_absolute_paths_unchanged(self, tmp_path: Path):
        """Test that absolute outlet paths are not modified."""
        config_path = tmp_path / "delineate.toml"
        absolute_outlets_path = tmp_path / "outlets.toml"

        config_path.write_text(f"""
[[regions]]
name = "test"
outlets = "{absolute_outlets_path}"
""")

        config = load_config(config_path)
        assert Path(config.regions[0].outlets) == absolute_outlets_path

    def test_missing_config_file(self, tmp_path: Path):
        """Test error when config file doesn't exist."""
        config_path = tmp_path / "missing.toml"
        with pytest.raises(FileNotFoundError, match="Configuration file not found"):
            load_config(config_path)

    def test_invalid_toml(self, tmp_path: Path):
        """Test error with malformed TOML."""
        config_path = tmp_path / "invalid.toml"
        config_path.write_text("this is not valid toml [[[")

        with pytest.raises(ValueError, match="Invalid TOML"):
            load_config(config_path)


class TestLoadOutlets:
    """Tests for load_outlets function."""

    def test_load_valid_outlets(self, tmp_path: Path):
        """Test loading valid outlets file."""
        outlets_path = tmp_path / "outlets.toml"
        outlets_path.write_text("""
[[outlets]]
gauge_id = "test_001"
lat = 40.5
lng = -105.2
gauge_name = "Test Gauge 1"

[[outlets]]
gauge_id = "test_002"
lat = 39.7
lng = -105.0
""")

        outlets = load_outlets(outlets_path)
        assert len(outlets) == 2
        assert outlets[0].gauge_id == "test_001"
        assert outlets[0].gauge_name == "Test Gauge 1"
        assert outlets[1].gauge_id == "test_002"
        assert outlets[1].gauge_name == ""

    def test_missing_outlets_file(self, tmp_path: Path):
        """Test error when outlets file doesn't exist."""
        outlets_path = tmp_path / "missing.toml"
        with pytest.raises(FileNotFoundError, match="Outlets file not found"):
            load_outlets(outlets_path)

    def test_duplicate_gauge_ids(self, tmp_path: Path):
        """Test error with duplicate gauge_ids in outlets file."""
        outlets_path = tmp_path / "outlets.toml"
        outlets_path.write_text("""
[[outlets]]
gauge_id = "test_001"
lat = 40.5
lng = -105.2

[[outlets]]
gauge_id = "test_001"
lat = 39.7
lng = -105.0
""")

        with pytest.raises(ValidationError, match="Duplicate gauge_ids"):
            load_outlets(outlets_path)

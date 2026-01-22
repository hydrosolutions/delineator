"""
Tests for data availability checking.

Uses tmp_path fixture for filesystem operations and mocks for external dependencies.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from delineator.core.data_check import (
    DataAvailability,
    _get_expected_files,
    check_data_availability,
    ensure_data_available,
    get_required_basins,
)


class TestDataAvailability:
    """Tests for DataAvailability dataclass."""

    def test_all_available_when_no_missing(self) -> None:
        """all_available is True when missing_basins is empty."""
        availability = DataAvailability(
            available_basins=[41, 42],
            missing_basins=[],
            missing_files=[],
        )
        assert availability.all_available is True

    def test_not_all_available_when_missing(self) -> None:
        """all_available is False when missing_basins is not empty."""
        availability = DataAvailability(
            available_basins=[41],
            missing_basins=[42],
            missing_files=[Path("missing.tif")],
        )
        assert availability.all_available is False


class TestGetExpectedFiles:
    """Tests for _get_expected_files helper function."""

    def test_returns_all_files_by_default(self, tmp_path: Path) -> None:
        """Default should return both raster and vector files."""
        files = _get_expected_files(basin=42, data_dir=tmp_path)

        assert len(files) == 4
        # Check rasters
        assert any("flowdir42.tif" in str(f) for f in files)
        assert any("accum42.tif" in str(f) for f in files)
        # Check vectors
        assert any("cat_pfaf_42" in str(f) for f in files)
        assert any("riv_pfaf_42" in str(f) for f in files)

    def test_rasters_only(self, tmp_path: Path) -> None:
        """check_vectors=False should return only rasters."""
        files = _get_expected_files(basin=42, data_dir=tmp_path, check_rasters=True, check_vectors=False)

        assert len(files) == 2
        assert all("tif" in str(f) for f in files)

    def test_vectors_only(self, tmp_path: Path) -> None:
        """check_rasters=False should return only vectors."""
        files = _get_expected_files(basin=42, data_dir=tmp_path, check_rasters=False, check_vectors=True)

        assert len(files) == 2
        assert all("shp" in str(f) for f in files)

    def test_correct_path_structure(self, tmp_path: Path) -> None:
        """Paths should follow expected directory structure."""
        files = _get_expected_files(basin=42, data_dir=tmp_path)

        paths_as_str = [str(f) for f in files]

        # Verify directory structure
        assert any("raster/flowdir_basins" in p for p in paths_as_str)
        assert any("raster/accum_basins" in p for p in paths_as_str)
        assert any("shp/merit_catchments" in p for p in paths_as_str)
        assert any("shp/merit_rivers" in p for p in paths_as_str)


class TestCheckDataAvailability:
    """Tests for check_data_availability function."""

    def test_all_files_present(self, tmp_path: Path) -> None:
        """Test when all required files exist."""
        data_dir = tmp_path / "data"

        # Create all expected files
        (data_dir / "raster" / "flowdir_basins").mkdir(parents=True)
        (data_dir / "raster" / "accum_basins").mkdir(parents=True)
        (data_dir / "shp" / "merit_catchments").mkdir(parents=True)
        (data_dir / "shp" / "merit_rivers").mkdir(parents=True)
        (data_dir / "shp" / "catchments_simplified").mkdir(parents=True)

        (data_dir / "raster" / "flowdir_basins" / "flowdir42.tif").touch()
        (data_dir / "raster" / "accum_basins" / "accum42.tif").touch()
        (data_dir / "shp" / "merit_catchments" / "cat_pfaf_42_MERIT_Hydro_v07_Basins_v01.shp").touch()
        (data_dir / "shp" / "merit_rivers" / "riv_pfaf_42_MERIT_Hydro_v07_Basins_v01.shp").touch()
        (data_dir / "shp" / "catchments_simplified" / "simplified.shp").touch()

        result = check_data_availability(basins=[42], data_dir=data_dir)

        assert result.all_available
        assert result.available_basins == [42]
        assert result.missing_basins == []
        assert result.missing_files == []

    def test_missing_rasters(self, tmp_path: Path) -> None:
        """Test when raster files are missing."""
        data_dir = tmp_path / "data"

        # Create only vector directories (no rasters)
        (data_dir / "raster" / "flowdir_basins").mkdir(parents=True)
        (data_dir / "raster" / "accum_basins").mkdir(parents=True)
        (data_dir / "shp" / "merit_catchments").mkdir(parents=True)
        (data_dir / "shp" / "merit_rivers").mkdir(parents=True)
        (data_dir / "shp" / "catchments_simplified").mkdir(parents=True)
        (data_dir / "shp" / "catchments_simplified" / "file.shp").touch()

        # Create vector files only
        (data_dir / "shp" / "merit_catchments" / "cat_pfaf_42_MERIT_Hydro_v07_Basins_v01.shp").touch()
        (data_dir / "shp" / "merit_rivers" / "riv_pfaf_42_MERIT_Hydro_v07_Basins_v01.shp").touch()

        result = check_data_availability(basins=[42], data_dir=data_dir)

        assert not result.all_available
        assert result.missing_basins == [42]
        assert len(result.missing_files) == 2  # flowdir and accum

    def test_missing_simplified_directory(self, tmp_path: Path) -> None:
        """Test when simplified catchments directory is missing."""
        data_dir = tmp_path / "data"

        # Create all basin files but no simplified directory
        (data_dir / "raster" / "flowdir_basins").mkdir(parents=True)
        (data_dir / "raster" / "accum_basins").mkdir(parents=True)
        (data_dir / "shp" / "merit_catchments").mkdir(parents=True)
        (data_dir / "shp" / "merit_rivers").mkdir(parents=True)

        (data_dir / "raster" / "flowdir_basins" / "flowdir42.tif").touch()
        (data_dir / "raster" / "accum_basins" / "accum42.tif").touch()
        (data_dir / "shp" / "merit_catchments" / "cat_pfaf_42_MERIT_Hydro_v07_Basins_v01.shp").touch()
        (data_dir / "shp" / "merit_rivers" / "riv_pfaf_42_MERIT_Hydro_v07_Basins_v01.shp").touch()

        result = check_data_availability(basins=[42], data_dir=data_dir)

        # Basin is available but simplified is missing
        assert result.available_basins == [42]
        assert len(result.missing_files) == 1  # simplified directory

    def test_multiple_basins_partial_availability(self, tmp_path: Path) -> None:
        """Test with some basins available and some missing."""
        data_dir = tmp_path / "data"

        # Create directories
        for subdir in ["raster/flowdir_basins", "raster/accum_basins", "shp/merit_catchments", "shp/merit_rivers"]:
            (data_dir / subdir).mkdir(parents=True)
        (data_dir / "shp" / "catchments_simplified").mkdir(parents=True)
        (data_dir / "shp" / "catchments_simplified" / "file.shp").touch()

        # Create files for basin 42 only (not 45)
        (data_dir / "raster" / "flowdir_basins" / "flowdir42.tif").touch()
        (data_dir / "raster" / "accum_basins" / "accum42.tif").touch()
        (data_dir / "shp" / "merit_catchments" / "cat_pfaf_42_MERIT_Hydro_v07_Basins_v01.shp").touch()
        (data_dir / "shp" / "merit_rivers" / "riv_pfaf_42_MERIT_Hydro_v07_Basins_v01.shp").touch()

        result = check_data_availability(basins=[42, 45], data_dir=data_dir)

        assert not result.all_available
        assert 42 in result.available_basins
        assert 45 in result.missing_basins

    def test_selective_check_rasters_only(self, tmp_path: Path) -> None:
        """Test checking only rasters."""
        data_dir = tmp_path / "data"

        # Create only raster files
        (data_dir / "raster" / "flowdir_basins").mkdir(parents=True)
        (data_dir / "raster" / "accum_basins").mkdir(parents=True)
        (data_dir / "raster" / "flowdir_basins" / "flowdir42.tif").touch()
        (data_dir / "raster" / "accum_basins" / "accum42.tif").touch()

        result = check_data_availability(
            basins=[42],
            data_dir=data_dir,
            check_rasters=True,
            check_vectors=False,
            check_simplified=False,
        )

        assert result.all_available
        assert result.available_basins == [42]

    def test_empty_simplified_directory(self, tmp_path: Path) -> None:
        """Test that empty simplified directory counts as missing."""
        data_dir = tmp_path / "data"

        # Create directories including empty simplified
        for subdir in ["raster/flowdir_basins", "raster/accum_basins", "shp/merit_catchments", "shp/merit_rivers"]:
            (data_dir / subdir).mkdir(parents=True)
        (data_dir / "shp" / "catchments_simplified").mkdir(parents=True)  # Empty!

        # Create all basin files
        (data_dir / "raster" / "flowdir_basins" / "flowdir42.tif").touch()
        (data_dir / "raster" / "accum_basins" / "accum42.tif").touch()
        (data_dir / "shp" / "merit_catchments" / "cat_pfaf_42_MERIT_Hydro_v07_Basins_v01.shp").touch()
        (data_dir / "shp" / "merit_rivers" / "riv_pfaf_42_MERIT_Hydro_v07_Basins_v01.shp").touch()

        result = check_data_availability(basins=[42], data_dir=data_dir)

        # Simplified directory is empty, so should be listed as missing
        assert len(result.missing_files) == 1


class TestEnsureDataAvailable:
    """Tests for ensure_data_available with auto-download."""

    def test_returns_immediately_when_all_available(self, tmp_path: Path) -> None:
        """Test early return when all data is already available."""
        data_dir = tmp_path / "data"

        # Create all expected files
        for subdir in ["raster/flowdir_basins", "raster/accum_basins", "shp/merit_catchments", "shp/merit_rivers"]:
            (data_dir / subdir).mkdir(parents=True)
        (data_dir / "shp" / "catchments_simplified").mkdir(parents=True)
        (data_dir / "shp" / "catchments_simplified" / "file.shp").touch()

        (data_dir / "raster" / "flowdir_basins" / "flowdir42.tif").touch()
        (data_dir / "raster" / "accum_basins" / "accum42.tif").touch()
        (data_dir / "shp" / "merit_catchments" / "cat_pfaf_42_MERIT_Hydro_v07_Basins_v01.shp").touch()
        (data_dir / "shp" / "merit_rivers" / "riv_pfaf_42_MERIT_Hydro_v07_Basins_v01.shp").touch()

        with patch("delineator.core.data_check.download_data") as mock_download:
            result = ensure_data_available(basins=[42], data_dir=data_dir)

            # Download should not be called
            mock_download.assert_not_called()
            assert result.all_available

    def test_no_download_when_disabled(self, tmp_path: Path) -> None:
        """Test that download is not triggered when auto_download=False."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        with patch("delineator.core.data_check.download_data") as mock_download:
            result = ensure_data_available(
                basins=[42],
                data_dir=data_dir,
                auto_download=False,
            )

            mock_download.assert_not_called()
            assert not result.all_available

    def test_download_triggered_for_missing_data(self, tmp_path: Path) -> None:
        """Test that download is triggered when data is missing."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        mock_download_result = Mock()
        mock_download_result.success = True
        mock_download_result.errors = []

        with patch(
            "delineator.core.data_check.download_data",
            return_value=mock_download_result,
        ) as mock_download:
            ensure_data_available(
                basins=[42],
                data_dir=data_dir,
                auto_download=True,
            )

            # Download should be called with missing basins
            mock_download.assert_called_once()
            call_args = mock_download.call_args
            assert call_args.kwargs["basins"] == [42]

    def test_handles_download_errors(self, tmp_path: Path) -> None:
        """Test handling of download errors."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        mock_download_result = Mock()
        mock_download_result.success = False
        mock_download_result.errors = ["Error downloading basin 42"]

        with patch(
            "delineator.core.data_check.download_data",
            return_value=mock_download_result,
        ):
            result = ensure_data_available(
                basins=[42],
                data_dir=data_dir,
                auto_download=True,
            )

            # Should return availability status even if download failed
            assert not result.all_available

    def test_handles_download_exception(self, tmp_path: Path) -> None:
        """Test handling when download raises an exception."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        with patch(
            "delineator.core.data_check.download_data",
            side_effect=RuntimeError("Network error"),
        ):
            # Should not raise, should return availability status
            result = ensure_data_available(
                basins=[42],
                data_dir=data_dir,
                auto_download=True,
            )

            assert not result.all_available


class TestGetRequiredBasins:
    """Tests for determining required basins from outlets."""

    def test_single_outlet(self) -> None:
        """Test basin determination for a single outlet."""
        with patch(
            "delineator.core.data_check.get_basins_for_bbox",
            return_value=[42],
        ) as mock_get_basins:
            basins = get_required_basins([(40.5, -105.5)])

            assert basins == [42]
            mock_get_basins.assert_called_once()
            # Verify bbox args (min_lon, min_lat, max_lon, max_lat)
            call_kwargs = mock_get_basins.call_args.kwargs
            assert call_kwargs["min_lat"] == 40.5
            assert call_kwargs["max_lat"] == 40.5
            assert call_kwargs["min_lon"] == -105.5
            assert call_kwargs["max_lon"] == -105.5

    def test_multiple_outlets_bbox(self) -> None:
        """Test that bbox is computed correctly for multiple outlets."""
        outlets = [(40.0, -106.0), (42.0, -104.0)]

        with patch(
            "delineator.core.data_check.get_basins_for_bbox",
            return_value=[42],
        ) as mock_get_basins:
            get_required_basins(outlets)

            call_kwargs = mock_get_basins.call_args.kwargs
            assert call_kwargs["min_lat"] == 40.0
            assert call_kwargs["max_lat"] == 42.0
            assert call_kwargs["min_lon"] == -106.0
            assert call_kwargs["max_lon"] == -104.0

    def test_empty_outlets_raises(self) -> None:
        """Test that empty outlets list raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            get_required_basins([])

    def test_invalid_latitude_raises(self) -> None:
        """Test that invalid latitude raises ValueError."""
        with pytest.raises(ValueError, match="Invalid latitude"):
            get_required_basins([(100, 0)])  # lat > 90

        with pytest.raises(ValueError, match="Invalid latitude"):
            get_required_basins([(-100, 0)])  # lat < -90

    def test_invalid_longitude_raises(self) -> None:
        """Test that invalid longitude raises ValueError."""
        with pytest.raises(ValueError, match="Invalid longitude"):
            get_required_basins([(0, 200)])  # lon > 180

        with pytest.raises(ValueError, match="Invalid longitude"):
            get_required_basins([(0, -200)])  # lon < -180

    def test_boundary_coordinates_valid(self) -> None:
        """Test that boundary coordinates are accepted."""
        with patch(
            "delineator.core.data_check.get_basins_for_bbox",
            return_value=[42],
        ):
            # These should not raise
            get_required_basins([(90, 180)])  # Max valid
            get_required_basins([(-90, -180)])  # Min valid
            get_required_basins([(0, 0)])  # Origin

    def test_invalid_format_raises(self) -> None:
        """Test that invalid coordinate format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid outlet coordinates format"):
            get_required_basins([(1, 2, 3)])  # type: ignore[list-item] # Too many values

        with pytest.raises(ValueError, match="Invalid outlet coordinates format"):
            get_required_basins([1, 2])  # type: ignore[list-item] # Not tuples

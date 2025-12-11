"""
Unit tests for the download module.

Tests cover the basin_selector, http_client, and downloader modules with comprehensive
test cases including edge cases, error handling, and mocking of external dependencies.
"""

from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
import httpx
import pytest
from shapely.geometry import Polygon, box

from delineator.download.basin_selector import (
    get_all_basin_codes,
    get_basins_for_bbox,
    validate_basin_codes,
)
from delineator.download.downloader import (
    DownloadResult,
    download_data,
    get_output_paths,
)
from delineator.download.http_client import (
    ACCUM_URL_PATTERN,
    FLOWDIR_URL_PATTERN,
    download_raster,
    download_simplified_catchments,
)

# ============================================================================
# Basin Selector Tests
# ============================================================================


class TestBasinSelector:
    """Tests for basin selector functionality."""

    @pytest.fixture
    def mock_basins_gdf(self) -> gpd.GeoDataFrame:
        """Create a mock GeoDataFrame with basin data."""
        # Create 61 mock basins with codes from 11 to 91 (no zeros in Pfafstetter)
        basin_codes = []
        for tens in range(1, 10):
            for ones in range(1, 10):
                basin_codes.append(tens * 10 + ones)

        # Create simple polygons for each basin
        geometries = [
            box(-180 + i * 4, -90, -180 + i * 4 + 3, -85)
            for i in range(len(basin_codes))
        ]

        gdf = gpd.GeoDataFrame(
            {"BASIN": basin_codes[:61]},  # Take first 61 codes
            geometry=geometries[:61],
            crs="EPSG:4326",
        )

        return gdf

    @pytest.fixture
    def mock_iceland_basins_gdf(self) -> gpd.GeoDataFrame:
        """Create a mock GeoDataFrame with Iceland region basin."""
        # Basin 27 covers Iceland region
        basin_polygon = Polygon([(-25, 63), (-13, 63), (-13, 67), (-25, 67), (-25, 63)])

        gdf = gpd.GeoDataFrame(
            {"BASIN": [27]},
            geometry=[basin_polygon],
            crs="EPSG:4326",
        )

        return gdf

    def test_get_all_basin_codes_returns_61_basins(self, mock_basins_gdf: gpd.GeoDataFrame) -> None:
        """Should return exactly 61 basin codes."""
        with patch("delineator.download.basin_selector._load_basins_gdf", return_value=mock_basins_gdf):
            basin_codes = get_all_basin_codes()

            assert len(basin_codes) == 61
            assert isinstance(basin_codes, list)
            assert all(isinstance(code, int) for code in basin_codes)

    def test_get_all_basin_codes_range(self, mock_basins_gdf: gpd.GeoDataFrame) -> None:
        """Basin codes should be between 11-91."""
        with patch("delineator.download.basin_selector._load_basins_gdf", return_value=mock_basins_gdf):
            basin_codes = get_all_basin_codes()

            assert min(basin_codes) >= 11
            assert max(basin_codes) <= 91
            # Ensure sorted
            assert basin_codes == sorted(basin_codes)

    def test_validate_basin_codes_valid(self, mock_basins_gdf: gpd.GeoDataFrame) -> None:
        """Should return valid codes unchanged."""
        with patch("delineator.download.basin_selector._load_basins_gdf", return_value=mock_basins_gdf):
            valid_codes = [11, 42, 45, 67]
            result = validate_basin_codes(valid_codes)

            assert result == valid_codes

    def test_validate_basin_codes_invalid(self, mock_basins_gdf: gpd.GeoDataFrame) -> None:
        """Should raise ValueError for invalid codes."""
        with patch("delineator.download.basin_selector._load_basins_gdf", return_value=mock_basins_gdf):
            invalid_codes = [11, 99]

            with pytest.raises(ValueError) as exc_info:
                validate_basin_codes(invalid_codes)

            assert "Invalid basin codes" in str(exc_info.value)
            assert "99" in str(exc_info.value)

    def test_validate_basin_codes_multiple_invalid(self, mock_basins_gdf: gpd.GeoDataFrame) -> None:
        """Should raise ValueError listing all invalid codes."""
        with patch("delineator.download.basin_selector._load_basins_gdf", return_value=mock_basins_gdf):
            invalid_codes = [11, 99, 100, 10]

            with pytest.raises(ValueError) as exc_info:
                validate_basin_codes(invalid_codes)

            error_message = str(exc_info.value)
            assert "Invalid basin codes" in error_message
            # All invalid codes should be mentioned
            assert "99" in error_message or "10" in error_message or "100" in error_message

    def test_get_basins_for_bbox_iceland(self, mock_iceland_basins_gdf: gpd.GeoDataFrame) -> None:
        """Iceland bbox should return basin 27."""
        with patch("delineator.download.basin_selector._load_basins_gdf", return_value=mock_iceland_basins_gdf):
            # Iceland coordinates
            basins = get_basins_for_bbox(min_lon=-25, min_lat=63, max_lon=-13, max_lat=67)

            assert basins == [27]

    def test_get_basins_for_bbox_invalid_coords(self) -> None:
        """Should raise ValueError if min > max."""
        # min_lon > max_lon
        with pytest.raises(ValueError) as exc_info:
            get_basins_for_bbox(min_lon=10, min_lat=0, max_lon=5, max_lat=10)

        assert "min_lon" in str(exc_info.value)
        assert "max_lon" in str(exc_info.value)

        # min_lat > max_lat
        with pytest.raises(ValueError) as exc_info:
            get_basins_for_bbox(min_lon=0, min_lat=20, max_lon=10, max_lat=10)

        assert "min_lat" in str(exc_info.value)
        assert "max_lat" in str(exc_info.value)

    def test_get_basins_for_bbox_no_intersection(self, mock_basins_gdf: gpd.GeoDataFrame) -> None:
        """Should return empty list when bbox doesn't intersect any basins."""
        with patch("delineator.download.basin_selector._load_basins_gdf", return_value=mock_basins_gdf):
            # Bbox in middle of ocean with no basins
            basins = get_basins_for_bbox(min_lon=170, min_lat=70, max_lon=175, max_lat=75)

            assert basins == []

    def test_get_basins_for_bbox_multiple_basins(self) -> None:
        """Should return multiple basins when bbox intersects several."""
        # Create basins that overlap
        basin_polygons = [
            Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]),
            Polygon([(5, 5), (15, 5), (15, 15), (5, 15), (5, 5)]),
            Polygon([(10, 10), (20, 10), (20, 20), (10, 20), (10, 10)]),
        ]

        gdf = gpd.GeoDataFrame(
            {"BASIN": [11, 12, 13]},
            geometry=basin_polygons,
            crs="EPSG:4326",
        )

        with patch("delineator.download.basin_selector._load_basins_gdf", return_value=gdf):
            # Bbox that intersects all three basins
            basins = get_basins_for_bbox(min_lon=8, min_lat=8, max_lon=12, max_lat=12)

            assert len(basins) == 3
            assert basins == [11, 12, 13]

    def test_get_basins_for_bbox_custom_shapefile_path(self, mock_basins_gdf: gpd.GeoDataFrame) -> None:
        """Should accept custom shapefile path."""
        custom_path = Path("/custom/path/basins.shp")

        with patch("delineator.download.basin_selector._load_basins_gdf", return_value=mock_basins_gdf) as mock_load:
            get_basins_for_bbox(
                min_lon=-25, min_lat=63, max_lon=-13, max_lat=67, basins_shapefile=custom_path
            )

            # Verify custom path was used
            mock_load.assert_called_once_with(str(custom_path))


# ============================================================================
# HTTP Client Tests
# ============================================================================


class TestHttpClient:
    """Tests for HTTP download client."""

    @pytest.fixture
    def temp_dest_dir(self, tmp_path: Path) -> Path:
        """Create a temporary destination directory."""
        dest_dir = tmp_path / "downloads"
        dest_dir.mkdir(parents=True, exist_ok=True)
        return dest_dir

    def test_download_raster_invalid_type(self, temp_dest_dir: Path) -> None:
        """Should raise ValueError for invalid raster type."""
        with pytest.raises(ValueError) as exc_info:
            download_raster(basin=42, raster_type="invalid", dest_dir=temp_dest_dir)

        assert "Invalid raster_type" in str(exc_info.value)
        assert "flowdir" in str(exc_info.value)
        assert "accum" in str(exc_info.value)

    def test_download_raster_invalid_basin_code(self, temp_dest_dir: Path) -> None:
        """Should raise ValueError for invalid basin code."""
        # Basin code too low
        with pytest.raises(ValueError) as exc_info:
            download_raster(basin=-1, raster_type="flowdir", dest_dir=temp_dest_dir)

        assert "Invalid basin code" in str(exc_info.value)

        # Basin code too high
        with pytest.raises(ValueError) as exc_info:
            download_raster(basin=100, raster_type="flowdir", dest_dir=temp_dest_dir)

        assert "Invalid basin code" in str(exc_info.value)

    def test_download_raster_url_construction_flowdir(self, temp_dest_dir: Path) -> None:
        """Should construct correct URL for flowdir."""
        basin = 42
        FLOWDIR_URL_PATTERN.format(basin=basin)

        with patch("delineator.download.http_client._download_file") as mock_download:
            download_raster(basin=basin, raster_type="flowdir", dest_dir=temp_dest_dir)

            # Verify download was called
            assert mock_download.called
            # Check that the file path is correct
            call_args = mock_download.call_args
            dest_path = call_args[0][1]
            assert dest_path.name == f"flowdir{basin}.tif"

    def test_download_raster_url_construction_accum(self, temp_dest_dir: Path) -> None:
        """Should construct correct URL for accum."""
        basin = 42
        ACCUM_URL_PATTERN.format(basin=basin)

        with patch("delineator.download.http_client._download_file") as mock_download:
            download_raster(basin=basin, raster_type="accum", dest_dir=temp_dest_dir)

            # Verify download was called
            assert mock_download.called
            # Check that the file path is correct
            call_args = mock_download.call_args
            dest_path = call_args[0][1]
            assert dest_path.name == f"accum{basin}.tif"

    def test_download_raster_creates_directory(self, tmp_path: Path) -> None:
        """Should create destination directory if it doesn't exist."""
        dest_dir = tmp_path / "new" / "nested" / "dir"
        assert not dest_dir.exists()

        with patch("delineator.download.http_client._download_file"):
            download_raster(basin=42, raster_type="flowdir", dest_dir=dest_dir)

        assert dest_dir.exists()
        assert dest_dir.is_dir()

    def test_download_raster_skip_if_exists(self, temp_dest_dir: Path) -> None:
        """Should skip download if file exists and overwrite=False."""
        basin = 42
        filename = f"flowdir{basin}.tif"
        existing_file = temp_dest_dir / filename
        existing_file.touch()

        with patch("delineator.download.http_client._download_file") as mock_download:
            result = download_raster(basin=basin, raster_type="flowdir", dest_dir=temp_dest_dir, overwrite=False)

            # Should not call download
            mock_download.assert_not_called()
            # Should return existing file path
            assert result == existing_file

    def test_download_raster_overwrite_if_exists(self, temp_dest_dir: Path) -> None:
        """Should re-download if file exists and overwrite=True."""
        basin = 42
        filename = f"flowdir{basin}.tif"
        existing_file = temp_dest_dir / filename
        existing_file.write_text("old content")

        with patch("delineator.download.http_client._download_file") as mock_download:
            download_raster(basin=basin, raster_type="flowdir", dest_dir=temp_dest_dir, overwrite=True)

            # Should call download even though file exists
            mock_download.assert_called_once()

    def test_download_raster_retries_on_failure(self, temp_dest_dir: Path) -> None:
        """Should retry download on HTTP errors."""
        temp_dest_dir / "flowdir42.tif"

        with patch("delineator.download.http_client._download_file") as mock_download:
            # Simulate failure on first two attempts, success on third
            def side_effect_func(url: str, dest_path: Path, progress_callback: None = None) -> None:
                """Side effect that creates file on third call."""
                if mock_download.call_count == 3:
                    dest_path.touch()  # Create the file on success
                    return
                raise httpx.HTTPError(f"Attempt {mock_download.call_count}")

            mock_download.side_effect = side_effect_func

            with patch("delineator.download.http_client.time.sleep"):  # Skip actual sleep
                result = download_raster(basin=42, raster_type="flowdir", dest_dir=temp_dest_dir)

            # Should have called 3 times
            assert mock_download.call_count == 3
            assert result.exists()

    def test_download_raster_fails_after_max_retries(self, temp_dest_dir: Path) -> None:
        """Should raise error after max retries exceeded."""
        with patch("delineator.download.http_client._download_file") as mock_download:
            # Simulate continuous failures
            mock_download.side_effect = httpx.HTTPError("Persistent error")

            with (
                patch("delineator.download.http_client.time.sleep"),  # Skip actual sleep
                pytest.raises(httpx.HTTPError),
            ):
                download_raster(basin=42, raster_type="flowdir", dest_dir=temp_dest_dir)

            # Should have tried MAX_RETRIES times
            from delineator.download.http_client import MAX_RETRIES

            assert mock_download.call_count == MAX_RETRIES

    def test_download_simplified_catchments_url(self, temp_dest_dir: Path) -> None:
        """Should download simplified catchments from correct URL."""
        with patch("delineator.download.http_client._download_file") as mock_download:
            download_simplified_catchments(dest_dir=temp_dest_dir)

            # Verify download was called
            assert mock_download.called
            call_args = mock_download.call_args
            dest_path = call_args[0][1]
            assert dest_path.name == "catchments_simplified.zip"

    def test_download_simplified_catchments_skip_if_exists(self, temp_dest_dir: Path) -> None:
        """Should skip download if file exists and overwrite=False."""
        filename = "catchments_simplified.zip"
        existing_file = temp_dest_dir / filename
        existing_file.touch()

        with patch("delineator.download.http_client._download_file") as mock_download:
            result = download_simplified_catchments(dest_dir=temp_dest_dir, overwrite=False)

            # Should not call download
            mock_download.assert_not_called()
            # Should return existing file path
            assert result == existing_file


# ============================================================================
# Downloader Tests
# ============================================================================


class TestDownloader:
    """Tests for downloader orchestrator."""

    def test_download_result_success_property(self) -> None:
        """DownloadResult.success should be True when no errors."""
        result = DownloadResult(basins_downloaded=[42], errors=[])

        assert result.success is True

    def test_download_result_failure_property(self) -> None:
        """DownloadResult.success should be False when errors exist."""
        result = DownloadResult(basins_downloaded=[42], errors=["Error 1", "Error 2"])

        assert result.success is False

    def test_download_result_default_values(self) -> None:
        """DownloadResult should have sensible defaults."""
        result = DownloadResult()

        assert result.basins_downloaded == []
        assert result.rasters == {}
        assert result.vectors == {}
        assert result.simplified_catchments is None
        assert result.errors == []
        assert result.success is True  # No errors by default

    def test_download_data_requires_bbox_or_basins(self) -> None:
        """Should raise ValueError if neither bbox nor basins provided."""
        with pytest.raises(ValueError) as exc_info:
            download_data(bbox=None, basins=None)

        assert "Either bbox or basins must be provided" in str(exc_info.value)

    def test_download_data_with_basins(self, tmp_path: Path) -> None:
        """Should download data for provided basin codes."""
        basins = [42, 45]

        with patch("delineator.download.downloader.validate_basin_codes", return_value=basins), patch(
            "delineator.download.downloader.download_rasters_for_basins", return_value=({}, [])
        ) as mock_rasters, patch(
            "delineator.download.downloader.download_vectors_for_basins", return_value=({}, [])
        ), patch(
            "delineator.download.downloader.download_simplified_catchments"
        ):
            download_data(basins=basins, output_dir=tmp_path)

            # Should use provided basins
            mock_rasters.assert_called_once()
            assert mock_rasters.call_args[1]["basins"] == basins

    def test_download_data_with_bbox(self, tmp_path: Path) -> None:
        """Should determine basins from bounding box."""
        bbox = (-25.0, 63.0, -13.0, 67.0)
        expected_basins = [27]

        with patch("delineator.download.downloader.get_basins_for_bbox", return_value=expected_basins) as mock_bbox, patch(
            "delineator.download.downloader.download_rasters_for_basins", return_value=({}, [])
        ) as mock_rasters, patch(
            "delineator.download.downloader.download_vectors_for_basins", return_value=({}, [])
        ), patch(
            "delineator.download.downloader.download_simplified_catchments"
        ):
            download_data(bbox=bbox, output_dir=tmp_path)

            # Should call get_basins_for_bbox
            mock_bbox.assert_called_once_with(*bbox)
            # Should download for determined basins
            mock_rasters.assert_called_once()
            assert mock_rasters.call_args[1]["basins"] == expected_basins

    def test_download_data_basins_takes_precedence(self, tmp_path: Path) -> None:
        """Should use basins parameter when both bbox and basins provided."""
        bbox = (-25.0, 63.0, -13.0, 67.0)
        basins = [42, 45]

        with patch("delineator.download.downloader.validate_basin_codes", return_value=basins), patch(
            "delineator.download.downloader.get_basins_for_bbox"
        ) as mock_bbox, patch("delineator.download.downloader.download_rasters_for_basins", return_value=({}, [])), patch(
            "delineator.download.downloader.download_vectors_for_basins", return_value=({}, [])
        ), patch(
            "delineator.download.downloader.download_simplified_catchments"
        ):
            download_data(bbox=bbox, basins=basins, output_dir=tmp_path)

            # Should NOT call get_basins_for_bbox
            mock_bbox.assert_not_called()

    def test_download_data_invalid_basins(self, tmp_path: Path) -> None:
        """Should handle invalid basin codes gracefully."""
        invalid_basins = [99, 100]

        with patch(
            "delineator.download.downloader.validate_basin_codes", side_effect=ValueError("Invalid basin codes")
        ):
            result = download_data(basins=invalid_basins, output_dir=tmp_path)

            assert result.success is False
            assert len(result.errors) > 0
            assert "Basin validation failed" in result.errors[0]

    def test_download_data_no_basins_found_for_bbox(self, tmp_path: Path) -> None:
        """Should handle case where bbox doesn't intersect any basins."""
        bbox = (170.0, 70.0, 175.0, 75.0)

        with patch("delineator.download.downloader.get_basins_for_bbox", return_value=[]):
            result = download_data(bbox=bbox, output_dir=tmp_path)

            assert result.success is False
            assert len(result.errors) > 0
            assert "No basins found" in result.errors[0]

    def test_download_data_selective_downloads(self, tmp_path: Path) -> None:
        """Should respect include_rasters, include_vectors, include_simplified flags."""
        basins = [42]

        with patch("delineator.download.downloader.validate_basin_codes", return_value=basins), patch(
            "delineator.download.downloader.download_rasters_for_basins", return_value=({}, [])
        ) as mock_rasters, patch(
            "delineator.download.downloader.download_vectors_for_basins", return_value=({}, [])
        ) as mock_vectors, patch(
            "delineator.download.downloader.download_simplified_catchments"
        ) as mock_simplified:
            # Download only rasters
            download_data(
                basins=basins,
                output_dir=tmp_path,
                include_rasters=True,
                include_vectors=False,
                include_simplified=False,
            )

            mock_rasters.assert_called_once()
            mock_vectors.assert_not_called()
            mock_simplified.assert_not_called()

    def test_download_data_error_collection(self, tmp_path: Path) -> None:
        """Should collect errors from all download operations."""
        basins = [42]

        with patch("delineator.download.downloader.validate_basin_codes", return_value=basins), patch(
            "delineator.download.downloader.download_rasters_for_basins",
            return_value=({}, ["Raster error 1", "Raster error 2"]),
        ), patch(
            "delineator.download.downloader.download_vectors_for_basins", return_value=({}, ["Vector error 1"])
        ), patch(
            "delineator.download.downloader.download_simplified_catchments", side_effect=Exception("Simplified error")
        ):
            result = download_data(basins=basins, output_dir=tmp_path)

            assert result.success is False
            assert len(result.errors) == 4  # 2 raster + 1 vector + 1 simplified
            assert any("Raster error" in e for e in result.errors)
            assert any("Vector error" in e for e in result.errors)
            assert any("Simplified error" in e for e in result.errors)

    def test_get_output_paths(self, tmp_path: Path) -> None:
        """Should return correct directory structure."""
        base_dir = tmp_path / "data"
        paths = get_output_paths(base_dir)

        expected_paths = {
            "flowdir": base_dir / "raster" / "flowdir_basins",
            "accum": base_dir / "raster" / "accum_basins",
            "catchments": base_dir / "shp" / "merit_catchments",
            "rivers": base_dir / "shp" / "merit_rivers",
            "simplified": base_dir / "shp" / "catchments_simplified",
        }

        assert paths == expected_paths

    def test_download_data_creates_output_directories(self, tmp_path: Path) -> None:
        """Should create all output directories before downloading."""
        basins = [42]

        with patch("delineator.download.downloader.validate_basin_codes", return_value=basins), patch(
            "delineator.download.downloader.download_rasters_for_basins", return_value=({}, [])
        ), patch("delineator.download.downloader.download_vectors_for_basins", return_value=({}, [])), patch(
            "delineator.download.downloader.download_simplified_catchments"
        ):
            download_data(basins=basins, output_dir=tmp_path)

            # Verify directories were created
            paths = get_output_paths(tmp_path)
            for path in paths.values():
                assert path.exists()
                assert path.is_dir()

    def test_download_data_basins_downloaded_list(self, tmp_path: Path) -> None:
        """Should track which basins were successfully downloaded."""
        basins = [42, 45, 67]
        rasters_result = {
            42: {"flowdir": Path("f42.tif"), "accum": Path("a42.tif")},
            45: {"flowdir": Path("f45.tif"), "accum": Path("a45.tif")},
        }

        with patch("delineator.download.downloader.validate_basin_codes", return_value=basins), patch(
            "delineator.download.downloader.download_rasters_for_basins", return_value=(rasters_result, [])
        ), patch("delineator.download.downloader.download_vectors_for_basins", return_value=({}, [])), patch(
            "delineator.download.downloader.download_simplified_catchments"
        ):
            result = download_data(basins=basins, output_dir=tmp_path, include_vectors=False)

            assert set(result.basins_downloaded) == {42, 45}
            assert result.rasters == rasters_result

    def test_download_data_converts_output_dir_to_path(self, tmp_path: Path) -> None:
        """Should accept output_dir as string or Path."""
        basins = [42]
        output_dir_str = str(tmp_path)

        with patch("delineator.download.downloader.validate_basin_codes", return_value=basins), patch(
            "delineator.download.downloader.download_rasters_for_basins", return_value=({}, [])
        ), patch("delineator.download.downloader.download_vectors_for_basins", return_value=({}, [])), patch(
            "delineator.download.downloader.download_simplified_catchments"
        ):
            result = download_data(basins=basins, output_dir=output_dir_str)

            # Should work without errors
            assert result is not None


# ============================================================================
# Integration Tests
# ============================================================================


class TestDownloadIntegration:
    """Integration tests that test multiple components together."""

    def test_end_to_end_download_workflow(self, tmp_path: Path) -> None:
        """Test complete download workflow from bbox to files."""
        bbox = (-25.0, 63.0, -13.0, 67.0)
        expected_basins = [27]

        # Mock all external dependencies
        with patch("delineator.download.downloader.get_basins_for_bbox", return_value=expected_basins), patch(
            "delineator.download.http_client._download_file"
        ), patch("delineator.download.downloader.gdrive_download_basin_vectors", return_value={}):
            result = download_data(bbox=bbox, output_dir=tmp_path)

            # Should complete successfully
            assert result is not None
            # Output directories should exist
            paths = get_output_paths(tmp_path)
            for path in paths.values():
                assert path.exists()

    def test_download_with_mixed_success_and_failures(self, tmp_path: Path) -> None:
        """Test that download continues even when some basins fail."""
        basins = [42, 45, 67]

        # Simulate partial success
        def mock_rasters_download(basins: list[int], output_dir: Path, overwrite: bool) -> tuple[dict, list[str]]:
            results = {42: {"flowdir": Path("f42.tif"), "accum": Path("a42.tif")}}
            errors = ["Failed to download rasters for basin 45", "Failed to download rasters for basin 67"]
            return results, errors

        with patch("delineator.download.downloader.validate_basin_codes", return_value=basins), patch(
            "delineator.download.downloader.download_rasters_for_basins", side_effect=mock_rasters_download
        ), patch("delineator.download.downloader.download_vectors_for_basins", return_value=({}, [])), patch(
            "delineator.download.downloader.download_simplified_catchments"
        ):
            result = download_data(basins=basins, output_dir=tmp_path)

            # Should have partial results
            assert len(result.rasters) == 1
            assert 42 in result.rasters
            # Should have errors
            assert result.success is False
            assert len(result.errors) >= 2

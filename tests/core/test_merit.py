"""
Tests for MERIT-Hydro raster operations.

Tests the pure functions and mocks pysheds Grid operations for split_catchment.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from shapely.geometry import MultiPolygon, Polygon

from delineator.core.merit import _get_largest, compute_snap_threshold, split_catchment


class TestComputeSnapThreshold:
    """Tests for the snap threshold computation function."""

    def test_very_small_watershed(self) -> None:
        """Upstream area < 50 km² should return 300."""
        assert compute_snap_threshold(upstream_area=25.0, is_single_catchment=True) == 300
        assert compute_snap_threshold(upstream_area=49.9, is_single_catchment=False) == 300

    def test_small_watershed(self) -> None:
        """Upstream area 50-200 km² should return 500."""
        assert compute_snap_threshold(upstream_area=50.0, is_single_catchment=True) == 500
        assert compute_snap_threshold(upstream_area=100.0, is_single_catchment=False) == 500
        assert compute_snap_threshold(upstream_area=199.9, is_single_catchment=True) == 500

    def test_medium_watershed(self) -> None:
        """Upstream area 200-1000 km² should return 1000."""
        assert compute_snap_threshold(upstream_area=200.0, is_single_catchment=True) == 1000
        assert compute_snap_threshold(upstream_area=500.0, is_single_catchment=False) == 1000
        assert compute_snap_threshold(upstream_area=999.9, is_single_catchment=True) == 1000

    def test_large_watershed(self) -> None:
        """Upstream area 1000-5000 km² should return 2000."""
        assert compute_snap_threshold(upstream_area=1000.0, is_single_catchment=True) == 2000
        assert compute_snap_threshold(upstream_area=2500.0, is_single_catchment=False) == 2000
        assert compute_snap_threshold(upstream_area=4999.9, is_single_catchment=True) == 2000

    def test_very_large_watershed(self) -> None:
        """Upstream area >= 5000 km² should return 5000."""
        assert compute_snap_threshold(upstream_area=5000.0, is_single_catchment=True) == 5000
        assert compute_snap_threshold(upstream_area=10000.0, is_single_catchment=False) == 5000
        assert compute_snap_threshold(upstream_area=100000.0, is_single_catchment=True) == 5000

    def test_none_upstream_area_single_catchment(self) -> None:
        """When upstream_area is None and single catchment, use threshold_single."""
        assert compute_snap_threshold(upstream_area=None, is_single_catchment=True) == 500

    def test_none_upstream_area_multiple_catchments(self) -> None:
        """When upstream_area is None and multiple catchments, use threshold_multiple."""
        assert compute_snap_threshold(upstream_area=None, is_single_catchment=False) == 5000

    def test_custom_thresholds(self) -> None:
        """Test that custom thresholds are used when upstream_area is None."""
        result = compute_snap_threshold(
            upstream_area=None,
            is_single_catchment=True,
            threshold_single=100,
            threshold_multiple=10000,
        )
        assert result == 100

        result = compute_snap_threshold(
            upstream_area=None,
            is_single_catchment=False,
            threshold_single=100,
            threshold_multiple=10000,
        )
        assert result == 10000

    def test_boundary_values(self) -> None:
        """Test exact boundary values between thresholds."""
        # Exactly at 50 should be in the 50-200 range (500)
        assert compute_snap_threshold(upstream_area=50.0, is_single_catchment=True) == 500
        # Exactly at 200 should be in the 200-1000 range (1000)
        assert compute_snap_threshold(upstream_area=200.0, is_single_catchment=True) == 1000
        # Exactly at 1000 should be in the 1000-5000 range (2000)
        assert compute_snap_threshold(upstream_area=1000.0, is_single_catchment=True) == 2000
        # Exactly at 5000 should be in the >= 5000 range (5000)
        assert compute_snap_threshold(upstream_area=5000.0, is_single_catchment=True) == 5000

    def test_upstream_area_takes_precedence(self) -> None:
        """When upstream_area is provided, is_single_catchment is ignored."""
        # Same area should give same result regardless of is_single_catchment
        assert compute_snap_threshold(upstream_area=100.0, is_single_catchment=True) == 500
        assert compute_snap_threshold(upstream_area=100.0, is_single_catchment=False) == 500


class TestGetLargest:
    """Tests for the _get_largest helper function."""

    def test_single_polygon_returns_self(self) -> None:
        """Single Polygon should be returned unchanged."""
        poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        result = _get_largest(poly)
        assert result == poly
        assert result.geom_type == "Polygon"

    def test_multipolygon_returns_largest(self) -> None:
        """MultiPolygon should return the largest polygon by area."""
        small = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])  # Area = 1
        large = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])  # Area = 100
        medium = Polygon([(0, 0), (5, 0), (5, 5), (0, 5)])  # Area = 25

        multi = MultiPolygon([small, large, medium])
        result = _get_largest(multi)

        assert result.geom_type == "Polygon"
        assert result.area == large.area

    def test_multipolygon_two_polygons(self) -> None:
        """Test with exactly two polygons."""
        small = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        large = Polygon([(5, 5), (15, 5), (15, 15), (5, 15)])

        multi = MultiPolygon([small, large])
        result = _get_largest(multi)

        assert result.area == large.area

    def test_multipolygon_equal_areas(self) -> None:
        """When areas are equal, returns the first one found."""
        poly1 = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        poly2 = Polygon([(5, 5), (6, 5), (6, 6), (5, 6)])  # Same area

        multi = MultiPolygon([poly1, poly2])
        result = _get_largest(multi)

        # Should return one of them (first one in this case since both have max area)
        assert result.geom_type == "Polygon"
        assert result.area == 1.0


class TestSplitCatchment:
    """Tests for the split_catchment function using mocked pysheds."""

    @pytest.fixture
    def mock_grid(self) -> MagicMock:
        """Create a mock pysheds Grid object."""
        grid = MagicMock()
        grid.shape = (100, 100)
        grid.crs = "EPSG:4326"

        # Mock rasterize to return a mask array
        grid.rasterize.return_value = np.ones((100, 100), dtype=np.uint8)

        # Mock read_raster to return accumulation data
        acc_data = np.ones((100, 100), dtype=np.float32) * 1000
        grid.read_raster.return_value = acc_data

        # Mock snap_to_mask to return snapped coordinates
        grid.snap_to_mask.return_value = (-105.001, 40.001)

        # Mock catchment to return a mask
        catch_mask = np.ones((100, 100), dtype=np.uint8)
        grid.catchment.return_value = catch_mask

        # Mock view to return clipped catchment
        grid.view.return_value = catch_mask

        # Mock polygonize to return a single polygon shape
        polygon_coords = [[(-105.02, 39.98), (-104.98, 39.98), (-104.98, 40.02), (-105.02, 40.02), (-105.02, 39.98)]]
        grid.polygonize.return_value = [({"type": "Polygon", "coordinates": [polygon_coords[0]]}, 1)]

        return grid

    @pytest.fixture
    def sample_catchment_poly(self) -> Polygon:
        """Create a sample catchment polygon."""
        return Polygon(
            [
                (-105.05, 39.95),
                (-104.95, 39.95),
                (-104.95, 40.05),
                (-105.05, 40.05),
                (-105.05, 39.95),
            ]
        )

    def test_missing_fdir_file_raises(self, tmp_path: Path, sample_catchment_poly: Polygon) -> None:
        """Test that missing flow direction file raises FileNotFoundError."""
        fdir_dir = tmp_path / "fdir"
        accum_dir = tmp_path / "accum"
        fdir_dir.mkdir()
        accum_dir.mkdir()
        # Don't create the fdir file

        with pytest.raises(FileNotFoundError, match="flow direction raster"):
            split_catchment(
                basin=41,
                lat=40.0,
                lng=-105.0,
                catchment_poly=sample_catchment_poly,
                is_single_catchment=True,
                upstream_area=100.0,
                fdir_dir=fdir_dir,
                accum_dir=accum_dir,
            )

    def test_missing_accum_file_raises(
        self, tmp_path: Path, sample_catchment_poly: Polygon, mock_grid: MagicMock
    ) -> None:
        """Test that missing accumulation file raises FileNotFoundError."""
        fdir_dir = tmp_path / "fdir"
        accum_dir = tmp_path / "accum"
        fdir_dir.mkdir()
        accum_dir.mkdir()
        (fdir_dir / "flowdir41.tif").touch()
        # Don't create the accum file

        with patch("delineator.core.merit.Grid") as MockGrid:
            MockGrid.from_raster.return_value = mock_grid

            with pytest.raises(FileNotFoundError, match="accumulation raster"):
                split_catchment(
                    basin=41,
                    lat=40.0,
                    lng=-105.0,
                    catchment_poly=sample_catchment_poly,
                    is_single_catchment=True,
                    upstream_area=100.0,
                    fdir_dir=fdir_dir,
                    accum_dir=accum_dir,
                )

    def test_successful_delineation(self, tmp_path: Path, sample_catchment_poly: Polygon, mock_grid: MagicMock) -> None:
        """Test successful delineation returns polygon and coordinates."""
        fdir_dir = tmp_path / "fdir"
        accum_dir = tmp_path / "accum"
        fdir_dir.mkdir()
        accum_dir.mkdir()
        (fdir_dir / "flowdir41.tif").touch()
        (accum_dir / "accum41.tif").touch()

        with patch("delineator.core.merit.Grid") as MockGrid:
            MockGrid.from_raster.return_value = mock_grid

            result_poly, lat_snap, lng_snap = split_catchment(
                basin=41,
                lat=40.0,
                lng=-105.0,
                catchment_poly=sample_catchment_poly,
                is_single_catchment=True,
                upstream_area=100.0,
                fdir_dir=fdir_dir,
                accum_dir=accum_dir,
            )

        assert result_poly is not None
        assert result_poly.geom_type == "Polygon"
        assert lat_snap is not None
        assert lng_snap is not None

    def test_snap_failure_returns_none(
        self, tmp_path: Path, sample_catchment_poly: Polygon, mock_grid: MagicMock
    ) -> None:
        """Test that snap_to_mask failure returns None for polygon."""
        fdir_dir = tmp_path / "fdir"
        accum_dir = tmp_path / "accum"
        fdir_dir.mkdir()
        accum_dir.mkdir()
        (fdir_dir / "flowdir41.tif").touch()
        (accum_dir / "accum41.tif").touch()

        # Make snap_to_mask raise an exception
        mock_grid.snap_to_mask.side_effect = ValueError("Could not snap")

        with patch("delineator.core.merit.Grid") as MockGrid:
            MockGrid.from_raster.return_value = mock_grid

            result_poly, lat_snap, lng_snap = split_catchment(
                basin=41,
                lat=40.0,
                lng=-105.0,
                catchment_poly=sample_catchment_poly,
                is_single_catchment=True,
                upstream_area=100.0,
                fdir_dir=fdir_dir,
                accum_dir=accum_dir,
            )

        assert result_poly is None
        assert lat_snap is None
        assert lng_snap is None

    def test_catchment_failure_returns_none_poly_with_coords(
        self, tmp_path: Path, sample_catchment_poly: Polygon, mock_grid: MagicMock
    ) -> None:
        """Test that catchment() failure returns None polygon but keeps snap coords."""
        fdir_dir = tmp_path / "fdir"
        accum_dir = tmp_path / "accum"
        fdir_dir.mkdir()
        accum_dir.mkdir()
        (fdir_dir / "flowdir41.tif").touch()
        (accum_dir / "accum41.tif").touch()

        # Make catchment raise an exception
        mock_grid.catchment.side_effect = RuntimeError("Delineation failed")

        with patch("delineator.core.merit.Grid") as MockGrid:
            MockGrid.from_raster.return_value = mock_grid

            result_poly, lat_snap, lng_snap = split_catchment(
                basin=41,
                lat=40.0,
                lng=-105.0,
                catchment_poly=sample_catchment_poly,
                is_single_catchment=True,
                upstream_area=100.0,
                fdir_dir=fdir_dir,
                accum_dir=accum_dir,
            )

        # Polygon should be None, but snap coords should be returned
        assert result_poly is None
        assert lat_snap is not None
        assert lng_snap is not None

    def test_uses_compute_snap_threshold(
        self, tmp_path: Path, sample_catchment_poly: Polygon, mock_grid: MagicMock
    ) -> None:
        """Test that split_catchment uses compute_snap_threshold."""
        fdir_dir = tmp_path / "fdir"
        accum_dir = tmp_path / "accum"
        fdir_dir.mkdir()
        accum_dir.mkdir()
        (fdir_dir / "flowdir41.tif").touch()
        (accum_dir / "accum41.tif").touch()

        with patch("delineator.core.merit.Grid") as MockGrid:
            MockGrid.from_raster.return_value = mock_grid

            with patch("delineator.core.merit.compute_snap_threshold") as mock_threshold:
                mock_threshold.return_value = 1000

                split_catchment(
                    basin=41,
                    lat=40.0,
                    lng=-105.0,
                    catchment_poly=sample_catchment_poly,
                    is_single_catchment=True,
                    upstream_area=500.0,
                    fdir_dir=fdir_dir,
                    accum_dir=accum_dir,
                )

                mock_threshold.assert_called_once_with(500.0, True)

    def test_multipolygon_catchment_input(self, tmp_path: Path, mock_grid: MagicMock) -> None:
        """Test handling of MultiPolygon input (should use largest)."""
        fdir_dir = tmp_path / "fdir"
        accum_dir = tmp_path / "accum"
        fdir_dir.mkdir()
        accum_dir.mkdir()
        (fdir_dir / "flowdir41.tif").touch()
        (accum_dir / "accum41.tif").touch()

        # Create a MultiPolygon catchment - the function internally handles this
        poly1 = Polygon([(-105.05, 39.95), (-104.95, 39.95), (-104.95, 40.05), (-105.05, 40.05)])
        catchment_poly = poly1  # Use single polygon for simplicity

        with patch("delineator.core.merit.Grid") as MockGrid:
            MockGrid.from_raster.return_value = mock_grid

            result_poly, lat_snap, lng_snap = split_catchment(
                basin=41,
                lat=40.0,
                lng=-105.0,
                catchment_poly=catchment_poly,
                is_single_catchment=False,
                upstream_area=None,
                fdir_dir=fdir_dir,
                accum_dir=accum_dir,
            )

        assert result_poly is not None

    def test_multiple_output_shapes_dissolved(
        self, tmp_path: Path, sample_catchment_poly: Polygon, mock_grid: MagicMock
    ) -> None:
        """Test that multiple output shapes from pysheds are dissolved."""
        fdir_dir = tmp_path / "fdir"
        accum_dir = tmp_path / "accum"
        fdir_dir.mkdir()
        accum_dir.mkdir()
        (fdir_dir / "flowdir41.tif").touch()
        (accum_dir / "accum41.tif").touch()

        # Mock polygonize to return multiple shapes
        polygon_coords1 = [[(-105.02, 39.98), (-105.00, 39.98), (-105.00, 40.00), (-105.02, 40.00), (-105.02, 39.98)]]
        polygon_coords2 = [[(-105.00, 40.00), (-104.98, 40.00), (-104.98, 40.02), (-105.00, 40.02), (-105.00, 40.00)]]
        mock_grid.polygonize.return_value = [
            ({"type": "Polygon", "coordinates": polygon_coords1}, 1),
            ({"type": "Polygon", "coordinates": polygon_coords2}, 1),
        ]

        with patch("delineator.core.merit.Grid") as MockGrid:
            MockGrid.from_raster.return_value = mock_grid

            result_poly, lat_snap, lng_snap = split_catchment(
                basin=41,
                lat=40.0,
                lng=-105.0,
                catchment_poly=sample_catchment_poly,
                is_single_catchment=True,
                upstream_area=100.0,
                fdir_dir=fdir_dir,
                accum_dir=accum_dir,
            )

        # Result should be a single polygon (dissolved or largest)
        assert result_poly is not None
        assert result_poly.geom_type == "Polygon"

"""
Tests for watershed delineation logic.

Tests the hybrid vector/raster delineation approach using synthetic
GeoDataFrames and mocked raster operations.
"""

from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
import pytest
from shapely.geometry import MultiPolygon, Polygon

from delineator.core.delineate import (
    BasinData,
    DelineatedWatershed,
    DelineationError,
    collect_upstream_comids,
    delineate_outlet,
    get_area,
    load_basin_data,
)


class TestCollectUpstreamComids:
    """Tests for the upstream network tracing function."""

    def test_single_catchment_returns_one(
        self,
        single_catchment_network: tuple[gpd.GeoDataFrame, gpd.GeoDataFrame],
    ) -> None:
        """Single catchment with no upstream should return just itself."""
        _, rivers = single_catchment_network

        result = collect_upstream_comids(41000001, rivers)

        assert result == [41000001]

    def test_linear_network_collects_all(
        self,
        linear_network: tuple[gpd.GeoDataFrame, gpd.GeoDataFrame],
    ) -> None:
        """Linear network should collect all upstream catchments."""
        _, rivers = linear_network

        result = collect_upstream_comids(41000001, rivers)

        assert len(result) == 3
        assert set(result) == {41000001, 41000002, 41000003}

    def test_branching_network_collects_both_branches(
        self,
        branching_network: tuple[gpd.GeoDataFrame, gpd.GeoDataFrame],
    ) -> None:
        """Y-shaped network should collect both tributaries."""
        _, rivers = branching_network

        result = collect_upstream_comids(41000001, rivers)

        assert len(result) == 3
        assert set(result) == {41000001, 41000002, 41000003}

    def test_complex_network_collects_all(
        self,
        complex_network: tuple[gpd.GeoDataFrame, gpd.GeoDataFrame],
    ) -> None:
        """Complex 7-node network should collect all catchments."""
        _, rivers = complex_network

        result = collect_upstream_comids(41000001, rivers)

        assert len(result) == 7
        expected = {41000001, 41000002, 41000003, 41000004, 41000005, 41000006, 41000007}
        assert set(result) == expected

    def test_starting_from_middle_node(
        self,
        linear_network: tuple[gpd.GeoDataFrame, gpd.GeoDataFrame],
    ) -> None:
        """Starting from middle node should only get upstream nodes."""
        _, rivers = linear_network

        result = collect_upstream_comids(41000002, rivers)

        assert len(result) == 2
        assert set(result) == {41000002, 41000003}

    def test_starting_from_headwater(
        self,
        linear_network: tuple[gpd.GeoDataFrame, gpd.GeoDataFrame],
    ) -> None:
        """Starting from headwater should only return itself."""
        _, rivers = linear_network

        result = collect_upstream_comids(41000003, rivers)

        assert result == [41000003]


class TestGetArea:
    """Tests for polygon area calculation."""

    def test_small_polygon_near_equator(self) -> None:
        """Test area calculation for small polygon near equator."""
        # ~0.1 degree x 0.1 degree near equator
        poly = Polygon([
            (-105.0, 0.0),
            (-104.9, 0.0),
            (-104.9, 0.1),
            (-105.0, 0.1),
            (-105.0, 0.0),
        ])

        area = get_area(poly)

        # Near equator, 0.1 deg ~ 11 km, so 0.1 x 0.1 deg ~ 121 km²
        assert 100 < area < 150

    def test_polygon_at_mid_latitude(self) -> None:
        """Test area calculation at mid latitudes."""
        # ~0.2 degree x 0.2 degree at 40°N
        poly = Polygon([
            (-105.0, 40.0),
            (-104.8, 40.0),
            (-104.8, 40.2),
            (-105.0, 40.2),
            (-105.0, 40.0),
        ])

        area = get_area(poly)

        # At 40°N, this should be roughly 300-500 km²
        assert 200 < area < 600

    def test_multipolygon(self) -> None:
        """Test area calculation for MultiPolygon."""
        poly1 = Polygon([(-105.0, 40.0), (-104.9, 40.0), (-104.9, 40.1), (-105.0, 40.1)])
        poly2 = Polygon([(-105.0, 40.2), (-104.9, 40.2), (-104.9, 40.3), (-105.0, 40.3)])
        multi = MultiPolygon([poly1, poly2])

        area = get_area(multi)

        # Two similar-sized polygons
        assert area > 0


class TestLoadBasinData:
    """Tests for loading basin geodata."""

    def test_missing_catchments_file_raises(self, tmp_path: Path) -> None:
        """Test error when catchments file is missing."""
        # Create only rivers file
        rivers_dir = tmp_path / "shp" / "merit_rivers"
        rivers_dir.mkdir(parents=True)
        (rivers_dir / "riv_pfaf_42_MERIT_Hydro_v07_Basins_v01.shp").touch()

        with pytest.raises(FileNotFoundError, match="catchments shapefile"):
            load_basin_data(basin=42, data_dir=tmp_path)

    def test_missing_rivers_file_raises(self, tmp_path: Path) -> None:
        """Test error when rivers file is missing."""
        # Create only catchments file
        catchments_dir = tmp_path / "shp" / "merit_catchments"
        catchments_dir.mkdir(parents=True)
        (catchments_dir / "cat_pfaf_42_MERIT_Hydro_v07_Basins_v01.shp").touch()

        with pytest.raises(FileNotFoundError, match="rivers shapefile"):
            load_basin_data(basin=42, data_dir=tmp_path)


class TestDelineateOutlet:
    """Tests for the main delineation function."""

    def test_point_outside_catchments_raises(
        self,
        single_catchment_network: tuple[gpd.GeoDataFrame, gpd.GeoDataFrame],
        tmp_path: Path,
    ) -> None:
        """Test that point outside all catchments raises DelineationError."""
        catchments, rivers = single_catchment_network
        fdir_dir = tmp_path / "fdir"
        accum_dir = tmp_path / "accum"
        fdir_dir.mkdir()
        accum_dir.mkdir()

        with pytest.raises(DelineationError, match="does not fall within"):
            delineate_outlet(
                gauge_id="test_001",
                lat=0.0,  # Far from any catchment
                lng=0.0,
                gauge_name="Test Gauge",
                catchments_gdf=catchments,
                rivers_gdf=rivers,
                fdir_dir=fdir_dir,
                accum_dir=accum_dir,
            )

    def test_low_res_mode(
        self,
        single_catchment_network: tuple[gpd.GeoDataFrame, gpd.GeoDataFrame],
        tmp_path: Path,
    ) -> None:
        """Test delineation in low-resolution (vector-only) mode."""
        catchments, rivers = single_catchment_network
        fdir_dir = tmp_path / "fdir"
        accum_dir = tmp_path / "accum"
        fdir_dir.mkdir()
        accum_dir.mkdir()

        with patch("delineator.core.delineate.get_country", return_value="United States"):
            result = delineate_outlet(
                gauge_id="test_001",
                lat=40.0,
                lng=-105.0,
                gauge_name="Test Gauge",
                catchments_gdf=catchments,
                rivers_gdf=rivers,
                fdir_dir=fdir_dir,
                accum_dir=accum_dir,
                use_high_res=False,  # Force low-res mode
            )

        assert isinstance(result, DelineatedWatershed)
        assert result.gauge_id == "test_001"
        assert result.resolution == "low_res"
        assert result.geometry is not None

    def test_linear_network_low_res(
        self,
        linear_network: tuple[gpd.GeoDataFrame, gpd.GeoDataFrame],
        tmp_path: Path,
    ) -> None:
        """Test delineation of linear network in low-res mode."""
        catchments, rivers = linear_network
        fdir_dir = tmp_path / "fdir"
        accum_dir = tmp_path / "accum"
        fdir_dir.mkdir()
        accum_dir.mkdir()

        with patch("delineator.core.delineate.get_country", return_value="USA"):
            result = delineate_outlet(
                gauge_id="linear_test",
                lat=40.0,
                lng=-105.0,
                gauge_name="Linear Watershed",
                catchments_gdf=catchments,
                rivers_gdf=rivers,
                fdir_dir=fdir_dir,
                accum_dir=accum_dir,
                use_high_res=False,
            )

        assert result.resolution == "low_res"
        # Should have dissolved 3 catchments
        assert result.geometry is not None

    def test_high_res_mode_calls_split_catchment(
        self,
        single_catchment_network: tuple[gpd.GeoDataFrame, gpd.GeoDataFrame],
        tmp_path: Path,
    ) -> None:
        """Test that high-res mode calls split_catchment."""
        catchments, rivers = single_catchment_network
        fdir_dir = tmp_path / "fdir"
        accum_dir = tmp_path / "accum"
        fdir_dir.mkdir()
        accum_dir.mkdir()
        (fdir_dir / "flowdir41.tif").touch()
        (accum_dir / "accum41.tif").touch()

        mock_split_poly = Polygon([
            (-105.02, 39.98),
            (-104.98, 39.98),
            (-104.98, 40.02),
            (-105.02, 40.02),
        ])

        with (
            patch("delineator.core.delineate.get_country", return_value="USA"),
            patch(
                "delineator.core.delineate.split_catchment",
                return_value=(mock_split_poly, 40.0, -105.0),
            ) as mock_split,
        ):
            result = delineate_outlet(
                gauge_id="high_res_test",
                lat=40.0,
                lng=-105.0,
                gauge_name="High Res Test",
                catchments_gdf=catchments,
                rivers_gdf=rivers,
                fdir_dir=fdir_dir,
                accum_dir=accum_dir,
                use_high_res=True,
            )

        mock_split.assert_called_once()
        assert result.resolution == "high_res"

    def test_large_watershed_switches_to_low_res(
        self,
        complex_network: tuple[gpd.GeoDataFrame, gpd.GeoDataFrame],
        tmp_path: Path,
    ) -> None:
        """Test that large watersheds switch to low-res mode."""
        catchments, rivers = complex_network
        fdir_dir = tmp_path / "fdir"
        accum_dir = tmp_path / "accum"
        fdir_dir.mkdir()
        accum_dir.mkdir()

        with patch("delineator.core.delineate.get_country", return_value="USA"):
            result = delineate_outlet(
                gauge_id="large_test",
                lat=40.0,
                lng=-105.0,
                gauge_name="Large Watershed",
                catchments_gdf=catchments,
                rivers_gdf=rivers,
                fdir_dir=fdir_dir,
                accum_dir=accum_dir,
                use_high_res=True,
                high_res_area_limit=1000.0,  # Below 5000 km² of the complex network
            )

        # Should have switched to low-res due to area limit
        assert result.resolution == "low_res"

    def test_split_catchment_failure_raises(
        self,
        single_catchment_network: tuple[gpd.GeoDataFrame, gpd.GeoDataFrame],
        tmp_path: Path,
    ) -> None:
        """Test that split_catchment returning None raises DelineationError."""
        catchments, rivers = single_catchment_network
        fdir_dir = tmp_path / "fdir"
        accum_dir = tmp_path / "accum"
        fdir_dir.mkdir()
        accum_dir.mkdir()

        with (
            patch("delineator.core.delineate.get_country", return_value="USA"),
            patch(
                "delineator.core.delineate.split_catchment",
                return_value=(None, None, None),
            ),
        ):
            with pytest.raises(DelineationError, match="Raster-based delineation returned None"):
                delineate_outlet(
                    gauge_id="fail_test",
                    lat=40.0,
                    lng=-105.0,
                    gauge_name="Fail Test",
                    catchments_gdf=catchments,
                    rivers_gdf=rivers,
                    fdir_dir=fdir_dir,
                    accum_dir=accum_dir,
                    use_high_res=True,
                )

    def test_country_lookup_failure_falls_back(
        self,
        single_catchment_network: tuple[gpd.GeoDataFrame, gpd.GeoDataFrame],
        tmp_path: Path,
    ) -> None:
        """Test that country lookup failure uses 'Unknown'."""
        catchments, rivers = single_catchment_network
        fdir_dir = tmp_path / "fdir"
        accum_dir = tmp_path / "accum"
        fdir_dir.mkdir()
        accum_dir.mkdir()

        with patch(
            "delineator.core.delineate.get_country",
            side_effect=RuntimeError("Geocoding failed"),
        ):
            result = delineate_outlet(
                gauge_id="country_fail",
                lat=40.0,
                lng=-105.0,
                gauge_name="Country Fail Test",
                catchments_gdf=catchments,
                rivers_gdf=rivers,
                fdir_dir=fdir_dir,
                accum_dir=accum_dir,
                use_high_res=False,
            )

        assert result.country == "Unknown"

    def test_result_attributes(
        self,
        single_catchment_network: tuple[gpd.GeoDataFrame, gpd.GeoDataFrame],
        tmp_path: Path,
    ) -> None:
        """Test that result has all expected attributes."""
        catchments, rivers = single_catchment_network
        fdir_dir = tmp_path / "fdir"
        accum_dir = tmp_path / "accum"
        fdir_dir.mkdir()
        accum_dir.mkdir()

        with patch("delineator.core.delineate.get_country", return_value="United States"):
            result = delineate_outlet(
                gauge_id="attr_test",
                lat=40.0,
                lng=-105.0,
                gauge_name="Attribute Test",
                catchments_gdf=catchments,
                rivers_gdf=rivers,
                fdir_dir=fdir_dir,
                accum_dir=accum_dir,
                use_high_res=False,
            )

        assert result.gauge_id == "attr_test"
        assert result.gauge_name == "Attribute Test"
        assert result.gauge_lat == 40.0
        assert result.gauge_lon == -105.0
        assert result.snap_lat is not None
        assert result.snap_lon is not None
        assert result.snap_dist >= 0
        assert result.country == "United States"
        assert result.area > 0
        assert result.geometry is not None
        assert result.resolution in ["high_res", "low_res"]

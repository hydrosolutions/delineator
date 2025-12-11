"""
Tests for polygon dissolve and hole-filling operations.

These tests use pure geometry fixtures without external dependencies.
"""

import geopandas as gpd
import pytest
from shapely.geometry import MultiPolygon, Polygon, box

from delineator.core.dissolve import (
    buffer,
    close_holes,
    dissolve_geopandas,
    fill_geopandas,
)


class TestBuffer:
    """Tests for buffer cleaning function."""

    def test_cleans_simple_polygon(self) -> None:
        """Buffer operation should not significantly change a clean polygon."""
        poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])
        result = buffer(poly)

        assert result.is_valid
        # Area should be approximately the same (within buffer tolerance)
        assert abs(result.area - poly.area) < 0.01

    def test_fixes_self_intersecting_polygon(self) -> None:
        """Buffer operation should fix self-intersection issues."""
        # Create a self-intersecting polygon (bowtie shape)
        poly = Polygon([(0, 0), (10, 10), (10, 0), (0, 10), (0, 0)])

        # Buffer should return a valid polygon
        result = buffer(poly)
        assert result.is_valid

    def test_returns_polygon_type(self) -> None:
        """Buffer should return a Polygon."""
        poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
        result = buffer(poly)

        assert isinstance(result, Polygon)


class TestCloseHoles:
    """Tests for hole-filling function."""

    @pytest.fixture
    def polygon_with_small_hole(self) -> Polygon:
        """Polygon with a small interior hole (area = 4)."""
        exterior = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
        hole = [(2, 2), (2, 4), (4, 4), (4, 2), (2, 2)]  # 2x2 = area 4
        return Polygon(exterior, [hole])

    @pytest.fixture
    def polygon_with_large_hole(self) -> Polygon:
        """Polygon with a large interior hole (area = 36)."""
        exterior = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
        hole = [(1, 1), (1, 7), (7, 7), (7, 1), (1, 1)]  # 6x6 = area 36
        return Polygon(exterior, [hole])

    @pytest.fixture
    def polygon_with_two_holes(self) -> Polygon:
        """Polygon with two holes of different sizes."""
        exterior = [(0, 0), (20, 0), (20, 20), (0, 20), (0, 0)]
        small_hole = [(2, 2), (2, 3), (3, 3), (3, 2), (2, 2)]  # area = 1
        large_hole = [(10, 10), (10, 15), (15, 15), (15, 10), (10, 10)]  # area = 25
        return Polygon(exterior, [small_hole, large_hole])

    def test_fill_all_holes_with_zero_threshold(
        self, polygon_with_small_hole: Polygon
    ) -> None:
        """area_max=0 should fill ALL holes."""
        result = close_holes(polygon_with_small_hole, area_max=0)

        assert len(result.interiors) == 0
        # Area should increase by the hole area
        assert result.area > polygon_with_small_hole.area

    def test_keep_hole_above_threshold(self, polygon_with_large_hole: Polygon) -> None:
        """Holes larger than area_max should be kept."""
        result = close_holes(polygon_with_large_hole, area_max=10)

        # The 36 sq unit hole should be preserved
        assert len(result.interiors) == 1

    def test_fill_hole_below_threshold(self, polygon_with_small_hole: Polygon) -> None:
        """Holes smaller than area_max should be filled."""
        result = close_holes(polygon_with_small_hole, area_max=10)

        # The 4 sq unit hole should be filled
        assert len(result.interiors) == 0

    def test_selective_hole_filling(self, polygon_with_two_holes: Polygon) -> None:
        """Only fill holes below threshold, keep holes above."""
        # Threshold between small (1) and large (25) holes
        result = close_holes(polygon_with_two_holes, area_max=5)

        # Only the small hole should be filled
        assert len(result.interiors) == 1
        # The remaining hole should be the large one
        remaining_hole = Polygon(result.interiors[0])
        assert remaining_hole.area > 20  # Large hole ~25 sq units

    def test_polygon_without_holes_unchanged(self) -> None:
        """Polygon without holes should remain unchanged."""
        poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])
        result = close_holes(poly, area_max=0)

        assert result.equals(poly)

    def test_multipolygon_holes_filled(self) -> None:
        """MultiPolygon should have holes filled in all parts."""
        # First polygon with a hole
        exterior1 = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
        hole1 = [(2, 2), (2, 4), (4, 4), (4, 2), (2, 2)]
        poly1 = Polygon(exterior1, [hole1])

        # Second polygon with a hole
        exterior2 = [(20, 20), (30, 20), (30, 30), (20, 30), (20, 20)]
        hole2 = [(22, 22), (22, 24), (24, 24), (24, 22), (22, 22)]
        poly2 = Polygon(exterior2, [hole2])

        multi = MultiPolygon([poly1, poly2])
        result = close_holes(multi, area_max=0)

        assert isinstance(result, MultiPolygon)
        # Both parts should have no holes
        for geom in result.geoms:
            assert len(geom.interiors) == 0

    def test_unsupported_geometry_type_raises(self) -> None:
        """Non-polygon geometry should raise ValueError."""
        from shapely.geometry import Point

        with pytest.raises(ValueError, match="Unsupported geometry type"):
            close_holes(Point(0, 0), area_max=0)  # type: ignore[arg-type]


class TestFillGeopandas:
    """Tests for GeoDataFrame hole-filling."""

    def test_fills_holes_in_all_rows(self) -> None:
        """All geometries in GeoDataFrame should have holes filled."""
        # Create GeoDataFrame with polygons having holes
        poly1 = Polygon(
            [(0, 0), (10, 0), (10, 10), (0, 10)],
            [[(2, 2), (2, 4), (4, 4), (4, 2)]],
        )
        poly2 = Polygon(
            [(20, 20), (30, 20), (30, 30), (20, 30)],
            [[(22, 22), (22, 24), (24, 24), (24, 22)]],
        )

        gdf = gpd.GeoDataFrame(geometry=[poly1, poly2], crs="EPSG:4326")
        result = fill_geopandas(gdf, area_max=0)

        assert isinstance(result, gpd.GeoSeries)
        assert len(result) == 2
        for geom in result:
            assert len(geom.interiors) == 0

    def test_preserves_crs(self) -> None:
        """CRS should be preserved in the result."""
        poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        gdf = gpd.GeoDataFrame(geometry=[poly], crs="EPSG:4326")

        result = fill_geopandas(gdf, area_max=0)

        # GeoSeries from apply preserves CRS
        assert result.crs == gdf.crs


class TestDissolveGeopandas:
    """Tests for GeoDataFrame dissolve function."""

    @pytest.fixture
    def adjacent_squares(self) -> gpd.GeoDataFrame:
        """Four adjacent squares forming a 2x2 grid."""
        polys = [
            box(0, 0, 5, 5),  # Bottom-left
            box(5, 0, 10, 5),  # Bottom-right
            box(0, 5, 5, 10),  # Top-left
            box(5, 5, 10, 10),  # Top-right
        ]
        return gpd.GeoDataFrame(geometry=polys, crs="EPSG:4326")

    @pytest.fixture
    def overlapping_polygons(self) -> gpd.GeoDataFrame:
        """Two overlapping polygons."""
        polys = [
            box(0, 0, 6, 6),
            box(4, 4, 10, 10),
        ]
        return gpd.GeoDataFrame(geometry=polys, crs="EPSG:4326")

    @pytest.fixture
    def disjoint_polygons(self) -> gpd.GeoDataFrame:
        """Two non-touching polygons."""
        polys = [
            box(0, 0, 5, 5),
            box(10, 10, 15, 15),
        ]
        return gpd.GeoDataFrame(geometry=polys, crs="EPSG:4326")

    def test_dissolve_adjacent_polygons(self, adjacent_squares: gpd.GeoDataFrame) -> None:
        """Adjacent polygons should merge into one."""
        result = dissolve_geopandas(adjacent_squares)

        assert isinstance(result, gpd.GeoSeries)
        # Should return a single geometry covering the 10x10 area
        assert len(result) == 1

    def test_dissolve_overlapping_polygons(
        self, overlapping_polygons: gpd.GeoDataFrame
    ) -> None:
        """Overlapping polygons should merge into one."""
        result = dissolve_geopandas(overlapping_polygons)

        assert len(result) == 1
        # Dissolved area should be less than sum of individual areas (due to overlap)
        total_input_area = sum(g.area for g in overlapping_polygons.geometry)
        assert result.iloc[0].area < total_input_area

    def test_dissolve_disjoint_polygons(
        self, disjoint_polygons: gpd.GeoDataFrame
    ) -> None:
        """Disjoint polygons should result in MultiPolygon or separate features."""
        result = dissolve_geopandas(disjoint_polygons)

        # The clip-based dissolve may return a MultiPolygon for disjoint inputs
        assert len(result) >= 1

    def test_dissolve_single_polygon(self) -> None:
        """Single polygon should remain a single polygon."""
        poly = box(0, 0, 10, 10)
        gdf = gpd.GeoDataFrame(geometry=[poly], crs="EPSG:4326")

        result = dissolve_geopandas(gdf)

        assert len(result) == 1
        # Area should be approximately the same
        assert abs(result.iloc[0].area - poly.area) < 1

    def test_preserves_crs(self, adjacent_squares: gpd.GeoDataFrame) -> None:
        """CRS should be preserved in the result."""
        result = dissolve_geopandas(adjacent_squares)

        assert result.crs == adjacent_squares.crs

    def test_result_is_valid_geometry(
        self, overlapping_polygons: gpd.GeoDataFrame
    ) -> None:
        """Dissolved result should be valid geometry."""
        result = dissolve_geopandas(overlapping_polygons)

        for geom in result:
            assert geom.is_valid

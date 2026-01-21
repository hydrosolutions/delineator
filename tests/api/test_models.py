"""
Tests for API model functions.

Verifies geometry simplification behavior including vertex reduction,
topology preservation, and handling of complex/multi-part geometries.
"""

from shapely.geometry import MultiPolygon, Point

from delineator.api.models import simplify_geometry


class TestSimplifyGeometry:
    """Tests for geometry simplification."""

    def test_reduces_vertex_count_on_complex_polygon(self) -> None:
        """Complex polygon with 256+ vertices is reduced to fewer vertices."""
        # Create a complex polygon with 256+ vertices
        original = Point(-105.0, 40.0).buffer(0.1, resolution=64)
        original_vertex_count = len(original.exterior.coords)

        # Verify we have a complex polygon
        assert original_vertex_count >= 256

        # Simplify the geometry
        simplified = simplify_geometry(original)

        # Verify vertex count was reduced
        assert len(simplified.exterior.coords) < original_vertex_count

    def test_simplified_geometry_remains_valid(self) -> None:
        """Simplified geometry remains topologically valid."""
        # Create a complex polygon
        original = Point(-105.0, 40.0).buffer(0.1, resolution=64)

        # Simplify the geometry
        simplified = simplify_geometry(original)

        # Verify the simplified geometry is valid
        assert simplified.is_valid

    def test_handles_multipolygon_geometries(self) -> None:
        """MultiPolygon geometries are simplified correctly."""
        # Create two separate polygons
        polygon1 = Point(-105.0, 40.0).buffer(0.1, resolution=64)
        polygon2 = Point(-104.5, 40.5).buffer(0.1, resolution=64)

        # Create a MultiPolygon
        original = MultiPolygon([polygon1, polygon2])

        # Simplify the geometry
        simplified = simplify_geometry(original)

        # Verify it's still a MultiPolygon
        assert isinstance(simplified, MultiPolygon)

        # Verify it's valid
        assert simplified.is_valid

        # Verify both parts were simplified (vertex count reduced)
        original_vertices = sum(len(geom.exterior.coords) for geom in original.geoms)
        simplified_vertices = sum(len(geom.exterior.coords) for geom in simplified.geoms)
        assert simplified_vertices < original_vertices

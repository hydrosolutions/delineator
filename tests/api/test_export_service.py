"""
Unit tests for the watershed export service module.

Tests verify the conversion of DelineateResponse objects to various geospatial
file formats including GeoJSON, Shapefile, and GeoPackage.
"""

import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import geopandas as gpd

from delineator.api.export import (
    export_geojson,
    export_geopackage,
    export_shapefile_zip,
    export_watershed,
    response_to_geodataframe,
)
from delineator.api.models import ExportFormat


class TestResponseToGeoDataFrame:
    """Tests for response_to_geodataframe function."""

    def test_columns(self, mock_delineate_response):
        """Test that GeoDataFrame has correct columns."""
        gdf = response_to_geodataframe(mock_delineate_response)

        expected_columns = {
            "gauge_id",
            "area_km2",
            "snap_lat",
            "snap_lng",
            "snap_distance_m",
            "resolution",
            "geometry",
        }
        actual_columns = set(gdf.columns)

        assert actual_columns == expected_columns

    def test_crs(self, mock_delineate_response):
        """Test that GeoDataFrame has CRS EPSG:4326."""
        gdf = response_to_geodataframe(mock_delineate_response)

        assert gdf.crs is not None
        assert gdf.crs.to_string() == "EPSG:4326"

    def test_values(self, mock_delineate_response):
        """Test that values in GeoDataFrame match the response properties."""
        gdf = response_to_geodataframe(mock_delineate_response)

        # Should have exactly one row
        assert len(gdf) == 1

        # Check all property values
        props = mock_delineate_response.watershed.properties
        row = gdf.iloc[0]

        assert row["gauge_id"] == props.gauge_id
        assert row["area_km2"] == props.area_km2
        assert row["snap_lat"] == props.snap_lat
        assert row["snap_lng"] == props.snap_lng
        assert row["snap_distance_m"] == props.snap_distance_m
        assert row["resolution"] == props.resolution

        # Check geometry type
        assert row["geometry"].geom_type == "Polygon"


class TestExportGeojson:
    """Tests for export_geojson function."""

    def test_produces_valid_json(self, mock_delineate_response):
        """Test that export_geojson returns bytes that parse as valid JSON with type=FeatureCollection."""
        result = export_geojson(mock_delineate_response)

        # Should be bytes
        assert isinstance(result, bytes)

        # Should parse as valid JSON
        geojson = json.loads(result.decode("utf-8"))

        # Should be a FeatureCollection (geopandas outputs this by default)
        assert geojson["type"] == "FeatureCollection"
        assert "features" in geojson

    def test_preserves_properties(self, mock_delineate_response):
        """Test that GeoJSON features have all expected properties."""
        result = export_geojson(mock_delineate_response)
        geojson = json.loads(result.decode("utf-8"))

        # Get the first (and only) feature
        features = geojson["features"]
        assert len(features) == 1

        feature = features[0]
        props = feature["properties"]

        # Check all expected properties are present
        expected_props = mock_delineate_response.watershed.properties
        assert props["gauge_id"] == expected_props.gauge_id
        assert props["area_km2"] == expected_props.area_km2
        assert props["snap_lat"] == expected_props.snap_lat
        assert props["snap_lng"] == expected_props.snap_lng
        assert props["snap_distance_m"] == expected_props.snap_distance_m
        assert props["resolution"] == expected_props.resolution

        # Check geometry is present
        assert "geometry" in feature
        assert feature["geometry"]["type"] == "Polygon"


class TestExportShapefileZip:
    """Tests for export_shapefile_zip function."""

    def test_contains_required_files(self, mock_delineate_response):
        """Test that ZIP contains .shp, .shx, .dbf, .prj files."""
        gauge_id = "test-gauge-001"
        result = export_shapefile_zip(mock_delineate_response, gauge_id)

        # Should be bytes
        assert isinstance(result, bytes)

        # Read ZIP contents
        zip_buffer = BytesIO(result)
        with ZipFile(zip_buffer, "r") as zipf:
            filenames = zipf.namelist()

        # Check for required shapefile components
        required_extensions = {".shp", ".shx", ".dbf", ".prj"}
        actual_extensions = {Path(f).suffix for f in filenames}

        assert required_extensions.issubset(actual_extensions)

        # All files should have the gauge_id as base name
        for filename in filenames:
            assert Path(filename).stem == gauge_id

    def test_column_name_truncation(self, mock_delineate_response, tmp_path):
        """Test that snap_dist_m is used instead of snap_distance_m in shapefile."""
        gauge_id = "test-gauge-001"
        result = export_shapefile_zip(mock_delineate_response, gauge_id)

        # Extract ZIP to temporary directory
        zip_buffer = BytesIO(result)
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        with ZipFile(zip_buffer, "r") as zipf:
            zipf.extractall(extract_dir)

        # Read the shapefile back
        shp_path = extract_dir / f"{gauge_id}.shp"
        gdf = gpd.read_file(shp_path)

        # Check that snap_dist_ column exists (truncated from snap_distance_m)
        # Note: Shapefile limits column names to 10 chars, so snap_dist_m becomes snap_dist_
        assert "snap_dist_" in gdf.columns
        assert "snap_distance_m" not in gdf.columns

        # Verify the value is correct
        expected_value = mock_delineate_response.watershed.properties.snap_distance_m
        assert gdf.iloc[0]["snap_dist_"] == expected_value


class TestExportGeopackage:
    """Tests for export_geopackage function."""

    def test_valid_sqlite(self, mock_delineate_response):
        """Test that returned bytes start with SQLite magic bytes."""
        gauge_id = "test-gauge-001"
        result = export_geopackage(mock_delineate_response, gauge_id)

        # Should be bytes
        assert isinstance(result, bytes)

        # Should start with SQLite magic bytes
        assert result.startswith(b"SQLite format 3")

    def test_has_watershed_layer(self, mock_delineate_response, tmp_path):
        """Test that GeoPackage can be read back and has 'watershed' layer."""
        gauge_id = "test-gauge-001"
        result = export_geopackage(mock_delineate_response, gauge_id)

        # Write to temporary file
        gpkg_path = tmp_path / "test.gpkg"
        gpkg_path.write_bytes(result)

        # Read back the GeoPackage
        gdf = gpd.read_file(gpkg_path, layer="watershed")

        # Should have one row
        assert len(gdf) == 1

        # Check properties
        props = mock_delineate_response.watershed.properties
        row = gdf.iloc[0]

        assert row["gauge_id"] == props.gauge_id
        assert row["area_km2"] == props.area_km2
        assert row["snap_lat"] == props.snap_lat
        assert row["snap_lng"] == props.snap_lng
        assert row["snap_distance_m"] == props.snap_distance_m
        assert row["resolution"] == props.resolution


class TestExportWatershed:
    """Tests for export_watershed dispatcher function."""

    def test_geojson_returns_correct_content_type(self, mock_delineate_response):
        """Test that GeoJSON export returns correct content type and filename."""
        gauge_id = "test-gauge-001"
        data, content_type, filename = export_watershed(mock_delineate_response, gauge_id, ExportFormat.geojson)

        assert isinstance(data, bytes)
        assert content_type == "application/geo+json"
        assert filename == f"{gauge_id}.geojson"

        # Verify data is valid GeoJSON
        geojson = json.loads(data.decode("utf-8"))
        assert geojson["type"] == "FeatureCollection"

    def test_shapefile_returns_correct_content_type(self, mock_delineate_response):
        """Test that Shapefile export returns correct content type and filename."""
        gauge_id = "test-gauge-001"
        data, content_type, filename = export_watershed(mock_delineate_response, gauge_id, ExportFormat.shapefile)

        assert isinstance(data, bytes)
        assert content_type == "application/zip"
        assert filename == f"{gauge_id}.shp.zip"

        # Verify data is a valid ZIP
        zip_buffer = BytesIO(data)
        with ZipFile(zip_buffer, "r") as zipf:
            assert len(zipf.namelist()) > 0

    def test_geopackage_returns_correct_content_type(self, mock_delineate_response):
        """Test that GeoPackage export returns correct content type and filename."""
        gauge_id = "test-gauge-001"
        data, content_type, filename = export_watershed(mock_delineate_response, gauge_id, ExportFormat.geopackage)

        assert isinstance(data, bytes)
        assert content_type == "application/geopackage+sqlite3"
        assert filename == f"{gauge_id}.gpkg"

        # Verify data is valid SQLite
        assert data.startswith(b"SQLite format 3")

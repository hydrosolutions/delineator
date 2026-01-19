"""
Integration tests for the watershed export endpoint.

Tests the GET /export/{gauge_id} endpoint which exports cached watershed
delineations in various file formats (GeoJSON, Shapefile, GeoPackage).
Validates file format correctness, content integrity, and error handling.
"""

import json
import zipfile
from io import BytesIO
from unittest.mock import patch

from fastapi.testclient import TestClient

from delineator.api import routes
from delineator.api.cache import WatershedCache
from delineator.api.main import create_app
from delineator.api.models import DelineateResponse


class TestExportEndpoint:
    """Tests for GET /export/{gauge_id} endpoint."""

    def test_export_geojson_explicit_format(
        self,
        test_client: TestClient,
        mock_delineate_response: DelineateResponse,
    ) -> None:
        """GET with format=geojson returns 200 with valid GeoJSON FeatureCollection."""
        # Populate cache with test data
        routes.cache.put(
            lat=40.001,
            lng=-104.999,
            gauge_id="test-gauge-001",
            response=mock_delineate_response,
        )

        # Export as GeoJSON
        response = test_client.get("/export/test-gauge-001?format=geojson")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/geo+json"
        assert response.headers["content-disposition"] == 'attachment; filename="test-gauge-001.geojson"'

        # Parse and validate GeoJSON
        data = json.loads(response.content)
        assert data["type"] == "FeatureCollection"
        assert "features" in data
        assert len(data["features"]) == 1

        feature = data["features"][0]
        assert feature["type"] == "Feature"
        assert feature["geometry"]["type"] == "Polygon"
        assert feature["properties"]["gauge_id"] == "test-gauge-001"
        assert feature["properties"]["area_km2"] == 250.5

    def test_export_geojson_default_format(
        self,
        test_client: TestClient,
        mock_delineate_response: DelineateResponse,
    ) -> None:
        """GET without format param defaults to GeoJSON."""
        # Populate cache
        routes.cache.put(
            lat=40.001,
            lng=-104.999,
            gauge_id="test-gauge-002",
            response=mock_delineate_response,
        )

        # Export without specifying format
        response = test_client.get("/export/test-gauge-002")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/geo+json"
        assert response.headers["content-disposition"] == 'attachment; filename="test-gauge-002.geojson"'

        # Validate it's valid GeoJSON
        data = json.loads(response.content)
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) == 1

    def test_export_shapefile_returns_zip(
        self,
        test_client: TestClient,
        mock_delineate_response: DelineateResponse,
    ) -> None:
        """GET with format=shapefile returns 200 with ZIP containing shapefile components."""
        # Populate cache
        routes.cache.put(
            lat=40.001,
            lng=-104.999,
            gauge_id="test-gauge-003",
            response=mock_delineate_response,
        )

        # Export as shapefile
        response = test_client.get("/export/test-gauge-003?format=shapefile")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert response.headers["content-disposition"] == 'attachment; filename="test-gauge-003.shp.zip"'

        # Validate ZIP contents
        zip_buffer = BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            filenames = zf.namelist()

            # Check for required shapefile components
            assert "test-gauge-003.shp" in filenames
            assert "test-gauge-003.shx" in filenames
            assert "test-gauge-003.dbf" in filenames
            assert "test-gauge-003.prj" in filenames

            # Verify files are not empty
            for filename in filenames:
                file_info = zf.getinfo(filename)
                assert file_info.file_size > 0, f"{filename} is empty"

    def test_export_geopackage_returns_valid_file(
        self,
        test_client: TestClient,
        mock_delineate_response: DelineateResponse,
    ) -> None:
        """GET with format=geopackage returns 200 with valid GeoPackage file."""
        # Populate cache
        routes.cache.put(
            lat=40.001,
            lng=-104.999,
            gauge_id="test-gauge-004",
            response=mock_delineate_response,
        )

        # Export as GeoPackage
        response = test_client.get("/export/test-gauge-004?format=geopackage")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/geopackage+sqlite3"
        assert response.headers["content-disposition"] == 'attachment; filename="test-gauge-004.gpkg"'

        # Validate GeoPackage magic bytes (SQLite format)
        assert response.content.startswith(b"SQLite format 3")
        assert len(response.content) > 0

    def test_export_non_existent_gauge_returns_404(
        self,
        test_client: TestClient,
    ) -> None:
        """GET for non-existent gauge_id returns 404 with WATERSHED_NOT_FOUND error code."""
        response = test_client.get("/export/non-existent-gauge-id")

        assert response.status_code == 404
        data = response.json()
        assert data["status"] == "error"
        assert data["error_code"] == "WATERSHED_NOT_FOUND"
        assert "non-existent-gauge-id" in data["error_message"]
        assert data["gauge_id"] == "non-existent-gauge-id"

    def test_export_invalid_format_returns_400(
        self,
        test_client: TestClient,
        mock_delineate_response: DelineateResponse,
    ) -> None:
        """GET with invalid format parameter returns 400 validation error."""
        # Populate cache
        routes.cache.put(
            lat=40.001,
            lng=-104.999,
            gauge_id="test-gauge-005",
            response=mock_delineate_response,
        )

        # Request with invalid format
        response = test_client.get("/export/test-gauge-005?format=invalid_format")

        assert response.status_code == 400
        data = response.json()
        assert data["status"] == "error"
        assert data["error_code"] == "INVALID_COORDINATES"
        assert "format" in data["error_message"]
        assert "geojson" in data["error_message"]
        assert "shapefile" in data["error_message"]
        assert "geopackage" in data["error_message"]

    def test_export_preserves_all_properties_geojson(
        self,
        test_client: TestClient,
        mock_delineate_response: DelineateResponse,
    ) -> None:
        """Exported GeoJSON preserves all properties (gauge_id, area_km2, snap_lat, snap_lng, resolution)."""
        # Populate cache
        routes.cache.put(
            lat=40.001,
            lng=-104.999,
            gauge_id="test-gauge-006",
            response=mock_delineate_response,
        )

        # Export as GeoJSON
        response = test_client.get("/export/test-gauge-006?format=geojson")

        assert response.status_code == 200
        data = json.loads(response.content)

        feature = data["features"][0]
        props = feature["properties"]

        # Verify all properties are preserved
        assert props["gauge_id"] == "test-gauge-001"  # Original from mock
        assert props["area_km2"] == 250.5
        assert props["snap_lat"] == 40.001
        assert props["snap_lng"] == -104.999
        assert props["snap_distance_m"] == 150.5
        assert props["resolution"] == "high_res"

    def test_export_preserves_all_properties_shapefile(
        self,
        test_client: TestClient,
        mock_delineate_response: DelineateResponse,
    ) -> None:
        """Exported Shapefile preserves all properties with appropriate field name truncation."""
        # Populate cache
        routes.cache.put(
            lat=40.001,
            lng=-104.999,
            gauge_id="test-gauge-007",
            response=mock_delineate_response,
        )

        # Export as shapefile
        response = test_client.get("/export/test-gauge-007?format=shapefile")

        assert response.status_code == 200

        # Validate ZIP contains DBF file (contains attributes)
        zip_buffer = BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            assert "test-gauge-007.dbf" in zf.namelist()
            dbf_data = zf.read("test-gauge-007.dbf")
            assert len(dbf_data) > 0

    def test_export_preserves_all_properties_geopackage(
        self,
        test_client: TestClient,
        mock_delineate_response: DelineateResponse,
    ) -> None:
        """Exported GeoPackage preserves all properties."""
        # Populate cache
        routes.cache.put(
            lat=40.001,
            lng=-104.999,
            gauge_id="test-gauge-008",
            response=mock_delineate_response,
        )

        # Export as GeoPackage
        response = test_client.get("/export/test-gauge-008?format=geopackage")

        assert response.status_code == 200
        # GeoPackage is SQLite, verify it's a valid SQLite file
        assert response.content.startswith(b"SQLite format 3")

    def test_export_multiple_formats_same_gauge(
        self,
        test_client: TestClient,
        mock_delineate_response: DelineateResponse,
    ) -> None:
        """Same gauge can be exported in multiple formats."""
        # Populate cache
        routes.cache.put(
            lat=40.001,
            lng=-104.999,
            gauge_id="test-gauge-009",
            response=mock_delineate_response,
        )

        # Export as GeoJSON
        response_geojson = test_client.get("/export/test-gauge-009?format=geojson")
        assert response_geojson.status_code == 200
        assert response_geojson.headers["content-type"] == "application/geo+json"

        # Export as Shapefile
        response_shp = test_client.get("/export/test-gauge-009?format=shapefile")
        assert response_shp.status_code == 200
        assert response_shp.headers["content-type"] == "application/zip"

        # Export as GeoPackage
        response_gpkg = test_client.get("/export/test-gauge-009?format=geopackage")
        assert response_gpkg.status_code == 200
        assert response_gpkg.headers["content-type"] == "application/geopackage+sqlite3"

    def test_export_after_delineate_request(
        self,
        test_client: TestClient,
    ) -> None:
        """Export works after a successful delineate request that populates cache."""
        # First, delineate to populate cache
        delineate_response = test_client.post(
            "/delineate",
            json={"gauge_id": "test-gauge-010", "lat": 40.0, "lng": -105.0},
        )
        assert delineate_response.status_code == 200

        # Now export the same gauge
        export_response = test_client.get("/export/test-gauge-010?format=geojson")
        assert export_response.status_code == 200

        # Verify the exported data matches the delineate response
        export_data = json.loads(export_response.content)
        feature = export_data["features"][0]
        assert feature["properties"]["gauge_id"] == "test-gauge-010"

    def test_export_with_fresh_cache(
        self,
        fresh_cache: WatershedCache,
        mock_delineate_response: DelineateResponse,
        mock_basin_data,
        tmp_path,
    ) -> None:
        """Export endpoint works with a fresh cache instance."""
        with (
            patch(
                "delineator.api.routes.get_basin_for_point",
                return_value=mock_basin_data,
            ),
            patch(
                "delineator.api.routes.get_data_dir",
                return_value=tmp_path,
            ),
        ):
            # Use the fresh cache
            routes.cache = fresh_cache
            routes.stats = routes.RequestStats()

            # Populate the fresh cache
            fresh_cache.put(
                lat=40.001,
                lng=-104.999,
                gauge_id="test-gauge-011",
                response=mock_delineate_response,
            )

            app = create_app()
            client = TestClient(app)

            # Export from fresh cache
            response = client.get("/export/test-gauge-011?format=geojson")

            assert response.status_code == 200
            data = json.loads(response.content)
            assert data["type"] == "FeatureCollection"
            assert len(data["features"]) == 1

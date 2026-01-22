"""
Tests for the delineator API routes.

Covers all endpoints:
- POST /delineate - Watershed delineation
- GET /health - Health check
- GET /cache/stats - Cache statistics
- DELETE /cache/{gauge_id} - Cache invalidation
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from delineator.api import routes
from delineator.api.cache import WatershedCache
from delineator.api.main import create_app
from delineator.core.delineate import DelineationError


class TestDelineateEndpoint:
    """Tests for POST /delineate endpoint."""

    def test_delineate_success(self, test_client: TestClient) -> None:
        """Valid request returns watershed GeoJSON with success status."""
        response = test_client.post(
            "/delineate",
            json={"gauge_id": "test-gauge-001", "lat": 40.0, "lng": -105.0},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "success"
        assert data["gauge_id"] == "test-gauge-001"
        assert data["cached"] is False
        assert data["watershed"]["type"] == "Feature"
        assert data["watershed"]["geometry"]["type"] == "Polygon"
        assert data["watershed"]["properties"]["area_km2"] == 250.5
        assert data["watershed"]["properties"]["snap_lat"] == 40.001
        assert data["watershed"]["properties"]["snap_lng"] == -104.999
        assert data["watershed"]["properties"]["snap_distance_m"] == 150.5
        assert data["watershed"]["properties"]["resolution"] == "high_res"

    def test_delineate_cache_miss_then_hit(self, test_client: TestClient) -> None:
        """First request is cache miss, second request is cache hit."""
        # First request - cache miss
        response1 = test_client.post(
            "/delineate",
            json={"gauge_id": "cache-test", "lat": 40.0, "lng": -105.0},
        )
        assert response1.status_code == 200
        assert response1.json()["cached"] is False

        # Second request - cache hit (same coordinates)
        response2 = test_client.post(
            "/delineate",
            json={"gauge_id": "cache-test-2", "lat": 40.0, "lng": -105.0},
        )
        assert response2.status_code == 200
        assert response2.json()["cached"] is True
        # gauge_id should be updated to the new request's gauge_id
        assert response2.json()["gauge_id"] == "cache-test-2"

    def test_delineate_updates_cache_stats(self, test_client: TestClient) -> None:
        """Cache stats are updated correctly after requests."""
        # Initial stats
        stats_response = test_client.get("/cache/stats")
        initial_stats = stats_response.json()
        assert initial_stats["total_requests"] == 0
        assert initial_stats["cache_hits"] == 0
        assert initial_stats["cache_misses"] == 0

        # First request - miss
        test_client.post(
            "/delineate",
            json={"gauge_id": "stats-test", "lat": 40.0, "lng": -105.0},
        )

        stats_response = test_client.get("/cache/stats")
        stats = stats_response.json()
        assert stats["total_requests"] == 1
        assert stats["cache_hits"] == 0
        assert stats["cache_misses"] == 1

        # Second request - hit
        test_client.post(
            "/delineate",
            json={"gauge_id": "stats-test-2", "lat": 40.0, "lng": -105.0},
        )

        stats_response = test_client.get("/cache/stats")
        stats = stats_response.json()
        assert stats["total_requests"] == 2
        assert stats["cache_hits"] == 1
        assert stats["cache_misses"] == 1
        assert stats["hit_rate"] == 0.5

    def test_delineate_invalid_lat_type(self, test_client: TestClient) -> None:
        """Non-numeric latitude returns INVALID_COORDINATES error."""
        response = test_client.post(
            "/delineate",
            json={"gauge_id": "test", "lat": "not-a-number", "lng": -105.0},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["status"] == "error"
        assert data["error_code"] == "INVALID_COORDINATES"
        assert "lat" in data["error_message"]

    def test_delineate_missing_fields(self, test_client: TestClient) -> None:
        """Missing required fields returns INVALID_COORDINATES error."""
        response = test_client.post(
            "/delineate",
            json={"gauge_id": "test"},  # Missing lat and lng
        )

        assert response.status_code == 400
        data = response.json()
        assert data["status"] == "error"
        assert data["error_code"] == "INVALID_COORDINATES"
        # Should mention missing fields
        assert "lat" in data["error_message"] or "lng" in data["error_message"]

    def test_delineate_lat_out_of_range(self, test_client: TestClient) -> None:
        """Latitude > 90 is rejected with INVALID_COORDINATES."""
        response = test_client.post(
            "/delineate",
            json={"gauge_id": "test", "lat": 95.0, "lng": -105.0},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["status"] == "error"
        assert data["error_code"] == "INVALID_COORDINATES"
        assert "lat" in data["error_message"]

    def test_delineate_lng_out_of_range(self, test_client: TestClient) -> None:
        """Longitude > 180 is rejected with INVALID_COORDINATES."""
        response = test_client.post(
            "/delineate",
            json={"gauge_id": "test", "lat": 40.0, "lng": 200.0},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["status"] == "error"
        assert data["error_code"] == "INVALID_COORDINATES"
        assert "lng" in data["error_message"]

    def test_delineate_no_river_found(
        self,
        mock_basin_data,
        tmp_path,
    ) -> None:
        """DelineationError with 'unit catchment' message returns NO_RIVER_FOUND."""
        with (
            patch(
                "delineator.api.routes.get_basin_for_point",
                return_value=mock_basin_data,
            ),
            patch(
                "delineator.api.routes.get_data_dir",
                return_value=tmp_path,
            ),
            patch(
                "delineator.api.routes.delineate_outlet",
                side_effect=DelineationError("Point (40.0, -105.0) does not fall within any unit catchment"),
            ),
        ):
            routes.cache = WatershedCache(tmp_path / "cache.db")
            routes.stats = routes.RequestStats()

            app = create_app()
            client = TestClient(app)

            response = client.post(
                "/delineate",
                json={"gauge_id": "test", "lat": 40.0, "lng": -105.0},
            )

            assert response.status_code == 404
            data = response.json()
            assert data["status"] == "error"
            assert data["error_code"] == "NO_RIVER_FOUND"
            assert "unit catchment" in data["error_message"]

    def test_delineate_no_data_available(
        self,
        mock_basin_data,
        tmp_path,
    ) -> None:
        """FileNotFoundError returns NO_DATA_AVAILABLE."""
        with (
            patch(
                "delineator.api.routes.get_basin_for_point",
                return_value=mock_basin_data,
            ),
            patch(
                "delineator.api.routes.get_data_dir",
                return_value=tmp_path,
            ),
            patch(
                "delineator.api.routes.delineate_outlet",
                side_effect=FileNotFoundError("Flow direction raster not found"),
            ),
        ):
            routes.cache = WatershedCache(tmp_path / "cache.db")
            routes.stats = routes.RequestStats()

            app = create_app()
            client = TestClient(app)

            response = client.post(
                "/delineate",
                json={"gauge_id": "test", "lat": 40.0, "lng": -105.0},
            )

            assert response.status_code == 404
            data = response.json()
            assert data["status"] == "error"
            assert data["error_code"] == "NO_DATA_AVAILABLE"

    def test_delineate_generic_error(
        self,
        mock_basin_data,
        tmp_path,
    ) -> None:
        """Other DelineationError returns DELINEATION_FAILED."""
        with (
            patch(
                "delineator.api.routes.get_basin_for_point",
                return_value=mock_basin_data,
            ),
            patch(
                "delineator.api.routes.get_data_dir",
                return_value=tmp_path,
            ),
            patch(
                "delineator.api.routes.delineate_outlet",
                side_effect=DelineationError("Unexpected error during delineation"),
            ),
        ):
            routes.cache = WatershedCache(tmp_path / "cache.db")
            routes.stats = routes.RequestStats()

            app = create_app()
            client = TestClient(app)

            response = client.post(
                "/delineate",
                json={"gauge_id": "test", "lat": 40.0, "lng": -105.0},
            )

            assert response.status_code == 500
            data = response.json()
            assert data["status"] == "error"
            assert data["error_code"] == "DELINEATION_FAILED"


class TestHealthEndpoint:
    """Tests for GET /health endpoint."""

    def test_health_returns_status(self, test_client: TestClient) -> None:
        """Health endpoint returns healthy status and version."""
        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "healthy"
        assert data["version"] == "0.1.0"
        assert "data_dir" in data


class TestCacheStatsEndpoint:
    """Tests for GET /cache/stats endpoint."""

    def test_cache_stats_initial(self, test_client: TestClient) -> None:
        """Initial cache stats are all zeros."""
        response = test_client.get("/cache/stats")

        assert response.status_code == 200
        data = response.json()

        assert data["total_requests"] == 0
        assert data["cache_hits"] == 0
        assert data["cache_misses"] == 0
        assert data["hit_rate"] == 0.0
        assert data["cache_size"] == 0

    def test_cache_stats_after_requests(self, test_client: TestClient) -> None:
        """Cache stats update correctly after delineation requests."""
        # Make a request
        test_client.post(
            "/delineate",
            json={"gauge_id": "test", "lat": 40.0, "lng": -105.0},
        )

        response = test_client.get("/cache/stats")
        data = response.json()

        assert data["total_requests"] == 1
        assert data["cache_misses"] == 1
        assert data["cache_size"] == 1


class TestDeleteCacheEndpoint:
    """Tests for DELETE /cache/{gauge_id} endpoint."""

    def test_delete_cache_returns_204(self, test_client: TestClient) -> None:
        """Delete endpoint returns 204 No Content."""
        # First create a cache entry
        test_client.post(
            "/delineate",
            json={"gauge_id": "delete-test", "lat": 40.0, "lng": -105.0},
        )

        # Verify it's in cache
        stats = test_client.get("/cache/stats").json()
        assert stats["cache_size"] == 1

        # Delete it
        response = test_client.delete("/cache/delete-test")
        assert response.status_code == 204

        # Verify it's gone
        stats = test_client.get("/cache/stats").json()
        assert stats["cache_size"] == 0

    def test_delete_cache_idempotent(self, test_client: TestClient) -> None:
        """Deleting non-existent cache entry returns 204 (idempotent)."""
        response = test_client.delete("/cache/non-existent-gauge")

        assert response.status_code == 204


class TestForceLowRes:
    """Tests for force_low_res parameter in /delineate endpoint."""

    def test_delineate_without_force_low_res_defaults_to_false(self, test_client: TestClient) -> None:
        """POST request without force_low_res field defaults to high-res behavior."""
        response = test_client.post(
            "/delineate",
            json={"gauge_id": "test-gauge", "lat": 40.0, "lng": -105.0},
        )
        assert response.status_code == 200
        data = response.json()
        # Check default behavior is high-res
        assert data["watershed"]["properties"]["resolution"] == "high_res"

    def test_delineate_with_force_low_res_true_is_accepted(
        self,
        mock_basin_data,
        mock_watershed_low_res,
        tmp_path,
    ) -> None:
        """POST request with force_low_res=true is accepted and returns low-res result."""
        with (
            patch("delineator.api.routes.get_basin_for_point", return_value=mock_basin_data),
            patch("delineator.api.routes.get_data_dir", return_value=tmp_path),
            patch("delineator.api.routes.delineate_outlet", return_value=mock_watershed_low_res),
        ):
            routes.cache = WatershedCache(tmp_path / "cache.db")
            routes.stats = routes.RequestStats()

            app = create_app()
            client = TestClient(app)

            response = client.post(
                "/delineate",
                json={"gauge_id": "test-gauge", "lat": 40.0, "lng": -105.0, "force_low_res": True},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["watershed"]["properties"]["resolution"] == "low_res"

    def test_delineate_cache_isolation_by_resolution(self, test_client: TestClient) -> None:
        """Same coordinates with different force_low_res values create different cache entries."""
        # First POST with force_low_res=false (default) → cache miss
        response1 = test_client.post(
            "/delineate",
            json={"gauge_id": "gauge-1", "lat": 40.0, "lng": -105.0},
        )
        assert response1.status_code == 200
        assert response1.json()["cached"] is False

        # Second POST with force_low_res=true → cache miss (different resolution)
        # This needs custom mocking to return low_res watershed
        # For this test, we'll verify the cache miss happens
        # Note: Since test_client always returns high_res mock, we can't verify the resolution
        # but we can verify that it's treated as a cache miss
        response2 = test_client.post(
            "/delineate",
            json={"gauge_id": "gauge-2", "lat": 40.0, "lng": -105.0, "force_low_res": True},
        )
        assert response2.status_code == 200
        # This should be a cache miss because resolution differs
        assert response2.json()["cached"] is False

        # Third POST with force_low_res=false again → cache hit
        response3 = test_client.post(
            "/delineate",
            json={"gauge_id": "gauge-3", "lat": 40.0, "lng": -105.0},
        )
        assert response3.status_code == 200
        assert response3.json()["cached"] is True

    def test_delineate_invalid_force_low_res_type_rejected(self, test_client: TestClient) -> None:
        """POST with force_low_res as object/list returns 400 validation error."""
        # Pydantic coerces strings to booleans, but rejects objects/lists
        response = test_client.post(
            "/delineate",
            json={"gauge_id": "test", "lat": 40.0, "lng": -105.0, "force_low_res": {"invalid": "object"}},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["status"] == "error"
        assert data["error_code"] == "INVALID_COORDINATES"
        # Validation error should mention the field
        assert "force_low_res" in data["error_message"]


class TestIncludeRivers:
    """Tests for include_rivers parameter in /delineate endpoint."""

    def test_delineate_without_include_rivers_excludes_rivers(self, test_client: TestClient) -> None:
        """POST request without include_rivers returns response without rivers."""
        response = test_client.post(
            "/delineate",
            json={"gauge_id": "test-gauge", "lat": 40.0, "lng": -105.0},
        )
        assert response.status_code == 200
        data = response.json()
        # Rivers should be null when not requested
        assert data.get("rivers") is None

    def test_delineate_with_include_rivers_true_returns_rivers(
        self,
        mock_basin_data,
        mock_watershed_with_rivers,
        tmp_path,
    ) -> None:
        """POST request with include_rivers=true returns rivers FeatureCollection."""
        with (
            patch("delineator.api.routes.get_basin_for_point", return_value=mock_basin_data),
            patch("delineator.api.routes.get_data_dir", return_value=tmp_path),
            patch("delineator.api.routes.delineate_outlet", return_value=mock_watershed_with_rivers),
        ):
            routes.cache = WatershedCache(tmp_path / "cache.db")
            routes.stats = routes.RequestStats()

            app = create_app()
            client = TestClient(app)

            response = client.post(
                "/delineate",
                json={"gauge_id": "test-gauge", "lat": 40.0, "lng": -105.0, "include_rivers": True},
            )
            assert response.status_code == 200
            data = response.json()

            # Rivers should be present as FeatureCollection
            assert data["rivers"] is not None
            assert data["rivers"]["type"] == "FeatureCollection"
            assert len(data["rivers"]["features"]) == 2

            # Verify river feature structure
            feature = data["rivers"]["features"][0]
            assert feature["type"] == "Feature"
            assert feature["geometry"]["type"] == "LineString"
            assert "comid" in feature["properties"]
            assert "uparea" in feature["properties"]

    def test_delineate_cache_isolation_by_include_rivers(self, test_client: TestClient) -> None:
        """Same coordinates with different include_rivers values create different cache entries."""
        # First POST without include_rivers → cache miss
        response1 = test_client.post(
            "/delineate",
            json={"gauge_id": "gauge-1", "lat": 40.0, "lng": -105.0},
        )
        assert response1.status_code == 200
        assert response1.json()["cached"] is False

        # Second POST with include_rivers=true → cache miss (different key)
        response2 = test_client.post(
            "/delineate",
            json={"gauge_id": "gauge-2", "lat": 40.0, "lng": -105.0, "include_rivers": True},
        )
        assert response2.status_code == 200
        assert response2.json()["cached"] is False

        # Third POST without include_rivers again → cache hit
        response3 = test_client.post(
            "/delineate",
            json={"gauge_id": "gauge-3", "lat": 40.0, "lng": -105.0},
        )
        assert response3.status_code == 200
        assert response3.json()["cached"] is True

        # Fourth POST with include_rivers=true again → cache hit
        response4 = test_client.post(
            "/delineate",
            json={"gauge_id": "gauge-4", "lat": 40.0, "lng": -105.0, "include_rivers": True},
        )
        assert response4.status_code == 200
        assert response4.json()["cached"] is True

    def test_delineate_include_rivers_false_explicit(self, test_client: TestClient) -> None:
        """POST with include_rivers=false explicitly returns no rivers."""
        response = test_client.post(
            "/delineate",
            json={"gauge_id": "test-gauge", "lat": 40.0, "lng": -105.0, "include_rivers": False},
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("rivers") is None

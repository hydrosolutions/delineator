"""
Unit tests for the WatershedCache module.

Tests the cache's ability to store and retrieve watershed delineation responses
by both coordinates and gauge ID.
"""

from delineator.api.cache import WatershedCache
from delineator.api.models import DelineateResponse


def test_get_by_gauge_id_returns_response_when_exists(
    fresh_cache: WatershedCache, mock_delineate_response: DelineateResponse
) -> None:
    """Test that get_by_gauge_id returns a DelineateResponse when gauge_id exists in cache."""
    # Arrange: Add a cached response with a specific gauge_id
    lat, lng = 40.0, -105.0
    gauge_id = "test-gauge-001"
    fresh_cache.put(lat, lng, gauge_id, mock_delineate_response)

    # Act: Retrieve by gauge_id
    result = fresh_cache.get_by_gauge_id(gauge_id)

    # Assert: Should return the cached response
    assert result is not None
    assert isinstance(result, DelineateResponse)
    assert result.gauge_id == gauge_id
    assert result.watershed == mock_delineate_response.watershed


def test_get_by_gauge_id_returns_none_when_not_exists(fresh_cache: WatershedCache) -> None:
    """Test that get_by_gauge_id returns None when gauge_id doesn't exist in cache."""
    # Act: Try to retrieve a gauge_id that was never cached
    result = fresh_cache.get_by_gauge_id("nonexistent-gauge-id")

    # Assert: Should return None
    assert result is None

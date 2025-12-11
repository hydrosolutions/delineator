"""
Tests for country extraction via reverse geocoding.

Uses mocking to avoid actual reverse_geocoder library calls.
"""

from unittest.mock import patch

import pytest

from delineator.core.country import get_country


class TestGetCountry:
    """Tests for get_country function."""

    def test_successful_lookup(self) -> None:
        """Test successful country lookup returns name."""
        mock_results = [
            {
                "name": "Denver",
                "cc": "US",
                "admin1": "Colorado",
                "admin2": "Denver County",
            }
        ]

        with patch("delineator.core.country.rg.search", return_value=mock_results):
            result = get_country(lat=39.7392, lng=-104.9903)

            assert result == "Denver"

    def test_empty_results_raises(self) -> None:
        """Test that empty results raise ValueError."""
        with patch("delineator.core.country.rg.search", return_value=[]):
            with pytest.raises(ValueError, match="No reverse geocoding results"):
                get_country(lat=0.0, lng=0.0)

    def test_missing_country_code_raises(self) -> None:
        """Test that missing country code raises ValueError."""
        mock_results = [{"name": "Unknown", "cc": ""}]

        with patch("delineator.core.country.rg.search", return_value=mock_results):
            with pytest.raises(ValueError, match="No country code found"):
                get_country(lat=0.0, lng=0.0)

    def test_library_exception_propagates(self) -> None:
        """Test that library exceptions are propagated."""
        with patch(
            "delineator.core.country.rg.search",
            side_effect=RuntimeError("Database error"),
        ):
            with pytest.raises(RuntimeError, match="Database error"):
                get_country(lat=39.7392, lng=-104.9903)

    @pytest.mark.parametrize(
        "lat,lng,mock_cc,expected_name",
        [
            (64.1466, -21.9426, "IS", "Reykjavik"),  # Iceland
            (51.5074, -0.1278, "GB", "London"),  # UK
            (-33.8688, 151.2093, "AU", "Sydney"),  # Australia
            (43.2220, 76.8512, "KZ", "Almaty"),  # Kazakhstan
            (35.6762, 139.6503, "JP", "Tokyo"),  # Japan
        ],
    )
    def test_various_locations(
        self, lat: float, lng: float, mock_cc: str, expected_name: str
    ) -> None:
        """Test country lookup for various global locations."""
        mock_results = [{"name": expected_name, "cc": mock_cc}]

        with patch("delineator.core.country.rg.search", return_value=mock_results):
            result = get_country(lat=lat, lng=lng)
            assert result == expected_name

    def test_calls_search_with_correct_format(self) -> None:
        """Test that rg.search is called with (lat, lng) tuple."""
        mock_results = [{"name": "Test", "cc": "XX"}]

        with patch("delineator.core.country.rg.search", return_value=mock_results) as mock_search:
            get_country(lat=40.0, lng=-105.0)

            # Verify called with tuple (lat, lng)
            mock_search.assert_called_once_with((40.0, -105.0))

    def test_uses_first_result(self) -> None:
        """Test that first result is used when multiple are returned."""
        mock_results = [
            {"name": "First", "cc": "AA"},
            {"name": "Second", "cc": "BB"},
            {"name": "Third", "cc": "CC"},
        ]

        with patch("delineator.core.country.rg.search", return_value=mock_results):
            result = get_country(lat=40.0, lng=-105.0)
            assert result == "First"

    def test_falls_back_to_country_code_if_no_name(self) -> None:
        """Test fallback to country code when name is missing."""
        mock_results = [{"cc": "US"}]  # No 'name' field

        with patch("delineator.core.country.rg.search", return_value=mock_results):
            result = get_country(lat=40.0, lng=-105.0)
            # Should fall back to country code
            assert result == "US"

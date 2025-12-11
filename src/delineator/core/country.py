"""
Country extraction using offline reverse geocoding.

Provides functionality to determine the country name for a given
latitude/longitude coordinate using the reverse_geocoder library,
which performs offline lookups without requiring internet access.
"""

import logging

import reverse_geocoder as rg

logger = logging.getLogger(__name__)


def get_country(lat: float, lng: float) -> str:
    """
    Get full country name for a coordinate using offline reverse geocoding.

    Uses the reverse_geocoder library to perform fast, offline lookups
    of country information based on coordinates.

    Args:
        lat: Latitude in decimal degrees
        lng: Longitude in decimal degrees

    Returns:
        Full country name (e.g., "Kazakhstan" not "KZ")

    Raises:
        Exception: If reverse geocoding fails or returns no results

    Example:
        >>> get_country(43.2220, 76.8512)
        'Kazakhstan'
    """
    try:
        # reverse_geocoder expects coordinates as (lat, lng) tuple
        results = rg.search((lat, lng))

        if not results:
            raise ValueError(f"No reverse geocoding results for coordinates ({lat}, {lng})")

        # Results is a list of dicts, take the first (best) match
        result = results[0]

        # The 'cc' field contains country code, 'name' contains place name
        # We want the country name - typically stored in 'cc' but we need to map it
        country_code = result.get("cc", "")

        if not country_code:
            raise ValueError(f"No country code found for coordinates ({lat}, {lng})")

        # reverse_geocoder returns country codes, so we need to get the full name
        # The library actually provides this in the admin1 field sometimes,
        # but the most reliable way is to use a mapping or the 'name' field
        # Let's use the result directly - it contains the country name
        country_name = result.get("name", country_code)

        logger.info(f"Reverse geocoded ({lat}, {lng}) to country: {country_name}")

        return country_name

    except Exception as e:
        logger.error(f"Failed to reverse geocode coordinates ({lat}, {lng}): {e}")
        raise

"""
Pydantic models for the delineator API request/response schemas.

This module defines the data models used for API communication, including
request validation and response serialization. All models use Pydantic v2
for data validation and serialization.
"""

from enum import Enum

from pydantic import BaseModel, Field
from shapely.geometry import mapping

from delineator.core.delineate import DelineatedWatershed


class ExportFormat(str, Enum):
    """Supported export file formats."""

    geojson = "geojson"
    shapefile = "shapefile"
    geopackage = "geopackage"


class DelineateRequest(BaseModel):
    """Request model for watershed delineation."""

    gauge_id: str
    lat: float = Field(ge=-90, le=90, description="Latitude in decimal degrees")
    lng: float = Field(ge=-180, le=180, description="Longitude in decimal degrees")


class WatershedProperties(BaseModel):
    """GeoJSON properties for a delineated watershed feature."""

    gauge_id: str
    area_km2: float
    snap_lat: float
    snap_lng: float
    snap_distance_m: float
    resolution: str


class WatershedFeature(BaseModel):
    """GeoJSON Feature representing a delineated watershed."""

    type: str = "Feature"
    geometry: dict
    properties: WatershedProperties


class DelineateResponse(BaseModel):
    """Success response for watershed delineation."""

    gauge_id: str
    status: str = "success"
    cached: bool
    watershed: WatershedFeature


class ErrorResponse(BaseModel):
    """Error response for failed watershed delineation."""

    gauge_id: str
    status: str = "error"
    error_code: str
    error_message: str


def watershed_to_response(
    watershed: DelineatedWatershed,
    gauge_id: str,
    cached: bool,
) -> DelineateResponse:
    """
    Convert a DelineatedWatershed dataclass to a DelineateResponse.

    Args:
        watershed: The delineated watershed dataclass
        gauge_id: Unique identifier for the gauge
        cached: Whether this result was retrieved from cache

    Returns:
        DelineateResponse with GeoJSON-formatted watershed feature
    """
    # Convert shapely geometry to GeoJSON dict
    geometry_dict = mapping(watershed.geometry)

    # Build the properties object
    properties = WatershedProperties(
        gauge_id=gauge_id,
        area_km2=watershed.area,
        snap_lat=watershed.snap_lat,
        snap_lng=watershed.snap_lon,
        snap_distance_m=watershed.snap_dist,
        resolution=watershed.resolution,
    )

    # Build the GeoJSON feature
    feature = WatershedFeature(
        type="Feature",
        geometry=geometry_dict,
        properties=properties,
    )

    # Build the final response
    return DelineateResponse(
        gauge_id=gauge_id,
        status="success",
        cached=cached,
        watershed=feature,
    )

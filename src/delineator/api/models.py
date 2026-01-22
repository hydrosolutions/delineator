"""
Pydantic models for the delineator API request/response schemas.

This module defines the data models used for API communication, including
request validation and response serialization. All models use Pydantic v2
for data validation and serialization.
"""

from enum import Enum

from pydantic import BaseModel, Field
from shapely.geometry import MultiPolygon, Polygon, mapping

from delineator.core.delineate import DelineatedWatershed

DEFAULT_SIMPLIFY_TOLERANCE = 0.001  # ~100m at equator


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
    force_low_res: bool = Field(default=False, description="Force low-resolution delineation for faster results")
    include_rivers: bool = Field(default=False, description="Include river network geometries in response")


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


class RiverProperties(BaseModel):
    """GeoJSON properties for a river reach feature."""

    comid: int
    uparea: float


class RiverFeature(BaseModel):
    """GeoJSON Feature representing a river reach."""

    type: str = "Feature"
    geometry: dict
    properties: RiverProperties


class RiversFeatureCollection(BaseModel):
    """GeoJSON FeatureCollection of river reaches."""

    type: str = "FeatureCollection"
    features: list[RiverFeature]


class DelineateResponse(BaseModel):
    """Success response for watershed delineation."""

    gauge_id: str
    status: str = "success"
    cached: bool
    watershed: WatershedFeature
    rivers: RiversFeatureCollection | None = None


class ErrorResponse(BaseModel):
    """Error response for failed watershed delineation."""

    gauge_id: str
    status: str = "error"
    error_code: str
    error_message: str


def simplify_geometry(
    geometry: Polygon | MultiPolygon,
    tolerance: float = DEFAULT_SIMPLIFY_TOLERANCE,
) -> Polygon | MultiPolygon:
    """Simplify geometry to reduce vertex count while preserving topology."""
    return geometry.simplify(tolerance, preserve_topology=True)


def watershed_to_response(
    watershed: DelineatedWatershed,
    gauge_id: str,
    cached: bool,
    include_rivers: bool = False,
) -> DelineateResponse:
    """
    Convert a DelineatedWatershed dataclass to a DelineateResponse.

    Args:
        watershed: The delineated watershed dataclass
        gauge_id: Unique identifier for the gauge
        cached: Whether this result was retrieved from cache
        include_rivers: Whether to include river geometries in the response

    Returns:
        DelineateResponse with GeoJSON-formatted watershed feature
    """
    # Convert shapely geometry to GeoJSON dict
    simplified = simplify_geometry(watershed.geometry)
    geometry_dict = mapping(simplified)

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

    # Build rivers FeatureCollection if included
    rivers_fc: RiversFeatureCollection | None = None
    if include_rivers and watershed.rivers is not None:
        river_features = []
        for comid, row in watershed.rivers.iterrows():
            river_geom = mapping(row.geometry)
            river_props = RiverProperties(
                comid=int(comid),
                uparea=float(row["uparea"]),
            )
            river_features.append(
                RiverFeature(
                    type="Feature",
                    geometry=river_geom,
                    properties=river_props,
                )
            )
        rivers_fc = RiversFeatureCollection(
            type="FeatureCollection",
            features=river_features,
        )

    # Build the final response
    return DelineateResponse(
        gauge_id=gauge_id,
        status="success",
        cached=cached,
        watershed=feature,
        rivers=rivers_fc,
    )

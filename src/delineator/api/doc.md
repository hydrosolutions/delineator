---
module: api
description: HTTP API for watershed delineation, providing REST endpoints for the Virtual-Gauges frontend to request watershed boundaries with persistent caching.
---

## Files

- `__init__.py` - Module exports (app, create_app)
- `main.py` - FastAPI application factory and app instance
- `routes.py` - API route handlers for delineation, health, cache, and export endpoints
- `models.py` - Pydantic request/response models and serialization
- `cache.py` - SQLite-based watershed result caching
- `deps.py` - Dependency injection for basin data and data directory
- `exceptions.py` - Custom exception handlers and error responses
- `export.py` - Export watershed results to GeoJSON, Shapefile, or GeoPackage formats
- `logging_config.py` - Structured logging configuration

## Key Interfaces

### Application Factory

- `create_app()` - Factory function returning configured FastAPI application
- `app` - Module-level FastAPI instance for uvicorn

### Request/Response Models (`models.py`)

- `DelineateRequest` - Request model with parameters:
  - `gauge_id: str` - Unique identifier for the gauge/outlet
  - `lat: float` - Latitude in decimal degrees (range: -90 to 90)
  - `lng: float` - Longitude in decimal degrees (range: -180 to 180)
  - `force_low_res: bool` - Force low-resolution delineation (default: False)
  - `include_rivers: bool` - Include river network geometries in response (default: False)

- `DelineateResponse` - Success response containing:
  - `gauge_id: str` - Gauge identifier
  - `status: str` - Always "success"
  - `cached: bool` - Whether result was retrieved from cache
  - `watershed: WatershedFeature` - GeoJSON Feature with watershed polygon
  - `rivers: RiversFeatureCollection | None` - GeoJSON FeatureCollection of river reaches (if include_rivers=true)

- `WatershedFeature` - GeoJSON Feature with:
  - `type: str` - Always "Feature"
  - `geometry: dict` - Polygon or MultiPolygon geometry
  - `properties: WatershedProperties` - Watershed attributes

- `WatershedProperties` - Watershed attributes:
  - `gauge_id: str` - Gauge identifier
  - `area_km2: float` - Watershed area in square kilometers
  - `snap_lat: float` - Snapped outlet latitude
  - `snap_lng: float` - Snapped outlet longitude
  - `snap_distance_m: float` - Distance outlet was moved to nearest stream (meters)
  - `resolution: str` - Delineation resolution ("high_res" or "low_res")

- `RiversFeatureCollection` - GeoJSON FeatureCollection containing:
  - `type: str` - Always "FeatureCollection"
  - `features: list[RiverFeature]` - List of river reach features

- `RiverFeature` - GeoJSON Feature representing a river reach:
  - `type: str` - Always "Feature"
  - `geometry: dict` - LineString geometry of river reach
  - `properties: RiverProperties` - River attributes

- `RiverProperties` - River reach attributes:
  - `comid: int` - MERIT-Hydro COMID (catchment identifier)
  - `uparea: float` - Upstream drainage area in km²
  - `strahler_order: int | None` - Strahler stream order (1 = headwater)
  - `shreve_order: int | None` - Shreve magnitude (sum of upstream orders)

- `ErrorResponse` - Error response containing:
  - `gauge_id: str` - Gauge identifier from request
  - `status: str` - Always "error"
  - `error_code: str` - Machine-readable error code
  - `error_message: str` - Human-readable error description

### Export Formats

When using the `/export/{gauge_id}` endpoint, results can be exported in different formats:

- **GeoJSON** - Single FeatureCollection with watershed and rivers (if included) as separate features
- **Shapefile** - Watershed polygon in main .shp file, rivers in separate `{gauge_id}_rivers.shp` file
- **GeoPackage** - Watershed in default layer, rivers in separate "rivers" layer

### Routes (`routes.py`)

- `POST /delineate` - Delineate watershed for outlet coordinates
- `GET /health` - Health check and API status
- `GET /cache/stats` - Cache hit/miss statistics
- `DELETE /cache/{gauge_id}` - Delete cached entries for a gauge
- `GET /export/{gauge_id}` - Export cached watershed as downloadable file

### Utility Functions

- `watershed_to_response()` - Convert DelineatedWatershed to DelineateResponse
- `simplify_geometry()` - Simplify geometry to reduce vertex count for network transfer

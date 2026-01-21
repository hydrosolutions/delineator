---
project: Delineator
branchName: ralph/watershed-export
description: Add endpoint to export cached watershed boundaries as downloadable files (GeoJSON, Shapefile, GeoPackage)

stories:
  US-001: { passes: true, notes: "Completed 2026-01-19" }
  US-002: { passes: true, notes: "Completed 2026-01-19" }
  US-003: { passes: true, notes: "Completed 2026-01-19" }
  US-004: { passes: true, notes: "Completed 2026-01-19" }
  US-005: { passes: true, notes: "Completed 2026-01-19" }
---

# PRD: Watershed Export Endpoint

## Introduction

Add a `GET /export/{gauge_id}` endpoint that allows downloading cached watershed boundaries as files in multiple formats (GeoJSON, Shapefile, GeoPackage). This enables exporting delineated watersheds for use in GIS software like QGIS or ArcGIS.

Currently, the API returns watershed data in HTTP responses and caches it in SQLite, but there's no way to download the watershed as a file. This feature bridges that gap.

**Technical Context:**
- FastAPI app in `src/delineator/api/`
- Existing endpoints: `POST /delineate`, `GET /health`, `GET /cache/stats`, `DELETE /cache/{gauge_id}`
- Cache stores full `DelineateResponse` with GeoJSON geometry in SQLite
- Response properties: `gauge_id`, `area_km2`, `snap_lat`, `snap_lng`, `snap_distance_m`, `resolution`

## Goals

- Export cached watersheds as downloadable GeoJSON, Shapefile (ZIP), or GeoPackage files
- Default to GeoJSON format when no format specified
- Return 404 with clear error if watershed not cached (user must call `/delineate` first)
- Preserve all watershed properties in exported files

## User Stories

### US-001: Add ExportFormat enum and WATERSHED_NOT_FOUND error code
**Priority:** 1

**Description:** As a developer, I need the data models and error codes in place before implementing the endpoint.

**Acceptance Criteria:**
- [ ] Add `ExportFormat` enum to `src/delineator/api/models.py` with values: `geojson`, `shapefile`, `geopackage`
- [ ] Add `WATERSHED_NOT_FOUND` to `APIErrorCode` enum in `src/delineator/api/exceptions.py`
- [ ] Typecheck passes (`uv run pyright`)
- [ ] Lint passes (`uv run ruff check`)

### US-002: Add get_by_gauge_id method to cache
**Priority:** 2

**Description:** As a developer, I need to retrieve cached watersheds by gauge_id to support the export endpoint.

**Acceptance Criteria:**
- [ ] Add `get_by_gauge_id(gauge_id: str) -> DelineateResponse | None` method to `WatershedCache` class in `src/delineator/api/cache.py`
- [ ] Method queries SQLite by gauge_id and returns first match (or None if not found)
- [ ] Unit test verifies method returns cached response for existing gauge_id
- [ ] Unit test verifies method returns None for non-existent gauge_id
- [ ] Typecheck and lint pass

**Implementation Notes:**
- The cache uses coordinates as primary key with gauge_id as indexed column
- If same gauge_id used for different coordinates, return first match (known limitation)

### US-003: Create export service module
**Priority:** 3

**Description:** As a developer, I need functions to convert watershed responses to different file formats.

**Acceptance Criteria:**
- [ ] Create `src/delineator/api/export.py` with module docstring
- [ ] Implement `response_to_geodataframe(response: DelineateResponse) -> gpd.GeoDataFrame`
- [ ] Implement `export_geojson(response: DelineateResponse) -> bytes` returning FeatureCollection
- [ ] Implement `export_shapefile_zip(response: DelineateResponse, gauge_id: str) -> bytes` returning ZIP with .shp, .shx, .dbf, .prj, .cpg
- [ ] Implement `export_geopackage(response: DelineateResponse, gauge_id: str) -> bytes`
- [ ] Implement `export_watershed(response, gauge_id, format) -> tuple[bytes, str, str]` dispatcher returning (data, content_type, filename)
- [ ] Unit tests verify GeoDataFrame has correct columns and CRS (EPSG:4326)
- [ ] Unit tests verify each export format produces valid output
- [ ] Typecheck and lint pass

**Implementation Notes:**
- Use `geopandas` for file I/O (already a dependency)
- Use `shapely.geometry.shape()` to convert GeoJSON geometry
- Shapefile column names limited to 10 chars: use `snap_dist_m` instead of `snap_distance_m`
- Use tempfile for Shapefile/GeoPackage generation, clean up after

### US-004: Add export endpoint to routes
**Priority:** 4

**Description:** As a user, I want to download a watershed boundary file so I can use it in GIS software.

**Acceptance Criteria:**
- [ ] Add `GET /export/{gauge_id}` endpoint to `src/delineator/api/routes.py`
- [ ] Accept optional `format` query param (default: `geojson`)
- [ ] Return file with correct Content-Type header:
  - `application/geo+json` for GeoJSON
  - `application/zip` for Shapefile
  - `application/geopackage+sqlite3` for GeoPackage
- [ ] Return Content-Disposition header with filename: `{gauge_id}.geojson`, `{gauge_id}.shp.zip`, or `{gauge_id}.gpkg`
- [ ] Return 404 with `WATERSHED_NOT_FOUND` error code if gauge_id not in cache
- [ ] Return 422 for invalid format parameter
- [ ] Typecheck and lint pass

### US-005: Integration tests for export endpoint
**Priority:** 5

**Description:** As a developer, I need comprehensive tests to ensure the export endpoint works correctly.

**Acceptance Criteria:**
- [ ] Create `tests/api/test_export.py`
- [ ] Test: GET with format=geojson returns 200, correct content-type, valid GeoJSON FeatureCollection
- [ ] Test: GET without format param defaults to GeoJSON
- [ ] Test: GET with format=shapefile returns 200, ZIP containing .shp, .shx, .dbf, .prj files
- [ ] Test: GET with format=geopackage returns 200, valid GeoPackage (starts with SQLite magic bytes)
- [ ] Test: GET for non-existent gauge_id returns 404 with WATERSHED_NOT_FOUND
- [ ] Test: GET with invalid format returns 422
- [ ] Test: Exported files preserve all properties (gauge_id, area_km2, snap_lat, snap_lng, resolution)
- [ ] All tests pass (`uv run pytest tests/api/test_export.py -v`)

**Implementation Notes:**
- Use existing `conftest.py` fixtures pattern
- Mock `cache.get_by_gauge_id()` to return pre-built `DelineateResponse`
- Use `zipfile` module to validate Shapefile ZIP contents

## Functional Requirements

- FR-1: `GET /export/{gauge_id}` endpoint accepts gauge_id path parameter
- FR-2: Optional `format` query parameter with values: `geojson` (default), `shapefile`, `geopackage`
- FR-3: GeoJSON export returns FeatureCollection with single Feature
- FR-4: Shapefile export returns ZIP archive containing all sidecar files (.shp, .shx, .dbf, .prj, .cpg)
- FR-5: GeoPackage export returns single .gpkg file with "watershed" layer
- FR-6: All exports preserve properties: gauge_id, area_km2, snap_lat, snap_lng, snap_distance_m, resolution
- FR-7: Return 404 with WATERSHED_NOT_FOUND if gauge_id not in cache
- FR-8: Return 422 for invalid format values

## Non-Goals

- No on-demand delineation (cache-only)
- No KML/KMZ format support
- No batch export of multiple watersheds
- No coordinate-based lookup (gauge_id only)
- No additional metadata beyond existing response properties

## Technical Considerations

- Dependencies already available: `geopandas`, `fiona`, `shapely`
- Shapefile column names limited to 10 characters
- Use tempfile for intermediate file generation; ensure cleanup
- If same gauge_id used for different coordinates, returns first match (document limitation)

## Success Metrics

- All export formats download successfully and open in QGIS
- Export completes in under 1 second for typical watersheds
- No regressions in existing API tests

## Open Questions

None - all clarified.

---
project: Delineator
branchName: ralph/delineator-api
description: HTTP API for watershed delineation with caching, enabling Virtual-Gauges frontend integration

stories:
  US-001: { passes: true, notes: "Completed 2026-01-19" }
  US-002: { passes: true, notes: "Completed 2026-01-19" }
  US-003: { passes: true, notes: "Completed 2026-01-19" }
  US-004: { passes: true, notes: "Completed 2026-01-19" }
  US-005: { passes: true, notes: "Completed 2026-01-19" }
  US-006: { passes: true, notes: "Completed 2026-01-19" }
  US-007: { passes: true, notes: "Completed 2026-01-19" }
  US-008: { passes: true, notes: "Completed 2026-01-19" }
  US-009: { passes: true, notes: "Completed 2026-01-19" }
---

# PRD: Delineator HTTP API

## Introduction

The Virtual-Gauges team needs to call watershed delineation from their web frontend. Users click on a map to mark outlet locations, and the frontend requests watershed boundaries for those points.

This PRD defines an HTTP API that wraps the existing `delineate_outlet()` function, adds persistent caching (SQLite), and lazy-loads basin data with an LRU cache to stay within memory constraints.

### Technical Context

**Core function to wrap:** `delineate_outlet()` in `src/delineator/core/delineate.py`

**Inputs required:**

- Coordinates (lat, lng) in WGS84
- Basin data: `BasinData` containing `catchments_gdf` and `rivers_gdf` GeoDataFrames
- Raster paths for flow direction and accumulation

**Output:** `DelineatedWatershed` dataclass with:

- `geometry`: Shapely Polygon/MultiPolygon
- `snap_lat`, `snap_lon`: Snapped coordinates
- `snap_dist`: Distance in meters
- `area`: Watershed area in km²
- `resolution`: "high_res" or "low_res"

**Memory model:**

- Basin vector data: ~50-200MB per basin
- Raster data: Windowed reading only (~1-10MB per request)
- LRU cache with maxsize=5 keeps memory bounded (~1GB max)
- 4GB RAM (t3.medium) is sufficient

**Module location:** `src/delineator/api/`

## Goals

- Expose watershed delineation as a REST API for the Virtual-Gauges frontend
- Cache results to avoid recomputing identical requests
- Lazy-load basin data to minimize startup time and memory usage
- Provide health and cache monitoring endpoints
- Return standardized error codes for frontend error handling

## User Stories

### US-001: Add FastAPI dependencies

**Priority:** 1

**Description:** As a developer, I need FastAPI and uvicorn installed so I can build the HTTP API.

**Acceptance Criteria:**

- [ ] `fastapi>=0.115.0` added to pyproject.toml dependencies
- [ ] `uvicorn[standard]>=0.32.0` added to pyproject.toml dependencies
- [ ] `uv sync` runs successfully
- [ ] `uv run python -c "import fastapi; import uvicorn"` works

### US-002: Create API module skeleton

**Priority:** 2

**Description:** As a developer, I need the module structure in place so I can implement the API incrementally.

**Acceptance Criteria:**

- [ ] Directory `src/delineator/api/` created
- [ ] `__init__.py` exports `app` and `create_app`
- [ ] `doc.md` created with module documentation following project conventions
- [ ] `main.py` contains `create_app()` factory returning a FastAPI app
- [ ] `uv run uvicorn delineator.api:app --help` runs without import errors

### US-003: Implement Pydantic request/response models

**Priority:** 3

**Description:** As a developer, I need validated request/response models so the API has type-safe contracts.

**Acceptance Criteria:**

- [ ] `models.py` created with:
  - `DelineateRequest`: gauge_id (str), lat (float, -90 to 90), lng (float, -180 to 180)
  - `WatershedProperties`: gauge_id, area_km2, snap_lat, snap_lng, snap_distance_m, resolution
  - `WatershedFeature`: GeoJSON Feature with geometry dict and WatershedProperties
  - `DelineateResponse`: gauge_id, status, cached, watershed (WatershedFeature)
  - `ErrorResponse`: gauge_id, status, error_code, error_message
- [ ] `watershed_to_response()` function converts `DelineatedWatershed` to `DelineateResponse`
- [ ] Invalid coordinates rejected by Pydantic (e.g., lat=91 raises ValidationError)
- [ ] `uv run ruff check` passes

### US-004: Implement SQLite result cache

**Priority:** 4

**Description:** As a user, I want repeated requests for the same coordinates to return instantly from cache.

**Acceptance Criteria:**

- [ ] `cache.py` created with `WatershedCache` class
- [ ] SQLite schema: `watershed_cache(cache_key TEXT PRIMARY KEY, gauge_id TEXT, response_json TEXT, created_at TEXT, lat REAL, lng REAL, area_km2 REAL)`
- [ ] Cache key computed as `f"{round(lat, 6):.6f},{round(lng, 6):.6f}"`
- [ ] Methods: `get(lat, lng)`, `put(lat, lng, gauge_id, response)`, `delete_by_gauge_id(gauge_id)`, `stats()`
- [ ] Cache path configurable via `DELINEATOR_CACHE_DB` env var (default: `./cache/watersheds.db`)
- [ ] Database and parent directories created automatically if missing
- [ ] `uv run ruff check` passes

### US-005: Implement exception handling

**Priority:** 5

**Description:** As a frontend developer, I need standardized error codes so I can display appropriate messages to users.

**Acceptance Criteria:**

- [ ] `exceptions.py` created with:
  - `APIErrorCode` enum: `INVALID_COORDINATES`, `NO_RIVER_FOUND`, `NO_DATA_AVAILABLE`, `DELINEATION_FAILED`
  - `APIException` class with error_code, message, http_status
  - FastAPI exception handlers registered
- [ ] Pydantic ValidationError → 400 `INVALID_COORDINATES`
- [ ] `DelineationError` "does not fall within any unit catchment" → 404 `NO_RIVER_FOUND`
- [ ] `FileNotFoundError` for missing rasters/vectors → 404 `NO_DATA_AVAILABLE`
- [ ] Other `DelineationError` → 500 `DELINEATION_FAILED`
- [ ] Error responses match format: `{gauge_id, status: "error", error_code, error_message}`
- [ ] `uv run ruff check` passes

### US-006: Implement basin data loading with LRU cache

**Priority:** 6

**Description:** As an operator, I need basin data cached in memory so subsequent requests to the same basin are fast.

**Acceptance Criteria:**

- [ ] `deps.py` created with:
  - `get_data_dir()`: reads `MERIT_DATA_DIR` env var (default: `/data/merit-hydro`)
  - `@lru_cache(maxsize=5)` wrapped function for loading basin data
  - `get_basin_for_point(lat, lng)`: determines basin code, loads and returns `BasinData`
- [ ] Second request to same basin uses cached data (no disk I/O)
- [ ] Cache info accessible for stats endpoint
- [ ] `uv run ruff check` passes

### US-007: Implement POST /delineate endpoint

**Priority:** 7

**Description:** As a Virtual-Gauges user, I want to submit coordinates and receive the watershed boundary as GeoJSON.

**Acceptance Criteria:**

- [ ] `routes.py` created with `/delineate` POST endpoint
- [ ] Request body: `{"gauge_id": "string", "lat": float, "lng": float}`
- [ ] Response (success): `{gauge_id, status: "success", cached: bool, watershed: {type: "Feature", geometry: {...}, properties: {...}}}`
- [ ] Response (error): `{gauge_id, status: "error", error_code, error_message}`
- [ ] Cache checked before delineation; `cached: true` if hit
- [ ] Result stored in cache after successful delineation
- [ ] Delineation runs in thread pool executor (not blocking async loop)
- [ ] `uv run ruff check` passes

**Implementation Notes:**

- Use `asyncio.get_running_loop().run_in_executor(None, delineate_fn)` to run sync code
- Pass all required args to `delineate_outlet()`: gauge_id, lat, lng, gauge_name="", catchments_gdf, rivers_gdf, fdir_dir, accum_dir

### US-008: Implement monitoring endpoints

**Priority:** 8

**Description:** As an operator, I want health and cache stats endpoints for monitoring.

**Acceptance Criteria:**

- [ ] `GET /health` returns `{status: "healthy", version: "0.1.0", data_dir: string}`
- [ ] `GET /cache/stats` returns `{total_requests: int, cache_hits: int, cache_misses: int, hit_rate: float, cache_size: int}`
- [ ] `DELETE /cache/{gauge_id}` removes cache entry, returns 204 No Content
- [ ] Health endpoint returns 200 even if no basins loaded yet
- [ ] `uv run ruff check` passes

### US-009: Implement request logging

**Priority:** 9

**Description:** As an operator, I want request logs for debugging failed requests.

**Acceptance Criteria:**

- [ ] `logging_config.py` created with structured logging setup
- [ ] Each request logs: `timestamp | gauge_id | lat, lng | status | duration | cached=bool`
- [ ] Example: `2025-01-19 14:32:01 | gauge_001 | 47.6062, -122.3321 | SUCCESS | 4.2s | cached=false`
- [ ] Errors log: `2025-01-19 14:32:15 | gauge_002 | 51.5074, -0.1278 | ERROR | 1.1s | NO_RIVER_FOUND`
- [ ] Logs written to stdout (for CloudWatch capture)
- [ ] Optional file logging via `DELINEATOR_LOG_FILE` env var (e.g., `/var/log/delineator/requests.log`)
- [ ] `uv run ruff check` passes

## Functional Requirements

- FR-1: `POST /delineate` accepts `{gauge_id, lat, lng}` and returns GeoJSON watershed or error
- FR-2: Cache key is `(lat, lng)` rounded to 6 decimal places
- FR-3: Cache persists in SQLite database across API restarts
- FR-4: Response includes `cached: true/false` field
- FR-5: Basin data loaded on-demand with LRU cache (maxsize=5)
- FR-6: Data directory configurable via `MERIT_DATA_DIR` environment variable
- FR-7: Cache database path configurable via `DELINEATOR_CACHE_DB` environment variable
- FR-8: `GET /health` returns API status and configuration
- FR-9: `GET /cache/stats` returns cache hit/miss statistics
- FR-10: `DELETE /cache/{gauge_id}` invalidates a specific cached result
- FR-11: All requests logged with timestamp, gauge_id, coordinates, status, duration, and cached flag

## Non-Goals

- No authentication/authorization (internal tool behind VPN)
- No rate limiting (small user base)
- No server-side timeout enforcement (client handles timeout)
- No batch endpoint (single point per request)
- No WebSocket for progress updates
- No OpenAPI customization beyond FastAPI defaults

## Technical Considerations

- **Threading:** `delineate_outlet()` is CPU-bound and synchronous. Use `run_in_executor` with default thread pool.
- **Memory:** LRU cache maxsize=5 keeps ~1GB basin data in memory. 4GB RAM is sufficient.
- **Rasters:** Loaded via windowed reading, not cached in memory.
- **Startup:** No basin preloading. First request per basin incurs load time.
- **Logging:** Use Python `logging` module. Logs to stdout by default; optional file via `DELINEATOR_LOG_FILE`.

## Success Metrics

- Virtual-Gauges team can successfully call the API and display watersheds
- Cached requests return in <100ms
- Fresh delineations complete within 1-30 seconds (typical)
- API handles concurrent requests without errors

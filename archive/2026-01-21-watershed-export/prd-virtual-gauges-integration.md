---
project: "Delineator"
branchName: "ralph/virtual-gauges-integration"
description: "Enable Virtual-Gauges frontend integration with CORS support, geometry simplification, and resolution control"

stories:
  US-001: { passes: false, notes: "" }
  US-002: { passes: false, notes: "" }
  US-003: { passes: false, notes: "" }
  US-004: { passes: false, notes: "" }
  US-005: { passes: false, notes: "" }
  US-006: { passes: false, notes: "" }
  US-007: { passes: false, notes: "" }
---

# PRD: Virtual-Gauges Integration

## Introduction

The Virtual-Gauges team is building a watershed delineation feature where users click on a map to delineate upstream basins. Their Next.js frontend (localhost:3000) needs to call the Delineator API (localhost:8000) directly from the browser.

This integration requires three changes:

1. **CORS Configuration** - Browser security blocks cross-origin requests without proper headers
2. **Geometry Simplification** - Watershed polygons can have thousands of vertices (several MB), too large for Convex database storage and browser rendering
3. **Resolution Toggle** - Users want control over speed vs. precision trade-off

### Technical Context

**Delineator Architecture:**
- FastAPI app at `src/delineator/api/main.py` with factory pattern (`create_app()`)
- Routes in `routes.py`: `POST /delineate`, `GET /health`, `GET /export/{gauge_id}`, etc.
- SQLite cache in `cache.py` keyed by rounded lat/lng coordinates
- Core `delineate_outlet()` in `core/delineate.py` has existing `use_high_res` parameter

**Virtual-Gauges Architecture:**
- Next.js 16 + React 19 on port 3000
- Convex backend for data persistence
- Leaflet/react-leaflet for map rendering
- Will store watershed GeoJSON in Convex database

## Goals

- Enable cross-origin requests from Virtual-Gauges frontend (localhost:3000)
- Reduce watershed polygon payloads from several MB to <100KB
- Allow users to force low-resolution mode for faster results
- Maintain backward compatibility with existing API consumers
- Provide comprehensive test coverage for all changes

## User Stories

### US-001: Add CORS middleware to API
**Priority:** 1

**Description:** As a frontend developer, I want the Delineator API to accept cross-origin requests so that I can call it from the Virtual-Gauges browser app.

**Acceptance Criteria:**
- [ ] CORSMiddleware added to FastAPI app in `main.py`
- [ ] Default allowed origins: `http://localhost:3000`, `http://127.0.0.1:3000`
- [ ] Allowed methods: GET, POST, DELETE
- [ ] Allowed headers: `*`
- [ ] `_get_cors_origins()` helper reads from `DELINEATOR_CORS_ORIGINS` env var (comma-separated)
- [ ] Falls back to default localhost origins when env var not set
- [ ] Typecheck passes (`uv run pyright`)
- [ ] Lint passes (`uv run ruff check`)

**Implementation Notes:**
- Add middleware before `register_exception_handlers()` and `include_router()` calls
- Follow existing `os.getenv()` pattern used in `deps.py` and `cache.py`

---

### US-002: Add CORS unit tests
**Priority:** 1

**Description:** As a developer, I want CORS behavior tested so that regressions are caught automatically.

**Acceptance Criteria:**
- [ ] New file `tests/api/test_cors.py` created
- [ ] Test: OPTIONS preflight request returns correct CORS headers
- [ ] Test: Allowed origin receives `Access-Control-Allow-Origin` header
- [ ] Test: Unauthorized origin does not receive CORS headers
- [ ] Test: `_get_cors_origins()` returns defaults when env var not set
- [ ] Test: `_get_cors_origins()` parses comma-separated env var correctly
- [ ] All tests pass (`uv run pytest tests/api/test_cors.py`)

**Implementation Notes:**
- Use `patch.dict("os.environ", ...)` for env var tests
- Send `Origin` header in requests to test CORS behavior

---

### US-003: Add geometry simplification function
**Priority:** 2

**Description:** As an API consumer, I want watershed geometries simplified so that payloads are small enough for storage and rendering.

**Acceptance Criteria:**
- [ ] New function `simplify_geometry()` added to `src/delineator/api/models.py`
- [ ] Uses Shapely's `simplify()` with `preserve_topology=True`
- [ ] Default tolerance: 0.001 degrees (~100m at equator)
- [ ] Handles both `Polygon` and `MultiPolygon` types
- [ ] Function has type hints and docstring
- [ ] Typecheck passes

**Implementation Notes:**
```python
DEFAULT_SIMPLIFY_TOLERANCE = 0.001  # ~100m at equator

def simplify_geometry(
    geometry: Polygon | MultiPolygon,
    tolerance: float = DEFAULT_SIMPLIFY_TOLERANCE,
) -> Polygon | MultiPolygon:
    """Simplify geometry to reduce vertex count while preserving topology."""
    return geometry.simplify(tolerance, preserve_topology=True)
```

---

### US-004: Integrate simplification into API response
**Priority:** 2

**Description:** As an API consumer, I want the `/delineate` endpoint to return simplified geometry automatically.

**Acceptance Criteria:**
- [ ] `watershed_to_response()` in `models.py` calls `simplify_geometry()` before `mapping()`
- [ ] Simplification applied before geometry is converted to GeoJSON dict
- [ ] Existing tests still pass (mock fixtures use simple geometries)
- [ ] Typecheck passes

**Implementation Notes:**
- Simplification is applied in the API layer, not core, for separation of concerns
- This ensures cached responses contain simplified geometry

---

### US-005: Add simplification unit tests
**Priority:** 2

**Description:** As a developer, I want simplification behavior tested to ensure correctness.

**Acceptance Criteria:**
- [ ] Tests added to `tests/api/test_models.py` (create file if needed)
- [ ] Test: Complex polygon (256+ vertices) is reduced to fewer vertices
- [ ] Test: Simplified geometry remains valid (`is_valid` is True)
- [ ] Test: MultiPolygon geometries are handled correctly
- [ ] New fixture `mock_complex_watershed` in `tests/api/conftest.py` with high-vertex polygon
- [ ] All tests pass

**Implementation Notes:**
- Create complex polygon with `Point.buffer(0.1, resolution=64)` for 256+ vertices
- Verify vertex count reduction: `len(simplified.exterior.coords) < len(original.exterior.coords)`

---

### US-006: Add force_low_res parameter
**Priority:** 3

**Description:** As an API consumer, I want to optionally force low-resolution mode so that I can get faster results when precision isn't critical.

**Acceptance Criteria:**
- [ ] `force_low_res: bool = False` field added to `DelineateRequest` in `models.py`
- [ ] Field has Pydantic `Field()` with description for OpenAPI docs
- [ ] `routes.py` passes `use_high_res=not request.force_low_res` to `delineate_outlet()`
- [ ] Cache key includes resolution: format `"{lat},{lng},{high|low}"`
- [ ] `cache.py` methods `get()` and `put()` accept `force_low_res` parameter
- [ ] Backward compatible: requests without parameter use default (high-res when applicable)
- [ ] Typecheck passes

**Implementation Notes:**
- Update `_make_cache_key()` helper in `cache.py` to include resolution suffix
- The core `delineate_outlet()` already has `use_high_res` param - just wire it through

---

### US-007: Add force_low_res tests
**Priority:** 3

**Description:** As a developer, I want force_low_res behavior tested for correctness.

**Acceptance Criteria:**
- [ ] Test: Request without `force_low_res` defaults to False
- [ ] Test: Request with `force_low_res=true` is accepted
- [ ] Test: Different cache entries for same coordinates with different resolution
- [ ] Test: Invalid `force_low_res` type (e.g., string "yes") is rejected with 400
- [ ] New fixture `mock_watershed_low_res` with `resolution="low_res"`
- [ ] All tests pass

**Implementation Notes:**
- Cache isolation test: POST with force_low_res=false, then POST with force_low_res=true to same coords, verify second is cache miss

---

## Functional Requirements

- FR-1: API must include `CORSMiddleware` allowing requests from configurable origins
- FR-2: Default CORS origins must be `http://localhost:3000` and `http://127.0.0.1:3000`
- FR-3: CORS origins must be configurable via `DELINEATOR_CORS_ORIGINS` environment variable
- FR-4: All watershed geometries returned by `/delineate` must be simplified with 0.001 degree tolerance
- FR-5: Simplified geometries must remain valid (no self-intersections)
- FR-6: `POST /delineate` must accept optional `force_low_res` boolean parameter
- FR-7: Cache keys must include resolution mode to isolate high-res and low-res results
- FR-8: API must remain backward compatible (existing requests without new parameters work unchanged)

## Non-Goals

- No configurable simplification tolerance via API parameter (fixed at 0.001 degrees)
- No adaptive simplification based on watershed area
- No changes to CLI behavior (only API layer affected)
- No changes to export formats (simplification only affects `/delineate` response)
- No authentication or rate limiting for CORS
- No production CORS domains in code (configured via environment variable)

## Technical Considerations

- **Middleware Order:** CORS middleware must be added before routes in `create_app()`
- **Cache Migration:** New cache key format is backward compatible; old entries simply won't match new requests
- **Shapely Import:** `simplify` function is available as `from shapely import simplify` or via geometry method
- **Testing Pattern:** Follow existing patterns in `tests/api/test_routes.py` and `tests/api/conftest.py`

## Success Metrics

- Virtual-Gauges frontend can call `/delineate` without CORS errors
- Watershed GeoJSON payloads reduced by >90% (from MB to <100KB)
- All existing tests continue to pass
- New features have >90% test coverage

## Open Questions

- Should we clear the cache when deploying this update? (New cache key format means old entries are stale but not harmful)
- Should `force_low_res` be logged for analytics on user preferences?

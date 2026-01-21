# Feature Requests: Virtual-Gauges Integration

**Date:** 2026-01-21
**From:** Virtual-Gauges Team
**Priority:** Required for MVP

---

## Context

We're building a watershed delineation feature into Virtual-Gauges where users can:

1. Click on the map to add a gauge location
2. Click "Delineate Watershed" to extract the upstream basin
3. View the watershed polygon on the map
4. Store the result for later viewing

The frontend will call the Delineator API directly from the browser (client-side fetch) during local development, with plans to move to a server-side call for production.

---

## Request 1: CORS Configuration

**Why:** Browser security prevents cross-origin requests. The Virtual-Gauges dev server runs on `localhost:3000`, but the Delineator API runs on `localhost:8000`.

**What we need:** Add CORS middleware to allow requests from the frontend.

**Suggested implementation:**

```python
# In src/delineator/api/main.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",    # Next.js dev server
        "http://127.0.0.1:3000",    # Alternative localhost
        # Add production origins later
    ],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)
```

**Endpoints we'll call:**

- `POST /delineate` - Main delineation
- `GET /health` - Health check (optional)
- `GET /export/{gauge_id}` - Export (future)

---

## Request 2: Geometry Simplification

**Why:** Watershed polygons can have thousands of vertices, resulting in large GeoJSON payloads (several MB). We need to store these in our database (Convex) and render them in the browser. Simplified geometries reduce storage costs and improve rendering performance.

**What we need:** Simplify the watershed geometry before returning it in the API response.

**Suggested implementation:**

```python
# In src/delineator/core/delineate.py, before returning DelineatedWatershed
from shapely import simplify

# Simplify with ~100m tolerance (0.001 degrees ≈ 111m at equator)
simplified_geometry = simplify(geometry, tolerance=0.001, preserve_topology=True)
```

**Options to consider:**

1. **Fixed tolerance** - Always simplify to ~100m (simplest)
2. **Request parameter** - Add optional `simplify_tolerance` to `POST /delineate`
3. **Adaptive** - More aggressive simplification for larger watersheds

We're fine with option 1 for now. If you prefer option 2, we can pass a parameter.

**Note:** `preserve_topology=True` ensures the polygon remains valid (no self-intersections).

---

## Request 3 (Nice-to-have): Resolution Toggle Parameter

**Current behavior:** The API auto-switches between `high_res` and `low_res` based on watershed area (threshold: 10,000 km²).

**What we'd like:** An optional parameter to force low-res mode even for small watersheds, giving users control over speed vs. precision.

**Suggested API change:**

```python
class DelineateRequest(BaseModel):
    gauge_id: str
    lat: float
    lng: float
    force_low_res: bool = False  # New optional parameter
```

If `force_low_res=True`, skip raster-based delineation regardless of area.

---

## Timeline

We're aiming to have a working proof-of-concept this week. CORS is blocking us immediately. Simplification is important for storage but not blocking the initial demo.

---

**Contact:** Virtual-Gauges Team

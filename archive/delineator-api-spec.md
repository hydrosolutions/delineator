# Delineator API Specification

**From**: Virtual-Gauges Team
**To**: Delineator Team
**Date**: January 2026

## Overview

We're building an internal tool (Virtual-Gauges) where users can click on a map to mark locations and then request watershed delineation for those locations. We need the Delineator to be exposed as an HTTP API that we can call from our frontend.

## What We Need

A single endpoint that:

1. Accepts coordinates (lat/lng)
2. Runs watershed delineation
3. Returns the watershed boundary as GeoJSON
4. Caches results so repeated requests for the same coordinates don't re-compute

## API Contract

### Endpoint

```
POST /delineate
```

### Request

```json
{
  "gauge_id": "string",      // Unique identifier from our system
  "lat": 47.6062,            // Latitude (WGS84)
  "lng": -122.3321           // Longitude (WGS84)
}
```

### Response (Success - 200)

```json
{
  "gauge_id": "string",
  "status": "success",
  "cached": false,           // true if result was from cache
  "watershed": {
    "type": "Feature",
    "geometry": {
      "type": "Polygon",     // or MultiPolygon
      "coordinates": [...]
    },
    "properties": {
      "gauge_id": "string",
      "area_km2": 1234.56,
      "snap_lat": 47.6065,   // Where the outlet snapped to river
      "snap_lng": -122.3318,
      "snap_distance_m": 45.2,
      "resolution": "high_res"  // or "low_res" for large watersheds
    }
  }
}
```

### Response (Error - 4xx/5xx)

```json
{
  "gauge_id": "string",
  "status": "error",
  "error_code": "NO_RIVER_FOUND",  // or other error codes
  "error_message": "Could not find a river within snapping distance of the specified coordinates"
}
```

### Error Codes

| Code | HTTP Status | Meaning |
|------|-------------|---------|
| `INVALID_COORDINATES` | 400 | Lat/lng out of valid range |
| `NO_RIVER_FOUND` | 404 | No river found near coordinates |
| `NO_DATA_AVAILABLE` | 404 | MERIT data not available for this region |
| `DELINEATION_FAILED` | 500 | Unexpected error during processing |

## Caching Requirements

- Cache key: `(lat, lng)` rounded to 6 decimal places
- Cache should persist across API restarts (file-based or database)
- Return `"cached": true` in response when serving from cache
- No cache expiration needed (watersheds don't change)

## Performance Expectations

- Most delineations should complete in 1-30 seconds
- For very large watersheds (>10,000 km²), up to 2 minutes is acceptable
- We'll handle timeout on our end (60 second default, user can wait longer)

## Infrastructure Notes

- Will run on AWS EC2 (t3.medium or similar)
- MERIT-Hydro data will be on attached EBS volume at `/data/merit-hydro/`
- Talk to IT about provisioning

## Nice-to-Haves (Not Required for V1)

- `GET /health` endpoint for monitoring
- `GET /cache/stats` to see cache hit rate
- `DELETE /cache/{gauge_id}` to invalidate a cached result

## Questions for Delineator Team

1. How long does a typical delineation take? (So we can set appropriate timeouts)
2. Are there any coordinate ranges that will always fail? (e.g., oceans, Antarctica)
3. Any memory/CPU requirements we should communicate to IT?

---

## Example Usage

```bash
# Request delineation
curl -X POST https://delineator-api.internal/delineate \
  -H "Content-Type: application/json" \
  -d '{"gauge_id": "gauge_001", "lat": 47.6062, "lng": -122.3321}'

# Response
{
  "gauge_id": "gauge_001",
  "status": "success",
  "cached": false,
  "watershed": {
    "type": "Feature",
    "geometry": {
      "type": "MultiPolygon",
      "coordinates": [[[[...]]]]
    },
    "properties": {
      "gauge_id": "gauge_001",
      "area_km2": 523.7,
      "snap_lat": 47.6065,
      "snap_lng": -122.3318,
      "snap_distance_m": 42.1,
      "resolution": "high_res"
    }
  }
}
```

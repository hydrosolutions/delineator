# Bug Report: Single-Point Bounding Box Causes ValueError

## Summary

When delineating a single outlet, the CLI fails with a `ValueError` because the bounding box calculation produces identical min/max coordinates for a single point.

## Steps to Reproduce

1. Create an outlets file with a single outlet:

```toml
# outlets.toml
[[outlets]]
gauge_id = "test_outlet"
lat = -25.528206
lng = 32.181872
gauge_name = "Test Location"
```

2. Create a master config:

```toml
# delineate.toml
[settings]
output_dir = "./output"

[[regions]]
name = "test_region"
outlets = "outlets.toml"
```

3. Run the delineation:

```bash
delineator run delineate.toml
```

## Expected Behavior

The CLI should successfully determine the required basin and proceed with delineation.

## Actual Behavior

The CLI crashes with:

```
ValueError: Invalid bbox: min_lon (32.181872) must be less than max_lon (32.181872)
```

## Stack Trace

```
File "/Users/nicolaslazaro/Desktop/work/delineator/src/delineator/cli/main.py", line 200, in run_command
    required_basins = get_required_basins(all_outlets)
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
File "/Users/nicolaslazaro/Desktop/work/delineator/src/delineator/core/data_check.py", line 315, in get_required_basins
    basins = get_basins_for_bbox(min_lon=min_lon, min_lat=min_lat, max_lon=max_lon, max_lat=max_lat)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
File "/Users/nicolaslazaro/Desktop/work/delineator/src/delineator/download/basin_selector.py", line 105, in get_basins_for_bbox
    raise ValueError(f"Invalid bbox: min_lon ({min_lon}) must be less than max_lon ({max_lon})")
ValueError: Invalid bbox: min_lon (32.181872) must be less than max_lon (32.181872)
```

## Root Cause

In `src/delineator/core/data_check.py`, the `get_required_basins()` function computes a bounding box from all outlet coordinates. When there's only a single outlet (or multiple outlets at the exact same location), the min and max coordinates are identical, which fails the validation in `get_basins_for_bbox()`.

## Suggested Fix

Add a small buffer (e.g., 0.001 degrees) when the bounding box collapses to a point. This could be done in either:

1. **`get_required_basins()`** in `data_check.py` — add buffer after computing bbox if min == max
2. **`get_basins_for_bbox()`** in `basin_selector.py` — handle point queries by adding internal buffer

Example fix in `data_check.py`:

```python
# After computing min/max coordinates
POINT_BUFFER = 0.001  # ~111 meters at equator

if min_lon == max_lon:
    min_lon -= POINT_BUFFER
    max_lon += POINT_BUFFER

if min_lat == max_lat:
    min_lat -= POINT_BUFFER
    max_lat += POINT_BUFFER
```

## Environment

- OS: macOS (Darwin 24.6.0)
- Python: 3.x (via uv)
- Delineator: current main branch (commit 493a316)

## Severity

**Medium** — Prevents single-outlet delineation, which is a common use case.

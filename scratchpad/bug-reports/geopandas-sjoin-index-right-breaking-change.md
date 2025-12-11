# Bug Report: GeoPandas 1.0 Breaking Change — `index_right` Column Renamed

## Summary

The delineation fails with `KeyError: 'index_right'` due to a breaking API change in GeoPandas 1.0.0. The `sjoin()` method no longer creates an `index_right` column when the right GeoDataFrame has a named index — it uses the index name instead.

## Error

```
KeyError: 'index_right'
```

**Location:** `src/delineator/core/delineate.py`, lines 206 and 209

## Steps to Reproduce

```bash
delineator run config.toml --verbose
```

With any valid outlet point (e.g., `-25.528206, 32.181872`).

## Root Cause

### The Breaking Change

**GeoPandas 1.0.0** (released June 24, 2024) changed `sjoin()` behavior:

| GeoPandas Version | Right GDF Index Type | Result Column Name |
|-------------------|---------------------|-------------------|
| < 1.0.0           | Any                 | `index_right`     |
| >= 1.0.0          | Unnamed (default)   | `index_right`     |
| >= 1.0.0          | **Named**           | Uses index name   |

This was documented as a "backwards incompatible API change" in the GeoPandas changelog.

### How It Breaks the Code

**Step 1:** `load_basin_data()` sets a named index (line 138):
```python
catchments_gdf.set_index("COMID", inplace=True)  # Index is now named "COMID"
```

**Step 2:** `delineate_outlet()` performs spatial join (line 204):
```python
joined = gpd.sjoin(point_gdf, catchments_gdf, how="left", predicate="intersects")
```

**Result with GeoPandas 1.0+:**
```python
joined.columns.tolist()  # ['geometry', 'COMID', 'unitarea']
# NO 'index_right' column — it's named 'COMID' instead
```

**Step 3:** Code tries to access `index_right` (lines 206, 209):
```python
if joined.empty or pd.isna(joined.iloc[0]["index_right"]):  # KeyError!
    ...
terminal_comid = joined.iloc[0]["index_right"]  # KeyError!
```

## Environment

- **GeoPandas installed:** 1.1.1
- **Project requirement:** `geopandas>=1.0.0` (pyproject.toml line 14)
- **Breaking change introduced:** GeoPandas 1.0.0

## Affected Code

**File:** `src/delineator/core/delineate.py`

```python
# Line 138 — Creates named index
catchments_gdf.set_index("COMID", inplace=True)

# Line 206 — Expects 'index_right' but column is named 'COMID'
if joined.empty or pd.isna(joined.iloc[0]["index_right"]):

# Line 209 — Same issue
terminal_comid = joined.iloc[0]["index_right"]
```

## Suggested Fixes

### Option 1: Use the actual index name

```python
# Line 206
index_col = catchments_gdf.index.name or "index_right"
if joined.empty or pd.isna(joined.iloc[0][index_col]):

# Line 209
terminal_comid = joined.iloc[0][index_col]
```

### Option 2: Access via column that matches the index name

Since we know the index is always `COMID`:

```python
# Line 206
if joined.empty or pd.isna(joined.iloc[0]["COMID"]):

# Line 209
terminal_comid = joined.iloc[0]["COMID"]
```

### Option 3: Reset index before sjoin

```python
# Before sjoin, reset to unnamed index
catchments_for_join = catchments_gdf.reset_index()
joined = gpd.sjoin(point_gdf, catchments_for_join, how="left", predicate="intersects")
# Now 'index_right' will exist, and COMID is a regular column
```

### Option 4: Use rsuffix parameter (if applicable)

Check if GeoPandas `sjoin` has parameters to control column naming.

## References

- [GeoPandas Changelog — Version 1.0.0](https://geopandas.org/en/latest/docs/changelog.html)
- [GitHub Issue #846: Spatial join loses index names of input](https://github.com/geopandas/geopandas/issues/846)
- [GitHub Issue #438: ENH: Preserve index names on sjoin](https://github.com/geopandas/geopandas/issues/438)
- [GitHub PR #2144: ENH: preserve index names in sjoin](https://github.com/geopandas/geopandas/pull/2144)

## Severity

**Critical** — All delineation operations fail. No watersheds can be delineated until this is fixed.

## Notes

- The missing `.prj` file (CRS) in downloaded shapefiles is a separate issue and NOT related to this bug
- The code at line 139 (`set_crs(..., allow_override=True)`) correctly handles missing CRS
- This bug affects any code path that uses `sjoin` with a GeoDataFrame that has a named index

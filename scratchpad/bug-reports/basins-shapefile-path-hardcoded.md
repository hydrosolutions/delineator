# Bug: Basin selector ignores `data_dir` config setting

## Summary

The `basin_selector.py` module uses a hardcoded path relative to the project root for the Level 2 basins shapefile, ignoring the `data_dir` setting in the configuration file.

## Reproduction

1. Set `data_dir = "~/data/merit-hydro"` in config
2. Have MERIT-Hydro data at `~/data/merit-hydro/shp/basins_level2/merit_hydro_vect_level2.shp`
3. Run `delineator run config.toml`

## Expected

Tool should look for basins shapefile at `{data_dir}/shp/basins_level2/merit_hydro_vect_level2.shp`

## Actual

Tool looks at hardcoded path: `{PROJECT_ROOT}/data/shp/basins_level2/merit_hydro_vect_level2.shp`

```
FileNotFoundError: Basins shapefile not found: /Users/nicolaslazaro/Desktop/work/delineator/data/shp/basins_level2/merit_hydro_vect_level2.shp
```

## Root Cause

In `src/delineator/download/basin_selector.py` (lines 21-23):

```python
_MODULE_DIR = Path(__file__).parent
_PROJECT_ROOT = _MODULE_DIR.parent.parent.parent
DEFAULT_BASINS_SHAPEFILE = str(_PROJECT_ROOT / "data" / "shp" / "basins_level2" / "merit_hydro_vect_level2.shp")
```

This path is computed at module load time and doesn't respect the runtime `data_dir` configuration.

## Suggested Fix

The `get_required_basins()` function in `data_check.py` (which calls into `basin_selector.py`) should pass the resolved `data_dir` path to the basin selector functions, rather than relying on the hardcoded default.

Alternatively, check `DELINEATOR_DATA_DIR` environment variable as a fallback in `basin_selector.py`.

## Affected Files

- `src/delineator/download/basin_selector.py`
- `src/delineator/core/data_check.py`

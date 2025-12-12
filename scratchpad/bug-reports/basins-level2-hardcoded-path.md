# Bug: basins_level2 shapefile path is hardcoded to delineator install directory

## Summary

The `basins_level2` shapefile path is hardcoded relative to the delineator package location, not derived from the configurable `data_dir`. This prevents running delineations with data stored in a different location.

## Current Behavior

In `src/delineator/download/basin_selector.py`, the default path is:

```python
DEFAULT_BASINS_SHAPEFILE = Path(__file__).parent.parent.parent.parent / "data/shp/basins_level2/merit_hydro_vect_level2.shp"
```

This resolves to the delineator install directory regardless of where the user's data is located.

## Expected Behavior

The `basins_level2` shapefile should be loaded from the same `data_dir` that other MERIT data uses (rasters, catchments, rivers), which is derived from `output_dir.parent / "data"`.

## Impact

Users cannot run delineations with data stored outside the delineator install directory without:
- Symlinking the data folder back to the delineator directory
- Copying the basins_level2 folder manually

## Reproduction

```bash
# Move data to a separate directory
mv /path/to/delineator/data /path/to/my-project/data

# Try to run with output in that directory
cd /path/to/my-project
delineator run config.toml -o ./output

# Error: Basins shapefile not found: /path/to/delineator/data/shp/basins_level2/...
```

## Suggested Fix

1. Remove the hardcoded `DEFAULT_BASINS_SHAPEFILE`
2. Pass `data_dir` to `get_required_basins()` and `get_basins_for_bbox()`
3. Construct the path as `data_dir / "shp" / "basins_level2" / "merit_hydro_vect_level2.shp"`

This aligns with how other data paths are handled in `data_check.py` and `delineate.py`.

## Affected Files

- `src/delineator/download/basin_selector.py` - hardcoded default
- `src/delineator/core/data_check.py:315` - calls `get_basins_for_bbox()` without data_dir
- `src/delineator/cli/main.py:200` - calls `get_required_basins()` without data_dir

## Workaround

Symlink the data folder back to the delineator install directory:

```bash
ln -s /path/to/my-project/data /path/to/delineator/data
```

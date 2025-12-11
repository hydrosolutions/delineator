# Bug Report: Downloaded Files Path Mismatch

## Summary

The Google Drive download code saves shapefile components into subdirectories (e.g., `cat_pfaf_12/`), but the data availability check expects them directly in the parent `merit_catchments/` directory.

## Expected Path (what data_check.py looks for)

```
data/shp/merit_catchments/cat_pfaf_12_MERIT_Hydro_v07_Basins_v01.shp
data/shp/merit_rivers/riv_pfaf_12_MERIT_Hydro_v07_Basins_v01.shp
```

## Actual Path (where gdrive_client.py downloads to)

```
data/shp/merit_catchments/cat_pfaf_12/cat_pfaf_12_MERIT_Hydro_v07_Basins_v01.shp
data/shp/merit_catchments/riv_pfaf_12/riv_pfaf_12_MERIT_Hydro_v07_Basins_v01.shp
```

## Affected Code

**data_check.py line 72:**
```python
data_dir / "shp" / "merit_catchments" / f"cat_pfaf_{basin}_MERIT_Hydro_v07_Basins_v01.shp"
```

**gdrive_client.py** downloads to subdirectories like `cat_pfaf_12/`.

## Suggested Fix

Either:
1. Update `gdrive_client.py` to download files directly into `merit_catchments/` (no subdirectory)
2. Update `data_check.py` to look in the subdirectory path

## Workaround

Move the files up one level:
```bash
mv data/shp/merit_catchments/cat_pfaf_12/* data/shp/merit_catchments/
mv data/shp/merit_rivers/riv_pfaf_12/* data/shp/merit_rivers/
```

## Severity

**High** — Downloads succeed but delineation still fails due to path mismatch.

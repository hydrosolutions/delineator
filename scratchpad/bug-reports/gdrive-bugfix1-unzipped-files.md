# Bug Report: MERIT-Basins Bugfix1 Files Are No Longer Zipped

## Summary

The MERIT-Basins bugfix1 version on Google Drive contains individual shapefile components (`.shp`, `.dbf`, `.shx`, `.cpg`) instead of `.zip` archives. The current download code expects ZIP files and fails to find them.

## Environment

- **Google Drive Folder ID (bugfix1 pfaf_level_02):** `1owkvZQBMZbvRv3V4Ff3xQPEgmAC48vJo`
- **Parent folder (bugfix1 root):** `1J8vyqCnSdquY1cRI1PPsXzMBLBXKzzoW`

## Expected File Format (what code expects)

```
cat_pfaf_12_MERIT_Hydro_v07_Basins_v01.zip
riv_pfaf_12_MERIT_Hydro_v07_Basins_v01.zip
```

## Actual File Format (what exists on Google Drive)

```
cat_pfaf_12_MERIT_Hydro_v07_Basins_v01_bugfix1.cpg
cat_pfaf_12_MERIT_Hydro_v07_Basins_v01_bugfix1.dbf
cat_pfaf_12_MERIT_Hydro_v07_Basins_v01_bugfix1.shp
cat_pfaf_12_MERIT_Hydro_v07_Basins_v01_bugfix1.shx
```

Note two differences:
1. Files are **not zipped** — individual shapefile components are stored separately
2. Filename includes **`_bugfix1` suffix** before the extension

## Affected Code

**File:** `src/delineator/download/gdrive_client.py`

```python
# Lines 39-40: Current file naming patterns
CATCHMENTS_PATTERN = "cat_pfaf_{basin:02d}_MERIT_Hydro_v07_Basins_v01"
RIVERS_PATTERN = "riv_pfaf_{basin:02d}_MERIT_Hydro_v07_Basins_v01"
```

The code constructs a ZIP filename like:
```python
zip_filename = f"{filename}.zip"  # e.g., "cat_pfaf_12_MERIT_Hydro_v07_Basins_v01.zip"
```

## Error Message

```
File not found on Google Drive: cat_pfaf_12_MERIT_Hydro_v07_Basins_v01.zip.
Check that the basin code is valid and the file exists in folder 1owkvZQBMZbvRv3V4Ff3xQPEgmAC48vJo
```

## Available Files in Bugfix1 Folder

Total: 567 files (individual shapefile components for all 61 basins × 2 types × ~4 extensions)

Sample listing:
```
cat_pfaf_11_MERIT_Hydro_v07_Basins_v01_bugfix1.cpg
cat_pfaf_11_MERIT_Hydro_v07_Basins_v01_bugfix1.dbf
cat_pfaf_11_MERIT_Hydro_v07_Basins_v01_bugfix1.shp
cat_pfaf_11_MERIT_Hydro_v07_Basins_v01_bugfix1.shx
cat_pfaf_12_MERIT_Hydro_v07_Basins_v01_bugfix1.cpg
cat_pfaf_12_MERIT_Hydro_v07_Basins_v01_bugfix1.dbf
cat_pfaf_12_MERIT_Hydro_v07_Basins_v01_bugfix1.shp
cat_pfaf_12_MERIT_Hydro_v07_Basins_v01_bugfix1.shx
...
riv_pfaf_11_MERIT_Hydro_v07_Basins_v01_bugfix1.cpg
riv_pfaf_11_MERIT_Hydro_v07_Basins_v01_bugfix1.dbf
riv_pfaf_11_MERIT_Hydro_v07_Basins_v01_bugfix1.prj
riv_pfaf_11_MERIT_Hydro_v07_Basins_v01_bugfix1.shp
riv_pfaf_11_MERIT_Hydro_v07_Basins_v01_bugfix1.shx
...
```

## Suggested Fix Options

### Option 1: Download Individual Files (Recommended)

Modify `gdrive_client.py` to download all shapefile components individually:

```python
SHAPEFILE_EXTENSIONS = ['.shp', '.dbf', '.shx', '.cpg', '.prj']
CATCHMENTS_PATTERN_BUGFIX = "cat_pfaf_{basin:02d}_MERIT_Hydro_v07_Basins_v01_bugfix1"
RIVERS_PATTERN_BUGFIX = "riv_pfaf_{basin:02d}_MERIT_Hydro_v07_Basins_v01_bugfix1"

def download_catchments(basin: int, dest_dir: Path, ...) -> Path:
    base_name = CATCHMENTS_PATTERN_BUGFIX.format(basin=basin)
    for ext in SHAPEFILE_EXTENSIONS:
        filename = f"{base_name}{ext}"
        # Download each file individually
        ...
```

### Option 2: Support Both Formats

Add configuration or auto-detection to handle both:
- ZIP files (original v1.0)
- Individual files (bugfix1)

### Option 3: Use Original v1.0 Folder

Fall back to the original v1.0 folder which may still have ZIP files:
- **Folder ID:** `1uCQFmdxFbjwoT9OYJxw-pXaP8q_GYH1a`

This is a workaround, not a fix, as bugfix1 likely contains important corrections.

## Workaround for Users

Until this is fixed, users can:

1. Manually download the shapefile components from Google Drive
2. Place them in `data/shp/merit_catchments/` with the expected naming:
   ```
   cat_pfaf_12_MERIT_Hydro_v07_Basins_v01.shp
   cat_pfaf_12_MERIT_Hydro_v07_Basins_v01.dbf
   cat_pfaf_12_MERIT_Hydro_v07_Basins_v01.shx
   cat_pfaf_12_MERIT_Hydro_v07_Basins_v01.cpg
   ```

## Severity

**High** — Blocks all Google Drive vector downloads when using the recommended bugfix1 data source.

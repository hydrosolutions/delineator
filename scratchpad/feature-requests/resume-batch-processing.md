# Feature Request: Resume/Skip Functionality for Batch Processing

## Summary

Add the ability to skip already-delineated outlets when running batch jobs, allowing users to resume interrupted runs without re-processing completed work.

## Problem

Currently, if a batch run is interrupted (crash, Ctrl+C, timeout) or a user needs to add outlets to an existing dataset, they must either:

1. Re-process all outlets from scratch (wasteful for large batches)
2. Manually edit outlets.toml to remove completed entries (error-prone, tedious)

For large batches (10k+ outlets), re-processing can take hours/days.

## Proposed Solution

### Option A: `--skip-existing` flag

```bash
delineator run config.toml --skip-existing
```

Before delineating each outlet, check if `gauge_id` already exists in the output shapefile for that region. If it does, skip processing.

**Implementation notes:**

- Load existing shapefile at start of each region (if exists)
- Build a `set` of existing `gauge_id` values
- Skip outlets whose `gauge_id` is in the set
- Append new watersheds to existing shapefile (requires switching to GeoPackage or merging shapefiles)

### Option B: Checkpoint file approach

Write a checkpoint file (`output_dir/.checkpoint.json`) tracking processed outlets:

```json
{
  "config_hash": "abc123",
  "completed": {
    "region_name": ["gauge_id_1", "gauge_id_2", ...]
  }
}
```

On startup with `--resume`, read checkpoint and skip completed outlets.

**Pros:** Works with current shapefile-per-region architecture
**Cons:** Extra file to manage, can get out of sync

### Option C: Per-outlet output files

Write one shapefile per outlet instead of per region:

```
output/REGION_NAME=foo/data_type=shapefiles/gauge_id_001.shp
output/REGION_NAME=foo/data_type=shapefiles/gauge_id_002.shp
```

Skip if file exists. Provide a separate `delineator merge` command to combine into single shapefile.

**Pros:** Natural resume, crash-safe
**Cons:** Many small files, requires merge step

## Recommended Approach

Option A with GeoPackage format is cleanest:

- GeoPackage supports append mode natively
- Single file per region (no merge needed)
- `--skip-existing` is intuitive
- Minimal architecture change

## CLI Interface

```bash
# Skip outlets that already exist in output
delineator run config.toml --skip-existing

# Force re-process even if exists
delineator run config.toml --overwrite
```

## Affected Files

- `src/delineator/cli/main.py` - Add flag, implement skip logic
- `src/delineator/core/output_writer.py` - Support append mode, add method to read existing gauge_ids
- Possibly migrate from Shapefile to GeoPackage format

## Considerations

1. **gauge_id uniqueness**: Already enforced per-region in config validation
2. **Changed geometries**: `--skip-existing` won't update outlets that were previously delineated with different parameters
3. **FAILED.csv**: Should skip logic also check FAILED.csv to avoid re-attempting known failures? (Probably not by default, but could add `--skip-failed` flag)

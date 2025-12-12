# Bug: No Output Written During Large Batch Delineation Run

## Summary

Running a large batch delineation (23k+ outlets across 9 regions) produces no output files despite successfully completing 11,000+ delineations. All results are held in RAM with nothing written to disk.

## Environment

- **Run directory**: `/Users/nicolaslazaro/Desktop/caravan-basin-extraction`
- **Config**: `delineate.toml` with 9 regions, 23,167 total outlets
- **Log file**: `delineation.log` (230MB, DEBUG level)

## Observed Behavior

1. CLI starts and processes regions sequentially (log shows `[1/9] Processing region: camels` through `[8/9] Processing region: hysets`)
2. Delineations succeed - log contains 11,093 entries of `Final delineated area: X km²`
3. **No output directory created** at `./output`
4. **No shapefiles written anywhere**
5. **No region completion messages** in log (e.g., "X succeeded, Y failed")

## Expected Behavior

Per `main.py:384-389`, after each region completes:
1. `writer.write_region_shapefile()` should be called
2. Output directory should be created
3. Shapefile should be written to `./output/REGION_NAME={name}/data_type=shapefiles/{name}_shapes.shp`
4. Console should print success count and shapefile path

## Data Points

| Region | Outlets | Cumulative | Status |
|--------|---------|------------|--------|
| camels | 667 | 667 | Should be complete |
| camelsaus | 437 | 1,104 | Should be complete |
| camelsbr | 819 | 1,923 | Should be complete |
| camelscl | 475 | 2,398 | Should be complete |
| camelsde | 1,887 | 4,285 | Should be complete |
| camelsgb | 671 | 4,956 | Should be complete |
| grdc | 5,321 | 10,277 | Should be complete |
| hysets | 12,031 | 22,308 | ~800 in progress |
| lamah | 859 | 23,167 | Not started |

With 11,093 successful delineations, regions 1-7 (10,277 outlets) should have completed and written shapefiles. They haven't.

## Log Evidence

```bash
# Region progression shows 8 regions started
$ grep "Processing region" delineation.log
[1/9] Processing region: camels
[2/9] Processing region: camelsaus
[3/9] Processing region: camelsbr
[4/9] Processing region: camelscl
[5/9] Processing region: camelsde
[6/9] Processing region: camelsgb
[7/9] Processing region: grdc
[8/9] Processing region: hysets

# Successful delineations confirmed
$ grep -c "Final delineated area" delineation.log
11093

# No completion/write messages (these go to console.print, not logger)
$ grep -E "completed|Wrote|succeeded.*failed" delineation.log
# (no results)

# No output directory
$ ls ./output
ls: ./output: No such file or directory
```

## Potential Causes

1. **Silent write failure**: `write_region_shapefile()` may be failing without raising an exception
2. **Path resolution issue**: Output path may be resolving to unexpected location
3. **Working directory mismatch**: CLI may be using different CWD than expected
4. **Region loop not completing**: Something preventing the loop from reaching the write step after outlet processing

## Investigation Suggestions

1. Add explicit logging before/after `writer.write_region_shapefile()` call (main.py:386)
2. Check if `region_watersheds` list is populated when reaching line 384
3. Verify `OutputWriter.write_region_shapefile()` creates parent directories
4. Check for swallowed exceptions in the write path
5. Add logging of actual resolved output path

## Impact

- **Data loss risk**: 11k+ delineated watersheds exist only in RAM
- **No progress visibility**: User cannot see results until entire run completes
- **Crash recovery impossible**: If process dies, all work is lost

## Related Concern

Even if this specific bug is fixed, the architecture accumulates all results per-region in RAM before writing. For large regions like `hysets` (12k outlets), this means:
- High memory pressure
- No intermediate results visible
- All-or-nothing data persistence per region

Consider incremental/streaming writes as a follow-up enhancement.

## Reproduction

```bash
cd /Users/nicolaslazaro/Desktop/caravan-basin-extraction
uv run delineator run delineate.toml --verbose 2>&1 | tee delineation.log
# Wait for several regions to "complete"
# Check: ls ./output (should exist but doesn't)
```

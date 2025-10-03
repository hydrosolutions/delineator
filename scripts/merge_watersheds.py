"""
Merge individual watershed files into a single shapefile with all geometries.

After running delineate.py, this script combines all individual watershed outputs
into one multi-feature shapefile where each feature retains its gauge_id.

Usage:
    uv run python scripts/merge_watersheds.py

Input:  output/kazakhstan/*.gpkg (or *.shp)
Output: output/kazakhstan_watersheds_merged.shp (or .gpkg)
"""
import geopandas as gpd
import pandas as pd
from pathlib import Path
import sys

# Configuration
INPUT_DIR = Path("output/kazakhstan")
OUTPUT_FILE = Path("output/kazakhstan_watersheds_merged.gpkg")
INPUT_EXT = "gpkg"  # or "shp" - must match OUTPUT_EXT in config.py

def main():
    print("="*70)
    print("MERGING INDIVIDUAL WATERSHEDS INTO SINGLE FILE")
    print("="*70)

    # Check if input directory exists
    if not INPUT_DIR.exists():
        print(f"❌ ERROR: Input directory not found: {INPUT_DIR}")
        print("   Run delineate.py first to generate watershed files.")
        sys.exit(1)

    # Find all watershed files
    watershed_files = list(INPUT_DIR.glob(f"*.{INPUT_EXT}"))

    if len(watershed_files) == 0:
        print(f"❌ ERROR: No .{INPUT_EXT} files found in {INPUT_DIR}")
        print(f"   Make sure OUTPUT_EXT in config.py is set to '{INPUT_EXT}'")
        sys.exit(1)

    print(f"\nFound {len(watershed_files)} watershed files in {INPUT_DIR}")

    # Load and merge all watersheds
    watersheds = []
    successful = 0
    failed = []

    print("\nLoading watersheds...")
    for i, filepath in enumerate(watershed_files, 1):
        gauge_id = filepath.stem  # Filename without extension

        try:
            gdf = gpd.read_file(filepath)

            # Add gauge_id as attribute if not present
            if 'gauge_id' not in gdf.columns:
                gdf['gauge_id'] = gauge_id

            watersheds.append(gdf)
            successful += 1

            if i % 50 == 0:
                print(f"  Loaded {i}/{len(watershed_files)}...")

        except Exception as e:
            failed.append((gauge_id, str(e)))
            print(f"  ⚠️  Failed to load {gauge_id}: {e}")

    print(f"  Loaded {successful}/{len(watershed_files)} watersheds")

    if failed:
        print(f"\n⚠️  WARNING: {len(failed)} watersheds failed to load:")
        for gauge_id, error in failed[:10]:
            print(f"    - {gauge_id}: {error}")
        if len(failed) > 10:
            print(f"    ... and {len(failed) - 10} more")

    if len(watersheds) == 0:
        print("❌ ERROR: No watersheds loaded successfully")
        sys.exit(1)

    # Combine all watersheds into single GeoDataFrame
    print(f"\nMerging {len(watersheds)} watersheds...")
    merged_gdf = pd.concat(watersheds, ignore_index=True)

    # Ensure gauge_id is first column (for convenience)
    cols = merged_gdf.columns.tolist()
    if 'gauge_id' in cols:
        cols.remove('gauge_id')
        cols = ['gauge_id'] + cols
        merged_gdf = merged_gdf[cols]

    print(f"  Total features: {len(merged_gdf)}")
    print(f"  CRS: {merged_gdf.crs}")

    # Calculate some statistics
    if 'area' in merged_gdf.columns or hasattr(merged_gdf.geometry.iloc[0], 'area'):
        # Calculate area in km² (assuming projected or WGS84)
        areas_km2 = merged_gdf.geometry.to_crs('EPSG:6933').area / 1e6  # Equal Earth projection
        print(f"\n  Watershed area statistics (km²):")
        print(f"    Min:    {areas_km2.min():,.1f}")
        print(f"    Max:    {areas_km2.max():,.1f}")
        print(f"    Mean:   {areas_km2.mean():,.1f}")
        print(f"    Median: {areas_km2.median():,.1f}")

    # Save merged file
    print(f"\nSaving merged watersheds to: {OUTPUT_FILE}")
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    merged_gdf.to_file(OUTPUT_FILE, driver='GPKG' if OUTPUT_FILE.suffix == '.gpkg' else None)

    file_size_mb = OUTPUT_FILE.stat().st_size / (1024 * 1024)
    print(f"  File size: {file_size_mb:.1f} MB")

    print("\n" + "="*70)
    print("✅ MERGE COMPLETE!")
    print("="*70)
    print(f"\nOutput: {OUTPUT_FILE}")
    print(f"  {len(merged_gdf)} watershed polygons")
    print(f"  Each with gauge_id attribute")

    if failed:
        print(f"\n⚠️  Note: {len(failed)} watersheds failed and were excluded")
        failed_csv = INPUT_DIR / "failed_to_merge.csv"
        pd.DataFrame(failed, columns=['gauge_id', 'error']).to_csv(failed_csv, index=False)
        print(f"  See {failed_csv} for details")

if __name__ == "__main__":
    main()

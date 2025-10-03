"""
Verify that all gauge points fall within the Pfafstetter basins we have data for
"""
import geopandas as gpd
import pandas as pd
from pathlib import Path

# Load gauge points CSV
GAUGE_CSV = "data/gauge_data/kazakhstan/kazakhstan_gauge_outlets.csv"
BASINS_SHP = "data/shp/basins_level2/merit_hydro_vect_level2.shp"

# Basins we have data for
AVAILABLE_BASINS = [26, 27, 28, 31, 46]

def main():
    # Read gauge points
    print(f"Reading gauge points: {GAUGE_CSV}")
    gauges_df = pd.read_csv(GAUGE_CSV)
    print(f"  Found {len(gauges_df)} gauge points")

    # Convert to GeoDataFrame
    gauges_gdf = gpd.GeoDataFrame(
        gauges_df,
        geometry=gpd.points_from_xy(gauges_df.lng, gauges_df.lat),
        crs="EPSG:4326"
    )

    # Read Pfafstetter level 2 basins
    print(f"\nReading basin boundaries: {BASINS_SHP}")
    basins_gdf = gpd.read_file(BASINS_SHP)
    print(f"  Found {len(basins_gdf)} basins")

    # Ensure same CRS
    if basins_gdf.crs != gauges_gdf.crs:
        basins_gdf = basins_gdf.to_crs(gauges_gdf.crs)

    # Spatial join to find which basin each gauge falls in
    print("\nPerforming spatial join...")
    joined = gpd.sjoin(gauges_gdf, basins_gdf, how="left", predicate="within")

    # Count gauges per basin
    basin_counts = joined.groupby('BASIN').size().sort_index()

    print("\n" + "="*60)
    print("BASIN COVERAGE SUMMARY")
    print("="*60)

    for basin_id, count in basin_counts.items():
        if pd.isna(basin_id):
            print(f"  Basin UNKNOWN: {count} gauges (not within any basin)")
        else:
            basin_id = int(basin_id)
            status = "✓ HAVE DATA" if basin_id in AVAILABLE_BASINS else "✗ NEED DATA"
            print(f"  Basin {basin_id:2d}: {count:3d} gauges  {status}")

    # Check for gauges outside any basin
    outside = joined[joined['BASIN'].isna()]
    if len(outside) > 0:
        print(f"\n⚠️  WARNING: {len(outside)} gauges fall outside basin boundaries:")
        print(outside[['id', 'lat', 'lng', 'name']].head(10))

    # Check for missing basin data
    needed_basins = set(basin_counts.dropna().index.astype(int)) - set(AVAILABLE_BASINS)

    if needed_basins:
        print(f"\n❌ MISSING DATA FOR BASINS: {sorted(needed_basins)}")
        print(f"   Download data for these basins before running delineator.py")
        return False
    else:
        print(f"\n✅ ALL GAUGES COVERED! All points fall within basins: {AVAILABLE_BASINS}")
        return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)

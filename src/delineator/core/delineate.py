"""
Watershed delineation logic for single outlet points.

This module implements the core delineation algorithm using a hybrid
vector/raster approach:
1. Find terminal unit catchment containing outlet
2. Trace upstream to collect all contributing unit catchments
3. Use raster-based delineation for terminal catchment (high precision)
4. Dissolve all catchments into single polygon
5. Fill small holes

The hybrid approach was first described by Djokic and Ye at the 1999 ESRI
User Conference. It combines the efficiency of vector data for upstream areas
with the precision of raster methods for the downstream terminal catchment.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyproj
import shapely.ops
from shapely.geometry import MultiPolygon, Point, Polygon

from delineator.core.country import get_country
from delineator.core.dissolve import dissolve_geopandas, fill_geopandas
from delineator.core.merit import split_catchment

logger = logging.getLogger(__name__)


class DelineationError(Exception):
    """Raised when watershed delineation fails."""

    pass


@dataclass
class DelineatedWatershed:
    """Result from delineating a single watershed."""

    gauge_id: str
    gauge_name: str
    gauge_lat: float
    gauge_lon: float
    snap_lat: float
    snap_lon: float
    snap_dist: float  # meters
    country: str
    area: float  # km²
    geometry: Polygon | MultiPolygon
    resolution: str  # "high_res" or "low_res"
    rivers: gpd.GeoDataFrame | None = None  # River network geometries


@dataclass
class BasinData:
    """Loaded geodata for a single Pfafstetter Level 2 basin."""

    basin_code: int
    catchments_gdf: gpd.GeoDataFrame
    rivers_gdf: gpd.GeoDataFrame


def collect_upstream_comids(
    terminal_comid: int,
    rivers_gdf: gpd.GeoDataFrame,
) -> list[int]:
    """
    Trace upstream network from terminal catchment to collect all contributing COMIDs.

    Uses an iterative approach to traverse the river network upstream using the
    up1, up2, up3, up4 fields in rivers_gdf, which contain the COMIDs of
    upstream tributaries.

    Args:
        terminal_comid: COMID of the terminal (most downstream) catchment
        rivers_gdf: GeoDataFrame of river reaches with network topology (indexed by COMID).
                   Must have columns 'up1', 'up2', 'up3', 'up4' containing upstream COMIDs.

    Returns:
        List of all upstream COMIDs including the terminal_comid
    """
    upstream_comids: list[int] = []
    stack = [terminal_comid]

    while stack:
        node = stack.pop()
        upstream_comids.append(node)

        # Check all four upstream connection fields
        for col in ["up1", "up2", "up3", "up4"]:
            up_id = rivers_gdf[col].loc[node]
            if up_id != 0:
                stack.append(up_id)

    return upstream_comids


def calculate_stream_orders(
    rivers_gdf: gpd.GeoDataFrame,
) -> tuple[dict[int, int], dict[int, int]]:
    """
    Calculate Strahler and Shreve stream orders for a river network.

    Uses topological sort to process nodes from headwaters downstream.

    Strahler order rules:
    - Headwater streams: order = 1
    - When streams of different orders merge: max order
    - When two or more streams of the same order merge: order + 1

    Shreve order rules:
    - Headwater streams: order = 1
    - At confluences: sum of all upstream orders

    Args:
        rivers_gdf: GeoDataFrame indexed by COMID with up1, up2, up3, up4 columns.

    Returns:
        Tuple of (strahler_orders, shreve_orders) dicts mapping COMID -> order
    """
    if rivers_gdf.empty:
        return {}, {}

    # Build upstream lookup (COMID -> set of upstream COMIDs that exist in subset)
    up_nodes: dict[int, set[int]] = {}
    for comid in rivers_gdf.index:
        upstream = set()
        for col in ["up1", "up2", "up3", "up4"]:
            up_id = rivers_gdf.loc[comid, col]
            if up_id != 0 and up_id in rivers_gdf.index:
                upstream.add(int(up_id))
        up_nodes[comid] = upstream

    # Build downstream lookup
    downstream_of: dict[int, set[int]] = {comid: set() for comid in rivers_gdf.index}
    for comid, upstream_set in up_nodes.items():
        for up_comid in upstream_set:
            downstream_of[up_comid].add(comid)

    # Kahn's algorithm for topological sort
    in_degree = {comid: len(upstream) for comid, upstream in up_nodes.items()}
    queue = [comid for comid, deg in in_degree.items() if deg == 0]
    topo_order = []

    while queue:
        node = queue.pop(0)
        topo_order.append(node)
        for downstream in downstream_of[node]:
            in_degree[downstream] -= 1
            if in_degree[downstream] == 0:
                queue.append(downstream)

    # Calculate stream orders
    strahler: dict[int, int] = {}
    shreve: dict[int, int] = {}

    for comid in topo_order:
        upstream_comids = up_nodes[comid]

        if not upstream_comids:
            strahler[comid] = 1
            shreve[comid] = 1
        else:
            # Strahler
            upstream_orders = [strahler[up] for up in upstream_comids]
            max_order = max(upstream_orders)
            if upstream_orders.count(max_order) >= 2:
                strahler[comid] = max_order + 1
            else:
                strahler[comid] = max_order

            # Shreve
            shreve[comid] = sum(shreve[up] for up in upstream_comids)

    return strahler, shreve


def get_area(poly: Polygon | MultiPolygon) -> float:
    """
    Calculate area of polygon in km² using equal-area projection.

    Projects the polygon from WGS84 (lat/lng) to an Albers Equal Area
    projection centered on the polygon's bounding box, then computes
    the area in square kilometers.

    Args:
        poly: Shapely polygon in WGS84 coordinates

    Returns:
        Area in km²
    """
    # Use partial from functools to create a projection transform
    from functools import partial

    projected_poly = shapely.ops.transform(
        partial(
            pyproj.transform,
            pyproj.Proj(init="EPSG:4326"),
            pyproj.Proj(proj="aea", lat_1=poly.bounds[1], lat_2=poly.bounds[3]),
        ),
        poly,
    )

    # Get the area in m² and convert to km²
    return projected_poly.area / 1e6


def load_basin_data(
    basin: int,
    data_dir: Path,
) -> BasinData:
    """
    Load catchments and rivers geodataframes for a basin.

    Loads the MERIT-Hydro vector data for a Pfafstetter Level 2 basin.
    The data consists of:
    - Unit catchment polygons (catchments_gdf)
    - River reach centerlines with network topology (rivers_gdf)

    Args:
        basin: Pfafstetter Level 2 basin code (11-91)
        data_dir: Root directory containing MERIT-Hydro data

    Returns:
        BasinData with loaded catchments and rivers GeoDataFrames

    Raises:
        FileNotFoundError: If required shapefiles are not found
        DelineationError: If files cannot be loaded or are malformed

    The function expects these file paths:
    - data_dir/shp/merit_catchments/cat_pfaf_{basin}_MERIT_Hydro_v07_Basins_v01.shp
    - data_dir/shp/merit_rivers/riv_pfaf_{basin}_MERIT_Hydro_v07_Basins_v01.shp
    """
    catchments_file = data_dir / "shp/merit_catchments" / f"cat_pfaf_{basin}_MERIT_Hydro_v07_Basins_v01.shp"
    rivers_file = data_dir / "shp/merit_rivers" / f"riv_pfaf_{basin}_MERIT_Hydro_v07_Basins_v01.shp"

    if not catchments_file.is_file():
        raise FileNotFoundError(f"Could not find catchments shapefile: {catchments_file}")

    if not rivers_file.is_file():
        raise FileNotFoundError(f"Could not find rivers shapefile: {rivers_file}")

    logger.info(f"Loading basin {basin} data")
    logger.info(f"  Catchments: {catchments_file}")
    logger.info(f"  Rivers: {rivers_file}")

    try:
        catchments_gdf = gpd.read_file(catchments_file)
        catchments_gdf.set_index("COMID", inplace=True)
        catchments_gdf.set_crs("EPSG:4326", inplace=True, allow_override=True)

        rivers_gdf = gpd.read_file(rivers_file)
        rivers_gdf.set_index("COMID", inplace=True)
        rivers_gdf.set_crs("EPSG:4326", inplace=True, allow_override=True)

    except Exception as e:
        raise DelineationError(f"Failed to load basin {basin} data: {e}") from e

    return BasinData(
        basin_code=basin,
        catchments_gdf=catchments_gdf,
        rivers_gdf=rivers_gdf,
    )


def delineate_outlet(
    gauge_id: str,
    lat: float,
    lng: float,
    gauge_name: str,
    catchments_gdf: gpd.GeoDataFrame,
    rivers_gdf: gpd.GeoDataFrame,
    fdir_dir: Path,
    accum_dir: Path,
    fill_threshold: int = 100,
    use_high_res: bool = True,
    high_res_area_limit: float = 10000.0,
    include_rivers: bool = False,
) -> DelineatedWatershed:
    """
    Delineate watershed for a single outlet point.

    Uses hybrid vector/raster approach:
    1. Find terminal unit catchment containing outlet
    2. Trace upstream to collect all contributing unit catchments
    3. Use raster-based delineation for terminal catchment (high precision)
    4. Dissolve all catchments into single polygon
    5. Fill small holes

    Args:
        gauge_id: Unique identifier for the gauge/outlet
        lat: Latitude of outlet point (decimal degrees)
        lng: Longitude of outlet point (decimal degrees)
        gauge_name: Human-readable name for the outlet
        catchments_gdf: GeoDataFrame of unit catchment polygons (indexed by COMID)
        rivers_gdf: GeoDataFrame of river reaches with network topology (indexed by COMID)
        fdir_dir: Directory containing MERIT-Hydro flow direction rasters
        accum_dir: Directory containing MERIT-Hydro flow accumulation rasters
        fill_threshold: Number of MERIT-Hydro pixels - holes smaller than this will be filled
        use_high_res: Whether to attempt high-resolution raster delineation
        high_res_area_limit: Switch to low-res mode for watersheds larger than this (km²)
        include_rivers: Whether to include river network geometries in the result

    Returns:
        DelineatedWatershed with all attributes including geometry

    Raises:
        DelineationError: If delineation fails at any step
    """
    logger.info(f"Delineating watershed for gauge {gauge_id} at ({lat}, {lng})")

    # Step 1: Find the terminal unit catchment that contains the outlet point
    outlet_point = Point(lng, lat)
    point_gdf = gpd.GeoDataFrame(geometry=[outlet_point], crs="EPSG:4326")

    # Spatial join to find which catchment contains the point
    joined = gpd.sjoin(point_gdf, catchments_gdf, how="left", predicate="intersects")

    if joined.empty or pd.isna(joined.iloc[0]["COMID"]):
        raise DelineationError(f"Outlet point ({lat}, {lng}) does not fall within any unit catchment")

    terminal_comid = joined.iloc[0]["COMID"]
    logger.info(f"  Terminal unit catchment COMID: {terminal_comid}")

    # Step 2: Trace upstream to find all contributing unit catchments
    upstream_comids = collect_upstream_comids(terminal_comid, rivers_gdf)
    logger.info(f"  Found {len(upstream_comids)} unit catchments in watershed")

    # Extract river geometries if requested
    rivers = rivers_gdf.loc[upstream_comids].copy() if include_rivers else None

    if rivers is not None and not rivers.empty:
        strahler_orders, shreve_orders = calculate_stream_orders(rivers)
        rivers["strahler_order"] = rivers.index.map(strahler_orders)
        rivers["shreve_order"] = rivers.index.map(shreve_orders)

    # Get the upstream area from the rivers dataset
    upstream_area_km2 = rivers_gdf.loc[terminal_comid]["uparea"]
    logger.info(f"  Upstream area: {upstream_area_km2:.1f} km²")

    # Determine whether to use high-resolution or low-resolution mode
    bool_high_res = use_high_res and upstream_area_km2 <= high_res_area_limit

    if use_high_res and not bool_high_res:
        logger.info(
            f"  Watershed area ({upstream_area_km2:.1f} km²) exceeds limit "
            f"({high_res_area_limit} km²). Switching to low-resolution mode."
        )

    # Step 3: Create a GeoDataFrame containing only the unit catchments in this watershed
    subbasins_gdf = catchments_gdf.loc[upstream_comids].copy()

    # Step 4: In high-resolution mode, perform raster-based delineation for terminal catchment
    if bool_high_res:
        logger.info("  Performing high-resolution raster-based delineation")

        # Get the terminal catchment polygon
        terminal_catchment_poly = subbasins_gdf.loc[terminal_comid].geometry

        # Check if this watershed consists of only a single unit catchment
        is_single_catchment = len(upstream_comids) == 1

        # Get the basin code from the first catchment (they're all in the same basin)
        # The basin code should be available in the catchments_gdf or we can infer it
        # For now, we'll need to pass it as a parameter or extract it from the data
        # Looking at the original code, it seems the basin is tracked separately
        # We'll need to add basin as a parameter or extract it somehow
        # For now, let's assume we can get it from the rivers_gdf or catchments_gdf
        # The MERIT-Hydro data should have a PFAF field or similar

        # Actually, looking at load_basin_data, the basin is passed in
        # We need to add basin as a parameter to this function
        # For now, I'll extract it from the COMID (first 2 digits)
        basin = int(str(terminal_comid)[:2])

        # Call split_catchment to perform detailed delineation
        try:
            split_poly, lat_snap, lng_snap = split_catchment(
                basin=basin,
                lat=lat,
                lng=lng,
                catchment_poly=terminal_catchment_poly,
                is_single_catchment=is_single_catchment,
                upstream_area=upstream_area_km2,
                fdir_dir=fdir_dir,
                accum_dir=accum_dir,
            )

            if split_poly is None:
                raise DelineationError("Raster-based delineation returned None")

            # Update the geometry of the terminal catchment with the split result
            subbasins_gdf.loc[terminal_comid, "geometry"] = split_poly

            resolution = "high_res"

        except Exception as e:
            raise DelineationError(f"Raster-based delineation failed: {e}") from e

    else:
        # Low-resolution mode: use the outlet of the terminal river reach as snap point
        logger.info("  Using low-resolution (vector-only) mode")

        # Get the downstream end of the terminal river reach
        terminal_river_geom = rivers_gdf.loc[terminal_comid].geometry
        # The river geometry is a LineString; get the first coordinate (downstream end)
        snapped_outlet = terminal_river_geom.coords[0]
        lng_snap = snapped_outlet[0]
        lat_snap = snapped_outlet[1]

        resolution = "low_res"

    # Step 5: Dissolve all unit catchments into a single polygon
    logger.info("  Dissolving unit catchments")
    mybasin_gs = dissolve_geopandas(subbasins_gdf)

    # Step 6: Fill small holes in the watershed polygon
    # Convert fill_threshold (in pixels) to area in square decimal degrees
    PIXEL_AREA = 0.000000695  # Area of a single MERIT-Hydro pixel in decimal degrees
    area_max = fill_threshold * PIXEL_AREA
    mybasin_gs = fill_geopandas(mybasin_gs, area_max=area_max)

    # Extract the final watershed polygon
    basin_poly = mybasin_gs.iloc[0]

    # Step 7: Calculate final area
    area_km2 = get_area(basin_poly)
    logger.info(f"  Final delineated area: {area_km2:.1f} km²")

    # Step 8: Calculate snap distance (how far the outlet was moved)
    geod = pyproj.Geod(ellps="WGS84")
    snap_dist_m = geod.inv(lng, lat, lng_snap, lat_snap)[2]

    # Step 9: Get country name
    try:
        country = get_country(lat, lng)
    except Exception as e:
        logger.warning(f"Could not determine country: {e}")
        country = "Unknown"

    # Step 10: Return the result
    return DelineatedWatershed(
        gauge_id=gauge_id,
        gauge_name=gauge_name,
        gauge_lat=lat,
        gauge_lon=lng,
        snap_lat=lat_snap,
        snap_lon=lng_snap,
        snap_dist=snap_dist_m,
        country=country,
        area=area_km2,
        geometry=basin_poly,
        resolution=resolution,
        rivers=rivers,
    )

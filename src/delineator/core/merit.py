"""
MERIT-Hydro raster operations for detailed watershed delineation.

Provides functions for loading MERIT flow direction and accumulation
rasters and performing pixel-scale delineation using pysheds.

This module implements a hybrid delineation method that uses raster-based
delineation only within a single unit catchment (the most downstream one),
while using vector data for upstream areas. This approach significantly
reduces memory usage and processing time.
"""

import logging
from pathlib import Path

import numpy as np
from numpy import ceil, floor
from pysheds.grid import Grid
from shapely import ops, wkb
from shapely.geometry import MultiPolygon, Polygon

logger = logging.getLogger(__name__)


def compute_snap_threshold(
    upstream_area: float | None,
    is_single_catchment: bool,
    threshold_single: int = 500,
    threshold_multiple: int = 5000,
) -> int:
    """
    Compute the pixel threshold for stream snapping based on watershed size.

    The threshold determines the minimum number of upstream pixels required
    to define a waterway. Smaller watersheds need lower thresholds to find
    streams, while larger watersheds can use higher thresholds.

    Args:
        upstream_area: Upstream drainage area in km² (if available).
            If None, falls back to is_single_catchment logic.
        is_single_catchment: Whether the watershed consists of a single unit catchment.
            Used as fallback when upstream_area is None.
        threshold_single: Threshold to use for single-catchment watersheds (default 500).
        threshold_multiple: Threshold to use for multi-catchment watersheds (default 5000).

    Returns:
        Number of pixels to use as the stream snapping threshold.
    """
    if upstream_area is not None:
        # Dynamic threshold based on watershed area (km²)
        # Small watersheds need lower thresholds to find the stream
        if upstream_area < 50:
            return 300  # Very small catchments
        elif upstream_area < 200:
            return 500  # Small catchments
        elif upstream_area < 1000:
            return 1000  # Medium catchments
        elif upstream_area < 5000:
            return 2000  # Large catchments
        else:
            return 5000  # Very large catchments
    else:
        # Fallback to fixed thresholds based on number of unit catchments
        return threshold_single if is_single_catchment else threshold_multiple


def split_catchment(
    basin: int,
    lat: float,
    lng: float,
    catchment_poly: Polygon,
    is_single_catchment: bool,
    upstream_area: float | None,
    fdir_dir: Path,
    accum_dir: Path,
) -> tuple[Polygon | None, float | None, float | None]:
    """
    Perform detailed pixel-scale raster-based delineation for a watershed.

    To efficiently delineate large watersheds, we only use raster-based methods in a small area,
    the size of a single unit catchment that is most downstream. This results in big
    savings in processing time and memory use, making it possible to delineate even large watersheds
    on a laptop computer.

    This is an implementation of the hybrid method first described by Djokic and Ye
    at the 1999 ESRI User Conference.

    Args:
        basin: 2-digit Pfafstetter code for the level 2 basin (tells us what files to open)
        lat: Latitude of the outlet point
        lng: Longitude of the outlet point
        catchment_poly: A Shapely polygon for the terminal unit catchment; used to clip
            the flow accumulation raster for accurate snapping
        is_single_catchment: Is the watershed small (only one unit catchment)?
            If so, we'll use a lower snap threshold for the outlet.
        upstream_area: Upstream drainage area in km² (if available). Used to dynamically
            set the snap threshold. If None, falls back to is_single_catchment logic.
        fdir_dir: Directory containing MERIT-Hydro flow direction rasters
        accum_dir: Directory containing MERIT-Hydro flow accumulation rasters

    Returns:
        tuple containing:
            - poly: A Shapely polygon representing the part of the terminal unit catchment
                   that is upstream of the outlet point, or None if delineation failed
            - lat_snap: Latitude of the outlet snapped to the river centerline, or None if failed
            - lng_snap: Longitude of the outlet snapped to the river centerline, or None if failed

    The function performs the following steps:
    1. Loads a windowed portion of the flow direction raster covering the catchment
    2. Masks the raster to the catchment polygon to prevent snapping to neighboring watersheds
    3. Loads the accumulation raster and masks it similarly
    4. Snaps the outlet point to the nearest stream using a dynamic threshold
    5. Performs raster-based catchment delineation using pysheds
    6. Converts the resulting raster catchment to a polygon
    """
    # Get a bounding box for the unit catchment
    bounds = catchment_poly.bounds
    bounds_list = [float(i) for i in bounds]

    # The coordinates of the bounding box edges that we get from the above query
    # do not correspond well with the edges of the grid pixels.
    # We need to round them to the nearest whole pixel and then
    # adjust them by a half-pixel width to get good results in pysheds.

    # Distance of a half-pixel (3 arcsecond resolution = 1/1200 degree)
    halfpix = 0.000416667

    # Bounding box is xmin, ymin, xmax, ymax
    # Round the elements DOWN, DOWN, UP, UP
    # The number 1200 is because the MERIT-Hydro rasters have 3 arcsecond resolution (1/1200 of a decimal degree)
    # We multiply by 1200, round up or down to the nearest whole number, then divide by 1200
    # to put it back in regular units of decimal degrees. Then, since pysheds wants the *center*
    # of the pixel, not its edge, add or subtract a half-pixel width as appropriate.
    bounds_list[0] = floor(bounds_list[0] * 1200) / 1200 - halfpix
    bounds_list[1] = floor(bounds_list[1] * 1200) / 1200 - halfpix
    bounds_list[2] = ceil(bounds_list[2] * 1200) / 1200 + halfpix
    bounds_list[3] = ceil(bounds_list[3] * 1200) / 1200 + halfpix

    # The bounding box needs to be a tuple for pysheds
    bounding_box = tuple(bounds_list)

    # Open the flow direction raster using windowed reading mode
    fdir_fname = fdir_dir / f"flowdir{basin}.tif"
    logger.info(f"Loading flow direction raster from: {fdir_fname}")
    logger.info(f"Using windowed reading mode with bounding_box = {bounding_box!r}")

    if not fdir_fname.is_file():
        raise FileNotFoundError(f"Could not find flow direction raster: {fdir_fname}")

    # Load the grid and flow direction data
    grid = Grid.from_raster(str(fdir_fname), window=bounding_box, nodata=0)
    fdir = grid.read_raster(str(fdir_fname), window=bounding_box, nodata=0)

    # Now "clip" the rectangular flow direction grid even further so that it ONLY contains data
    # inside the boundaries of the terminal unit catchment.
    # This prevents us from accidentally snapping the pour point to a neighboring watershed.
    # This was especially a problem around confluences, but this step fixes it.
    hexpoly = catchment_poly.wkb_hex
    poly = wkb.loads(hexpoly, hex=True)

    # Coerce this into a single-part polygon, in case the geometry is a MultiPolygon
    poly = _get_largest(poly)

    # Fix any holes in the polygon by taking the exterior coordinates.
    # One of the annoyances of working with GeoPandas and pysheds is that you have
    # to constantly switch back and forth between Polygons and MultiPolygons...
    filled_poly = Polygon(poly.exterior.coords)

    # It needs to be of type MultiPolygon to work with rasterio apparently
    multi_poly = MultiPolygon([filled_poly])
    polygon_list = list(multi_poly.geoms)

    # Convert the polygon into a pixelized raster "mask"
    mymask = grid.rasterize(polygon_list)

    # Zero out flow direction values outside the mask
    # This makes the plots look nicer and ensures we only consider pixels inside the catchment
    m, n = grid.shape
    for i in range(m):
        for j in range(n):
            if int(mymask[i, j]) == 0:
                fdir[i, j] = 0

    # MERIT-Hydro flow direction uses the old ESRI standard for flow direction
    dirmap = (64, 128, 1, 2, 4, 8, 16, 32)

    logger.info("Snapping pour point")

    # Open the accumulation raster, again using windowed reading mode
    accum_fname = accum_dir / f"accum{basin}.tif"
    if not accum_fname.is_file():
        raise FileNotFoundError(f"Could not find accumulation raster: {accum_fname}")

    acc = grid.read_raster(str(accum_fname), data_name="acc", window=bounding_box, window_crs=grid.crs, nodata=0)

    # Clip the flow direction grid to a new rectangular bounding box
    # that corresponds to the mask of the unit catchment
    grid.clip_to(mymask)

    # MASK the accumulation raster to the unit catchment POLYGON. Set any pixel that is not
    # in 'mymask' to zero. That way, the pour point will always snap to a grid cell that is
    # inside our polygon for the unit catchment, and will not accidentally snap
    # to a neighboring watershed. This is the key to getting good results in small watersheds,
    # especially when there are other streams nearby.
    m, n = grid.shape
    for i in range(m):
        for j in range(n):
            if int(mymask[i, j]) == 0:
                acc[i, j] = 0

    # Snap the outlet to the nearest stream. This function depends entirely on the threshold
    # for the minimum number of upstream pixels to define a waterway.
    # Use dynamic threshold based on watershed size (upstream area) if available,
    # otherwise fall back to the old logic based on number of unit catchments.
    numpixels = compute_snap_threshold(upstream_area, is_single_catchment)

    logger.info(f"Using threshold of {numpixels} for number of upstream pixels")

    # Snap the pour point to a point on the accumulation grid where accum (# of upstream pixels)
    # is greater than our threshold
    streams = acc > numpixels
    xy = (lng, lat)
    try:
        lng_snap, lat_snap = grid.snap_to_mask(streams, xy)
    except Exception as e:
        logger.error(f"Could not snap the pour point. Error: {e}")
        return None, None, None

    # Finally, here is the raster based watershed delineation with pysheds!
    logger.info("Delineating catchment")
    try:
        catch = grid.catchment(
            fdir=fdir, x=lng_snap, y=lat_snap, dirmap=dirmap, xytype="coordinate", recursionlimit=15000
        )

        # Clip the bounding box to the catchment
        # Seems optional, but turns out this line is essential
        grid.clip_to(catch)
        clipped_catch = grid.view(catch, dtype=np.uint8)
    except Exception as e:
        logger.error(f"ERROR: something went wrong during pysheds grid.catchment(). Error: {e}")
        return None, lng_snap, lat_snap

    # Convert high-precision raster subcatchment to a polygon using pysheds method .polygonize()
    logger.info("Converting to polygon")
    shapes = grid.polygonize(clipped_catch)

    # The output from pysheds can create MANY shapes.
    # Dissolve them together with the unary union operation in shapely
    # MERIT-Hydro flow-direction grids, while being a very nice dataset,
    # can produce polygons with dangles and donut holes.
    # The solution "discard all but the largest polygon" is not ideal from a
    # theoretical standpoint, because we could discard a piece of the drainage
    # area, but in testing, it usually only results in the loss of a few pixels
    # here and there, in other words, trivial differences. The tradeoff is
    # worthwhile -- we lose a bit of accuracy, but in exchange, we gain the simplicity
    # of working with Polygon geometries, rather than MultiPolygons.

    shapely_polygons = []
    shape_count = 0

    # The snapped vertices look better if we nudge them one half pixel
    lng_snap += halfpix
    lat_snap -= halfpix

    # Convert the result from pysheds into a list of shapely polygons
    for shape, _value in shapes:
        pysheds_polygon = shape
        shape_count += 1

        # The pysheds polygon can be converted to a shapely Polygon in this one-liner
        shapely_polygon = Polygon([[p[0], p[1]] for p in pysheds_polygon["coordinates"][0]])
        shapely_polygons.append(shapely_polygon)

    if shape_count > 1:
        # If pysheds returned multiple polygons, dissolve them using shapely's unary_union() function
        # Note that this can sometimes return a MultiPolygon, which we'll need to fix later
        result_polygon = ops.unary_union(shapely_polygons)

        if result_polygon.geom_type == "MultiPolygon":
            result_polygon = _get_largest(result_polygon)
    else:
        # If pysheds generated a single polygon, that is our answer
        result_polygon = shapely_polygons[0]

    return result_polygon, lat_snap, lng_snap


def _get_largest(input_poly: MultiPolygon | Polygon) -> Polygon:
    """
    Convert a Shapely MultiPolygon to a Shapely Polygon.

    For multipart polygons, will only keep the largest polygon
    in terms of area. In testing, this was usually good enough.

    Args:
        input_poly: A Shapely Polygon or MultiPolygon

    Returns:
        A shapely Polygon (the largest if input was MultiPolygon)
    """
    if input_poly.geom_type == "MultiPolygon":
        polygons = list(input_poly.geoms)
        areas = [poly.area for poly in polygons]
        max_index = areas.index(max(areas))
        return polygons[max_index]
    else:
        return input_poly

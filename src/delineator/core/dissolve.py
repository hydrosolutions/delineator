"""
Polygon dissolve operations for watershed boundary processing.

Provides efficient methods for dissolving multiple polygons into a single
boundary and for filling donut holes in polygon geometries.

The dissolve algorithm uses a clever optimization: instead of using the
standard (slow) GeoPandas dissolve operation, it creates a bounding box
around all polygons and clips it to the input layer. This is much faster
for layers with many polygons.
"""

import logging

import geopandas as gpd
from shapely.geometry import MultiPolygon, Polygon

logger = logging.getLogger(__name__)


def buffer(poly: Polygon) -> Polygon:
    """
    Remove slivers, dangles, and other geometric errors in a Shapely polygon.

    This is a little trick that works wonders: we do a series of
    2 buffers, out and then in, and it magically fixes many topology issues.

    Args:
        poly: Input Shapely polygon

    Returns:
        Buffered (and cleaned) polygon
    """
    dist = 0.00001
    return poly.buffer(dist, join_style=2).buffer(-dist, join_style=2)


def close_holes(poly: Polygon | MultiPolygon, area_max: float) -> Polygon | MultiPolygon:
    """
    Close polygon holes by removing interior rings below a size threshold.

    Args:
        poly: Input Shapely Polygon or MultiPolygon
        area_max: Keep holes that are larger than this value.
                  Fill any holes less than or equal to this.
                  We're working with unprojected lat/lng coordinates,
                  so this needs to be in square decimal degrees.
                  Set to 0 to fill ALL holes.

    Returns:
        Polygon or MultiPolygon with small holes filled

    Example:
        df.geometry.apply(lambda p: close_holes(p, area_max=0.001))
    """
    if isinstance(poly, Polygon):
        # Handle Polygon case
        if area_max == 0:
            if poly.interiors:
                return Polygon(list(poly.exterior.coords))
            else:
                return poly
        else:
            list_interiors = []

            for interior in poly.interiors:
                p = Polygon(interior)
                if p.area > area_max:
                    list_interiors.append(interior)

            return Polygon(poly.exterior.coords, holes=list_interiors)

    elif isinstance(poly, MultiPolygon):
        # Handle MultiPolygon case
        result_polygons = []
        for sub_poly in poly.geoms:
            new_sub_poly = close_holes(sub_poly, area_max)
            result_polygons.append(new_sub_poly)
        return MultiPolygon(result_polygons)
    else:
        raise ValueError(f"Unsupported geometry type: {type(poly)}")


def fill_geopandas(gdf: gpd.GeoDataFrame, area_max: float) -> gpd.GeoSeries:
    """
    Fill holes in all geometries in a GeoDataFrame.

    Args:
        gdf: GeoDataFrame containing polygons
        area_max: Maximum area threshold for holes to fill (square decimal degrees)

    Returns:
        GeoSeries with filled geometries
    """
    filled = gdf.geometry.apply(lambda p: close_holes(p, area_max))
    return filled


def dissolve_geopandas(df: gpd.GeoDataFrame) -> gpd.GeoSeries:
    """
    Dissolve multiple polygons into a single polygon.

    This method is much faster than using GeoPandas dissolve().

    It creates a box around the polygons, then clips the box to
    the polygon layer. The result is one feature instead of many.

    Args:
        df: GeoDataFrame with multiple polygons to merge and dissolve
               into a single polygon

    Returns:
        GeoSeries containing a single dissolved polygon

    Note:
        This approach works by:
        1. Getting the total bounds of all features
        2. Creating a slightly larger rectangular box
        3. Clipping the box to the input polygons
        4. Applying a small buffer operation to fix topology issues
    """
    left, bottom, right, top = df.total_bounds
    left -= 1
    right += 1
    top += 1
    bottom -= 1

    lat_point_list = [left, right, right, left, left]
    lon_point_list = [top, top, bottom, bottom, top]

    polygon_geom = Polygon(zip(lat_point_list, lon_point_list, strict=True))
    rect = gpd.GeoDataFrame(index=[0], crs=df.crs, geometry=[polygon_geom])
    clipped = gpd.clip(rect, df)

    # This removes some weird artifacts that result from MERIT-BASINS having lots
    # of little topology issues
    clipped = clipped.geometry.apply(lambda p: buffer(p))

    return clipped

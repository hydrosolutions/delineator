"""
Export service for converting watershed responses to various file formats.

This module provides functions to convert DelineateResponse objects into
different geospatial file formats (GeoJSON, Shapefile, GeoPackage) for
download and external use.
"""

import tempfile
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import geopandas as gpd
from shapely.geometry import shape

from delineator.api.models import DelineateResponse, ExportFormat


def response_to_geodataframe(response: DelineateResponse) -> gpd.GeoDataFrame:
    """
    Convert a DelineateResponse watershed to a GeoDataFrame.

    Args:
        response: The delineation response containing watershed geometry and properties

    Returns:
        GeoDataFrame with watershed geometry and attributes, CRS set to EPSG:4326
    """
    # Convert GeoJSON geometry dict to Shapely geometry
    geometry = shape(response.watershed.geometry)

    # Extract properties
    props = response.watershed.properties

    # Create GeoDataFrame with properties
    gdf = gpd.GeoDataFrame(
        {
            "gauge_id": [props.gauge_id],
            "area_km2": [props.area_km2],
            "snap_lat": [props.snap_lat],
            "snap_lng": [props.snap_lng],
            "snap_distance_m": [props.snap_distance_m],
            "resolution": [props.resolution],
        },
        geometry=[geometry],
        crs="EPSG:4326",
    )

    return gdf


def rivers_to_geodataframe(response: DelineateResponse) -> gpd.GeoDataFrame | None:
    """
    Convert rivers from a DelineateResponse to a GeoDataFrame.

    Args:
        response: The delineation response containing river features

    Returns:
        GeoDataFrame with river geometries and attributes, or None if no rivers.
        Attributes: comid, uparea, strahler_order, shreve_order
    """
    if response.rivers is None or not response.rivers.features:
        return None

    geometries = []
    data = []

    for feature in response.rivers.features:
        geometries.append(shape(feature.geometry))
        data.append(
            {
                "comid": feature.properties.comid,
                "uparea": feature.properties.uparea,
                "strahler_order": feature.properties.strahler_order,
                "shreve_order": feature.properties.shreve_order,
            }
        )

    return gpd.GeoDataFrame(data, geometry=geometries, crs="EPSG:4326")


def export_geojson(response: DelineateResponse) -> bytes:
    """
    Export watershed as GeoJSON format.

    If rivers are included in the response, they are combined with the watershed
    into a single FeatureCollection.

    Args:
        response: The delineation response to export

    Returns:
        UTF-8 encoded GeoJSON bytes
    """

    watershed_gdf = response_to_geodataframe(response)
    rivers_gdf = rivers_to_geodataframe(response)

    if rivers_gdf is not None:
        # Combine watershed and rivers into a single FeatureCollection
        import pandas as pd

        combined_gdf = gpd.GeoDataFrame(
            pd.concat([watershed_gdf, rivers_gdf], ignore_index=True),
            crs="EPSG:4326",
        )
        geojson_str = combined_gdf.to_json()
    else:
        geojson_str = watershed_gdf.to_json()

    return geojson_str.encode("utf-8")


def export_shapefile_zip(response: DelineateResponse, gauge_id: str) -> bytes:
    """
    Export watershed as a zipped Shapefile.

    Shapefile column names are limited to 10 characters, so snap_distance_m
    is renamed to snap_dist_m. If rivers are included, a separate rivers
    shapefile is added to the ZIP.

    Args:
        response: The delineation response to export
        gauge_id: Gauge identifier used for naming files

    Returns:
        ZIP archive containing watershed shapefile and optionally rivers shapefile
    """
    watershed_gdf = response_to_geodataframe(response)
    rivers_gdf = rivers_to_geodataframe(response)

    # Rename column to meet 10-character shapefile limit
    watershed_gdf = watershed_gdf.rename(columns={"snap_distance_m": "snap_dist_m"})

    # Create temporary directory for shapefile components
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        shp_path = tmpdir_path / f"{gauge_id}.shp"

        # Write watershed shapefile
        watershed_gdf.to_file(shp_path, driver="ESRI Shapefile")

        # Write rivers shapefile if present
        if rivers_gdf is not None:
            rivers_shp_path = tmpdir_path / f"{gauge_id}_rivers.shp"
            rivers_gdf.to_file(rivers_shp_path, driver="ESRI Shapefile")

        # Create ZIP archive in memory
        zip_buffer = BytesIO()
        with ZipFile(zip_buffer, "w") as zipf:
            # Add all shapefile components to ZIP
            for file in tmpdir_path.glob(f"{gauge_id}.*"):
                zipf.write(file, arcname=file.name)
            # Add rivers shapefile components if present
            if rivers_gdf is not None:
                for file in tmpdir_path.glob(f"{gauge_id}_rivers.*"):
                    zipf.write(file, arcname=file.name)

        return zip_buffer.getvalue()


def export_geopackage(response: DelineateResponse, gauge_id: str) -> bytes:
    """
    Export watershed as GeoPackage format.

    If rivers are included in the response, they are written as a separate
    'rivers' layer in the GeoPackage.

    Args:
        response: The delineation response to export
        gauge_id: Gauge identifier used for naming the file

    Returns:
        GeoPackage file bytes
    """
    watershed_gdf = response_to_geodataframe(response)
    rivers_gdf = rivers_to_geodataframe(response)

    # Create temporary file for GeoPackage
    with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as tmpfile:
        tmpfile_path = Path(tmpfile.name)

    try:
        # Write watershed layer
        watershed_gdf.to_file(tmpfile_path, driver="GPKG", layer="watershed")

        # Write rivers layer if present
        if rivers_gdf is not None:
            rivers_gdf.to_file(tmpfile_path, driver="GPKG", layer="rivers", mode="a")

        # Read bytes
        with open(tmpfile_path, "rb") as f:
            gpkg_bytes = f.read()

        return gpkg_bytes
    finally:
        # Clean up temporary file
        if tmpfile_path.exists():
            tmpfile_path.unlink()


def export_watershed(response: DelineateResponse, gauge_id: str, format: ExportFormat) -> tuple[bytes, str, str]:
    """
    Export watershed in the specified format.

    Dispatcher function that routes to the appropriate export function based
    on the requested format.

    Args:
        response: The delineation response to export
        gauge_id: Gauge identifier used for naming files
        format: The desired export format

    Returns:
        Tuple of (file_bytes, content_type, filename)
    """
    if format == ExportFormat.geojson:
        data = export_geojson(response)
        content_type = "application/geo+json"
        filename = f"{gauge_id}.geojson"
    elif format == ExportFormat.shapefile:
        data = export_shapefile_zip(response, gauge_id)
        content_type = "application/zip"
        filename = f"{gauge_id}.shp.zip"
    elif format == ExportFormat.geopackage:
        data = export_geopackage(response, gauge_id)
        content_type = "application/geopackage+sqlite3"
        filename = f"{gauge_id}.gpkg"
    else:
        raise ValueError(f"Unsupported export format: {format}")

    return data, content_type, filename

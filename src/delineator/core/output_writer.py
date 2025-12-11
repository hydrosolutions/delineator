"""
Output writer module for watershed delineation results.

Handles writing delineation results to Hive-partitioned directory structures,
including shapefiles for successful watersheds and CSV logging for failures.
"""

import csv
import logging
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd

# Import DelineatedWatershed from delineate module to avoid duplication
from delineator.core.delineate import DelineatedWatershed

logger = logging.getLogger(__name__)


@dataclass
class FailedOutlet:
    """
    Record of a failed delineation.

    Attributes:
        region_name: Name of the region/group this outlet belongs to
        gauge_id: Unique identifier for the outlet point
        lat: Latitude of the outlet point
        lng: Longitude of the outlet point
        error: Description of what went wrong
    """

    region_name: str
    gauge_id: str
    lat: float
    lng: float
    error: str


class OutputWriter:
    """
    Handles output file writing for delineation results.

    Creates Hive-partitioned directory structure for regional outputs and
    maintains a centralized FAILED.csv log for all failures.
    """

    def __init__(self, output_dir: Path):
        """
        Initialize writer with output directory.

        Args:
            output_dir: Base directory for all outputs
        """
        self.output_dir = Path(output_dir)
        self.failed_outlets: list[FailedOutlet] = []

    def get_region_output_dir(self, region_name: str) -> Path:
        """
        Get Hive-partitioned directory for a region.

        Creates directory structure: output_dir/REGION_NAME={region_name}/data_type=shapefiles/

        Args:
            region_name: Name of the region

        Returns:
            Path to the region's shapefile directory
        """
        region_dir = self.output_dir / f"REGION_NAME={region_name}" / "data_type=shapefiles"
        region_dir.mkdir(parents=True, exist_ok=True)
        return region_dir

    def write_region_shapefile(
        self,
        region_name: str,
        watersheds: list[DelineatedWatershed],
    ) -> Path:
        """
        Write all watersheds for a region to a single shapefile.

        Creates a shapefile with all successfully delineated watersheds in the region.
        Shapefile is written to a Hive-partitioned directory structure.

        Shapefile attributes:
            - gauge_id: str - Outlet identifier
            - gauge_nam: str - Outlet name (truncated to fit shapefile 10-char limit)
            - gauge_lat: float - Original outlet latitude
            - gauge_lon: float - Original outlet longitude
            - snap_lat: float - Snapped outlet latitude
            - snap_lon: float - Snapped outlet longitude
            - snap_dist: float - Snap distance in meters
            - country: str - Country name
            - area: float - Watershed area in km²
            - geometry: Polygon - Watershed boundary

        Args:
            region_name: Name of the region
            watersheds: List of successfully delineated watersheds

        Returns:
            Path to the written shapefile (.shp)

        Raises:
            ValueError: If watersheds list is empty
        """
        if not watersheds:
            raise ValueError(f"Cannot write shapefile for region '{region_name}': no watersheds provided")

        logger.info(f"Writing {len(watersheds)} watersheds for region '{region_name}'")

        # Get output directory
        region_dir = self.get_region_output_dir(region_name)
        shapefile_path = region_dir / f"{region_name}_shapes.shp"

        # Convert watersheds to GeoDataFrame
        data = []
        geometries = []

        for ws in watersheds:
            data.append(
                {
                    "gauge_id": ws.gauge_id,
                    "gauge_nam": ws.gauge_name,  # Will be truncated by geopandas if needed
                    "gauge_lat": ws.gauge_lat,
                    "gauge_lon": ws.gauge_lon,
                    "snap_lat": ws.snap_lat,
                    "snap_lon": ws.snap_lon,
                    "snap_dist": ws.snap_dist,
                    "country": ws.country,
                    "area": ws.area,
                }
            )
            geometries.append(ws.geometry)

        # Create GeoDataFrame
        gdf = gpd.GeoDataFrame(data, geometry=geometries, crs="EPSG:4326")

        # Write to shapefile
        gdf.to_file(shapefile_path, driver="ESRI Shapefile")

        logger.info(f"Successfully wrote shapefile: {shapefile_path}")
        return shapefile_path

    def record_failure(
        self,
        region_name: str,
        gauge_id: str,
        lat: float,
        lng: float,
        error: str,
    ) -> None:
        """
        Record a failed delineation for later writing to FAILED.csv.

        Args:
            region_name: Name of the region this outlet belongs to
            gauge_id: Unique identifier for the outlet
            lat: Latitude of the outlet point
            lng: Longitude of the outlet point
            error: Description of what went wrong
        """
        failure = FailedOutlet(
            region_name=region_name,
            gauge_id=gauge_id,
            lat=lat,
            lng=lng,
            error=error,
        )
        self.failed_outlets.append(failure)
        logger.warning(f"Recorded failure for {region_name}/{gauge_id}: {error}")

    def write_failed_csv(self) -> Path | None:
        """
        Write all recorded failures to FAILED.csv.

        CSV columns: region_name, gauge_id, lat, lng, error

        Returns:
            Path to FAILED.csv if any failures were recorded, else None
        """
        if not self.failed_outlets:
            logger.info("No failures to write")
            return None

        failed_csv = self.output_dir / "FAILED.csv"

        logger.info(f"Writing {len(self.failed_outlets)} failures to {failed_csv}")

        with open(failed_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["region_name", "gauge_id", "lat", "lng", "error"])

            for failure in self.failed_outlets:
                writer.writerow(
                    [
                        failure.region_name,
                        failure.gauge_id,
                        failure.lat,
                        failure.lng,
                        failure.error,
                    ]
                )

        logger.info(f"Successfully wrote FAILED.csv: {failed_csv}")
        return failed_csv

    def finalize(self) -> Path | None:
        """
        Finalize output by writing FAILED.csv.

        Call this after all regions have been processed.

        Returns:
            Path to FAILED.csv if any failures occurred, else None
        """
        return self.write_failed_csv()

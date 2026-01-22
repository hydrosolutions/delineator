"""
Output writer module for watershed delineation results.

Handles writing delineation results to Hive-partitioned directory structures,
including shapefiles/GeoPackages for successful watersheds and CSV logging for failures.
"""

import csv
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal

import fiona
import geopandas as gpd


class OutputFormat(str, Enum):
    """Supported output file formats for watershed delineation results."""

    SHAPEFILE = "shp"
    GEOPACKAGE = "gpkg"


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

    def __init__(
        self,
        output_dir: Path,
        output_format: OutputFormat = OutputFormat.GEOPACKAGE,
        include_rivers: bool = False,
    ):
        """
        Initialize writer with output directory and format.

        Args:
            output_dir: Base directory for all outputs
            output_format: Output format (GeoPackage or Shapefile)
            include_rivers: Whether to include river geometries in output
        """
        self.output_dir = Path(output_dir)
        self.output_format = output_format
        self.include_rivers = include_rivers
        self.failed_outlets: list[FailedOutlet] = []

    def get_region_output_dir(self, region_name: str) -> Path:
        """
        Get Hive-partitioned directory for a region.

        Creates directory structure based on output format:
        - GeoPackage: output_dir/REGION_NAME={region_name}/data_type=geopackage/
        - Shapefile: output_dir/REGION_NAME={region_name}/data_type=shapefiles/

        Args:
            region_name: Name of the region

        Returns:
            Path to the region's output directory
        """
        data_type = "geopackage" if self.output_format == OutputFormat.GEOPACKAGE else "shapefiles"
        region_dir = self.output_dir / f"REGION_NAME={region_name}" / f"data_type={data_type}"
        region_dir.mkdir(parents=True, exist_ok=True)
        return region_dir

    def get_output_path(self, region_name: str) -> Path:
        """
        Get the output file path for a region (without creating directories).

        Args:
            region_name: Name of the region

        Returns:
            Path to the output file (.gpkg or .shp)
        """
        if self.output_format == OutputFormat.GEOPACKAGE:
            data_type = "geopackage"
            filename = f"{region_name}.gpkg"
        else:
            data_type = "shapefiles"
            filename = f"{region_name}_shapes.shp"

        return self.output_dir / f"REGION_NAME={region_name}" / f"data_type={data_type}" / filename

    def check_output_exists(self, region_name: str) -> bool:
        """
        Check if output file already exists for a region.

        Args:
            region_name: Name of the region

        Returns:
            True if output file exists, False otherwise
        """
        return self.get_output_path(region_name).exists()

    def read_existing_gauge_ids(self, region_name: str) -> set[str]:
        """
        Load gauge_ids from existing output file without loading geometries.

        Uses fiona iterator for efficiency (~0.1s for 10k records vs ~5s with gpd.read_file).

        Args:
            region_name: Name of the region

        Returns:
            Set of gauge_ids found in existing output, empty set if file doesn't exist
        """
        output_path = self.get_output_path(region_name)

        if not output_path.exists():
            return set()

        try:
            gauge_ids: set[str] = set()
            with fiona.open(output_path, "r") as src:
                for feature in src:
                    gauge_id = feature["properties"].get("gauge_id")
                    if gauge_id is not None:
                        gauge_ids.add(str(gauge_id))
            logger.info(f"Loaded {len(gauge_ids)} existing gauge_ids from {output_path}")
            return gauge_ids
        except Exception as e:
            logger.warning(f"Could not read existing gauge_ids from {output_path}: {e}")
            return set()

    def _build_geodataframe(self, watersheds: list[DelineatedWatershed]) -> gpd.GeoDataFrame:
        """
        Convert list of DelineatedWatershed to GeoDataFrame.

        Args:
            watersheds: List of delineated watersheds

        Returns:
            GeoDataFrame with watershed data and geometries
        """
        data = []
        geometries = []

        for ws in watersheds:
            data.append(
                {
                    "gauge_id": ws.gauge_id,
                    "gauge_nam": ws.gauge_name,  # Truncated by geopandas for shapefiles
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

        return gpd.GeoDataFrame(data, geometry=geometries, crs="EPSG:4326")

    def _build_rivers_geodataframe(self, watersheds: list[DelineatedWatershed]) -> gpd.GeoDataFrame | None:
        """
        Combine river geometries from all watersheds into a single GeoDataFrame.

        Args:
            watersheds: List of delineated watersheds with optional rivers

        Returns:
            GeoDataFrame with river geometries, or None if no rivers present
        """
        import pandas as pd

        river_gdfs = []
        for ws in watersheds:
            if ws.rivers is not None and not ws.rivers.empty:
                # Add gauge_id to track which watershed each river belongs to
                rivers_copy = ws.rivers.copy()
                rivers_copy["gauge_id"] = ws.gauge_id
                river_gdfs.append(rivers_copy)

        if not river_gdfs:
            return None

        combined = gpd.GeoDataFrame(
            pd.concat(river_gdfs, ignore_index=True),
            crs="EPSG:4326",
        )
        return combined

    def write_region_output(
        self,
        region_name: str,
        watersheds: list[DelineatedWatershed],
        mode: Literal["w", "a"] = "w",
    ) -> Path:
        """
        Write watersheds to region output file (GeoPackage or Shapefile).

        Supports append mode for GeoPackage. For Shapefile, append mode uses
        read-concat-write pattern since Shapefile doesn't support native append.

        Output attributes:
            - gauge_id: str - Outlet identifier
            - gauge_nam: str - Outlet name (truncated to 10 chars for Shapefile)
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
            mode: Write mode - "w" to overwrite, "a" to append

        Returns:
            Path to the written output file (.gpkg or .shp)

        Raises:
            ValueError: If watersheds list is empty
        """
        if not watersheds:
            raise ValueError(f"Cannot write output for region '{region_name}': no watersheds provided")

        logger.info(f"Writing {len(watersheds)} watersheds for region '{region_name}' (mode={mode})")

        # Get output directory and path (get_region_output_dir creates the directory)
        self.get_region_output_dir(region_name)
        output_path = self.get_output_path(region_name)

        # Convert watersheds to GeoDataFrame
        gdf = self._build_geodataframe(watersheds)

        # Build rivers GeoDataFrame if include_rivers is enabled
        rivers_gdf = self._build_rivers_geodataframe(watersheds) if self.include_rivers else None

        if self.output_format == OutputFormat.GEOPACKAGE:
            # GeoPackage supports native append mode
            driver = "GPKG"
            if mode == "a" and output_path.exists():
                gdf.to_file(output_path, driver=driver, mode="a")
                # Append rivers to existing rivers layer if present
                if rivers_gdf is not None:
                    rivers_gdf.to_file(output_path, driver=driver, layer="rivers", mode="a")
            else:
                gdf.to_file(output_path, driver=driver)
                # Write rivers as separate layer
                if rivers_gdf is not None:
                    rivers_gdf.to_file(output_path, driver=driver, layer="rivers", mode="a")
        else:
            # Shapefile: use read-concat-write for append
            driver = "ESRI Shapefile"
            if mode == "a" and output_path.exists():
                existing_gdf = gpd.read_file(output_path)
                import pandas as pd

                gdf = gpd.GeoDataFrame(
                    pd.concat([existing_gdf, gdf], ignore_index=True),
                    crs="EPSG:4326",
                )
            gdf.to_file(output_path, driver=driver)

            # Write rivers as separate shapefile
            if rivers_gdf is not None:
                rivers_path = output_path.parent / f"{region_name}_rivers.shp"
                if mode == "a" and rivers_path.exists():
                    import pandas as pd

                    existing_rivers = gpd.read_file(rivers_path)
                    rivers_gdf = gpd.GeoDataFrame(
                        pd.concat([existing_rivers, rivers_gdf], ignore_index=True),
                        crs="EPSG:4326",
                    )
                rivers_gdf.to_file(rivers_path, driver=driver)
                logger.info(f"Successfully wrote rivers output: {rivers_path}")

        logger.info(f"Successfully wrote output: {output_path}")
        return output_path

    def write_region_shapefile(
        self,
        region_name: str,
        watersheds: list[DelineatedWatershed],
    ) -> Path:
        """
        Write all watersheds for a region (backward compatibility alias).

        This method exists for backward compatibility. New code should use
        write_region_output() which supports both formats and append mode.

        Args:
            region_name: Name of the region
            watersheds: List of successfully delineated watersheds

        Returns:
            Path to the written output file
        """
        return self.write_region_output(region_name, watersheds, mode="w")

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

    def load_failed_gauge_ids(self) -> set[str]:
        """
        Load gauge_ids from existing FAILED.csv file.

        This is used by --skip-failed to skip outlets that previously failed.

        Returns:
            Set of gauge_ids that have previously failed, empty set if no FAILED.csv
        """
        failed_csv = self.output_dir / "FAILED.csv"

        if not failed_csv.exists():
            return set()

        try:
            gauge_ids: set[str] = set()
            with open(failed_csv, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    gauge_id = row.get("gauge_id")
                    if gauge_id:
                        gauge_ids.add(gauge_id)
            logger.info(f"Loaded {len(gauge_ids)} failed gauge_ids from {failed_csv}")
            return gauge_ids
        except Exception as e:
            logger.warning(f"Could not read FAILED.csv: {e}")
            return set()

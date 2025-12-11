"""
Data availability checker for MERIT-Hydro data.

This module provides utilities to check if required MERIT data files exist
locally and optionally trigger downloads for missing data. It validates the
presence of rasters (flow direction, flow accumulation), vectors (catchments,
rivers), and simplified catchments data.

The checker integrates with the download module to automatically fetch missing
data when requested, streamlining the workflow for watershed delineation tasks.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from delineator.download import download_data, get_basins_for_bbox

# Set up logging
logger = logging.getLogger(__name__)


@dataclass
class DataAvailability:
    """
    Results from a data availability check.

    Attributes:
        available_basins: List of basin codes with all required files present
        missing_basins: List of basin codes with one or more missing files
        missing_files: List of specific file paths that are missing
    """

    available_basins: list[int]
    missing_basins: list[int]
    missing_files: list[Path]

    @property
    def all_available(self) -> bool:
        """Check if all requested data is available."""
        return len(self.missing_basins) == 0


def _get_expected_files(
    basin: int,
    data_dir: Path,
    check_rasters: bool = True,
    check_vectors: bool = True,
) -> list[Path]:
    """
    Get list of expected file paths for a basin.

    Args:
        basin: Pfafstetter Level 2 basin code
        data_dir: Base data directory
        check_rasters: Include raster files in check
        check_vectors: Include vector files in check

    Returns:
        List of expected file paths
    """
    expected_files: list[Path] = []

    if check_rasters:
        # Flow direction and accumulation rasters
        expected_files.append(data_dir / "raster" / "flowdir_basins" / f"flowdir{basin}.tif")
        expected_files.append(data_dir / "raster" / "accum_basins" / f"accum{basin}.tif")

    if check_vectors:
        # Catchments shapefile (main .shp file)
        expected_files.append(
            data_dir / "shp" / "merit_catchments" / f"cat_pfaf_{basin}_MERIT_Hydro_v07_Basins_v01.shp"
        )
        # Rivers shapefile (main .shp file)
        expected_files.append(data_dir / "shp" / "merit_rivers" / f"riv_pfaf_{basin}_MERIT_Hydro_v07_Basins_v01.shp")

    return expected_files


def check_data_availability(
    basins: list[int],
    data_dir: Path,
    check_rasters: bool = True,
    check_vectors: bool = True,
    check_simplified: bool = True,
) -> DataAvailability:
    """
    Check if required MERIT data files exist.

    This function validates the presence of all necessary data files for the
    requested basins without triggering any downloads. It checks for flow
    direction and accumulation rasters, catchment and river shapefiles, and
    optionally simplified catchments data.

    Args:
        basins: List of Pfafstetter Level 2 basin codes to check
        data_dir: Base directory where MERIT data is stored
        check_rasters: Check for flow direction and accumulation rasters
        check_vectors: Check for catchment and river shapefiles
        check_simplified: Check for simplified catchments directory

    Returns:
        DataAvailability object with availability status and missing files

    Example:
        >>> from pathlib import Path
        >>> availability = check_data_availability(
        ...     basins=[41, 42],
        ...     data_dir=Path("data")
        ... )
        >>> if not availability.all_available:
        ...     print(f"Missing basins: {availability.missing_basins}")
    """
    logger.info(f"Checking data availability for {len(basins)} basin(s): {basins}")

    available_basins: list[int] = []
    missing_basins: list[int] = []
    missing_files: list[Path] = []

    # Check each basin
    for basin in basins:
        expected_files = _get_expected_files(
            basin=basin,
            data_dir=data_dir,
            check_rasters=check_rasters,
            check_vectors=check_vectors,
        )

        # Check which files are missing
        basin_missing_files = [f for f in expected_files if not f.exists()]

        if basin_missing_files:
            missing_basins.append(basin)
            missing_files.extend(basin_missing_files)
            logger.debug(f"Basin {basin}: {len(basin_missing_files)} missing file(s)")
        else:
            available_basins.append(basin)
            logger.debug(f"Basin {basin}: all files present")

    # Check simplified catchments directory if requested
    if check_simplified:
        simplified_dir = data_dir / "shp" / "catchments_simplified"
        if not simplified_dir.exists() or not any(simplified_dir.iterdir()):
            logger.debug("Simplified catchments directory missing or empty")
            missing_files.append(simplified_dir)
        else:
            logger.debug("Simplified catchments directory present")

    # Log summary
    logger.info(f"Data availability check complete: {len(available_basins)} available, {len(missing_basins)} missing")

    if missing_basins:
        logger.info(f"Missing basins: {missing_basins}")
        logger.debug(f"Total missing files: {len(missing_files)}")

    return DataAvailability(
        available_basins=available_basins,
        missing_basins=missing_basins,
        missing_files=missing_files,
    )


def ensure_data_available(
    basins: list[int],
    data_dir: Path,
    auto_download: bool = True,
    gdrive_credentials: Path | None = None,
) -> DataAvailability:
    """
    Check data and optionally download missing data.

    This function first checks if all required data files exist. If any files
    are missing and auto_download is True, it automatically downloads the
    missing data using the download module. After download (if triggered), it
    re-checks availability and returns the final status.

    Args:
        basins: List of Pfafstetter Level 2 basin codes
        data_dir: Base directory for MERIT data
        auto_download: If True, download missing data automatically
        gdrive_credentials: Path to Google Drive service account credentials
            (required for downloading vector data)

    Returns:
        DataAvailability object with final availability status

    Example:
        >>> from pathlib import Path
        >>> availability = ensure_data_available(
        ...     basins=[41],
        ...     data_dir=Path("data"),
        ...     auto_download=True,
        ...     gdrive_credentials=Path("credentials.json")
        ... )
        >>> if availability.all_available:
        ...     print("All data ready!")
    """
    logger.info(f"Ensuring data availability for {len(basins)} basin(s)")

    # Initial check
    availability = check_data_availability(
        basins=basins,
        data_dir=data_dir,
        check_rasters=True,
        check_vectors=True,
        check_simplified=True,
    )

    # If all data is available, return immediately
    if availability.all_available:
        logger.info("All requested data is already available")
        return availability

    # If auto_download is disabled, return current status
    if not auto_download:
        logger.warning(f"Missing data for {len(availability.missing_basins)} basin(s) but auto_download is disabled")
        return availability

    # Download missing data
    logger.info(
        f"Downloading missing data for {len(availability.missing_basins)} basin(s): {availability.missing_basins}"
    )

    try:
        download_result = download_data(
            basins=availability.missing_basins,
            output_dir=data_dir,
            include_rasters=True,
            include_vectors=True,
            include_simplified=True,
            overwrite=False,
            gdrive_credentials=gdrive_credentials,
        )

        if not download_result.success:
            logger.warning(f"Download completed with {len(download_result.errors)} error(s)")
            for error in download_result.errors:
                logger.warning(f"  - {error}")

    except Exception as e:
        logger.error(f"Download failed: {e}")

    # Re-check availability after download
    logger.info("Re-checking data availability after download")
    availability = check_data_availability(
        basins=basins,
        data_dir=data_dir,
        check_rasters=True,
        check_vectors=True,
        check_simplified=True,
    )

    if availability.all_available:
        logger.info("All data is now available")
    else:
        logger.warning(
            f"Still missing data for {len(availability.missing_basins)} basin(s): {availability.missing_basins}"
        )

    return availability


def get_required_basins(outlets: list[tuple[float, float]]) -> list[int]:
    """
    Given outlet coordinates, determine which Pfafstetter Level 2 basins are needed.

    This function computes a bounding box around all outlet points and uses the
    basin selector from the download module to determine which basins intersect
    that bounding box. This is useful for automatically determining which data
    needs to be downloaded for a set of watershed outlets.

    Args:
        outlets: List of (latitude, longitude) tuples in decimal degrees

    Returns:
        List of Pfafstetter Level 2 basin codes needed for the outlets

    Raises:
        ValueError: If outlets list is empty or contains invalid coordinates

    Example:
        >>> # Outlets in Iceland
        >>> outlets = [(64.1, -21.9), (65.7, -18.1)]
        >>> basins = get_required_basins(outlets)
        >>> print(basins)
        [41]
    """
    if not outlets:
        raise ValueError("Outlets list cannot be empty")

    logger.info(f"Determining required basins for {len(outlets)} outlet(s)")

    # Extract latitudes and longitudes
    try:
        lats, lons = zip(*outlets, strict=True)
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid outlet coordinates format. Expected list of (lat, lon) tuples: {e}") from e

    # Validate coordinates
    for i, (lat, lon) in enumerate(outlets):
        if not (-90 <= lat <= 90):
            raise ValueError(f"Invalid latitude at outlet {i}: {lat}. Must be between -90 and 90.")
        if not (-180 <= lon <= 180):
            raise ValueError(f"Invalid longitude at outlet {i}: {lon}. Must be between -180 and 180.")

    # Compute bounding box
    min_lat = min(lats)
    max_lat = max(lats)
    min_lon = min(lons)
    max_lon = max(lons)

    logger.debug(f"Computed bounding box: ({min_lon}, {min_lat}, {max_lon}, {max_lat})")

    # Get basins intersecting the bounding box
    basins = get_basins_for_bbox(min_lon=min_lon, min_lat=min_lat, max_lon=max_lon, max_lat=max_lat)

    logger.info(f"Found {len(basins)} required basin(s): {basins}")

    return basins

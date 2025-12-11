"""
Downloader orchestrator for MERIT-Hydro and MERIT-Basins data.

This module provides the main interface for downloading all required data
(rasters and vectors) for watershed delineation. It orchestrates downloads
from multiple sources (HTTP and Google Drive) and handles batch operations
across multiple basins.

The downloader supports:
- Automatic basin selection from bounding boxes
- Batch downloads of flow direction and accumulation rasters
- Batch downloads of catchment and river shapefiles
- Simplified catchments data
- Error collection and reporting
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .basin_selector import get_basins_for_bbox, validate_basin_codes
from .gdrive_client import download_basin_vectors as gdrive_download_basin_vectors
from .http_client import download_basin_rasters, download_simplified_catchments

# Set up logging
logger = logging.getLogger(__name__)


@dataclass
class DownloadResult:
    """Results from a data download operation."""

    basins_downloaded: list[int] = field(default_factory=list)
    rasters: dict[int, dict[str, Path]] = field(
        default_factory=dict
    )  # basin -> {flowdir: path, accum: path}
    vectors: dict[int, dict[str, Path]] = field(
        default_factory=dict
    )  # basin -> {catchments: path, rivers: path}
    simplified_catchments: Path | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Check if the download completed without errors."""
        return len(self.errors) == 0


def get_output_paths(base_dir: Path) -> dict[str, Path]:
    """
    Get standard output directory paths.

    Args:
        base_dir: Base directory for all data

    Returns:
        Dictionary mapping data type to output path
    """
    return {
        "flowdir": base_dir / "raster" / "flowdir_basins",
        "accum": base_dir / "raster" / "accum_basins",
        "catchments": base_dir / "shp" / "merit_catchments",
        "rivers": base_dir / "shp" / "merit_rivers",
        "simplified": base_dir / "shp" / "catchments_simplified",
    }


def download_rasters_for_basins(
    basins: list[int], output_dir: Path, overwrite: bool = False
) -> tuple[dict[int, dict[str, Path]], list[str]]:
    """
    Download rasters for multiple basins.

    Args:
        basins: List of Pfafstetter Level 2 basin codes
        output_dir: Base directory for raster outputs
        overwrite: Re-download files even if they exist

    Returns:
        Tuple of (results_dict, errors_list) where results_dict maps
        basin code to dict of raster type to path
    """
    results: dict[int, dict[str, Path]] = {}
    errors: list[str] = []

    # Get output paths
    paths = get_output_paths(output_dir)
    flowdir_dir = paths["flowdir"]
    accum_dir = paths["accum"]

    logger.info(f"Downloading rasters for {len(basins)} basin(s)")

    for basin in basins:
        try:
            logger.info(f"Downloading rasters for basin {basin}")

            # Download flow direction to its directory
            flowdir_path = download_basin_rasters(
                basin=basin,
                dest_dir=flowdir_dir,
                include_flowdir=True,
                include_accum=False,
                overwrite=overwrite,
            )

            # Download flow accumulation to its directory
            accum_path = download_basin_rasters(
                basin=basin,
                dest_dir=accum_dir,
                include_flowdir=False,
                include_accum=True,
                overwrite=overwrite,
            )

            # Combine results
            results[basin] = {
                "flowdir": flowdir_path["flowdir"],
                "accum": accum_path["accum"],
            }

            logger.info(f"Successfully downloaded rasters for basin {basin}")

        except Exception as e:
            error_msg = f"Failed to download rasters for basin {basin}: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

    return results, errors


def download_vectors_for_basins(
    basins: list[int],
    output_dir: Path,
    overwrite: bool = False,
    credentials: Path | None = None,
) -> tuple[dict[int, dict[str, Path]], list[str]]:
    """
    Download vectors for multiple basins from Google Drive.

    Args:
        basins: List of Pfafstetter Level 2 basin codes
        output_dir: Base directory for vector outputs
        overwrite: Re-download files even if they exist
        credentials: Path to Google Drive service account credentials

    Returns:
        Tuple of (results_dict, errors_list) where results_dict maps
        basin code to dict of vector type to path
    """
    results: dict[int, dict[str, Path]] = {}
    errors: list[str] = []

    # Get output paths
    paths = get_output_paths(output_dir)
    catchments_dir = paths["catchments"]

    logger.info(f"Downloading vectors for {len(basins)} basin(s)")

    for basin in basins:
        try:
            logger.info(f"Downloading vectors for basin {basin}")

            # Download both catchments and rivers
            vector_paths = gdrive_download_basin_vectors(
                basin=basin,
                dest_dir=catchments_dir,  # Will be organized by type
                include_catchments=True,
                include_rivers=True,
                overwrite=overwrite,
                credentials_path=credentials,
            )

            results[basin] = vector_paths
            logger.info(f"Successfully downloaded vectors for basin {basin}")

        except Exception as e:
            error_msg = f"Failed to download vectors for basin {basin}: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

    return results, errors


def download_data(
    bbox: tuple[float, float, float, float] | None = None,
    basins: list[int] | None = None,
    output_dir: Path | str = "data",
    include_rasters: bool = True,
    include_vectors: bool = True,
    include_simplified: bool = True,
    overwrite: bool = False,
    gdrive_credentials: Path | None = None,
) -> DownloadResult:
    """
    Download all MERIT data needed for delineation.

    Either bbox or basins must be provided. If both are provided, basins takes precedence.

    Args:
        bbox: Bounding box as (min_lon, min_lat, max_lon, max_lat)
        basins: List of Pfafstetter Level 2 basin codes to download
        output_dir: Base directory for downloaded data
        include_rasters: Download flow direction and accumulation rasters
        include_vectors: Download catchment and river shapefiles from Google Drive
        include_simplified: Download simplified catchments ZIP
        overwrite: Re-download files even if they exist
        gdrive_credentials: Path to Google Drive service account credentials

    Returns:
        DownloadResult with paths to all downloaded files and any errors

    Raises:
        ValueError: Neither bbox nor basins provided

    Example:
        >>> # Download data for Iceland
        >>> result = download_data(bbox=(-25, 63, -13, 67))
        >>> print(f"Downloaded {len(result.basins_downloaded)} basin(s)")
        >>> print(f"Success: {result.success}")
    """
    # Validate inputs
    if bbox is None and basins is None:
        raise ValueError("Either bbox or basins must be provided")

    # Convert output_dir to Path
    output_dir = Path(output_dir)

    # Initialize result
    result = DownloadResult()

    # Determine which basins to download
    if basins is not None:
        logger.info(f"Using provided basin codes: {basins}")
        try:
            basins = validate_basin_codes(basins)
        except ValueError as e:
            result.errors.append(f"Basin validation failed: {e}")
            return result
    else:
        # Extract from bbox
        assert bbox is not None  # For type checker
        min_lon, min_lat, max_lon, max_lat = bbox
        logger.info(
            f"Finding basins for bbox: ({min_lon}, {min_lat}, {max_lon}, {max_lat})"
        )
        try:
            basins = get_basins_for_bbox(min_lon, min_lat, max_lon, max_lat)
            if not basins:
                result.errors.append(f"No basins found for bbox: {bbox}")
                return result
        except Exception as e:
            result.errors.append(f"Failed to get basins for bbox: {e}")
            return result

    logger.info(f"Will download data for {len(basins)} basin(s): {basins}")

    # Create output directories
    paths = get_output_paths(output_dir)
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Created directory: {path}")

    # Download rasters
    if include_rasters:
        logger.info("=" * 60)
        logger.info("DOWNLOADING RASTERS")
        logger.info("=" * 60)

        rasters_result, rasters_errors = download_rasters_for_basins(
            basins=basins, output_dir=output_dir, overwrite=overwrite
        )

        result.rasters = rasters_result
        result.errors.extend(rasters_errors)

        if rasters_result:
            result.basins_downloaded.extend(rasters_result.keys())

    # Download vectors
    if include_vectors:
        logger.info("=" * 60)
        logger.info("DOWNLOADING VECTORS")
        logger.info("=" * 60)

        vectors_result, vectors_errors = download_vectors_for_basins(
            basins=basins,
            output_dir=output_dir,
            overwrite=overwrite,
            credentials=gdrive_credentials,
        )

        result.vectors = vectors_result
        result.errors.extend(vectors_errors)

    # Download simplified catchments
    if include_simplified:
        logger.info("=" * 60)
        logger.info("DOWNLOADING SIMPLIFIED CATCHMENTS")
        logger.info("=" * 60)

        try:
            simplified_path = download_simplified_catchments(
                dest_dir=paths["simplified"], overwrite=overwrite
            )
            result.simplified_catchments = simplified_path
            logger.info("Successfully downloaded simplified catchments")
        except Exception as e:
            error_msg = f"Failed to download simplified catchments: {e}"
            logger.error(error_msg)
            result.errors.append(error_msg)

    # Remove duplicates from basins_downloaded and sort
    result.basins_downloaded = sorted(set(result.basins_downloaded))

    # Log summary
    logger.info("=" * 60)
    logger.info("DOWNLOAD SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Basins downloaded: {result.basins_downloaded}")
    logger.info(f"Rasters downloaded: {len(result.rasters)}")
    logger.info(f"Vectors downloaded: {len(result.vectors)}")
    logger.info(f"Simplified catchments: {result.simplified_catchments is not None}")
    logger.info(f"Errors: {len(result.errors)}")

    if result.errors:
        logger.warning("Download completed with errors:")
        for error in result.errors:
            logger.warning(f"  - {error}")
    else:
        logger.info("Download completed successfully!")

    return result

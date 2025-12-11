"""
HTTP download client for MERIT-Hydro raster data.

This module provides functions to download MERIT-Hydro raster files from mghydro.com
via direct HTTP. It supports downloading flow direction, flow accumulation rasters
for specific basins, and simplified catchments data.
"""

import logging
import time
from collections.abc import Callable
from pathlib import Path

import httpx
from tqdm import tqdm

# Configure logging
logger = logging.getLogger(__name__)

# URL patterns for MERIT-Hydro data
MGHYDRO_BASE_URL = "https://mghydro.com/watersheds/rasters"
ACCUM_URL_PATTERN = f"{MGHYDRO_BASE_URL}/accum_basins/accum{{basin}}.tif"
FLOWDIR_URL_PATTERN = f"{MGHYDRO_BASE_URL}/flow_dir_basins/flowdir{{basin}}.tif"
SIMPLIFIED_CATCHMENTS_URL = "https://mghydro.com/watersheds/share/catchments_simplified.zip"

# Download configuration
CHUNK_SIZE = 8192  # 8KB chunks
MAX_RETRIES = 3
RETRY_DELAY = 2.0  # seconds
TIMEOUT = 3600.0  # 1 hour for large files


def download_raster(
    basin: int,
    raster_type: str,
    dest_dir: Path,
    overwrite: bool = False,
    progress_callback: Callable[[int, int], None] | None = None,
) -> Path:
    """
    Download a MERIT-Hydro raster file for a specific basin.

    Args:
        basin: Pfafstetter Level 2 basin code (e.g., 42)
        raster_type: Either "flowdir" or "accum"
        dest_dir: Directory to save the file
        overwrite: If True, re-download even if file exists
        progress_callback: Optional callback(bytes_downloaded, total_bytes)

    Returns:
        Path to downloaded file

    Raises:
        ValueError: Invalid raster_type or basin
        httpx.HTTPError: Download failed
    """
    # Validate inputs
    if raster_type not in ["flowdir", "accum"]:
        raise ValueError(f"Invalid raster_type: {raster_type}. Must be 'flowdir' or 'accum'")

    if basin < 0 or basin > 99:
        raise ValueError(f"Invalid basin code: {basin}. Must be between 0 and 99")

    # Determine URL and filename
    if raster_type == "flowdir":
        url = FLOWDIR_URL_PATTERN.format(basin=basin)
        filename = f"flowdir{basin}.tif"
    else:  # accum
        url = ACCUM_URL_PATTERN.format(basin=basin)
        filename = f"accum{basin}.tif"

    # Create destination directory if it doesn't exist
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest_path = dest_dir / filename

    # Check if file exists
    if dest_path.exists() and not overwrite:
        logger.info(f"File already exists: {dest_path}")
        return dest_path

    logger.info(f"Downloading {raster_type} raster for basin {basin} from {url}")

    # Download with retries
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            _download_file(url, dest_path, progress_callback)
            logger.info(f"Successfully downloaded {filename}")
            return dest_path
        except httpx.HTTPError as e:
            if attempt < MAX_RETRIES:
                logger.warning(f"Download attempt {attempt} failed: {e}. Retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
            else:
                logger.error(f"Download failed after {MAX_RETRIES} attempts: {e}")
                # Clean up partial download
                if dest_path.exists():
                    dest_path.unlink()
                raise


def download_simplified_catchments(
    dest_dir: Path,
    overwrite: bool = False,
    progress_callback: Callable[[int, int], None] | None = None,
) -> Path:
    """
    Download the simplified catchments ZIP file.

    Args:
        dest_dir: Directory to save the file
        overwrite: If True, re-download even if file exists
        progress_callback: Optional callback(bytes_downloaded, total_bytes)

    Returns:
        Path to downloaded file

    Raises:
        httpx.HTTPError: Download failed
    """
    # Create destination directory if it doesn't exist
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    filename = "catchments_simplified.zip"
    dest_path = dest_dir / filename

    # Check if file exists
    if dest_path.exists() and not overwrite:
        logger.info(f"File already exists: {dest_path}")
        return dest_path

    logger.info(f"Downloading simplified catchments from {SIMPLIFIED_CATCHMENTS_URL}")

    # Download with retries
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            _download_file(SIMPLIFIED_CATCHMENTS_URL, dest_path, progress_callback)
            logger.info(f"Successfully downloaded {filename}")
            return dest_path
        except httpx.HTTPError as e:
            if attempt < MAX_RETRIES:
                logger.warning(f"Download attempt {attempt} failed: {e}. Retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
            else:
                logger.error(f"Download failed after {MAX_RETRIES} attempts: {e}")
                # Clean up partial download
                if dest_path.exists():
                    dest_path.unlink()
                raise


def download_basin_rasters(
    basin: int,
    dest_dir: Path,
    include_flowdir: bool = True,
    include_accum: bool = True,
    overwrite: bool = False,
) -> dict[str, Path]:
    """
    Download both flowdir and accum rasters for a basin.

    Args:
        basin: Pfafstetter Level 2 basin code (e.g., 42)
        dest_dir: Directory to save the files
        include_flowdir: If True, download flow direction raster
        include_accum: If True, download flow accumulation raster
        overwrite: If True, re-download even if files exist

    Returns:
        Dictionary mapping raster type to downloaded file path

    Raises:
        ValueError: Invalid basin or no raster types selected
        httpx.HTTPError: Download failed
    """
    if not include_flowdir and not include_accum:
        raise ValueError("At least one of include_flowdir or include_accum must be True")

    results: dict[str, Path] = {}

    if include_flowdir:
        logger.info(f"Downloading flow direction raster for basin {basin}")
        results["flowdir"] = download_raster(
            basin=basin,
            raster_type="flowdir",
            dest_dir=dest_dir,
            overwrite=overwrite,
        )

    if include_accum:
        logger.info(f"Downloading flow accumulation raster for basin {basin}")
        results["accum"] = download_raster(
            basin=basin,
            raster_type="accum",
            dest_dir=dest_dir,
            overwrite=overwrite,
        )

    return results


def _download_file(
    url: str,
    dest_path: Path,
    progress_callback: Callable[[int, int], None] | None = None,
) -> None:
    """
    Download a file from URL to destination path with progress tracking.

    Args:
        url: URL to download from
        dest_path: Path to save the file
        progress_callback: Optional callback(bytes_downloaded, total_bytes)

    Raises:
        httpx.HTTPError: Download failed
    """
    with httpx.Client(timeout=TIMEOUT) as client, client.stream("GET", url) as response:
        response.raise_for_status()

        total_size = int(response.headers.get("content-length", 0))

        # Use tqdm if no callback provided
        if progress_callback is None and total_size > 0:
            progress_bar = tqdm(
                total=total_size,
                unit="B",
                unit_scale=True,
                desc=dest_path.name,
            )
        else:
            progress_bar = None

        bytes_downloaded = 0

        try:
            with open(dest_path, "wb") as f:
                for chunk in response.iter_bytes(chunk_size=CHUNK_SIZE):
                    f.write(chunk)
                    bytes_downloaded += len(chunk)

                    if progress_callback:
                        progress_callback(bytes_downloaded, total_size)
                    elif progress_bar:
                        progress_bar.update(len(chunk))
        finally:
            if progress_bar:
                progress_bar.close()

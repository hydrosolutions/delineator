"""
Google Drive download client for MERIT-Basins vector data.

This module provides functions to download MERIT-Basins vector shapefiles from
Google Drive (hosted by ReachHydro/Princeton). The data includes catchment polygons
and river flowlines organized by Pfafstetter Level 2 basin codes.

Data is hosted at: https://www.reachhydro.org/home/params/merit-basins

Supports two data formats:
- v1.0: Original ZIP archives (cat_pfaf_{basin}_MERIT_Hydro_v07_Basins_v01.zip)
- bugfix1: Individual shapefile components with _bugfix1 suffix (default)

Configure via environment variables:
- MERIT_BASINS_VERSION: "v1.0" or "bugfix1" (default: "bugfix1")
- MERIT_BASINS_FOLDER_ID: Override default folder ID for the selected version
"""

import io
import logging
import os
import time
import zipfile
from collections.abc import Callable
from enum import Enum
from functools import lru_cache
from pathlib import Path

from google.auth.exceptions import GoogleAuthError
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from tqdm import tqdm

# Configure logging
logger = logging.getLogger(__name__)


class DataSource(Enum):
    """Available MERIT-Basins data sources on Google Drive."""

    V1_ZIP = "v1.0"  # Original ZIP files
    BUGFIX1 = "bugfix1"  # Bugfix1 individual shapefile components (default)


# Shapefile component extensions
SHAPEFILE_EXTENSIONS_REQUIRED = [".shp", ".dbf", ".shx"]
SHAPEFILE_EXTENSIONS_OPTIONAL = [".prj", ".cpg"]
SHAPEFILE_EXTENSIONS = SHAPEFILE_EXTENSIONS_REQUIRED + SHAPEFILE_EXTENSIONS_OPTIONAL

# Default folder IDs for each data source
FOLDER_IDS: dict[DataSource, str] = {
    DataSource.V1_ZIP: "1uCQFmdxFbjwoT9OYJxw-pXaP8q_GYH1a",
    DataSource.BUGFIX1: "1owkvZQBMZbvRv3V4Ff3xQPEgmAC48vJo",
}

# File naming patterns for each data source
PATTERNS: dict[DataSource, dict[str, str]] = {
    DataSource.V1_ZIP: {
        "catchments": "cat_pfaf_{basin:02d}_MERIT_Hydro_v07_Basins_v01",
        "rivers": "riv_pfaf_{basin:02d}_MERIT_Hydro_v07_Basins_v01",
    },
    DataSource.BUGFIX1: {
        "catchments": "cat_pfaf_{basin:02d}_MERIT_Hydro_v07_Basins_v01_bugfix1",
        "rivers": "riv_pfaf_{basin:02d}_MERIT_Hydro_v07_Basins_v01_bugfix1",
    },
}

# Canonical output pattern (what downstream code expects - no _bugfix1 suffix)
OUTPUT_PATTERN: dict[str, str] = {
    "catchments": "cat_pfaf_{basin:02d}_MERIT_Hydro_v07_Basins_v01",
    "rivers": "riv_pfaf_{basin:02d}_MERIT_Hydro_v07_Basins_v01",
}


def _get_default_data_source() -> DataSource:
    """Get the default data source from environment variable."""
    version = os.getenv("MERIT_BASINS_VERSION", "bugfix1")
    try:
        return DataSource(version)
    except ValueError:
        logger.warning(
            f"Invalid MERIT_BASINS_VERSION: {version}. Using 'bugfix1'. "
            f"Valid values: {[ds.value for ds in DataSource]}"
        )
        return DataSource.BUGFIX1


# Legacy: Google Drive folder ID - can be overridden via environment variable
# This is now computed based on data source, but env var still takes precedence
MERIT_BASINS_FOLDER_ID = os.getenv("MERIT_BASINS_FOLDER_ID", "")

# Legacy file naming patterns (kept for backward compatibility)
CATCHMENTS_PATTERN = "cat_pfaf_{basin:02d}_MERIT_Hydro_v07_Basins_v01"
RIVERS_PATTERN = "riv_pfaf_{basin:02d}_MERIT_Hydro_v07_Basins_v01"

# Download configuration
CHUNK_SIZE = 8 * 1024 * 1024  # 8MB chunks for Google Drive
MAX_RETRIES = 3
RETRY_DELAY = 2.0  # seconds


def download_catchments(
    basin: int,
    dest_dir: Path,
    overwrite: bool = False,
    credentials_path: Path | None = None,
    data_source: DataSource | None = None,
) -> Path:
    """
    Download MERIT-Basins catchment shapefile for a specific basin.

    Supports two data formats:
    - v1.0: Downloads ZIP archive and extracts it
    - bugfix1 (default): Downloads individual shapefile components

    Args:
        basin: Pfafstetter Level 2 basin code (e.g., 42)
        dest_dir: Directory to save extracted files
        overwrite: If True, re-download even if files exist
        credentials_path: Path to service account JSON. If None, uses GOOGLE_APPLICATION_CREDENTIALS env var.
        data_source: Data source to use. If None, uses MERIT_BASINS_VERSION env var (default: bugfix1).

    Returns:
        Path to directory containing extracted shapefile components

    Raises:
        ValueError: Invalid basin code
        FileNotFoundError: Credentials file not found or data not found on Google Drive
        GoogleAuthError: Authentication failed

    Example:
        >>> from pathlib import Path
        >>> cat_dir = download_catchments(42, Path("data/vectors"))
        >>> list(cat_dir.glob("*.shp"))
        [PosixPath('data/vectors/cat_pfaf_42/cat_pfaf_42_MERIT_Hydro_v07_Basins_v01.shp')]
    """
    _validate_basin(basin)

    # Determine data source
    if data_source is None:
        data_source = _get_default_data_source()

    # Get folder ID (env var overrides default)
    folder_id = MERIT_BASINS_FOLDER_ID or FOLDER_IDS.get(data_source, "")
    if not folder_id:
        raise RuntimeError(
            f"No folder ID configured for data source '{data_source.value}'. "
            "Set MERIT_BASINS_FOLDER_ID environment variable."
        )

    # Get patterns
    source_base = PATTERNS[data_source]["catchments"].format(basin=basin)
    target_base = OUTPUT_PATTERN["catchments"].format(basin=basin)
    extract_dir_name = f"cat_pfaf_{basin:02d}"
    extract_dir = Path(dest_dir) / extract_dir_name

    # Check if already downloaded (check for .shp file)
    target_shp = extract_dir / f"{target_base}.shp"
    if target_shp.exists() and not overwrite:
        logger.info(f"Files already exist: {extract_dir}")
        return extract_dir

    if data_source == DataSource.BUGFIX1:
        # Download individual shapefile components
        credentials = _get_credentials(credentials_path)
        service = _get_drive_service(credentials)

        logger.info(f"Downloading catchments for basin {basin} (bugfix1 format)")
        return _download_shapefile_components(
            service=service,
            folder_id=folder_id,
            source_base=source_base,
            dest_dir=extract_dir,
            target_base=target_base,
            overwrite=overwrite,
        )
    else:
        # Original ZIP download (v1.0)
        zip_filename = f"{source_base}.zip"

        logger.info(f"Downloading catchments for basin {basin} (ZIP format)")
        return _download_and_extract(
            filename=zip_filename,
            dest_dir=dest_dir,
            extract_dir_name=extract_dir_name,
            overwrite=overwrite,
            credentials_path=credentials_path,
        )


def download_rivers(
    basin: int,
    dest_dir: Path,
    overwrite: bool = False,
    credentials_path: Path | None = None,
    data_source: DataSource | None = None,
) -> Path:
    """
    Download MERIT-Basins river flowlines shapefile for a specific basin.

    Supports two data formats:
    - v1.0: Downloads ZIP archive and extracts it
    - bugfix1 (default): Downloads individual shapefile components

    Args:
        basin: Pfafstetter Level 2 basin code (e.g., 42)
        dest_dir: Directory to save extracted files
        overwrite: If True, re-download even if files exist
        credentials_path: Path to service account JSON. If None, uses GOOGLE_APPLICATION_CREDENTIALS env var.
        data_source: Data source to use. If None, uses MERIT_BASINS_VERSION env var (default: bugfix1).

    Returns:
        Path to directory containing extracted shapefile components

    Raises:
        ValueError: Invalid basin code
        FileNotFoundError: Credentials file not found or data not found on Google Drive
        GoogleAuthError: Authentication failed

    Example:
        >>> from pathlib import Path
        >>> riv_dir = download_rivers(42, Path("data/vectors"))
        >>> list(riv_dir.glob("*.shp"))
        [PosixPath('data/vectors/riv_pfaf_42/riv_pfaf_42_MERIT_Hydro_v07_Basins_v01.shp')]
    """
    _validate_basin(basin)

    # Determine data source
    if data_source is None:
        data_source = _get_default_data_source()

    # Get folder ID (env var overrides default)
    folder_id = MERIT_BASINS_FOLDER_ID or FOLDER_IDS.get(data_source, "")
    if not folder_id:
        raise RuntimeError(
            f"No folder ID configured for data source '{data_source.value}'. "
            "Set MERIT_BASINS_FOLDER_ID environment variable."
        )

    # Get patterns
    source_base = PATTERNS[data_source]["rivers"].format(basin=basin)
    target_base = OUTPUT_PATTERN["rivers"].format(basin=basin)
    extract_dir_name = f"riv_pfaf_{basin:02d}"
    extract_dir = Path(dest_dir) / extract_dir_name

    # Check if already downloaded (check for .shp file)
    target_shp = extract_dir / f"{target_base}.shp"
    if target_shp.exists() and not overwrite:
        logger.info(f"Files already exist: {extract_dir}")
        return extract_dir

    if data_source == DataSource.BUGFIX1:
        # Download individual shapefile components
        credentials = _get_credentials(credentials_path)
        service = _get_drive_service(credentials)

        logger.info(f"Downloading rivers for basin {basin} (bugfix1 format)")
        return _download_shapefile_components(
            service=service,
            folder_id=folder_id,
            source_base=source_base,
            dest_dir=extract_dir,
            target_base=target_base,
            overwrite=overwrite,
        )
    else:
        # Original ZIP download (v1.0)
        zip_filename = f"{source_base}.zip"

        logger.info(f"Downloading rivers for basin {basin} (ZIP format)")
        return _download_and_extract(
            filename=zip_filename,
            dest_dir=dest_dir,
            extract_dir_name=extract_dir_name,
            overwrite=overwrite,
            credentials_path=credentials_path,
        )


def download_basin_vectors(
    basin: int,
    dest_dir: Path,
    include_catchments: bool = True,
    include_rivers: bool = True,
    overwrite: bool = False,
    credentials_path: Path | None = None,
    data_source: DataSource | None = None,
) -> dict[str, Path]:
    """
    Download both catchments and rivers for a basin.

    Supports two data formats:
    - v1.0: Downloads ZIP archives and extracts them
    - bugfix1 (default): Downloads individual shapefile components

    Args:
        basin: Pfafstetter Level 2 basin code (e.g., 42)
        dest_dir: Directory to save the files
        include_catchments: If True, download catchment polygons
        include_rivers: If True, download river flowlines
        overwrite: If True, re-download even if files exist
        credentials_path: Path to service account JSON. If None, uses GOOGLE_APPLICATION_CREDENTIALS env var.
        data_source: Data source to use. If None, uses MERIT_BASINS_VERSION env var (default: bugfix1).

    Returns:
        Dictionary mapping vector type ("catchments", "rivers") to extracted directory path

    Raises:
        ValueError: Invalid basin or no vector types selected
        FileNotFoundError: Credentials file not found or data not found on Google Drive
        GoogleAuthError: Authentication failed

    Example:
        >>> from pathlib import Path
        >>> paths = download_basin_vectors(42, Path("data/vectors"))
        >>> paths.keys()
        dict_keys(['catchments', 'rivers'])
    """
    if not include_catchments and not include_rivers:
        raise ValueError("At least one of include_catchments or include_rivers must be True")

    _validate_basin(basin)

    results: dict[str, Path] = {}

    if include_catchments:
        results["catchments"] = download_catchments(
            basin=basin,
            dest_dir=dest_dir,
            overwrite=overwrite,
            credentials_path=credentials_path,
            data_source=data_source,
        )

    if include_rivers:
        results["rivers"] = download_rivers(
            basin=basin,
            dest_dir=dest_dir,
            overwrite=overwrite,
            credentials_path=credentials_path,
            data_source=data_source,
        )

    return results


def list_available_files(
    folder_id: str | None = None,
    credentials_path: Path | None = None,
) -> list[dict]:
    """
    List all files in the MERIT-Basins Google Drive folder.

    This function is useful for discovering available basin files or debugging
    download issues.

    Args:
        folder_id: Google Drive folder ID. If None, uses MERIT_BASINS_FOLDER_ID env var.
        credentials_path: Path to service account JSON. If None, uses GOOGLE_APPLICATION_CREDENTIALS env var.

    Returns:
        List of file metadata dictionaries with keys:
        - id: File ID
        - name: Filename
        - mimeType: MIME type
        - size: File size in bytes (if available)

    Raises:
        FileNotFoundError: Credentials file not found
        GoogleAuthError: Authentication failed
        RuntimeError: Google Drive folder ID not configured

    Example:
        >>> files = list_available_files()
        >>> len(files)
        122
        >>> files[0]['name']
        'cat_pfaf_11_MERIT_Hydro_v07_Basins_v01.zip'
    """
    if folder_id is None:
        _validate_folder_id()
        folder_id = MERIT_BASINS_FOLDER_ID

    credentials = _get_credentials(credentials_path)
    service = _get_drive_service(credentials)

    logger.info(f"Listing files in folder ID: {folder_id}")

    try:
        # Query all files in the folder
        results = (
            service.files()
            .list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="files(id, name, mimeType, size)",
                pageSize=1000,  # Get up to 1000 files at once
            )
            .execute()
        )

        files = results.get("files", [])
        logger.info(f"Found {len(files)} files in folder")

        return files

    except Exception as e:
        logger.error(f"Error listing files: {e}")
        raise


def _validate_basin(basin: int) -> None:
    """
    Validate that basin code is in valid range.

    Args:
        basin: Basin code to validate

    Raises:
        ValueError: If basin code is invalid
    """
    # Pfafstetter Level 2 codes range from 11 to 91 (digits 1-9 only, no 0)
    if basin < 11 or basin > 99:
        raise ValueError(
            f"Invalid basin code: {basin}. Must be a valid Pfafstetter Level 2 code (11-91, no 0 in digits)"
        )

    # Check that both digits are 1-9 (no zeros in Pfafstetter codes)
    basin_str = f"{basin:02d}"
    if "0" in basin_str:
        raise ValueError(f"Invalid basin code: {basin}. Pfafstetter codes cannot contain 0")


def _validate_folder_id() -> None:
    """
    Validate that Google Drive folder ID is configured.

    Raises:
        RuntimeError: If MERIT_BASINS_FOLDER_ID is not set
    """
    if not MERIT_BASINS_FOLDER_ID:
        raise RuntimeError(
            "MERIT_BASINS_FOLDER_ID environment variable is not set. "
            "Please set it to the Google Drive folder ID containing MERIT-Basins data. "
            "Example: export MERIT_BASINS_FOLDER_ID='your_folder_id_here'"
        )


def _get_credentials(credentials_path: Path | None) -> Credentials | ServiceAccountCredentials:
    """
    Get Google API credentials from file or environment.

    Supports both service account credentials (for automation) and OAuth2 credentials.

    Args:
        credentials_path: Path to credentials JSON file. If None, uses GOOGLE_APPLICATION_CREDENTIALS env var.

    Returns:
        Google API credentials object

    Raises:
        FileNotFoundError: Credentials file not found
        GoogleAuthError: Authentication failed
    """
    # Determine credentials path
    if credentials_path is None:
        env_creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if not env_creds:
            raise FileNotFoundError(
                "No credentials provided. Either pass credentials_path or set "
                "GOOGLE_APPLICATION_CREDENTIALS environment variable."
            )
        credentials_path = Path(env_creds)
    else:
        credentials_path = Path(credentials_path)

    # Check that file exists
    if not credentials_path.exists():
        raise FileNotFoundError(f"Credentials file not found: {credentials_path}")

    logger.debug(f"Loading credentials from: {credentials_path}")

    # Try to load as service account credentials (most common for automation)
    try:
        credentials = ServiceAccountCredentials.from_service_account_file(
            str(credentials_path),
            scopes=["https://www.googleapis.com/auth/drive.readonly"],
        )
        logger.debug("Loaded service account credentials")
        return credentials
    except Exception as e:
        logger.debug(f"Not a service account credential file: {e}")
        raise GoogleAuthError(
            f"Failed to load credentials from {credentials_path}. Ensure it is a valid service account JSON file."
        ) from e


@lru_cache(maxsize=1)
def _get_drive_service(credentials: Credentials | ServiceAccountCredentials):
    """
    Build Google Drive API service.

    This function is cached to avoid rebuilding the service on every call.

    Args:
        credentials: Google API credentials

    Returns:
        Google Drive API service object
    """
    logger.debug("Building Google Drive API service")
    service = build("drive", "v3", credentials=credentials, cache_discovery=False)
    return service


def _find_file_id(service, folder_id: str, filename: str) -> str | None:
    """
    Find file ID by name in a Google Drive folder.

    Args:
        service: Google Drive API service
        folder_id: Folder ID to search in
        filename: Name of file to find

    Returns:
        File ID if found, None otherwise
    """
    logger.debug(f"Searching for file: {filename} in folder {folder_id}")

    try:
        # Query for file by name in folder
        query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
        results = (
            service.files()
            .list(
                q=query,
                fields="files(id, name)",
                pageSize=10,
            )
            .execute()
        )

        files = results.get("files", [])

        if not files:
            logger.warning(f"File not found: {filename}")
            return None

        if len(files) > 1:
            logger.warning(f"Multiple files found with name {filename}, using first one")

        file_id = files[0]["id"]
        logger.debug(f"Found file ID: {file_id}")
        return file_id

    except Exception as e:
        logger.error(f"Error searching for file: {e}")
        raise


def _download_file(
    service,
    file_id: str,
    dest_path: Path,
    progress_callback: Callable[[int, int], None] | None = None,
) -> None:
    """
    Download a file from Google Drive.

    Args:
        service: Google Drive API service
        file_id: ID of file to download
        dest_path: Path to save the file
        progress_callback: Optional callback(bytes_downloaded, total_bytes)

    Raises:
        Exception: Download failed
    """
    logger.debug(f"Downloading file ID {file_id} to {dest_path}")

    try:
        # Request file download
        request = service.files().get_media(fileId=file_id)

        # Create file handle
        fh = io.BytesIO()

        # Create downloader
        downloader = MediaIoBaseDownload(fh, request, chunksize=CHUNK_SIZE)

        # Get file metadata for progress tracking
        try:
            file_metadata = service.files().get(fileId=file_id, fields="size,name").execute()
            total_size = int(file_metadata.get("size", 0))
            filename = file_metadata.get("name", "unknown")
        except Exception:
            total_size = 0
            filename = dest_path.name

        # Set up progress bar if no callback provided
        if progress_callback is None and total_size > 0:
            progress_bar = tqdm(
                total=total_size,
                unit="B",
                unit_scale=True,
                desc=filename,
            )
        else:
            progress_bar = None

        # Download file in chunks
        done = False
        while not done:
            status, done = downloader.next_chunk()

            if status:
                bytes_downloaded = int(status.resumable_progress)

                if progress_callback:
                    progress_callback(bytes_downloaded, total_size)
                elif progress_bar:
                    progress_bar.n = bytes_downloaded
                    progress_bar.refresh()

        if progress_bar:
            progress_bar.close()

        # Write to file
        logger.debug(f"Writing downloaded content to {dest_path}")
        with open(dest_path, "wb") as f:
            f.write(fh.getvalue())

        logger.info(f"Successfully downloaded {filename}")

    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        raise


def _extract_zip(zip_path: Path, extract_dir: Path) -> None:
    """
    Extract a ZIP file to a directory.

    Args:
        zip_path: Path to ZIP file
        extract_dir: Directory to extract to

    Raises:
        zipfile.BadZipFile: Invalid ZIP file
    """
    logger.debug(f"Extracting {zip_path} to {extract_dir}")

    extract_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(extract_dir)

    logger.info(f"Extracted {len(list(extract_dir.iterdir()))} files to {extract_dir}")


def _download_shapefile_components(
    service,
    folder_id: str,
    source_base: str,
    dest_dir: Path,
    target_base: str,
    overwrite: bool,
) -> Path:
    """
    Download individual shapefile components from Google Drive.

    Downloads .shp, .dbf, .shx (required) and .prj, .cpg (optional) files.
    Renames files to strip the _bugfix1 suffix for downstream compatibility.

    Args:
        service: Google Drive API service
        folder_id: Google Drive folder ID containing the files
        source_base: Base filename on Google Drive (e.g., "cat_pfaf_42_..._bugfix1")
        dest_dir: Directory to save files
        target_base: Target base filename (e.g., "cat_pfaf_42_..." without _bugfix1)
        overwrite: If True, re-download even if files exist

    Returns:
        Path to directory containing downloaded shapefile components

    Raises:
        FileNotFoundError: Required shapefile components not found on Google Drive
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    downloaded_files: list[Path] = []
    missing_required: list[str] = []

    for ext in SHAPEFILE_EXTENSIONS:
        source_filename = f"{source_base}{ext}"
        target_path = dest_dir / f"{target_base}{ext}"

        # Skip if exists and not overwriting
        if target_path.exists() and not overwrite:
            logger.debug(f"File already exists: {target_path}")
            downloaded_files.append(target_path)
            continue

        # Find file on Google Drive
        file_id = _find_file_id(service, folder_id, source_filename)

        if file_id is None:
            if ext in SHAPEFILE_EXTENSIONS_REQUIRED:
                missing_required.append(source_filename)
            else:
                logger.debug(f"Optional shapefile component not found: {source_filename}")
            continue

        # Download with retries
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info(
                    f"Downloading {source_filename} (attempt {attempt}/{MAX_RETRIES})"
                )
                _download_file(service, file_id, target_path)
                downloaded_files.append(target_path)
                break
            except Exception as e:
                if attempt < MAX_RETRIES:
                    logger.warning(
                        f"Download attempt {attempt} failed: {e}. Retrying in {RETRY_DELAY}s..."
                    )
                    time.sleep(RETRY_DELAY)
                else:
                    logger.error(f"Download failed after {MAX_RETRIES} attempts: {e}")
                    # Clean up partially downloaded files on failure
                    for f in downloaded_files:
                        if f.exists():
                            f.unlink()
                    raise

    # Check for missing required files
    if missing_required:
        # Clean up any files that were downloaded
        for f in downloaded_files:
            if f.exists():
                f.unlink()
        raise FileNotFoundError(
            f"Required shapefile components not found on Google Drive: {missing_required}. "
            f"Check folder ID: {folder_id}"
        )

    logger.info(
        f"Successfully downloaded {len(downloaded_files)} shapefile components to {dest_dir}"
    )
    return dest_dir


def _download_and_extract(
    filename: str,
    dest_dir: Path,
    extract_dir_name: str,
    overwrite: bool,
    credentials_path: Path | None,
) -> Path:
    """
    Download a ZIP file from Google Drive and extract it.

    This is a helper function that encapsulates the common download-and-extract workflow.

    Args:
        filename: Name of file to download (e.g., "cat_pfaf_42_MERIT_Hydro_v07_Basins_v01.zip")
        dest_dir: Directory to save extracted files
        extract_dir_name: Name of subdirectory to extract to
        overwrite: If True, re-download even if files exist
        credentials_path: Path to service account JSON

    Returns:
        Path to directory containing extracted files

    Raises:
        FileNotFoundError: File not found on Google Drive or credentials missing
        GoogleAuthError: Authentication failed
    """
    # Create destination directory
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Paths for ZIP file and extracted directory
    zip_path = dest_dir / filename
    extract_dir = dest_dir / extract_dir_name

    # Check if already extracted
    if extract_dir.exists() and not overwrite:
        logger.info(f"Files already extracted: {extract_dir}")
        return extract_dir

    # Check if ZIP already downloaded
    if zip_path.exists() and not overwrite:
        logger.info(f"ZIP file already exists: {zip_path}, extracting...")
        _extract_zip(zip_path, extract_dir)
        return extract_dir

    # Get credentials and service
    credentials = _get_credentials(credentials_path)
    service = _get_drive_service(credentials)

    # Find file on Google Drive
    file_id = _find_file_id(service, MERIT_BASINS_FOLDER_ID, filename)

    if file_id is None:
        raise FileNotFoundError(
            f"File not found on Google Drive: {filename}. "
            f"Check that the basin code is valid and the file exists in folder {MERIT_BASINS_FOLDER_ID}"
        )

    # Download with retries
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f"Downloading {filename} from Google Drive (attempt {attempt}/{MAX_RETRIES})")
            _download_file(service, file_id, zip_path)
            break
        except Exception as e:
            if attempt < MAX_RETRIES:
                logger.warning(f"Download attempt {attempt} failed: {e}. Retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
            else:
                logger.error(f"Download failed after {MAX_RETRIES} attempts: {e}")
                # Clean up partial download
                if zip_path.exists():
                    zip_path.unlink()
                raise

    # Extract ZIP file
    try:
        _extract_zip(zip_path, extract_dir)

        # Optionally remove ZIP file after successful extraction to save space
        # Uncomment if you want to delete ZIPs after extraction:
        # zip_path.unlink()
        # logger.debug(f"Removed ZIP file: {zip_path}")

        return extract_dir

    except Exception as e:
        logger.error(f"Error extracting ZIP file: {e}")
        # Clean up failed extraction
        if extract_dir.exists():
            import shutil

            shutil.rmtree(extract_dir)
        raise

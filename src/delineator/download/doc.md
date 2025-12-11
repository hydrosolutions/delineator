---
module: download
description: Programmatic download of MERIT-Hydro rasters and MERIT-Basins vectors for watershed delineation.
---

# Download Module

This module provides utilities to programmatically download all data required for watershed delineation from multiple sources:

- MERIT-Hydro rasters (flow direction, flow accumulation) from mghydro.com
- MERIT-Basins vectors (catchments, rivers) from Google Drive (ReachHydro/Princeton)
- Simplified catchments from mghydro.com

The module handles automatic basin selection from bounding boxes, batch downloads across multiple basins, retry logic, progress tracking, and comprehensive error reporting.

## Files

- `__init__.py` - Module exports and public API surface
- `basin_selector.py` - Spatial selection of basins by bounding box or validation of basin codes
- `http_client.py` - HTTP downloads from mghydro.com (rasters, simplified catchments)
- `gdrive_client.py` - Google Drive downloads for MERIT-Basins vectors (requires credentials)
- `downloader.py` - Main orchestrator coordinating all downloads with error handling

## Architecture

The module is organized in layers:

1. **Data Source Clients** (`http_client.py`, `gdrive_client.py`) - Low-level download functions for specific data sources
2. **Basin Selection** (`basin_selector.py`) - Spatial operations to determine which basins to download
3. **Orchestrator** (`downloader.py`) - High-level interface coordinating downloads across basins and sources

## Key Interfaces

### Basin Selection

```python
def get_basins_for_bbox(
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    basins_shapefile: str | Path | None = None,
) -> list[int]
```

Get Pfafstetter Level 2 basin codes intersecting a bounding box. Uses spatial intersection with the Level 2 basins shapefile (default: `data/shp/basins_level2/merit_hydro_vect_level2.shp`).

```python
def get_all_basin_codes() -> list[int]
```

Return all 61 valid Pfafstetter Level 2 basin codes (11-91, excluding codes with 0 digits).

```python
def validate_basin_codes(codes: list[int]) -> list[int]
```

Validate that basin codes exist in the basins shapefile. Raises `ValueError` if any codes are invalid.

### HTTP Downloads (mghydro.com)

```python
def download_raster(
    basin: int,
    raster_type: str,  # "flowdir" or "accum"
    dest_dir: Path,
    overwrite: bool = False,
    progress_callback: Callable[[int, int], None] | None = None,
) -> Path
```

Download a single raster file (flow direction or accumulation) for a basin. Includes automatic retry logic (3 attempts) and progress tracking.

```python
def download_simplified_catchments(
    dest_dir: Path,
    overwrite: bool = False,
    progress_callback: Callable[[int, int], None] | None = None,
) -> Path
```

Download the global simplified catchments ZIP file (lightweight for fast spatial queries).

```python
def download_basin_rasters(
    basin: int,
    dest_dir: Path,
    include_flowdir: bool = True,
    include_accum: bool = True,
    overwrite: bool = False,
) -> dict[str, Path]
```

Download both raster types for a basin. Returns dict mapping raster type to file path.

### Google Drive Downloads (MERIT-Basins)

Requires Google Drive credentials (service account). Supports two data versions:

- **bugfix1** (default): Individual shapefile components with important bug fixes
- **v1.0**: Original ZIP archives

```python
from delineator.download import DataSource

def download_catchments(
    basin: int,
    dest_dir: Path,
    overwrite: bool = False,
    credentials_path: Path | None = None,
    data_source: DataSource | None = None,  # Default: bugfix1
) -> Path
```

Download catchment shapefiles for a basin. Returns path to extracted directory. The `data_source` parameter selects which version to download.

```python
def download_rivers(
    basin: int,
    dest_dir: Path,
    overwrite: bool = False,
    credentials_path: Path | None = None,
    data_source: DataSource | None = None,  # Default: bugfix1
) -> Path
```

Download river flowlines shapefiles for a basin. Returns path to extracted directory.

```python
def download_basin_vectors(
    basin: int,
    dest_dir: Path,
    include_catchments: bool = True,
    include_rivers: bool = True,
    overwrite: bool = False,
    credentials_path: Path | None = None,
    data_source: DataSource | None = None,  # Default: bugfix1
) -> dict[str, Path]
```

Download both vector types for a basin. Returns dict mapping vector type to directory path.

```python
def list_available_files(
    folder_id: str | None = None,
    credentials_path: Path | None = None,
) -> list[dict]
```

List all files in the MERIT-Basins Google Drive folder. Useful for discovery and debugging.

### Main Orchestrator

```python
def download_data(
    bbox: tuple[float, float, float, float] | None = None,
    basins: list[int] | None = None,
    output_dir: Path | str = "data",
    include_rasters: bool = True,
    include_vectors: bool = True,
    include_simplified: bool = True,
    overwrite: bool = False,
    gdrive_credentials: Path | None = None,
) -> DownloadResult
```

Main entry point for downloading all data needed for delineation. Either `bbox` or `basins` must be provided. Automatically:

- Determines which basins to download (from bbox or validates provided codes)
- Creates output directory structure
- Downloads rasters, vectors, and simplified catchments as requested
- Collects and reports errors
- Returns comprehensive results

```python
@dataclass
class DownloadResult:
    basins_downloaded: list[int]
    rasters: dict[int, dict[str, Path]]  # basin -> {flowdir: path, accum: path}
    vectors: dict[int, dict[str, Path]]  # basin -> {catchments: path, rivers: path}
    simplified_catchments: Path | None
    errors: list[str]

    @property
    def success(self) -> bool:
        """Check if download completed without errors."""
```

Dataclass containing all download results and errors.

## Data Sources

| Data Type | Source | URL Pattern |
|-----------|--------|-------------|
| Flow Direction Rasters | mghydro.com | `https://mghydro.com/watersheds/rasters/flow_dir_basins/flowdir{basin}.tif` |
| Flow Accumulation Rasters | mghydro.com | `https://mghydro.com/watersheds/rasters/accum_basins/accum{basin}.tif` |
| Simplified Catchments | mghydro.com | `https://mghydro.com/watersheds/share/catchments_simplified.zip` |
| Catchment Shapefiles (v1.0) | Google Drive (ReachHydro) | `cat_pfaf_{basin:02d}_MERIT_Hydro_v07_Basins_v01.zip` |
| Catchment Shapefiles (bugfix1) | Google Drive (ReachHydro) | `cat_pfaf_{basin:02d}_MERIT_Hydro_v07_Basins_v01_bugfix1.{shp,dbf,shx,prj,cpg}` |
| River Shapefiles (v1.0) | Google Drive (ReachHydro) | `riv_pfaf_{basin:02d}_MERIT_Hydro_v07_Basins_v01.zip` |
| River Shapefiles (bugfix1) | Google Drive (ReachHydro) | `riv_pfaf_{basin:02d}_MERIT_Hydro_v07_Basins_v01_bugfix1.{shp,dbf,shx,prj,cpg}` |

### MERIT-Basins Data Versions

The module supports two versions of MERIT-Basins vector data:

| Version | Format | Description | Default |
|---------|--------|-------------|---------|
| **bugfix1** | Individual files (.shp, .dbf, .shx, .prj, .cpg) | Contains important bug fixes. Recommended. | Yes |
| **v1.0** | ZIP archives | Original release. | No |

**Note:** When downloading bugfix1 data, the files are automatically renamed to strip the `_bugfix1` suffix for compatibility with downstream code. The output files will match the v1.0 naming convention (e.g., `cat_pfaf_42_MERIT_Hydro_v07_Basins_v01.shp`).

### Selecting Data Version

```python
from delineator.download import download_catchments, DataSource

# Use bugfix1 (default)
download_catchments(basin=42, dest_dir=Path("data/vectors"))

# Explicitly specify bugfix1
download_catchments(basin=42, dest_dir=Path("data/vectors"), data_source=DataSource.BUGFIX1)

# Use original v1.0 ZIP format
download_catchments(basin=42, dest_dir=Path("data/vectors"), data_source=DataSource.V1_ZIP)
```

Or set via environment variable:

```bash
export MERIT_BASINS_VERSION="bugfix1"  # or "v1.0"
```

### Data Organization

The MERIT-Hydro dataset is organized into 61 continental-scale basins identified by Pfafstetter Level 2 codes (2-digit integers from 11 to 91, excluding codes with 0 digits).

MERIT-Basins vectors are hosted by ReachHydro/Princeton at: <https://www.reachhydro.org/home/params/merit-basins>

## Environment Variables

### Required for Google Drive Downloads

- `GOOGLE_APPLICATION_CREDENTIALS` - Path to service account JSON file

### Optional

- `MERIT_BASINS_VERSION` - Data version to download: `"bugfix1"` (default) or `"v1.0"`
- `MERIT_BASINS_FOLDER_ID` - Override the default Google Drive folder ID for the selected version. If not set, uses built-in folder IDs:
  - bugfix1: `1owkvZQBMZbvRv3V4Ff3xQPEgmAC48vJo`
  - v1.0: `1uCQFmdxFbjwoT9OYJxw-pXaP8q_GYH1a`

The module uses these if set, otherwise requires explicit paths:

- Default basins shapefile: `data/shp/basins_level2/merit_hydro_vect_level2.shp`

## Output Directory Structure

The `download_data()` function creates the following structure:

```
output_dir/
├── raster/
│   ├── flowdir_basins/
│   │   └── flowdir{basin}.tif
│   └── accum_basins/
│       └── accum{basin}.tif
└── shp/
    ├── merit_catchments/
    │   ├── cat_pfaf_{basin}_MERIT_Hydro_v07_Basins_v01.shp
    │   ├── cat_pfaf_{basin}_MERIT_Hydro_v07_Basins_v01.shx
    │   ├── cat_pfaf_{basin}_MERIT_Hydro_v07_Basins_v01.dbf
    │   └── cat_pfaf_{basin}_MERIT_Hydro_v07_Basins_v01.prj
    ├── merit_rivers/
    │   ├── riv_pfaf_{basin}_MERIT_Hydro_v07_Basins_v01.shp
    │   └── [similar to catchments]
    └── catchments_simplified/
        └── catchments_simplified.zip
```

Note: Shapefile components are stored directly in `merit_catchments/` and `merit_rivers/` directories (no subdirectories per basin).

## Usage Examples

### Download data for a region (Iceland)

```python
from delineator.download import download_data

# Download all data types for Iceland
result = download_data(
    bbox=(-25, 63, -13, 67),  # min_lon, min_lat, max_lon, max_lat
    output_dir="data",
    include_rasters=True,
    include_vectors=True,
    include_simplified=True,
)

print(f"Downloaded basins: {result.basins_downloaded}")
print(f"Success: {result.success}")
if result.errors:
    print(f"Errors: {result.errors}")
```

### Download only rasters (no Google Drive needed)

```python
from delineator.download import download_data

# Download only rasters, skip vectors to avoid needing GDrive credentials
result = download_data(
    bbox=(-25, 63, -13, 67),
    output_dir="data",
    include_rasters=True,
    include_vectors=False,  # Skip Google Drive downloads
    include_simplified=True,
)
```

### Download specific basins

```python
from delineator.download import download_data

# Download data for specific basins (e.g., Amazon region)
result = download_data(
    basins=[61, 62, 63],  # Explicit basin codes
    output_dir="data",
    include_rasters=True,
    include_vectors=True,
)
```

### Low-level: Download individual files

```python
from pathlib import Path
from delineator.download import download_raster, download_catchments

# Download single raster
flowdir_path = download_raster(
    basin=42,
    raster_type="flowdir",
    dest_dir=Path("data/raster"),
)

# Download catchments with custom credentials
catchments_dir = download_catchments(
    basin=42,
    dest_dir=Path("data/vectors"),
    credentials_path=Path("/path/to/service-account.json"),
)
```

### Find basins for a region

```python
from delineator.download import get_basins_for_bbox, get_all_basin_codes

# Get basins for Iceland
basins = get_basins_for_bbox(
    min_lon=-25, min_lat=63, max_lon=-13, max_lat=67
)
print(f"Found basins: {basins}")  # [41]

# Get all available basins
all_basins = get_all_basin_codes()
print(f"Total basins: {len(all_basins)}")  # 61
```

### List available files on Google Drive

```python
from delineator.download import list_available_files

# Debug: List all files in the MERIT-Basins folder
files = list_available_files()
for file in files[:5]:  # Show first 5
    print(f"{file['name']} - {file['size']} bytes")
```

## Error Handling

The module uses comprehensive error handling:

- **HTTP Downloads**: Automatic retry with exponential backoff (3 attempts, 2s delay)
- **Google Drive**: Authentication errors raised immediately; download errors retried
- **Batch Operations**: Individual failures collected as errors but don't stop other downloads
- **Validation**: Invalid basin codes, bounding boxes, and credentials are validated early

All errors are collected in `DownloadResult.errors` and logged at appropriate levels.

## Configuration

### HTTP Downloads

- Chunk size: 8KB
- Timeout: 3600s (1 hour)
- Max retries: 3
- Retry delay: 2s

### Google Drive Downloads

- Chunk size: 8MB
- Max retries: 3
- Retry delay: 2s
- Authentication: Service account (read-only access)

## Logging

The module uses Python's `logging` module extensively. Configure logging level to control verbosity:

```python
import logging
logging.basicConfig(level=logging.INFO)

# For more detail:
logging.basicConfig(level=logging.DEBUG)
```

## Dependencies

- `httpx` - HTTP client for mghydro.com downloads
- `geopandas` - Spatial operations for basin selection
- `shapely` - Geometry operations
- `google-auth`, `google-api-python-client` - Google Drive authentication and API
- `tqdm` - Progress bars for downloads

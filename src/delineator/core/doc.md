---
module: core
description: Core utilities for watershed delineation including data availability checking, MERIT-Hydro raster operations, polygon processing, and geocoding.
---

# Core Module

This module contains core functionality and utilities needed throughout the delineator package for watershed delineation operations.

## Files

- `__init__.py` - Module exports and public API surface
- `data_check.py` - Data availability checker with optional auto-download
- `merit.py` - MERIT-Hydro raster operations for detailed watershed delineation
- `dissolve.py` - Efficient polygon dissolve and hole-filling operations
- `country.py` - Country extraction via offline reverse geocoding
- `output_writer.py` - Output file writing for watersheds and failures (GeoPackage/Shapefile)
- `delineate.py` - Main delineation algorithm and data structures

## Key Interfaces

### Data Availability Checking

```python
@dataclass
class DataAvailability:
    """Results from a data availability check."""
    available_basins: list[int]
    missing_basins: list[int]
    missing_files: list[Path]

    @property
    def all_available(self) -> bool:
        """Check if all requested data is available."""
```

Dataclass containing availability status for requested basins.

```python
def check_data_availability(
    basins: list[int],
    data_dir: Path,
    check_rasters: bool = True,
    check_vectors: bool = True,
    check_simplified: bool = True,
) -> DataAvailability
```

Check if required MERIT data files exist locally. Validates presence of:
- Flow direction and accumulation rasters (if `check_rasters=True`)
- Catchment and river shapefiles (if `check_vectors=True`)
- Simplified catchments directory (if `check_simplified=True`)

Returns a `DataAvailability` object with lists of available/missing basins and specific missing files.

```python
def ensure_data_available(
    basins: list[int],
    data_dir: Path,
    auto_download: bool = True,
    gdrive_credentials: Path | None = None,
) -> DataAvailability
```

Check data and optionally download missing data. First checks if all required data files exist. If any files are missing and `auto_download=True`, automatically downloads the missing data using the download module. After download (if triggered), re-checks availability and returns final status.

```python
def get_required_basins(outlets: list[tuple[float, float]]) -> list[int]
```

Given a list of (latitude, longitude) outlet coordinates, determine which Pfafstetter Level 2 basins are needed. Computes a bounding box around all outlet points and uses the basin selector from the download module to determine which basins intersect that bounding box.

### MERIT-Hydro Raster Operations

```python
def split_catchment(
    basin: int,
    lat: float,
    lng: float,
    catchment_poly: Polygon,
    is_single_catchment: bool,
    upstream_area: float | None,
    fdir_dir: Path,
    accum_dir: Path,
) -> tuple[Polygon | None, float | None, float | None]
```

Perform detailed pixel-scale raster-based delineation within a single unit catchment. This implements the hybrid delineation method that only uses raster operations in the most downstream catchment, significantly reducing memory usage and processing time.

Returns a tuple of:
- Delineated polygon (or None if failed)
- Snapped latitude (or None if failed)
- Snapped longitude (or None if failed)

The function:
1. Loads windowed flow direction and accumulation rasters
2. Masks rasters to the catchment polygon
3. Snaps outlet point to nearest stream using dynamic threshold
4. Performs raster-based delineation with pysheds
5. Converts result to polygon geometry

### Polygon Dissolve Operations

```python
def dissolve_geopandas(df: gpd.GeoDataFrame) -> gpd.GeoSeries
```

Fast dissolve operation that merges multiple polygons into a single boundary. Much faster than standard GeoPandas dissolve() by using a clip-box approach.

```python
def fill_geopandas(gdf: gpd.GeoDataFrame, area_max: float) -> gpd.GeoSeries
```

Fill holes in all geometries in a GeoDataFrame below a size threshold.

```python
def close_holes(poly: Polygon | MultiPolygon, area_max: float) -> Polygon | MultiPolygon
```

Close polygon holes by removing interior rings below a specified area threshold. Set `area_max=0` to fill all holes.

### Country Extraction

```python
def get_country(lat: float, lng: float) -> str
```

Get full country name for coordinates using offline reverse geocoding via the `reverse_geocoder` library.

## Expected File Paths

The data checker validates the following file structure:

```
data_dir/
├── raster/
│   ├── flowdir_basins/
│   │   └── flowdir{basin}.tif
│   └── accum_basins/
│       └── accum{basin}.tif
└── shp/
    ├── merit_catchments/
    │   └── cat_pfaf_{basin}_MERIT_Hydro_v07_Basins_v01.shp
    ├── merit_rivers/
    │   └── riv_pfaf_{basin}_MERIT_Hydro_v07_Basins_v01.shp
    └── catchments_simplified/
        └── [any files]
```

## Usage Examples

### Check if data exists

```python
from pathlib import Path
from delineator.core import check_data_availability

# Check if all required data exists for basins
availability = check_data_availability(
    basins=[41, 42],
    data_dir=Path("data")
)

if availability.all_available:
    print("All data present, ready for delineation!")
else:
    print(f"Missing basins: {availability.missing_basins}")
    print(f"Missing files: {len(availability.missing_files)}")
```

### Auto-download missing data

```python
from pathlib import Path
from delineator.core import ensure_data_available

# Check and auto-download if needed
availability = ensure_data_available(
    basins=[41, 42],
    data_dir=Path("data"),
    auto_download=True,
    gdrive_credentials=Path("credentials.json")
)

if availability.all_available:
    print("All data ready (downloaded if needed)!")
```

### Determine required basins from outlets

```python
from delineator.core import get_required_basins, ensure_data_available

# Outlets in Iceland
outlets = [
    (64.1, -21.9),  # Near Reykjavik
    (65.7, -18.1),  # North Iceland
]

# Determine which basins are needed
basins = get_required_basins(outlets)
print(f"Need basins: {basins}")  # [41]

# Ensure all required data is available
availability = ensure_data_available(
    basins=basins,
    data_dir=Path("data"),
    auto_download=True
)
```

### Workflow integration

```python
from pathlib import Path
from delineator.core import get_required_basins, ensure_data_available

def prepare_delineation_data(
    outlet_coordinates: list[tuple[float, float]],
    data_dir: Path = Path("data"),
    credentials: Path | None = None,
) -> bool:
    """
    Prepare all data needed for delineation.

    Returns True if all data is available, False otherwise.
    """
    # Determine which basins are needed
    basins = get_required_basins(outlet_coordinates)

    # Ensure data is available (download if needed)
    availability = ensure_data_available(
        basins=basins,
        data_dir=data_dir,
        auto_download=True,
        gdrive_credentials=credentials,
    )

    return availability.all_available

# Use in workflow
outlets = [(64.1, -21.9), (65.7, -18.1)]
if prepare_delineation_data(outlets):
    print("Ready for delineation!")
else:
    print("Failed to acquire all required data")
```

## Integration with Download Module

The data checker integrates seamlessly with the download module:

- `get_required_basins()` uses `download.get_basins_for_bbox()` for basin selection
- `ensure_data_available()` uses `download.download_data()` for auto-download
- File paths match the output structure created by `download_data()`

This ensures consistent file organization across the entire delineator package.

## Error Handling

The module handles errors gracefully:

- **Invalid coordinates**: `get_required_basins()` validates lat/lon ranges and raises `ValueError` for invalid inputs
- **Empty outlet list**: Raises `ValueError` immediately
- **Download failures**: Logged and tracked, but don't raise exceptions - availability status reflects actual state
- **Missing files**: Recorded in `DataAvailability.missing_files` for detailed diagnostics

## Logging

The module uses Python's `logging` module. Configure logging level to control verbosity:

```python
import logging
logging.basicConfig(level=logging.INFO)

# For more detail:
logging.basicConfig(level=logging.DEBUG)
```

Log messages include:
- INFO: Summary of checks and download operations
- DEBUG: Individual file checks, bounding box calculations
- WARNING: Missing data when auto-download is disabled
- ERROR: Download failures

### Output Writing

```python
class OutputFormat(str, Enum):
    """Supported output file formats."""
    SHAPEFILE = "shp"
    GEOPACKAGE = "gpkg"  # Default
```

```python
class OutputWriter:
    """Handles output file writing for delineation results."""

    def __init__(
        self,
        output_dir: Path,
        output_format: OutputFormat = OutputFormat.GEOPACKAGE,
    ) -> None: ...
```

Key methods:
- `write_region_output(region_name, watersheds, mode="w")` - Write watersheds to GeoPackage/Shapefile
- `check_output_exists(region_name)` - Check if output file exists for a region
- `read_existing_gauge_ids(region_name)` - Load gauge_ids from existing output (for resume)
- `load_failed_gauge_ids()` - Load gauge_ids from FAILED.csv (for --skip-failed)
- `record_failure(region_name, gauge_id, lat, lng, error)` - Record a failed delineation
- `finalize()` - Write FAILED.csv

Output structure (Hive-partitioned):
```
output_dir/
├── REGION_NAME={name}/
│   └── data_type=geopackage/  # or data_type=shapefiles
│       └── {name}.gpkg        # or {name}_shapes.shp
└── FAILED.csv
```

## Dependencies

- `pathlib` - File path operations
- `dataclasses` - Structured data containers
- `logging` - Diagnostic logging
- `fiona` - Efficient reading of gauge_ids without loading geometries
- `geopandas` - GeoDataFrame operations
- `delineator.download` - Basin selection and data download

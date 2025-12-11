# Delineator

Fast, accurate watershed delineation for any point on Earth's land surface using hybrid vector/raster methods with MERIT-Hydro and MERIT-Basins datasets.

**Citation:** DOI [10.5281/zenodo.7314287](https://zenodo.org/badge/latestdoi/564865701)

**Online Demo:** [https://mghydro.com/watersheds/](https://mghydro.com/watersheds/) (free, easy to use, good for most users)

## Overview

Delineator is a Python CLI tool for watershed delineation that combines:
- High-resolution MERIT-Hydro raster data (flow direction and accumulation)
- MERIT-Basins vector data (unit catchments and river networks)
- Hybrid vector/raster algorithms for optimal speed and accuracy

The tool automatically downloads required data, handles large-scale batch processing, and outputs results in standard GIS formats.

## Installation

### With uv (recommended)
```bash
git clone https://github.com/your-org/delineator.git
cd delineator
uv sync
```

### With pip
```bash
git clone https://github.com/your-org/delineator.git
cd delineator
pip install -e .
```

**Requirements:** Python 3.12+

## Quick Start

### 1. Create an outlets file (TOML format)

```toml
# outlets.toml
[[outlets]]
gauge_id = "usgs_12345678"
lat = 47.6062
lng = -122.3321
gauge_name = "Green River near Seattle, WA"  # optional
```

### 2. Create a master configuration file

```toml
# config.toml
[settings]
output_dir = "./output"
max_fails = 100  # optional

[[regions]]
name = "my_region"
outlets = "outlets.toml"
```

### 3. Run delineation

```bash
delineator run config.toml
```

The tool will automatically:
- Determine required MERIT-Hydro basins from outlet coordinates
- Download missing data
- Delineate watersheds
- Output shapefiles in `output/region=my_region/`

## CLI Commands

### Run watershed delineation
```bash
delineator run config.toml
delineator run config.toml --dry-run              # Validate config without processing
delineator run config.toml -o ./output            # Override output directory
delineator run config.toml --max-fails 10         # Stop after 10 failures
delineator run config.toml --no-download          # Fail if data is missing (no auto-download)
```

### Download MERIT-Hydro data
```bash
# Download by bounding box (min_lon,min_lat,max_lon,max_lat)
delineator download --bbox -125,45,-120,50 -o data/

# Download specific basins by Pfafstetter Level 2 code
delineator download --basins 71,72,73 -o data/

# Download only rasters (no Google Drive credentials needed)
delineator download --bbox -125,45,-120,50 --rasters-only

# Preview what would be downloaded
delineator download --bbox -125,45,-120,50 --dry-run
```

### List available basins
```bash
delineator list-basins
```

Displays all 61 Pfafstetter Level 2 basin codes grouped by continent.

## Configuration

### Master Config (delineate.toml)

```toml
[settings]
output_dir = "./output"      # Required: base output directory
max_fails = 100              # Optional: stop after N failures (default: unlimited)

[[regions]]
name = "region_name"         # Required: used for hive partitioning (region=name/)
outlets = "outlets.toml"     # Required: path to outlets file
```

### Outlets File Format

```toml
[[outlets]]
gauge_id = "unique_id"       # Required: unique identifier (used in output filenames)
lat = 47.6062                # Required: latitude (decimal degrees, EPSG:4326)
lng = -122.3321              # Required: longitude (decimal degrees, EPSG:4326)
gauge_name = "River Name"    # Optional: descriptive name
```

See `examples/` directory for complete configuration examples.

## Output Structure

```
output/
├── region=my_region/
│   └── my_region.shp        # Shapefile with all watersheds for this region
└── FAILED.csv               # Log of failed outlets (if any)
```

Each watershed shapefile includes attributes:
- `gauge_id`: Unique identifier
- `gauge_name`: Descriptive name (if provided)
- `area`: Watershed area (km²)
- `country`: Country code
- Geometry: Watershed polygon

## Data Sources

The tool uses data from:
- **MERIT-Hydro**: High-resolution flow direction and accumulation rasters (3-arcsecond, ~90m resolution)
- **MERIT-Basins**: Vector unit catchments and river networks

Data is organized by Pfafstetter Level 2 basins (61 continental-scale basins worldwide). The tool automatically downloads required data on first use.

For manual download or offline use:
- Rasters: [https://mghydro.com/watersheds/rasters](https://mghydro.com/watersheds/rasters)
- Vectors: [https://www.reachhydro.org/home/params/merit-basins](https://www.reachhydro.org/home/params/merit-basins)

## Development

### Package Structure

```
src/delineator/
├── cli/          # Typer CLI (run, download, list-basins commands)
├── config/       # Pydantic configuration schema for TOML configs
├── core/         # Delineation logic (watershed algorithms, dissolve, raster ops)
└── download/     # MERIT-Hydro data download (HTTP and Google Drive)
```

### Running Tests
```bash
uv run pytest
```

### Formatting and Linting
```bash
uv run ruff format
uv run ruff check --fix
```

See `CLAUDE.md` for detailed development guidelines.

## License

MIT License. See LICENSE file for details.

## Citation

If you use this tool in research, please cite:

> Heberger, M. (2022). delineator: Fast watershed delineation using MERIT-Hydro (Version 1.0.0) [Software].
> Zenodo. https://doi.org/10.5281/zenodo.7314287

## Acknowledgments

Original author: Matthew Heberger

Built using:
- [MERIT-Hydro](http://hydro.iis.u-tokyo.ac.jp/~yamadai/MERIT_Hydro/) (Yamazaki et al., 2019)
- [MERIT-Basins](https://www.reachhydro.org/home/params/merit-basins) (Lin et al., 2021)
- [GeoPandas](https://geopandas.org/), [Shapely](https://shapely.readthedocs.io/), [pysheds](https://github.com/mdbartos/pysheds)

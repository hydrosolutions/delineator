# Delineator - Codebase Overview

## What is Delineator?

**Delineator** is a Python tool for fast, accurate watershed delineation at any point on Earth's land surface. Given GPS coordinates of watershed outlets (e.g., river gages, dam locations), it automatically generates precise watershed boundary polygons using a hybrid of vector and raster GIS methods.

The tool is built on top of two high-quality global datasets:

- **MERIT-Hydro**: 3-arcsecond resolution (~90m) hydrological data from University of Tokyo
- **MERIT-Basins**: Pre-computed river basins and stream networks from Princeton University

### Key Features

- **Dual-mode operation**: High-resolution (accurate) and low-resolution (fast) modes
- **Global coverage**: Works anywhere on Earth between 60°S and 85°N
- **Multiple output formats**: GeoPackage, GeoJSON, Shapefile, and others
- **Interactive web viewer**: Built-in HTML/JavaScript map for reviewing results
- **Batch processing**: Delineate multiple watersheds from a CSV file
- **Smart outlet snapping**: Automatically finds the nearest stream reach to your point
- **Area matching**: Can search for the correct stream based on expected watershed size

### Online Demo

A web-based version is available at: <https://mghydro.com/watersheds/>

---

## Project Structure

```
delineator/
├── delineate.py              # Main watershed delineation script
├── config.py                 # Configuration settings (edit before running)
├── main.py                   # Simple entry point
├── outlets_sample.csv        # Example outlet points (Iceland)
├── py/                       # Helper modules
│   ├── merit_detailed.py     # High-res raster processing
│   ├── fast_dissolve.py      # Polygon dissolve/merge operations
│   ├── mapper.py             # Interactive map generation
│   ├── raster_plots.py       # Debugging visualizations
│   ├── add_prj.py            # Projection file utilities
│   └── viewer_template.html  # Web map template
├── data/                     # Input data directories
│   ├── raster/               # Flow direction & accumulation grids
│   └── shp/                  # Vector catchments & rivers
├── doc/                      # Documentation and images
├── output/                   # Generated watershed files
└── map/                      # Generated web map files
```

---

## How It Works

### The Hybrid Approach

Delineator combines two complementary methods:

1. **Vector-based (fast)**: Merges pre-existing unit catchment polygons from MERIT-Basins
2. **Raster-based (precise)**: Uses flow direction grids to "split" the downstream-most catchment at the exact outlet location

### Workflow

1. **Input**: User provides CSV file with outlet coordinates (lat, lng)
2. **Snap to stream**: Finds the nearest river reach to each outlet point
3. **Trace upstream**: Identifies all upstream unit catchments that drain to the outlet
4. **Merge catchments**: Dissolves unit catchment polygons into a single watershed
5. **Refine boundary** (high-res mode): Uses flow direction rasters to clip the downstream catchment at the precise outlet
6. **Post-process**: Fills holes, simplifies boundaries (optional)
7. **Output**: Saves watershed polygons and creates interactive map

### Resolution Modes

**High-Resolution Mode** (`HIGH_RES = True`)

- More accurate, especially for small watersheds (<50,000 km²)
- Requires MERIT-Hydro raster data (flow direction + accumulation)
- Uses detailed raster analysis to split the outlet catchment
- Slower processing time

**Low-Resolution Mode** (`HIGH_RES = False` or large watersheds)

- Faster, suitable for large watersheds (>50,000 km²)
- Only requires vector data (unit catchments)
- Includes extra area downstream of the outlet (typically ~20 km²)
- Uses simplified catchment boundaries for speed

The script can automatically switch to low-res mode for watersheds above a size threshold (`LOW_RES_THRESHOLD` in config.py).

---

## Core Components

### 1. `delineate.py` - Main Script

The primary entry point that orchestrates the entire workflow:

- Reads outlet points from CSV
- Validates input data
- Loads vector data (catchments, rivers) from shapefiles or pickle files
- For each outlet:
  - Finds containing or nearest catchment
  - Optionally matches upstream area to expected size
  - Traces upstream network
  - Merges catchment polygons
  - Applies high-res refinement if enabled
  - Fills holes and simplifies boundaries
  - Exports results
- Generates interactive web map

**Key functions:**

- `validate()`: Checks CSV file format
- `load_data()`: Reads/caches spatial datasets
- `find_catchment()`: Locates outlet catchment
- `trace_upstream()`: Identifies contributing catchments
- `merge_catchments()`: Dissolves polygons

### 2. `config.py` - Settings

User-editable configuration file with all adjustable parameters:

**Data Paths:**

- `OUTLETS_CSV`: Input CSV file
- `MERIT_FDIR_DIR`, `MERIT_ACCUM_DIR`: Raster data locations
- `HIGHRES_CATCHMENTS_DIR`, `LOWRES_CATCHMENTS_DIR`: Vector catchment paths
- `RIVERS_DIR`: River flowline shapefiles
- `OUTPUT_DIR`: Where to save results

**Processing Options:**

- `HIGH_RES`: Enable high-resolution mode
- `LOW_RES_THRESHOLD`: Auto-switch size (km²)
- `SEARCH_DIST`: Outlet search radius (decimal degrees)
- `MATCH_AREAS`: Use area-matching feature
- `FILL`: Fill donut holes in watershed
- `FILL_THRESHOLD`: Max hole size to fill (pixels)
- `SIMPLIFY`: Simplify output boundaries
- `SIMPLIFY_TOLERANCE`: Simplification distance

**Output Options:**

- `OUTPUT_EXT`: File format (gpkg, geojson, shp)
- `MAKE_MAP`: Generate web viewer
- `MAP_RIVERS`: Include rivers on map

### 3. `py/merit_detailed.py` - High-Resolution Processing

Handles precise raster-based watershed delineation for the outlet catchment:

- Reads MERIT-Hydro flow direction and accumulation rasters
- Identifies the outlet pixel on the stream network
- Traces upstream contributing pixels using D8 flow direction
- Converts raster cells to polygon boundary
- Clips the downstream catchment at the outlet

This is the most computationally intensive part and is only used when `HIGH_RES = True`.

### 4. `py/fast_dissolve.py` - Polygon Operations

Efficient geometric operations on watershed polygons:

- `dissolve_geopandas()`: Merges multiple catchment polygons into one watershed
- `fill_geopandas()`: Removes donut holes (internal gaps)

Uses unary union operations from Shapely/GEOS for fast processing.

### 5. `py/mapper.py` - Web Map Generation

Creates an interactive HTML/JavaScript viewer:

- Exports watersheds to GeoJSON format
- Generates JavaScript data files for each watershed
- Optionally includes river networks
- Creates searchable/sortable table of results
- Uses Leaflet.js for web mapping

The output `_viewer.html` file can be opened in any web browser to review results.

### 6. `py/raster_plots.py` - Debugging Visualizations

Matplotlib-based plotting functions for development/troubleshooting:

- Plots flow accumulation grids
- Visualizes flow direction
- Shows snapped outlet locations
- Overlays watershed boundaries on rasters

Only active when `PLOTS = True` in config.py.

---

## Data Requirements

### Input Data to Download

The sample data includes Iceland watersheds. For other regions:

1. **MERIT-Hydro Rasters** (for high-res mode)
   - Flow direction grids
   - Flow accumulation grids
   - Organized by Pfafstetter Level 2 basins (61 basins globally)
   - Download: <https://mghydro.com/watersheds/rasters>

2. **MERIT-Basins Vector Data**
   - Unit catchment polygons
   - River network flowlines
   - Download: <https://www.reachhydro.org/home/params/merit-basins>

3. **Simplified Catchments** (for low-res mode)
   - Pre-generalized boundaries
   - Download: <https://mghydro.com/watersheds/share/catchments_simplified.zip>

### Pfafstetter Basin System

The data is organized into 61 continental-scale basins identified by 2-digit codes (11-91). See `doc/merit_level2_basins.jpg` for a global map. You only need to download data for basins covering your region of interest.

### Outlet CSV Format

Required columns:

- `id`: Unique identifier (alphanumeric)
- `lat`: Latitude in decimal degrees (WGS84)
- `lng`: Longitude in decimal degrees (WGS84)

Optional columns:

- `name`: Descriptive name (in quotes)
- `area`: Expected watershed area in km² (for area matching)

Example:

```csv
id,lat,lng,name,area
iceland_01,65.1,-20.3,"Blanda River",900
iceland_02,64.8,-21.1,"Hvita River",1200
```

---

## Usage

### Basic Workflow

1. **Download required data** for your region (see Data Requirements above)

2. **Edit `config.py`**:
   - Set data directory paths
   - Choose `OUTLETS_CSV` filename
   - Configure processing options

3. **Create outlets CSV file** with your points

4. **Run the script**:

   ```bash
   uv run python delineate.py
   ```

5. **Review results**:
   - Check output folder for watershed files
   - Open `map/_viewer.html` in browser (if `MAKE_MAP = True`)

6. **Iterate**: Adjust outlet coordinates if needed and re-run

### Example: Delineating Iceland Watersheds

The repository includes sample data. To test:

```bash
# Install dependencies
uv sync

# Run with default settings (uses outlets_sample.csv)
uv run python delineate.py
```

This will create watersheds for several Icelandic rivers and generate an interactive map in the `map/` folder.

---

## Key Algorithms & Techniques

### Upstream Tracing

The script builds the watershed by identifying all unit catchments that contribute flow to the outlet:

1. Find the outlet catchment (contains the outlet point)
2. Use MERIT-Basins topology to trace upstream:
   - Each catchment has a unique `COMID`
   - Rivers have `NextDownID` pointing to the downstream catchment
   - Recursively find all catchments draining to the outlet

### Outlet Snapping

User-provided coordinates rarely fall exactly on a stream centerline. The script:

1. Searches within `SEARCH_DIST` radius for the nearest catchment
2. Examines river reaches within that catchment
3. Snaps to the reach with the largest upstream area
4. Optionally uses area matching to find the right tributary

### Area Matching (Experimental)

When `MATCH_AREAS = True`:

1. User provides expected watershed area in CSV
2. Script searches within `MAX_DIST` of outlet
3. Finds river reach whose upstream area matches within `AREA_MATCHING_THRESHOLD`
4. Uses that reach as the actual outlet

This helps when the outlet point is near multiple tributaries.

### Donut Hole Filling

MERIT-Basins data contains small gaps between catchments and larger endorheic basins (internal sinks). When `FILL = True`:

- Holes smaller than `FILL_THRESHOLD` pixels are filled
- Larger holes (e.g., disconnected playas) are preserved
- Set `FILL_THRESHOLD = 0` to fill all holes

---

## Performance Optimization

### Pickle Files

Reading shapefiles is slow. The script can cache GeoDataFrames as pickle files:

- Set `PICKLE_DIR` to a directory path
- First run reads shapefiles and saves pickles
- Subsequent runs load pickles (much faster)
- Pickle files are large (~1 GB for major basins)

### Spatial Indexing

GeoPandas/Shapely uses R-tree spatial indices for fast nearest-neighbor searches. This makes outlet snapping efficient even with millions of river reaches.

### Low-Res Mode for Large Watersheds

For watersheds >50,000 km²:

- Use simplified catchment boundaries (fewer vertices)
- Skip raster processing
- Dramatically faster with minimal accuracy loss

---

## Common Issues & Solutions

### Outlet Not Snapping to Stream

**Problem**: Watershed is much smaller than expected
**Solution**:

- Increase `SEARCH_DIST` in config.py
- Enable `MATCH_AREAS` and provide expected area in CSV
- Manually adjust outlet coordinates

### Unexpected Watershed Boundaries

**Problem**: Delineation includes/excludes wrong areas
**Solution**:

- Review results in web viewer with rivers overlay
- Check for coordinate typos in CSV
- Verify correct Pfafstetter basin data is loaded

### Slow Performance

**Problem**: Script takes too long
**Solution**:

- Enable pickle files (`PICKLE_DIR`)
- Use low-res mode for large watersheds
- Disable plots (`PLOTS = False`)
- Consider using online demo for one-off watersheds

### Missing Data Errors

**Problem**: Script can't find input files
**Solution**:

- Check all paths in config.py
- Verify downloaded data for correct Pfafstetter basin
- Ensure file names match expected patterns

---

## Technical Stack

**Core Libraries:**

- `geopandas`: Vector GIS operations
- `shapely`: Geometric calculations
- `rasterio`: Raster data I/O
- `numpy`: Array operations
- `pandas`: CSV handling and data frames

**Optional:**

- `matplotlib`: Plotting (if `PLOTS = True`)
- `pyproj`: Coordinate transformations

**Development Tools:**

- `uv`: Fast Python package manager
- `ruff`: Linting and formatting

---

## Development Notes

### Code Style

This project follows guidelines in `CLAUDE.md`:

- Type hints required (using `|` for unions, built-in generics)
- Use `uv` for all package management
- Use `logging` instead of `print`
- Format with `ruff`

### Testing

The Iceland sample dataset serves as integration test data. Run with default settings to verify the installation works.

### Contributing

See README.md for contribution guidelines. Bug reports and feature requests welcome via GitHub Issues.

### Citation

If you use this tool in research, please cite:

> Heberger, M. (2022). delineator.py: Fast watershed delineation using MERIT-Hydro and MERIT-Basins. <https://doi.org/10.5281/zenodo.7314287>

---

## Future Enhancements

Potential improvements (from code comments and issues):

- Migration to Shapely 2.0
- Better distance metrics (geodesic instead of decimal degrees)
- Database backend (PostgreSQL/PostGIS) for faster data access
- Parallel processing for batch operations
- More robust error handling
- Unit test coverage
- Support for custom DEM data

---

## Resources

- **Project repository**: <https://github.com/mheberger/delineator>
- **Online demo**: <https://mghydro.com/watersheds/>
- **MERIT-Hydro**: <http://hydro.iis.u-tokyo.ac.jp/~yamadai/MERIT_Hydro/>
- **MERIT-Basins**: <https://www.reachhydro.org/home/params/merit-basins>
- **Contact**: <matt@mghydro.com>

---

*This overview was generated for developers forking or contributing to the delineator project. For user-facing documentation, see README.md.*

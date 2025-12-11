#!/usr/bin/env python3
"""
CLI tool for downloading MERIT-Hydro and MERIT-Basins data.

This script provides a command-line interface for downloading the data required
for watershed delineation. It supports downloading by bounding box or explicit
basin codes.

Usage:
    # Download by bounding box (recommended)
    uv run download_data.py download --bbox -25,63,-13,67 --output data/

    # Download specific basins
    uv run download_data.py download --basins 18,45 --output data/

    # Download only rasters (skip vectors)
    uv run download_data.py download --bbox -25,63,-13,67 --rasters-only

    # Download only simplified catchments
    uv run download_data.py download --simplified-only --output data/

    # List available basins
    uv run download_data.py list-basins

    # Show basins for a bounding box without downloading
    uv run download_data.py dry-run --bbox -25,63,-13,67
"""

import logging
from pathlib import Path
from typing import Annotated

import typer

from delineator.download import (
    download_data,
    download_simplified_catchments,
    get_all_basin_codes,
    get_basins_for_bbox,
)

app = typer.Typer(
    help="Download MERIT-Hydro and MERIT-Basins data for watershed delineation.",
    no_args_is_help=True,
)


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the CLI."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_bbox(bbox_str: str) -> tuple[float, float, float, float]:
    """
    Parse a bounding box string into a tuple.

    Args:
        bbox_str: Comma-separated string "min_lon,min_lat,max_lon,max_lat"

    Returns:
        Tuple of (min_lon, min_lat, max_lon, max_lat)

    Raises:
        ValueError: Invalid bbox format
    """
    try:
        parts = [float(x.strip()) for x in bbox_str.split(",")]
        if len(parts) != 4:
            raise ValueError("Bbox must have exactly 4 values")
        return (parts[0], parts[1], parts[2], parts[3])
    except Exception as e:
        raise ValueError(
            f"Invalid bbox format. Expected 'min_lon,min_lat,max_lon,max_lat', got '{bbox_str}': {e}"
        ) from e


def parse_basins(basins_str: str) -> list[int]:
    """
    Parse a basins string into a list of integers.

    Args:
        basins_str: Comma-separated string of basin codes "18,45,42"

    Returns:
        List of basin codes as integers

    Raises:
        ValueError: Invalid basin format
    """
    try:
        return [int(x.strip()) for x in basins_str.split(",")]
    except Exception as e:
        raise ValueError(
            f"Invalid basins format. Expected comma-separated integers, got '{basins_str}': {e}"
        ) from e


@app.command(name="list-basins")
def cmd_list_basins() -> None:
    """List all available Pfafstetter Level 2 basin codes."""
    basins = get_all_basin_codes()
    typer.echo(f"Available Pfafstetter Level 2 basin codes ({len(basins)} total):")
    typer.echo()

    # Group by first digit for readability
    by_continent = {}
    for basin in basins:
        first_digit = basin // 10
        if first_digit not in by_continent:
            by_continent[first_digit] = []
        by_continent[first_digit].append(basin)

    for continent, codes in sorted(by_continent.items()):
        codes_str = ", ".join(str(c) for c in codes)
        typer.echo(f"  {continent}x: {codes_str}")

    typer.echo()
    typer.echo("See doc/merit_level2_basins.jpg for a visual map of basin locations.")


@app.command(name="dry-run")
def cmd_dry_run(
    bbox: Annotated[
        str,
        typer.Option(
            help="Bounding box as 'min_lon,min_lat,max_lon,max_lat'",
        ),
    ],
) -> None:
    """Show which basins would be downloaded without actually downloading."""
    try:
        bbox_tuple = parse_bbox(bbox)
        min_lon, min_lat, max_lon, max_lat = bbox_tuple
        typer.echo(f"Bounding box: ({min_lon}, {min_lat}, {max_lon}, {max_lat})")
        typer.echo()

        basins = get_basins_for_bbox(min_lon, min_lat, max_lon, max_lat)
        if basins:
            typer.echo(f"Basins that intersect this region ({len(basins)} total):")
            for basin in basins:
                typer.echo(f"  - Basin {basin}")
        else:
            typer.echo("No basins found for this bounding box.")
            typer.echo("Check that coordinates are in (longitude, latitude) order.")
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None


@app.command()
def download(
    bbox: Annotated[
        str | None,
        typer.Option(
            help="Bounding box as 'min_lon,min_lat,max_lon,max_lat'",
        ),
    ] = None,
    basins: Annotated[
        str | None,
        typer.Option(
            help="Comma-separated basin codes (e.g., '18,45,42')",
        ),
    ] = None,
    output: Annotated[
        Path,
        typer.Option(
            "-o",
            "--output",
            help="Output directory",
        ),
    ] = Path("data"),
    overwrite: Annotated[
        bool,
        typer.Option(
            help="Re-download files even if they exist",
        ),
    ] = False,
    rasters_only: Annotated[
        bool,
        typer.Option(
            "--rasters-only",
            help="Download only rasters (flowdir, accum) - no Google Drive needed",
        ),
    ] = False,
    vectors_only: Annotated[
        bool,
        typer.Option(
            "--vectors-only",
            help="Download only vectors (catchments, rivers) from Google Drive",
        ),
    ] = False,
    simplified_only: Annotated[
        bool,
        typer.Option(
            "--simplified-only",
            help="Download only simplified catchments ZIP",
        ),
    ] = False,
    no_simplified: Annotated[
        bool,
        typer.Option(
            "--no-simplified",
            help="Skip downloading simplified catchments",
        ),
    ] = False,
    gdrive_credentials: Annotated[
        Path | None,
        typer.Option(
            help="Path to Google Drive service account JSON credentials",
        ),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option(
            "-v",
            "--verbose",
            help="Enable verbose output",
        ),
    ] = False,
) -> None:
    """
    Download MERIT-Hydro and MERIT-Basins data for watershed delineation.

    Examples:

        Download data for Iceland by bounding box:
        $ uv run download_data.py download --bbox -25,63,-13,67 --output data/

        Download specific basins:
        $ uv run download_data.py download --basins 18,45 --output data/

        Download only rasters (no Google Drive needed):
        $ uv run download_data.py download --bbox -25,63,-13,67 --rasters-only

        Download only simplified catchments:
        $ uv run download_data.py download --simplified-only
    """
    # Setup logging
    setup_logging(verbose=verbose)
    logger = logging.getLogger(__name__)

    # Validate we have a selection for download
    if not bbox and not basins and not simplified_only:
        typer.echo("Error: One of --bbox, --basins, or --simplified-only is required", err=True)
        raise typer.Exit(code=1)

    # Parse selection
    bbox_tuple: tuple[float, float, float, float] | None = None
    basins_list: list[int] | None = None

    try:
        if bbox:
            bbox_tuple = parse_bbox(bbox)
        if basins:
            basins_list = parse_basins(basins)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None

    # Determine what to download
    include_rasters = True
    include_vectors = True
    include_simplified = not no_simplified

    if rasters_only:
        include_vectors = False
        include_simplified = False
    elif vectors_only:
        include_rasters = False
        include_simplified = False
    elif simplified_only:
        include_rasters = False
        include_vectors = False
        include_simplified = True

    # Handle simplified-only case
    if not include_rasters and not include_vectors and include_simplified:
        logger.info("Downloading simplified catchments only...")
        try:
            dest_dir = output / "shp" / "catchments_simplified"
            dest_dir.mkdir(parents=True, exist_ok=True)
            path = download_simplified_catchments(dest_dir=dest_dir, overwrite=overwrite)
            logger.info(f"Downloaded to: {path}")
            return
        except Exception as e:
            logger.error(f"Download failed: {e}")
            raise typer.Exit(code=1) from None

    # Regular download
    result = download_data(
        bbox=bbox_tuple,
        basins=basins_list,
        output_dir=output,
        include_rasters=include_rasters,
        include_vectors=include_vectors,
        include_simplified=include_simplified,
        overwrite=overwrite,
        gdrive_credentials=gdrive_credentials,
    )

    # Print summary
    typer.echo()
    typer.echo("=" * 60)
    typer.echo("DOWNLOAD COMPLETE")
    typer.echo("=" * 60)
    typer.echo(f"Basins: {result.basins_downloaded}")
    typer.echo(f"Rasters downloaded: {len(result.rasters)} basin(s)")
    typer.echo(f"Vectors downloaded: {len(result.vectors)} basin(s)")
    typer.echo(f"Simplified catchments: {'Yes' if result.simplified_catchments else 'No'}")
    typer.echo(f"Errors: {len(result.errors)}")

    if result.errors:
        typer.echo()
        typer.echo("Errors encountered:")
        for error in result.errors:
            typer.echo(f"  - {error}")

    if not result.success:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()

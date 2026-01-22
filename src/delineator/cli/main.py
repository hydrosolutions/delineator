"""
Main Typer CLI application for delineator.

This module provides the unified command-line interface with three subcommands:
- run: Main watershed delineation workflow
- download: Pre-download MERIT data for a region
- list-basins: Display available Pfafstetter Level 2 basin codes

The CLI follows the design specified in CLI_DESIGN_SPEC.md and adheres to
code style guidelines in CLAUDE.md.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from delineator.config import ENV_DATA_DIR, load_config, load_outlets
from delineator.core import (
    BasinData,
    DelineatedWatershed,
    DelineationError,
    OutputWriter,
    check_data_availability,
    delineate_outlet,
    ensure_data_available,
    get_required_basins,
    load_basin_data,
)
from delineator.download import download_data, get_all_basin_codes

# Initialize Typer app
app = typer.Typer(
    name="delineator",
    help="Watershed delineation using MERIT-Hydro data",
    no_args_is_help=True,
    add_completion=False,
)

# Initialize Rich console for formatted output
console = Console()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _setup_logging(verbose: bool, quiet: bool) -> None:
    """
    Configure logging level based on verbosity flags.

    Args:
        verbose: Enable debug logging
        quiet: Suppress all logging except errors
    """
    if quiet:
        logging.getLogger().setLevel(logging.ERROR)
    elif verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)


@app.command("run")
def run_command(
    config_file: Annotated[
        Path,
        typer.Argument(
            help="Path to master configuration file (delineate.toml)",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Override output directory from config"),
    ] = None,
    max_fails: Annotated[
        int | None,
        typer.Option("--max-fails", help="Stop after N failures (overrides config)", min=1),
    ] = None,
    fill_threshold: Annotated[
        int | None,
        typer.Option("--fill-threshold", help="Fill holes smaller than N pixels (overrides config)", min=0),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Validate configuration without processing"),
    ] = False,
    no_download: Annotated[
        bool,
        typer.Option("--no-download", help="Disable auto-download of missing MERIT data"),
    ] = False,
    output_format: Annotated[
        str,
        typer.Option("--output-format", help="Output format: text or json"),
    ] = "text",
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress progress output"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show detailed progress"),
    ] = False,
    skip_existing: Annotated[
        bool,
        typer.Option("--skip-existing", help="Skip outlets already present in output file"),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Overwrite existing output files"),
    ] = False,
    skip_failed: Annotated[
        bool,
        typer.Option("--skip-failed", help="Skip outlets that previously failed (in FAILED.csv)"),
    ] = False,
    file_format: Annotated[
        str,
        typer.Option("--file-format", help="Output file format: 'gpkg' (GeoPackage) or 'shp' (Shapefile)"),
    ] = "gpkg",
    include_rivers: Annotated[
        bool,
        typer.Option("--include-rivers", help="Include river network geometries in output"),
    ] = False,
) -> None:
    """
    Run watershed delineation for outlets defined in CONFIG_FILE.

    \b
    RESUME MODES:
        By default, the command fails if output files already exist.
        Use --skip-existing to process only new outlets (resume an interrupted run).
        Use --force to overwrite all existing outputs.

    \b
    CONFIG FILE FORMAT (delineate.toml):
        [settings]
        output_dir = "./output"    # Required
        max_fails = 100            # Optional

        [[regions]]
        name = "region_name"       # Required: for hive partitioning
        outlets = "outlets.toml"   # Required: path to outlets file

    \b
    OUTLETS FILE FORMAT (outlets.toml):
        [[outlets]]
        gauge_id = "unique_id"     # Required
        lat = 28.5                 # Required (decimal degrees)
        lng = 84.2                 # Required (decimal degrees)
        gauge_name = "River Name"  # Optional

    \b
    EXAMPLES:
        delineator run config.toml
        delineator run config.toml --dry-run
        delineator run config.toml -o ./output --max-fails 10
        delineator run config.toml --no-download
        delineator run config.toml --skip-existing    # Resume interrupted run
        delineator run config.toml --force            # Overwrite existing
        delineator run config.toml --file-format shp  # Output as Shapefile
    """
    # Setup logging
    _setup_logging(verbose=verbose, quiet=quiet)

    # Validate output format
    if output_format not in ["text", "json"]:
        console.print(f"[red]Error:[/red] Invalid output format '{output_format}'. Must be 'text' or 'json'.")
        raise typer.Exit(2)

    # Validate new flags
    if skip_existing and force:
        console.print(
            "[red]Error:[/red] --skip-existing and --force are mutually exclusive\n\n"
            "[yellow]Use one of:[/yellow]\n"
            "  --skip-existing  Skip already-processed outlets\n"
            "  --force          Overwrite all existing outputs"
        )
        raise typer.Exit(2)

    if file_format not in ["gpkg", "shp"]:
        console.print(f"[red]Error:[/red] Invalid file format '{file_format}'. Must be 'gpkg' or 'shp'.")
        raise typer.Exit(2)

    # Convert file_format string to OutputFormat enum
    from delineator.core.output_writer import OutputFormat

    output_file_format = OutputFormat.GEOPACKAGE if file_format == "gpkg" else OutputFormat.SHAPEFILE

    # Auto-detect format if output is being piped
    if output_format == "text" and not sys.stdout.isatty():
        output_format = "json"
        logger.debug("Auto-detected non-TTY output, switching to JSON format")

    try:
        # Load configuration
        if not quiet:
            console.print("[cyan]Loading configuration...[/cyan]")

        config = load_config(config_file)

        # Apply CLI overrides
        if output is not None:
            config.settings.output_dir = str(output)
            logger.info(f"Output directory overridden to: {output}")

        if max_fails is not None:
            config.settings.max_fails = max_fails
            logger.info(f"Max fails overridden to: {max_fails}")

        if fill_threshold is not None:
            config.settings.fill_threshold = fill_threshold
            logger.info(f"Fill threshold overridden to: {fill_threshold}")

        # Load all outlets
        all_outlets: list[tuple[float, float]] = []
        region_stats: list[dict[str, str | int]] = []

        for region in config.regions:
            outlets_path = Path(region.outlets)

            if not outlets_path.exists():
                console.print(
                    f"[red]Error:[/red] Outlets file not found for region '{region.name}': {outlets_path}\n\n"
                    f"[yellow]Fix:[/yellow] Create the outlets file or update the path in {config_file}"
                )
                raise typer.Exit(2)

            outlets = load_outlets(outlets_path)
            region_stats.append({"name": region.name, "outlets": len(outlets)})

            # Collect coordinates for basin calculation
            for outlet in outlets:
                all_outlets.append((outlet.lat, outlet.lng))

        total_outlets = len(all_outlets)

        if not quiet:
            console.print("[green]✓[/green] Config valid")
            console.print(f"[green]✓[/green] Found {len(config.regions)} region(s):")
            for stat in region_stats:
                console.print(f"    - {stat['name']}: {stat['outlets']} outlets")
            console.print(f"[green]✓[/green] Total: {total_outlets:,} outlets")

        # Determine data directory (fallback chain: config -> env var -> derived from output_dir)
        if config.settings.data_dir:
            data_dir = Path(config.settings.data_dir).expanduser()
        elif os.getenv(ENV_DATA_DIR):
            data_dir = Path(os.getenv(ENV_DATA_DIR)).expanduser()
        else:
            data_dir = Path(config.settings.output_dir).parent / "data"

        # Determine required basins
        required_basins = get_required_basins(all_outlets, data_dir=data_dir)

        if not quiet:
            console.print(f"[green]✓[/green] Required MERIT basins: {', '.join(map(str, required_basins))}")

        availability = check_data_availability(
            basins=required_basins,
            data_dir=data_dir,
            check_rasters=True,
            check_vectors=True,
            check_simplified=True,
        )

        if availability.all_available:
            if not quiet:
                console.print("  [green]✓[/green] All data available")
        else:
            if not quiet:
                console.print(f"  - Available: {', '.join(map(str, availability.available_basins)) or 'none'}")
                console.print(
                    f"  - Missing: {', '.join(map(str, availability.missing_basins))} "
                    f"({'will download' if not no_download else 'ERROR'})"
                )

            if no_download:
                console.print("\n[red]Error:[/red] Missing MERIT data\n")
                console.print(f"  Required basins not found: {', '.join(map(str, availability.missing_basins))}\n")
                console.print("  [yellow]Expected locations:[/yellow]")
                for missing_file in availability.missing_files[:5]:  # Show first 5
                    console.print(f"    - {missing_file}")
                if len(availability.missing_files) > 5:
                    console.print(f"    ... and {len(availability.missing_files) - 5} more files")
                console.print(
                    "\n  [yellow]Fix:[/yellow] Run without --no-download to auto-download, or pre-download with:"
                )
                console.print(f"    delineator download --basins {','.join(map(str, availability.missing_basins))}")
                raise typer.Exit(2)

        # Check output directory
        output_dir_path = Path(config.settings.output_dir).resolve()
        if output_dir_path.exists() and not output_dir_path.is_dir():
            console.print(f"[red]Error:[/red] Output path exists but is not a directory: {output_dir_path}")
            raise typer.Exit(2)

        if not quiet:
            console.print(f"[green]✓[/green] Output directory {output_dir_path} is valid")

        # If dry-run, stop here
        if dry_run:
            console.print("\n[bold green]Ready to run.[/bold green]")
            raise typer.Exit(0)

        # Download missing data if needed
        if not availability.all_available and not no_download:
            if not quiet:
                console.print("\n[cyan]Downloading missing data...[/cyan]")

            availability = ensure_data_available(
                basins=required_basins,
                data_dir=data_dir,
                auto_download=True,
                gdrive_credentials=None,  # TODO: Add CLI option for credentials
            )

            if not availability.all_available:
                console.print(
                    f"[red]Error:[/red] Failed to download all required data. "
                    f"Still missing: {', '.join(map(str, availability.missing_basins))}"
                )
                raise typer.Exit(2)

            if not quiet:
                console.print("[green]✓[/green] All data downloaded successfully")

        # Create output directories and writer
        output_dir_path.mkdir(parents=True, exist_ok=True)
        writer = OutputWriter(output_dir_path, output_format=output_file_format, include_rivers=include_rivers)

        # Fail-safe check: error if outputs exist and neither --skip-existing nor --force
        if not skip_existing and not force:
            existing_regions = [r.name for r in config.regions if writer.check_output_exists(r.name)]
            if existing_regions:
                console.print(
                    f"[red]Error:[/red] Output already exists for regions: {', '.join(existing_regions)}\n\n"
                    "[yellow]Choose one:[/yellow]\n"
                    "  --skip-existing  Resume: skip already-processed outlets\n"
                    "  --force          Overwrite: re-process all outlets\n\n"
                    "See 'delineator run --help' for more information."
                )
                raise typer.Exit(2)

        # Load failed gauge_ids if --skip-failed is set
        failed_gauge_ids: set[str] = set()
        if skip_failed:
            failed_gauge_ids = writer.load_failed_gauge_ids()
            if failed_gauge_ids and not quiet:
                console.print(f"[cyan]Found {len(failed_gauge_ids)} previously failed outlets to skip[/cyan]")

        # Track processing statistics
        total_processed = 0
        total_failed = 0
        total_skipped = 0
        fail_count = 0
        max_fails_value = max_fails or config.settings.max_fails

        # Load basin data (cache for reuse across outlets in same basin)
        basin_data_cache: dict[int, BasinData] = {}

        # Get data directories
        fdir_dir = data_dir / "raster" / "flowdir_basins"
        accum_dir = data_dir / "raster" / "accum_basins"

        # Process each region
        for region_idx, region in enumerate(config.regions, 1):
            region_name = region.name
            outlets_path = Path(region.outlets)

            if not quiet:
                console.print(f"\n[cyan][{region_idx}/{len(config.regions)}] Processing region: {region_name}[/cyan]")

            # Load outlets for this region
            outlets = load_outlets(outlets_path)
            region_watersheds: list[DelineatedWatershed] = []
            region_failed = 0
            region_skipped = 0

            # Load existing gauge_ids for this region (if --skip-existing)
            existing_gauge_ids: set[str] = set()
            if skip_existing:
                existing_gauge_ids = writer.read_existing_gauge_ids(region_name)
                if existing_gauge_ids and not quiet:
                    console.print(f"  Found {len(existing_gauge_ids)} existing outlets to skip")

            for outlet_idx, outlet in enumerate(outlets, 1):
                # Skip logic
                if skip_existing and outlet.gauge_id in existing_gauge_ids:
                    region_skipped += 1
                    total_skipped += 1
                    if verbose and not quiet:
                        console.print(f"  [dim]⊘ {outlet.gauge_id}: skipped (already exists)[/dim]")
                    continue

                if skip_failed and outlet.gauge_id in failed_gauge_ids:
                    region_skipped += 1
                    total_skipped += 1
                    if verbose and not quiet:
                        console.print(f"  [dim]⊘ {outlet.gauge_id}: skipped (previously failed)[/dim]")
                    continue

                # Simple progress indicator
                if not quiet and not verbose and (outlet_idx % 10 == 0 or outlet_idx == len(outlets)):
                    console.print(f"  Processing outlet {outlet_idx}/{len(outlets)}...", end="\r")

                try:
                    # Determine which basin this outlet is in
                    outlet_basins = get_required_basins([(outlet.lat, outlet.lng)], data_dir=data_dir)
                    if not outlet_basins:
                        raise DelineationError(f"Could not determine basin for outlet at ({outlet.lat}, {outlet.lng})")

                    basin_code = outlet_basins[0]  # Use first matching basin

                    # Load basin data if not cached
                    if basin_code not in basin_data_cache:
                        if verbose and not quiet:
                            console.print(f"  Loading basin {basin_code} data...")
                        basin_data_cache[basin_code] = load_basin_data(basin_code, data_dir)

                    basin_data = basin_data_cache[basin_code]

                    # Perform delineation
                    watershed = delineate_outlet(
                        gauge_id=outlet.gauge_id,
                        lat=outlet.lat,
                        lng=outlet.lng,
                        gauge_name=outlet.gauge_name or "",
                        catchments_gdf=basin_data.catchments_gdf,
                        rivers_gdf=basin_data.rivers_gdf,
                        fdir_dir=fdir_dir,
                        accum_dir=accum_dir,
                        fill_threshold=config.settings.fill_threshold,
                        use_high_res=True,
                        include_rivers=include_rivers,
                    )

                    region_watersheds.append(watershed)
                    total_processed += 1

                    if verbose and not quiet:
                        console.print(
                            f"  [green]✓[/green] {outlet.gauge_id}: {watershed.area:.1f} km², {watershed.country}"
                        )

                except DelineationError as e:
                    # Record failure
                    writer.record_failure(
                        region_name=region_name,
                        gauge_id=outlet.gauge_id,
                        lat=outlet.lat,
                        lng=outlet.lng,
                        error=str(e),
                    )
                    total_failed += 1
                    region_failed += 1
                    fail_count += 1

                    if verbose and not quiet:
                        console.print(f"  [red]✗[/red] {outlet.gauge_id}: {e}")

                    # Check max_fails threshold
                    if max_fails_value is not None and fail_count >= max_fails_value:
                        console.print(f"\n[red]Error:[/red] Reached maximum failures ({max_fails_value})")
                        raise typer.Exit(2) from None

                except Exception as e:
                    # Unexpected error - also record as failure
                    writer.record_failure(
                        region_name=region_name,
                        gauge_id=outlet.gauge_id,
                        lat=outlet.lat,
                        lng=outlet.lng,
                        error=f"Unexpected error: {e}",
                    )
                    total_failed += 1
                    region_failed += 1
                    fail_count += 1
                    logger.exception(f"Unexpected error delineating {outlet.gauge_id}")

                    # Check max_fails threshold (same as DelineationError handler)
                    if max_fails_value is not None and fail_count >= max_fails_value:
                        console.print(f"\n[red]Error:[/red] Reached maximum failures ({max_fails_value})")
                        raise typer.Exit(2) from None

                except KeyboardInterrupt:
                    logger.warning(f"Interrupted while processing {outlet.gauge_id}")
                    # Write partial results for current region before exiting
                    if region_watersheds:
                        console.print(
                            f"\n[yellow]Interrupted! Saving {len(region_watersheds)} "
                            f"partial results for {region_name}...[/yellow]"
                        )
                        try:
                            # Use append mode if we're resuming
                            write_mode = "a" if (skip_existing and existing_gauge_ids) else "w"
                            partial_path = writer.write_region_output(
                                f"{region_name}_PARTIAL", region_watersheds, mode=write_mode
                            )
                            console.print(f"  [green]✓[/green] Partial results saved to {partial_path}")
                        except Exception as write_err:
                            logger.error(f"Failed to save partial results: {write_err}")
                    writer.finalize()
                    raise typer.Exit(130) from None  # Standard exit code for SIGINT

            # Log region completion
            logger.info(
                f"Region '{region_name}' outlet loop complete: "
                f"{len(region_watersheds)} succeeded, {region_failed} failed"
            )

            # Write region output if any watersheds succeeded
            if region_watersheds:
                logger.info(f"Writing {len(region_watersheds)} watersheds for region '{region_name}'")
                try:
                    # Use append mode when resuming (skip_existing and outputs already exist)
                    write_mode = "a" if (skip_existing and existing_gauge_ids) else "w"
                    output_path = writer.write_region_output(region_name, region_watersheds, mode=write_mode)
                    logger.info(f"Successfully wrote output: {output_path}")
                    if not quiet:
                        msg = f"  [green]✓[/green] {len(region_watersheds)} succeeded"
                        if region_skipped > 0:
                            msg += f", {region_skipped} skipped"
                        if region_failed > 0:
                            msg += f", {region_failed} failed"
                        console.print(msg)
                        console.print(f"    → {output_path}")
                except Exception as e:
                    logger.exception(f"Failed to write output for region '{region_name}'")
                    console.print(f"  [red]✗[/red] Failed to write output: {e}")
                    # Continue to next region instead of aborting entire batch
            else:
                if not quiet:
                    if region_skipped > 0 and region_failed == 0:
                        console.print(f"  [green]✓[/green] All {region_skipped} outlets skipped (already exist)")
                    elif region_skipped > 0:
                        console.print(f"  [yellow]![/yellow] {region_skipped} skipped, {region_failed} failed")
                    else:
                        console.print(f"  [red]✗[/red] All {region_failed} outlets failed")

        # Finalize output (write FAILED.csv)
        failed_csv_path = writer.finalize()

        # Print summary
        if not quiet:
            console.print("\n[bold]Complete![/bold]")
            summary_msg = f"  Total: [bold]{total_processed}[/bold] succeeded"
            if total_skipped > 0:
                summary_msg += f", [bold]{total_skipped}[/bold] skipped"
            summary_msg += f", [bold]{total_failed}[/bold] failed"
            console.print(summary_msg)
            if failed_csv_path:
                console.print(f"  Failed outlets logged to: [yellow]{failed_csv_path}[/yellow]")

        # Exit with appropriate code
        if total_failed == 0:
            raise typer.Exit(0)
        elif total_processed > 0:
            raise typer.Exit(1)  # Partial success
        else:
            raise typer.Exit(2)  # Complete failure

    except typer.Exit:
        raise
    except KeyboardInterrupt:
        logger.warning("Process interrupted by user")
        console.print("\n[yellow]Interrupted by user[/yellow]")
        raise typer.Exit(130) from None
    except Exception as e:
        logger.exception("Unexpected error during run command")
        console.print(f"\n[red]Error:[/red] {e}")
        raise typer.Exit(2) from None


@app.command("download")
def download_command(
    bbox: Annotated[
        str | None,
        typer.Option("--bbox", help="Bounding box: min_lon,min_lat,max_lon,max_lat"),
    ] = None,
    basins: Annotated[
        str | None,
        typer.Option("--basins", help="Comma-separated basin codes (e.g., '18,45,61')"),
    ] = None,
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output directory for downloaded data"),
    ] = Path("data"),
    rasters_only: Annotated[
        bool,
        typer.Option("--rasters-only", help="Download only rasters (no Google Drive needed)"),
    ] = False,
    vectors_only: Annotated[
        bool,
        typer.Option("--vectors-only", help="Download only vectors"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would be downloaded without downloading"),
    ] = False,
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", help="Re-download existing files"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Debug logging"),
    ] = False,
) -> None:
    """
    Download MERIT-Hydro data for a region.

    You must specify either --bbox OR --basins (not both).

    \b
    EXAMPLES:
        # Download by bounding box
        delineator download --bbox -25,63,-13,67 --output data/

        # Download specific basins
        delineator download --basins 18,45,61 --output data/

        # Download only rasters (no Google Drive credentials needed)
        delineator download --bbox -25,63,-13,67 --rasters-only

        # Preview what would be downloaded
        delineator download --bbox -25,63,-13,67 --dry-run
    """
    # Setup logging
    _setup_logging(verbose=verbose, quiet=False)

    # Validate inputs
    if bbox and basins:
        console.print("[red]Error:[/red] Cannot specify both --bbox and --basins. Choose one.")
        raise typer.Exit(2)

    if not bbox and not basins:
        console.print("[red]Error:[/red] Must specify either --bbox or --basins")
        raise typer.Exit(2)

    if rasters_only and vectors_only:
        console.print("[red]Error:[/red] Cannot specify both --rasters-only and --vectors-only")
        raise typer.Exit(2)

    try:
        # Determine basin codes
        basin_codes: list[int]

        if bbox:
            # Parse bounding box
            try:
                bbox_parts = [float(x.strip()) for x in bbox.split(",")]
                if len(bbox_parts) != 4:
                    raise ValueError("Bounding box must have exactly 4 values")
                min_lon, min_lat, max_lon, max_lat = bbox_parts
            except ValueError as e:
                console.print(f"[red]Error:[/red] Invalid bounding box format: {e}")
                console.print("\n[yellow]Expected format:[/yellow] min_lon,min_lat,max_lon,max_lat")
                console.print("[yellow]Example:[/yellow] --bbox -25,63,-13,67")
                raise typer.Exit(2) from None

            # Get basins for bbox
            from delineator.download import get_basins_for_bbox

            basin_codes = get_basins_for_bbox(
                min_lon=min_lon,
                min_lat=min_lat,
                max_lon=max_lon,
                max_lat=max_lat,
            )

            console.print(f"[cyan]Bounding box:[/cyan] ({min_lon}, {min_lat}) to ({max_lon}, {max_lat})")
            console.print(f"[cyan]Found basins:[/cyan] {', '.join(map(str, basin_codes))}")

        else:  # basins specified
            # Parse basin codes
            try:
                basin_codes = [int(x.strip()) for x in basins.split(",")]  # type: ignore
            except ValueError as e:
                console.print(f"[red]Error:[/red] Invalid basin codes: {e}")
                console.print("\n[yellow]Expected format:[/yellow] Comma-separated integers")
                console.print("[yellow]Example:[/yellow] --basins 18,45,61")
                raise typer.Exit(2) from None

            # Validate basin codes
            from delineator.download import validate_basin_codes

            try:
                validate_basin_codes(basin_codes)
            except ValueError as e:
                console.print(f"[red]Error:[/red] {e}")
                console.print("\n[yellow]Hint:[/yellow] Use 'delineator list-basins' to see all valid codes")
                raise typer.Exit(2) from None

        if not basin_codes:
            console.print("[yellow]Warning:[/yellow] No basins found for the specified region")
            raise typer.Exit(0)

        # Dry run mode
        if dry_run:
            console.print("\n[bold cyan]Dry run - would download:[/bold cyan]")
            console.print(f"  Basins: {', '.join(map(str, basin_codes))}")
            console.print(f"  Output directory: {output}")
            console.print(f"  Rasters: {'yes' if not vectors_only else 'no'}")
            console.print(f"  Vectors: {'yes' if not rasters_only else 'no'}")
            raise typer.Exit(0)

        # Perform download
        console.print(f"\n[cyan]Downloading data for {len(basin_codes)} basin(s)...[/cyan]")

        result = download_data(
            basins=basin_codes,
            output_dir=output,
            include_rasters=not vectors_only,
            include_vectors=not rasters_only,
            include_simplified=not vectors_only,
            overwrite=overwrite,
            gdrive_credentials=None,  # TODO: Add CLI option for credentials
        )

        # Report results
        if result.success:
            console.print("\n[bold green]✓ Download complete![/bold green]")
            console.print(f"  Basins downloaded: {', '.join(map(str, result.basins_downloaded))}")
            console.print(f"  Output directory: {output}")
        else:
            console.print("\n[yellow]⚠ Download completed with errors:[/yellow]")
            for error in result.errors:
                console.print(f"  - {error}")
            raise typer.Exit(1)

    except typer.Exit:
        raise
    except Exception as e:
        logger.exception("Unexpected error during download command")
        console.print(f"\n[red]Error:[/red] {e}")
        raise typer.Exit(2) from None


@app.command("list-basins")
def list_basins_command() -> None:
    """
    List all available Pfafstetter Level 2 basin codes.

    Displays the 61 basin codes grouped by continent. These codes can be used
    with the 'download' command to fetch specific basin data.

    \b
    EXAMPLE:
        delineator list-basins
    """
    console.print("\n[bold cyan]Available Pfafstetter Level 2 Basin Codes[/bold cyan]\n")

    # Get all basin codes
    all_basins = get_all_basin_codes()

    # Group by continent (first digit of basin code)
    continent_map = {
        1: "Africa",
        2: "Africa",
        3: "Europe",
        4: "Europe",
        5: "Asia",
        6: "South America",
        7: "North America",
        8: "Oceania",
        9: "Antarctica",
    }

    grouped: dict[str, list[int]] = {}
    for basin in all_basins:
        first_digit = int(str(basin)[0])
        continent = continent_map.get(first_digit, "Unknown")

        if continent not in grouped:
            grouped[continent] = []
        grouped[continent].append(basin)

    # Create a table
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Continent", style="cyan", width=20)
    table.add_column("Basin Codes", style="white")

    for continent in sorted(grouped.keys()):
        basins = sorted(grouped[continent])
        basin_str = ", ".join(map(str, basins))
        table.add_row(continent, basin_str)

    console.print(table)
    console.print(f"\n[cyan]Total:[/cyan] {len(all_basins)} basins available\n")


if __name__ == "__main__":
    app()

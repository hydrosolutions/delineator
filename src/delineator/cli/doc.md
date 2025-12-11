---
module: cli
description: Unified Typer-based command-line interface for watershed delineation with three subcommands (run, download, list-basins)
---

## Files

- `__init__.py` - Public API exports (app)
- `main.py` - Main Typer application with all subcommands
- `output.py` - Output formatting for text (Rich) and JSON modes
- `config.py` - Configuration loading utilities (planned)

## Key Interfaces

### Main Application (`main.py`)

- `app` - Main Typer application instance
- `run_command()` - Main delineation workflow command
- `download_command()` - Pre-download MERIT data
- `list_basins_command()` - Display available basin codes

### Output Formatting (`output.py`)

- `OutputFormatter` - Main class for formatting CLI output
  - `print_result()` - Print final delineation results
  - `print_dry_run()` - Print validation/dry-run output
  - `print_error()` - Print formatted error messages with hints
  - `print_progress()` - Print progress messages (respects quiet mode)
  - `print_verbose()` - Print verbose debug messages
  - `print_validation_summary()` - Print structured validation info
  - `create_progress_table()` - Create Rich tables for structured output
- `DelineationResult` - Dataclass representing delineation run results
- `RegionResult` - Dataclass representing single region results

## Commands

### `delineator run <config>`

Main watershed delineation command that:
1. Loads and validates master config (delineate.toml)
2. Loads outlets from region-specific TOML files
3. Determines required MERIT basins
4. Checks/downloads data availability
5. Processes outlets and generates watershed shapefiles (TODO: Phase 4)

Options:
- `--output/-o`: Override output directory
- `--max-fails`: Stop after N failures
- `--dry-run`: Validate without processing
- `--no-download`: Disable auto-download
- `--output-format`: text or json output
- `--quiet/-q`: Suppress progress
- `--verbose/-v`: Debug logging

### `delineator download`

Pre-download MERIT data for offline use. Supports:
- Download by bounding box (`--bbox`)
- Download specific basins (`--basins`)
- Rasters only (`--rasters-only`)
- Vectors only (`--vectors-only`)
- Dry run mode (`--dry-run`)

### `delineator list-basins`

Display all 61 Pfafstetter Level 2 basin codes grouped by continent.

## Exit Codes

- 0: Success
- 1: Partial success (some operations failed)
- 2: Error (validation failed, missing data with --no-download, etc.)

## Output Modes

The CLI supports two output formats controlled by `--output-format`:

1. **text** (default for TTY): Rich-formatted output with colors, tables, panels, and progress indicators
2. **json** (auto-selected for pipes): Machine-readable JSON for automation and scripting

The formatter automatically detects non-TTY environments (pipes, redirects) and switches to JSON mode unless explicitly overridden.

## Dependencies

- `typer`: CLI framework
- `rich`: Formatted console output (tables, panels, colors)
- `delineator.config`: Configuration loading (Pydantic)
- `delineator.core`: Data checking and delineation
- `delineator.download`: Data download utilities

## Related Documentation

- Design spec: `/docs/CLI_DESIGN_SPEC.md`
- Output module: `/docs/OUTPUT_MODULE_README.md`
- Project guidelines: `/CLAUDE.md`

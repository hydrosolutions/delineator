"""
Output formatting module for the delineator CLI.

This module handles formatted output for the CLI, supporting both:
- Human-readable text output with Rich formatting
- Machine-readable JSON output for automation

The output formatter adapts to the execution context (TTY vs pipe) and
provides consistent, clear output for both interactive use and integration
with automation tools.
"""

import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..config.schema import MasterConfig

logger = logging.getLogger(__name__)


@dataclass
class RegionResult:
    """Result for a single region."""

    name: str
    processed: int
    failed: int
    output_path: str  # Using str for JSON serialization

    def __post_init__(self) -> None:
        """Validate region result fields."""
        if self.processed < 0:
            raise ValueError(f"processed must be non-negative, got {self.processed}")
        if self.failed < 0:
            raise ValueError(f"failed must be non-negative, got {self.failed}")


@dataclass
class DelineationResult:
    """Result from a delineation run."""

    status: str  # "success", "partial_success", "failure"
    exit_code: int  # 0, 1, or 2
    regions: list[RegionResult]
    total_processed: int
    total_failed: int
    failed_log: str | None  # Using str for JSON serialization
    data_downloaded: dict[str, list[int] | float] | None = None  # {"basins": [43], "size_mb": 245.3}

    def __post_init__(self) -> None:
        """Validate delineation result fields."""
        valid_statuses = {"success", "partial_success", "failure"}
        if self.status not in valid_statuses:
            raise ValueError(f"status must be one of {valid_statuses}, got '{self.status}'")

        valid_exit_codes = {0, 1, 2}
        if self.exit_code not in valid_exit_codes:
            raise ValueError(f"exit_code must be one of {valid_exit_codes}, got {self.exit_code}")

        if self.total_processed < 0:
            raise ValueError(f"total_processed must be non-negative, got {self.total_processed}")
        if self.total_failed < 0:
            raise ValueError(f"total_failed must be non-negative, got {self.total_failed}")


class OutputFormatter:
    """Handles CLI output formatting for text and JSON modes."""

    def __init__(self, output_format: str = "text", quiet: bool = False, verbose: bool = False) -> None:
        """
        Initialize the output formatter.

        Args:
            output_format: Output format ("text" or "json")
            quiet: Suppress progress output
            verbose: Show detailed progress information

        Raises:
            ValueError: If output_format is not "text" or "json"
        """
        if output_format not in ("text", "json"):
            raise ValueError(f"output_format must be 'text' or 'json', got '{output_format}'")

        self.output_format = output_format
        self.quiet = quiet
        self.verbose = verbose
        self.console = Console(file=sys.stdout, force_terminal=output_format == "text")

        logger.debug(f"OutputFormatter initialized: format={output_format}, quiet={quiet}, verbose={verbose}")

    def print_result(self, result: DelineationResult) -> None:
        """
        Print delineation result in text or JSON format.

        Args:
            result: The delineation result to print
        """
        if self.output_format == "json":
            self._print_json_result(result)
        else:
            self._print_text_result(result)

    def _print_json_result(self, result: DelineationResult) -> None:
        """Print result as JSON."""
        # Convert dataclass to dict
        output = asdict(result)
        print(json.dumps(output, indent=2))
        logger.debug("Printed JSON result")

    def _print_text_result(self, result: DelineationResult) -> None:
        """Print result as formatted text using Rich."""
        # Summary header
        if result.status == "success":
            status_text = Text("Complete!", style="bold green")
            status_icon = "✓"
        elif result.status == "partial_success":
            status_text = Text("Partially Complete", style="bold yellow")
            status_icon = "⚠"
        else:
            status_text = Text("Failed", style="bold red")
            status_icon = "✗"

        self.console.print()
        self.console.print(status_icon, status_text)
        self.console.print()

        # Region-by-region results
        if result.regions:
            for region in result.regions:
                status_symbol = "✓" if region.failed == 0 else "⚠"
                self.console.print(
                    f"  {status_symbol} [bold]{region.name}[/bold]: "
                    f"{region.processed} succeeded, {region.failed} failed"
                )
                self.console.print(f"    → {region.output_path}")

            self.console.print()

        # Summary statistics
        self.console.print(
            f"  Total: [bold]{result.total_processed}[/bold] succeeded, [bold]{result.total_failed}[/bold] failed"
        )

        # Failed log location
        if result.failed_log:
            self.console.print(f"  Failed outlets logged to: [yellow]{result.failed_log}[/yellow]")

        # Data download information
        if result.data_downloaded:
            basins = result.data_downloaded.get("basins", [])
            size_mb = result.data_downloaded.get("size_mb", 0.0)
            if basins:
                self.console.print(
                    f"  Downloaded {len(basins)} basin(s) ({size_mb:.1f} MB): {basins}",
                    style="cyan",
                )

        self.console.print()
        logger.debug("Printed text result")

    def print_dry_run(
        self,
        config: MasterConfig,
        basins: list[int],
        available: list[int],
        missing: list[int],
    ) -> None:
        """
        Print dry-run validation results.

        Args:
            config: The validated master configuration
            basins: List of required basin codes
            available: List of available basin codes
            missing: List of missing basin codes that will be downloaded
        """
        if self.output_format == "json":
            self._print_json_dry_run(config, basins, available, missing)
        else:
            self._print_text_dry_run(config, basins, available, missing)

    def _print_json_dry_run(
        self,
        config: MasterConfig,
        basins: list[int],
        available: list[int],
        missing: list[int],
    ) -> None:
        """Print dry-run as JSON."""
        # Count total outlets
        from ..config.schema import load_outlets

        region_info = []
        total_outlets = 0

        for region in config.regions:
            try:
                outlets = load_outlets(Path(region.outlets))
                outlet_count = len(outlets)
                total_outlets += outlet_count
                region_info.append({"name": region.name, "outlets": outlet_count, "outlets_file": region.outlets})
            except Exception as e:
                region_info.append({"name": region.name, "outlets": 0, "error": str(e)})

        output = {
            "valid": True,
            "regions": region_info,
            "total_outlets": total_outlets,
            "required_basins": sorted(basins),
            "available_basins": sorted(available),
            "missing_basins": sorted(missing),
            "will_download": len(missing) > 0,
            "output_dir": config.settings.output_dir,
        }

        print(json.dumps(output, indent=2))
        logger.debug("Printed JSON dry-run")

    def _print_text_dry_run(
        self,
        config: MasterConfig,
        basins: list[int],
        available: list[int],
        missing: list[int],
    ) -> None:
        """Print dry-run as formatted text using Rich."""
        from ..config.schema import load_outlets

        self.console.print()
        self.console.print("✓ [green]Config valid[/green]")

        # Region summary
        region_lines = []
        total_outlets = 0

        for region in config.regions:
            try:
                outlets = load_outlets(Path(region.outlets))
                outlet_count = len(outlets)
                total_outlets += outlet_count
                region_lines.append(f"  - {region.name}: {outlet_count} outlet(s)")
            except Exception as e:
                region_lines.append(f"  - {region.name}: [red]Error loading outlets: {e}[/red]")

        self.console.print(f"✓ Found [bold]{len(config.regions)}[/bold] region(s):")
        for line in region_lines:
            self.console.print(line)

        self.console.print(f"✓ Total: [bold]{total_outlets}[/bold] outlet(s)")

        # Basin availability
        if basins:
            self.console.print(f"✓ Required MERIT basins: {', '.join(map(str, sorted(basins)))}")

            if available:
                self.console.print(f"  - Available: {', '.join(map(str, sorted(available)))}", style="green")

            if missing:
                self.console.print(
                    f"  - Missing (will download): {', '.join(map(str, sorted(missing)))}",
                    style="yellow",
                )

        # Output directory
        output_dir = Path(config.settings.output_dir)
        if output_dir.exists() and output_dir.is_dir():
            self.console.print(f"✓ Output directory [cyan]{config.settings.output_dir}[/cyan] is writable")
        else:
            self.console.print(
                f"✓ Output directory [cyan]{config.settings.output_dir}[/cyan] will be created",
                style="yellow",
            )

        self.console.print()
        self.console.print("[bold green]Ready to run.[/bold green]")
        self.console.print()

        logger.debug("Printed text dry-run")

    def print_error(self, message: str, hint: str | None = None, details: str | None = None) -> None:
        """
        Print error with optional hint and details.

        Args:
            message: The main error message
            hint: Optional hint for fixing the error
            details: Optional detailed error information (e.g., stack trace snippet)
        """
        if self.output_format == "json":
            error_obj = {"error": message}
            if hint:
                error_obj["hint"] = hint
            if details:
                error_obj["details"] = details
            print(json.dumps(error_obj, indent=2))
        else:
            self.console.print()
            self.console.print(f"[bold red]Error:[/bold red] {message}")

            if details:
                # Print details in a panel for better visibility
                details_panel = Panel(
                    details,
                    title="Details",
                    border_style="red",
                    expand=False,
                )
                self.console.print(details_panel)

            if hint:
                self.console.print()
                self.console.print(f"[bold cyan]Fix:[/bold cyan] {hint}")

            self.console.print()

        logger.error(f"Error: {message}")
        if hint:
            logger.error(f"Hint: {hint}")
        if details:
            logger.error(f"Details: {details}")

    def print_progress(self, message: str, style: str = "") -> None:
        """
        Print progress message (only if not quiet and format is text).

        Args:
            message: The progress message to print
            style: Optional Rich style string (e.g., "bold green", "cyan")
        """
        if self.quiet or self.output_format == "json":
            return

        if style:
            self.console.print(message, style=style)
        else:
            self.console.print(message)

        logger.debug(f"Progress: {message}")

    def print_verbose(self, message: str, style: str = "") -> None:
        """
        Print verbose message (only if verbose mode is enabled and format is text).

        Args:
            message: The verbose message to print
            style: Optional Rich style string
        """
        if not self.verbose or self.quiet or self.output_format == "json":
            return

        if style:
            self.console.print(message, style=style)
        else:
            self.console.print(message)

        logger.debug(f"Verbose: {message}")

    def create_progress_table(self, title: str, columns: list[tuple[str, str]]) -> Table:
        """
        Create a Rich table for displaying structured progress information.

        Args:
            title: Table title
            columns: List of (column_name, style) tuples

        Returns:
            Configured Rich Table instance
        """
        table = Table(title=title, show_header=True, header_style="bold magenta")

        for col_name, col_style in columns:
            table.add_column(col_name, style=col_style)

        return table

    def print_validation_summary(
        self,
        config_valid: bool,
        regions: list[tuple[str, int, str | None]],
        basins_required: list[int],
        basins_available: list[int],
        basins_missing: list[int],
    ) -> None:
        """
        Print a validation summary with structured information.

        Args:
            config_valid: Whether the config is valid
            regions: List of (region_name, outlet_count, error_message) tuples
            basins_required: List of required basin codes
            basins_available: List of available basin codes
            basins_missing: List of missing basin codes
        """
        if self.output_format == "json":
            output = {
                "config_valid": config_valid,
                "regions": [{"name": name, "outlets": count, "error": error} for name, count, error in regions],
                "basins": {
                    "required": sorted(basins_required),
                    "available": sorted(basins_available),
                    "missing": sorted(basins_missing),
                },
            }
            print(json.dumps(output, indent=2))
        else:
            if config_valid:
                self.console.print("✓ [green]Configuration valid[/green]")
            else:
                self.console.print("✗ [red]Configuration invalid[/red]")

            # Print regions table
            table = self.create_progress_table("Regions", [("Region", "cyan"), ("Outlets", "green"), ("Status", "")])

            for name, count, error in regions:
                if error:
                    table.add_row(name, str(count), f"[red]Error: {error}[/red]")
                else:
                    table.add_row(name, str(count), "[green]✓[/green]")

            self.console.print(table)

            # Print basin information
            if basins_required:
                self.console.print(f"\n[bold]Required basins:[/bold] {', '.join(map(str, sorted(basins_required)))}")
                if basins_available:
                    self.console.print(f"  [green]Available:[/green] {', '.join(map(str, sorted(basins_available)))}")
                if basins_missing:
                    self.console.print(f"  [yellow]Missing:[/yellow] {', '.join(map(str, sorted(basins_missing)))}")

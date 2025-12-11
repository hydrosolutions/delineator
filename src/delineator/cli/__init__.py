"""
Unified Typer CLI for the delineator tool.

This module exports the main Typer application that provides the command-line
interface for watershed delineation using MERIT-Hydro data.
"""

from .main import app

__all__ = ["app"]

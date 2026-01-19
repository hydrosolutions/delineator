"""
FastAPI HTTP API for watershed delineation.

This module provides a REST API that wraps the delineate_outlet() function,
enabling the Virtual-Gauges frontend to request watershed boundaries.
"""

from .main import app, create_app

__all__ = ["app", "create_app"]

"""
Logging configuration for the delineator API.

Configures structured request logging with timestamps, gauge IDs, coordinates,
status, duration, and cache hit information.
"""

import logging
import os
import sys
from pathlib import Path


def setup_logging() -> logging.Logger:
    """
    Configure logging for the API.

    Logs to stdout by default. If DELINEATOR_LOG_FILE env var is set,
    also logs to that file.

    Returns:
        Logger instance for the API module.
    """
    logger = logging.getLogger("delineator.api")
    logger.setLevel(logging.INFO)

    # Remove any existing handlers
    logger.handlers.clear()

    # Log format: timestamp | message
    formatter = logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    # Always log to stdout
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.INFO)
    stdout_handler.setFormatter(formatter)
    logger.addHandler(stdout_handler)

    # Optional file logging
    log_file = os.getenv("DELINEATOR_LOG_FILE")
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def log_request(
    logger: logging.Logger,
    gauge_id: str,
    lat: float,
    lng: float,
    status: str,
    duration_seconds: float,
    cached: bool,
    error_code: str | None = None,
) -> None:
    """
    Log a request with structured format.

    Args:
        logger: Logger instance
        gauge_id: Gauge identifier
        lat: Latitude
        lng: Longitude
        status: "SUCCESS" or "ERROR"
        duration_seconds: Request duration in seconds
        cached: Whether result was from cache
        error_code: Optional error code for failed requests

    Log format:
        SUCCESS: gauge_id | lat, lng | SUCCESS | 4.2s | cached=false
        ERROR:   gauge_id | lat, lng | ERROR | 1.1s | NO_RIVER_FOUND
    """
    duration_str = f"{duration_seconds:.1f}s"

    if status == "SUCCESS":
        message = f"{gauge_id} | {lat}, {lng} | SUCCESS | {duration_str} | cached={str(cached).lower()}"
    else:
        message = f"{gauge_id} | {lat}, {lng} | ERROR | {duration_str} | {error_code}"

    logger.info(message)

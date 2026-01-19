"""
API routes for the delineator service.
"""

import asyncio
import time
from dataclasses import dataclass
from functools import partial

from fastapi import APIRouter, Response, status

from delineator.api.cache import WatershedCache
from delineator.api.deps import get_basin_for_point, get_data_dir
from delineator.api.logging_config import log_request, setup_logging
from delineator.api.models import (
    DelineateRequest,
    DelineateResponse,
    watershed_to_response,
)
from delineator.core.delineate import DelineationError, delineate_outlet


@dataclass
class RequestStats:
    """Track cache hit/miss statistics."""

    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0

    @property
    def hit_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.cache_hits / self.total_requests


router = APIRouter()
cache = WatershedCache()
stats = RequestStats()
api_logger = setup_logging()


@router.post("/delineate", response_model=DelineateResponse)
async def delineate(request: DelineateRequest) -> DelineateResponse:
    """
    Delineate a watershed for the given outlet coordinates.

    Returns a GeoJSON Feature with the watershed polygon and properties.
    Results are cached; subsequent requests for the same coordinates
    return instantly with cached=True.
    """
    start_time = time.time()
    stats.total_requests += 1

    # Check cache first
    cached_response = cache.get(request.lat, request.lng)
    if cached_response is not None:
        stats.cache_hits += 1
        duration = time.time() - start_time
        log_request(
            api_logger,
            gauge_id=request.gauge_id,
            lat=request.lat,
            lng=request.lng,
            status="SUCCESS",
            duration_seconds=duration,
            cached=True,
        )
        # Update the gauge_id and cached flag
        cached_response.gauge_id = request.gauge_id
        cached_response.cached = True
        return cached_response

    stats.cache_misses += 1

    try:
        # Load basin data for the point
        basin_data = get_basin_for_point(request.lat, request.lng)

        # Get data directories
        data_dir = get_data_dir()
        fdir_dir = data_dir / "raster/flowdir_basins"
        accum_dir = data_dir / "raster/accum_basins"

        # Run delineation in thread pool (CPU-bound)
        loop = asyncio.get_running_loop()

        delineate_fn = partial(
            delineate_outlet,
            gauge_id=request.gauge_id,
            lat=request.lat,
            lng=request.lng,
            gauge_name="",  # Optional, empty for API
            catchments_gdf=basin_data.catchments_gdf,
            rivers_gdf=basin_data.rivers_gdf,
            fdir_dir=fdir_dir,
            accum_dir=accum_dir,
        )

        watershed = await loop.run_in_executor(None, delineate_fn)

        # Convert to response
        response = watershed_to_response(watershed, request.gauge_id, cached=False)

        # Store in cache
        cache.put(request.lat, request.lng, request.gauge_id, response)

        # Log successful delineation
        duration = time.time() - start_time
        log_request(
            api_logger,
            gauge_id=request.gauge_id,
            lat=request.lat,
            lng=request.lng,
            status="SUCCESS",
            duration_seconds=duration,
            cached=False,
        )

        return response

    except DelineationError as e:
        duration = time.time() - start_time
        error_msg = str(e)
        if "does not fall within any unit catchment" in error_msg:
            error_code = "NO_RIVER_FOUND"
        else:
            error_code = "DELINEATION_FAILED"
        log_request(
            api_logger,
            gauge_id=request.gauge_id,
            lat=request.lat,
            lng=request.lng,
            status="ERROR",
            duration_seconds=duration,
            cached=False,
            error_code=error_code,
        )
        raise
    except FileNotFoundError:
        duration = time.time() - start_time
        log_request(
            api_logger,
            gauge_id=request.gauge_id,
            lat=request.lat,
            lng=request.lng,
            status="ERROR",
            duration_seconds=duration,
            cached=False,
            error_code="NO_DATA_AVAILABLE",
        )
        raise
    except Exception:
        duration = time.time() - start_time
        log_request(
            api_logger,
            gauge_id=request.gauge_id,
            lat=request.lat,
            lng=request.lng,
            status="ERROR",
            duration_seconds=duration,
            cached=False,
            error_code="DELINEATION_FAILED",
        )
        raise


@router.get("/health")
async def health() -> dict:
    """
    Health check endpoint.

    Returns API status, version, and configuration.
    """
    return {
        "status": "healthy",
        "version": "0.1.0",
        "data_dir": str(get_data_dir()),
    }


@router.get("/cache/stats")
async def cache_stats() -> dict:
    """
    Get cache statistics.

    Returns request counts, hit/miss rates, and cache size.
    """
    db_stats = cache.stats()

    return {
        "total_requests": stats.total_requests,
        "cache_hits": stats.cache_hits,
        "cache_misses": stats.cache_misses,
        "hit_rate": stats.hit_rate,
        "cache_size": db_stats["cache_size"],
    }


@router.delete("/cache/{gauge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cache(gauge_id: str) -> Response:
    """
    Delete cached entries for a gauge.

    Returns 204 No Content on success.
    """
    cache.delete_by_gauge_id(gauge_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

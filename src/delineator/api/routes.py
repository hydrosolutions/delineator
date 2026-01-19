"""
API routes for the delineator service.
"""

import asyncio
from functools import partial

from fastapi import APIRouter

from delineator.api.cache import WatershedCache
from delineator.api.deps import get_basin_for_point, get_data_dir
from delineator.api.models import (
    DelineateRequest,
    DelineateResponse,
    watershed_to_response,
)
from delineator.core.delineate import delineate_outlet

router = APIRouter()
cache = WatershedCache()


@router.post("/delineate", response_model=DelineateResponse)
async def delineate(request: DelineateRequest) -> DelineateResponse:
    """
    Delineate a watershed for the given outlet coordinates.

    Returns a GeoJSON Feature with the watershed polygon and properties.
    Results are cached; subsequent requests for the same coordinates
    return instantly with cached=True.
    """
    # Check cache first
    cached_response = cache.get(request.lat, request.lng)
    if cached_response is not None:
        # Update the gauge_id and cached flag
        cached_response.gauge_id = request.gauge_id
        cached_response.cached = True
        return cached_response

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

    return response

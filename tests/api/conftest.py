"""
Shared pytest fixtures for API module tests.

Provides fixtures for testing the FastAPI endpoints including mocked
dependencies, test clients, and synthetic data for watershed responses.
"""

from collections.abc import Generator
from dataclasses import dataclass
from unittest.mock import patch

import geopandas as gpd
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import LineString, Point, Polygon, box

from delineator.api import routes
from delineator.api.cache import WatershedCache
from delineator.api.main import create_app
from delineator.api.models import (
    DelineateResponse,
    RiverFeature,
    RiverProperties,
    RiversFeatureCollection,
    WatershedFeature,
    WatershedProperties,
)
from delineator.core.delineate import BasinData, DelineatedWatershed


@dataclass
class MockBasinData:
    """Mock basin data for testing."""

    basin_code: int
    catchments_gdf: gpd.GeoDataFrame
    rivers_gdf: gpd.GeoDataFrame


def make_test_catchments_gdf() -> gpd.GeoDataFrame:
    """Create a synthetic catchments GeoDataFrame for testing."""
    comids = [41000001, 41000002]
    centers = [(-105.0, 40.0), (-105.0, 40.05)]

    geometries = [box(lng - 0.025, lat - 0.025, lng + 0.025, lat + 0.025) for lng, lat in centers]

    return gpd.GeoDataFrame(
        {"unitarea": [100.0, 100.0]},
        index=pd.Index(comids, name="COMID"),
        geometry=geometries,
        crs="EPSG:4326",
    )


def make_test_rivers_gdf() -> gpd.GeoDataFrame:
    """Create a synthetic rivers GeoDataFrame for testing."""
    comids = [41000001, 41000002]
    downstream_coords = [(-105.0, 39.975), (-105.0, 40.025)]

    geometries = [LineString([(lng, lat), (lng, lat + 0.04)]) for lng, lat in downstream_coords]

    data = {
        "up1": [41000002, 0],
        "up2": [0, 0],
        "up3": [0, 0],
        "up4": [0, 0],
        "uparea": [500.0, 200.0],
    }

    return gpd.GeoDataFrame(
        data,
        index=pd.Index(comids, name="COMID"),
        geometry=geometries,
        crs="EPSG:4326",
    )


@pytest.fixture
def mock_basin_data() -> BasinData:
    """Create mock BasinData with synthetic GeoDataFrames."""
    return BasinData(
        basin_code=41,
        catchments_gdf=make_test_catchments_gdf(),
        rivers_gdf=make_test_rivers_gdf(),
    )


@pytest.fixture
def mock_watershed() -> DelineatedWatershed:
    """Create a mock DelineatedWatershed for successful responses."""
    return DelineatedWatershed(
        gauge_id="test-gauge-001",
        gauge_name="Test Gauge",
        gauge_lat=40.0,
        gauge_lon=-105.0,
        snap_lat=40.001,
        snap_lon=-104.999,
        snap_dist=150.5,
        country="USA",
        area=250.5,
        geometry=Polygon(
            [
                (-105.05, 39.95),
                (-104.95, 39.95),
                (-104.95, 40.05),
                (-105.05, 40.05),
                (-105.05, 39.95),
            ]
        ),
        resolution="high_res",
    )


@pytest.fixture
def mock_watershed_low_res() -> DelineatedWatershed:
    """Mock watershed with low-resolution for testing force_low_res parameter."""
    return DelineatedWatershed(
        gauge_id="test-gauge-001",
        gauge_name="Test Gauge",
        gauge_lat=40.0,
        gauge_lon=-105.0,
        snap_lat=40.001,
        snap_lon=-104.999,
        snap_dist=150.5,
        country="USA",
        area=250.5,
        geometry=Polygon(
            [
                (-105.05, 39.95),
                (-104.95, 39.95),
                (-104.95, 40.05),
                (-105.05, 40.05),
                (-105.05, 39.95),
            ]
        ),
        resolution="low_res",
    )


@pytest.fixture
def mock_complex_watershed() -> DelineatedWatershed:
    """Create a mock DelineatedWatershed with a high-vertex polygon (256+ vertices).

    Uses Point.buffer() with resolution=64 to generate a 256-vertex polygon,
    useful for testing geometry simplification.
    """
    # Create a circular polygon with 256+ vertices using buffer
    # resolution=64 creates 64 points per quarter circle = 256 vertices
    complex_geometry = Point(-105.0, 40.0).buffer(0.1, resolution=64)

    return DelineatedWatershed(
        gauge_id="complex-gauge-001",
        gauge_name="Complex Gauge",
        gauge_lat=40.0,
        gauge_lon=-105.0,
        snap_lat=40.0,
        snap_lon=-105.0,
        snap_dist=0.0,
        country="USA",
        area=100.0,
        geometry=complex_geometry,
        resolution="high_res",
    )


@pytest.fixture
def mock_delineate_response() -> DelineateResponse:
    """Create a mock DelineateResponse for cache testing."""
    return DelineateResponse(
        gauge_id="test-gauge-001",
        status="success",
        cached=False,
        watershed=WatershedFeature(
            type="Feature",
            geometry={
                "type": "Polygon",
                "coordinates": [
                    [
                        [-105.05, 39.95],
                        [-104.95, 39.95],
                        [-104.95, 40.05],
                        [-105.05, 40.05],
                        [-105.05, 39.95],
                    ]
                ],
            },
            properties=WatershedProperties(
                gauge_id="test-gauge-001",
                area_km2=250.5,
                snap_lat=40.001,
                snap_lng=-104.999,
                snap_distance_m=150.5,
                resolution="high_res",
            ),
        ),
    )


@pytest.fixture
def fresh_cache(tmp_path) -> WatershedCache:
    """Create a fresh in-memory cache for each test."""
    db_path = tmp_path / "test_cache.db"
    return WatershedCache(db_path)


@pytest.fixture
def test_client(
    mock_basin_data: BasinData,
    mock_watershed: DelineatedWatershed,
    tmp_path,
) -> Generator[TestClient, None, None]:
    """
    Create a FastAPI TestClient with mocked dependencies.

    Patches:
    - get_basin_for_point: Returns mock_basin_data
    - get_data_dir: Returns tmp_path
    - delineate_outlet: Returns mock_watershed

    Also resets module-level cache and stats for isolation.
    """
    with (
        patch(
            "delineator.api.routes.get_basin_for_point",
            return_value=mock_basin_data,
        ),
        patch(
            "delineator.api.routes.get_data_dir",
            return_value=tmp_path,
        ),
        patch(
            "delineator.api.routes.delineate_outlet",
            return_value=mock_watershed,
        ),
    ):
        # Reset module-level state for test isolation
        db_path = tmp_path / "test_cache.db"
        routes.cache = WatershedCache(db_path)
        routes.stats = routes.RequestStats()

        app = create_app()
        yield TestClient(app)


def make_test_rivers_gdf_for_watershed() -> gpd.GeoDataFrame:
    """Create a rivers GeoDataFrame for testing watershed with rivers."""
    comids = [41000001, 41000002]
    downstream_coords = [(-105.0, 39.975), (-105.0, 40.025)]

    geometries = [LineString([(lng, lat), (lng, lat + 0.04)]) for lng, lat in downstream_coords]

    data = {
        "up1": [41000002, 0],
        "up2": [0, 0],
        "up3": [0, 0],
        "up4": [0, 0],
        "uparea": [500.0, 200.0],
    }

    return gpd.GeoDataFrame(
        data,
        index=pd.Index(comids, name="COMID"),
        geometry=geometries,
        crs="EPSG:4326",
    )


@pytest.fixture
def mock_watershed_with_rivers() -> DelineatedWatershed:
    """Create a mock DelineatedWatershed with rivers included."""
    return DelineatedWatershed(
        gauge_id="test-gauge-001",
        gauge_name="Test Gauge",
        gauge_lat=40.0,
        gauge_lon=-105.0,
        snap_lat=40.001,
        snap_lon=-104.999,
        snap_dist=150.5,
        country="USA",
        area=250.5,
        geometry=Polygon(
            [
                (-105.05, 39.95),
                (-104.95, 39.95),
                (-104.95, 40.05),
                (-105.05, 40.05),
                (-105.05, 39.95),
            ]
        ),
        resolution="high_res",
        rivers=make_test_rivers_gdf_for_watershed(),
    )


@pytest.fixture
def mock_delineate_response_with_rivers() -> DelineateResponse:
    """Create a mock DelineateResponse with rivers for cache testing."""
    return DelineateResponse(
        gauge_id="test-gauge-001",
        status="success",
        cached=False,
        watershed=WatershedFeature(
            type="Feature",
            geometry={
                "type": "Polygon",
                "coordinates": [
                    [
                        [-105.05, 39.95],
                        [-104.95, 39.95],
                        [-104.95, 40.05],
                        [-105.05, 40.05],
                        [-105.05, 39.95],
                    ]
                ],
            },
            properties=WatershedProperties(
                gauge_id="test-gauge-001",
                area_km2=250.5,
                snap_lat=40.001,
                snap_lng=-104.999,
                snap_distance_m=150.5,
                resolution="high_res",
            ),
        ),
        rivers=RiversFeatureCollection(
            type="FeatureCollection",
            features=[
                RiverFeature(
                    type="Feature",
                    geometry={
                        "type": "LineString",
                        "coordinates": [[-105.0, 39.975], [-105.0, 40.015]],
                    },
                    properties=RiverProperties(comid=41000001, uparea=500.0),
                ),
                RiverFeature(
                    type="Feature",
                    geometry={
                        "type": "LineString",
                        "coordinates": [[-105.0, 40.025], [-105.0, 40.065]],
                    },
                    properties=RiverProperties(comid=41000002, uparea=200.0),
                ),
            ],
        ),
    )

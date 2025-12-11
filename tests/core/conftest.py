"""
Shared pytest fixtures for core module tests.

Provides synthetic GeoDataFrame fixtures for testing delineation logic
without requiring real MERIT-Hydro data files.
"""

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, Polygon, box


def make_catchment_polygon(
    center_lng: float,
    center_lat: float,
    size_deg: float = 0.05,
) -> Polygon:
    """Create a square catchment polygon centered at given coordinates."""
    half = size_deg / 2
    return box(center_lng - half, center_lat - half, center_lng + half, center_lat + half)


def make_catchments_gdf(
    comids: list[int],
    centers: list[tuple[float, float]],
    sizes: list[float] | None = None,
) -> gpd.GeoDataFrame:
    """
    Create a synthetic catchments GeoDataFrame.

    Args:
        comids: List of COMID identifiers
        centers: List of (lng, lat) centers for each catchment
        sizes: Optional list of polygon sizes in degrees (default 0.05)

    Returns:
        GeoDataFrame indexed by COMID with polygon geometries
    """
    if sizes is None:
        sizes = [0.05] * len(comids)

    geometries = [
        make_catchment_polygon(lng, lat, size)
        for (lng, lat), size in zip(centers, sizes, strict=True)
    ]

    gdf = gpd.GeoDataFrame(
        {"unitarea": [100.0] * len(comids)},
        index=pd.Index(comids, name="COMID"),
        geometry=geometries,
        crs="EPSG:4326",
    )
    return gdf


def make_rivers_gdf(
    comids: list[int],
    downstream_coords: list[tuple[float, float]],
    upstream_connections: list[dict[str, int]],
    upareas: list[float],
) -> gpd.GeoDataFrame:
    """
    Create a synthetic rivers GeoDataFrame with network topology.

    Args:
        comids: List of COMID identifiers
        downstream_coords: List of (lng, lat) for downstream end of each river
        upstream_connections: List of dicts with keys 'up1', 'up2', 'up3', 'up4'
        upareas: List of upstream areas in km2

    Returns:
        GeoDataFrame indexed by COMID with network topology columns
    """
    geometries = [
        LineString([(lng, lat), (lng, lat + 0.04)])  # Simple north-flowing river
        for lng, lat in downstream_coords
    ]

    data = {
        "up1": [c.get("up1", 0) for c in upstream_connections],
        "up2": [c.get("up2", 0) for c in upstream_connections],
        "up3": [c.get("up3", 0) for c in upstream_connections],
        "up4": [c.get("up4", 0) for c in upstream_connections],
        "uparea": upareas,
    }

    gdf = gpd.GeoDataFrame(
        data,
        index=pd.Index(comids, name="COMID"),
        geometry=geometries,
        crs="EPSG:4326",
    )
    return gdf


@pytest.fixture
def single_catchment_network() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """
    Single catchment with no upstream tributaries.

    Scenario: Small headwater basin with only one unit catchment.
    Used to test: is_single_catchment=True path, low snap thresholds

    Network:
        41000001 (terminal, no upstream)
    """
    comid = 41000001
    center = (-105.0, 40.0)

    catchments = make_catchments_gdf(
        comids=[comid],
        centers=[center],
        sizes=[0.1],
    )

    rivers = make_rivers_gdf(
        comids=[comid],
        downstream_coords=[(-105.0, 39.95)],
        upstream_connections=[{"up1": 0, "up2": 0, "up3": 0, "up4": 0}],
        upareas=[25.0],  # Small watershed
    )

    return catchments, rivers


@pytest.fixture
def linear_network() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """
    Linear chain: 3 catchments in sequence (no branching).

    Topology: 41000003 -> 41000002 -> 41000001 (terminal)

    Used to test: Basic upstream traversal, no branching
    """
    comids = [41000001, 41000002, 41000003]
    centers = [
        (-105.0, 40.0),  # Terminal
        (-105.0, 40.05),  # Middle
        (-105.0, 40.10),  # Headwater
    ]

    catchments = make_catchments_gdf(comids=comids, centers=centers)

    rivers = make_rivers_gdf(
        comids=comids,
        downstream_coords=[
            (-105.0, 39.975),
            (-105.0, 40.025),
            (-105.0, 40.075),
        ],
        upstream_connections=[
            {"up1": 41000002, "up2": 0, "up3": 0, "up4": 0},  # Terminal has one upstream
            {"up1": 41000003, "up2": 0, "up3": 0, "up4": 0},  # Middle has one upstream
            {"up1": 0, "up2": 0, "up3": 0, "up4": 0},  # Headwater has none
        ],
        upareas=[500.0, 300.0, 100.0],
    )

    return catchments, rivers


@pytest.fixture
def branching_network() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """
    Y-shaped network: Two tributaries converging.

    Topology:
        41000003 (left tributary)  \\
                                    -> 41000001 (terminal)
        41000002 (right tributary) /

    Used to test: Multiple up1/up2 connections, branching traversal
    """
    comids = [41000001, 41000002, 41000003]
    centers = [
        (-105.0, 40.0),  # Terminal (confluence)
        (-105.03, 40.05),  # Right tributary
        (-104.97, 40.05),  # Left tributary
    ]

    catchments = make_catchments_gdf(comids=comids, centers=centers)

    rivers = make_rivers_gdf(
        comids=comids,
        downstream_coords=[
            (-105.0, 39.975),
            (-105.03, 40.025),
            (-104.97, 40.025),
        ],
        upstream_connections=[
            {"up1": 41000002, "up2": 41000003, "up3": 0, "up4": 0},  # Two tributaries
            {"up1": 0, "up2": 0, "up3": 0, "up4": 0},  # Headwater
            {"up1": 0, "up2": 0, "up3": 0, "up4": 0},  # Headwater
        ],
        upareas=[1000.0, 400.0, 600.0],
    )

    return catchments, rivers


@pytest.fixture
def complex_network() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """
    Complex 7-node network testing all up1-up4 connections.

    Topology:
        41000004  41000005  41000006  41000007
              \\      \\       /       /
               \\      \\     /       /
                 41000002  41000003
                      \\     /
                       \\   /
                     41000001 (terminal)

    Used to test: Deep recursion, all four upstream fields
    """
    comids = [41000001, 41000002, 41000003, 41000004, 41000005, 41000006, 41000007]

    centers = [
        (-105.0, 40.0),  # Terminal
        (-105.02, 40.04),  # Left branch
        (-104.98, 40.04),  # Right branch
        (-105.04, 40.08),  # Far left headwater
        (-105.02, 40.08),  # Mid-left headwater
        (-104.98, 40.08),  # Mid-right headwater
        (-104.96, 40.08),  # Far right headwater
    ]

    catchments = make_catchments_gdf(comids=comids, centers=centers, sizes=[0.04] * 7)

    rivers = make_rivers_gdf(
        comids=comids,
        downstream_coords=[
            (-105.0, 39.98),
            (-105.02, 40.02),
            (-104.98, 40.02),
            (-105.04, 40.06),
            (-105.02, 40.06),
            (-104.98, 40.06),
            (-104.96, 40.06),
        ],
        upstream_connections=[
            {"up1": 41000002, "up2": 41000003, "up3": 0, "up4": 0},
            {"up1": 41000004, "up2": 41000005, "up3": 0, "up4": 0},
            {"up1": 41000006, "up2": 41000007, "up3": 0, "up4": 0},
            {"up1": 0, "up2": 0, "up3": 0, "up4": 0},
            {"up1": 0, "up2": 0, "up3": 0, "up4": 0},
            {"up1": 0, "up2": 0, "up3": 0, "up4": 0},
            {"up1": 0, "up2": 0, "up3": 0, "up4": 0},
        ],
        upareas=[5000.0, 2000.0, 3000.0, 500.0, 500.0, 1000.0, 1000.0],
    )

    return catchments, rivers

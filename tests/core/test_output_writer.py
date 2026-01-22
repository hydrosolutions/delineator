"""
Tests for output writer module.

Uses tmp_path fixture for actual file operations and mock DelineatedWatershed objects.
"""

import csv
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from delineator.core.delineate import DelineatedWatershed
from delineator.core.output_writer import FailedOutlet, OutputFormat, OutputWriter


@pytest.fixture
def sample_watershed() -> DelineatedWatershed:
    """Create a sample DelineatedWatershed for testing."""
    return DelineatedWatershed(
        gauge_id="test_001",
        gauge_name="Test Gauge",
        gauge_lat=40.5,
        gauge_lon=-105.5,
        snap_lat=40.501,
        snap_lon=-105.499,
        snap_dist=150.0,
        country="United States",
        area=1234.5,
        geometry=Polygon([(-106, 40), (-105, 40), (-105, 41), (-106, 41), (-106, 40)]),
        resolution="high_res",
    )


@pytest.fixture
def multiple_watersheds() -> list[DelineatedWatershed]:
    """Create multiple watersheds for testing."""
    return [
        DelineatedWatershed(
            gauge_id="ws_001",
            gauge_name="Watershed One",
            gauge_lat=40.0,
            gauge_lon=-105.0,
            snap_lat=40.001,
            snap_lon=-105.001,
            snap_dist=100.0,
            country="USA",
            area=500.0,
            geometry=Polygon([(-106, 40), (-105, 40), (-105, 41), (-106, 41)]),
            resolution="high_res",
        ),
        DelineatedWatershed(
            gauge_id="ws_002",
            gauge_name="Watershed Two",
            gauge_lat=41.0,
            gauge_lon=-104.0,
            snap_lat=41.001,
            snap_lon=-104.001,
            snap_dist=200.0,
            country="USA",
            area=750.0,
            geometry=Polygon([(-105, 41), (-104, 41), (-104, 42), (-105, 42)]),
            resolution="low_res",
        ),
    ]


class TestFailedOutlet:
    """Tests for FailedOutlet dataclass."""

    def test_create_failed_outlet(self) -> None:
        """Test basic creation of FailedOutlet."""
        failure = FailedOutlet(
            region_name="test_region",
            gauge_id="gauge_001",
            lat=40.5,
            lng=-105.5,
            error="Point outside catchments",
        )

        assert failure.region_name == "test_region"
        assert failure.gauge_id == "gauge_001"
        assert failure.lat == 40.5
        assert failure.lng == -105.5
        assert failure.error == "Point outside catchments"


class TestOutputWriter:
    """Tests for OutputWriter class."""

    def test_init_creates_output_dir_attribute(self, tmp_path: Path) -> None:
        """Test initialization sets output_dir."""
        writer = OutputWriter(output_dir=tmp_path)

        assert writer.output_dir == tmp_path
        assert writer.failed_outlets == []

    def test_get_region_output_dir_creates_structure(self, tmp_path: Path) -> None:
        """Test that get_region_output_dir creates Hive-partitioned structure."""
        writer = OutputWriter(output_dir=tmp_path, output_format=OutputFormat.SHAPEFILE)

        result = writer.get_region_output_dir("test_region")

        expected = tmp_path / "REGION_NAME=test_region" / "data_type=shapefiles"
        assert result == expected
        assert result.exists()
        assert result.is_dir()

    def test_get_region_output_dir_creates_geopackage_structure(self, tmp_path: Path) -> None:
        """Test that get_region_output_dir creates GeoPackage structure by default."""
        writer = OutputWriter(output_dir=tmp_path)

        result = writer.get_region_output_dir("test_region")

        expected = tmp_path / "REGION_NAME=test_region" / "data_type=geopackage"
        assert result == expected
        assert result.exists()
        assert result.is_dir()

    def test_get_region_output_dir_idempotent(self, tmp_path: Path) -> None:
        """Test that calling get_region_output_dir multiple times is safe."""
        writer = OutputWriter(output_dir=tmp_path)

        # Call multiple times
        result1 = writer.get_region_output_dir("test_region")
        result2 = writer.get_region_output_dir("test_region")

        assert result1 == result2

    def test_write_region_shapefile_creates_file(self, tmp_path: Path, sample_watershed: DelineatedWatershed) -> None:
        """Test that shapefile is created."""
        writer = OutputWriter(output_dir=tmp_path, output_format=OutputFormat.SHAPEFILE)

        result = writer.write_region_shapefile(
            region_name="test_region",
            watersheds=[sample_watershed],
        )

        assert result.exists()
        assert result.name == "test_region_shapes.shp"
        # Should also create .dbf, .shx, .prj files
        assert (result.parent / "test_region_shapes.dbf").exists()
        assert (result.parent / "test_region_shapes.shx").exists()

    def test_write_region_output_creates_geopackage(
        self, tmp_path: Path, sample_watershed: DelineatedWatershed
    ) -> None:
        """Test that GeoPackage is created by default."""
        writer = OutputWriter(output_dir=tmp_path)

        result = writer.write_region_output(
            region_name="test_region",
            watersheds=[sample_watershed],
        )

        assert result.exists()
        assert result.name == "test_region.gpkg"
        assert result.suffix == ".gpkg"

    def test_write_region_shapefile_correct_path(self, tmp_path: Path, sample_watershed: DelineatedWatershed) -> None:
        """Test that shapefile is written to Hive-partitioned path."""
        writer = OutputWriter(output_dir=tmp_path, output_format=OutputFormat.SHAPEFILE)

        result = writer.write_region_shapefile(
            region_name="my_region",
            watersheds=[sample_watershed],
        )

        expected_dir = tmp_path / "REGION_NAME=my_region" / "data_type=shapefiles"
        assert result.parent == expected_dir

    def test_write_region_shapefile_multiple_watersheds(
        self, tmp_path: Path, multiple_watersheds: list[DelineatedWatershed]
    ) -> None:
        """Test writing multiple watersheds to single shapefile."""
        writer = OutputWriter(output_dir=tmp_path)

        result = writer.write_region_shapefile(
            region_name="multi_region",
            watersheds=multiple_watersheds,
        )

        assert result.exists()

        # Read back and verify
        import geopandas as gpd

        gdf = gpd.read_file(result)
        assert len(gdf) == 2
        assert set(gdf["gauge_id"]) == {"ws_001", "ws_002"}

    def test_write_region_shapefile_empty_raises(self, tmp_path: Path) -> None:
        """Test that empty watersheds list raises ValueError."""
        writer = OutputWriter(output_dir=tmp_path)

        with pytest.raises(ValueError, match="no watersheds provided"):
            writer.write_region_shapefile(region_name="empty", watersheds=[])

    def test_write_region_shapefile_attributes(self, tmp_path: Path, sample_watershed: DelineatedWatershed) -> None:
        """Test that all attributes are written correctly."""
        writer = OutputWriter(output_dir=tmp_path)

        result = writer.write_region_shapefile(
            region_name="attr_test",
            watersheds=[sample_watershed],
        )

        # Read back and verify attributes
        import geopandas as gpd

        gdf = gpd.read_file(result)
        row = gdf.iloc[0]

        assert row["gauge_id"] == "test_001"
        assert row["gauge_lat"] == 40.5
        assert row["gauge_lon"] == -105.5
        assert row["snap_lat"] == 40.501
        assert row["snap_lon"] == -105.499
        assert row["snap_dist"] == 150.0
        assert row["country"] == "United States"
        assert row["area"] == 1234.5


class TestRecordFailure:
    """Tests for failure recording."""

    def test_record_failure_adds_to_list(self, tmp_path: Path) -> None:
        """Test that record_failure adds to failed_outlets list."""
        writer = OutputWriter(output_dir=tmp_path)

        writer.record_failure(
            region_name="test_region",
            gauge_id="failed_001",
            lat=40.5,
            lng=-105.5,
            error="Point outside all catchments",
        )

        assert len(writer.failed_outlets) == 1
        failure = writer.failed_outlets[0]
        assert failure.gauge_id == "failed_001"
        assert failure.error == "Point outside all catchments"

    def test_record_multiple_failures(self, tmp_path: Path) -> None:
        """Test recording multiple failures."""
        writer = OutputWriter(output_dir=tmp_path)

        writer.record_failure("region1", "gauge_001", 40.0, -105.0, "Error 1")
        writer.record_failure("region2", "gauge_002", 41.0, -106.0, "Error 2")
        writer.record_failure("region1", "gauge_003", 42.0, -107.0, "Error 3")

        assert len(writer.failed_outlets) == 3


class TestWriteFailedCsv:
    """Tests for FAILED.csv writing."""

    def test_write_failed_csv_creates_file(self, tmp_path: Path) -> None:
        """Test that FAILED.csv is created."""
        writer = OutputWriter(output_dir=tmp_path)
        writer.record_failure("region1", "gauge_001", 40.0, -105.0, "Error 1")

        result = writer.write_failed_csv()

        assert result is not None
        assert result.exists()
        assert result.name == "FAILED.csv"

    def test_write_failed_csv_correct_content(self, tmp_path: Path) -> None:
        """Test that CSV content is correct."""
        writer = OutputWriter(output_dir=tmp_path)
        writer.record_failure("region1", "gauge_001", 40.0, -105.0, "Error 1")
        writer.record_failure("region2", "gauge_002", 41.0, -106.0, "Error 2")

        result = writer.write_failed_csv()

        # Read and verify
        with open(result) as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Check header
        assert rows[0] == ["region_name", "gauge_id", "lat", "lng", "error"]

        # Check data rows
        assert len(rows) == 3  # Header + 2 data rows
        assert rows[1] == ["region1", "gauge_001", "40.0", "-105.0", "Error 1"]
        assert rows[2] == ["region2", "gauge_002", "41.0", "-106.0", "Error 2"]

    def test_write_failed_csv_no_failures_returns_none(self, tmp_path: Path) -> None:
        """Test that None is returned when no failures recorded."""
        writer = OutputWriter(output_dir=tmp_path)

        result = writer.write_failed_csv()

        assert result is None
        assert not (tmp_path / "FAILED.csv").exists()

    def test_write_failed_csv_path_in_output_dir(self, tmp_path: Path) -> None:
        """Test that FAILED.csv is written to output_dir root."""
        writer = OutputWriter(output_dir=tmp_path)
        writer.record_failure("region1", "gauge_001", 40.0, -105.0, "Error")

        result = writer.write_failed_csv()

        assert result.parent == tmp_path


class TestFinalize:
    """Tests for finalize method."""

    def test_finalize_writes_failed_csv(self, tmp_path: Path) -> None:
        """Test that finalize calls write_failed_csv."""
        writer = OutputWriter(output_dir=tmp_path)
        writer.record_failure("region1", "gauge_001", 40.0, -105.0, "Error")

        result = writer.finalize()

        assert result is not None
        assert result.name == "FAILED.csv"

    def test_finalize_no_failures_returns_none(self, tmp_path: Path) -> None:
        """Test finalize with no failures."""
        writer = OutputWriter(output_dir=tmp_path)

        result = writer.finalize()

        assert result is None


class TestIntegration:
    """Integration tests for full workflow."""

    def test_full_workflow(self, tmp_path: Path, multiple_watersheds: list[DelineatedWatershed]) -> None:
        """Test complete workflow with successes and failures."""
        writer = OutputWriter(output_dir=tmp_path)

        # Write successful watersheds
        shp_path = writer.write_region_shapefile(
            region_name="success_region",
            watersheds=multiple_watersheds,
        )

        # Record some failures
        writer.record_failure("fail_region", "fail_001", 50.0, -100.0, "Out of bounds")
        writer.record_failure("fail_region", "fail_002", 51.0, -101.0, "Network error")

        # Finalize
        failed_path = writer.finalize()

        # Verify outputs
        assert shp_path.exists()
        assert failed_path is not None
        assert failed_path.exists()

        # Verify shapefile content
        import geopandas as gpd

        gdf = gpd.read_file(shp_path)
        assert len(gdf) == 2

        # Verify CSV content
        with open(failed_path) as f:
            reader = csv.reader(f)
            rows = list(reader)
        assert len(rows) == 3  # Header + 2 failures


class TestReadExistingGaugeIds:
    """Tests for reading existing gauge_ids from output files."""

    def test_returns_empty_set_when_no_file(self, tmp_path: Path) -> None:
        """Test that empty set is returned when output file doesn't exist."""
        writer = OutputWriter(output_dir=tmp_path)

        result = writer.read_existing_gauge_ids("nonexistent_region")

        assert result == set()

    def test_returns_gauge_ids_from_geopackage(
        self, tmp_path: Path, multiple_watersheds: list[DelineatedWatershed]
    ) -> None:
        """Test reading gauge_ids from existing GeoPackage."""
        writer = OutputWriter(output_dir=tmp_path)

        # Write some watersheds
        writer.write_region_output("test_region", multiple_watersheds)

        # Read back gauge_ids
        result = writer.read_existing_gauge_ids("test_region")

        assert result == {"ws_001", "ws_002"}

    def test_returns_gauge_ids_from_shapefile(
        self, tmp_path: Path, multiple_watersheds: list[DelineatedWatershed]
    ) -> None:
        """Test reading gauge_ids from existing Shapefile."""
        writer = OutputWriter(output_dir=tmp_path, output_format=OutputFormat.SHAPEFILE)

        # Write some watersheds
        writer.write_region_output("test_region", multiple_watersheds)

        # Read back gauge_ids
        result = writer.read_existing_gauge_ids("test_region")

        assert result == {"ws_001", "ws_002"}


class TestCheckOutputExists:
    """Tests for checking if output exists."""

    def test_returns_false_when_no_file(self, tmp_path: Path) -> None:
        """Test that False is returned when no output file."""
        writer = OutputWriter(output_dir=tmp_path)

        result = writer.check_output_exists("nonexistent_region")

        assert result is False

    def test_returns_true_when_file_exists(self, tmp_path: Path, sample_watershed: DelineatedWatershed) -> None:
        """Test that True is returned when output file exists."""
        writer = OutputWriter(output_dir=tmp_path)

        # Write a watershed
        writer.write_region_output("test_region", [sample_watershed])

        result = writer.check_output_exists("test_region")

        assert result is True


class TestLoadFailedGaugeIds:
    """Tests for loading failed gauge_ids from FAILED.csv."""

    def test_returns_empty_set_when_no_file(self, tmp_path: Path) -> None:
        """Test that empty set is returned when FAILED.csv doesn't exist."""
        writer = OutputWriter(output_dir=tmp_path)

        result = writer.load_failed_gauge_ids()

        assert result == set()

    def test_returns_gauge_ids_from_failed_csv(self, tmp_path: Path) -> None:
        """Test reading gauge_ids from existing FAILED.csv."""
        writer = OutputWriter(output_dir=tmp_path)

        # Create FAILED.csv
        writer.record_failure("region1", "fail_001", 40.0, -105.0, "Error 1")
        writer.record_failure("region2", "fail_002", 41.0, -106.0, "Error 2")
        writer.write_failed_csv()

        # Create fresh writer (simulating restart)
        writer2 = OutputWriter(output_dir=tmp_path)
        result = writer2.load_failed_gauge_ids()

        assert result == {"fail_001", "fail_002"}


class TestGeoPackageAppendMode:
    """Tests for GeoPackage append mode."""

    def test_append_mode_adds_to_existing(self, tmp_path: Path, multiple_watersheds: list[DelineatedWatershed]) -> None:
        """Test that append mode adds to existing GeoPackage."""
        writer = OutputWriter(output_dir=tmp_path)

        # Write first watershed
        writer.write_region_output("test_region", [multiple_watersheds[0]], mode="w")

        # Append second watershed
        writer.write_region_output("test_region", [multiple_watersheds[1]], mode="a")

        # Read back and verify
        import geopandas as gpd

        output_path = writer.get_output_path("test_region")
        gdf = gpd.read_file(output_path)
        assert len(gdf) == 2
        assert set(gdf["gauge_id"]) == {"ws_001", "ws_002"}

    def test_append_mode_creates_if_not_exists(self, tmp_path: Path, sample_watershed: DelineatedWatershed) -> None:
        """Test that append mode creates file if it doesn't exist."""
        writer = OutputWriter(output_dir=tmp_path)

        # Append to non-existent file should create it
        writer.write_region_output("new_region", [sample_watershed], mode="a")

        output_path = writer.get_output_path("new_region")
        assert output_path.exists()

        import geopandas as gpd

        gdf = gpd.read_file(output_path)
        assert len(gdf) == 1


class TestIncludeRiversOutput:
    """Tests for rivers output in OutputWriter."""

    @pytest.fixture
    def watershed_with_rivers(self) -> DelineatedWatershed:
        """Create a DelineatedWatershed with rivers GeoDataFrame."""
        from shapely.geometry import LineString

        # Create river geometries
        rivers_gdf = gpd.GeoDataFrame(
            {
                "uparea": [500.0, 300.0, 100.0],
                "up1": [41000002, 41000003, 0],
                "up2": [0, 0, 0],
                "up3": [0, 0, 0],
                "up4": [0, 0, 0],
            },
            index=[41000001, 41000002, 41000003],
            geometry=[
                LineString([(-105.0, 39.975), (-105.0, 40.0)]),
                LineString([(-105.0, 40.025), (-105.0, 40.05)]),
                LineString([(-105.0, 40.075), (-105.0, 40.1)]),
            ],
            crs="EPSG:4326",
        )
        rivers_gdf.index.name = "COMID"

        return DelineatedWatershed(
            gauge_id="rivers_001",
            gauge_name="Rivers Test Gauge",
            gauge_lat=40.0,
            gauge_lon=-105.0,
            snap_lat=40.001,
            snap_lon=-105.001,
            snap_dist=100.0,
            country="USA",
            area=500.0,
            geometry=Polygon([(-106, 40), (-105, 40), (-105, 41), (-106, 41)]),
            resolution="low_res",
            rivers=rivers_gdf,
        )

    @pytest.fixture
    def watershed_without_rivers(self) -> DelineatedWatershed:
        """Create a DelineatedWatershed without rivers (rivers=None)."""
        return DelineatedWatershed(
            gauge_id="no_rivers_001",
            gauge_name="No Rivers Gauge",
            gauge_lat=40.5,
            gauge_lon=-105.5,
            snap_lat=40.501,
            snap_lon=-105.499,
            snap_dist=150.0,
            country="United States",
            area=1234.5,
            geometry=Polygon([(-106, 40), (-105, 40), (-105, 41), (-106, 41)]),
            resolution="high_res",
            rivers=None,
        )

    @pytest.fixture
    def watershed_with_empty_rivers(self) -> DelineatedWatershed:
        """Create a DelineatedWatershed with empty rivers GeoDataFrame."""
        empty_rivers = gpd.GeoDataFrame(
            columns=["uparea", "up1", "up2", "up3", "up4", "geometry"],
            crs="EPSG:4326",
        )
        empty_rivers.index.name = "COMID"

        return DelineatedWatershed(
            gauge_id="empty_rivers_001",
            gauge_name="Empty Rivers Gauge",
            gauge_lat=41.0,
            gauge_lon=-104.0,
            snap_lat=41.001,
            snap_lon=-104.001,
            snap_dist=50.0,
            country="USA",
            area=200.0,
            geometry=Polygon([(-105, 41), (-104, 41), (-104, 42), (-105, 42)]),
            resolution="low_res",
            rivers=empty_rivers,
        )

    def test_geopackage_with_rivers_layer(self, tmp_path: Path, watershed_with_rivers: DelineatedWatershed) -> None:
        """GeoPackage should have both watershed and rivers layers."""
        writer = OutputWriter(
            output_dir=tmp_path,
            output_format=OutputFormat.GEOPACKAGE,
            include_rivers=True,
        )

        result_path = writer.write_region_output(
            region_name="test_region",
            watersheds=[watershed_with_rivers],
        )

        assert result_path.exists()
        assert result_path.suffix == ".gpkg"

        # Read the watershed layer (default layer)
        gdf = gpd.read_file(result_path)
        assert len(gdf) == 1
        assert gdf.iloc[0]["gauge_id"] == "rivers_001"

        # Read the rivers layer
        import fiona

        layers = fiona.listlayers(result_path)

        assert "rivers" in layers

        rivers_gdf = gpd.read_file(result_path, layer="rivers")
        assert len(rivers_gdf) == 3
        assert "uparea" in rivers_gdf.columns
        assert "gauge_id" in rivers_gdf.columns  # Added by OutputWriter

    def test_shapefile_with_separate_rivers_file(
        self, tmp_path: Path, watershed_with_rivers: DelineatedWatershed
    ) -> None:
        """Should create {region}_rivers.shp alongside watershed shapefile."""
        writer = OutputWriter(
            output_dir=tmp_path,
            output_format=OutputFormat.SHAPEFILE,
            include_rivers=True,
        )

        result_path = writer.write_region_output(
            region_name="test_region",
            watersheds=[watershed_with_rivers],
        )

        assert result_path.exists()
        assert result_path.name == "test_region_shapes.shp"

        # Check that rivers shapefile was created
        rivers_path = result_path.parent / "test_region_rivers.shp"
        assert rivers_path.exists()

        # Verify rivers shapefile content
        rivers_gdf = gpd.read_file(rivers_path)
        assert len(rivers_gdf) == 3
        assert "uparea" in rivers_gdf.columns
        assert "gauge_id" in rivers_gdf.columns

    def test_backward_compatibility_without_rivers(
        self, tmp_path: Path, watershed_without_rivers: DelineatedWatershed
    ) -> None:
        """When include_rivers=False, no rivers layer/file should be created."""
        writer = OutputWriter(
            output_dir=tmp_path,
            output_format=OutputFormat.GEOPACKAGE,
            include_rivers=False,  # Explicitly set to False
        )

        result_path = writer.write_region_output(
            region_name="test_region",
            watersheds=[watershed_without_rivers],
        )

        assert result_path.exists()

        # Verify no rivers layer in GeoPackage
        import fiona

        layers = fiona.listlayers(result_path)
        assert "rivers" not in layers

    def test_include_rivers_false_ignores_watershed_rivers(
        self, tmp_path: Path, watershed_with_rivers: DelineatedWatershed
    ) -> None:
        """When include_rivers=False, rivers in watershed should be ignored."""
        writer = OutputWriter(
            output_dir=tmp_path,
            output_format=OutputFormat.GEOPACKAGE,
            include_rivers=False,  # Rivers in watershed should be ignored
        )

        result_path = writer.write_region_output(
            region_name="test_region",
            watersheds=[watershed_with_rivers],  # This has rivers, but should be ignored
        )

        assert result_path.exists()

        # Verify no rivers layer in GeoPackage
        import fiona

        layers = fiona.listlayers(result_path)
        assert "rivers" not in layers

    def test_empty_rivers_handled_gracefully_geopackage(
        self, tmp_path: Path, watershed_with_empty_rivers: DelineatedWatershed
    ) -> None:
        """If watershed.rivers is empty GDF, handle gracefully (no rivers layer)."""
        writer = OutputWriter(
            output_dir=tmp_path,
            output_format=OutputFormat.GEOPACKAGE,
            include_rivers=True,
        )

        result_path = writer.write_region_output(
            region_name="test_region",
            watersheds=[watershed_with_empty_rivers],
        )

        assert result_path.exists()

        # Verify watershed data was written
        gdf = gpd.read_file(result_path)
        assert len(gdf) == 1

        # Empty rivers should result in no rivers layer
        import fiona

        layers = fiona.listlayers(result_path)
        # The _build_rivers_geodataframe returns None if rivers is empty
        assert "rivers" not in layers

    def test_empty_rivers_handled_gracefully_shapefile(
        self, tmp_path: Path, watershed_with_empty_rivers: DelineatedWatershed
    ) -> None:
        """If watershed.rivers is empty GDF, no rivers shapefile should be created."""
        writer = OutputWriter(
            output_dir=tmp_path,
            output_format=OutputFormat.SHAPEFILE,
            include_rivers=True,
        )

        result_path = writer.write_region_output(
            region_name="test_region",
            watersheds=[watershed_with_empty_rivers],
        )

        assert result_path.exists()

        # Verify no rivers shapefile was created
        rivers_path = result_path.parent / "test_region_rivers.shp"
        assert not rivers_path.exists()

    def test_multiple_watersheds_rivers_combined(
        self,
        tmp_path: Path,
        watershed_with_rivers: DelineatedWatershed,
    ) -> None:
        """Rivers from multiple watersheds should be combined into one layer."""
        from shapely.geometry import LineString

        # Create a second watershed with different rivers
        rivers_gdf2 = gpd.GeoDataFrame(
            {
                "uparea": [800.0, 400.0],
                "up1": [42000002, 0],
                "up2": [0, 0],
                "up3": [0, 0],
                "up4": [0, 0],
            },
            index=[42000001, 42000002],
            geometry=[
                LineString([(-104.0, 39.975), (-104.0, 40.0)]),
                LineString([(-104.0, 40.025), (-104.0, 40.05)]),
            ],
            crs="EPSG:4326",
        )
        rivers_gdf2.index.name = "COMID"

        watershed2 = DelineatedWatershed(
            gauge_id="rivers_002",
            gauge_name="Rivers Test Gauge 2",
            gauge_lat=40.0,
            gauge_lon=-104.0,
            snap_lat=40.001,
            snap_lon=-104.001,
            snap_dist=100.0,
            country="USA",
            area=800.0,
            geometry=Polygon([(-105, 40), (-104, 40), (-104, 41), (-105, 41)]),
            resolution="low_res",
            rivers=rivers_gdf2,
        )

        writer = OutputWriter(
            output_dir=tmp_path,
            output_format=OutputFormat.GEOPACKAGE,
            include_rivers=True,
        )

        result_path = writer.write_region_output(
            region_name="test_region",
            watersheds=[watershed_with_rivers, watershed2],
        )

        assert result_path.exists()

        # Read the rivers layer
        rivers_gdf = gpd.read_file(result_path, layer="rivers")

        # Should have 5 rivers total (3 from watershed1 + 2 from watershed2)
        assert len(rivers_gdf) == 5

        # Verify gauge_ids are present to track which watershed each river belongs to
        gauge_ids = set(rivers_gdf["gauge_id"])
        assert gauge_ids == {"rivers_001", "rivers_002"}

    def test_mixed_watersheds_with_and_without_rivers(
        self,
        tmp_path: Path,
        watershed_with_rivers: DelineatedWatershed,
        watershed_without_rivers: DelineatedWatershed,
    ) -> None:
        """Mixed watersheds (some with rivers, some without) should work correctly."""
        writer = OutputWriter(
            output_dir=tmp_path,
            output_format=OutputFormat.GEOPACKAGE,
            include_rivers=True,
        )

        result_path = writer.write_region_output(
            region_name="test_region",
            watersheds=[watershed_with_rivers, watershed_without_rivers],
        )

        assert result_path.exists()

        # Verify watershed data
        gdf = gpd.read_file(result_path)
        assert len(gdf) == 2

        # Verify rivers layer only has rivers from watershed_with_rivers
        rivers_gdf = gpd.read_file(result_path, layer="rivers")
        assert len(rivers_gdf) == 3
        assert all(rivers_gdf["gauge_id"] == "rivers_001")

    def test_shapefile_rivers_append_mode(self, tmp_path: Path, watershed_with_rivers: DelineatedWatershed) -> None:
        """Shapefile rivers should be appended correctly in append mode."""
        from shapely.geometry import LineString

        # Create a second watershed with different rivers
        rivers_gdf2 = gpd.GeoDataFrame(
            {
                "uparea": [800.0],
                "up1": [0],
                "up2": [0],
                "up3": [0],
                "up4": [0],
            },
            index=[42000001],
            geometry=[
                LineString([(-104.0, 39.975), (-104.0, 40.0)]),
            ],
            crs="EPSG:4326",
        )
        rivers_gdf2.index.name = "COMID"

        watershed2 = DelineatedWatershed(
            gauge_id="rivers_002",
            gauge_name="Rivers Test Gauge 2",
            gauge_lat=40.0,
            gauge_lon=-104.0,
            snap_lat=40.001,
            snap_lon=-104.001,
            snap_dist=100.0,
            country="USA",
            area=800.0,
            geometry=Polygon([(-105, 40), (-104, 40), (-104, 41), (-105, 41)]),
            resolution="low_res",
            rivers=rivers_gdf2,
        )

        writer = OutputWriter(
            output_dir=tmp_path,
            output_format=OutputFormat.SHAPEFILE,
            include_rivers=True,
        )

        # First write
        writer.write_region_output(
            region_name="test_region",
            watersheds=[watershed_with_rivers],
            mode="w",
        )

        # Append second watershed
        result_path = writer.write_region_output(
            region_name="test_region",
            watersheds=[watershed2],
            mode="a",
        )

        # Verify rivers were appended
        rivers_path = result_path.parent / "test_region_rivers.shp"
        rivers_gdf = gpd.read_file(rivers_path)

        assert len(rivers_gdf) == 4  # 3 from first + 1 from second

    def test_geopackage_rivers_append_mode(self, tmp_path: Path, watershed_with_rivers: DelineatedWatershed) -> None:
        """GeoPackage rivers should be appended correctly in append mode."""
        from shapely.geometry import LineString

        # Create a second watershed with different rivers
        rivers_gdf2 = gpd.GeoDataFrame(
            {
                "uparea": [800.0],
                "up1": [0],
                "up2": [0],
                "up3": [0],
                "up4": [0],
            },
            index=[42000001],
            geometry=[
                LineString([(-104.0, 39.975), (-104.0, 40.0)]),
            ],
            crs="EPSG:4326",
        )
        rivers_gdf2.index.name = "COMID"

        watershed2 = DelineatedWatershed(
            gauge_id="rivers_002",
            gauge_name="Rivers Test Gauge 2",
            gauge_lat=40.0,
            gauge_lon=-104.0,
            snap_lat=40.001,
            snap_lon=-104.001,
            snap_dist=100.0,
            country="USA",
            area=800.0,
            geometry=Polygon([(-105, 40), (-104, 40), (-104, 41), (-105, 41)]),
            resolution="low_res",
            rivers=rivers_gdf2,
        )

        writer = OutputWriter(
            output_dir=tmp_path,
            output_format=OutputFormat.GEOPACKAGE,
            include_rivers=True,
        )

        # First write
        writer.write_region_output(
            region_name="test_region",
            watersheds=[watershed_with_rivers],
            mode="w",
        )

        # Append second watershed
        result_path = writer.write_region_output(
            region_name="test_region",
            watersheds=[watershed2],
            mode="a",
        )

        # Verify rivers were appended
        rivers_gdf = gpd.read_file(result_path, layer="rivers")
        assert len(rivers_gdf) == 4  # 3 from first + 1 from second

    def test_include_rivers_init_parameter(self, tmp_path: Path) -> None:
        """Test that include_rivers parameter is correctly stored."""
        writer_with = OutputWriter(
            output_dir=tmp_path,
            output_format=OutputFormat.GEOPACKAGE,
            include_rivers=True,
        )
        assert writer_with.include_rivers is True

        writer_without = OutputWriter(
            output_dir=tmp_path,
            output_format=OutputFormat.GEOPACKAGE,
            include_rivers=False,
        )
        assert writer_without.include_rivers is False

        # Default should be False
        writer_default = OutputWriter(output_dir=tmp_path)
        assert writer_default.include_rivers is False

"""
Unit tests for the Google Drive download client with bugfix1 support.

Tests cover both the original ZIP format (v1.0) and the individual shapefile
components format (bugfix1), including configuration, file naming, and downloads.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from delineator.download.gdrive_client import (
    FOLDER_IDS,
    OUTPUT_PATTERN,
    PATTERNS,
    SHAPEFILE_EXTENSIONS,
    SHAPEFILE_EXTENSIONS_OPTIONAL,
    SHAPEFILE_EXTENSIONS_REQUIRED,
    DataSource,
    _download_shapefile_components,
    _get_default_data_source,
    download_basin_vectors,
    download_catchments,
    download_rivers,
)

# ============================================================================
# DataSource Enum Tests
# ============================================================================


class TestDataSourceEnum:
    """Tests for DataSource enum configuration."""

    def test_data_source_enum_values(self) -> None:
        """Should have correct string values for each source."""
        assert DataSource.V1_ZIP.value == "v1.0"
        assert DataSource.BUGFIX1.value == "bugfix1"

    def test_data_source_from_string(self) -> None:
        """Should create DataSource from string value."""
        assert DataSource("v1.0") == DataSource.V1_ZIP
        assert DataSource("bugfix1") == DataSource.BUGFIX1

    def test_data_source_invalid_value_raises(self) -> None:
        """Should raise ValueError for invalid string value."""
        with pytest.raises(ValueError):
            DataSource("invalid")


class TestDefaultDataSource:
    """Tests for default data source configuration."""

    def test_default_is_bugfix1(self) -> None:
        """Default data source should be bugfix1 when env var not set."""
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("os.getenv", return_value="bugfix1"),
        ):
            result = _get_default_data_source()
            assert result == DataSource.BUGFIX1

    def test_env_var_v1_zip(self) -> None:
        """Should use v1.0 when MERIT_BASINS_VERSION=v1.0."""
        with patch("os.getenv", return_value="v1.0"):
            result = _get_default_data_source()
            assert result == DataSource.V1_ZIP

    def test_env_var_invalid_falls_back_to_bugfix1(self) -> None:
        """Should fall back to bugfix1 for invalid MERIT_BASINS_VERSION."""
        with patch("os.getenv", return_value="invalid_version"):
            result = _get_default_data_source()
            assert result == DataSource.BUGFIX1


# ============================================================================
# Configuration Constants Tests
# ============================================================================


class TestConfigurationConstants:
    """Tests for configuration constants."""

    def test_folder_ids_defined(self) -> None:
        """Should have folder IDs for all data sources."""
        assert DataSource.V1_ZIP in FOLDER_IDS
        assert DataSource.BUGFIX1 in FOLDER_IDS
        assert FOLDER_IDS[DataSource.V1_ZIP] != ""
        assert FOLDER_IDS[DataSource.BUGFIX1] != ""

    def test_patterns_defined(self) -> None:
        """Should have patterns for all data sources."""
        assert DataSource.V1_ZIP in PATTERNS
        assert DataSource.BUGFIX1 in PATTERNS

        for source in DataSource:
            assert "catchments" in PATTERNS[source]
            assert "rivers" in PATTERNS[source]

    def test_bugfix1_patterns_have_suffix(self) -> None:
        """Bugfix1 patterns should include _bugfix1 suffix."""
        bugfix1_catchments = PATTERNS[DataSource.BUGFIX1]["catchments"]
        bugfix1_rivers = PATTERNS[DataSource.BUGFIX1]["rivers"]

        assert "_bugfix1" in bugfix1_catchments
        assert "_bugfix1" in bugfix1_rivers

    def test_v1_patterns_no_bugfix_suffix(self) -> None:
        """V1 patterns should not include _bugfix1 suffix."""
        v1_catchments = PATTERNS[DataSource.V1_ZIP]["catchments"]
        v1_rivers = PATTERNS[DataSource.V1_ZIP]["rivers"]

        assert "_bugfix1" not in v1_catchments
        assert "_bugfix1" not in v1_rivers

    def test_output_patterns_no_bugfix_suffix(self) -> None:
        """Output patterns should not include _bugfix1 suffix."""
        assert "_bugfix1" not in OUTPUT_PATTERN["catchments"]
        assert "_bugfix1" not in OUTPUT_PATTERN["rivers"]

    def test_shapefile_extensions_complete(self) -> None:
        """Should have all required shapefile extensions."""
        assert ".shp" in SHAPEFILE_EXTENSIONS
        assert ".dbf" in SHAPEFILE_EXTENSIONS
        assert ".shx" in SHAPEFILE_EXTENSIONS
        assert ".prj" in SHAPEFILE_EXTENSIONS
        assert ".cpg" in SHAPEFILE_EXTENSIONS

    def test_shapefile_extensions_required_vs_optional(self) -> None:
        """Should separate required and optional extensions."""
        assert ".shp" in SHAPEFILE_EXTENSIONS_REQUIRED
        assert ".dbf" in SHAPEFILE_EXTENSIONS_REQUIRED
        assert ".shx" in SHAPEFILE_EXTENSIONS_REQUIRED

        assert ".prj" in SHAPEFILE_EXTENSIONS_OPTIONAL
        assert ".cpg" in SHAPEFILE_EXTENSIONS_OPTIONAL


# ============================================================================
# _download_shapefile_components Tests
# ============================================================================


class TestDownloadShapefileComponents:
    """Tests for individual shapefile component download."""

    @pytest.fixture
    def mock_service(self) -> MagicMock:
        """Create a mock Google Drive service."""
        return MagicMock()

    @pytest.fixture
    def temp_dest_dir(self, tmp_path: Path) -> Path:
        """Create a temporary destination directory."""
        dest_dir = tmp_path / "downloads"
        dest_dir.mkdir(parents=True, exist_ok=True)
        return dest_dir

    def test_downloads_all_components(self, mock_service: MagicMock, temp_dest_dir: Path) -> None:
        """Should download all shapefile components."""
        # Mock _find_file_id to return file IDs
        with (
            patch("delineator.download.gdrive_client._find_file_id", return_value="mock_file_id"),
            patch("delineator.download.gdrive_client._download_file") as mock_download,
        ):
            # Track downloaded files
            downloaded_files: list[str] = []

            def track_download(service, file_id, dest_path):
                downloaded_files.append(dest_path.name)
                dest_path.touch()

            mock_download.side_effect = track_download

            _download_shapefile_components(
                service=mock_service,
                folder_id="test_folder_id",
                source_base="cat_pfaf_42_MERIT_Hydro_v07_Basins_v01_bugfix1",
                dest_dir=temp_dest_dir,
                target_base="cat_pfaf_42_MERIT_Hydro_v07_Basins_v01",
                overwrite=False,
            )

            # Should have downloaded all extensions
            assert len(downloaded_files) == len(SHAPEFILE_EXTENSIONS)
            for ext in SHAPEFILE_EXTENSIONS:
                assert f"cat_pfaf_42_MERIT_Hydro_v07_Basins_v01{ext}" in downloaded_files

    def test_renames_files_correctly(self, mock_service: MagicMock, temp_dest_dir: Path) -> None:
        """Downloaded files should be renamed to remove _bugfix1 suffix."""
        with (
            patch("delineator.download.gdrive_client._find_file_id", return_value="mock_file_id"),
            patch("delineator.download.gdrive_client._download_file") as mock_download,
        ):

            def create_file(service, file_id, dest_path):
                dest_path.touch()

            mock_download.side_effect = create_file

            _download_shapefile_components(
                service=mock_service,
                folder_id="test_folder_id",
                source_base="cat_pfaf_42_MERIT_Hydro_v07_Basins_v01_bugfix1",
                dest_dir=temp_dest_dir,
                target_base="cat_pfaf_42_MERIT_Hydro_v07_Basins_v01",
                overwrite=False,
            )

            # Check that files don't have _bugfix1 suffix
            for ext in SHAPEFILE_EXTENSIONS:
                expected_file = temp_dest_dir / f"cat_pfaf_42_MERIT_Hydro_v07_Basins_v01{ext}"
                assert expected_file.exists(), f"Expected {expected_file} to exist"

            # Output directory should not have _bugfix1 in filenames
            for f in temp_dest_dir.iterdir():
                assert "_bugfix1" not in f.name

    def test_raises_on_missing_required(self, mock_service: MagicMock, temp_dest_dir: Path) -> None:
        """Should raise FileNotFoundError if required component is missing."""
        with patch("delineator.download.gdrive_client._find_file_id", return_value=None):
            with pytest.raises(FileNotFoundError) as exc_info:
                _download_shapefile_components(
                    service=mock_service,
                    folder_id="test_folder_id",
                    source_base="nonexistent",
                    dest_dir=temp_dest_dir,
                    target_base="output",
                    overwrite=False,
                )

            assert "Required shapefile components not found" in str(exc_info.value)

    def test_skips_missing_optional(self, mock_service: MagicMock, temp_dest_dir: Path) -> None:
        """Should skip optional extensions (.prj, .cpg) if not found."""

        def mock_find_file(service, folder_id, filename):
            # Return None for optional extensions
            for opt_ext in SHAPEFILE_EXTENSIONS_OPTIONAL:
                if filename.endswith(opt_ext):
                    return None
            return "mock_file_id"

        with (
            patch("delineator.download.gdrive_client._find_file_id", side_effect=mock_find_file),
            patch("delineator.download.gdrive_client._download_file") as mock_download,
        ):

            def create_file(service, file_id, dest_path):
                dest_path.touch()

            mock_download.side_effect = create_file

            # Should not raise
            result = _download_shapefile_components(
                service=mock_service,
                folder_id="test_folder_id",
                source_base="cat_pfaf_42_bugfix1",
                dest_dir=temp_dest_dir,
                target_base="cat_pfaf_42",
                overwrite=False,
            )

            # Should have downloaded only required extensions
            assert result == temp_dest_dir
            downloaded_count = mock_download.call_count
            assert downloaded_count == len(SHAPEFILE_EXTENSIONS_REQUIRED)

    def test_skips_existing_files(self, mock_service: MagicMock, temp_dest_dir: Path) -> None:
        """Should skip download if files already exist and overwrite=False."""
        # Create existing files
        target_base = "cat_pfaf_42_MERIT_Hydro_v07_Basins_v01"
        for ext in SHAPEFILE_EXTENSIONS:
            (temp_dest_dir / f"{target_base}{ext}").touch()

        with (
            patch("delineator.download.gdrive_client._find_file_id") as mock_find,
            patch("delineator.download.gdrive_client._download_file") as mock_download,
        ):
            _download_shapefile_components(
                service=mock_service,
                folder_id="test_folder_id",
                source_base="cat_pfaf_42_MERIT_Hydro_v07_Basins_v01_bugfix1",
                dest_dir=temp_dest_dir,
                target_base=target_base,
                overwrite=False,
            )

            # Should not call download or find_file_id
            mock_find.assert_not_called()
            mock_download.assert_not_called()

    def test_overwrites_when_requested(self, mock_service: MagicMock, temp_dest_dir: Path) -> None:
        """Should re-download if files exist and overwrite=True."""
        # Create existing files
        target_base = "cat_pfaf_42_MERIT_Hydro_v07_Basins_v01"
        for ext in SHAPEFILE_EXTENSIONS:
            (temp_dest_dir / f"{target_base}{ext}").touch()

        with (
            patch("delineator.download.gdrive_client._find_file_id", return_value="mock_file_id"),
            patch("delineator.download.gdrive_client._download_file") as mock_download,
        ):

            def create_file(service, file_id, dest_path):
                dest_path.touch()

            mock_download.side_effect = create_file

            _download_shapefile_components(
                service=mock_service,
                folder_id="test_folder_id",
                source_base="cat_pfaf_42_MERIT_Hydro_v07_Basins_v01_bugfix1",
                dest_dir=temp_dest_dir,
                target_base=target_base,
                overwrite=True,
            )

            # Should call download for all extensions
            assert mock_download.call_count == len(SHAPEFILE_EXTENSIONS)


# ============================================================================
# download_catchments Tests
# ============================================================================


class TestDownloadCatchments:
    """Tests for download_catchments with data source support."""

    @pytest.fixture
    def temp_dest_dir(self, tmp_path: Path) -> Path:
        """Create a temporary destination directory."""
        return tmp_path / "downloads"

    def test_uses_bugfix1_by_default(self, temp_dest_dir: Path) -> None:
        """Should use bugfix1 data source by default."""
        with (
            patch("delineator.download.gdrive_client._get_default_data_source", return_value=DataSource.BUGFIX1),
            patch("delineator.download.gdrive_client._get_credentials"),
            patch("delineator.download.gdrive_client._get_drive_service"),
            patch("delineator.download.gdrive_client._download_shapefile_components") as mock_components,
        ):
            mock_components.return_value = temp_dest_dir

            download_catchments(basin=42, dest_dir=temp_dest_dir)

            # Should call shapefile components download (bugfix1 behavior)
            mock_components.assert_called_once()

    def test_uses_zip_for_v1(self, temp_dest_dir: Path) -> None:
        """Should use ZIP download for v1.0 data source."""
        with (
            patch("delineator.download.gdrive_client._download_and_extract") as mock_extract,
        ):
            mock_extract.return_value = temp_dest_dir / "cat_pfaf_42"

            download_catchments(basin=42, dest_dir=temp_dest_dir, data_source=DataSource.V1_ZIP)

            # Should call ZIP download
            mock_extract.assert_called_once()
            call_args = mock_extract.call_args
            assert ".zip" in call_args.kwargs["filename"]

    def test_accepts_data_source_parameter(self, temp_dest_dir: Path) -> None:
        """Should accept explicit data_source parameter."""
        with (
            patch("delineator.download.gdrive_client._get_credentials"),
            patch("delineator.download.gdrive_client._get_drive_service"),
            patch("delineator.download.gdrive_client._download_shapefile_components") as mock_components,
        ):
            mock_components.return_value = temp_dest_dir

            download_catchments(basin=42, dest_dir=temp_dest_dir, data_source=DataSource.BUGFIX1)

            mock_components.assert_called_once()
            # Check that bugfix1 pattern was used
            call_args = mock_components.call_args
            assert "_bugfix1" in call_args.kwargs["source_base"]

    def test_output_has_no_bugfix_suffix(self, temp_dest_dir: Path) -> None:
        """Output files should not have _bugfix1 suffix."""
        with (
            patch("delineator.download.gdrive_client._get_credentials"),
            patch("delineator.download.gdrive_client._get_drive_service"),
            patch("delineator.download.gdrive_client._download_shapefile_components") as mock_components,
        ):
            mock_components.return_value = temp_dest_dir

            download_catchments(basin=42, dest_dir=temp_dest_dir, data_source=DataSource.BUGFIX1)

            # Check that target_base does NOT have _bugfix1
            call_args = mock_components.call_args
            assert "_bugfix1" not in call_args.kwargs["target_base"]

    def test_skips_if_exists(self, temp_dest_dir: Path) -> None:
        """Should skip download if .shp file already exists."""
        # Create dest directory and .shp file directly in it (no subdirectory)
        temp_dest_dir.mkdir(parents=True, exist_ok=True)
        shp_file = temp_dest_dir / "cat_pfaf_42_MERIT_Hydro_v07_Basins_v01.shp"
        shp_file.touch()

        with (
            patch("delineator.download.gdrive_client._get_credentials") as mock_creds,
        ):
            result = download_catchments(basin=42, dest_dir=temp_dest_dir, data_source=DataSource.BUGFIX1)

            # Should not try to get credentials
            mock_creds.assert_not_called()
            assert result == temp_dest_dir

    def test_invalid_basin_raises(self, temp_dest_dir: Path) -> None:
        """Should raise ValueError for invalid basin code."""
        with pytest.raises(ValueError) as exc_info:
            download_catchments(basin=10, dest_dir=temp_dest_dir)

        assert "Invalid basin code" in str(exc_info.value)


# ============================================================================
# download_rivers Tests
# ============================================================================


class TestDownloadRivers:
    """Tests for download_rivers with data source support."""

    @pytest.fixture
    def temp_dest_dir(self, tmp_path: Path) -> Path:
        """Create a temporary destination directory."""
        return tmp_path / "downloads"

    def test_uses_bugfix1_by_default(self, temp_dest_dir: Path) -> None:
        """Should use bugfix1 data source by default."""
        with (
            patch("delineator.download.gdrive_client._get_default_data_source", return_value=DataSource.BUGFIX1),
            patch("delineator.download.gdrive_client._get_credentials"),
            patch("delineator.download.gdrive_client._get_drive_service"),
            patch("delineator.download.gdrive_client._download_shapefile_components") as mock_components,
        ):
            mock_components.return_value = temp_dest_dir

            download_rivers(basin=42, dest_dir=temp_dest_dir)

            mock_components.assert_called_once()

    def test_rivers_pattern_correct(self, temp_dest_dir: Path) -> None:
        """Should use rivers pattern, not catchments."""
        with (
            patch("delineator.download.gdrive_client._get_credentials"),
            patch("delineator.download.gdrive_client._get_drive_service"),
            patch("delineator.download.gdrive_client._download_shapefile_components") as mock_components,
        ):
            mock_components.return_value = temp_dest_dir

            download_rivers(basin=42, dest_dir=temp_dest_dir, data_source=DataSource.BUGFIX1)

            call_args = mock_components.call_args
            assert "riv_pfaf_42" in call_args.kwargs["source_base"]
            assert "cat_pfaf_42" not in call_args.kwargs["source_base"]


# ============================================================================
# download_basin_vectors Tests
# ============================================================================


class TestDownloadBasinVectors:
    """Tests for download_basin_vectors with data source support."""

    @pytest.fixture
    def temp_dest_dir(self, tmp_path: Path) -> Path:
        """Create a temporary destination directory."""
        return tmp_path / "downloads"

    def test_passes_data_source_to_catchments(self, temp_dest_dir: Path) -> None:
        """Should pass data_source to download_catchments."""
        with (
            patch("delineator.download.gdrive_client.download_catchments") as mock_catchments,
            patch("delineator.download.gdrive_client.download_rivers") as mock_rivers,
        ):
            mock_catchments.return_value = temp_dest_dir / "catchments"
            mock_rivers.return_value = temp_dest_dir / "rivers"

            download_basin_vectors(
                basin=42,
                dest_dir=temp_dest_dir,
                data_source=DataSource.BUGFIX1,
            )

            mock_catchments.assert_called_once()
            assert mock_catchments.call_args.kwargs["data_source"] == DataSource.BUGFIX1

    def test_passes_data_source_to_rivers(self, temp_dest_dir: Path) -> None:
        """Should pass data_source to download_rivers."""
        with (
            patch("delineator.download.gdrive_client.download_catchments") as mock_catchments,
            patch("delineator.download.gdrive_client.download_rivers") as mock_rivers,
        ):
            mock_catchments.return_value = temp_dest_dir / "catchments"
            mock_rivers.return_value = temp_dest_dir / "rivers"

            download_basin_vectors(
                basin=42,
                dest_dir=temp_dest_dir,
                data_source=DataSource.V1_ZIP,
            )

            mock_rivers.assert_called_once()
            assert mock_rivers.call_args.kwargs["data_source"] == DataSource.V1_ZIP

    def test_downloads_both_by_default(self, temp_dest_dir: Path) -> None:
        """Should download both catchments and rivers by default."""
        with (
            patch("delineator.download.gdrive_client.download_catchments") as mock_catchments,
            patch("delineator.download.gdrive_client.download_rivers") as mock_rivers,
        ):
            mock_catchments.return_value = temp_dest_dir / "catchments"
            mock_rivers.return_value = temp_dest_dir / "rivers"

            result = download_basin_vectors(basin=42, dest_dir=temp_dest_dir)

            mock_catchments.assert_called_once()
            mock_rivers.assert_called_once()
            assert "catchments" in result
            assert "rivers" in result


# ============================================================================
# Environment Variable Override Tests
# ============================================================================


class TestEnvironmentVariableOverride:
    """Tests for environment variable configuration."""

    def test_folder_id_env_var_overrides_default(self, tmp_path: Path) -> None:
        """MERIT_BASINS_FOLDER_ID should override default folder ID."""
        custom_folder_id = "custom_folder_12345"

        with (
            patch.dict("os.environ", {"MERIT_BASINS_FOLDER_ID": custom_folder_id}),
            patch("delineator.download.gdrive_client.MERIT_BASINS_FOLDER_ID", custom_folder_id),
            patch("delineator.download.gdrive_client._get_credentials"),
            patch("delineator.download.gdrive_client._get_drive_service"),
            patch("delineator.download.gdrive_client._download_shapefile_components") as mock_components,
        ):
            mock_components.return_value = tmp_path

            download_catchments(basin=42, dest_dir=tmp_path, data_source=DataSource.BUGFIX1)

            # Should use custom folder ID
            call_args = mock_components.call_args
            assert call_args.kwargs["folder_id"] == custom_folder_id

"""
Pytest configuration and shared fixtures for the test suite.
"""

import logging
import sys
from pathlib import Path

import pytest

# Add project root to Python path to enable imports from py/ directory
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture(autouse=True)
def setup_logging() -> None:
    """Configure logging for tests."""
    logging.basicConfig(
        level=logging.WARNING,  # Reduce noise during tests
        format="%(name)s - %(levelname)s - %(message)s",
    )


@pytest.fixture
def sample_basin_codes() -> list[int]:
    """Return a list of sample basin codes for testing."""
    return [11, 42, 45, 67, 89]


@pytest.fixture
def iceland_bbox() -> tuple[float, float, float, float]:
    """Return bounding box coordinates for Iceland."""
    return (-25.0, 63.0, -13.0, 67.0)


@pytest.fixture
def test_data_dir(tmp_path: Path) -> Path:
    """Create a temporary test data directory."""
    data_dir = tmp_path / "test_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir

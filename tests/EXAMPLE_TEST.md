# Example: Adding New Tests

## Basic Test Template

```python
"""Tests for my_new_module."""

from pathlib import Path
from unittest.mock import patch

import pytest

from py.my_module import my_function


class TestMyFunction:
    """Tests for my_function."""

    def test_my_function_returns_expected_value(self) -> None:
        """Should return expected value for valid input."""
        result = my_function(input_value=42)

        assert result == "expected output"
        assert isinstance(result, str)

    def test_my_function_raises_on_invalid_input(self) -> None:
        """Should raise ValueError for invalid input."""
        with pytest.raises(ValueError) as exc_info:
            my_function(input_value=-1)

        assert "invalid" in str(exc_info.value).lower()

    @pytest.fixture
    def sample_data(self) -> dict[str, int]:
        """Create sample test data."""
        return {"key1": 1, "key2": 2}

    def test_my_function_with_fixture(self, sample_data: dict[str, int]) -> None:
        """Should process fixture data correctly."""
        result = my_function(data=sample_data)

        assert result is not None
```

## Mocking External Dependencies

### Mock a Function
```python
from unittest.mock import patch

def test_with_mocked_function() -> None:
    """Should use mocked function."""
    with patch("py.my_module.external_function") as mock_func:
        mock_func.return_value = "mocked value"

        result = code_under_test()

        assert result == "expected"
        mock_func.assert_called_once_with(expected_arg)
```

### Mock File Operations
```python
from pathlib import Path
from unittest.mock import mock_open, patch

def test_with_mocked_file() -> None:
    """Should read file content."""
    mock_content = "file content"

    with patch("builtins.open", mock_open(read_data=mock_content)):
        result = read_my_file(Path("test.txt"))

        assert result == mock_content
```

### Mock HTTP Requests
```python
from unittest.mock import patch
import httpx

def test_with_mocked_http() -> None:
    """Should handle HTTP download."""
    with patch("py.my_module._download_file") as mock_download:
        download_data(url="https://example.com/file.zip")

        mock_download.assert_called_once()
        call_args = mock_download.call_args
        assert "example.com" in call_args[0][0]
```

## Parametrized Tests

Test multiple inputs with one test function:

```python
import pytest

@pytest.mark.parametrize(
    "input_value,expected",
    [
        (0, "zero"),
        (1, "one"),
        (2, "two"),
        (10, "ten"),
    ],
)
def test_number_to_word(input_value: int, expected: str) -> None:
    """Should convert numbers to words."""
    result = number_to_word(input_value)
    assert result == expected
```

## Testing Exceptions

```python
def test_function_raises_value_error() -> None:
    """Should raise ValueError with specific message."""
    with pytest.raises(ValueError) as exc_info:
        dangerous_function(invalid_input)

    # Check error message contains expected text
    assert "expected error message" in str(exc_info.value)
```

## Testing with Temporary Files

```python
def test_with_temp_file(tmp_path: Path) -> None:
    """Should create file in temp directory."""
    # tmp_path is automatically provided by pytest
    test_file = tmp_path / "test.txt"
    test_file.write_text("test content")

    result = process_file(test_file)

    assert result is not None
    assert test_file.exists()
```

## Async Tests

```python
import pytest

@pytest.mark.asyncio
async def test_async_function() -> None:
    """Should handle async operation."""
    result = await async_download_data()

    assert result is not None
```

## Testing with Custom Fixtures

Add to `conftest.py`:

```python
import pytest
from pathlib import Path

@pytest.fixture
def mock_config_file(tmp_path: Path) -> Path:
    """Create a mock configuration file."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text('''
        setting1: value1
        setting2: value2
    ''')
    return config_path
```

Use in tests:

```python
def test_with_config(mock_config_file: Path) -> None:
    """Should load configuration."""
    config = load_config(mock_config_file)

    assert config["setting1"] == "value1"
```

## Running Your New Tests

```bash
# Run just your new test file
uv run pytest tests/test_my_new_module.py -v

# Run just one test class
uv run pytest tests/test_my_new_module.py::TestMyFunction -v

# Run just one test
uv run pytest tests/test_my_new_module.py::TestMyFunction::test_my_function_returns_expected_value -v

# Run with coverage
uv run pytest tests/test_my_new_module.py --cov=py.my_module
```

## Best Practices Checklist

- [ ] Test function name starts with `test_`
- [ ] Test has a descriptive docstring
- [ ] All parameters have type hints
- [ ] Return type is annotated as `-> None`
- [ ] Assertions are clear and specific
- [ ] External dependencies are mocked
- [ ] Test is focused on one behavior
- [ ] Error cases are tested
- [ ] Edge cases are covered

## Common Patterns from test_download.py

### Pattern 1: Mock GeoDataFrame
```python
@pytest.fixture
def mock_gdf(self) -> gpd.GeoDataFrame:
    """Create mock GeoDataFrame."""
    gdf = gpd.GeoDataFrame(
        {"column": [1, 2, 3]},
        geometry=[...],
        crs="EPSG:4326",
    )
    return gdf

def test_with_gdf(self, mock_gdf: gpd.GeoDataFrame) -> None:
    """Should process GeoDataFrame."""
    with patch("module._load_gdf", return_value=mock_gdf):
        result = function_using_gdf()
        assert result is not None
```

### Pattern 2: Test Success/Failure Properties
```python
def test_result_success_property(self) -> None:
    """Result.success should be True when no errors."""
    result = MyResult(errors=[])
    assert result.success is True

def test_result_failure_property(self) -> None:
    """Result.success should be False when errors exist."""
    result = MyResult(errors=["Error 1"])
    assert result.success is False
```

### Pattern 3: Test Retry Logic
```python
def test_retries_on_failure(self) -> None:
    """Should retry on failure."""
    with patch("module.operation") as mock_op:
        # Fail twice, succeed on third attempt
        mock_op.side_effect = [
            Exception("Error 1"),
            Exception("Error 2"),
            "success",
        ]

        with patch("time.sleep"):  # Skip actual sleep
            result = retry_operation()

        assert mock_op.call_count == 3
        assert result == "success"
```

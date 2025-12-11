# Testing Guide

## Quick Start

Run all tests:

```bash
uv run pytest tests/
```

Run tests with verbose output:

```bash
uv run pytest tests/ -v
```

Run specific test file:

```bash
uv run pytest tests/test_download.py -v
```

Run specific test class:

```bash
uv run pytest tests/test_download.py::TestBasinSelector -v
```

Run specific test:

```bash
uv run pytest tests/test_download.py::TestBasinSelector::test_get_all_basin_codes_returns_61_basins -v
```

## Coverage Reports

Generate coverage report:

```bash
uv run pytest tests/ --cov=py --cov-report=term-missing
```

Generate HTML coverage report:

```bash
uv run pytest tests/ --cov=py --cov-report=html
open htmlcov/index.html
```

## Useful Pytest Options

- `-v` or `--verbose`: Verbose output showing each test name
- `-s`: Show print statements (don't capture stdout)
- `-x`: Stop after first failure
- `--lf`: Run only tests that failed last time
- `--ff`: Run failed tests first, then the rest
- `-k EXPRESSION`: Run tests matching the expression (e.g., `-k "basin"`)
- `--tb=short`: Shorter traceback format
- `--tb=line`: Even shorter traceback (one line per failure)
- `-n auto`: Run tests in parallel (requires pytest-xdist: `uv add --dev pytest-xdist`)

## Writing New Tests

### Test File Naming

- Test files must start with `test_` or end with `_test.py`
- Place in the `tests/` directory

### Test Function Naming

- Test functions must start with `test_`
- Use descriptive names that explain what is being tested
- Example: `test_download_raster_invalid_type`

### Test Class Naming

- Test classes must start with `Test`
- Group related tests together
- Example: `TestBasinSelector`, `TestHttpClient`

### Example Test Structure

```python
class TestMyModule:
    \"\"\"Tests for my module.\"\"\"

    @pytest.fixture
    def sample_data(self) -> dict[str, int]:
        \"\"\"Create sample test data.\"\"\"
        return {"key": 42}

    def test_something_works(self, sample_data: dict[str, int]) -> None:
        \"\"\"Should verify that something works correctly.\"\"\"
        result = my_function(sample_data)
        assert result == expected_value
```

## Test Organization

### `/tests/test_download.py`

Comprehensive tests for the download module including:

- Basin selector functionality
- HTTP client operations
- Download orchestration
- Integration tests

### `/tests/conftest.py`

Shared pytest fixtures and configuration:

- Logging setup
- Common test data fixtures
- Temporary directory fixtures

## Mocking Strategy

Tests use Python's `unittest.mock` to mock external dependencies:

```python
from unittest.mock import patch, MagicMock

def test_with_mock():
    with patch('module.function') as mock_func:
        mock_func.return_value = "mocked value"
        result = code_under_test()
        assert result == "expected"
        mock_func.assert_called_once()
```

## Common Assertions

```python
# Equality
assert result == expected

# Exceptions
with pytest.raises(ValueError) as exc_info:
    function_that_raises()
assert "error message" in str(exc_info.value)

# Boolean
assert condition is True
assert condition is False

# Collections
assert len(items) == 5
assert item in collection
assert collection == [1, 2, 3]

# Path/File
assert path.exists()
assert path.is_file()
assert path.is_dir()
```

## Debugging Failed Tests

1. Run with verbose output and full traceback:

   ```bash
   uv run pytest tests/test_download.py -vv --tb=long
   ```

2. Drop into debugger on failure:

   ```bash
   uv run pytest tests/test_download.py --pdb
   ```

3. Show print statements:

   ```bash
   uv run pytest tests/test_download.py -s
   ```

4. Run only failed tests from last run:

   ```bash
   uv run pytest tests/ --lf
   ```

## Best Practices

1. **Test one thing per test**: Each test should verify a single behavior
2. **Use descriptive names**: Test names should clearly state what is being tested
3. **Add docstrings**: Explain what the test verifies
4. **Mock external dependencies**: Don't make real HTTP requests or access external services
5. **Use fixtures**: Share common setup code via pytest fixtures
6. **Test edge cases**: Include tests for error conditions and boundary cases
7. **Keep tests fast**: Mocked tests should run in milliseconds
8. **Follow project conventions**: Use type hints, follow CLAUDE.md guidelines

## Continuous Integration

Tests should pass before committing:

```bash
# Run linting
uv run ruff check py/ tests/

# Run formatting check
uv run ruff format --check py/ tests/

# Run tests
uv run pytest tests/

# All together
uv run ruff check py/ tests/ && uv run ruff format --check py/ tests/ && uv run pytest tests/
```

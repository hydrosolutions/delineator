# Quick Start - Running Tests

## Installation

Ensure dev dependencies are installed:

```bash
uv sync
```

## Run All Tests

```bash
uv run pytest tests/ -v
```

Expected output:

```
==================== test session starts ====================
tests/test_download.py::TestBasinSelector::test_get_all_basin_codes_returns_61_basins PASSED
tests/test_download.py::TestBasinSelector::test_get_all_basin_codes_range PASSED
tests/test_download.py::TestBasinSelector::test_validate_basin_codes_valid PASSED
...
==================== 42 passed in 2.35s ====================
```

## Run Specific Test Module

```bash
uv run pytest tests/test_download.py -v
```

## Run With Coverage

```bash
uv run pytest tests/ --cov=py.download --cov-report=term-missing
```

This shows which lines are not covered by tests.

## Common Issues

### Import Errors

If you see `ModuleNotFoundError: No module named 'py'`:

- Ensure you're running from the project root directory
- Check that `py/__init__.py` exists
- Verify `pythonpath = ["."]` is in `pyproject.toml` under `[tool.pytest.ini_options]`

### Shapefile Not Found

Some tests mock the shapefile loading. If you see shapefile errors:

- The tests should be using mocks - check that patches are applied correctly
- Real shapefile is at: `data/shp/basins_level2/merit_hydro_vect_level2.shp`

## Next Steps

- See `TESTING_GUIDE.md` for detailed testing instructions
- See `README.md` for test structure documentation
- See `TEST_SUMMARY.md` for test coverage overview

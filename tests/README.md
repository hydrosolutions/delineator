# Test Suite

This directory contains comprehensive unit tests for the delineator package.

## Running Tests

To run all tests:

```bash
uv run pytest tests/
```

To run tests for a specific module:

```bash
uv run pytest tests/test_download.py -v
```

To run tests with coverage:

```bash
uv run pytest tests/ --cov=py --cov-report=html
```

## Test Structure

### `test_download.py`

Comprehensive tests for the download module covering:

#### Basin Selector Tests (`TestBasinSelector`)

- `test_get_all_basin_codes_returns_61_basins` - Verifies 61 basins are returned
- `test_get_all_basin_codes_range` - Validates basin codes are between 11-91
- `test_validate_basin_codes_valid` - Ensures valid codes pass validation
- `test_validate_basin_codes_invalid` - Ensures invalid codes raise errors
- `test_validate_basin_codes_multiple_invalid` - Tests multiple invalid codes
- `test_get_basins_for_bbox_iceland` - Tests Iceland bbox returns basin 27
- `test_get_basins_for_bbox_invalid_coords` - Validates coordinate checking
- `test_get_basins_for_bbox_no_intersection` - Tests empty results
- `test_get_basins_for_bbox_multiple_basins` - Tests multiple basin intersection
- `test_get_basins_for_bbox_custom_shapefile_path` - Tests custom shapefile paths

#### HTTP Client Tests (`TestHttpClient`)

- `test_download_raster_invalid_type` - Validates raster type checking
- `test_download_raster_invalid_basin_code` - Validates basin code checking
- `test_download_raster_url_construction_flowdir` - Verifies flowdir URL construction
- `test_download_raster_url_construction_accum` - Verifies accum URL construction
- `test_download_raster_creates_directory` - Tests directory creation
- `test_download_raster_skip_if_exists` - Tests overwrite=False behavior
- `test_download_raster_overwrite_if_exists` - Tests overwrite=True behavior
- `test_download_raster_retries_on_failure` - Tests retry mechanism
- `test_download_raster_fails_after_max_retries` - Tests retry limit
- `test_download_simplified_catchments_url` - Tests simplified catchments download
- `test_download_simplified_catchments_skip_if_exists` - Tests skip existing files

#### Downloader Tests (`TestDownloader`)

- `test_download_result_success_property` - Tests success property when no errors
- `test_download_result_failure_property` - Tests success property with errors
- `test_download_result_default_values` - Tests default initialization
- `test_download_data_requires_bbox_or_basins` - Tests parameter validation
- `test_download_data_with_basins` - Tests basin-based download
- `test_download_data_with_bbox` - Tests bbox-based download
- `test_download_data_basins_takes_precedence` - Tests parameter priority
- `test_download_data_invalid_basins` - Tests error handling for invalid basins
- `test_download_data_no_basins_found_for_bbox` - Tests empty bbox results
- `test_download_data_selective_downloads` - Tests include_* flags
- `test_download_data_error_collection` - Tests error aggregation
- `test_get_output_paths` - Tests output directory structure
- `test_download_data_creates_output_directories` - Tests directory creation
- `test_download_data_basins_downloaded_list` - Tests basin tracking
- `test_download_data_converts_output_dir_to_path` - Tests string/Path conversion

#### Integration Tests (`TestDownloadIntegration`)

- `test_end_to_end_download_workflow` - Tests complete download workflow
- `test_download_with_mixed_success_and_failures` - Tests partial success scenarios

## Testing Strategy

All tests follow these principles:

1. **Mocking External Dependencies**: HTTP requests and file I/O are mocked to ensure tests are fast and don't require network access
2. **Type Annotations**: All test functions use proper type hints
3. **Descriptive Names**: Test names clearly describe what is being tested
4. **Docstrings**: Each test has a docstring explaining its purpose
5. **Fixtures**: Pytest fixtures are used for common test data
6. **Error Cases**: Both success and failure scenarios are tested

## Coverage

The test suite provides comprehensive coverage of:

- Basin selection logic
- HTTP download functionality
- Download orchestration
- Error handling and retries
- Input validation
- File system operations (mocked)

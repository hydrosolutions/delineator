# Bug Report: `validate_basin_codes` return value mishandled in CLI

## Summary

The `download` command incorrectly rejects valid basin codes due to a misunderstanding of the `validate_basin_codes()` function contract.

## Reproduction

```bash
uv run delineator download --basins 12 --dry-run
```

**Expected:** Dry-run output showing basin 12 would be downloaded
**Actual:** `Error: Invalid basin codes: 12`

## Root Cause

**File:** `src/delineator/cli/main.py` lines 533-537

```python
invalid = validate_basin_codes(basin_codes)
if invalid:
    console.print(f"[red]Error:[/red] Invalid basin codes: {', '.join(map(str, invalid))}")
    console.print("\n[yellow]Hint:[/yellow] Use 'delineator list-basins' to see all valid codes")
    raise typer.Exit(2)
```

The code assumes `validate_basin_codes()` returns a list of *invalid* codes, but the actual contract (see `basin_selector.py:182-217`) is:

- **On success:** Returns the same list of codes (validated)
- **On failure:** Raises `ValueError` with details about invalid codes

So when `[12]` is passed:

1. Validation succeeds, returns `[12]`
2. `invalid = [12]` is truthy
3. The error branch executes, incorrectly reporting `12` as invalid

## Suggested Fix

Wrap the call in try/except to catch `ValueError`:

```python
try:
    validate_basin_codes(basin_codes)
except ValueError as e:
    console.print(f"[red]Error:[/red] {e}")
    console.print("\n[yellow]Hint:[/yellow] Use 'delineator list-basins' to see all valid codes")
    raise typer.Exit(2) from None
```

## Impact

- **Severity:** High - completely blocks the `--basins` flag from working
- **Affected command:** `delineator download --basins`
- **Workaround:** Use `--bbox` instead of `--basins`

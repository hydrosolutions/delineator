# CLAUDE.md — Development Guidelines

This document defines the **mandatory practices** for Python development in this repository. These are not suggestions — they are rules. Deviations must be justified with strong technical reasons and agreed upon in review.

---

## Python Package Management with `uv`

* **Use `uv` exclusively** for Python package management.
* Do **not** use `pip`, `pip-tools`, `poetry`, or `conda` directly.
* Commands you should know:

  * Install: `uv add <package>`
  * Remove: `uv remove <package>`
  * Sync lockfile: `uv sync`
* Running:

  * Python scripts: `uv run <script>.py`
  * Tools: `uv run pytest`, `uv run ruff`
  * REPL: `uv run python`

---

## Python Coding Style

### Type Hints (mandatory)

* Always annotate function parameters and return types.
* Use built-in generics (`list`, `dict`, `tuple`, `set`) — **never** import `List`, `Dict`, etc. from `typing`.
* Use `|` for unions (Python 3.10+).
* Annotate variables where type is not obvious.

```python
def process_data(items: list[str]) -> dict[str, int]:
    ...

value: str | None = None
```

### Error Handling

* **Never** use bare `except`.
* Always raise meaningful errors with context.
* Prefer explicit error classes over generic `Exception`.

### Logging

* Use `logging` — never `print` — for runtime diagnostics.

### Formatting & Linting

* Use `ruff` for both linting and formatting:

  * Format: `uv run ruff format`
  * Lint + fix: `uv run ruff check --fix`

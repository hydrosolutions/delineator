# Claude Agent Guidelines

## Documentation Requirements

### Purpose

Maintain LLM-oriented documentation so Claude can efficiently explore and understand the codebase without reading every file.

### File-level documentation

Every `.py` file must have a module-level docstring at the top describing what the file does.

### Module-level documentation

Every module directory must contain a `doc.md` file with YAML frontmatter:

```markdown
---
module: <module-name>
description: <1-2 sentence description of module purpose and responsibility>
---

## Files

- `file1.py` - Brief description
- `file2.py` - Brief description

## Key Interfaces

- `ClassName` - What it does
- `function_name()` - What it does
```

When exploring a module, read its `doc.md` first to understand scope before diving into files. Update `doc.md` only when explicitly asked.

### Project-level documentation

The `docs/` folder contains user-facing and architectural documentation.

---

## Tooling

### Python Package Management with `uv`

Use `uv` exclusively. Do not use `pip`, `pip-tools`, `poetry`, or `conda`.

Commands:

- Install: `uv add <package>`
- Remove: `uv remove <package>`
- Sync: `uv sync`

Running:

- Scripts: `uv run <script>.py`
- Tools: `uv run pytest`, `uv run ruff`
- REPL: `uv run python`

### Formatting & Linting

Use `ruff` for both:

- Format: `uv run ruff format`
- Lint + fix: `uv run ruff check --fix`

### Ad-hoc Analyses

Use shell heredoc syntax for one-time scripts. Do not create throwaway `.py` files.

```bash
uv run python3 << 'EOF'
import pandas as pd

df = pd.read_csv('data.csv')
print(df.describe())
EOF
```

---

## Code Style

### Type Hints (mandatory)

- Annotate function parameters and return types
- Use built-in generics (`list`, `dict`, `tuple`, `set`) - never import `List`, `Dict` from `typing`
- Use `|` for unions (Python 3.10+)

```python
def process_data(items: list[str]) -> dict[str, int]:
    ...

value: str | None = None
```

### Error Handling

- Never use bare `except`
- Raise meaningful errors with context

### Logging

Use `logging` - never `print` - for runtime diagnostics.

### Testability

Never use `datetime.now()` or `random.random()` directly in business logic. Inject dependencies:

```python
# ❌ Wrong
def create_record():
    return {"created_at": datetime.now()}

# ✅ Correct
def create_record(clock: Callable[[], datetime]) -> dict:
    return {"created_at": clock()}
```

---

## Task Management

### Avoid Task Jags

**Critical**: Avoid task jags at all cost. Jags are semantic changes in task direction:

- Going from implementing A to testing A
- Switching from implementing A to implementing B
- Any mid-stream change in the core task focus

Stay focused on the current task until completion.

### Delegation Strategy

Delegate orthogonal tasks to sub-agents aggressively (3+ agents at a time). Remain at a higher level of abstraction and coordination, resisting the temptation to jump in yourself for quick fixes.

- Break down complex work into focused sub-tasks
- Route each sub-task to the specialist agent best suited for it
- Maintain clear task boundaries between agents
- Give agents all the context they need

### Workflow Principles

- Ask clarifying questions before implementing
- Design the shape of the solution (signatures, data structures) before writing logic
- Parallelize independent work

---

## Context Awareness

Use all skills that make semantic sense for the task.

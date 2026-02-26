---
name: python-dev
description: "Python development guidance with code quality standards, error handling, testing practices, and environment management. Use when writing, reviewing, or modifying Python code (.py files) or Jupyter notebooks (.ipynb files)."
---

# Python Development Rules

## Overview
Python development guidance focused on code quality, error handling, testing, and environment management. Apply when working with Python code or Jupyter notebooks.

## When to Use This Skill

Use this skill when:
- Writing new Python code or modifying existing Python files
- Creating or updating Jupyter notebooks
- Setting up Python development environments
- Writing or updating tests
- Reviewing Python code for quality and best practices

## Code Quality

### Principles
- **DRY (Don't Repeat Yourself)**: Avoid code duplication
- **Composition over inheritance**: Prefer composition patterns
- **Pure functions when possible**: Functions without side effects
- **Simple solutions over clever ones**: Prioritize readability and maintainability
- **Design for common use cases first**: Solve the primary problem before edge cases

### Style & Documentation
- **Type hints required**: All functions must include type annotations
- **snake_case naming**: Use snake_case for variables, functions, and modules
- **Google-style docstrings**: Document functions, classes, and modules using Google-style docstrings
- **Keep functions small**: Single responsibility principle - one function, one purpose
- **Preserve existing comments**: Maintain and update existing code comments

### Example

```python
def calculate_total(items: list[dict[str, float]], tax_rate: float = 0.08) -> float:
    """Calculate total cost including tax.
    
    Args:
        items: List of items with 'price' key
        tax_rate: Tax rate as decimal (default 0.08)
        
    Returns:
        Total cost including tax
        
    Raises:
        ValueError: If tax_rate is negative or items list is empty
    """
    if not items:
        raise ValueError("Items list cannot be empty")
    if tax_rate < 0:
        raise ValueError("Tax rate cannot be negative")
    
    subtotal = sum(item['price'] for item in items)
    return subtotal * (1 + tax_rate)
```

## Error Handling & Efficiency

### Error Handling
- **Specific exception types**: Catch specific exceptions, not bare `except`
- **Validate inputs early**: Check inputs at function entry
- **No bare except**: Always specify exception types

### Efficiency Patterns
- **f-strings**: Use f-strings for string formatting
- **Comprehensions**: Prefer list/dict/set comprehensions over loops when appropriate
- **Context managers**: Use `with` statements for resource management

### Example

```python
def process_file(file_path: str) -> list[str]:
    """Process file and return lines.
    
    Args:
        file_path: Path to file
        
    Returns:
        List of non-empty lines
        
    Raises:
        FileNotFoundError: If file doesn't exist
        PermissionError: If file cannot be read
    """
    if not file_path:
        raise ValueError("File path cannot be empty")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {file_path}")
    except PermissionError:
        raise PermissionError(f"Permission denied: {file_path}")
```

## Testing (Critical)

### Framework & Structure
- **pytest only**: Use pytest exclusively (no unittest)
- **Test location**: All tests in `./tests/` directory
- **Test package**: Include `__init__.py` in tests directory
- **TDD approach**: Write/update tests for all new/modified code
- **All tests must pass**: Ensure all tests pass before task completion

### Test Structure Example

```
project/
├── src/
│   └── my_module.py
└── tests/
    ├── __init__.py
    └── test_my_module.py
```

### Example Test

```python
# tests/test_calculations.py
import pytest
from src.calculations import calculate_total

def test_calculate_total_basic():
    """Test basic total calculation."""
    items = [{'price': 10.0}, {'price': 20.0}]
    result = calculate_total(items, tax_rate=0.1)
    assert result == 33.0

def test_calculate_total_empty_list():
    """Test error handling for empty list."""
    with pytest.raises(ValueError, match="Items list cannot be empty"):
        calculate_total([])

def test_calculate_total_negative_tax():
    """Test error handling for negative tax rate."""
    items = [{'price': 10.0}]
    with pytest.raises(ValueError, match="Tax rate cannot be negative"):
        calculate_total(items, tax_rate=-0.1)
```

## Environment Management

### Dependency Management
- **Use uv exclusively**: All packaging, environment, and script execution via [uv](https://github.com/astral-sh/uv)
- **No pip/venv/conda**: Do not use `pip`, `python3 -m venv`, or `conda` — `uv` handles all of this
- **pyproject.toml is the source of truth**: Define all dependencies in `pyproject.toml` (not `requirements.txt`)

### Environment Setup Example

```bash
# Install dependencies from pyproject.toml
uv sync

# Install with optional dev dependencies
uv sync --extra dev

# Run a script (no activation needed)
uv run python script.py

# Run pytest
uv run pytest

# Add a new dependency
uv add requests

# Remove a dependency
uv remove requests
```

### Running Python Code
- Use `uv run` to execute scripts — no manual venv activation needed
- Use `uv run <tool>` for dev tools (pytest, ruff, etc.)
- Dependencies are defined in `pyproject.toml` (not requirements.txt)

### Linting & Formatting (Ruff)
- **Ruff**: Use Ruff for linting AND formatting (replaces flake8, black, isort)

```bash
# Lint code
uv run ruff check .

# Lint and auto-fix
uv run ruff check --fix .

# Format code
uv run ruff format .

# Check formatting without changes
uv run ruff format --check .
```

### Type Checking (Pyright)

```bash
# Check types
uv run pyright
```

Note: Use `pyright` for type checking — do not use `mypy`.

## Best Practices Summary

1. **Code Quality**: DRY, composition, pure functions, simple solutions
2. **Style**: Type hints, snake_case, Google docstrings, small functions
3. **Errors**: Specific exceptions, early validation, no bare except
4. **Efficiency**: f-strings, comprehensions, context managers
5. **Testing**: pytest only, TDD, tests in `./tests/`, all must pass
6. **Environment**: Use `uv` exclusively for dependencies and execution, Ruff for linting/formatting, Pyright for type checking


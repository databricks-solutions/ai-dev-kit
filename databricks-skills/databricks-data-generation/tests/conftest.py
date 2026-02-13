"""Shared fixtures for databricks-data-generation tests."""

from pathlib import Path

import pytest

from helpers import SCHEMAS_DIR, load_schema

# ── Fixtures ────────────────────────────────────────────────────────────────
_schema_paths = sorted(SCHEMAS_DIR.glob("*.json"))


@pytest.fixture(params=_schema_paths, ids=[p.stem for p in _schema_paths])
def schema_path(request) -> Path:
    """Parametrized fixture yielding each schema JSON path."""
    return request.param


@pytest.fixture
def schema(schema_path) -> dict:
    """Parsed JSON for the current schema_path."""
    return load_schema(schema_path)

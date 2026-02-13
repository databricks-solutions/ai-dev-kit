"""Shared constants and helpers for databricks-data-generation tests."""

import importlib.util
import json
from functools import lru_cache
from pathlib import Path

# ── Path constants ──────────────────────────────────────────────────────────
SKILL_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = SKILL_ROOT / "assets" / "schemas"
GENERATORS_DIR = SKILL_ROOT / "scripts" / "generators" / "polars"

# ── Validation constants ────────────────────────────────────────────────────
VALID_INDUSTRIES = {"retail", "healthcare", "financial", "iot", "manufacturing"}
VALID_MEDALLION_LAYERS = {"bronze", "silver", "gold"}
REQUIRED_SCHEMA_KEYS = {
    "$schema", "name", "version", "description",
    "industry", "medallion_layer", "typical_rows", "columns",
}
REQUIRED_COLUMN_KEYS = {"name", "type", "description", "generation"}
VALID_COLUMN_TYPES = {
    "long", "string", "date", "timestamp", "boolean",
    "integer", "double", "float", "decimal",
}


# ── Helpers ─────────────────────────────────────────────────────────────────
def load_schema(path: Path) -> dict:
    """Read and parse a JSON schema file."""
    return json.loads(path.read_text())


@lru_cache(maxsize=None)
def load_generator(module_name: str):
    """Dynamically import a generator module from the polars/ directory."""
    module_path = GENERATORS_DIR / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

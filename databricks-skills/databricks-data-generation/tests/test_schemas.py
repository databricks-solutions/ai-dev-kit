"""Validate all 18 JSON schema files for structural correctness."""

import re

from helpers import (
    SCHEMAS_DIR,
    REQUIRED_COLUMN_KEYS,
    REQUIRED_SCHEMA_KEYS,
    VALID_COLUMN_TYPES,
    VALID_INDUSTRIES,
    VALID_MEDALLION_LAYERS,
)


# ── Top-level structure ─────────────────────────────────────────────────────

def test_required_keys_present(schema):
    missing = REQUIRED_SCHEMA_KEYS - schema.keys()
    assert not missing, f"Missing top-level keys: {missing}"


def test_industry_is_valid(schema):
    assert schema["industry"] in VALID_INDUSTRIES, (
        f"Invalid industry '{schema['industry']}'"
    )


def test_medallion_layer_is_valid(schema):
    assert schema["medallion_layer"] in VALID_MEDALLION_LAYERS, (
        f"Invalid medallion_layer '{schema['medallion_layer']}'"
    )


def test_typical_rows_ordering(schema):
    rows = schema["typical_rows"]
    assert {"min", "default", "max"} <= rows.keys()
    assert rows["min"] <= rows["default"] <= rows["max"]


def test_name_matches_filename(schema_path, schema):
    assert schema["name"] == schema_path.stem, (
        f"Schema name '{schema['name']}' != filename '{schema_path.stem}'"
    )


# ── Column validation ───────────────────────────────────────────────────────

def test_columns_non_empty(schema):
    assert len(schema["columns"]) > 0


def test_column_required_keys(schema):
    for col in schema["columns"]:
        missing = REQUIRED_COLUMN_KEYS - col.keys()
        assert not missing, (
            f"Column '{col.get('name', '?')}' missing keys: {missing}"
        )


def test_column_types_recognized(schema):
    for col in schema["columns"]:
        col_type = col["type"]
        # Strip decimal precision, e.g. "decimal(12,2)" -> "decimal"
        base_type = re.sub(r"\(.*\)", "", col_type)
        assert base_type in VALID_COLUMN_TYPES, (
            f"Column '{col['name']}' has unrecognized type '{col_type}'"
        )


def test_weights_values_alignment(schema):
    """If a column has both 'values' and 'weights', they must be the same length."""
    for col in schema["columns"]:
        gen = col["generation"]
        if "values" in gen and "weights" in gen:
            assert len(gen["values"]) == len(gen["weights"]), (
                f"Column '{col['name']}': values ({len(gen['values'])}) "
                f"and weights ({len(gen['weights'])}) length mismatch"
            )


# ── Cross-schema relationships ──────────────────────────────────────────────

def test_relationship_targets_exist(schema):
    """Every relationship target must correspond to an existing schema file."""
    existing = {p.stem for p in SCHEMAS_DIR.glob("*.json")}
    for rel in schema.get("relationships", []):
        target = rel.get("parent_of") or rel.get("child_of")
        if target:
            assert target in existing, (
                f"Relationship target '{target}' has no matching schema file"
            )

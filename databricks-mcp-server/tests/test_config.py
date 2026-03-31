"""
Centralized test configuration for MCP server integration tests.

Each test module uses a unique schema to enable parallel test execution without conflicts.
"""

import os

# =============================================================================
# Core Test Configuration
# =============================================================================

# Default catalog for all tests (can be overridden via env var)
TEST_CATALOG = os.environ.get("TEST_CATALOG", "ai_dev_kit_test")

# =============================================================================
# Per-Module Schema Configuration
# Each module gets its own schema to avoid conflicts during parallel execution
# =============================================================================

SCHEMAS = {
    # SQL and core tests
    "sql": "test_sql",
    "warehouse": "test_warehouse",

    # Pipeline tests
    "pipelines": "test_pipelines",

    # Vector search tests
    "vector_search": "test_vs",

    # Genie tests
    "genie": "test_genie",

    # Serving tests
    "serving": "test_serving",

    # Dashboard tests
    "dashboards": "test_dashboards",

    # Apps tests
    "apps": "test_apps",

    # Jobs tests
    "jobs": "test_jobs",

    # Volume files tests
    "volume_files": "test_volume_files",

    # Workspace file tests
    "workspace_files": "test_workspace_files",

    # Lakebase tests
    "lakebase": "test_lakebase",

    # Compute tests
    "compute": "test_compute",

    # Agent bricks tests
    "agent_bricks": "test_agent_bricks",

    # Unity catalog tests
    "unity_catalog": "test_uc",

    # PDF tests
    "pdf": "test_pdf",
}

# =============================================================================
# Resource Naming Conventions
# =============================================================================

# Prefix for all test resources (pipelines, endpoints, etc.)
TEST_RESOURCE_PREFIX = "ai_dev_kit_test_"

# Pipeline names
PIPELINE_NAMES = {
    "basic": f"{TEST_RESOURCE_PREFIX}pipeline_basic",
    "with_run": f"{TEST_RESOURCE_PREFIX}pipeline_with_run",
}

# Vector search endpoint names
VS_ENDPOINT_NAMES = {
    "basic": f"{TEST_RESOURCE_PREFIX}vs_endpoint",
}

# Vector search index names (use schema-qualified names)
def get_vs_index_name(index_key: str) -> str:
    """Get fully-qualified VS index name."""
    return f"{TEST_CATALOG}.{SCHEMAS['vector_search']}.{TEST_RESOURCE_PREFIX}vs_index_{index_key}"

# Genie space names
GENIE_SPACE_NAMES = {
    "basic": f"{TEST_RESOURCE_PREFIX}genie_space",
}

# Serving endpoint names
SERVING_ENDPOINT_NAMES = {
    "basic": f"{TEST_RESOURCE_PREFIX}serving_endpoint",
}

# Dashboard names
DASHBOARD_NAMES = {
    "basic": f"{TEST_RESOURCE_PREFIX}dashboard",
}

# App names
APP_NAMES = {
    "basic": f"{TEST_RESOURCE_PREFIX}app",
}

# Job names
JOB_NAMES = {
    "basic": f"{TEST_RESOURCE_PREFIX}job",
}

# Volume names
VOLUME_NAMES = {
    "basic": f"{TEST_RESOURCE_PREFIX}volume",
}

# =============================================================================
# Helper Functions
# =============================================================================

def get_full_schema_name(module: str) -> str:
    """Get fully-qualified schema name for a test module."""
    return f"{TEST_CATALOG}.{SCHEMAS[module]}"

def get_table_name(module: str, table: str) -> str:
    """Get fully-qualified table name for a test module."""
    return f"{TEST_CATALOG}.{SCHEMAS[module]}.{table}"

def get_volume_path(module: str, volume: str = "test_volume") -> str:
    """Get volume path for a test module."""
    return f"/Volumes/{TEST_CATALOG}/{SCHEMAS[module]}/{volume}"

def get_workspace_path(username: str, module: str) -> str:
    """Get workspace path for a test module."""
    return f"/Workspace/Users/{username}/ai_dev_kit_test/{module}/resources"

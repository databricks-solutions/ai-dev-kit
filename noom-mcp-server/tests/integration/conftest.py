"""Fixtures for live Databricks integration tests."""

import os

import pytest


@pytest.fixture(scope="session")
def warehouse_id() -> str:
    """SQL warehouse to run test queries against.

    Set DATABRICKS_WAREHOUSE_ID in your environment before running.
    """
    wh = os.environ.get("DATABRICKS_WAREHOUSE_ID")
    if not wh:
        pytest.skip("Set DATABRICKS_WAREHOUSE_ID to run integration tests")
    return wh


@pytest.fixture(scope="session")
def patches_applied() -> None:
    """Apply all Noom governance patches once for the integration test session.

    This also validates:
    - The upstream version pin (UpstreamChangedError if mismatched)
    - PAT rejection (RuntimeError if the calling user authenticated with a PAT)

    So the test session itself only succeeds under valid OAuth credentials.
    """
    from customization.patches import apply_all_patches

    apply_all_patches()

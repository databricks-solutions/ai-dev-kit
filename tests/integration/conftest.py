"""Conftest for integration tests — no Spark/DatabricksConnect dependency."""

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "online: tests that require a live Databricks connection"
    )

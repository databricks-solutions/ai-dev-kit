"""Root pytest configuration for noom-mcp-server.

Adds the --integration flag and automatically skips @pytest.mark.integration
tests unless the flag is passed.
"""

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run integration tests that require live Databricks credentials.",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not config.getoption("--integration"):
        skip = pytest.mark.skip(reason="pass --integration to run live tests")
        for item in items:
            if item.get_closest_marker("integration"):
                item.add_marker(skip)

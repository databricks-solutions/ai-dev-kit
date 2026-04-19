"""Pytest configuration and shared fixtures."""

import csv
import json
import os
import pathlib
import sys
from contextlib import contextmanager

import pytest

try:
    from databricks.connect import DatabricksSession
    from databricks.sdk import WorkspaceClient
    from pyspark.sql import SparkSession
except ImportError:
    raise ImportError(
        "Test dependencies not found.\n\n"
        "Run tests using 'uv run pytest'. See http://docs.astral.sh/uv to learn more about uv."
    )


@pytest.fixture()
def spark() -> SparkSession:
    """Provide a SparkSession fixture for tests."""
    return DatabricksSession.builder.getOrCreate()


@pytest.fixture()
def load_fixture(spark: SparkSession):
    """Load JSON or CSV from fixtures/ directory as a DataFrame.

    Example:
        def test_using_fixture(load_fixture):
            data = load_fixture("my_data.json")
            assert data.count() >= 1
    """

    def _loader(filename: str):
        path = pathlib.Path(__file__).parent.parent / "fixtures" / filename
        suffix = path.suffix.lower()
        if suffix == ".json":
            rows = json.loads(path.read_text())
            return spark.createDataFrame(rows)
        if suffix == ".csv":
            with path.open(newline="") as f:
                rows = list(csv.DictReader(f))
            return spark.createDataFrame(rows)
        raise ValueError(f"Unsupported fixture type for: {filename}")

    return _loader


def _enable_fallback_compute():
    """Enable serverless compute if no compute is specified."""
    conf = WorkspaceClient().config
    if conf.serverless_compute_id or conf.cluster_id or os.environ.get("SPARK_REMOTE"):
        return

    url = "https://docs.databricks.com/dev-tools/databricks-connect/cluster-config"
    print("No compute specified, falling back to serverless compute", file=sys.stderr)
    print(f"  see {url} for manual configuration", file=sys.stdout)

    os.environ["DATABRICKS_SERVERLESS_COMPUTE_ID"] = "auto"


@contextmanager
def _allow_stderr_output(config: pytest.Config):
    """Temporarily disable pytest output capture."""
    capman = config.pluginmanager.get_plugin("capturemanager")
    if capman:
        with capman.global_and_fixture_disabled():
            yield
    else:
        yield


def pytest_configure(config: pytest.Config):
    """Configure pytest session."""
    with _allow_stderr_output(config):
        _enable_fallback_compute()

        if hasattr(DatabricksSession.builder, "validateSession"):
            DatabricksSession.builder.validateSession().getOrCreate()
        else:
            DatabricksSession.builder.getOrCreate()

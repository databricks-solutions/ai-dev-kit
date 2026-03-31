# Integration Tests

This directory contains integration tests for the Databricks MCP Server tools. These tests run against a real Databricks workspace.

## Prerequisites

1. **Databricks Authentication**: Configure your Databricks credentials via environment variables or `~/.databrickscfg`
2. **Test Catalog**: Set `TEST_CATALOG` in `tests/test_config.py` or use the default
3. **Python Dependencies**: Install test dependencies with `pip install -e ".[dev]"`

## Running Tests

### Quick Start: Run All Tests

```bash
# Run all tests (excluding slow tests)
python tests/integration/run_tests.py

# Run all tests including slow tests (cluster lifecycle, etc.)
python tests/integration/run_tests.py --all
```

### View Test Reports

```bash
# Show report from the latest test run
python tests/integration/run_tests.py --report

# Show report from a specific run (by timestamp)
python tests/integration/run_tests.py --report 20260331_112315
```

### Check Status of Running Tests

```bash
# Show status of ongoing and recently completed runs
python tests/integration/run_tests.py --status
```

### Advanced Options

```bash
# Run with fewer parallel workers (default: 8)
python tests/integration/run_tests.py -j 4

# Combine options
python tests/integration/run_tests.py --all -j 4

# Clean up old test results (keeps last 5 runs)
python tests/integration/run_tests.py --cleanup-results
```

### Run Individual Test Folders

```bash
# Run a specific test folder
python -m pytest tests/integration/sql -m integration -v

# Run a specific test
python -m pytest tests/integration/sql/test_sql.py::TestExecuteSql::test_simple_query -v
```

## Test Output

Test results are saved to `.test-results/<timestamp>/`:

```
.test-results/
└── 20260331_112315/
    ├── results.json      # Machine-readable results
    ├── sql.txt           # Logs for sql tests
    ├── workspace_files.txt
    ├── dashboards.txt
    └── ...
```

## Test Markers

- `@pytest.mark.integration` - Standard integration tests
- `@pytest.mark.slow` - Tests that take a long time (cluster creation, etc.)

## Test Folders

| Folder | Description |
|--------|-------------|
| `sql/` | SQL execution and query tests |
| `workspace_files/` | Workspace file upload/download tests |
| `volume_files/` | Unity Catalog volume file operations |
| `dashboards/` | AI/BI dashboard management |
| `genie/` | Genie (AI assistant) spaces |
| `agent_bricks/` | Agent Bricks tool tests |
| `compute/` | Cluster and serverless compute |
| `jobs/` | Job creation and execution |
| `pipelines/` | DLT pipeline management |
| `vector_search/` | Vector search endpoints and indexes |
| `serving/` | Model serving endpoints |
| `apps/` | Databricks Apps |
| `lakebase/` | Lakebase database operations |
| `pdf/` | PDF processing tests |

## Re-running Failed Tests

After a test run, you can re-run specific failed tests:

```bash
# View the failure details
cat .test-results/<timestamp>/jobs.txt

# Re-run with more verbose output
python -m pytest tests/integration/jobs -v --tb=long
```

## Cleanup

Test resources are automatically cleaned up after tests. If cleanup fails, resources are prefixed with `ai_dev_kit_test_` for easy identification.

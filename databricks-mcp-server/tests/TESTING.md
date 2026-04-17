# Integration Tests

This document describes how to run integration tests for the Databricks MCP Server.

## Prerequisites

1. **Databricks Workspace**: You need access to a Databricks workspace
2. **Authentication**: Configure authentication via:
   - Environment variables: `DATABRICKS_HOST`, `DATABRICKS_TOKEN`
   - Or Databricks CLI profile: `databricks configure`
3. **Test Catalog**: Default test catalog is `ai_dev_kit_test` (configurable via `TEST_CATALOG` env var)

## Running Tests

### Fast Tests (Validation Only)

Run fast validation tests that don't create expensive resources:

```bash
# All fast tests (~30s total)
python -m pytest tests/integration -m "integration and not slow" -v

# Single module
python -m pytest tests/integration/sql -m "integration and not slow" -v
python -m pytest tests/integration/genie -m "integration and not slow" -v
python -m pytest tests/integration/apps -m "integration and not slow" -v
```

### All Tests (Including Slow)

Run all tests including lifecycle tests that create/delete resources:

```bash
# All tests (may take 10+ minutes)
python -m pytest tests/integration -m integration -v

# Single module with all tests
python -m pytest tests/integration/apps -m integration -v
```

### Run Tests in Parallel

For faster execution, run test modules in parallel:

```bash
# Run all modules in parallel with output to .test-results/
TIMESTAMP=$(date +%Y%m%d_%H%M%S) && mkdir -p .test-results/$TIMESTAMP && \
(
  python -m pytest tests/integration/sql -m integration -v > .test-results/$TIMESTAMP/sql.txt 2>&1 &
  python -m pytest tests/integration/genie -m integration -v > .test-results/$TIMESTAMP/genie.txt 2>&1 &
  python -m pytest tests/integration/apps -m integration -v > .test-results/$TIMESTAMP/apps.txt 2>&1 &
  python -m pytest tests/integration/agent_bricks -m integration -v > .test-results/$TIMESTAMP/agent_bricks.txt 2>&1 &
  python -m pytest tests/integration/dashboards -m integration -v > .test-results/$TIMESTAMP/dashboards.txt 2>&1 &
  python -m pytest tests/integration/lakebase -m integration -v > .test-results/$TIMESTAMP/lakebase.txt 2>&1 &
  python -m pytest tests/integration/compute -m integration -v > .test-results/$TIMESTAMP/compute.txt 2>&1 &
  python -m pytest tests/integration/pipelines -m integration -v > .test-results/$TIMESTAMP/pipelines.txt 2>&1 &
  python -m pytest tests/integration/jobs -m integration -v > .test-results/$TIMESTAMP/jobs.txt 2>&1 &
  python -m pytest tests/integration/vector_search -m integration -v > .test-results/$TIMESTAMP/vector_search.txt 2>&1 &
  python -m pytest tests/integration/volume_files -m integration -v > .test-results/$TIMESTAMP/volume_files.txt 2>&1 &
  python -m pytest tests/integration/serving -m integration -v > .test-results/$TIMESTAMP/serving.txt 2>&1 &
  python -m pytest tests/integration/workspace_files -m integration -v > .test-results/$TIMESTAMP/workspace_files.txt 2>&1 &
  python -m pytest tests/integration/pdf -m integration -v > .test-results/$TIMESTAMP/pdf.txt 2>&1 &
  wait
) && echo "Results in: .test-results/$TIMESTAMP/"
```

### Analyze Results

After running tests in parallel, analyze results:

```bash
# Show summary of all test results
for f in .test-results/$(ls -t .test-results | head -1)/*.txt; do
  name=$(basename "$f" .txt)
  result=$(grep -E "passed|failed|error" "$f" | tail -1)
  echo "$name: $result"
done

# Show failures only
grep -l FAILED .test-results/$(ls -t .test-results | head -1)/*.txt | \
  xargs -I{} sh -c 'echo "=== {} ===" && grep -A5 "FAILED\|ERROR" {}'
```

## Test Structure

### Test Markers

- `@pytest.mark.integration` - All integration tests
- `@pytest.mark.slow` - Tests that take >10s (list operations, lifecycle tests)

### Test Categories

| Module | Fast Tests | Lifecycle Tests | Notes |
|--------|------------|-----------------|-------|
| sql | Yes | No | SQL query execution |
| genie | Yes | Yes | Genie space CRUD + queries |
| apps | Yes | Yes | App deployment (slow) |
| agent_bricks | Yes | Yes | KA/MAS creation (very slow) |
| dashboards | Yes | No | Dashboard CRUD |
| lakebase | Yes | Yes | Autoscale project lifecycle |
| compute | Yes | Yes | Cluster lifecycle |
| pipelines | Yes | Yes | DLT pipeline lifecycle |
| jobs | Yes | Yes | Job lifecycle |
| vector_search | Yes | Yes | VS endpoint/index lifecycle |
| volume_files | Yes | No | Volume file operations |
| workspace_files | Yes | No | Workspace file operations |
| serving | Yes | No | Model serving endpoints |
| pdf | Yes | No | PDF processing |

### Naming Conventions

Test resources use the prefix `ai_dev_kit_test_` to enable safe cleanup:
- Apps: `ai-dev-kit-test-app-{uuid}` (apps require lowercase/dashes only)
- Other resources: `ai_dev_kit_test_{type}_{uuid}`

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TEST_CATALOG` | Unity Catalog for test resources | `ai_dev_kit_test` |
| `DATABRICKS_HOST` | Workspace URL | From CLI profile |
| `DATABRICKS_TOKEN` | Personal access token | From CLI profile |

## Test Output

Test results are stored in `.test-results/` (gitignored):
- Each run creates a timestamped folder: `.test-results/20250331_123456/`
- Each module gets its own file: `sql.txt`, `genie.txt`, etc.
- Summary in `summary.txt`

## Troubleshooting

### Tests Timeout

Some lifecycle tests (apps, agent_bricks, compute) may take 5+ minutes:
```bash
# Increase pytest timeout
python -m pytest tests/integration/apps -m integration -v --timeout=600
```

### Resource Cleanup

Test resources are automatically cleaned up. Manual cleanup:
```bash
# List test resources
databricks apps list | grep ai-dev-kit-test
databricks clusters list | grep ai_dev_kit_test

# Delete orphaned resources
databricks apps delete ai-dev-kit-test-app-abc123
```

### SDK Version Issues

If you see API errors like `unexpected keyword argument`:
```bash
# Update SDK
pip install --upgrade databricks-sdk
```

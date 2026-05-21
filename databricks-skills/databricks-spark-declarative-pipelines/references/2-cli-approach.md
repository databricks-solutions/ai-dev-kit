# Rapid Pipeline Iteration with CLI

Use CLI commands to create, run, and iterate on **SDP pipelines**. This is the fastest approach for prototyping without managing bundle files.

**IMPORTANT: Default to serverless pipelines.** Only use classic clusters if user explicitly requires R language, Spark RDD APIs, or JAR libraries.

### Step 1: Write Pipeline Files Locally

Create `.sql` or `.py` files in a local folder. For syntax examples, see:
- [sql/1-syntax-basics.md](sql/1-syntax-basics.md) for SQL syntax
- [python/1-syntax-basics.md](python/1-syntax-basics.md) for Python syntax

### Step 2: Upload to Databricks Workspace

```bash
# Upload local folder to workspace
databricks workspace import-dir ./my_pipeline /Workspace/Users/user@example.com/my_pipeline
```

### Step 3: Create Pipeline

Use the canonical `databricks pipelines create --json` shape from [SKILL.md](../SKILL.md#step-1-check-pipeline-execution-status). Notes specific to the `libraries` field:

- `"glob"` = directory of files (recommended for medallion folders).
- `"file"` = single `.sql`/`.py` file. A `"file"` pointing at a folder fails with `Paths must end with .py or .sql`.
- `"notebook"` is deprecated — don't use it.

Enumerate files instead of glob when you need explicit ordering:
```json
"libraries": [
  {"file": {"path": "/Workspace/.../bronze/ingest_orders.sql"}},
  {"file": {"path": "/Workspace/.../silver/clean_orders.sql"}}
]
```

Save the returned `pipeline_id` for subsequent operations.

### Step 4: Run Pipeline

Use the `start-update` + `get-update` polling pattern from [SKILL.md](../SKILL.md#step-1-check-pipeline-execution-status). Don't poll top-level `pipelines get` state — see the rationale there.

### Step 5: Validate Results

**On Success** - Verify tables were created with correct data:

```bash
# Check schema, row counts, sample data, and null counts for all tables
databricks experimental aitools tools discover-schema \
  my_catalog.my_schema.bronze_orders \
  my_catalog.my_schema.silver_orders \
  my_catalog.my_schema.gold_summary
```

This returns per table: columns/types, 5 sample rows, total_rows count, and null counts.

Or use Python for detailed stats:
```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Get table info
table = w.tables.get("my_catalog.my_schema.bronze_orders")
print(f"Columns: {len(table.columns)}")
print(f"Created: {table.created_at}")
```

**On Failure** - Get pipeline events and errors:

```bash
# Get pipeline details with recent events (pipeline_id is positional)
databricks pipelines get <pipeline_id>

# Get specific run events
databricks pipelines list-pipeline-events <pipeline_id>
```

### Step 6: Iterate Until Working

1. Review errors from pipeline status or events
2. Fix issues in local files
3. Re-upload: `databricks workspace import-dir ./my_pipeline /Workspace/Users/user@example.com/my_pipeline --overwrite`
4. Update and run: `databricks pipelines update <pipeline_id> --json '...'` then `databricks pipelines start-update <pipeline_id>`
5. Repeat until pipeline completes successfully

---

## Quick Reference: CLI Commands

### Pipeline Lifecycle

| Command | Description |
|---------|-------------|
| `databricks pipelines create --json '{...}'` | Create new pipeline |
| `databricks pipelines get PIPELINE_ID` | Get pipeline details and status |
| `databricks pipelines update PIPELINE_ID --json '{...}'` | Update pipeline config |
| `databricks pipelines delete PIPELINE_ID` | Delete a pipeline |
| `databricks pipelines list-pipelines` | List all pipelines |

### Run Management

| Command | Description |
|---------|-------------|
| `databricks pipelines start-update PIPELINE_ID` | Start pipeline update |
| `databricks pipelines start-update PIPELINE_ID --full-refresh` | Start with full refresh |
| `databricks pipelines stop PIPELINE_ID` | Stop running pipeline |
| `databricks pipelines list-pipeline-events PIPELINE_ID` | Get events/logs |
| `databricks pipelines list-updates PIPELINE_ID` | List recent runs |

### Supporting Commands

| Command | Description |
|---------|-------------|
| `databricks workspace import-dir` | Upload files/folders to workspace |
| `databricks workspace list` | List workspace files |
| `databricks experimental aitools tools discover-schema` | Get schema, row counts, sample data, null counts |
| `databricks experimental aitools tools query` | Run ad-hoc SQL queries |

---

## Python SDK Alternative

For more programmatic control, use the Databricks SDK:

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Create pipeline — same shape as the CLI canonical example.
pipeline = w.pipelines.create(
    name="my_orders_pipeline",
    catalog="my_catalog",
    schema="my_schema",
    serverless=True,
    continuous=False,  # explicit — true auto-retries failed updates forever
    libraries=[
        {"glob": {"include": "/Workspace/Users/user@example.com/my_pipeline/**"}}
    ],
    development=True,
)
print(f"Created pipeline: {pipeline.pipeline_id}")

# Start update — capture update_id; poll THAT update, not pipeline-level state.
# Pipeline state flips back to RUNNING on RETRY_ON_FAILURE, so a loop watching
# the pipeline (or latest_updates[0]) can spin past a real FAILED update.
update = w.pipelines.start_update(
    pipeline_id=pipeline.pipeline_id,
    full_refresh=True
)

import time
while True:
    u = w.pipelines.get_update(pipeline_id=pipeline.pipeline_id, update_id=update.update_id).update
    if str(u.state) in ("COMPLETED", "FAILED", "CANCELED"):
        print(f"Update {u.update_id}: {u.state}")
        break
    time.sleep(10)
```

---

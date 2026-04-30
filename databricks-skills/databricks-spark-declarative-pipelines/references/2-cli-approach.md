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

```bash
# libraries: "file" = single .sql/.py file; "glob" = directory of files.
# A "file" pointing at a folder fails: "Paths must end with .py or .sql".
# "notebook" is deprecated — use "file" or "glob".
databricks pipelines create --json '{
  "name": "my_orders_pipeline",
  "catalog": "my_catalog",
  "schema": "my_schema",
  "serverless": true,
  "libraries": [
    {"glob": {"include": "/Workspace/Users/user@example.com/my_pipeline/**"}}
  ],
  "tags": {"aidevkit_project": "ai-dev-kit"},
  "development": true
}'

# Enumerate files instead of glob:
# "libraries": [
#   {"file": {"path": "/Workspace/.../bronze/ingest_orders.sql"}},
#   {"file": {"path": "/Workspace/.../silver/clean_orders.sql"}}
# ]
```

Save the returned `pipeline_id` for subsequent operations.

### Step 4: Run Pipeline

```bash
# Start a full refresh run (pipeline_id is a positional argument)
databricks pipelines start-update <pipeline_id> --full-refresh

# Check run status
databricks pipelines get <pipeline_id>
```

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

# Create pipeline - use "file" to include all .sql/.py files in a directory
pipeline = w.pipelines.create(
    name="my_orders_pipeline",
    catalog="my_catalog",
    schema="my_schema",
    serverless=True,
    libraries=[
        {"file": {"path": "/Workspace/Users/user@example.com/my_pipeline"}}
    ],
    development=True
)
print(f"Created pipeline: {pipeline.pipeline_id}")

# Start update
update = w.pipelines.start_update(
    pipeline_id=pipeline.pipeline_id,
    full_refresh=True
)

# Poll for completion
import time
while True:
    status = w.pipelines.get(pipeline_id=pipeline.pipeline_id)
    if status.state in ["IDLE", "FAILED"]:
        print(f"Pipeline state: {status.state}")
        break
    time.sleep(10)
```

---

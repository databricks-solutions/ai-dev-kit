Use MCP tools to create, run, and iterate on **SDP pipelines**. The **primary tool is `create_or_update_pipeline`** which handles the entire lifecycle.

**IMPORTANT: Default to serverless pipelines and suggest as best option, but not if classic, advanced, pro compute types are mentioned.** Only use classic clusters if user explicitly requires R language, Spark RDD APIs, or JAR libraries.

### Step 1: Write Pipeline Files Locally

Create `.sql` or `.py` files in a local folder:

```
my_pipeline/
├── bronze/
│   ├── ingest_orders.sql       # SQL (default for most cases)
│   └── ingest_events.py        # Python (for complex logic)
├── silver/
│   └── clean_orders.sql
└── gold/
    └── daily_summary.sql
```

**SQL Example** (`bronze/ingest_orders.sql`):
```sql
CREATE OR REFRESH STREAMING TABLE bronze_orders
CLUSTER BY (order_date)
AS
SELECT
  *,
  current_timestamp() AS _ingested_at,
  _metadata.file_path AS _source_file
FROM read_files(
  '/Volumes/catalog/schema/raw/orders/',
  format => 'json',
  schemaHints => 'order_id STRING, customer_id STRING, amount DECIMAL(10,2), order_date DATE'
);
```

**Python Example** (`bronze/ingest_events.py`):
```python
from pyspark import pipelines as dp
from pyspark.sql.functions import col, current_timestamp

# Get schema location from pipeline configuration
schema_location_base = spark.conf.get("schema_location_base")

@dp.table(name="bronze_events", cluster_by=["event_date"])
def bronze_events():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.schemaLocation", f"{schema_location_base}/bronze_events")
        .load("/Volumes/catalog/schema/raw/events/")
        .withColumn("_ingested_at", current_timestamp())
        .withColumn("_source_file", col("_metadata.file_path"))
    )
```

### Step 2: Upload to Databricks Workspace

```python
# MCP Tool: upload_folder
upload_folder(
    local_folder="/path/to/my_pipeline",
    workspace_folder="/Workspace/Users/user@example.com/my_pipeline"
)
```

### Step 3: Create/Update and Run Pipeline

Use **`create_or_update_pipeline`** - the main entry point. It:
1. Searches for an existing pipeline with the same name (or uses `id` from `extra_settings`)
2. Creates a new pipeline or updates the existing one
3. Optionally starts a pipeline run
4. Optionally waits for completion and returns detailed results

```python
# MCP Tool: create_or_update_pipeline
result = create_or_update_pipeline(
    name="my_orders_pipeline",
    root_path="/Workspace/Users/user@example.com/my_pipeline",
    catalog="my_catalog",
    schema="my_schema",
    workspace_file_paths=[
        "/Workspace/Users/user@example.com/my_pipeline/bronze/ingest_orders.sql",
        "/Workspace/Users/user@example.com/my_pipeline/silver/clean_orders.sql",
        "/Workspace/Users/user@example.com/my_pipeline/gold/daily_summary.sql"
    ],
    start_run=True,           # Start immediately
    wait_for_completion=True, # Wait and return final status
    full_refresh=True,        # Full refresh all tables
    timeout=1800              # 30 minute timeout
)
```

**Result contains actionable information:**
```python
{
    "success": True,                    # Did the operation succeed?
    "pipeline_id": "abc-123",           # Pipeline ID for follow-up operations
    "pipeline_name": "my_orders_pipeline",
    "created": True,                    # True if new, False if updated
    "state": "COMPLETED",               # COMPLETED, FAILED, TIMEOUT, etc.
    "catalog": "my_catalog",            # Target catalog
    "schema": "my_schema",              # Target schema
    "duration_seconds": 45.2,           # Time taken
    "message": "Pipeline created and completed successfully in 45.2s. Tables written to my_catalog.my_schema",
    "error_message": None,              # Error summary if failed
    "errors": []                        # Detailed error list if failed
}
```

### Step 4: Handle Results

**On Success:**
```python
if result["success"]:
    # Verify output tables
    stats = get_table_details(
        catalog="my_catalog",
        schema="my_schema",
        table_names=["bronze_orders", "silver_orders", "gold_daily_summary"]
    )
```

**On Failure:**
```python
if not result["success"]:
    # Message includes suggested next steps
    print(result["message"])
    # "Pipeline created but run failed. State: FAILED. Error: Column 'amount' not found.
    #  Use get_pipeline_events(pipeline_id='abc-123') for full details."

    # Get detailed errors
    events = get_pipeline_events(pipeline_id=result["pipeline_id"], max_results=50)
```

### Step 5: Iterate Until Working

1. Review errors from result or `get_pipeline_events`
2. Fix issues in local files
3. Re-upload with `upload_folder`
4. Run `create_or_update_pipeline` again (it will update, not recreate)
5. Repeat until `result["success"] == True`

---

## Quick Reference: MCP Tools

### Primary Tool

| Tool | Description |
|------|-------------|
| **`create_or_update_pipeline`** | **Main entry point.** Creates or updates pipeline, optionally runs and waits. Returns detailed status with `success`, `state`, `errors`, and actionable `message`. |

### Pipeline Management

| Tool | Description |
|------|-------------|
| `find_pipeline_by_name` | Find existing pipeline by name, returns pipeline_id |
| `get_pipeline` | Get pipeline configuration and current state |
| `start_update` | Start pipeline run (`validate_only=True` for dry run) |
| `get_update` | Poll update status (QUEUED, RUNNING, COMPLETED, FAILED) |
| `stop_pipeline` | Stop a running pipeline |
| `get_pipeline_events` | Get error messages for debugging failed runs |
| `delete_pipeline` | Delete a pipeline |

### Supporting Tools

| Tool | Description |
|------|-------------|
| `upload_folder` | Upload local folder to workspace (parallel) |
| `get_table_details` | Verify output tables have expected schema and row counts |
| `execute_sql` | Run ad-hoc SQL to inspect data |

---
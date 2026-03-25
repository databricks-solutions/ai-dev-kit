Use MCP tools to create, run, and iterate on **SDP pipelines**. The **primary tool is `create_or_update_pipeline`** which handles the entire lifecycle.

**IMPORTANT: Default to serverless pipelines.** Only use classic clusters if user explicitly requires R language, Spark RDD APIs, or JAR libraries.

### Step 1: Write Pipeline Files Locally

Create `.sql` or `.py` files in a local folder. For syntax examples, see:
- [sql/1-syntax-basics.md](sql/1-syntax-basics.md) for SQL syntax
- [python/1-syntax-basics.md](python/1-syntax-basics.md) for Python syntax

### Step 2: Upload to Databricks Workspace

```python
# MCP Tool: upload_folder
upload_folder(
    local_folder="/path/to/my_pipeline",
    workspace_folder="/Workspace/Users/user@example.com/my_pipeline"
)
```

### Step 3: Create/Update and Run Pipeline

Use **`create_or_update_pipeline`** to manage the resource, then **`run_pipeline`** to execute it:

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
    ]
)

# MCP Tool: run_pipeline
run_result = run_pipeline(
    pipeline_id=result["pipeline_id"],
    full_refresh=True,            # Full refresh all tables
    wait_for_completion=True,     # Wait and return final status
    timeout=1800                  # 30 minute timeout
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
    stats = get_table_stats_and_schema(
        catalog="my_catalog",
        schema="my_schema",
        table_names=["bronze_orders", "silver_orders", "gold_daily_summary"]
    )
```

**On Failure:**
```python
if not run_result["success"]:
    # Message includes suggested next steps
    print(run_result["message"])

    # Get detailed errors (get_pipeline enriches with recent events)
    details = get_pipeline(pipeline_id=result["pipeline_id"])
    print(details.get("recent_events"))
```

### Step 5: Iterate Until Working

1. Review errors from run result or `get_pipeline`
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
| `get_pipeline` | Get pipeline details by ID or name; enriched with latest update status and recent events. Omit args to list all. |
| `run_pipeline` | Start, stop, or wait for pipeline runs (`stop=True` to stop, `validate_only=True` for dry run) |
| `delete_pipeline` | Delete a pipeline |

### Supporting Tools

| Tool | Description |
|------|-------------|
| `upload_folder` | Upload local folder to workspace (parallel) |
| `get_table_stats_and_schema` | Verify output tables have expected schema and row counts |
| `execute_sql` | Run ad-hoc SQL to inspect data |

---
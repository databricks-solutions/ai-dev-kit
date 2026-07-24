Use MCP tools to create, run, and iterate on **SDP pipelines**. The **primary tool is `manage_pipeline`** which handles the entire lifecycle.

**IMPORTANT: Default to serverless pipelines.** Only use classic clusters if user explicitly requires R language, Spark RDD APIs, or JAR libraries.

### Step 1: Write Pipeline Files Locally

Create `.sql` or `.py` files in a local folder. For syntax examples, see:
- [sql/1-syntax-basics.md](sql/1-syntax-basics.md) for SQL syntax
- [python/1-syntax-basics.md](python/1-syntax-basics.md) for Python syntax

### Step 2: Upload to Databricks Workspace

```
# MCP Tool: manage_workspace_files
manage_workspace_files(
    action="upload",
    local_path="/path/to/my_pipeline",
    workspace_path="/Workspace/Users/user@example.com/my_pipeline"
)
```

### Step 3: Create/Update and Run Pipeline

Use **`manage_pipeline`** with `action="create_or_update"` to manage the resource:

```
# MCP Tool: manage_pipeline
manage_pipeline(
    action="create_or_update",
    name="my_orders_pipeline",
    root_path="/Workspace/Users/user@example.com/my_pipeline",
    catalog="my_catalog",
    schema="my_schema",
    workspace_file_paths=[
        "/Workspace/Users/user@example.com/my_pipeline/bronze/ingest_orders.sql",
        "/Workspace/Users/user@example.com/my_pipeline/silver/clean_orders.sql",
        "/Workspace/Users/user@example.com/my_pipeline/gold/daily_summary.sql"
    ],
    start_run=True,           # Automatically run after create/update
    wait_for_completion=True, # Wait for run to finish
    full_refresh=True         # Reprocess all data
)
```

**Result contains actionable information:**
```json
{
    "success": true,
    "pipeline_id": "abc-123",
    "pipeline_name": "my_orders_pipeline",
    "created": true,
    "state": "COMPLETED",
    "catalog": "my_catalog",
    "schema": "my_schema",
    "duration_seconds": 45.2,
    "message": "Pipeline created and completed successfully in 45.2s. Tables written to my_catalog.my_schema",
    "error_message": null,
    "errors": []
}
```

### Alternative: Run Pipeline Separately

If you want to run an existing pipeline or control the run separately:

```
# MCP Tool: manage_pipeline_run
manage_pipeline_run(
    action="start",
    pipeline_id="<pipeline_id>",
    full_refresh=True,
    wait=True,    # Wait for completion
    timeout=1800  # 30 minute timeout
)
```

### Step 4: Validate Results

**On Success** - Use `get_table_stats_and_schema` to verify tables (NOT manual SQL COUNT queries):
```
# MCP Tool: get_table_stats_and_schema
get_table_stats_and_schema(
    catalog="my_catalog",
    schema="my_schema",
    table_names=["bronze_orders", "silver_orders", "gold_daily_summary"]
)
# Returns schema, row counts, and column stats for all tables in one call
```

**On Failure** - Check `run_result["message"]` for suggested next steps, then get detailed errors:
```
# MCP Tool: manage_pipeline
manage_pipeline(action="get", pipeline_id="<pipeline_id>")
# Returns pipeline details enriched with recent events and error messages

# Or get events/logs directly:
# MCP Tool: manage_pipeline_run
manage_pipeline_run(
    action="get_events",
    pipeline_id="<pipeline_id>",
    event_log_level="ERROR",  # ERROR, WARN, or INFO
    max_results=10
)
```

### Step 5: Iterate Until Working

1. Review errors from run result or `manage_pipeline(action="get")`
2. Fix issues in local files
3. Re-upload with `manage_workspace_files(action="upload")`
4. Run `manage_pipeline(action="create_or_update", start_run=True)` again (it will update, not recreate)
5. Repeat until `result["success"] == True`

---

## Quick Reference: MCP Tools

### manage_pipeline - Pipeline Lifecycle

| Action | Description | Required Params |
|--------|-------------|-----------------|
| `create` | Create new pipeline | name, root_path, catalog, schema, workspace_file_paths |
| `create_or_update` | **Main entry point.** Idempotent create/update, optionally run | name, root_path, catalog, schema, workspace_file_paths |
| `get` | Get pipeline details by ID | pipeline_id |
| `update` | Update pipeline config | pipeline_id + fields to change |
| `delete` | Delete a pipeline | pipeline_id |
| `find_by_name` | Find pipeline by name | name |

**create_or_update options:**
- `start_run=True`: Automatically run after create/update
- `wait_for_completion=True`: Block until run finishes
- `full_refresh=True`: Reprocess all data (default)
- `timeout=1800`: Max wait time in seconds

### manage_pipeline_run - Run Management

| Action | Description | Required Params |
|--------|-------------|-----------------|
| `start` | Start pipeline update | pipeline_id |
| `get` | Get run status | pipeline_id, update_id |
| `stop` | Stop running pipeline | pipeline_id |
| `get_events` | Get events/logs for debugging | pipeline_id |

**start options:**
- `wait=True`: Block until complete (default)
- `full_refresh=True`: Reprocess all data
- `validate_only=True`: Dry run without writing data
- `refresh_selection=["table1", "table2"]`: Refresh specific tables only

**get_events options:**
- `event_log_level`: "ERROR", "WARN" (default), "INFO"
- `max_results`: Number of events (default 5)
- `update_id`: Filter to specific run

### Supporting Tools

| Tool | Description |
|------|-------------|
| `manage_workspace_files(action="upload")` | Upload files/folders to workspace |
| `get_table_stats_and_schema` | **Use this to validate tables** - returns schema, row counts, and stats in one call |
| `execute_sql` | Run ad-hoc SQL to inspect actual data content (not for row counts) |

---

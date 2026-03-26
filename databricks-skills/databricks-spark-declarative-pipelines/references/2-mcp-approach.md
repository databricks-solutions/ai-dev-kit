Use MCP tools to create, run, and iterate on **SDP pipelines**. The **primary tool is `create_or_update_pipeline`** which handles the entire lifecycle.

**IMPORTANT: Default to serverless pipelines.** Only use classic clusters if user explicitly requires R language, Spark RDD APIs, or JAR libraries.

### Step 1: Write Pipeline Files Locally

Create `.sql` or `.py` files in a local folder. For syntax examples, see:
- [sql/1-syntax-basics.md](sql/1-syntax-basics.md) for SQL syntax
- [python/1-syntax-basics.md](python/1-syntax-basics.md) for Python syntax

### Step 2: Upload to Databricks Workspace

```
# MCP Tool: upload_to_workspace
upload_to_workspace(
    local_path="/path/to/my_pipeline",
    workspace_path="/Workspace/Users/user@example.com/my_pipeline"
)
```

### Step 3: Create/Update and Run Pipeline

Use **`create_or_update_pipeline`** to manage the resource, then **`run_pipeline`** to execute it:

```
# MCP Tool: create_or_update_pipeline
create_or_update_pipeline(
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
run_pipeline(
    pipeline_id="<pipeline_id from above>",
    full_refresh=True,
    wait_for_completion=True,
    timeout=1800
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
# MCP Tool: get_pipeline
get_pipeline(pipeline_id="<pipeline_id>")
# Returns pipeline details enriched with recent events and error messages
```

### Step 5: Iterate Until Working

1. Review errors from run result or `get_pipeline`
2. Fix issues in local files
3. Re-upload with `upload_to_workspace`
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
| `upload_to_workspace` | Upload files/folders to workspace (handles files, folders, globs) |
| `get_table_stats_and_schema` | **Use this to validate tables** - returns schema, row counts, and stats in one call. Do NOT use `execute_sql` with COUNT queries. |
| `execute_sql` | Run ad-hoc SQL to inspect actual data content (not for row counts) |

---
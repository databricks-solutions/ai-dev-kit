---
name: databricks-python-sdk
description: "Databricks development guidance including Python SDK, Databricks Connect, CLI, and REST API. Use when working with databricks-sdk, databricks-connect, or Databricks APIs."
---

# Databricks Development Guide

This skill provides guidance for Databricks SDK, Databricks Connect, CLI, and REST API.

**SDK Documentation:** https://databricks-sdk-py.readthedocs.io/en/latest/
**GitHub Repository:** https://github.com/databricks/databricks-sdk-py

---

## Environment Setup

- Use existing virtual environment at `.venv` or use `uv` to create one
- For Spark operations: `uv pip install databricks-connect`
- For SDK operations: `uv pip install databricks-sdk`
- Databricks CLI version should be 0.278.0 or higher

## Configuration

- Default profile name: `DEFAULT`
- Config file: `~/.databrickscfg`
- Environment variables: `DATABRICKS_HOST`, `DATABRICKS_TOKEN`

---

## Databricks Connect (Spark Operations)

Use `databricks-connect` for running Spark code locally against a Databricks cluster.

```python
from databricks.connect import DatabricksSession

# Auto-detects 'DEFAULT' profile from ~/.databrickscfg
spark = DatabricksSession.builder.getOrCreate()

# With explicit profile
spark = DatabricksSession.builder.profile("MY_PROFILE").getOrCreate()

# Use spark as normal
df = spark.sql("SELECT * FROM catalog.schema.table")
df.show()
```

**IMPORTANT:** Do NOT set `.master("local[*]")` - this will cause issues with Databricks Connect.

---

## Direct REST API Access

For operations not yet in SDK or overly complex via SDK, use direct REST API:

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Direct API call using authenticated client
response = w.api_client.do(
    method="GET",
    path="/api/2.0/clusters/list"
)

# POST with body
response = w.api_client.do(
    method="POST",
    path="/api/2.0/jobs/run-now",
    body={"job_id": 123}
)
```

**When to use:** Prefer SDK methods when available. Use `api_client.do` for:
- New API endpoints not yet in SDK
- Complex operations where SDK abstraction is problematic
- Debugging/testing raw API responses

---

## Databricks CLI

```bash
# Check version (should be >= 0.278.0)
databricks --version

# Use specific profile
databricks --profile MY_PROFILE clusters list

# Common commands
databricks clusters list
databricks jobs list
databricks workspace ls /Users/me
```

---

## SDK Documentation Architecture

The SDK documentation follows a predictable URL pattern:

```
Base: https://databricks-sdk-py.readthedocs.io/en/latest/

Workspace APIs:  /workspace/{category}/{service}.html
Account APIs:    /account/{category}/{service}.html
Authentication:  /authentication.html
DBUtils:         /dbutils.html
```

### Workspace API Categories
| Category | Services |
|----------|----------|
| `compute` | clusters, cluster_policies, command_execution, instance_pools, libraries |
| `catalog` | catalogs, schemas, tables, volumes, functions, storage_credentials, external_locations |
| `jobs` | jobs |
| `sql` | warehouses, statement_execution, queries, alerts, dashboards |
| `serving` | serving_endpoints |
| `vectorsearch` | vector_search_indexes, vector_search_endpoints |
| `pipelines` | pipelines |
| `workspace` | repos, secrets, workspace, git_credentials |
| `files` | files, dbfs |
| `ml` | experiments, model_registry |

---

## Authentication

**Doc:** https://databricks-sdk-py.readthedocs.io/en/latest/authentication.html

### Environment Variables
```bash
DATABRICKS_HOST=https://your-workspace.cloud.databricks.com
DATABRICKS_TOKEN=dapi...  # Personal Access Token
```

### Code Patterns

```python
# Auto-detect credentials from environment
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()

# Explicit token auth
w = WorkspaceClient(
    host="https://your-workspace.cloud.databricks.com",
    token="dapi..."
)

# Azure Service Principal
w = WorkspaceClient(
    host="https://adb-xxx.azuredatabricks.net",
    azure_workspace_resource_id="/subscriptions/.../resourceGroups/.../providers/Microsoft.Databricks/workspaces/...",
    azure_tenant_id="tenant-id",
    azure_client_id="client-id",
    azure_client_secret="secret"
)

# Use a named profile from ~/.databrickscfg
w = WorkspaceClient(profile="MY_PROFILE")
```

---

## Core API Reference

### Clusters API
**Doc:** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/compute/clusters.html

```python
# List all clusters
for cluster in w.clusters.list():
    print(f"{cluster.cluster_name}: {cluster.state}")

# Get cluster details
cluster = w.clusters.get(cluster_id="0123-456789-abcdef")

# Create a cluster (returns Wait object)
wait = w.clusters.create(
    cluster_name="my-cluster",
    spark_version=w.clusters.select_spark_version(latest=True),
    node_type_id=w.clusters.select_node_type(local_disk=True),
    num_workers=2
)
cluster = wait.result()  # Wait for cluster to be running

# Or use create_and_wait for blocking call
cluster = w.clusters.create_and_wait(
    cluster_name="my-cluster",
    spark_version="14.3.x-scala2.12",
    node_type_id="i3.xlarge",
    num_workers=2,
    timeout=timedelta(minutes=30)
)

# Start/stop/delete
w.clusters.start(cluster_id="...").result()
w.clusters.stop(cluster_id="...")
w.clusters.delete(cluster_id="...")
```

### Jobs API
**Doc:** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/jobs/jobs.html

```python
from databricks.sdk.service.jobs import Task, NotebookTask

# List jobs
for job in w.jobs.list():
    print(f"{job.job_id}: {job.settings.name}")

# Create a job
created = w.jobs.create(
    name="my-job",
    tasks=[
        Task(
            task_key="main",
            notebook_task=NotebookTask(notebook_path="/Users/me/notebook"),
            existing_cluster_id="0123-456789-abcdef"
        )
    ]
)

# Run a job now
run = w.jobs.run_now_and_wait(job_id=created.job_id)
print(f"Run completed: {run.state.result_state}")

# Get run output
output = w.jobs.get_run_output(run_id=run.run_id)
```

### SQL Statement Execution
**Doc:** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/sql/statement_execution.html

```python
# Execute SQL query
response = w.statement_execution.execute_statement(
    warehouse_id="abc123",
    statement="SELECT * FROM catalog.schema.table LIMIT 10",
    wait_timeout="30s"
)

# Check status and get results
if response.status.state == StatementState.SUCCEEDED:
    for row in response.result.data_array:
        print(row)

# For large results, fetch chunks
chunk = w.statement_execution.get_statement_result_chunk_n(
    statement_id=response.statement_id,
    chunk_index=0
)
```

### SQL Warehouses
**Doc:** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/sql/warehouses.html

```python
# List warehouses
for wh in w.warehouses.list():
    print(f"{wh.name}: {wh.state}")

# Get warehouse
warehouse = w.warehouses.get(id="abc123")

# Create warehouse
created = w.warehouses.create_and_wait(
    name="my-warehouse",
    cluster_size="Small",
    max_num_clusters=1,
    auto_stop_mins=15
)

# Start/stop
w.warehouses.start(id="abc123").result()
w.warehouses.stop(id="abc123").result()
```

### Unity Catalog - Tables
**Doc:** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/tables.html

```python
# List tables in a schema
for table in w.tables.list(catalog_name="main", schema_name="default"):
    print(f"{table.full_name}: {table.table_type}")

# Get table info
table = w.tables.get(full_name="main.default.my_table")
print(f"Columns: {[c.name for c in table.columns]}")

# Check if table exists
exists = w.tables.exists(full_name="main.default.my_table")
```

### Unity Catalog - Catalogs & Schemas
**Doc (Catalogs):** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/catalogs.html
**Doc (Schemas):** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/schemas.html

```python
# List catalogs
for catalog in w.catalogs.list():
    print(catalog.name)

# Create catalog
w.catalogs.create(name="my_catalog", comment="Description")

# List schemas
for schema in w.schemas.list(catalog_name="main"):
    print(schema.name)

# Create schema
w.schemas.create(name="my_schema", catalog_name="main")
```

### Volumes
**Doc:** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/volumes.html

```python
from databricks.sdk.service.catalog import VolumeType

# List volumes
for vol in w.volumes.list(catalog_name="main", schema_name="default"):
    print(f"{vol.full_name}: {vol.volume_type}")

# Create managed volume
w.volumes.create(
    catalog_name="main",
    schema_name="default",
    name="my_volume",
    volume_type=VolumeType.MANAGED
)

# Read volume info
vol = w.volumes.read(name="main.default.my_volume")
```

### Files API
**Doc:** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/files/files.html

```python
# Upload file to volume
w.files.upload(
    file_path="/Volumes/main/default/my_volume/data.csv",
    contents=open("local_file.csv", "rb")
)

# Download file
with w.files.download(file_path="/Volumes/main/default/my_volume/data.csv") as f:
    content = f.read()

# List directory contents
for entry in w.files.list_directory_contents("/Volumes/main/default/my_volume/"):
    print(f"{entry.name}: {entry.is_directory}")

# Upload/download with progress (parallel)
w.files.upload_from(
    file_path="/Volumes/main/default/my_volume/large.parquet",
    source_path="/local/path/large.parquet",
    use_parallel=True
)

w.files.download_to(
    file_path="/Volumes/main/default/my_volume/large.parquet",
    destination="/local/output/",
    use_parallel=True
)
```

### Serving Endpoints (Model Serving)
**Doc:** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/serving/serving_endpoints.html

```python
# List endpoints
for ep in w.serving_endpoints.list():
    print(f"{ep.name}: {ep.state}")

# Get endpoint
endpoint = w.serving_endpoints.get(name="my-endpoint")

# Query endpoint
response = w.serving_endpoints.query(
    name="my-endpoint",
    inputs={"prompt": "Hello, world!"}
)

# For chat/completions endpoints
response = w.serving_endpoints.query(
    name="my-chat-endpoint",
    messages=[{"role": "user", "content": "Hello!"}]
)

# Get OpenAI-compatible client
openai_client = w.serving_endpoints.get_open_ai_client()
```

### Vector Search
**Doc (Indexes):** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/vectorsearch/vector_search_indexes.html
**Doc (Endpoints):** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/vectorsearch/vector_search_endpoints.html

```python
# List vector search indexes
for idx in w.vector_search_indexes.list_indexes(endpoint_name="my-vs-endpoint"):
    print(idx.name)

# Query index
results = w.vector_search_indexes.query_index(
    index_name="main.default.my_index",
    columns=["id", "text", "embedding"],
    query_text="search query",
    num_results=10
)
for doc in results.result.data_array:
    print(doc)
```

### Pipelines (Delta Live Tables)
**Doc:** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/pipelines/pipelines.html

```python
# List pipelines
for pipeline in w.pipelines.list_pipelines():
    print(f"{pipeline.name}: {pipeline.state}")

# Get pipeline
pipeline = w.pipelines.get(pipeline_id="abc123")

# Start pipeline update
w.pipelines.start_update(pipeline_id="abc123")

# Stop pipeline
w.pipelines.stop_and_wait(pipeline_id="abc123")
```

### Secrets
**Doc:** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/workspace/secrets.html

```python
# List secret scopes
for scope in w.secrets.list_scopes():
    print(scope.name)

# Create scope
w.secrets.create_scope(scope="my-scope")

# Put secret
w.secrets.put_secret(scope="my-scope", key="api-key", string_value="secret123")

# Get secret (returns GetSecretResponse with value)
secret = w.secrets.get_secret(scope="my-scope", key="api-key")

# List secrets in scope (metadata only, not values)
for s in w.secrets.list_secrets(scope="my-scope"):
    print(s.key)
```

### DBUtils
**Doc:** https://databricks-sdk-py.readthedocs.io/en/latest/dbutils.html

```python
# Access dbutils through WorkspaceClient
dbutils = w.dbutils

# File system operations
files = dbutils.fs.ls("/")
dbutils.fs.cp("dbfs:/source", "dbfs:/dest")
dbutils.fs.rm("dbfs:/path", recurse=True)

# Secrets (same as w.secrets but dbutils interface)
value = dbutils.secrets.get(scope="my-scope", key="my-key")
```

---

## Common Patterns

### CRITICAL: Async Applications (FastAPI, etc.)

**The Databricks SDK is fully synchronous.** All calls block the thread. In async applications (FastAPI, asyncio), you MUST wrap SDK calls with `asyncio.to_thread()` to avoid blocking the event loop.

```python
import asyncio
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# WRONG - blocks the event loop
async def get_clusters_bad():
    return list(w.clusters.list())  # BLOCKS!

# CORRECT - runs in thread pool
async def get_clusters_good():
    return await asyncio.to_thread(lambda: list(w.clusters.list()))

# CORRECT - for simple calls
async def get_cluster(cluster_id: str):
    return await asyncio.to_thread(w.clusters.get, cluster_id)

# CORRECT - FastAPI endpoint
from fastapi import FastAPI
app = FastAPI()

@app.get("/clusters")
async def list_clusters():
    clusters = await asyncio.to_thread(lambda: list(w.clusters.list()))
    return [{"id": c.cluster_id, "name": c.cluster_name} for c in clusters]

@app.post("/query")
async def run_query(sql: str, warehouse_id: str):
    # Wrap the blocking SDK call
    response = await asyncio.to_thread(
        w.statement_execution.execute_statement,
        statement=sql,
        warehouse_id=warehouse_id,
        wait_timeout="30s"
    )
    return response.result.data_array
```

**Note:** `WorkspaceClient().config.host` is NOT a network call - it just reads config. No need to wrap property access.

---

### Wait for Long-Running Operations
```python
from datetime import timedelta

# Pattern 1: Use *_and_wait methods
cluster = w.clusters.create_and_wait(
    cluster_name="test",
    spark_version="14.3.x-scala2.12",
    node_type_id="i3.xlarge",
    num_workers=2,
    timeout=timedelta(minutes=30)
)

# Pattern 2: Use Wait object
wait = w.clusters.create(...)
cluster = wait.result()  # Blocks until ready

# Pattern 3: Manual polling with callback
def progress(cluster):
    print(f"State: {cluster.state}")

cluster = w.clusters.wait_get_cluster_running(
    cluster_id="...",
    timeout=timedelta(minutes=30),
    callback=progress
)
```

### Pagination
```python
# All list methods return iterators that handle pagination automatically
for job in w.jobs.list():  # Fetches all pages
    print(job.settings.name)

# For manual control
from databricks.sdk.service.jobs import ListJobsRequest
response = w.jobs.list(limit=10)
for job in response:
    print(job)
```

### Error Handling
```python
from databricks.sdk.errors import NotFound, PermissionDenied, ResourceAlreadyExists

try:
    cluster = w.clusters.get(cluster_id="invalid-id")
except NotFound:
    print("Cluster not found")
except PermissionDenied:
    print("Access denied")
```

---

## When Uncertain

If I'm unsure about a method, I should:

1. **Check the documentation URL pattern:**
   - `https://databricks-sdk-py.readthedocs.io/en/latest/workspace/{category}/{service}.html`

2. **Common categories:**
   - Clusters: `/workspace/compute/clusters.html`
   - Jobs: `/workspace/jobs/jobs.html`
   - Tables: `/workspace/catalog/tables.html`
   - Warehouses: `/workspace/sql/warehouses.html`
   - Serving: `/workspace/serving/serving_endpoints.html`

3. **Fetch and verify** before providing guidance on parameters or return types.

---

## Quick Reference Links

| API | Documentation URL |
|-----|-------------------|
| Authentication | https://databricks-sdk-py.readthedocs.io/en/latest/authentication.html |
| Clusters | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/compute/clusters.html |
| Jobs | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/jobs/jobs.html |
| SQL Warehouses | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/sql/warehouses.html |
| Statement Execution | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/sql/statement_execution.html |
| Tables | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/tables.html |
| Catalogs | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/catalogs.html |
| Schemas | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/schemas.html |
| Volumes | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/volumes.html |
| Files | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/files/files.html |
| Serving Endpoints | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/serving/serving_endpoints.html |
| Vector Search | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/vectorsearch/vector_search_indexes.html |
| Pipelines | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/pipelines/pipelines.html |
| Secrets | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/workspace/secrets.html |
| DBUtils | https://databricks-sdk-py.readthedocs.io/en/latest/dbutils.html |

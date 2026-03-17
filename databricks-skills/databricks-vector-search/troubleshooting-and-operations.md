# Vector Search Troubleshooting & Operations

Operational guidance for monitoring, cost optimization, capacity planning, and migration of Databricks Vector Search resources.

## Monitoring Endpoint Status

Use `get_vs_endpoint` (MCP tool) or `w.vector_search_endpoints.get_endpoint()` (SDK) to check endpoint health.

### Endpoint fields

| Field | Description |
|-------|-------------|
| `state` | `ONLINE`, `PROVISIONING`, `OFFLINE`, `YELLOW_STATE`, `RED_STATE`, `DELETED` |
| `message` | Human-readable status or error message |
| `endpoint_type` | `STANDARD` or `STORAGE_OPTIMIZED` |
| `num_indexes` | Number of indexes hosted on this endpoint |
| `creation_timestamp` | When the endpoint was created |
| `last_updated_timestamp` | When the endpoint was last modified |

### Example

```python
endpoint = w.vector_search_endpoints.get_endpoint(endpoint_name="my-endpoint")
print(f"State: {endpoint.endpoint_status.state.value}")
print(f"Indexes: {endpoint.num_indexes}")
```

**What to do per state:**
- `PROVISIONING` → Wait. Endpoint creation is asynchronous and can take several minutes.
- `ONLINE` → Ready to serve queries and host indexes.
- `OFFLINE` → Check the `message` field for error details. May require recreation.
- `YELLOW_STATE` → Endpoint is degraded but still serving. Investigate the `message` field.
- `RED_STATE` → Endpoint is unhealthy. Check `message` for details; may need support intervention.

## Monitoring Index Status

Use `get_vs_index` (MCP tool) or `w.vector_search_indexes.get_index()` (SDK) to check index health.

### Index fields

| Field | Description |
|-------|-------------|
| `status.ready` | Boolean — `True` when ready for queries, `False` when provisioning/syncing |
| `status.message` | Status details or error information |
| `status.index_url` | URL to access the index in the Databricks UI |
| `status.indexed_row_count` | Number of rows currently indexed |
| `delta_sync_index_spec.pipeline_id` | DLT pipeline ID (Delta Sync indexes only) — useful for debugging sync issues |
| `index_type` | `DELTA_SYNC` or `DIRECT_ACCESS` |

### Example

```python
index = w.vector_search_indexes.get_index(index_name="catalog.schema.my_index")
if index.status.ready:
    print("Index is ONLINE")
else:
    print(f"Index is NOT_READY: {index.status.message}")
```

## Pipeline Type Trade-offs

Delta Sync indexes use a DLT pipeline to sync data from the source Delta table. The pipeline type determines sync behavior:

| Pipeline Type | Behavior | Cost | Best for |
|---------------|----------|------|----------|
| **TRIGGERED** | Manual sync via `sync_vs_index()` | Lower — runs only when triggered | Batch updates, periodic refreshes, cost-sensitive workloads |
| **CONTINUOUS** | Auto-syncs on source table changes | Higher — always running | Real-time freshness, applications needing up-to-date results |

### Triggering a sync

```python
# For TRIGGERED pipelines only
w.vector_search_indexes.sync_index(index_name="catalog.schema.my_index")
# Check sync progress with get_index()
```

**Tip:** CONTINUOUS pipelines cannot be synced manually — they sync automatically. Calling `sync_index()` on a CONTINUOUS index will raise an error.

## Cost Optimization

### Endpoint type selection

| Factor | Standard | Storage-Optimized |
|--------|----------|-------------------|
| Query latency | 20-50ms | 300-500ms |
| Cost | Higher | ~7x lower |
| Max capacity | 320M vectors (768 dim) | 1B+ vectors (768 dim) |
| Indexing speed | Slower | 20x faster |

**Recommendation:** Start with Storage-Optimized unless you need sub-100ms latency. It handles most RAG workloads well.

### Reducing storage costs

- Use `columns_to_sync` to limit which columns are synced to the index. Only synced columns are available in query results, so include only what you need.
- Choose TRIGGERED pipelines for batch workloads to avoid continuous compute costs.

```python
# Only sync the columns you actually need in query results
delta_sync_index_spec={
    "source_table": "catalog.schema.documents",
    "embedding_source_columns": [
        {"name": "content", "embedding_model_endpoint_name": "databricks-gte-large-en"}
    ],
    "pipeline_type": "TRIGGERED",
    "columns_to_sync": ["id", "content", "title"]  # Exclude large unused columns
}
```

## Capacity Planning

| Endpoint Type | Max Vectors (768 dim) | Guidance |
|---------------|----------------------|----------|
| Standard | ~320M | Suitable for most production workloads under 300M documents |
| Storage-Optimized | 1B+ | Large-scale corpora, enterprise knowledge bases |

**Estimating needs:**
- One document typically maps to one vector (or multiple if chunked)
- If chunking at ~512 tokens, expect 2-5 vectors per page of text
- Monitor `num_indexes` on your endpoint to understand utilization

## Migration Patterns

### Changing endpoint type

Endpoints are **immutable after creation** — you cannot change the type (Standard ↔ Storage-Optimized) of an existing endpoint. To migrate:

1. **Create a new endpoint** with the desired type
2. **Recreate indexes** on the new endpoint pointing to the same source tables
3. **Wait for sync** to complete (check index state)
4. **Update applications** to query the new index names
5. **Delete old indexes**, then delete the old endpoint

```python
# Step 1: Create new endpoint
w.vector_search_endpoints.create_endpoint(
    name="my-endpoint-storage-optimized",
    endpoint_type="STORAGE_OPTIMIZED"
)

# Step 2: Recreate index on new endpoint (same source table)
w.vector_search_indexes.create_index(
    name="catalog.schema.my_index_v2",
    endpoint_name="my-endpoint-storage-optimized",
    primary_key="id",
    index_type="DELTA_SYNC",
    delta_sync_index_spec={
        "source_table": "catalog.schema.documents",
        "embedding_source_columns": [
            {"name": "content", "embedding_model_endpoint_name": "databricks-gte-large-en"}
        ],
        "pipeline_type": "TRIGGERED"
    }
)

# Step 3: Trigger sync and wait for ONLINE state
w.vector_search_indexes.sync_index(index_name="catalog.schema.my_index_v2")

# Step 4: Update your application to use "catalog.schema.my_index_v2"
# Step 5: Clean up old resources
w.vector_search_indexes.delete_index(index_name="catalog.schema.my_index")
w.vector_search_endpoints.delete_endpoint(endpoint_name="my-endpoint")
```

## Expanded Troubleshooting

| Issue | Likely Cause | Solution |
|-------|-------------|----------|
| **Index stuck in NOT_READY** | Sync pipeline failed or source table issue | Check `message` field via `get_vs_index()`. Inspect the DLT pipeline using `pipeline_id`. |
| **Embedding dimension mismatch** | Query vector dimensions ≠ index dimensions | Ensure your embedding model output matches the `embedding_dimension` in the index spec. |
| **Permission errors on create** | Missing Unity Catalog privileges | User needs `CREATE TABLE` on the schema and `USE CATALOG`/`USE SCHEMA` privileges. |
| **Index returns NOT_FOUND** | Wrong name format or index deleted | Index names must be fully qualified: `catalog.schema.index_name`. |
| **Sync not running (TRIGGERED)** | Sync not triggered after source update | Call `sync_vs_index()` or `w.vector_search_indexes.sync_index()` after updating source data. |
| **Endpoint NOT_FOUND** | Endpoint name typo or deleted | List all endpoints with `get_vs_endpoint()` (no name) to verify available endpoints. |
| **Query returns empty results** | Index not yet synced, or filters too restrictive | Check index state is ONLINE. Verify `columns_to_sync` includes queried columns. Test without filters first. |
| **filters_json has no effect** | Using wrong filter syntax for endpoint type | Standard endpoints use dict-format filters (`filters_json` in SDK, `filters` as dict in `databricks-vectorsearch`). Storage-Optimized endpoints use SQL-like string filters (`filters` as str in `databricks-vectorsearch`). |
| **Quota or capacity errors** | Too many indexes or vectors | Check `num_indexes` on endpoint. Consider Storage-Optimized for higher capacity. |
| **Upsert fails on Delta Sync** | Cannot upsert to Delta Sync indexes | Upsert/delete operations only work on Direct Access indexes. Delta Sync indexes update via their source table. |

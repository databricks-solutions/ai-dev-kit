# AI Search Troubleshooting & Operations

Operational guidance for monitoring, cost optimization, capacity planning, and migration of Databricks AI Search resources.

## Monitoring Endpoint Status

Use `manage_vs_endpoint(action="get")` (MCP tool) or `client.get_endpoint()` (SDK) to check endpoint health.

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
from databricks.ai_search.client import AISearchClient

client = AISearchClient()
endpoint = client.get_endpoint(name="my-endpoint")
```

**What to do per state:**
- `PROVISIONING` → Wait. Endpoint creation is asynchronous and can take several minutes.
- `ONLINE` → Ready to serve queries and host indexes.
- `OFFLINE` → Check the `message` field for error details. May require recreation.
- `YELLOW_STATE` → Endpoint is degraded but still serving. Investigate the `message` field.
- `RED_STATE` → Endpoint is unhealthy. Check `message` for details; may need support intervention.

## Monitoring Index Status

Use `manage_vs_index(action="get")` (MCP tool) or `client.get_index()` (SDK) to check index health.

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
index = client.get_index(
    endpoint_name="my-endpoint",
    index_name="catalog.schema.my_index"
)
index.describe()
```

## Pipeline Type Trade-offs

Delta Sync indexes use a DLT pipeline to sync data from the source Delta table. The pipeline type determines sync behavior:

| Pipeline Type | Behavior | Cost | Best for |
|---------------|----------|------|----------|
| **TRIGGERED** | Manual sync via `index.sync()` | Lower — runs only when triggered | Batch updates, periodic refreshes, cost-sensitive workloads |
| **CONTINUOUS** | Auto-syncs on source table changes | Higher — always running | Real-time freshness, applications needing up-to-date results |

### Triggering a sync

```python
index = client.get_index(
    endpoint_name="my-vs-endpoint",
    index_name="catalog.schema.my_index"
)
index.sync()
```

**Tip:** CONTINUOUS pipelines cannot be synced manually — they sync automatically. Calling `index.sync()` on a CONTINUOUS index will raise an error.

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
index = client.create_delta_sync_index(
    endpoint_name="my-vs-endpoint",
    source_table_name="catalog.schema.documents",
    index_name="catalog.schema.my_index",
    pipeline_type="TRIGGERED",
    primary_key="id",
    embedding_source_column="content",
    embedding_model_endpoint_name="databricks-gte-large-en",
    columns_to_sync=["id", "content", "title"]  # Exclude large unused columns
)
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
from databricks.ai_search.client import AISearchClient

client = AISearchClient()

# Step 1: Create new endpoint
client.create_endpoint(
    name="my-endpoint-storage-optimized",
    endpoint_type="STORAGE_OPTIMIZED"
)

# Step 2: Recreate index on new endpoint (same source table)
client.create_delta_sync_index(
    endpoint_name="my-endpoint-storage-optimized",
    source_table_name="catalog.schema.documents",
    index_name="catalog.schema.my_index_v2",
    pipeline_type="TRIGGERED",
    primary_key="id",
    embedding_source_column="content",
    embedding_model_endpoint_name="databricks-gte-large-en"
)

# Step 3: Trigger sync and wait for ONLINE state
index_v2 = client.get_index(
    endpoint_name="my-endpoint-storage-optimized",
    index_name="catalog.schema.my_index_v2"
)
index_v2.sync()

# Step 4: Update your application to use "catalog.schema.my_index_v2"
# Step 5: Clean up old resources
client.delete_index(index_name="catalog.schema.my_index")
client.delete_endpoint(name="my-endpoint")
```

## Performance & Capacity

### Production performance targets

| Metric | Target |
|--------|--------|
| P95 latency | < 500ms |
| P99 latency | < 1 second |
| Success rate | > 99.5% |

### Endpoint sizing

Operate at ~65% of maximum capacity to preserve headroom for traffic spikes. For example, to sustain 310 RPS, size your endpoint for ~480 RPS maximum capacity.

### Authentication performance

Use OAuth service principals instead of Personal Access Tokens for up to 100ms faster response time and higher request rate limits.

### Debugging latency with component timing

Set `debug_level=1` in `similarity_search()` to return per-component latency:

- `ann_time` — approximate nearest neighbor search duration
- `embedding_gen_time` — query embedding generation on the model endpoint
- `reranker_time` — reranking duration (if using `DatabricksReranker`)
- `response_time` — total end-to-end latency

If `embedding_gen_time` dominates, consider disabling scale-to-zero on your embedding endpoint or increasing its provisioned concurrency.

For full load testing guidance, see the [AI Search endpoint load test documentation](https://docs.databricks.com/aws/en/ai-search/endpoint-load-test).

## Expanded Troubleshooting

| Issue | Likely Cause | Solution |
|-------|-------------|----------|
| **Index stuck in NOT_READY** | Sync pipeline failed or source table issue | Check `message` field via `manage_vs_index(action="get")`. Inspect the DLT pipeline using `pipeline_id`. |
| **Embedding dimension mismatch** | Query vector dimensions ≠ index dimensions | Ensure your embedding model output matches the `embedding_dimension` in the index spec. |
| **Permission errors on create** | Missing Unity Catalog privileges | User needs `CREATE TABLE` on the schema and `USE CATALOG`/`USE SCHEMA` privileges. |
| **Index returns NOT_FOUND** | Wrong name format or index deleted | Index names must be fully qualified: `catalog.schema.index_name`. |
| **Sync not running (TRIGGERED)** | Sync not triggered after source update | Call `manage_vs_index(action="sync")` or `index.sync()` after updating source data. |
| **Endpoint NOT_FOUND** | Endpoint name typo or deleted | List all endpoints with `manage_vs_endpoint(action="list")` to verify available endpoints. |
| **Query returns empty results** | Index not yet synced, or filters too restrictive | Check index state is ONLINE. Verify `columns_to_sync` includes queried columns. Test without filters first. |
| **Filters not working** | Wrong filter syntax for endpoint type | Standard endpoints use a dict: `filters={"col": "val"}`. Storage-Optimized use a SQL string: `filters="col = 'val'"`. See [filtering.md](filtering.md). |
| **Quota or capacity errors** | Too many indexes or vectors | Check `num_indexes` on endpoint. Consider Storage-Optimized for higher capacity. |
| **Upsert fails on Delta Sync** | Cannot upsert to Delta Sync indexes | Upsert/delete operations only work on Direct Access indexes. Delta Sync indexes update via their source table. |
| **High latency (429 errors)** | Endpoint over capacity | Increase endpoint capacity. Implement client-side rate limiting with exponential backoff. |

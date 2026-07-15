---
name: databricks-vector-search
description: "Patterns for Databricks Vector Search: create endpoints and indexes, query with filters, manage embeddings. Use when building RAG applications, semantic search, or similarity matching. Covers both storage-optimized and standard endpoints."
---

# Databricks Vector Search

Patterns for creating, managing, and querying vector search indexes for RAG and semantic search applications.

## When to Use

Use this skill when:
- Building RAG (Retrieval-Augmented Generation) applications
- Implementing semantic search or similarity matching
- Creating vector indexes from Delta tables
- Choosing between storage-optimized and standard endpoints
- Querying vector indexes with filters

## Overview

Databricks Vector Search provides managed vector similarity search with automatic embedding generation and Delta Lake integration.

| Component | Description |
|-----------|-------------|
| **Endpoint** | Compute resource hosting indexes (Standard or Storage-Optimized) |
| **Index** | Vector data structure for similarity search |
| **Delta Sync** | Auto-syncs with source Delta table |
| **Direct Access** | Manual CRUD operations on vectors |

## Endpoint Types

| Type | Latency | Capacity | Cost | Best For |
|------|---------|----------|------|----------|
| **Standard** | 20-50ms | 320M vectors (768 dim) | Higher | Real-time, low-latency |
| **Storage-Optimized** | 300-500ms | 1B+ vectors (768 dim) | 7x lower | Large-scale, cost-sensitive |

## Index Types

| Type | Embeddings | Sync | Use Case |
|------|------------|------|----------|
| **Delta Sync (managed)** | Databricks computes | Auto from Delta | Easiest setup |
| **Delta Sync (self-managed)** | You provide | Auto from Delta | Custom embeddings |
| **Direct Access** | You provide | Manual CRUD | Real-time updates |

## Quick Start

### Create Endpoint

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Create a standard endpoint
endpoint = w.vector_search_endpoints.create_endpoint(
    name="my-vs-endpoint",
    endpoint_type="STANDARD"  # or "STORAGE_OPTIMIZED"
)
# Note: Endpoint creation is asynchronous; check status with get_endpoint()
```

### Create Delta Sync Index (Managed Embeddings)

```python
# Source table must have: primary key column + text column
index = w.vector_search_indexes.create_index(
    name="catalog.schema.my_index",
    endpoint_name="my-vs-endpoint",
    primary_key="id",
    index_type="DELTA_SYNC",
    delta_sync_index_spec={
        "source_table": "catalog.schema.documents",
        "embedding_source_columns": [
            {
                "name": "content",  # Text column to embed
                "embedding_model_endpoint_name": "databricks-gte-large-en"
            }
        ],
        "pipeline_type": "TRIGGERED"  # or "CONTINUOUS"
    }
)
```

### Query Index

```python
results = w.vector_search_indexes.query_index(
    index_name="catalog.schema.my_index",
    columns=["id", "content", "metadata"],
    query_text="What is machine learning?",
    num_results=5
)

for doc in results.result.data_array:
    score = doc[-1]  # Similarity score is last column
    print(f"Score: {score}, Content: {doc[1][:100]}...")
```

## Common Patterns

### Create Storage-Optimized Endpoint

```python
# For large-scale, cost-effective deployments
endpoint = w.vector_search_endpoints.create_endpoint(
    name="my-storage-endpoint",
    endpoint_type="STORAGE_OPTIMIZED"
)
```

### Delta Sync with Self-Managed Embeddings

```python
# Source table must have: primary key + embedding vector column
index = w.vector_search_indexes.create_index(
    name="catalog.schema.my_index",
    endpoint_name="my-vs-endpoint",
    primary_key="id",
    index_type="DELTA_SYNC",
    delta_sync_index_spec={
        "source_table": "catalog.schema.documents",
        "embedding_vector_columns": [
            {
                "name": "embedding",  # Pre-computed embedding column
                "embedding_dimension": 768
            }
        ],
        "pipeline_type": "TRIGGERED"
    }
)
```

### Direct Access Index

```python
import json

# Create index for manual CRUD
index = w.vector_search_indexes.create_index(
    name="catalog.schema.direct_index",
    endpoint_name="my-vs-endpoint",
    primary_key="id",
    index_type="DIRECT_ACCESS",
    direct_access_index_spec={
        "embedding_vector_columns": [
            {"name": "embedding", "embedding_dimension": 768}
        ],
        "schema_json": json.dumps({
            "id": "string",
            "text": "string",
            "embedding": "array<float>",
            "metadata": "string"
        })
    }
)

# Upsert data
w.vector_search_indexes.upsert_data_vector_index(
    index_name="catalog.schema.direct_index",
    inputs_json=json.dumps([
        {"id": "1", "text": "Hello", "embedding": [0.1, 0.2, ...], "metadata": "doc1"},
        {"id": "2", "text": "World", "embedding": [0.3, 0.4, ...], "metadata": "doc2"},
    ])
)

# Delete data
w.vector_search_indexes.delete_data_vector_index(
    index_name="catalog.schema.direct_index",
    primary_keys=["1", "2"]
)
```

### Query with Embedding Vector

```python
# When you have pre-computed query embedding
results = w.vector_search_indexes.query_index(
    index_name="catalog.schema.my_index",
    columns=["id", "text"],
    query_vector=[0.1, 0.2, 0.3, ...],  # Your 768-dim vector
    num_results=10
)
```

### Hybrid Search (Semantic + Keyword)

Hybrid search combines vector similarity (ANN) with BM25 keyword scoring. Use it when queries contain exact terms that must match — SKUs, error codes, proper nouns, or technical terminology — where pure semantic search might miss keyword-specific results. See [search-modes.md](search-modes.md) for detailed guidance on choosing between ANN and hybrid search.

```python
# Combines vector similarity with keyword matching
results = w.vector_search_indexes.query_index(
    index_name="catalog.schema.my_index",
    columns=["id", "content"],
    query_text="SPARK-12345 executor memory error",
    query_type="HYBRID",
    num_results=10
)
```

## Filtering

### Standard Endpoint Filters (Dictionary)

```python
# filters_json uses dictionary format
results = w.vector_search_indexes.query_index(
    index_name="catalog.schema.my_index",
    columns=["id", "content"],
    query_text="machine learning",
    num_results=10,
    filters_json='{"category": "ai", "status": ["active", "pending"]}'
)
```

### Storage-Optimized Filters (SQL-like)

Storage-Optimized endpoints use SQL-like filter syntax via the `databricks-vectorsearch` package's `filters` parameter (accepts a string):

```python
from databricks.vector_search.client import VectorSearchClient

vsc = VectorSearchClient()
index = vsc.get_index(endpoint_name="my-storage-endpoint", index_name="catalog.schema.my_index")

# SQL-like filter syntax for storage-optimized endpoints
results = index.similarity_search(
    query_text="machine learning",
    columns=["id", "content"],
    num_results=10,
    filters="category = 'ai' AND status IN ('active', 'pending')"
)

# More filter examples
# filters="price > 100 AND price < 500"
# filters="department LIKE 'eng%'"
# filters="created_at >= '2024-01-01'"
```

### Trigger Index Sync

```python
# For TRIGGERED pipeline type, manually sync
w.vector_search_indexes.sync_index(
    index_name="catalog.schema.my_index"
)
```

### Scan All Index Entries

```python
# Retrieve all vectors (for debugging/export)
scan_result = w.vector_search_indexes.scan_index(
    index_name="catalog.schema.my_index",
    num_results=100
)
```

## Reference Files

| Topic | File | Description |
|-------|------|-------------|
| Index Types | [index-types.md](index-types.md) | Detailed comparison of Delta Sync (managed/self-managed) vs Direct Access |
| End-to-End RAG | [end-to-end-rag.md](end-to-end-rag.md) | Complete walkthrough: source table → endpoint → index → query → agent integration |
| Search Modes | [search-modes.md](search-modes.md) | When to use semantic (ANN) vs hybrid search, decision guide |
| Operations | [troubleshooting-and-operations.md](troubleshooting-and-operations.md) | Monitoring, cost optimization, capacity planning, migration |

## CLI Quick Reference

```bash
# List endpoints
databricks vector-search endpoints list

# Create endpoint
databricks vector-search endpoints create \
    --name my-endpoint \
    --endpoint-type STANDARD

# List indexes on endpoint
databricks vector-search indexes list-indexes \
    --endpoint-name my-endpoint

# Get index status
databricks vector-search indexes get-index \
    --index-name catalog.schema.my_index

# Sync index (for TRIGGERED)
databricks vector-search indexes sync-index \
    --index-name catalog.schema.my_index

# Delete index
databricks vector-search indexes delete-index \
    --index-name catalog.schema.my_index
```

## Common Issues

| Issue | Solution |
|-------|----------|
| **Index sync slow** | Use Storage-Optimized endpoints (20x faster indexing) |
| **Query latency high** | Use Standard endpoint for <100ms latency |
| **filters_json not working** | Storage-Optimized uses SQL-like string filters via `databricks-vectorsearch` package's `filters` parameter |
| **Embedding dimension mismatch** | Ensure query and index dimensions match |
| **Index not updating** | Check pipeline_type; use sync_index() for TRIGGERED |
| **Out of capacity** | Upgrade to Storage-Optimized (1B+ vectors) |
| **`query_vector` truncated by MCP tool** | MCP tool calls serialize arrays as JSON and can truncate large vectors (e.g. 1024-dim). Use `query_text` instead (for managed embedding indexes), or use the Databricks SDK/CLI to pass raw vectors |

## Embedding Models

Databricks provides built-in embedding models:

| Model | Dimensions | Context Window | Use Case |
|-------|------------|----------------|----------|
| `databricks-gte-large-en` | 1024 | 8192 tokens | English text, high quality |
| `databricks-bge-large-en` | 1024 | 512 tokens | English text, general purpose |

```python
# Use with managed embeddings
embedding_source_columns=[
    {
        "name": "content",
        "embedding_model_endpoint_name": "databricks-gte-large-en"
    }
]
```

## MCP Tools

The following MCP tools are available for managing Vector Search infrastructure. For a full end-to-end walkthrough, see [end-to-end-rag.md](end-to-end-rag.md).

### manage_vs_endpoint - Endpoint Management

| Action | Description | Required Params |
|--------|-------------|-----------------|
| `create_or_update` | Create endpoint (STANDARD or STORAGE_OPTIMIZED). Idempotent | name |
| `get` | Get endpoint details | name |
| `list` | List all endpoints | (none) |
| `delete` | Delete endpoint (indexes must be deleted first) | name |

```python
# Create or update an endpoint
result = manage_vs_endpoint(action="create_or_update", name="my-vs-endpoint", endpoint_type="STANDARD")
# Returns {"name": "my-vs-endpoint", "endpoint_type": "STANDARD", "created": True}

# List all endpoints
endpoints = manage_vs_endpoint(action="list")

# Get specific endpoint
endpoint = manage_vs_endpoint(action="get", name="my-vs-endpoint")
```

### manage_vs_index - Index Management

| Action | Description | Required Params |
|--------|-------------|-----------------|
| `create_or_update` | Create index. Idempotent, auto-triggers sync for DELTA_SYNC | name, endpoint_name, primary_key |
| `get` | Get index details | name |
| `list` | List indexes. Optional endpoint_name filter | (none) |
| `delete` | Delete index | name |

```python
# Create a Delta Sync index with managed embeddings
result = manage_vs_index(
    action="create_or_update",
    name="catalog.schema.my_index",
    endpoint_name="my-vs-endpoint",
    primary_key="id",
    index_type="DELTA_SYNC",
    delta_sync_index_spec={
        "source_table": "catalog.schema.docs",
        "embedding_source_columns": [{"name": "content", "embedding_model_endpoint_name": "databricks-gte-large-en"}],
        "pipeline_type": "TRIGGERED"
    }
)

# Get a specific index
index = manage_vs_index(action="get", name="catalog.schema.my_index")

# List all indexes on an endpoint
indexes = manage_vs_index(action="list", endpoint_name="my-vs-endpoint")

# List all indexes across all endpoints
all_indexes = manage_vs_index(action="list")
```

### query_vs_index - Query (Hot Path)

Query index with `query_text`, `query_vector`, or hybrid (`query_type="HYBRID"`). Prefer `query_text` over `query_vector` — MCP tool calls can truncate large embedding arrays (1024-dim).

```python
# Query an index
results = query_vs_index(
    index_name="catalog.schema.my_index",
    columns=["id", "content"],
    query_text="machine learning best practices",
    num_results=5
)

# Hybrid search (combines vector + keyword)
results = query_vs_index(
    index_name="catalog.schema.my_index",
    columns=["id", "content"],
    query_text="SPARK-12345 memory error",
    query_type="HYBRID",
    num_results=10
)
```

### manage_vs_data - Data Operations

| Action | Description | Required Params |
|--------|-------------|-----------------|
| `upsert` | Insert/update records | index_name, inputs_json |
| `delete` | Delete by primary key | index_name, primary_keys |
| `scan` | Scan index contents | index_name |
| `sync` | Trigger sync for TRIGGERED indexes | index_name |

```python
# Upsert data into a Direct Access index
manage_vs_data(
    action="upsert",
    index_name="catalog.schema.my_index",
    inputs_json=[{"id": "doc1", "content": "...", "embedding": [0.1, 0.2, ...]}]
)

# Trigger manual sync for a TRIGGERED pipeline index
manage_vs_data(action="sync", index_name="catalog.schema.my_index")

# Scan index contents
manage_vs_data(action="scan", index_name="catalog.schema.my_index", num_results=100)
```

## Notes

- **Storage-Optimized is newer** — better for most use cases unless you need <100ms latency
- **Delta Sync recommended** — easier than Direct Access for most scenarios
- **Hybrid search** — available for both Delta Sync and Direct Access indexes
- **`columns_to_sync` matters** — only synced columns are available in query results; include all columns you need
- **Filter syntax differs by endpoint** — Standard uses dict-format filters, Storage-Optimized uses SQL-like string filters. Use the `databricks-vectorsearch` package's `filters` parameter which accepts both formats
- **Management vs runtime** — MCP tools above handle lifecycle management; for agent tool-calling at runtime, use `VectorSearchRetrieverTool` or the Databricks managed Vector Search MCP server

## Related Skills

- **[databricks-model-serving](../databricks-model-serving/SKILL.md)** - Deploy agents that use VectorSearchRetrieverTool
- **[databricks-agent-bricks](../databricks-agent-bricks/SKILL.md)** - Knowledge Assistants use RAG over indexed documents
- **[databricks-unstructured-pdf-generation](../databricks-unstructured-pdf-generation/SKILL.md)** - Generate documents to index in Vector Search
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** - Manage the catalogs and tables that back Delta Sync indexes
- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** - Build Delta tables used as Vector Search sources

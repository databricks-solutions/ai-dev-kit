# Vector Search Index Types

## Comparison Matrix

| Feature | Delta Sync (Managed) | Delta Sync (Self-Managed) | Direct Access |
|---------|---------------------|---------------------------|---------------|
| **Embeddings** | Databricks computes | You provide | You provide |
| **Sync** | Auto from Delta | Auto from Delta | Manual CRUD |
| **Setup** | Easiest | Medium | Most control |
| **Source** | Delta table + text | Delta table + vectors | API calls |
| **Best for** | Quick start, RAG | Custom models | Real-time apps |

## Delta Sync with Managed Embeddings

Databricks automatically computes embeddings from your text column.

### Requirements

- Source Delta table with:
  - Primary key column (unique identifier)
  - Text column (content to embed)
- Embedding model endpoint (or use built-in)

### Create Index

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

index = w.vector_search_indexes.create_index(
    name="catalog.schema.docs_index",
    endpoint_name="my-vs-endpoint",
    primary_key="doc_id",
    index_type="DELTA_SYNC",
    delta_sync_index_spec={
        "source_table": "catalog.schema.documents",
        "embedding_source_columns": [
            {
                "name": "content",
                "embedding_model_endpoint_name": "databricks-gte-large-en"
            }
        ],
        "pipeline_type": "TRIGGERED",  # or "CONTINUOUS"
        "columns_to_sync": ["doc_id", "content", "title", "category"]
    }
)
```

### Pipeline Types

| Type | Behavior | Cost | Use Case |
|------|----------|------|----------|
| `TRIGGERED` | Manual sync via API | Lower | Batch updates |
| `CONTINUOUS` | Auto-sync on changes | Higher | Real-time sync |

### Source Table Example

```sql
CREATE TABLE catalog.schema.documents (
    doc_id STRING,
    title STRING,
    content STRING,  -- Text to embed
    category STRING,
    created_at TIMESTAMP
);
```

## Delta Sync with Self-Managed Embeddings

You pre-compute embeddings and store them in the source table.

### Requirements

- Source Delta table with:
  - Primary key column
  - Embedding vector column (array of floats)

### Create Index

```python
index = w.vector_search_indexes.create_index(
    name="catalog.schema.custom_index",
    endpoint_name="my-vs-endpoint",
    primary_key="id",
    index_type="DELTA_SYNC",
    delta_sync_index_spec={
        "source_table": "catalog.schema.embedded_docs",
        "embedding_vector_columns": [
            {
                "name": "embedding",
                "embedding_dimension": 768
            }
        ],
        "pipeline_type": "TRIGGERED"
    }
)
```

### Compute Embeddings

```python
from databricks.sdk import WorkspaceClient
import pandas as pd

w = WorkspaceClient()

def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Call embedding endpoint for texts."""
    response = w.serving_endpoints.query(
        name="databricks-gte-large-en",
        input=texts
    )
    return [item.embedding for item in response.data]

# Add embeddings to your data
df = spark.table("catalog.schema.documents").toPandas()
df["embedding"] = get_embeddings(df["content"].tolist())

# Write back to Delta
spark.createDataFrame(df).write.mode("overwrite").saveAsTable(
    "catalog.schema.embedded_docs"
)
```

### Source Table Example

```sql
CREATE TABLE catalog.schema.embedded_docs (
    id STRING,
    content STRING,
    embedding ARRAY<FLOAT>,  -- Pre-computed embedding
    metadata STRING
);
```

## Direct Access Index

Full control over vector data via CRUD API. No Delta table sync.

### Requirements

- Define schema upfront
- Manage upsert/delete operations yourself

### Create Index

```python
import json

index = w.vector_search_indexes.create_index(
    name="catalog.schema.realtime_index",
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
            "category": "string",
            "score": "float"
        })
    }
)
```

### Upsert Data

```python
import json

# Insert or update vectors
w.vector_search_indexes.upsert_data_vector_index(
    index_name="catalog.schema.realtime_index",
    inputs_json=json.dumps([
        {
            "id": "doc-001",
            "text": "Machine learning basics",
            "embedding": [0.1, 0.2, 0.3, ...],  # 768 floats
            "category": "ml",
            "score": 0.95
        },
        {
            "id": "doc-002",
            "text": "Deep learning overview",
            "embedding": [0.4, 0.5, 0.6, ...],
            "category": "dl",
            "score": 0.88
        }
    ])
)
```

### Delete Data

```python
w.vector_search_indexes.delete_data_vector_index(
    index_name="catalog.schema.realtime_index",
    primary_keys=["doc-001", "doc-002"]
)
```

### Attach Embedding Model (Optional)

For Direct Access with text queries:

```python
# Create index with embedding model for query-time embedding
index = w.vector_search_indexes.create_index(
    name="catalog.schema.hybrid_index",
    endpoint_name="my-vs-endpoint",
    primary_key="id",
    index_type="DIRECT_ACCESS",
    direct_access_index_spec={
        "embedding_vector_columns": [
            {"name": "embedding", "embedding_dimension": 768}
        ],
        "embedding_model_endpoint_name": "databricks-gte-large-en",  # For query_text
        "schema_json": json.dumps({...})
    }
)
```

## Choosing the Right Type

```
Start here:
│
├─ Do you have pre-computed embeddings?
│   ├─ Yes → Do you want auto-sync from Delta?
│   │         ├─ Yes → Delta Sync (Self-Managed)
│   │         └─ No  → Direct Access
│   │
│   └─ No → Delta Sync (Managed Embeddings)
│
└─ Do you need real-time updates (<1 sec)?
    ├─ Yes → Direct Access
    └─ No  → Delta Sync (any type)
```

## Endpoint Selection

After choosing index type, choose endpoint:

| Scenario | Endpoint Type |
|----------|---------------|
| Need <100ms latency | Standard |
| >100M vectors | Storage-Optimized |
| Cost-sensitive | Storage-Optimized |
| Default choice | Storage-Optimized |

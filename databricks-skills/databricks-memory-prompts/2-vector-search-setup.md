# Vector Search Setup for Memory

Configure Databricks Vector Search to enable semantic retrieval over memory tables.

## Overview

Memory retrieval works best with semantic search — finding memories by meaning, not just keywords. This guide shows how to set up Vector Search over the unified `memory_embeddings` table.

## Prerequisites

- Unity Catalog enabled workspace
- Vector Search endpoint (or create one)
- Memory tables created (see [1-memory-schema.md](1-memory-schema.md))

## Step 1: Create Vector Search Endpoint

```python
from databricks.vector_search.client import VectorSearchClient

vsc = VectorSearchClient()

# Create endpoint if it doesn't exist
try:
    vsc.create_endpoint(
        name="memory_search_endpoint",
        endpoint_type="STANDARD"  # or "PERFORMANCE" for production
    )
except Exception as e:
    if "already exists" not in str(e):
        raise
```

## Step 2: Create Sync Pipeline

The embeddings table needs to sync from source tables. Use a Lakeflow pipeline:

```python
# In a Databricks notebook with DLT enabled

import dlt
from pyspark.sql.functions import col, lit, concat_ws, coalesce

@dlt.table(
    name="memory_embeddings_staging",
    comment="Staging table for memory embeddings"
)
def memory_embeddings_staging():
    # Combine all memory sources
    decisions = (
        spark.table("my_catalog.memory.decisions")
        .select(
            col("id").alias("source_id"),
            lit("decision").alias("memory_type"),
            concat_ws(" | ", 
                col("decision"), 
                coalesce(col("context"), lit("")),
                coalesce(col("rationale"), lit(""))
            ).alias("content"),
            col("task_scope"),
            col("confidence"),
            col("created_at")
        )
    )
    
    patterns = (
        spark.table("my_catalog.memory.patterns")
        .select(
            col("id").alias("source_id"),
            lit("pattern").alias("memory_type"),
            concat_ws(" | ", 
                col("pattern"), 
                coalesce(col("evidence"), lit(""))
            ).alias("content"),
            col("task_scope"),
            col("confidence"),
            col("last_seen").alias("created_at")
        )
    )
    
    feedback = (
        spark.table("my_catalog.memory.feedback")
        .filter(col("resolved") == False)  # Only unresolved feedback
        .select(
            col("id").alias("source_id"),
            lit("feedback").alias("memory_type"),
            concat_ws(" | ", 
                col("feedback_type"),
                coalesce(col("correction"), lit("")),
                coalesce(col("output_text"), lit(""))
            ).alias("content"),
            col("task_scope"),
            lit(0.5).alias("confidence"),  # Default confidence for feedback
            col("created_at")
        )
    )
    
    return decisions.union(patterns).union(feedback)
```

## Step 3: Create Vector Search Index

```python
from databricks.vector_search.client import VectorSearchClient

vsc = VectorSearchClient()

# Create the index with managed embeddings
index = vsc.create_delta_sync_index(
    endpoint_name="memory_search_endpoint",
    source_table_name="my_catalog.memory.memory_embeddings_staging",
    index_name="my_catalog.memory.memory_index",
    primary_key="source_id",
    pipeline_type="TRIGGERED",  # or "CONTINUOUS" for real-time
    embedding_source_column="content",
    embedding_model_endpoint_name="databricks-gte-large-en"
)

print(f"Index created: {index.name}")
```

## Step 4: Query the Index

```python
def search_memory(
    query: str,
    task_scope: str = None,
    memory_types: list = None,
    min_confidence: float = 0.0,
    k: int = 10
) -> list:
    """
    Search memory for relevant context.
    
    Args:
        query: The search query
        task_scope: Filter to specific task (optional)
        memory_types: Filter to specific types (optional)
        min_confidence: Minimum confidence threshold
        k: Number of results to return
    
    Returns:
        List of memory items with scores
    """
    vsc = VectorSearchClient()
    index = vsc.get_index("memory_search_endpoint", "my_catalog.memory.memory_index")
    
    # Build filters
    filters = {}
    if task_scope:
        filters["task_scope"] = task_scope
    if memory_types:
        filters["memory_type"] = {"$in": memory_types}
    if min_confidence > 0:
        filters["confidence"] = {"$gte": min_confidence}
    
    # Execute search
    results = index.similarity_search(
        query_text=query,
        columns=["source_id", "memory_type", "content", "confidence", "task_scope"],
        filters=filters if filters else None,
        num_results=k
    )
    
    # Parse results
    memories = []
    for row in results.get("result", {}).get("data_array", []):
        memories.append({
            "id": row[0],
            "type": row[1],
            "content": row[2],
            "confidence": row[3],
            "task_scope": row[4],
            "score": row[5] if len(row) > 5 else None
        })
    
    return memories
```

## Step 5: Sync Schedule

For production, set up a scheduled sync:

```python
# Trigger sync manually
index.sync()

# Or set up a scheduled job
# The TRIGGERED pipeline will sync whenever source tables change
```

## Index Management

### Check Sync Status

```python
status = index.describe()
print(f"Status: {status['status']['ready']}")
print(f"Indexed rows: {status['status'].get('indexed_row_count', 'N/A')}")
```

### Force Resync

```python
# If embeddings get out of sync
index.sync()
```

### Delete and Recreate

```python
# For schema changes
vsc.delete_index("memory_search_endpoint", "my_catalog.memory.memory_index")
# Then recreate with Step 3
```

## Performance Tuning

| Setting | Development | Production |
|---------|-------------|------------|
| Endpoint type | STANDARD | PERFORMANCE |
| Pipeline type | TRIGGERED | CONTINUOUS |
| num_results | 5-10 | 3-5 (latency-sensitive) |
| Sync frequency | On-demand | Real-time |

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Index not ready | Wait for sync to complete; check `index.describe()` |
| Empty results | Verify source tables have data; check filter syntax |
| Slow queries | Reduce `num_results`; use PERFORMANCE endpoint |
| Stale results | Trigger manual sync with `index.sync()` |
| Embedding errors | Ensure `content` column has valid text (no nulls) |

# End-to-End RAG with Vector Search

Build a complete Retrieval-Augmented Generation pipeline: prepare documents, create a vector index, query it, and wire it into an agent.

## MCP Tools Used

| Tool | Step |
|------|------|
| `execute_sql` | Create source table, insert documents |
| `create_vs_endpoint` | Create compute endpoint |
| `create_vs_index` | Create Delta Sync index with managed embeddings |
| `sync_vs_index` | Trigger index sync |
| `get_vs_index` | Check index status |
| `query_vs_index` | Test similarity search |

---

## Step 1: Prepare Source Table

The source Delta table needs a primary key column and a text column to embed.

```sql
CREATE TABLE IF NOT EXISTS catalog.schema.knowledge_base (
    doc_id STRING,
    title STRING,
    content STRING,
    category STRING,
    updated_at TIMESTAMP DEFAULT current_timestamp()
);

INSERT INTO catalog.schema.knowledge_base VALUES
('doc-001', 'Getting Started', 'Databricks is a unified analytics platform...', 'overview', current_timestamp()),
('doc-002', 'Unity Catalog', 'Unity Catalog provides centralized governance...', 'governance', current_timestamp()),
('doc-003', 'Delta Lake', 'Delta Lake is an open-source storage layer...', 'storage', current_timestamp());
```

Or via MCP:

```python
execute_sql(sql_query="""
    CREATE TABLE IF NOT EXISTS catalog.schema.knowledge_base (
        doc_id STRING,
        title STRING,
        content STRING,
        category STRING,
        updated_at TIMESTAMP DEFAULT current_timestamp()
    )
""")
```

## Step 2: Create Vector Search Endpoint

```python
create_vs_endpoint(
    name="my-rag-endpoint",
    endpoint_type="STORAGE_OPTIMIZED"
)
```

Endpoint creation is asynchronous. Check status:

```python
get_vs_endpoint(name="my-rag-endpoint")
# Wait for state: "ONLINE"
```

## Step 3: Create Delta Sync Index

```python
create_vs_index(
    name="catalog.schema.knowledge_base_index",
    endpoint_name="my-rag-endpoint",
    primary_key="doc_id",
    index_type="DELTA_SYNC",
    delta_sync_index_spec={
        "source_table": "catalog.schema.knowledge_base",
        "embedding_source_columns": [
            {
                "name": "content",
                "embedding_model_endpoint_name": "databricks-gte-large-en"
            }
        ],
        "pipeline_type": "TRIGGERED",
        "columns_to_sync": ["doc_id", "title", "content", "category"]
    }
)
```

Key decisions:
- **`embedding_source_columns`**: Databricks computes embeddings automatically from the `content` column
- **`pipeline_type`**: `TRIGGERED` for manual sync (cheaper), `CONTINUOUS` for auto-sync on table changes
- **`columns_to_sync`**: Only sync columns you need in query results (reduces storage and improves performance)

## Step 4: Sync and Verify

```python
# Trigger initial sync
sync_vs_index(index_name="catalog.schema.knowledge_base_index")

# Check status
get_vs_index(index_name="catalog.schema.knowledge_base_index")
# Wait for state: "ONLINE"
```

## Step 5: Query the Index

```python
# Semantic search
query_vs_index(
    index_name="catalog.schema.knowledge_base_index",
    columns=["doc_id", "title", "content", "category"],
    query_text="How do I govern my data?",
    num_results=3
)
```

### With Filters

The filter syntax depends on the endpoint type used when creating the index.

```python
# Storage-Optimized endpoint (used in this walkthrough): SQL-like filter_string
query_vs_index(
    index_name="catalog.schema.knowledge_base_index",
    columns=["doc_id", "title", "content"],
    query_text="How do I govern my data?",
    num_results=3,
    filter_string="category = 'governance'"
)

# Standard endpoint (if you created a Standard endpoint instead): JSON filters_json
query_vs_index(
    index_name="catalog.schema.my_standard_index",
    columns=["doc_id", "title", "content"],
    query_text="How do I govern my data?",
    num_results=3,
    filters_json='{"category": "governance"}'
)
```

### Hybrid Search (Vector + Keyword)

```python
query_vs_index(
    index_name="catalog.schema.knowledge_base_index",
    columns=["doc_id", "title", "content"],
    query_text="Delta Lake ACID transactions",
    num_results=5,
    query_type="HYBRID"
)
```

---

## Step 6: Use in an Agent

### As a Tool in a ChatAgent

Use `VectorSearchRetrieverTool` to wire the index into an agent deployed on Model Serving:

```python
from databricks.agents import ChatAgent
from databricks.agents.tools import VectorSearchRetrieverTool
from databricks.sdk import WorkspaceClient

# Define the retriever tool
retriever_tool = VectorSearchRetrieverTool(
    index_name="catalog.schema.knowledge_base_index",
    columns=["doc_id", "title", "content"],
    num_results=3,
)

class RAGAgent(ChatAgent):
    def __init__(self):
        self.w = WorkspaceClient()

    def predict(self, messages, context=None):
        query = messages[-1].content

        results = self.w.vector_search_indexes.query_index(
            index_name="catalog.schema.knowledge_base_index",
            columns=["title", "content"],
            query_text=query,
            num_results=3,
        )

        context_docs = "\n\n".join(
            f"**{row[0]}**: {row[1]}"
            for row in results.result.data_array
        )

        response = self.w.serving_endpoints.query(
            name="databricks-meta-llama-3-3-70b-instruct",
            messages=[
                {"role": "system", "content": f"Answer using this context:\n{context_docs}"},
                {"role": "user", "content": query},
            ],
        )

        return {"content": response.choices[0].message.content}
```

---

## Updating the Index

### Add New Documents

```sql
INSERT INTO catalog.schema.knowledge_base VALUES
('doc-004', 'MLflow', 'MLflow is an open-source platform for ML lifecycle...', 'ml', current_timestamp());
```

Then sync:

```python
sync_vs_index(index_name="catalog.schema.knowledge_base_index")
```

### Delete Documents

```sql
DELETE FROM catalog.schema.knowledge_base WHERE doc_id = 'doc-001';
```

Then sync — the index automatically handles deletions via Delta change data feed.

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **Index stuck in PROVISIONING** | Endpoint may still be creating. Check `get_vs_endpoint` first |
| **Query returns no results** | Index may not be synced yet. Run `sync_vs_index` and wait for ONLINE state |
| **"Column not found in index"** | Column must be in `columns_to_sync`. Recreate index with the column included |
| **Embeddings not computed** | Ensure `embedding_model_endpoint_name` is a valid serving endpoint |
| **Stale results after table update** | For TRIGGERED pipelines, you must call `sync_vs_index` manually |
| **Filter not working** | Standard endpoints use `filters_json` (dict), Storage-Optimized use `filter_string` (SQL) |

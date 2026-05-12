# Vector Search Modes

Databricks Vector Search supports three search modes: **ANN** (semantic, default), **HYBRID** (semantic + keyword), and **FULL_TEXT** (keyword only, beta). ANN and HYBRID work with Delta Sync and Direct Access indexes.

## Semantic Search (ANN)

ANN (Approximate Nearest Neighbor) is the default search mode. It finds documents by vector similarity — matching the *meaning* of your query against stored embeddings.

### When to use

- Conceptual or meaning-based queries ("How do I handle errors in my pipeline?")
- Paraphrased input where exact terms may not appear in the documents
- Multilingual scenarios where query and document languages may differ
- General-purpose RAG retrieval

### Example

```python
# ANN is the default — no query_type parameter needed
results = w.vector_search_indexes.query_index(
    index_name="catalog.schema.my_index",
    columns=["id", "content"],
    query_text="How do I handle errors in my pipeline?",
    num_results=5
)
```

## Hybrid Search

Hybrid search combines vector similarity (ANN) with BM25 keyword scoring. It retrieves documents that are both semantically similar *and* contain matching keywords, then merges the results.

### When to use

- Queries containing exact terms that must appear: SKUs, product codes, error codes, acronyms
- Proper nouns — company names, people, specific technologies
- Technical documentation where terminology precision matters
- Mixed-intent queries combining concepts with specific terms

### Example

```python
results = w.vector_search_indexes.query_index(
    index_name="catalog.schema.my_index",
    columns=["id", "content"],
    query_text="SPARK-12345 executor memory error",
    query_type="HYBRID",
    num_results=10
)
```

## Decision Guide

| Mode | Best for | Trade-off | Choose when |
|------|----------|-----------|-------------|
| **ANN** (default) | Conceptual queries, paraphrases, meaning-based search | Fastest; may miss exact keyword matches | You want documents *about* a topic regardless of exact wording |
| **HYBRID** | Exact terms, codes, proper nouns, mixed-intent queries | ~2x resource usage vs ANN; max 200 results | Your queries contain specific identifiers or technical terms that must appear in results |
| **FULL_TEXT** (beta) | Pure keyword search without vector embeddings | No semantic understanding; max 200 results | You need keyword matching only, without vector similarity |

**Start with ANN.** Switch to HYBRID if you notice relevant documents being missed because they don't share vocabulary with the query.

## Combining Search Modes with Filters

Both search modes support filters. The filter syntax depends on your endpoint type:

- **Standard endpoints** → `filters` as dict (or `filters_json` as JSON string via `databricks-sdk`)
- **Storage-Optimized endpoints** → `filters` as SQL-like string (via `databricks-vectorsearch` package)

### Standard endpoint with hybrid search

```python
results = w.vector_search_indexes.query_index(
    index_name="catalog.schema.my_index",
    columns=["id", "content", "category"],
    query_text="SPARK-12345 executor memory error",
    query_type="HYBRID",
    num_results=10,
    filters_json='{"category": "troubleshooting", "status": ["open", "in_progress"]}'
)
```

### Storage-Optimized endpoint with hybrid search

```python
from databricks.vector_search.client import VectorSearchClient

vsc = VectorSearchClient()
index = vsc.get_index(endpoint_name="my-storage-endpoint", index_name="catalog.schema.my_index")

results = index.similarity_search(
    query_text="SPARK-12345 executor memory error",
    columns=["id", "content", "category"],
    query_type="hybrid",
    num_results=10,
    filters="category = 'troubleshooting' AND status IN ('open', 'in_progress')"
)
```

## Using with Pre-Computed Embeddings

If you compute embeddings yourself, use `query_vector` instead of `query_text` for ANN search:

```python
# ANN with pre-computed embedding (default)
results = w.vector_search_indexes.query_index(
    index_name="catalog.schema.my_index",
    columns=["id", "content"],
    query_vector=[0.1, 0.2, 0.3, ...],  # Your embedding vector
    num_results=10
)
```

For **hybrid search with self-managed embeddings** (indexes without an associated model endpoint), you must provide **both** `query_vector` and `query_text`. The vector is used for the ANN component and the text for the BM25 keyword component:

```python
# HYBRID with self-managed embeddings — requires both vector AND text
results = w.vector_search_indexes.query_index(
    index_name="catalog.schema.my_index",
    columns=["id", "content"],
    query_vector=[0.1, 0.2, 0.3, ...],  # For ANN similarity
    query_text="executor memory error",   # For BM25 keyword matching
    query_type="HYBRID",
    num_results=10
)
```

**Notes:**
- For **ANN** queries: provide either `query_text` or `query_vector`, not both.
- For **HYBRID** queries on **managed embedding indexes**: provide only `query_text` (the system handles both components).
- For **HYBRID** queries on **self-managed indexes without a model endpoint**: provide both `query_vector` and `query_text`.
- When using `query_text` alone, the index must have an associated embedding model (managed embeddings or `embedding_model_endpoint_name` on a Direct Access index).

## Parameter Reference

| Parameter | Type | Package | Description |
|-----------|------|---------|-------------|
| `query_text` | `str` | Both | Text query — requires embedding model on the index |
| `query_vector` | `list[float]` | Both | Pre-computed embedding vector |
| `query_type` | `str` | Both | `"ANN"` (default) or `"HYBRID"` or `"FULL_TEXT"` (beta) |
| `columns` | `list[str]` | Both | Column names to return in results |
| `num_results` | `int` | Both | Number of results (default: 10 in `databricks-sdk`, 5 in `databricks-vectorsearch`) |
| `filters_json` | `str` | `databricks-sdk` | JSON dict filter string (Standard endpoints) |
| `filters` | `str` or `dict` | `databricks-vectorsearch` | Dict for Standard, SQL-like string for Storage-Optimized |

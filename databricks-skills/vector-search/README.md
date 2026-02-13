# Databricks Vector Search

Patterns for Databricks Vector Search: create endpoints and indexes, query with filters, manage embeddings.

## Overview

This skill covers creating, managing, and querying vector search indexes for RAG and semantic search applications on Databricks. It activates when building retrieval-augmented generation pipelines, implementing similarity matching, or choosing between endpoint and index types. The skill details both standard and storage-optimized endpoints, all three index types (Delta Sync managed, Delta Sync self-managed, Direct Access), and filtering, hybrid search, and CLI operations.

## What's Included

```
vector-search/
├── SKILL.md          # Main skill reference: endpoints, indexes, queries, filtering, and CLI
└── index-types.md    # Detailed comparison of index types with creation patterns and decision tree
```

## Key Topics

- Standard vs. Storage-Optimized endpoints (latency, capacity, cost trade-offs)
- Delta Sync indexes with managed embeddings (easiest setup)
- Delta Sync indexes with self-managed (pre-computed) embeddings
- Direct Access indexes for real-time CRUD operations
- Querying with `query_text`, `query_vector`, and hybrid search
- Filtering: dictionary-style (`filters_json`) and SQL-like (`filter_string`)
- Built-in Databricks embedding models (`databricks-gte-large-en`, `databricks-bge-large-en`)
- Triggered vs. continuous pipeline sync
- Index scanning and manual sync operations
- Databricks CLI quick reference for endpoint and index management

## When to Use

- You are building a RAG application and need a vector index
- You need to choose between Standard and Storage-Optimized endpoints
- You are creating a Delta Sync or Direct Access index from a Delta table
- You need to query a vector index with text, vectors, or hybrid search
- You want to apply metadata filters to narrow search results
- You are integrating Vector Search as a retriever tool in an agent

## Related Skills

- [Model Serving](../model-serving/) -- Deploy agents that use VectorSearchRetrieverTool
- [Agent Bricks](../databricks-agent-bricks/) -- Knowledge Assistants use RAG over indexed documents
- [Unstructured PDF Generation](../unstructured-pdf-generation/) -- Generate documents to index in Vector Search
- [Databricks Unity Catalog](../databricks-unity-catalog/) -- Manage the catalogs and tables that back Delta Sync indexes
- [Spark Declarative Pipelines](../spark-declarative-pipelines/) -- Build Delta tables used as Vector Search sources

## Resources

- [Databricks Vector Search Documentation](https://docs.databricks.com/generative-ai/vector-search.html)
- [Vector Search Python SDK Reference](https://docs.databricks.com/dev-tools/sdk-python/vector-search.html)

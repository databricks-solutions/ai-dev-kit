---
name: vector-search-similarity
description: Understand and work with Databricks Vector Search similarity scores. Use when interpreting similarity results, normalizing embeddings, or troubleshooting unexpected ranking behavior in vector search applications.
author: Databricksters Community
source_url: https://www.databricksters.com/p/databricks-vector-search-similarity
source_site: databricksters.com
---

# Databricks Vector Search Similarity Scores

## Overview

Understanding similarity scores in Databricks Vector Search is critical for building effective RAG applications and semantic search. Unlike cosine similarity, Databricks uses a transformed Euclidean distance metric that can produce unexpected results if not properly understood.

**Key Insight:** When vectors are properly normalized, Databricks similarity scores maintain the same **rank order** as cosine similarity, even though the actual values differ.

## The Problem: Unexpected Scores

If you're coming from a cosine similarity background, Databricks Vector Search scores might seem puzzling:

```python
# Cosine similarity: range [-1, 1]
# Databricks score: range (0, 1]
# Same vectors, different numerical values!
```

### Score Comparison Example

```python
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

# Two vectors
vec_a = np.array([1.0, 0.0])
vec_b = np.array([0.0, 1.0])

# Cosine similarity
cos_sim = cosine_similarity(vec_a.reshape(1, -1), vec_b.reshape(1, -1))[0][0]
print(f"Cosine similarity: {cos_sim}")  # 0.0 (orthogonal)

# Databricks similarity (L2-based)
# Formula: 1 / (1 + distance²)
import numpy.linalg as la
distance = la.norm(vec_a - vec_b)
db_sim = 1 / (1 + distance ** 2)
print(f"Databricks similarity: {db_sim}")  # 0.33
```

**Both correctly identify the vectors as dissimilar, but with different numerical values.**

## How Databricks Calculates Similarity

### The Formula

Databricks Vector Search uses:

```
similarity = 1 / (1 + distance²)
```

Where `distance` is the Euclidean (L2) distance between vectors.

### Comparison of Metrics

| Aspect | Cosine Similarity | Databricks Score |
|--------|-------------------|------------------|
| **Based on** | Angle between vectors | Transformed L2 distance |
| **Range** | [-1, 1] | (0, 1] |
| **Perfect match** | 1.0 | 1.0 |
| **Orthogonal** | 0.0 | 0.5 (for unit vectors) |
| **Opposite** | -1.0 | ~0.0 |
| **Normalization required** | No (inherent) | Yes (for cosine-like behavior) |

### Why the Difference Matters

**Cosine Similarity** measures alignment (direction only):
- Two vectors pointing the same direction = 1.0
- Independent of vector magnitude

**Databricks Score** measures position (magnitude matters):
- Two vectors at the same point = 1.0
- Sensitive to both direction AND magnitude

## Vector Normalization

Normalization rescales vectors to unit length (L2 norm = 1), making the Databricks score depend only on direction.

### Python Implementation

```python
import numpy as np
from sklearn.preprocessing import normalize

def normalize_vectors(vectors):
    """
    L2 normalize vectors to unit length.
    
    Args:
        vectors: numpy array of shape (n_samples, n_features)
    
    Returns:
        Normalized vectors with unit L2 norm
    """
    return normalize(vectors, norm='l2', axis=1)

# Example
raw_vectors = np.array([
    [3.0, 4.0],  # Magnitude = 5
    [6.0, 8.0],  # Magnitude = 10, same direction
])

normalized = normalize_vectors(raw_vectors)
print(f"Before: {raw_vectors}")
print(f"After: {normalized}")
# After: [[0.6, 0.8], [0.6, 0.8]] - Same unit vectors!
```

### Model-Specific Notes

| Embedding Model | Normalized by Default? | Action Required |
|-----------------|------------------------|-----------------|
| **BGE (BAAI)** | Yes | None |
| **GTE (Databricks)** | No | Normalize before indexing |
| **OpenAI** | Yes | None |
| **Other external** | Varies | Check model documentation |

### Normalization in Databricks

```python
from pyspark.sql import functions as F
from pyspark.ml.feature import Normalizer

# Normalize embeddings before indexing
df_with_normalized = df.withColumn(
    "embedding_normalized",
    F.expr("normalize(embedding, 'L2')")
)

# Write to Delta table for Vector Search indexing
df_with_normalized.write \
    .mode("overwrite") \
    .saveAsTable("catalog.schema.normalized_documents")
```

## Rank-Order Equivalence

When vectors are normalized, the **ranking** from Databricks scores matches cosine similarity, even though values differ.

### Proof by Example

```python
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import normalize

def databricks_score(q, x):
    """Calculate Databricks similarity score."""
    distance = np.linalg.norm(q - x)
    return 1 / (1 + distance ** 2)

# Query vector
query = np.array([0.2, 0.8])

# Candidate vectors
candidates = {
    "a": np.array([1.0, 0.0]),
    "b": np.array([0.0, 1.0]),
    "c": np.array([1.0, 1.0]),
}

# --- NON-NORMALIZED (Problematic) ---
print("=== Non-Normalized Vectors ===")
cosine_scores = {k: cosine_similarity(query.reshape(1,-1), v.reshape(1,-1))[0][0] 
                 for k, v in candidates.items()}
db_scores = {k: databricks_score(query, v) for k, v in candidates.items()}

cosine_ranking = sorted(cosine_scores.items(), key=lambda x: x[1], reverse=True)
db_ranking = sorted(db_scores.items(), key=lambda x: x[1], reverse=True)

print(f"Cosine ranking: {[k for k, _ in cosine_ranking]}")
print(f"Databricks ranking: {[k for k, _ in db_ranking]}")
# Rankings may differ!

# --- NORMALIZED (Correct) ---
print("\n=== Normalized Vectors ===")
query_norm = normalize(query.reshape(1, -1))[0]
candidates_norm = {k: normalize(v.reshape(1, -1))[0] for k, v in candidates.items()}

cosine_scores_norm = {k: cosine_similarity(query_norm.reshape(1,-1), v.reshape(1,-1))[0][0] 
                      for k, v in candidates_norm.items()}
db_scores_norm = {k: databricks_score(query_norm, v) for k, v in candidates_norm.items()}

cosine_ranking_norm = sorted(cosine_scores_norm.items(), key=lambda x: x[1], reverse=True)
db_ranking_norm = sorted(db_scores_norm.items(), key=lambda x: x[1], reverse=True)

print(f"Cosine ranking: {[k for k, _ in cosine_ranking_norm]}")
print(f"Databricks ranking: {[k for k, _ in db_ranking_norm]}")
# Rankings now match!
```

## Working with Vector Search

### Creating Normalized Index

```python
from databricks.vector_search.client import VectorSearchClient

client = VectorSearchClient()

# Create index with normalized embeddings
client.create_delta_sync_index(
    endpoint_name="your-endpoint",
    index_name="catalog.schema.docs_index",
    source_table_name="catalog.schema.normalized_documents",
    primary_key="id",
    embedding_source_column="embedding_normalized",  # Use normalized column
    embedding_model_endpoint_name="databricks-gte-large-en"
)
```

### Querying with Normalization

```python
# Query must also be normalized!
from sklearn.preprocessing import normalize

# Get embedding from model
query_embedding = get_embedding("your query text")

# Normalize query (same as index time)
query_normalized = normalize([query_embedding], norm='l2')[0]

# Search
results = client.similarity_search(
    endpoint_name="your-endpoint",
    index_name="catalog.schema.docs_index",
    query_vector=query_normalized.tolist(),
    num_results=5
)
```

### Interpreting Results

```python
# Typical similarity score ranges (normalized vectors)
SCORE_THRESHOLDS = {
    "very_similar": 0.9,      # > 0.9: Highly relevant
    "similar": 0.7,           # > 0.7: Relevant
    "somewhat_similar": 0.5,  # > 0.5: Possibly relevant
    "not_similar": 0.0        # < 0.5: Likely not relevant
}

def interpret_score(score):
    """Interpret similarity score for RAG applications."""
    if score > 0.9:
        return "HIGH", "Very relevant"
    elif score > 0.7:
        return "MEDIUM", "Relevant"
    elif score > 0.5:
        return "LOW", "Possibly relevant"
    else:
        return "NONE", "Not relevant"
```

## Hybrid Search Considerations

When using `query_type='HYBRID'`, Databricks uses Reciprocal Rank Fusion (RRF) to combine vector and keyword search:

```python
results = client.similarity_search(
    endpoint_name="your-endpoint",
    index_name="catalog.schema.docs_index",
    query_text="machine learning",  # Text query for hybrid
    query_type="HYBRID",
    num_results=10
)

# Score is RRF-combined, not pure vector similarity
```

## Best Practices

1. **Always normalize GTE embeddings** before indexing
2. **Normalize queries at search time** using same method
3. **Use score thresholds** appropriate for your use case
4. **Test ranking behavior** with known similar/dissimilar documents
5. **Monitor for score drift** if embedding model changes

## Troubleshooting

### Issue: Unexpected ranking

**Symptoms:** Documents that should be similar have low scores

**Causes:**
- Vectors not normalized
- Query not normalized
- Using wrong embedding model

**Fix:**
```python
# Verify normalization
import numpy.linalg as la

embedding = get_embedding("test")
norm = la.norm(embedding)
print(f"Norm: {norm}")  # Should be ~1.0 for normalized vectors

# If not normalized, normalize it
if not (0.99 < norm < 1.01):
    embedding = embedding / norm
```

### Issue: Score thresholds don't work

**Solution:** Calibrate thresholds for your specific embedding model:

```python
# Test with known relevant/irrelevant documents
test_queries = [
    ("relevant query", ["known_relevant_doc_id"]),
    ("irrelevant query", ["known_irrelevant_doc_id"]),
]

for query, expected_ids in test_queries:
    results = search(query)
    for result in results:
        print(f"Query: {query}, Doc: {result.id}, Score: {result.score}")
```

## Attribution

This skill is based on **Databricks Vector Search Similarity Scores Deep Dive** from the Databricksters blog.

## Related Resources

- [Databricks Vector Search Documentation](https://docs.databricks.com/aws/en/generative-ai/vector-search)
- [Vector Search Index Creation](https://docs.databricks.com/aws/en/generative-ai/vector-search/create-index)
- [Reciprocal Rank Fusion Paper](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf)

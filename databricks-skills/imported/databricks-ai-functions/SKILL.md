---
name: databricks-ai-functions
description: "Use Databricks built-in AI Functions (ai_classify, ai_extract, ai_summarize, ai_mask, ai_translate, ai_fix_grammar, ai_gen, ai_analyze_sentiment, ai_similarity, ai_parse_document, ai_query, ai_forecast) to add AI capabilities directly to SQL and PySpark pipelines without managing model endpoints. Also covers document parsing and building custom RAG pipelines (parse → chunk → index → query)."
---

# Databricks AI Functions

> **Official Docs:** https://docs.databricks.com/aws/en/large-language-models/ai-functions
> Individual function reference: https://docs.databricks.com/aws/en/sql/language-manual/functions/

## Overview

Databricks AI Functions are built-in SQL and PySpark functions that call Foundation Model APIs directly from your data pipelines — no model endpoint setup, no API keys, no boilerplate. They operate on table columns as naturally as `UPPER()` or `LENGTH()`, and are optimized for batch inference at scale.

There are three categories:

| Category | Functions | Use when |
|---|---|---|
| **Task-specific** | `ai_analyze_sentiment`, `ai_classify`, `ai_extract`, `ai_fix_grammar`, `ai_gen`, `ai_mask`, `ai_similarity`, `ai_summarize`, `ai_translate`, `ai_parse_document` | The task is well-defined — prefer these always |
| **General-purpose** | `ai_query` | Complex nested JSON, custom endpoints, multimodal — **last resort only** |
| **Table-valued** | `ai_forecast` | Time series forecasting |

**Function selection rule — always prefer a task-specific function over `ai_query`:**

| Task | Use this | Fall back to `ai_query` when... |
|---|---|---|
| Sentiment scoring | `ai_analyze_sentiment` | Never |
| Fixed-label routing | `ai_classify` (2–500 labels; add descriptions for accuracy) | Never |
| Entity / field extraction | `ai_extract` | Never |
| Summarization | `ai_summarize` | Never — use `max_words=0` for uncapped |
| Grammar correction | `ai_fix_grammar` | Never |
| Translation | `ai_translate` | Target language not in the supported list |
| PII redaction | `ai_mask` | Never |
| Free-form generation | `ai_gen` | Need structured JSON output |
| Semantic similarity | `ai_similarity` | Never |
| PDF / document parsing | `ai_parse_document` | Need image-level reasoning |
| Complex JSON / reasoning | — | **This is the intended use case for `ai_query`** |

## Prerequisites

- Databricks SQL warehouse (**not Classic**) or cluster with DBR **15.1+**
- DBR **15.4 ML LTS** recommended for batch workloads
- DBR **17.1+** required for `ai_parse_document`
- `ai_forecast` requires a **Pro or Serverless** SQL warehouse
- Workspace in a supported AWS/Azure region for batch AI inference
- Models run under Apache 2.0 or LLAMA 3.3 Community License — customers are responsible for compliance

## Quick Start

Classify, extract, and score sentiment from a text column in a single query:

```sql
SELECT
    ticket_id,
    ticket_text,
    ai_classify(ticket_text, ARRAY('urgent', 'not urgent', 'spam')) AS priority,
    ai_extract(ticket_text, ARRAY('product', 'error_code', 'date'))  AS entities,
    ai_analyze_sentiment(ticket_text)                                 AS sentiment
FROM support_tickets;
```

```python
from pyspark.sql.functions import expr

df = spark.table("support_tickets")
df = (
    df.withColumn("priority",  expr("ai_classify(ticket_text, array('urgent', 'not urgent', 'spam'))"))
      .withColumn("entities",  expr("ai_extract(ticket_text, array('product', 'error_code', 'date'))"))
      .withColumn("sentiment", expr("ai_analyze_sentiment(ticket_text)"))
)
# Access nested STRUCT fields from ai_extract
df.select("ticket_id", "priority", "sentiment",
          "entities.product", "entities.error_code", "entities.date").display()
```

## Common Patterns

### Pattern 1: Text Analysis Pipeline

Chain multiple task-specific functions to enrich a text column in one pass:

```sql
SELECT
    id,
    content,
    ai_analyze_sentiment(content)               AS sentiment,
    ai_summarize(content, 30)                   AS summary,
    ai_classify(content,
        ARRAY('technical', 'billing', 'other')) AS category,
    ai_fix_grammar(content)                     AS content_clean
FROM raw_feedback;
```

### Pattern 2: PII Redaction Before Storage

```python
from pyspark.sql.functions import expr

df_clean = (
    spark.table("raw_messages")
    .withColumn(
        "message_safe",
        expr("ai_mask(message, array('person', 'email', 'phone', 'address'))")
    )
)
df_clean.write.format("delta").mode("append").saveAsTable("catalog.schema.messages_safe")
```

### Pattern 3: Document Ingestion from a Unity Catalog Volume

Parse PDFs/Office docs, then enrich with task-specific functions:

```python
from pyspark.sql.functions import expr

df = (
    spark.read.format("binaryFile")
    .load("/Volumes/catalog/schema/landing/documents/")
    .withColumn("parsed", expr("ai_parse_document(content)"))
    .selectExpr("path",
                "parsed:pages[*].elements[*].content AS text_blocks",
                "parsed:error AS parse_error")
    .filter("parse_error IS NULL")
    .withColumn("summary",  expr("ai_summarize(text_blocks, 50)"))
    .withColumn("entities", expr("ai_extract(text_blocks, array('date', 'amount', 'vendor'))"))
)
```

### Pattern 4: Semantic Matching / Deduplication

```sql
-- Find near-duplicate company names
SELECT a.id, b.id, ai_similarity(a.name, b.name) AS score
FROM companies a
JOIN companies b ON a.id < b.id
WHERE ai_similarity(a.name, b.name) > 0.85;
```

### Pattern 5: Complex JSON Extraction with `ai_query` (last resort)

Use only when the output schema has nested arrays or requires multi-step reasoning that no task-specific function handles:

```python
from pyspark.sql.functions import expr, from_json, col

df = (
    spark.table("parsed_documents")
    .withColumn("ai_response", expr("""
        ai_query(
            'databricks-claude-sonnet-4',
            concat('Extract invoice as JSON with nested itens array: ', text_blocks),
            responseFormat => '{"type":"json_object"}',
            failOnError     => false
        )
    """))
    .withColumn("invoice", from_json(
        col("ai_response.response"),
        "STRUCT<numero:STRING, total:DOUBLE, "
        "itens:ARRAY<STRUCT<codigo:STRING, descricao:STRING, qtde:DOUBLE, vlrUnit:DOUBLE>>>"
    ))
)
```

### Pattern 6: Time Series Forecasting

```sql
SELECT *
FROM ai_forecast(
    observed  => TABLE(SELECT date, sales FROM daily_sales),
    horizon   => '2026-12-31',
    time_col  => 'date',
    value_col => 'sales'
);
-- Returns: date, sales_forecast, sales_upper, sales_lower
```

## Reference Files

- [1-task-functions.md](1-task-functions.md) — Full syntax, parameters, SQL + PySpark examples for all 9 task-specific functions (`ai_analyze_sentiment`, `ai_classify`, `ai_extract`, `ai_fix_grammar`, `ai_gen`, `ai_mask`, `ai_similarity`, `ai_summarize`, `ai_translate`) and `ai_parse_document`
- [2-ai-query.md](2-ai-query.md) — `ai_query` complete reference: all parameters, structured output with `responseFormat`, multimodal `files =>`, UDF patterns, and error handling
- [3-ai-forecast.md](3-ai-forecast.md) — `ai_forecast` parameters, single-metric, multi-group, multi-metric, and confidence interval patterns
- [4-document-processing-pipeline.md](4-document-processing-pipeline.md) — End-to-end batch document processing pipeline using AI Functions in a Lakeflow Declarative Pipeline; includes `config.yml` centralization, function selection logic, custom RAG pipeline (parse → chunk → Vector Search), and DSPy/LangChain guidance for near-real-time variants

## Common Issues

| Issue | Solution |
|---|---|
| `ai_parse_document` not found | Requires DBR **17.1+**. Check cluster runtime. |
| `ai_forecast` fails | Requires **Pro or Serverless** SQL warehouse — not available on Classic or Starter. |
| All functions return NULL | Input column is NULL. Filter with `WHERE col IS NOT NULL` before calling. |
| `ai_translate` fails for a language | Supported: English, German, French, Italian, Portuguese, Hindi, Spanish, Thai. Use `ai_query` with a multilingual model for others. |
| `ai_classify` returns unexpected labels | Use clear, mutually exclusive label names. Fewer labels (2–5) produces more reliable results. |
| `ai_query` raises on some rows in a batch job | Add `failOnError => false` — returns a STRUCT with `.response` and `.error` instead of raising. |
| Batch job runs slowly | Use DBR **15.4 ML LTS** cluster (not serverless or interactive) for optimized batch inference throughput. |
| Want to swap models without editing pipeline code | Store all model names and prompts in `config.yml` — see [4-document-processing-pipeline.md](4-document-processing-pipeline.md) for the pattern. |

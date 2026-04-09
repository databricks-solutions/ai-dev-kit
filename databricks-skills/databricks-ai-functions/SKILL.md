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
| Fixed-label routing | `ai_classify` (2–500 labels, multi-label supported) | Need custom model control |
| Structured extraction (flat or nested) | `ai_extract` (JSON schema, up to 7 levels) | >128 fields, >7 nesting levels, or custom model/multimodal |
| Summarization | `ai_summarize` | Never — use `max_words=0` for uncapped |
| Grammar correction | `ai_fix_grammar` | Never |
| Translation | `ai_translate` | Target language not in the supported list |
| PII redaction | `ai_mask` | Never |
| Free-form generation | `ai_gen` | Need structured JSON output |
| Semantic similarity | `ai_similarity` | Never |
| PDF / document parsing | `ai_parse_document` | Need image-level reasoning |
| Extreme complexity / custom model / multimodal | — | **>128 fields, >7 levels, custom endpoints, or image input — use `ai_query`** |

## Prerequisites

- Databricks SQL warehouse (**not Classic**) or cluster with DBR **15.1+**
- DBR **15.4 ML LTS** recommended for batch workloads
- DBR **17.1+** required for `ai_parse_document`
- `ai_forecast` requires a **Pro or Serverless** SQL warehouse
- Workspace in a supported AWS/Azure region for batch AI inference
- Models run under Apache 2.0 or LLAMA 3.3 Community License — customers are responsible for compliance

## Quick Start

Classify, extract, and score sentiment from a text column in a single query (v2 syntax):

```sql
SELECT
    ticket_id,
    ticket_text,
    ai_classify(ticket_text, '["urgent", "not urgent", "spam"]'):response[0]  AS priority,
    ai_extract(ticket_text, '["product", "error_code", "date"]'):response     AS entities,
    ai_analyze_sentiment(ticket_text)                                          AS sentiment
FROM support_tickets;
```

> **V2 returns VARIANT** — access fields with `:response.field` (SQL) or `["response"]["field"]` (Python). V1 syntax (`ARRAY(...)` argument) still works but returns STRUCT with dot notation.

```python
from pyspark.sql.functions import expr

df = spark.table("support_tickets")
df = (
    df.withColumn("priority",  expr("ai_classify(ticket_text, '[\"urgent\", \"not urgent\", \"spam\"]'):response[0]"))
      .withColumn("entities",  expr("ai_extract(ticket_text, '[\"product\", \"error_code\", \"date\"]')"))
      .withColumn("sentiment", expr("ai_analyze_sentiment(ticket_text)"))
)
# Access VARIANT fields from ai_extract v2
df.select("ticket_id", "priority", "sentiment",
          "entities:response.product", "entities:response.error_code", "entities:response.date").display()
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
        '["technical", "billing", "other"]'):response[0] AS category,
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
    .withColumn("entities", expr("ai_extract(text_blocks, '[\"date\", \"amount\", \"vendor\"]')"))
)
```

### Pattern 3b: V2 Composable Chaining — VARIANT Flows Directly Between Functions

V2 `ai_classify` and `ai_extract` accept VARIANT input, so the output of `ai_parse_document` can flow directly into them without extracting text first. This avoids the intermediate `selectExpr` step and lets the functions operate on the full document structure:

```python
from pyspark.sql.functions import expr

df = (
    spark.read.format("binaryFile")
    .load("/Volumes/catalog/schema/landing/documents/")
    # Stage 1: parse — returns VARIANT
    .withColumn("parsed", expr("ai_parse_document(content)"))
    # Stage 2: classify — accepts VARIANT directly from ai_parse_document
    .withColumn("doc_type", expr("""
        ai_classify(parsed, '["invoice", "contract", "report", "other"]'):response[0]
    """))
    # Stage 3: extract — accepts VARIANT directly from ai_parse_document
    .withColumn("entities", expr("""
        ai_extract(parsed, '{
            "type": "object",
            "properties": {
                "date": {"type": "string"},
                "amount": {"type": "number"},
                "vendor": {"type": "string"}
            }
        }')
    """))
    .select(
        "path",
        "doc_type",
        "entities:response.date",
        "entities:response.amount",
        "entities:response.vendor",
    )
)
```

> This chaining pattern is only possible with v2 syntax. V1 `ai_classify` and `ai_extract` require STRING input and cannot accept the VARIANT output from `ai_parse_document`.

### Pattern 4: Semantic Matching / Deduplication

```sql
-- Find near-duplicate company names
SELECT a.id, b.id, ai_similarity(a.name, b.name) AS score
FROM companies a
JOIN companies b ON a.id < b.id
WHERE ai_similarity(a.name, b.name) > 0.85;
```

### Pattern 5: Complex JSON Extraction with `ai_query` (when `ai_extract` v2 limits are exceeded)

Use when extraction exceeds 128 fields or 7 nesting levels, requires a custom model endpoint, or involves multimodal input. For most nested extraction including line-item arrays, prefer `ai_extract` v2 with a JSON schema — see [1-task-functions.md](1-task-functions.md#ai_extract).

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
| `ai_classify` returns unexpected labels | Use clear, mutually exclusive label names. Fewer labels (2–5) is optimal for single-label. V2 supports up to 500 labels and label descriptions (`'{"label":"description"}'` format) for better disambiguation. |
| `ai_extract` v2 returns VARIANT, not STRUCT | V2 uses `:response.field` path notation. V1 `ARRAY(...)` syntax still returns STRUCT with dot notation. Use JSON string schema to get v2 behavior. |
| `ai_classify` v2 returns array in response | V2 returns `{"response": ["label"], ...}`. Access with `:response[0]` for single-label, or iterate `:response` for multi-label. |
| Need multi-label classification | Use `ai_classify` v2 with `map('multilabel', 'true')` in options. Returns all applicable labels in the response array. |
| `ai_query` raises on some rows in a batch job | Add `failOnError => false` — returns a STRUCT with `.response` and `.error` instead of raising. |
| Batch job runs slowly | Use DBR **15.4 ML LTS** cluster (not serverless or interactive) for optimized batch inference throughput. |
| Want to swap models without editing pipeline code | Store all model names and prompts in `config.yml` — see [4-document-processing-pipeline.md](4-document-processing-pipeline.md) for the pattern. |

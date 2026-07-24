---
name: databricks-ai-functions
description: "Use Databricks built-in AI Functions (ai_classify, ai_extract, ai_summarize, ai_mask, ai_translate, ai_fix_grammar, ai_gen, ai_analyze_sentiment, ai_similarity, ai_parse_document, ai_prep_search, ai_query, ai_forecast) to add AI capabilities directly to SQL and PySpark pipelines without managing model endpoints. Also covers document parsing and building custom RAG pipelines (parse → prep_search → index → query)."
---

# Databricks AI Functions

> **Official Docs:** https://docs.databricks.com/en/large-language-models/ai-functions
> Individual function reference: https://docs.databricks.com/en/sql/language-manual/functions/

## Overview

Databricks AI Functions are built-in SQL and PySpark functions that call Foundation Model APIs directly from your data pipelines — no model endpoint setup, no API keys, no boilerplate. They operate on table columns as naturally as `UPPER()` or `LENGTH()`, and are optimized for batch inference at scale.

**Always prefer a task-specific function over `ai_query`.** Reach for `ai_query` only when no task function fits (custom/external endpoints, multimodal, or JSON beyond `ai_extract`'s limits). Every function below shares a baseline: **DBR 15.1+** (notebooks) / **15.4 ML LTS** (batch), **not on SQL Warehouse Classic**, and region must support AI Functions — the Prereqs column lists only what's *additional*.

**Cost & speed — each call is an LLM inference (slow and billed per token).** Run a function **once** per row and persist the result to a Delta table; never re-invoke it on every downstream query. In demos, **avoid generating tables with millions of rows** — sample the input when needed so the demo runs quickly. Materialize once, then query the cheap Delta output.

The **Function** column links to the in-repo deep reference (full options, schemas, examples); **Docs** links to the official page.

| Function | Task | Input | Output | Extra prereqs | Docs |
|---|---|---|---|---|---|
| [`ai_analyze_sentiment`](1-task-functions.md#ai_analyze_sentiment) | Sentiment scoring | `content STRING` | `STRING` — `positive`/`negative`/`neutral`/`mixed`, or `NULL` | — | [↗](https://docs.databricks.com/en/sql/language-manual/functions/ai_analyze_sentiment) |
| [`ai_classify`](1-task-functions.md#ai_classify) | Fixed-label routing | `content STRING\|VARIANT`, `labels` (2–500), `[options MAP]` | `VARIANT` — `{response:[label], error_message}` | — | [↗](https://docs.databricks.com/en/sql/language-manual/functions/ai_classify) |
| [`ai_extract`](1-task-functions.md#ai_extract) | Entity / field extraction | `content STRING\|VARIANT`, `schema STRING` (JSON), `[options MAP]` | `VARIANT` — `{response:{…}, error_message, metadata}` | ≤128 fields, ≤7 nesting levels | [↗](https://docs.databricks.com/en/sql/language-manual/functions/ai_extract) |
| [`ai_fix_grammar`](1-task-functions.md#ai_fix_grammar) | Grammar correction | `content STRING` | `STRING` (corrected) | — | [↗](https://docs.databricks.com/en/sql/language-manual/functions/ai_fix_grammar) |
| [`ai_gen`](1-task-functions.md#ai_gen) | Free-form generation | `prompt STRING` | `STRING` | — | [↗](https://docs.databricks.com/en/sql/language-manual/functions/ai_gen) |
| [`ai_mask`](1-task-functions.md#ai_mask) | PII redaction | `content STRING`, `labels ARRAY<STRING>` | `STRING` (entities → `[MASKED]`) | — | [↗](https://docs.databricks.com/en/sql/language-manual/functions/ai_mask) |
| [`ai_similarity`](1-task-functions.md#ai_similarity) | Semantic similarity | `expr1 STRING`, `expr2 STRING` | `FLOAT` (0.0–1.0) | — | [↗](https://docs.databricks.com/en/sql/language-manual/functions/ai_similarity) |
| [`ai_summarize`](1-task-functions.md#ai_summarize) | Summarization | `content STRING`, `[max_words INT]` (0 = uncapped) | `STRING` | Public Preview; English-tuned | [↗](https://docs.databricks.com/en/sql/language-manual/functions/ai_summarize) |
| [`ai_translate`](1-task-functions.md#ai_translate) | Translation | `content STRING`, `to_lang STRING` | `STRING` | Langs: en, fr, de, hi, it, pt, es, th | [↗](https://docs.databricks.com/en/sql/language-manual/functions/ai_translate) |
| [`ai_parse_document`](1-task-functions.md#ai_parse_document) | Parse PDF / Office / images | `content BINARY`, `[Map('version','2.0', …)]` | `VARIANT` — pages, elements, error_status | **DBR 17.3+**; ≤500 pages / 100 MB | [↗](https://docs.databricks.com/en/sql/language-manual/functions/ai_parse_document) |
| [`ai_prep_search`](1-task-functions.md#ai_prep_search) | RAG chunking from parsed docs | `parsed VARIANT`, `[options MAP]` | `VARIANT` — `{document:{contents, pages, source_uri}, error_status}` | **DBR 18.2+** (serverless env v3+) | [↗](https://docs.databricks.com/en/sql/language-manual/functions/ai_prep_search) |
| [`ai_query`](2-ai-query.md) | Any serving endpoint (built-in foundation or custom), multimodal, complex JSON (**last resort**) | `endpoint STRING`, `request STRING\|STRUCT`, `[returnType]`, `[failOnError BOOL]`, `[modelParameters STRUCT]`, `[responseFormat STRING]`, `[files]` | Parsed response; with `failOnError => false` a `STRUCT{response, errorMessage}` | **Pro/Serverless** warehouse; `CAN QUERY` on endpoint | [↗](https://docs.databricks.com/en/sql/language-manual/functions/ai_query) |
| [`ai_forecast`](3-ai-forecast.md) | Time series forecasting (table-valued) | `observed TABLE`, `horizon`, `time_col`, `value_col`, `[group_col]`, `[prediction_interval_width]`, `[frequency]`, `[seed]`, `[parameters]` | Rows: time/group cols + per value `{v}_forecast`, `{v}_upper`, `{v}_lower` (DOUBLE) | **Pro/Serverless** warehouse; Public Preview | [↗](https://docs.databricks.com/en/sql/language-manual/functions/ai_forecast) |

Models run under Apache 2.0 or LLAMA 3.3 Community License — you are responsible for compliance.

## Patterns

**Chain task functions to enrich a column in one pass.** `ai_classify`/`ai_extract` return a VARIANT — read it with the colon operator (`:response`):

```sql
SELECT id,
  ai_analyze_sentiment(content)                                                   AS sentiment,
  ai_summarize(content, 30)                                                       AS summary,
  ai_classify(content, '["technical","billing","other"]', map('version','2.0')):response[0]::STRING AS category,
  ai_extract(content, '["product","error_code","date"]', map('version','2.0')):response:product::STRING AS product,
  ai_fix_grammar(content)                                                         AS content_clean
FROM raw_feedback;
```

In **PySpark**, call any of these inside `expr(...)`: `df.withColumn("category", expr("ai_classify(content, '[\"a\",\"b\"]', map('version','2.0')):response[0]::STRING"))` — and read VARIANT fields via `selectExpr("col:response:field::STRING AS field")`.

**PII redaction before storage** — `ai_mask(content, ARRAY(entity_types))` returns text with entities → `[MASKED]`.

```sql
SELECT ai_mask(message, array('person','email','phone','address')) AS message_safe FROM raw_messages;
```

**Semantic matching / dedup** — `ai_similarity` returns 0–1; self-join and threshold:

```sql
SELECT a.id, b.id, ai_similarity(a.name, b.name) AS score
FROM companies a JOIN companies b ON a.id < b.id
WHERE ai_similarity(a.name, b.name) > 0.85;
```

**Forecasting** — table-valued; one row per future period (+ per group). Full param/group/interval forms → [3-ai-forecast.md](3-ai-forecast.md):

```sql
SELECT * FROM ai_forecast(
    observed => TABLE(SELECT date, sales FROM daily_sales),
    horizon => '2026-12-31', time_col => 'date', value_col => 'sales');
-- Returns: date, sales_forecast, sales_upper, sales_lower
```

**Nested JSON via `ai_query`** (last resort — only past `ai_extract`'s limits) — parse the response with `from_json`. Model names, multimodal `files =>`, `modelParameters`, SQL UDF → [2-ai-query.md](2-ai-query.md):

```sql
SELECT from_json(
    ai_query('databricks-claude-sonnet-4',
        concat('Extract invoice as JSON with nested line_items array: ', text_blocks),
        responseFormat => '{"type":"json_object"}', failOnError => false).response,
    'STRUCT<numero:STRING, total:DOUBLE, line_items:ARRAY<STRUCT<code:STRING, qty:DOUBLE>>>'
) AS invoice
FROM parsed_documents;
```

Document parsing (`ai_parse_document`) and RAG chunking (`ai_prep_search`) get their own staged pipeline below.

## Document Processing Pipeline

Chain AI Functions stage-by-stage into Delta tables for batch document processing. The example is written as a **Spark Declarative Pipeline (SDP / Lakeflow / DLT)** — `CREATE OR REFRESH STREAMING TABLE` with `STREAM(...)` sources. To run the same logic standalone in a **notebook / SQL warehouse**, swap each `CREATE OR REFRESH STREAMING TABLE x AS` for `CREATE OR REPLACE TABLE x AS` and drop the `STREAM(...)` wrappers. In SDP Python it's `@dp.table` with `from pyspark import pipelines as dp`.

```sql
-- Stage 1 — parse binary docs (any type), filter parse errors
CREATE OR REFRESH STREAMING TABLE raw_parsed AS
SELECT path,
  concat_ws('\n', transform(parsed:document:elements, e -> e:content::STRING)) AS text_blocks,
  parsed:error_status AS parse_error
FROM (
  SELECT path, ai_parse_document(content, map('version','2.0')) AS parsed
  FROM STREAM read_files('/Volumes/my_catalog/doc_processing/landing/', format => 'binaryFile')
)
WHERE parsed:error_status IS NULL;

-- Stage 2 — classify document type (cheap, no endpoint selection)
CREATE OR REFRESH STREAMING TABLE classified_docs AS
SELECT *,
  ai_classify(text_blocks, '["invoice","purchase_order","receipt","contract","other"]', map('version','2.0')):response[0]::STRING AS doc_type
FROM STREAM raw_parsed;

-- Stage 3 — extract fields; ai_extract returns a VARIANT, read fields with `:`
CREATE OR REFRESH STREAMING TABLE extracted AS
SELECT path, doc_type,
  result:response:invoice_number::STRING AS invoice_number,
  result:response:vendor_name::STRING    AS vendor_name,
  result:response:total_amount::DOUBLE   AS total_amount,
  result:error_message::STRING           AS extract_error
FROM (
  SELECT *, ai_extract(text_blocks,
    '{"invoice_number":{"type":"string"},"vendor_name":{"type":"string"},"total_amount":{"type":"number"}}',
    map('version','2.0')) AS result
  FROM STREAM classified_docs WHERE doc_type = 'invoice' AND text_blocks IS NOT NULL
);
```

In a batch job, route the per-row error to a sidecar table instead of letting it crash the run: keep `ai_extract`'s `result:error_message` (VARIANT, colon-accessed, as above), and for `ai_query` pass `failOnError => false` and check `ai_response.errorMessage` (a STRUCT field, dot-accessed). See [2-ai-query.md](2-ai-query.md).

### Custom RAG Pipeline — Parse → Prep → Index

For retrieval rather than field extraction: `ai_parse_document` → `ai_prep_search` (semantic chunking + context enrichment, DBR 18.2+) → Vector Search Delta Sync index. `ai_prep_search` returns `chunk_id`, `chunk_to_retrieve`, and `chunk_to_embed` (enriched with title/headers/page) — **embed `chunk_to_embed`, return `chunk_to_retrieve` to the LLM.** Shown standalone; in an SDP swap `CREATE OR REPLACE TABLE` for `CREATE OR REFRESH STREAMING TABLE` + `STREAM read_files(...)`.

```sql
CREATE OR REPLACE TABLE parsed_chunks AS
WITH prepped AS (
  SELECT path AS source_path, ai_prep_search(ai_parse_document(content)) AS prep
  FROM read_files('/Volumes/my_catalog/doc_processing/docs/', format => 'binaryFile')
)
SELECT
  variant_get(chunk, '$.chunk_id',          'STRING') AS chunk_id,
  variant_get(chunk, '$.chunk_to_retrieve', 'STRING') AS chunk_to_retrieve,
  variant_get(chunk, '$.chunk_to_embed',    'STRING') AS chunk_to_embed,
  source_path
FROM prepped LATERAL VIEW explode(variant_get(prep, '$.chunks', 'ARRAY<VARIANT>')) c AS chunk;
```

Then enable CDF (`ALTER TABLE parsed_chunks SET TBLPROPERTIES (delta.enableChangeDataFeed = true)`) and use the **[databricks-vector-search](../databricks-vector-search/SKILL.md)** skill to build a Delta Sync index: PK `chunk_id`, embedding source `chunk_to_embed`, return `chunk_to_retrieve`.

**Beyond batch:**
- **Ask questions over the output** — point a Genie space at the resulting Delta table for natural-language querying instead of hand-written SQL; see the **[databricks-genie](../databricks-genie/SKILL.md)** skill.
- **Low-latency / serving** — to expose this as a real-time, governed endpoint (e.g. register a model to Unity Catalog and serve it), use the **[databricks-model-serving](../databricks-model-serving/SKILL.md)** skill.
- **Production incremental ingestion** — for a runnable end-to-end streaming `ai_parse_document` job (checkpoints, `trigger(availableNow=True)`), see [databricks/bundle-examples · job_with_ai_parse_document](https://github.com/databricks/bundle-examples/tree/main/contrib/job_with_ai_parse_document).

## Reference Files

- [1-task-functions.md](1-task-functions.md) — Deep reference for every task-specific function: full options/schemas (e.g. `ai_extract` v2.1 citations + confidence scores, `ai_classify` multilabel, `ai_parse_document` options + output schema, `ai_prep_search` chunk schema) and non-trivial examples. The Overview table above links to each function's section directly.
- [2-ai-query.md](2-ai-query.md) — `ai_query` complete reference: all parameters, structured output with `responseFormat`, multimodal `files =>`, UDF patterns, and error handling
- [3-ai-forecast.md](3-ai-forecast.md) — `ai_forecast` parameters, single-metric, multi-group, multi-metric, and confidence interval patterns

## Common Issues

| Issue | Solution |
|---|---|
| `ai_parse_document` not found | Requires DBR **17.3+**. Check cluster runtime. |
| `ai_prep_search` not found | Requires DBR **18.2+** (serverless env v3+). |
| `explode()` fails on a VARIANT | `explode` needs ARRAY — cast first: `explode(variant_get(prep, '$.chunks', 'ARRAY<VARIANT>'))`. |
| Embedding the wrong RAG column | Embed `chunk_to_embed` (context-enriched); return `chunk_to_retrieve` to the LLM. |
| `ai_forecast` fails | Requires **Pro or Serverless** SQL warehouse — not available on Classic or Starter. |
| All functions return NULL | Input column is NULL. Filter with `WHERE col IS NOT NULL` before calling. |
| `ai_translate` fails for a language | Supported: English, German, French, Italian, Portuguese, Hindi, Spanish, Thai. Use `ai_query` with a multilingual model for others. |
| `ai_classify` returns unexpected labels | Use clear, mutually exclusive label names. Fewer labels (2–5) produces more reliable results. |
| `ai_query` raises on some rows in a batch job | Add `failOnError => false` — returns a STRUCT with `.response` and `.errorMessage` (dot-accessed) instead of raising. |
| Batch job runs slowly | Use DBR **15.4 ML LTS** cluster (not serverless or interactive) for optimized batch inference throughput. |

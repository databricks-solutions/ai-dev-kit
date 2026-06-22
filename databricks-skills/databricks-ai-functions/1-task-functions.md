# Task-Specific AI Functions — Full Reference

These functions require no model endpoint selection. They call pre-configured Foundation Model APIs optimized for each task. All require DBR 15.1+ (15.4 ML LTS for batch); `ai_parse_document` requires DBR 17.3+; `ai_prep_search` requires DBR 18.2+ (serverless env v3+).

---

## `ai_analyze_sentiment`

**Docs:** https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_analyze_sentiment

Returns one of: `positive`, `negative`, `neutral`, `mixed`, or `NULL`.

```sql
SELECT ai_analyze_sentiment(review_text) AS sentiment
FROM customer_reviews;
```

```python
from pyspark.sql.functions import expr
df = spark.table("customer_reviews")
df.withColumn("sentiment", expr("ai_analyze_sentiment(review_text)")).display()
```

---

## `ai_classify`

**Docs:** https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_classify

**Syntax:** `ai_classify(content, labels [, options])`
- `content`: VARIANT | STRING — raw text, or VARIANT from `ai_parse_document` / `ai_extract`
- `labels`: STRING — JSON labels definition:
  - Simple array: `'["urgent", "not_urgent", "spam"]'`
  - With descriptions: `'{"billing_error": "Payment, invoice, or refund issues", "product_defect": "Any malfunction or bug"}'` (descriptions up to 1000 chars each)
  - 2–500 labels, each 1–100 characters
- `options`: optional MAP\<STRING, STRING\>:
  - `version`: `"2.0"` (recommended) or `"1.0"` for backward compatibility
  - `instructions`: task context to improve accuracy (max 20,000 chars)
  - `multilabel`: `"true"` to return multiple matching labels (default `"false"`)

Returns VARIANT `{"response": ["label", ...], "error_message": null}`. Returns `NULL` if content is `NULL`.

**Constraints:** total input + labels context capped at **128,000 tokens**; not available on Databricks SQL Classic.

```sql
-- simple labels
SELECT ticket_text,
       ai_classify(ticket_text, '["urgent", "not urgent", "spam"]') AS priority
FROM support_tickets;
-- {"response": ["urgent"], "error_message": null}

-- labels with descriptions
SELECT ticket_text,
       ai_classify(
           ticket_text,
           '{"billing_error": "Payment, invoice, or refund issues",
             "product_defect": "Any malfunction, bug, or breakage",
             "account_issue": "Login failures, password resets"}',
           MAP('instructions', 'Customer support tickets for a SaaS product')
       ) AS category
FROM support_tickets;
```

```python
from pyspark.sql.functions import expr
df = spark.table("support_tickets")
df.withColumn(
    "priority",
    expr("ai_classify(ticket_text, '[\"urgent\", \"not urgent\", \"spam\"]')")
).display()
```

**Tips:**
- Use label descriptions for ambiguous categories — they significantly improve accuracy
- `multilabel: "true"` enables multi-label classification without running multiple calls
- Up to 500 labels supported

---

## `ai_extract`

**Docs:** https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_extract

**Syntax:** `ai_extract(content, schema [, options])`
- `content`: VARIANT | STRING — raw text, or VARIANT from `ai_parse_document`
- `schema`: STRING — JSON schema definition:
  - Simple (field names only): `'["invoice_id", "vendor_name", "total_amount"]'`
  - Advanced (with types and descriptions):
    ```json
    {
      "invoice_id": {"type": "string"},
      "total_amount": {"type": "number"},
      "currency": {"type": "enum", "labels": ["USD", "EUR", "GBP"]},
      "line_items": {"type": "array", "items": {"type": "object", "properties": {...}}}
    }
    ```
  - Supported types: `string`, `integer`, `number`, `boolean`, `enum`, `object` (with `properties`), `array` (with `items`)
  - Max 128 fields, field names up to 150 chars, 7 nesting levels, 500 enum values, 128,000 token total context
- `options`: optional MAP\<STRING, STRING\>:
  - `version`: `"2.1"` (recommended) / `"2.0"` / `"1.0"`
  - `instructions`: task context to improve extraction quality (max 20,000 chars)
  - `enableCitations`: `"true"` to attach `citation_ids` to each extracted field
  - `enableConfidenceScores`: `"true"` to attach a per-field `confidence_score` (0–1)

Returns VARIANT `{"response": {...}, "error_message": null}`. With `enableCitations` or `enableConfidenceScores` enabled, each scalar field becomes an object `{"value": ..., "citation_ids": [...], "confidence_score": 0.x}` and a `metadata` block is added at the top level. Returns `NULL` if content is `NULL`.

```sql
-- simple schema
SELECT ai_extract(
    'Invoice #12345 from Acme Corp for $1,250.00',
    '["invoice_id", "vendor_name", "total_amount"]'
) AS extracted;
-- {"response": {"invoice_id": "12345", "vendor_name": "Acme Corp", ...}, "error_message": null}

-- composable with ai_parse_document
WITH parsed AS (
  SELECT ai_parse_document(content, MAP('version', '2.0')) AS parsed
  FROM READ_FILES('/Volumes/finance/invoices/', format => 'binaryFile')
)
SELECT ai_extract(
    parsed,
    '["invoice_id", "vendor_name", "total_amount"]',
    MAP('instructions', 'These are vendor invoices.')
) AS invoice_data
FROM parsed;
```

```python
from pyspark.sql.functions import expr
df = spark.table("messages")
df = df.withColumn(
    "entities",
    expr("ai_extract(message, '[\"person\", \"location\", \"date\"]')")
)
df.display()
```

### Version 2.1: citations and confidence scores

Pass `version => 2.1` with `enableCitations` and/or `enableConfidenceScores` to attach provenance and reliability metadata to each extracted field. Useful for review queues and downstream filtering by confidence.

```sql
SELECT ai_extract(
    document_text,
    '["invoice_id", "vendor_name", "total_amount"]',
    MAP(
        'version', '2.1',
        'enableCitations', 'true',
        'enableConfidenceScores', 'true'
    )
) AS extracted
FROM parsed_documents;

-- Each scalar field is now an object: {value, citation_ids, confidence_score}
-- Access:
SELECT
    extracted:response:invoice_id:value::STRING       AS invoice_id,
    extracted:response:invoice_id:confidence_score::DOUBLE AS invoice_id_conf,
    extracted:response:total_amount:value::DOUBLE     AS total_amount,
    extracted:metadata                                AS metadata
FROM extracted_invoices;
```

---

## `ai_fix_grammar`

**Docs:** https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_fix_grammar

**Syntax:** `ai_fix_grammar(content)` — Returns corrected STRING.

Optimized for English. Useful for cleaning user-generated content before downstream processing.

```sql
SELECT ai_fix_grammar(user_comment) AS corrected FROM user_feedback;
```

```python
from pyspark.sql.functions import expr
df = spark.table("user_feedback")
df.withColumn("corrected", expr("ai_fix_grammar(user_comment)")).display()
```

---

## `ai_gen`

**Docs:** https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_gen

**Syntax:** `ai_gen(prompt)` — Returns a generated STRING.

Use for free-form text generation where the output format doesn't need to be structured. For structured JSON output, use `ai_query` with `responseFormat`.

```sql
SELECT product_name,
       ai_gen(CONCAT('Write a one-sentence marketing tagline for: ', product_name)) AS tagline
FROM products;
```

```python
from pyspark.sql.functions import expr
df = spark.table("products")
df.withColumn(
    "tagline",
    expr("ai_gen(concat('Write a one-sentence marketing tagline for: ', product_name))")
).display()
```

---

## `ai_mask`

**Docs:** https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_mask

**Syntax:** `ai_mask(content, labels)`
- `content`: STRING — text with sensitive data
- `labels`: ARRAY\<STRING\> — entity types to redact

Returns text with identified entities replaced by `[MASKED]`.

Common label values: `'person'`, `'email'`, `'phone'`, `'address'`, `'ssn'`, `'credit_card'`

```sql
SELECT ai_mask(
    message_body,
    ARRAY('person', 'email', 'phone', 'address')
) AS message_safe
FROM customer_messages;
```

```python
from pyspark.sql.functions import expr
df = spark.table("customer_messages")
df.withColumn(
    "message_safe",
    expr("ai_mask(message_body, array('person', 'email', 'phone'))")
).write.format("delta").mode("append").saveAsTable("catalog.schema.messages_safe")
```

---

## `ai_similarity`

**Docs:** https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_similarity

**Syntax:** `ai_similarity(expr1, expr2)` — Returns a FLOAT between 0.0 and 1.0.

Use for fuzzy deduplication, search result ranking, or item matching across datasets.

```sql
-- Deduplicate company names (similarity > 0.85 = likely duplicate)
SELECT a.id, b.id, a.name, b.name,
       ai_similarity(a.name, b.name) AS score
FROM companies a
JOIN companies b ON a.id < b.id
WHERE ai_similarity(a.name, b.name) > 0.85
ORDER BY score DESC;
```

```python
from pyspark.sql.functions import expr
df = spark.table("product_search")
df.withColumn(
    "match_score",
    expr("ai_similarity(search_query, product_title)")
).orderBy("match_score", ascending=False).display()
```

---

## `ai_summarize`

**Docs:** https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_summarize

**Syntax:** `ai_summarize(content [, max_words])`
- `content`: STRING — text to summarize
- `max_words`: INTEGER (optional) — word limit; default 50; use `0` for uncapped

```sql
-- Default (50 words)
SELECT ai_summarize(article_body) AS summary FROM news_articles;

-- Custom word limit
SELECT ai_summarize(article_body, 20)  AS brief   FROM news_articles;
SELECT ai_summarize(article_body, 0)   AS full    FROM news_articles;
```

```python
from pyspark.sql.functions import expr
df = spark.table("news_articles")
df.withColumn("summary", expr("ai_summarize(article_body, 30)")).display()
```

---

## `ai_translate`

**Docs:** https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_translate

**Syntax:** `ai_translate(content, to_lang)`
- `content`: STRING — source text
- `to_lang`: STRING — target language code

**Supported languages:** `en`, `de`, `fr`, `it`, `pt`, `hi`, `es`, `th`

For unsupported languages, use `ai_query` with a multilingual model endpoint.

```sql
-- Single language
SELECT ai_translate(product_description, 'es') AS description_es FROM products;

-- Multi-language fanout
SELECT
    description,
    ai_translate(description, 'fr') AS description_fr,
    ai_translate(description, 'de') AS description_de
FROM products;
```

```python
from pyspark.sql.functions import expr
df = spark.table("products")
df.withColumn(
    "description_es",
    expr("ai_translate(product_description, 'es')")
).display()
```

---

## `ai_parse_document`

**Docs:** https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_parse_document

**Requires:** DBR 17.3+ (serverless env v3+ for VARIANT). Region-restricted — check feature availability.

**Syntax:** `ai_parse_document(content [, options])`
- `content`: BINARY — document content loaded from `read_files()` or `spark.read.format("binaryFile")`
- `options`: MAP\<STRING, STRING\> (optional) — parsing configuration

**Supported formats:** PDF, JPG/JPEG, PNG, TIFF/TIF, DOC/DOCX, PPT/PPTX

Returns a VARIANT with pages, elements (text, tables, figures, titles, captions, section headers, page headers/footers, page numbers, footnotes), bounding boxes, confidence scores, and error metadata.

**Options:**

| Key | Values | Description |
|-----|--------|-------------|
| `version` | `'2.0'` | Output schema version |
| `imageOutputPath` | Volume path | Save rendered page images to a UC Volume |
| `descriptionElementTypes` | `''`, `'figure'`, `'*'` | AI-generated descriptions (default: `'*'` for all). Set to `''` to disable and reduce cost. |
| `pageRange` | e.g. `'1,3,5-10'` | Restrict parsing to a subset of pages (1-indexed) |

**Output schema (v2.0):**

```
document
├── pages[]          -- id, image_uri
└── elements[]       -- extracted content
    ├── id           -- per-element id
    ├── type         -- text | table | figure | title | caption | section_header
    │                --   | page_header | page_footer | page_number | footnote
    ├── content      -- extracted text
    ├── confidence   -- DOUBLE 0–1
    ├── bbox         -- [{coord:[...], page_id}]
    └── description  -- AI-generated description (figures/tables when enabled)
metadata             -- id, version, file_metadata
error_status[]       -- {error_message, page_id} per page (if any)
```

**Limits:** max 500 pages per document, max 100 MB file size.

```sql
-- Parse and extract text blocks
SELECT
    path,
    parsed:pages[*].elements[*].content AS text_blocks,
    parsed:error AS parse_error
FROM (
    SELECT path, ai_parse_document(content) AS parsed
    FROM read_files('/Volumes/catalog/schema/landing/docs/', format => 'binaryFile')
);

-- Parse with options (image output + descriptions)
SELECT ai_parse_document(
    content,
    map(
        'version', '2.0',
        'imageOutputPath', '/Volumes/catalog/schema/volume/images/',
        'descriptionElementTypes', '*'
    )
) AS parsed
FROM read_files('/Volumes/catalog/schema/volume/invoices/', format => 'binaryFile');

-- Parse only specific pages (cheaper for large documents)
SELECT ai_parse_document(
    content,
    map('version', '2.0', 'pageRange', '1,3,5-10')
) AS parsed
FROM read_files('/Volumes/catalog/schema/volume/contracts/', format => 'binaryFile');
```

```python
from pyspark.sql.functions import expr

df = (
    spark.read.format("binaryFile")
    .load("/Volumes/catalog/schema/landing/docs/")
    .withColumn("parsed", expr("ai_parse_document(content)"))
    .selectExpr(
        "path",
        "parsed:pages[*].elements[*].content AS text_blocks",
        "parsed:error AS parse_error",
    )
    .filter("parse_error IS NULL")
)

# Chain with task-specific functions on the extracted text
df = (
    df.withColumn("summary",  expr("ai_summarize(text_blocks, 50)"))
      .withColumn("entities", expr("ai_extract(text_blocks, array('date', 'amount', 'vendor'))"))
      .withColumn("category", expr("ai_classify(text_blocks, array('invoice', 'contract', 'report'))"))
)
df.display()
```

**Limitations:**
- Max 500 pages per document, max 100 MB file size
- Processing is slow for dense or low-resolution documents
- Suboptimal for non-Latin alphabets (e.g., Japanese, Korean in images) and digitally signed PDFs
- Custom models not supported — always uses the built-in parsing model

---

## `ai_prep_search`

**Docs:** https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_prep_search

**Requires:** DBR **18.2+** (serverless env v3+ for VARIANT support).

Takes the VARIANT output of `ai_parse_document` and returns RAG-ready chunks. The function performs:
1. **Semantic chunking** — splits document content into retrieval-sized chunks at natural boundaries (paragraphs, sections, tables).
2. **Context enrichment** — adds document title, section headers, page numbers, and captions to each chunk's embedding text so Vector Search can match on context, not just chunk content.

Use this instead of hand-rolled `variant_get` + `explode` + `md5` chunking when feeding `ai_parse_document` output into Databricks Vector Search.

**Syntax:** `ai_prep_search(parsed [, options])`
- `parsed`: VARIANT — output from `ai_parse_document`
- `options`: optional MAP\<STRING, STRING\>:
  - `version`: output schema version (major.minor; minor upgrades are backward-compatible)

**Returns:** VARIANT with chunks ready for Vector Search:

```
chunks[]
├── chunk_id            -- unique id (document_id + position) — use as PK
├── chunk_position      -- ordinal within the document
├── chunk_to_retrieve   -- raw chunk text (return this to the LLM)
└── chunk_to_embed      -- context-enriched text (use this as the embedding source)
pages[]                 -- page index + image_uri (when imageOutputPath was set on ai_parse_document)
source_uri              -- input document path
error_status            -- per-page error info, if any
```

**End-to-end SQL — parse, prep, persist for Vector Search:**

```sql
CREATE OR REPLACE TABLE catalog.schema.parsed_chunks AS
WITH parsed AS (
  SELECT
    path AS source_path,
    ai_parse_document(content) AS parsed
  FROM read_files('/Volumes/catalog/schema/docs/', format => 'binaryFile')
),
prepped AS (
  SELECT
    source_path,
    ai_prep_search(parsed) AS prep
  FROM parsed
),
chunks AS (
  SELECT
    source_path,
    explode(variant_get(prep, '$.chunks', 'ARRAY<VARIANT>')) AS chunk
  FROM prepped
)
SELECT
  variant_get(chunk, '$.chunk_id',          'STRING') AS chunk_id,
  variant_get(chunk, '$.chunk_position',    'INT')    AS chunk_position,
  variant_get(chunk, '$.chunk_to_retrieve', 'STRING') AS chunk_to_retrieve,
  variant_get(chunk, '$.chunk_to_embed',    'STRING') AS chunk_to_embed,
  source_path,
  current_timestamp() AS prepped_at
FROM chunks;

-- Enable CDF so Vector Search Delta Sync picks up incremental changes
ALTER TABLE catalog.schema.parsed_chunks
SET TBLPROPERTIES (delta.enableChangeDataFeed = true);
```

**PySpark equivalent:**

```python
from pyspark.sql.functions import expr, current_timestamp

chunks_df = (
    spark.read.format("binaryFile")
    .load("/Volumes/catalog/schema/docs/")
    .withColumn("parsed", expr("ai_parse_document(content)"))
    .withColumn("prep",   expr("ai_prep_search(parsed)"))
    .withColumn("chunk",  expr("explode(variant_get(prep, '$.chunks', 'ARRAY<VARIANT>'))"))
    .selectExpr(
        "variant_get(chunk, '$.chunk_id',          'STRING') AS chunk_id",
        "variant_get(chunk, '$.chunk_position',    'INT')    AS chunk_position",
        "variant_get(chunk, '$.chunk_to_retrieve', 'STRING') AS chunk_to_retrieve",
        "variant_get(chunk, '$.chunk_to_embed',    'STRING') AS chunk_to_embed",
        "path AS source_path",
    )
    .withColumn("prepped_at", current_timestamp())
)

chunks_df.write.format("delta").mode("overwrite").saveAsTable("catalog.schema.parsed_chunks")
```

**Vector Search integration:** Point a Delta Sync index at this table with `chunk_to_embed` as the embedding source column and `chunk_id` as the primary key. The `chunk_to_retrieve` column is what you return to the LLM at query time.

**Tips:**
- Pass `imageOutputPath` on the upstream `ai_parse_document` call if you want page image URIs available in the prep output for multimodal retrieval.
- Schema is versioned major.minor; minor upgrades are backward-compatible — pin `version` only if you need to lock schema across deployments.
- On DBR < 18.2, fall back to manual chunking via `variant_get` + `explode` on `ai_parse_document` output.

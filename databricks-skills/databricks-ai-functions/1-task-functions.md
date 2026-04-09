# Task-Specific AI Functions — Full Reference

These functions require no model endpoint selection. They call pre-configured Foundation Model APIs optimized for each task. All require DBR 15.1+ (15.4 ML LTS for batch); `ai_parse_document` requires DBR 17.1+.

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

### V2 Syntax (Recommended)

```
ai_classify(content, labels [, options])
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `content` | VARIANT or STRING | Text to classify. Accepts VARIANT output from `ai_parse_document` directly. |
| `labels` | STRING | JSON array `'["label1","label2"]'` or JSON object with descriptions `'{"label1":"description1","label2":"description2"}'` — 2 to 500 labels |
| `options` | MAP\<STRING, STRING\> | Optional configuration (see below) |

**Options:**

| Key | Values | Description |
|-----|--------|-------------|
| `version` | `'1.0'`, `'2.0'` | Force API version (default: auto-detected from labels format) |
| `instructions` | STRING (max 20,000 chars) | Additional classification guidance |
| `multilabel` | `'true'`, `'false'` | Enable multi-label classification (default: `'false'`) |

**Returns:** VARIANT containing `{"response": ["label"], "error_message": null}`. Access the label with `:response[0]` (single-label) or iterate `:response` (multi-label). Returns `NULL` if content is null.

```sql
-- Basic classification with JSON array labels
SELECT ticket_text,
       ai_classify(ticket_text, '["urgent", "not urgent", "spam"]'):response[0] AS priority
FROM support_tickets;

-- Labels with descriptions for better disambiguation
SELECT ticket_text,
       ai_classify(
           ticket_text,
           '{"billing_error":"Payment or invoice issues","shipping_delay":"Delivery or logistics problems","product_defect":"Broken or malfunctioning product","other":"Anything else"}'
       ):response[0] AS category
FROM support_tickets;

-- Multi-label classification
SELECT ticket_text,
       ai_classify(
           ticket_text,
           '["billing", "shipping", "product_quality", "account_access"]',
           map('multilabel', 'true')
       ):response AS tags
FROM support_tickets;
```

```python
from pyspark.sql.functions import expr
df = spark.table("support_tickets")

# Single-label — extract label directly
df.withColumn(
    "priority",
    expr("ai_classify(ticket_text, '[\"urgent\", \"not urgent\", \"spam\"]'):response[0]")
).display()

# With instructions for context
df.withColumn(
    "priority",
    expr("""
        ai_classify(
            ticket_text,
            '["urgent", "not urgent", "spam"]',
            map('instructions', 'Classify as urgent only if the customer reports a system outage or data loss')
        ):response[0]
    """)
).display()
```

**Tips:**
- Fewer labels = more consistent results (2–5 is optimal for single-label)
- Use label descriptions (`{"label":"description"}` format) when labels are ambiguous
- V2 supports up to 500 labels (vs 20 in v1) — useful for fine-grained taxonomies
- Multi-label mode (`map('multilabel', 'true')`) returns all applicable labels — use when categories are not mutually exclusive
- Labels should be clearly distinguishable to avoid classification noise

### Legacy V1 Syntax

V1 syntax still works but V2 is recommended for new code.

```
ai_classify(content, labels)
```
- `content`: STRING — text to classify
- `labels`: ARRAY\<STRING\> — 2 to 20 mutually exclusive categories

Returns: STRING (matching label or `NULL`). Access directly — no `:response` path needed.

```sql
SELECT ai_classify(ticket_text, ARRAY('urgent', 'not urgent', 'spam')) AS priority
FROM support_tickets;
```

---

## `ai_extract`

**Docs:** https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_extract

### V2 Syntax (Recommended)

```
ai_extract(content, schema [, options])
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `content` | VARIANT or STRING | Source text. Accepts VARIANT output from `ai_parse_document` directly. |
| `schema` | STRING | JSON defining extraction structure (see schema formats below) |
| `options` | MAP\<STRING, STRING\> | Optional configuration (see below) |

**Options:**

| Key | Values | Description |
|-----|--------|-------------|
| `version` | `'1.0'`, `'2.0'` | Force API version (default: auto-detected from schema format) |
| `instructions` | STRING (max 20,000 chars) | Additional extraction guidance |

**Returns:** VARIANT containing `{"response": {...}, "error_message": null}`. Access fields with `:response.field` (SQL) or `["response"]["field"]` (Python DataFrame). Fields are `null` if not found.

### Schema Formats

The `schema` parameter accepts two formats:

**Simple array** — just field names (equivalent to v1 behavior):
```json
'["person", "location", "date"]'
```

**Typed object** — with types, descriptions, nested objects, and arrays:
```json
'{
  "type": "object",
  "properties": {
    "vendor_name": {"type": "string", "description": "Company or supplier name"},
    "total_amount": {"type": "number"},
    "is_paid": {"type": "boolean"},
    "status": {"type": "enum", "values": ["pending", "approved", "rejected"]},
    "line_items": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "item_code": {"type": "string"},
          "quantity": {"type": "integer"},
          "unit_price": {"type": "number"}
        }
      }
    }
  }
}'
```

**Supported types:** `string`, `integer`, `number`, `boolean`, `enum` (up to 500 values), `object`, `array`

**Limits:** max 128 fields, max 7 nesting levels, max 150 characters per field name

### Examples

```sql
-- Simple flat extraction (same fields as v1, but returns VARIANT)
SELECT
    entities:response.person  AS person,
    entities:response.location AS location,
    entities:response.date     AS date_mentioned
FROM (
    SELECT ai_extract(
        'John Doe called from New York on 2024-01-15.',
        '["person", "location", "date"]'
    ) AS entities
);

-- Typed schema with descriptions for better accuracy
SELECT ai_extract(
    invoice_text,
    '{
        "type": "object",
        "properties": {
            "invoice_number": {"type": "string"},
            "vendor_name": {"type": "string", "description": "Company or supplier name"},
            "issue_date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
            "total_amount": {"type": "number"},
            "tax_id": {"type": "string", "description": "Tax ID, digits only"}
        }
    }'
):response AS header
FROM invoices;

-- Nested extraction — arrays of objects (NEW in v2)
SELECT ai_extract(
    invoice_text,
    '{
        "type": "object",
        "properties": {
            "invoice_number": {"type": "string"},
            "line_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "item_code": {"type": "string"},
                        "description": {"type": "string"},
                        "quantity": {"type": "integer"},
                        "unit_price": {"type": "number"},
                        "total": {"type": "number"}
                    }
                }
            }
        }
    }'
):response AS invoice_data
FROM invoices;
```

```python
from pyspark.sql.functions import expr

df = spark.table("messages")

# Simple flat extraction
df = df.withColumn(
    "entities",
    expr("ai_extract(message, '[\"person\", \"location\", \"date\"]')")
)
df.select(
    "entities:response.person",
    "entities:response.location",
    "entities:response.date"
).display()

# Nested extraction with typed schema
schema = '''
{
    "type": "object",
    "properties": {
        "invoice_number": {"type": "string"},
        "vendor_name": {"type": "string"},
        "line_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "item_code": {"type": "string"},
                    "description": {"type": "string"},
                    "quantity": {"type": "integer"},
                    "unit_price": {"type": "number"},
                    "total": {"type": "number"}
                }
            }
        }
    }
}
'''
df = spark.table("invoices")
df = df.withColumn("result", expr(f"ai_extract(invoice_text, '{schema.strip()}')"))
df.select(
    "result:response.invoice_number",
    "result:response.vendor_name",
    "result:response.line_items"
).display()
```

**Composability with `ai_parse_document`:** V2 accepts VARIANT input directly — you can pass `ai_parse_document` output without casting to STRING:

```python
df = (
    spark.read.format("binaryFile").load("/Volumes/catalog/schema/docs/")
    .withColumn("parsed", expr("ai_parse_document(content)"))
    # Pass VARIANT directly to ai_extract — no STRING cast needed
    .withColumn("entities", expr("ai_extract(parsed, '[\"date\", \"amount\", \"vendor\"]')"))
    .select("path", "entities:response.*")
)
```

**Use `ai_query` instead when:** extraction exceeds 128 fields or 7 nesting levels, requires a custom model endpoint, involves multimodal input, or needs sampling parameter control.

### Legacy V1 Syntax

V1 syntax still works but V2 is recommended for new code.

```
ai_extract(content, labels)
```
- `content`: STRING — source text
- `labels`: ARRAY\<STRING\> — field names to extract

Returns: STRUCT where each field matches a label (access with dot notation: `entities.person`).

```sql
SELECT ai_extract('John Doe from New York', ARRAY('person', 'location')) AS entities;
-- Access: entities.person, entities.location
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

**Requires:** DBR 17.1+

**Syntax:** `ai_parse_document(content [, options])`
- `content`: BINARY — document content loaded from `read_files()` or `spark.read.format("binaryFile")`
- `options`: MAP\<STRING, STRING\> (optional) — parsing configuration

**Supported formats:** PDF, JPG/JPEG, PNG, DOCX, PPTX

Returns a VARIANT with pages, elements (text paragraphs, tables, figures, headers, footers), bounding boxes, and error metadata.

**Options:**

| Key | Values | Description |
|-----|--------|-------------|
| `version` | `'2.0'` | Output schema version |
| `imageOutputPath` | Volume path | Save rendered page images |
| `descriptionElementTypes` | `''`, `'figure'`, `'*'` | AI-generated descriptions (default: `'*'` for all) |

**Output schema:**

```
document
├── pages[]          -- page id, image_uri
└── elements[]       -- extracted content
    ├── type         -- "text", "table", "figure", etc.
    ├── content      -- extracted text
    ├── bbox         -- bounding box coordinates
    └── description  -- AI-generated description
metadata             -- file info, schema version
error_status[]       -- errors per page (if any)
```

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
      .withColumn("entities", expr("ai_extract(text_blocks, '[\"date\", \"amount\", \"vendor\"]')"))
      .withColumn("category", expr("ai_classify(text_blocks, '[\"invoice\", \"contract\", \"report\"]'):response[0]"))
)
df.display()
```

**Limitations:**
- Processing is slow for dense or low-resolution documents
- Suboptimal for non-Latin alphabets and digitally signed PDFs
- Custom models not supported — always uses the built-in parsing model

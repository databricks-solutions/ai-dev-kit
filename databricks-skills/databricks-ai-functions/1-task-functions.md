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

**Syntax:** `ai_classify(content, labels)`
- `content`: STRING — text to classify
- `labels`: ARRAY\<STRING\> — 2 to 20 mutually exclusive categories

Returns the matching label or `NULL`.

```sql
SELECT ticket_text,
       ai_classify(ticket_text, ARRAY('urgent', 'not urgent', 'spam')) AS priority
FROM support_tickets;
```

```python
from pyspark.sql.functions import expr
df = spark.table("support_tickets")
df.withColumn(
    "priority",
    expr("ai_classify(ticket_text, array('urgent', 'not urgent', 'spam'))")
).display()
```

**Tips:**
- Fewer labels = more consistent results (2–5 is optimal)
- Labels should be mutually exclusive and clearly distinguishable
- Not suitable for multi-label classification — run multiple calls if needed

---

## `ai_extract`

**Docs:** https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_extract

**Syntax:** `ai_extract(content, labels)`
- `content`: STRING — source text
- `labels`: ARRAY\<STRING\> — entity types to extract

Returns a STRUCT where each field name matches a label. Fields are `NULL` if not found.

```sql
-- Extract and access fields directly
SELECT
    entities.person,
    entities.location,
    entities.date
FROM (
    SELECT ai_extract(
        'John Doe called from New York on 2024-01-15.',
        ARRAY('person', 'location', 'date')
    ) AS entities
    FROM messages
);
```

```python
from pyspark.sql.functions import expr
df = spark.table("messages")
df = df.withColumn(
    "entities",
    expr("ai_extract(message, array('person', 'location', 'date'))")
)
df.select("entities.person", "entities.location", "entities.date").display()
```

**Use `ai_query` instead when:** the output has nested arrays or more than ~5 levels of hierarchy.

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

**Syntax:** `ai_parse_document(content)`
- `content`: BINARY — document content loaded from `read_files()` or `spark.read.format("binaryFile")`

**Supported formats:** PDF, JPG/JPEG, PNG, DOCX, PPTX

Returns a VARIANT with pages, elements (text paragraphs, tables, figures, headers, footers), bounding boxes, and error metadata.

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
- Processing is slow for dense or low-resolution documents
- Suboptimal for non-Latin alphabets and digitally signed PDFs
- Custom models not supported — always uses the built-in parsing model

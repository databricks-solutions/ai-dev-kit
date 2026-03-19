# `ai_query` — Full Reference

**Docs:** https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_query

> Use `ai_query` only when no task-specific function fits. See the function selection table in [SKILL.md](SKILL.md).

## When to Use `ai_query`

- Output schema has **nested arrays or deeply nested STRUCTs** (e.g., `itens: [{codigo, descricao, qtde}]`)
- Calling a **custom Model Serving endpoint** (your own fine-tuned model)
- **Multimodal input** — passing binary image files via `files =>`
- **Cross-document reasoning** — prompt includes content from multiple sources
- Need **sampling parameters** (`temperature`, `max_tokens`) control

## Syntax

```sql
ai_query(
    endpoint,
    request
    [, returnType      => ddl_schema]
    [, failOnError     => boolean]
    [, modelParameters => named_struct(...)]
    [, responseFormat  => json_string]
    [, files           => binary_column]
)
```

## Parameters

| Parameter | Type | Runtime | Description |
|---|---|---|---|
| `endpoint` | STRING literal | — | Foundation Model name or custom endpoint name. Never guess — use exact names from the [model serving docs](https://docs.databricks.com/aws/en/machine-learning/foundation-models/supported-models.html). |
| `request` | STRING or STRUCT | — | Prompt string for chat models; STRUCT for custom ML endpoints |
| `returnType` | DDL schema (optional) | 15.2+ | Structures the parsed response like `from_json` |
| `failOnError` | BOOLEAN (optional, default `true`) | 15.3+ | If `false`, returns STRUCT `{response, error}` instead of raising on failure |
| `modelParameters` | STRUCT (optional) | 15.3+ | Sampling params: `temperature`, `max_tokens`, `top_p`, etc. |
| `responseFormat` | JSON string (optional) | 15.4+ | Forces structured JSON output: `'{"type":"json_object"}'` |
| `files` | binary column (optional) | — | Pass binary images directly (JPEG/PNG) — no upload step needed |

## Foundation Model Names (Do Not Guess)

| Use case | Endpoint name |
|---|---|
| General reasoning / extraction | `databricks-claude-sonnet-4` |
| Fast / cheap tasks | `databricks-meta-llama-3-1-8b-instruct` |
| Large context / complex | `databricks-meta-llama-3-3-70b-instruct` |
| Multimodal (vision + text) | `databricks-llama-4-maverick` |
| Embeddings | `databricks-gte-large-en` |

## Patterns

### Basic — single prompt

```sql
SELECT ai_query(
    'databricks-meta-llama-3-3-70b-instruct',
    'Describe Databricks SQL in 30 words.'
) AS response;
```

### Applied to a table column

```sql
SELECT ticket_id,
       ai_query(
           'databricks-meta-llama-3-3-70b-instruct',
           CONCAT('Summarize in one sentence: ', ticket_body)
       ) AS summary
FROM support_tickets;
```

### Structured JSON output (`responseFormat`)

Preferred over `returnType` for chat models (requires Runtime 15.4+):

```sql
SELECT ai_query(
    'databricks-claude-sonnet-4',
    CONCAT('Extract invoice fields as JSON. Fields: numero, fornecedor, total, '
           'itens:[{codigo, descricao, qtde, vlrUnit}]. Input: ', text_blocks),
    responseFormat => '{"type":"json_object"}',
    failOnError     => false
) AS ai_response
FROM parsed_documents;
```

Then parse with `from_json`:

```python
from pyspark.sql.functions import from_json, col

df = df.withColumn(
    "invoice",
    from_json(
        col("ai_response.response"),
        "STRUCT<numero:STRING, fornecedor:STRING, total:DOUBLE, "
        "itens:ARRAY<STRUCT<codigo:STRING, descricao:STRING, qtde:DOUBLE, vlrUnit:DOUBLE>>>"
    )
)
# Access fields
df.select("invoice.numero", "invoice.total", "invoice.itens").display()
```

### With `failOnError` (always use in batch pipelines)

```sql
SELECT
    id,
    ai_response.response,
    ai_response.error
FROM (
    SELECT id,
           ai_query(
               'databricks-claude-sonnet-4',
               CONCAT('Classify: ', text),
               failOnError => false
           ) AS ai_response
    FROM documents
)
-- Route errors to a separate table downstream
```

### With `modelParameters` (control sampling)

```sql
SELECT ai_query(
    'databricks-meta-llama-3-3-70b-instruct',
    CONCAT('Extract entities from: ', text),
    failOnError     => false,
    modelParameters => named_struct('temperature', CAST(0.0 AS DOUBLE), 'max_tokens', 500)
) AS result
FROM documents;
```

### Multimodal — image files (`files =>`)

No file upload step needed. Pass the binary column directly:

```sql
SELECT
    path,
    ai_query(
        'databricks-llama-4-maverick',
        'Describe what is in this image in detail.',
        files => content
    ) AS description
FROM read_files('/Volumes/catalog/schema/images/', format => 'binaryFile');
```

```python
from pyspark.sql.functions import expr

df = (
    spark.read.format("binaryFile")
    .load("/Volumes/catalog/schema/images/")
    .withColumn("description", expr("""
        ai_query(
            'databricks-llama-4-maverick',
            'Describe the contents of this image.',
            files => content
        )
    """))
)
```

### As a reusable SQL UDF

```sql
CREATE FUNCTION catalog.schema.extract_invoice(text STRING)
RETURNS STRING
RETURN ai_query(
    'databricks-claude-sonnet-4',
    CONCAT('Extract invoice JSON from: ', text),
    responseFormat => '{"type":"json_object"}'
);

SELECT extract_invoice(document_text) FROM raw_documents;
```

### PySpark with `expr`

```python
from pyspark.sql.functions import expr

df = spark.table("documents")
df = df.withColumn("result", expr("""
    ai_query(
        'databricks-claude-sonnet-4',
        concat('Extract structured data from: ', content),
        responseFormat => '{"type":"json_object"}',
        failOnError     => false
    )
"""))
```

## Error Handling Pattern for Batch Pipelines

Always use `failOnError => false` in batch jobs. Write errors to a sidecar table:

```python
import dlt
from pyspark.sql.functions import expr, col

@dlt.table(comment="AI extraction results")
def extracted():
    return (
        dlt.read("raw")
        .withColumn("ai_response", expr("""
            ai_query('databricks-claude-sonnet-4', prompt,
                     responseFormat => '{"type":"json_object"}',
                     failOnError     => false)
        """))
    )

@dlt.table(comment="Rows that failed AI extraction")
def extraction_errors():
    return (
        dlt.read("extracted")
        .filter(col("ai_response.error").isNotNull())
        .select("id", "prompt", col("ai_response.error").alias("error"))
    )
```

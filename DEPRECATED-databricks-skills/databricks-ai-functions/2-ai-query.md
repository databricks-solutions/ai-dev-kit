# `ai_query` — Full Reference

Calls any Model Serving endpoint by name — a **built-in Databricks foundation model** (`databricks-claude-sonnet-4`, etc.) or your **own custom/fine-tuned serving endpoint**. **Last resort** among AI Functions — use only when no task-specific function fits: multimodal image input, cross-document reasoning, sampling-param control, a custom model, or JSON beyond `ai_extract`'s limits. See the [Overview table](SKILL.md#overview) for the signature.

## Parameters

| Parameter | Type | Runtime | Description |
|---|---|---|---|
| `endpoint` | STRING literal | — | Foundation Model or custom endpoint name. Never guess — use exact names below or from the [supported-models docs](https://docs.databricks.com/en/machine-learning/foundation-models/supported-models.html). |
| `request` | STRING or STRUCT | — | Prompt string for chat models; STRUCT for custom ML endpoints |
| `returnType` | DDL schema (optional) | 15.2+ | Structures the parsed response like `from_json` |
| `failOnError` | BOOLEAN (optional, default `true`) | 15.3+ | `false` → returns `STRUCT{response, errorMessage}` instead of raising. **Always set in batch.** |
| `modelParameters` | STRUCT (optional) | 15.3+ | Sampling params: `temperature`, `max_tokens`, `top_p` |
| `responseFormat` | JSON string (optional) | 15.4+ | Force structured output: `'{"type":"json_object"}'` |
| `files` | binary column (optional) | — | Pass JPEG/PNG bytes directly (multimodal) — no upload step |

## Endpoint Names (do not guess — list them)

Built-in foundation models are pre-provisioned `databricks-*` serving endpoints, but **which models exist is workspace- and date-specific** (new Claude/GPT/Gemini/Llama versions land regularly). List the real endpoints in the target workspace instead of hardcoding a name:

`serving-endpoints list` has no ownership/name filter (only `--limit`), so filter client-side. System foundation models are named `databricks-*` **and** have `creator == null` (a user-made endpoint that happens to start with `databricks-` has a real creator email — the `creator==null` check excludes it):

```bash
# Built-in foundation models, with task (chat vs embeddings):
databricks serving-endpoints list -o json \
  | jq -r '.[] | select(.name|startswith("databricks-")) | select(.creator==null) | "\(.name)\t\(.task)"'
```

Pick by `task`: `llm/v1/chat` for `ai_query` text/multimodal, `llm/v1/embeddings` for embeddings. Broadly-available stable names to fall back on: `databricks-claude-sonnet-4` (general), `databricks-meta-llama-3-1-8b-instruct` (fast/cheap), `databricks-llama-4-maverick` (vision), `databricks-gte-large-en` (embeddings). Newer families (e.g. `databricks-claude-opus-4-*`, `databricks-gpt-5-*`, `databricks-gemini-3-*`) appear in many workspaces — confirm with the list above before using one.

## Patterns

```sql
-- Structured JSON output + batch-safe error handling (the two flags you almost always want)
SELECT id, ai_response.response, ai_response.errorMessage
FROM (
  SELECT id, ai_query(
      'databricks-claude-sonnet-4',
      CONCAT('Extract invoice fields as JSON {numero, total, itens:[{codigo, qtde}]}: ', text_blocks),
      responseFormat => '{"type":"json_object"}',
      failOnError    => false,
      modelParameters => named_struct('temperature', CAST(0.0 AS DOUBLE), 'max_tokens', 500)
  ) AS ai_response
  FROM parsed_documents
);
-- Route rows WHERE ai_response.errorMessage IS NOT NULL to a sidecar table.
```

Parse the JSON response with `from_json`, or for multimodal pass the binary column via `files =>`:

```sql
-- Multimodal: describe images, no upload step
SELECT path, ai_query('databricks-llama-4-maverick',
    'Describe this image.', files => content) AS description
FROM read_files('/Volumes/catalog/schema/images/', format => 'binaryFile');
```

```sql
-- Reusable SQL UDF wrapping a fixed prompt + endpoint
CREATE FUNCTION catalog.schema.extract_invoice(text STRING) RETURNS STRING
RETURN ai_query('databricks-claude-sonnet-4',
    CONCAT('Extract invoice JSON from: ', text),
    responseFormat => '{"type":"json_object"}');
```

In PySpark, call inside `expr("...")` (`spark.table("t").withColumn("out", expr("ai_query(...)"))`). For SDP batch pipelines, write results and errors to two `@dp.table` stages (split on `ai_response.errorMessage IS NOT NULL`).

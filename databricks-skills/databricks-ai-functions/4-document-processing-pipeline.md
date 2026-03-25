# Document Processing Pipeline with AI Functions

End-to-end patterns for building batch document processing pipelines using AI Functions in a Lakeflow Declarative Pipeline (DLT). Covers function selection, `config.yml` centralization, error handling, and guidance on near-real-time variants with DSPy or LangChain.

> For workflow migration context (e.g., migrating from n8n, LangChain, or other orchestration tools), see the companion skill `n8n-to-databricks`.

---

## Function Selection for Document Pipelines

When processing documents with AI Functions, apply this order of preference for each stage:

| Stage | Preferred function | Use `ai_query` when... |
|---|---|---|
| Parse binary docs (PDF, DOCX, images) | `ai_parse_document` | Need image-level reasoning |
| Extract flat fields from text | `ai_extract` | Schema has nested arrays |
| Classify document type or status | `ai_classify` | More than 20 categories |
| Score item similarity / matching | `ai_similarity` | Need cross-document reasoning |
| Summarize long sections | `ai_summarize` | — |
| Extract nested JSON (e.g. line items) | `ai_query` with `responseFormat` | (This is the intended use case) |

---

## Centralized Configuration (`config.yml`)

**Always centralize model names, volume paths, and prompts in a `config.yml`.** This makes model swaps a one-line change and keeps pipeline code free of hardcoded strings.

```yaml
# config.yml
models:
  default: "databricks-claude-sonnet-4"
  mini:    "databricks-meta-llama-3-1-8b-instruct"
  vision:  "databricks-llama-4-maverick"

catalog:
  name:   "my_catalog"
  schema: "document_processing"

volumes:
  input: "/Volumes/my_catalog/document_processing/landing/"
  tmp:   "/Volumes/my_catalog/document_processing/tmp/"

output_tables:
  results: "my_catalog.document_processing.processed_docs"
  errors:  "my_catalog.document_processing.processing_errors"

prompts:
  extract_invoice: |
    Extract invoice fields and return ONLY valid JSON.
    Fields: invoice_number, vendor_name, vendor_tax_id (digits only),
    issue_date (dd/mm/yyyy), total_amount (numeric),
    line_items: [{item_code, description, quantity, unit_price, total}].
    Return null for missing fields.

  classify_doc: |
    Classify this document into exactly one category.
```

```python
# config_loader.py
import yaml

def load_config(path: str = "config.yml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)

CFG           = load_config()
ENDPOINT      = CFG["models"]["default"]
ENDPOINT_MINI = CFG["models"]["mini"]
VOLUME_INPUT  = CFG["volumes"]["input"]
PROMPT_INV    = CFG["prompts"]["extract_invoice"]
```

---

## Batch Pipeline — Lakeflow Declarative Pipeline

Each logical step in your document workflow maps to a `@dlt.table` stage. Data flows through Delta tables between stages.

```
[Landing Volume]  →  Stage 1: ai_parse_document
                  →  Stage 2: ai_classify (document type)
                  →  Stage 3: ai_extract (flat fields) + ai_query (nested JSON)
                  →  Stage 4: ai_similarity (item matching)
                  →  Stage 5: Final Delta output table
```

### `pipeline.py`

```python
import dlt
import yaml
from pyspark.sql.functions import expr, col, from_json

CFG      = yaml.safe_load(open("/Workspace/path/to/config.yml"))
ENDPOINT = CFG["models"]["default"]
VOL_IN   = CFG["volumes"]["input"]
PROMPT   = CFG["prompts"]["extract_invoice"]


# ── Stage 1: Parse binary documents ──────────────────────────────────────────
# Preferred: ai_parse_document — no model selection, no ai_query needed

@dlt.table(comment="Parsed document text from all file types in the landing volume")
def raw_parsed():
    return (
        spark.read.format("binaryFile").load(VOL_IN)
        .withColumn("parsed", expr("ai_parse_document(content)"))
        .selectExpr(
            "path",
            "parsed:pages[*].elements[*].content AS text_blocks",
            "parsed:error AS parse_error",
        )
        .filter("parse_error IS NULL")
    )


# ── Stage 2: Classify document type ──────────────────────────────────────────
# Preferred: ai_classify — cheap, no endpoint selection

@dlt.table(comment="Document type classification")
def classified_docs():
    return (
        dlt.read("raw_parsed")
        .withColumn(
            "doc_type",
            expr("ai_classify(text_blocks, array('invoice', 'purchase_order', 'receipt', 'contract', 'other'))")
        )
    )


# ── Stage 3a: Flat field extraction ──────────────────────────────────────────
# Preferred: ai_extract for flat fields (vendor, date, total)

@dlt.table(comment="Flat header fields extracted from documents")
def extracted_flat():
    return (
        dlt.read("classified_docs")
        .filter("doc_type = 'invoice'")
        .withColumn(
            "header",
            expr("ai_extract(text_blocks, array('invoice_number', 'vendor_name', 'issue_date', 'total_amount', 'tax_id'))")
        )
        .select("path", "doc_type", "text_blocks", col("header"))
    )


# ── Stage 3b: Nested JSON extraction (last resort: ai_query) ─────────────────
# Use ai_query only because line_items is a nested array — ai_extract can't handle it

@dlt.table(comment="Nested line items extracted — ai_query used for array schema only")
def extracted_line_items():
    return (
        dlt.read("extracted_flat")
        .withColumn(
            "ai_response",
            expr(f"""
                ai_query(
                    '{ENDPOINT}',
                    concat('{PROMPT.strip()}', '\\n\\nDocument text:\\n', LEFT(text_blocks, 6000)),
                    responseFormat => '{{"type":"json_object"}}',
                    failOnError     => false
                )
            """)
        )
        .withColumn(
            "line_items",
            from_json(
                col("ai_response.response"),
                "STRUCT<line_items:ARRAY<STRUCT<item_code:STRING, description:STRING, "
                "quantity:DOUBLE, unit_price:DOUBLE, total:DOUBLE>>>"
            )
        )
        .select("path", "doc_type", "header", "line_items", col("ai_response.error").alias("extraction_error"))
    )


# ── Stage 4: Similarity matching ─────────────────────────────────────────────
# Preferred: ai_similarity for fuzzy matching between extracted fields

@dlt.table(comment="Vendor name similarity vs reference master data")
def vendor_matched():
    extracted = dlt.read("extracted_line_items")
    # Join against a reference vendor table for fuzzy matching
    vendors = spark.table("my_catalog.document_processing.vendor_master").select("vendor_id", "vendor_name")

    return (
        extracted.crossJoin(vendors)
        .withColumn(
            "name_similarity",
            expr("ai_similarity(header.vendor_name, vendor_name)")
        )
        .filter("name_similarity > 0.80")
        .orderBy("name_similarity", ascending=False)
    )


# ── Stage 5: Final output + error sidecar ────────────────────────────────────

@dlt.table(
    comment="Final processed documents ready for downstream consumption",
    table_properties={"delta.enableChangeDataFeed": "true"},
)
def processed_docs():
    return (
        dlt.read("extracted_line_items")
        .filter("extraction_error IS NULL")
        .selectExpr(
            "path",
            "doc_type",
            "header.invoice_number",
            "header.vendor_name",
            "header.issue_date",
            "header.total_amount",
            "line_items.line_items AS items",
        )
    )


@dlt.table(comment="Rows that failed at any extraction stage — review and reprocess")
def processing_errors():
    return (
        dlt.read("extracted_line_items")
        .filter("extraction_error IS NOT NULL")
        .select("path", "doc_type", col("extraction_error").alias("error"))
    )
```

---

## Custom RAG Pipeline — Parse → Chunk → Index → Query

When the goal is retrieval-augmented generation rather than field extraction, use this pipeline to parse documents, chunk them into a Delta table, and index with Vector Search.

### Step 1 — Parse and Chunk into a Delta Table

`ai_parse_document` returns a VARIANT. Use `variant_get` with an explicit `ARRAY<VARIANT>` cast before calling `explode`, since `explode()` does not accept raw VARIANT values.

```sql
CREATE OR REPLACE TABLE catalog.schema.parsed_chunks AS
WITH parsed AS (
  SELECT
    path,
    ai_parse_document(content) AS doc
  FROM read_files('/Volumes/catalog/schema/volume/docs/', format => 'binaryFile')
),
elements AS (
  SELECT
    path,
    explode(variant_get(doc, '$.document.elements', 'ARRAY<VARIANT>')) AS element
  FROM parsed
)
SELECT
  md5(concat(path, variant_get(element, '$.content', 'STRING'))) AS chunk_id,
  path AS source_path,
  variant_get(element, '$.content', 'STRING') AS content,
  variant_get(element, '$.type', 'STRING') AS element_type,
  current_timestamp() AS parsed_at
FROM elements
WHERE variant_get(element, '$.content', 'STRING') IS NOT NULL
  AND length(trim(variant_get(element, '$.content', 'STRING'))) > 10;
```

### Step 1a (Production) — Incremental Parsing with Structured Streaming

For production pipelines where new documents arrive over time, use Structured Streaming with checkpoints for exactly-once processing. Each run processes only new files, then stops with `trigger(availableNow=True)`.

See the official bundle example:
[databricks/bundle-examples/contrib/job_with_ai_parse_document](https://github.com/databricks/bundle-examples/tree/main/contrib/job_with_ai_parse_document)

**Stage 1 — Parse raw documents (streaming):**

```python
from pyspark.sql.functions import col, current_timestamp, expr

files_df = (
    spark.readStream.format("binaryFile")
    .option("pathGlobFilter", "*.{pdf,jpg,jpeg,png}")
    .option("recursiveFileLookup", "true")
    .load("/Volumes/catalog/schema/volume/docs/")
)

parsed_df = (
    files_df
    .repartition(8, expr("crc32(path) % 8"))
    .withColumn("parsed", expr("""
        ai_parse_document(content, map(
            'version', '2.0',
            'descriptionElementTypes', '*'
        ))
    """))
    .withColumn("parsed_at", current_timestamp())
    .select("path", "parsed", "parsed_at")
)

(
    parsed_df.writeStream.format("delta")
    .outputMode("append")
    .option("checkpointLocation", "/Volumes/catalog/schema/checkpoints/01_parse")
    .option("mergeSchema", "true")
    .trigger(availableNow=True)
    .toTable("catalog.schema.parsed_documents_raw")
)
```

**Stage 2 — Extract text from parsed VARIANT (streaming):**

Uses `transform()` to extract element content from the VARIANT array, and `try_cast` for safe access. Error rows are preserved but flagged.

```python
from pyspark.sql.functions import col, concat_ws, expr, lit, when

parsed_stream = spark.readStream.format("delta").table("catalog.schema.parsed_documents_raw")

text_df = (
    parsed_stream
    .withColumn("text",
        when(
            expr("try_cast(parsed:error_status AS STRING)").isNotNull(), lit(None)
        ).otherwise(
            concat_ws("\n\n", expr("""
                transform(
                    try_cast(parsed:document:elements AS ARRAY),
                    element -> try_cast(element:content AS STRING)
                )
            """))
        )
    )
    .withColumn("error_status", expr("try_cast(parsed:error_status AS STRING)"))
    .select("path", "text", "error_status", "parsed_at")
)

(
    text_df.writeStream.format("delta")
    .outputMode("append")
    .option("checkpointLocation", "/Volumes/catalog/schema/checkpoints/02_text")
    .option("mergeSchema", "true")
    .trigger(availableNow=True)
    .toTable("catalog.schema.parsed_documents_text")
)
```

Key techniques:
- **`repartition` by file hash** — parallelizes `ai_parse_document` across workers
- **`trigger(availableNow=True)`** — processes all pending files then stops (batch-like)
- **Checkpoints** — exactly-once guarantee; no re-parsing on re-runs
- **`transform()` + `try_cast`** — safer than `explode` + `variant_get` for text extraction
- **Separate stages with independent checkpoints** — parse and text extraction can fail/retry independently

### Step 1b — Enable Change Data Feed

Required for Vector Search Delta Sync:

```sql
ALTER TABLE catalog.schema.parsed_chunks
SET TBLPROPERTIES (delta.enableChangeDataFeed = true);
```

### Step 2 — Create a Vector Search Index and Query It

Use the **[databricks-vector-search](../databricks-vector-search/SKILL.md)** skill to create a Delta Sync index on the chunked table and query it. Ensure CDF is enabled first (Step 1b above).

### RAG-Specific Issues

| Issue | Solution |
|-------|----------|
| `explode()` fails with VARIANT | `explode()` requires ARRAY, not VARIANT. Use `variant_get(doc, '$.document.elements', 'ARRAY<VARIANT>')` to cast before exploding |
| Short/noisy chunks | Filter with `length(trim(...)) > 10` — parsing produces tiny fragments (page numbers, headers) that pollute the index |
| Re-parsing unchanged documents | Use Structured Streaming with checkpoints — see Step 1a above |
| Region not supported | US/EU regions only, or enable cross-geography routing |

---

## Near-Real-Time Variant — DSPy + MLflow Agent

When the pipeline must respond in seconds (triggered by a user action, API call, or form submission), use DSPy with an MLflow ChatAgent instead of a DLT pipeline.

**When to use DSPy vs LangChain:**

| Scenario | Stack |
|---|---|
| Fixed pipeline steps, well-defined I/O, want prompt optimization | **DSPy** |
| Needs tool-calling, memory, or multi-agent coordination | **LangChain LCEL** + MLflow ChatAgent |
| Single LLM call, simple task | Direct AI Function or `ai_query` in a notebook |

### DSPy Signatures (replace LangChain agent system prompts)

```python
# pip install dspy-ai mlflow databricks-sdk
import dspy, yaml

CFG = yaml.safe_load(open("config.yml"))
lm = dspy.LM(
    model=f"databricks/{CFG['models']['default']}",
    api_base="https://<workspace-host>/serving-endpoints",
    api_key=dbutils.secrets.get("scope", "databricks-token"),
)
dspy.configure(lm=lm)


class ExtractInvoiceHeader(dspy.Signature):
    """Extract invoice header fields from document text."""
    document_text:  str = dspy.InputField(desc="Raw text from the document")
    invoice_number: str = dspy.OutputField(desc="Invoice number, or null")
    vendor_name:    str = dspy.OutputField(desc="Vendor/supplier name, or null")
    issue_date:     str = dspy.OutputField(desc="Date as dd/mm/yyyy, or null")
    total_amount:  float = dspy.OutputField(desc="Total amount as float, or null")


class ClassifyDocument(dspy.Signature):
    """Classify a document into one of the provided categories."""
    document_text: str = dspy.InputField()
    category:      str = dspy.OutputField(
        desc="One of: invoice, purchase_order, receipt, contract, other"
    )


class DocumentPipeline(dspy.Module):
    def __init__(self):
        self.classify = dspy.Predict(ClassifyDocument)
        self.extract  = dspy.Predict(ExtractInvoiceHeader)

    def forward(self, document_text: str):
        doc_type = self.classify(document_text=document_text).category
        if doc_type == "invoice":
            header = self.extract(document_text=document_text)
            return {"doc_type": doc_type, "header": header.__dict__}
        return {"doc_type": doc_type, "header": None}


pipeline = DocumentPipeline()
```

### Wrap and Register with MLflow

```python
import mlflow, json

class DSPyDocumentAgent(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        import dspy, yaml
        cfg = yaml.safe_load(open(context.artifacts["config"]))
        lm = dspy.LM(model=f"databricks/{cfg['models']['default']}")
        dspy.configure(lm=lm)
        self.pipeline = DocumentPipeline()

    def predict(self, context, model_input):
        text = model_input.iloc[0]["document_text"]
        return json.dumps(self.pipeline(document_text=text), ensure_ascii=False)

mlflow.set_registry_uri("databricks-uc")
with mlflow.start_run():
    mlflow.pyfunc.log_model(
        artifact_path="document_agent",
        python_model=DSPyDocumentAgent(),
        artifacts={"config": "config.yml"},
        registered_model_name="my_catalog.document_processing.document_agent",
    )
```

---

## Tips

1. **Parse first, enrich second** — always run `ai_parse_document` as the first stage. Feed its text output to task-specific functions; never pass raw binary to `ai_query`.
2. **Flat fields → `ai_extract`; nested arrays → `ai_query`** — this is the clearest decision boundary.
3. **`failOnError => false` is mandatory in batch** — write errors to a sidecar `_errors` table rather than crashing the pipeline.
4. **Truncate before sending to `ai_query`** — use `LEFT(text, 6000)` or chunk long documents to stay within context window limits.
5. **Prompts belong in `config.yml`** — never hardcode prompt strings in pipeline code. A prompt change should be a config change, not a code change.
6. **DSPy for agents** — when migrating from LangChain agent-based tools, DSPy typed `Signature` classes give you structured I/O contracts, testability, and optional prompt compilation/optimization.

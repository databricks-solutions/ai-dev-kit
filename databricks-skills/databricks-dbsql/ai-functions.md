# AI Functions, http_request, remote_query, and read_files Reference

Comprehensive reference for Databricks SQL advanced functions: built-in AI functions, HTTP requests, Lakehouse Federation remote queries, and file reading.

---

## Table of Contents

- [AI Functions Overview](#ai-functions-overview)
- [ai_query -- General-Purpose AI Function](#ai_query----general-purpose-ai-function)
- [Task-Specific AI Functions](#task-specific-ai-functions)
  - [ai_gen](#ai_gen)
  - [ai_classify](#ai_classify)
  - [ai_extract](#ai_extract)
  - [ai_analyze_sentiment](#ai_analyze_sentiment)
  - [ai_similarity](#ai_similarity)
  - [ai_summarize](#ai_summarize)
  - [ai_translate](#ai_translate)
  - [ai_fix_grammar](#ai_fix_grammar)
  - [ai_mask](#ai_mask)
- [Document and Multimodal AI Functions](#document-and-multimodal-ai-functions)
  - [ai_parse_document](#ai_parse_document)
- [Time Series AI Functions](#time-series-ai-functions)
  - [ai_forecast](#ai_forecast)
- [Vector Search Function](#vector-search-function)
  - [vector_search](#vector_search)
- [http_request Function](#http_request-function)
- [remote_query Function (Lakehouse Federation)](#remote_query-function-lakehouse-federation)
- [read_files Table-Valued Function](#read_files-table-valued-function)

---

## AI Functions Overview

Databricks AI Functions are built-in SQL functions that invoke state-of-the-art generative AI models directly from SQL. They run on Databricks Foundation Model APIs and are available from Databricks SQL, notebooks, Lakeflow Spark Declarative Pipelines, and Workflows.

**Common Requirements for All AI Functions:**
- Workspace must be in a region supporting AI Functions optimized for batch inference
- Not available on Databricks SQL Classic (requires Serverless SQL Warehouse)
- Databricks Runtime 15.1+ for notebooks; 15.4 ML LTS recommended for batch workloads
- Models licensed under Apache 2.0 or LLAMA 3.3 Community License
- Currently tuned for English (underlying models support multiple languages)
- Public Preview, HIPAA compliant

**Rate Limits and Billing:**
- AI Functions are subject to Foundation Model API rate limits
- Billed as Databricks SQL compute plus token usage on Foundation Model APIs
- Use `LIMIT` in queries during development to control costs

---

## ai_query -- General-Purpose AI Function

The most powerful and flexible AI function. Queries any serving endpoint (Foundation Models, external models, or custom ML models) for real-time or batch inference.

### Syntax

```sql
-- Basic invocation
ai_query(endpoint, request)

-- Full invocation with all optional parameters
ai_query(
  endpoint,
  request,
  returnType          => type_expression,
  failOnError         => boolean,
  modelParameters     => named_struct(...),
  responseFormat      => format_string,
  files               => content_expression
)
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `endpoint` | STRING | Yes | Name of a Foundation Model, external model, or custom model serving endpoint in the same workspace |
| `request` | STRING or STRUCT | Yes | For LLM endpoints: STRING prompt. For custom ML endpoints: single column or STRUCT matching expected input features |
| `returnType` | Expression | No | Expected return type (DDL-style). Optional in Runtime 15.2+; required in 15.1 and below |
| `failOnError` | BOOLEAN | No | Default `true`. When `false`, returns STRUCT with `response` and `errorStatus` fields instead of failing |
| `modelParameters` | STRUCT | No | Model parameters via `named_struct()` (Runtime 15.3+) |
| `responseFormat` | STRING | No | Controls output format: `'text'`, `'json_object'`, or a DDL/JSON schema string (Runtime 15.4 LTS+, chat models only) |
| `files` | Expression | No | Multimodal file input for image processing (JPEG, PNG supported) |

### Return Types

| Scenario | Return Type |
|----------|-------------|
| `failOnError => true` (default) | Parsed response matching endpoint type or `returnType` |
| `failOnError => false` | `STRUCT<result: T, errorMessage: STRING>` where T is the parsed type |
| With `responseFormat` | Structured output matching the specified schema |

### Model Parameters

```sql
-- Control generation with modelParameters
SELECT ai_query(
  'databricks-meta-llama-3-3-70b-instruct',
  'Explain quantum computing in 3 sentences.',
  modelParameters => named_struct(
    'max_tokens', 256,
    'temperature', 0.1,
    'top_p', 0.9
  )
) AS response;
```

Common model parameters:
- `max_tokens` (INT) -- Maximum tokens to generate
- `temperature` (DOUBLE) -- Randomness (0.0 = deterministic, 2.0 = max random)
- `top_p` (DOUBLE) -- Nucleus sampling threshold
- `stop` (ARRAY<STRING>) -- Stop sequences

### Structured Output with responseFormat

> **Note:** The top-level `responseFormat` STRUCT must contain exactly one field. To return multiple fields, wrap them in a single outer field.

```sql
-- Force JSON output matching a schema (top-level STRUCT must have exactly one field)
SELECT ai_query(
  'databricks-meta-llama-3-3-70b-instruct',
  'Extract the product name, price, and category from: "Sony WH-1000XM5 headphones, $348, Electronics"',
  responseFormat => 'STRUCT<result: STRUCT<product_name: STRING, price: DOUBLE, category: STRING>>'
) AS extracted;
```

### Batch Inference on Tables

```sql
-- Classify all rows in a table
SELECT
  review_id,
  review_text,
  ai_query(
    'databricks-meta-llama-3-3-70b-instruct',
    CONCAT('Classify the following review as positive, negative, or neutral: ', review_text),
    responseFormat => 'STRUCT<result: STRUCT<sentiment: STRING, confidence: STRING>>'
  ) AS classification
FROM catalog.schema.product_reviews;
```

### Custom ML Model Inference

```sql
-- Query a custom sklearn/MLflow model
SELECT ai_query(
  endpoint  => 'spam-classification-endpoint',
  request   => named_struct(
    'text', email_body,
    'subject', email_subject
  ),
  returnType => 'BOOLEAN'
) AS is_spam
FROM catalog.schema.inbox_messages;
```

### Multimodal (Image) Input

```sql
-- Analyze images using a vision model
SELECT ai_query(
  'databricks-meta-llama-3-2-90b-instruct',
  'Describe the contents of this image.',
  files => READ_FILES('/Volumes/catalog/schema/images/photo.jpg', format => 'binaryFile')
) AS description;
```

### Error Handling with failOnError

```sql
-- Graceful error handling for batch processing
SELECT
  id,
  result.result AS answer,
  result.errorMessage AS error
FROM (
  SELECT
    id,
    ai_query(
      'databricks-meta-llama-3-3-70b-instruct',
      question,
      failOnError => false
    ) AS result
  FROM catalog.schema.questions
);
```

### Embedding Generation

```sql
-- Generate embeddings using ai_query
SELECT
  text,
  ai_query('databricks-gte-large-en', text) AS embedding
FROM catalog.schema.documents;
```

---

## Task-Specific AI Functions

These functions provide simplified, single-purpose interfaces that do not require specifying an endpoint or model.

### ai_gen

Generate text from a prompt.

```sql
ai_gen(prompt)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `prompt` | STRING | The user's request/prompt |

**Returns:** STRING

```sql
-- Simple generation
SELECT ai_gen('Generate a concise, cheerful email title for a summer bike sale with 20% discount');
-- Returns: "Summer Bike Sale: Grab Your Dream Bike at 20% Off!"

-- Generation using table data
SELECT
  question,
  ai_gen('You are a teacher. Answer the students question in 50 words: ' || question) AS answer
FROM catalog.schema.questions
LIMIT 10;
```

---

### ai_classify

Classify text into one of the provided labels.

```sql
ai_classify(content, labels)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `content` | STRING | Text to classify |
| `labels` | ARRAY<STRING> | Classification options (min 2, max 20 elements) |

**Returns:** STRING matching one of the labels, or NULL if classification fails.

```sql
-- Simple classification
SELECT ai_classify('My password is leaked.', ARRAY('urgent', 'not urgent'));
-- Returns: "urgent"

-- Batch product categorization
SELECT
  product_name,
  description,
  ai_classify(description, ARRAY('clothing', 'shoes', 'accessories', 'furniture')) AS category
FROM catalog.schema.products
LIMIT 100;

-- Support ticket routing
SELECT
  ticket_id,
  ai_classify(
    description,
    ARRAY('billing', 'technical', 'account', 'feature_request', 'other')
  ) AS department
FROM catalog.schema.support_tickets;
```

---

### ai_extract

Extract named entities from text.

```sql
ai_extract(content, labels)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `content` | STRING | Text to extract entities from |
| `labels` | ARRAY<STRING> | Entity types to extract |

**Returns:** STRUCT where each field corresponds to a label, containing the extracted entity as STRING. Returns NULL if content is NULL.

```sql
-- Extract person, location, organization
SELECT ai_extract(
  'John Doe lives in New York and works for Acme Corp.',
  ARRAY('person', 'location', 'organization')
);
-- Returns: {"person": "John Doe", "location": "New York", "organization": "Acme Corp."}

-- Extract contact details
SELECT ai_extract(
  'Send an email to jane.doe@example.com about the meeting at 10am.',
  ARRAY('email', 'time')
);
-- Returns: {"email": "jane.doe@example.com", "time": "10am"}

-- Batch entity extraction from customer feedback
SELECT
  feedback_id,
  ai_extract(feedback_text, ARRAY('product', 'issue', 'person')) AS entities
FROM catalog.schema.customer_feedback;
```

---

### ai_analyze_sentiment

Perform sentiment analysis on text.

```sql
ai_analyze_sentiment(content)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `content` | STRING | Text to analyze |

**Returns:** STRING -- one of `'positive'`, `'negative'`, `'neutral'`, or `'mixed'`. Returns NULL if sentiment cannot be determined.

```sql
SELECT ai_analyze_sentiment('I am happy');     -- Returns: "positive"
SELECT ai_analyze_sentiment('I am sad');       -- Returns: "negative"
SELECT ai_analyze_sentiment('It is what it is'); -- Returns: "neutral"

-- Aggregate sentiment by product
SELECT
  product_id,
  ai_analyze_sentiment(review_text) AS sentiment,
  COUNT(*) AS review_count
FROM catalog.schema.reviews
GROUP BY product_id, ai_analyze_sentiment(review_text);
```

---

### ai_similarity

Compute semantic similarity between two text strings.

```sql
ai_similarity(expr1, expr2)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `expr1` | STRING | First text to compare |
| `expr2` | STRING | Second text to compare |

**Returns:** FLOAT -- Semantic similarity score where 1.0 means identical. The score is relative and should only be used for ranking.

```sql
-- Exact match
SELECT ai_similarity('Apache Spark', 'Apache Spark');
-- Returns: 1.0

-- Find similar company names (fuzzy matching)
SELECT company_name, ai_similarity(company_name, 'Databricks') AS score
FROM catalog.schema.customers
ORDER BY score DESC
LIMIT 10;

-- Duplicate detection
SELECT
  a.id AS id_a,
  b.id AS id_b,
  ai_similarity(a.description, b.description) AS similarity
FROM catalog.schema.products a
JOIN catalog.schema.products b ON a.id < b.id
WHERE ai_similarity(a.description, b.description) > 0.85;
```

---

### ai_summarize

Generate a summary of text.

```sql
ai_summarize(content [, max_words])
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `content` | STRING | Yes | Text to summarize |
| `max_words` | INTEGER | No | Target word count for summary. Default: 50. Set to 0 for no limit |

**Returns:** STRING. Returns NULL if content is NULL.

```sql
-- Summarize with default 50-word limit
SELECT ai_summarize(
  'Apache Spark is a unified analytics engine for large-scale data processing. '
  || 'It provides high-level APIs in Java, Scala, Python and R, and an optimized '
  || 'engine that supports general execution graphs.'
);

-- Summarize with custom word limit
SELECT ai_summarize(article_body, 100) AS summary
FROM catalog.schema.articles;

-- Executive summaries for reports
SELECT
  report_id,
  report_title,
  ai_summarize(report_body, 30) AS executive_summary
FROM catalog.schema.quarterly_reports;
```

---

### ai_translate

Translate text to a target language.

```sql
ai_translate(content, to_lang)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `content` | STRING | Text to translate |
| `to_lang` | STRING | Target language code |

**Supported Languages:** English (`en`), German (`de`), French (`fr`), Italian (`it`), Portuguese (`pt`), Hindi (`hi`), Spanish (`es`), Thai (`th`).

**Returns:** STRING. Returns NULL if content is NULL.

```sql
-- English to Spanish
SELECT ai_translate('Hello, how are you?', 'es');
-- Returns: "Hola, como estas?"

-- Spanish to English
SELECT ai_translate('La vida es un hermoso viaje.', 'en');
-- Returns: "Life is a beautiful journey."

-- Translate product descriptions for localization
SELECT
  product_id,
  description AS original,
  ai_translate(description, 'fr') AS french,
  ai_translate(description, 'de') AS german
FROM catalog.schema.products;
```

---

### ai_fix_grammar

Correct grammatical errors in text.

```sql
ai_fix_grammar(content)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `content` | STRING | Text to correct |

**Returns:** STRING with corrected grammar. Returns NULL if content is NULL.

```sql
SELECT ai_fix_grammar('This sentence have some mistake');
-- Returns: "This sentence has some mistakes"

SELECT ai_fix_grammar('She dont know what to did.');
-- Returns: "She doesn't know what to do."

-- Clean up user-generated content
SELECT
  comment_id,
  original_text,
  ai_fix_grammar(original_text) AS corrected_text
FROM catalog.schema.user_comments;
```

---

### ai_mask

Mask specified entity types in text (PII redaction).

```sql
ai_mask(content, labels)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `content` | STRING | Text containing entities to mask |
| `labels` | ARRAY<STRING> | Entity types to mask (e.g., `'person'`, `'email'`, `'phone'`, `'address'`, `'location'`, `'ssn'`, `'credit_card'`) |

**Returns:** STRING with specified entities replaced by `[MASKED]`. Returns NULL if content is NULL.

```sql
-- Mask personal information
SELECT ai_mask(
  'John Doe lives in New York. His email is john.doe@example.com.',
  ARRAY('person', 'email')
);
-- Returns: "[MASKED] lives in New York. His email is [MASKED]."

-- Mask contact details
SELECT ai_mask(
  'Contact me at 555-1234 or visit us at 123 Main St.',
  ARRAY('phone', 'address')
);
-- Returns: "Contact me at [MASKED] or visit us at [MASKED]"

-- Create anonymized dataset
CREATE TABLE catalog.schema.anonymized_feedback AS
SELECT
  feedback_id,
  ai_mask(feedback_text, ARRAY('person', 'email', 'phone', 'address')) AS masked_text,
  category
FROM catalog.schema.customer_feedback;
```

---

## Document and Multimodal AI Functions

### ai_parse_document

Extract structured content from unstructured documents (PDF, DOCX, PPTX, images).

```sql
ai_parse_document(content)
ai_parse_document(content, options_map)
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `content` | BINARY | Yes | Document as binary blob data |
| `options` | MAP<STRING, STRING> | No | Configuration options |

**Options Map Keys:**

| Key | Values | Description |
|-----|--------|-------------|
| `version` | `'2.0'` | Output schema version |
| `imageOutputPath` | Volume path | Path to save rendered page images in Unity Catalog volume |
| `descriptionElementTypes` | `''`, `'figure'`, `'*'` | Controls AI-generated descriptions. Default: `'*'` (all elements) |

**Returns:** VARIANT with structure:
- `document.pages[]` -- Page metadata (id, image_uri)
- `document.elements[]` -- Extracted content (type, content, bbox, description)
- `error_status[]` -- Error details per page
- `metadata` -- File and schema version info

**Supported Formats:** PDF, JPG/JPEG, PNG, DOC/DOCX, PPT/PPTX

**Requirements:** Databricks Runtime 17.1+, US/EU region or cross-geography routing enabled.

```sql
-- Basic document parsing
SELECT ai_parse_document(content)
FROM READ_FILES('/Volumes/catalog/schema/volume/docs/', format => 'binaryFile');

-- Parse with options (save images, version 2.0)
SELECT ai_parse_document(
  content,
  map(
    'version', '2.0',
    'imageOutputPath', '/Volumes/catalog/schema/volume/images/',
    'descriptionElementTypes', '*'
  )
)
FROM READ_FILES('/Volumes/catalog/schema/volume/invoices/', format => 'binaryFile');

-- Parse documents then extract structured data with ai_query
WITH parsed AS (
  SELECT
    path,
    ai_parse_document(content) AS doc
  FROM READ_FILES('/Volumes/catalog/schema/volume/invoices/', format => 'binaryFile')
)
SELECT
  path,
  ai_query(
    'databricks-meta-llama-3-3-70b-instruct',
    CONCAT('Extract vendor name, invoice number, and total from: ', doc:document:elements[0]:content::STRING),
    responseFormat => 'STRUCT<vendor: STRING, invoice_number: STRING, total: DOUBLE>'
  ) AS invoice_data
FROM parsed;
```

---

## Time Series AI Functions

### ai_forecast

Forecast time series data using a built-in prophet-like model. This is a table-valued function (TVF).

```sql
ai_forecast(
  observed                  TABLE,
  horizon                   DATE | TIMESTAMP | STRING,
  time_col                  STRING,
  value_col                 STRING | ARRAY<STRING>,
  group_col                 STRING | ARRAY<STRING> | NULL  DEFAULT NULL,
  prediction_interval_width DOUBLE                         DEFAULT 0.95,
  frequency                 STRING                         DEFAULT 'auto',
  seed                      INTEGER | NULL                 DEFAULT NULL,
  parameters                STRING                         DEFAULT '{}'
)
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `observed` | TABLE | Required | Training data passed as `TABLE(subquery)` or `TABLE(table_name)` |
| `horizon` | DATE/TIMESTAMP/STRING | Required | Right-exclusive forecast end time |
| `time_col` | STRING | Required | Name of DATE or TIMESTAMP column in observed data |
| `value_col` | STRING or ARRAY<STRING> | Required | One or more numeric columns to forecast |
| `group_col` | STRING, ARRAY<STRING>, or NULL | NULL | Partition column(s) for independent per-group forecasts |
| `prediction_interval_width` | DOUBLE | 0.95 | Confidence level for prediction bounds (0 to 1) |
| `frequency` | STRING | `'auto'` | Time granularity. Auto-infers from recent data. For DATE columns use: `'day'`, `'week'`, `'month'`. For TIMESTAMP columns: `'D'`, `'W'`, `'M'`, `'H'`, etc. |
| `seed` | INTEGER or NULL | NULL | Random seed for reproducibility |
| `parameters` | STRING | `'{}'` | JSON-encoded advanced settings |

**Advanced Parameters (JSON):**
- `global_cap` -- Upper bound for logistic growth
- `global_floor` -- Lower bound for logistic growth
- `daily_order` -- Fourier order for daily seasonality
- `weekly_order` -- Fourier order for weekly seasonality

### Return Columns

For each `value_col` named `v`, the output contains:
- `{v}_forecast` (DOUBLE) -- Point forecast
- `{v}_upper` (DOUBLE) -- Upper prediction bound
- `{v}_lower` (DOUBLE) -- Lower prediction bound
- Plus the original time column and group columns

**Requirements:** Serverless SQL Warehouse.

```sql
-- Basic revenue forecast
SELECT * FROM ai_forecast(
  TABLE(SELECT ds, revenue FROM catalog.schema.daily_sales),
  horizon    => '2025-12-31',
  time_col   => 'ds',
  value_col  => 'revenue'
);

-- Multi-metric forecast by group
SELECT * FROM ai_forecast(
  TABLE(
    SELECT date, zipcode, revenue, trip_count
    FROM catalog.schema.regional_metrics
  ),
  horizon                   => '2025-06-30',
  time_col                  => 'date',
  value_col                 => ARRAY('revenue', 'trip_count'),
  group_col                 => 'zipcode',
  prediction_interval_width => 0.90,
  frequency                 => 'D'
);

-- Monthly forecast with growth constraints (use 'month' for DATE columns, not 'M')
SELECT * FROM ai_forecast(
  TABLE(catalog.schema.monthly_kpis),
  horizon    => '2026-01-01',
  time_col   => 'month',
  value_col  => 'active_users',
  frequency  => 'month',
  parameters => '{"global_floor": 0}'
);
```

---

## Vector Search Function

### vector_search

Query a Mosaic AI Vector Search index using SQL. This is a table-valued function.

```sql
-- Databricks Runtime 15.3+
SELECT * FROM vector_search(
  index       => index_name,
  query_text  => search_text,         -- OR query_vector => embedding_array
  num_results => max_results,
  query_type  => 'ANN' | 'HYBRID'
)
```

### Parameters (Named Arguments Required)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `index` | STRING constant | Required | Fully qualified name of the vector search index |
| `query_text` | STRING | -- | Search string (for Delta Sync indexes with embedding source) |
| `query_vector` | ARRAY<FLOAT\|DOUBLE\|DECIMAL> | -- | Pre-computed embedding vector to search |
| `num_results` | INTEGER | 10 | Max records returned (max 100) |
| `query_type` | STRING | `'ANN'` | `'ANN'` for approximate nearest neighbor, `'HYBRID'` for hybrid search |

**Returns:** Table containing all index columns with top matching records.

**Requirements:** Serverless SQL Warehouse, Select permission on the index.

```sql
-- Text-based similarity search
SELECT * FROM vector_search(
  index      => 'catalog.schema.product_index',
  query_text => 'wireless noise canceling headphones',
  num_results => 5
);

-- Hybrid search (combines keyword + semantic)
SELECT * FROM vector_search(
  index       => 'catalog.schema.support_docs_index',
  query_text  => 'Wi-Fi connection issues with router model LMP-9R2',
  query_type  => 'HYBRID',
  num_results => 3
);

-- Vector-based search with pre-computed embedding
SELECT * FROM vector_search(
  index        => 'catalog.schema.embeddings_index',
  query_vector => ARRAY(0.45, -0.35, 0.78, 0.22),
  num_results  => 10
);

-- Batch search using LATERAL join
SELECT
  q.query_text,
  q.query_id,
  results.*
FROM catalog.schema.search_queries q,
LATERAL (
  SELECT * FROM vector_search(
    index       => 'catalog.schema.knowledge_base_index',
    query_text  => q.query_text,
    num_results => 3
  )
) AS results;
```

---

## http_request Function

Make HTTP requests to external services from SQL using Unity Catalog HTTP connections.

### Syntax

```sql
http_request(
  CONN    => connection_name,
  METHOD  => http_method,
  PATH    => path,
  HEADERS => header_map,
  PARAMS  => param_map,
  JSON    => json_body
)
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `CONN` | STRING constant | Yes | Name of an existing HTTP connection |
| `METHOD` | STRING constant | Yes | HTTP method: `'GET'`, `'POST'`, `'PUT'`, `'DELETE'`, `'PATCH'` |
| `PATH` | STRING constant | Yes | Path appended to the connection's base_path. Cannot contain directory traversal (`../`) |
| `HEADERS` | MAP<STRING, STRING> | No | Request headers. Default: NULL |
| `PARAMS` | MAP<STRING, STRING> | No | Query parameters. Default: NULL |
| `JSON` | STRING expression | No | Request body as JSON string |

### Return Type

`STRUCT<status_code: INT, text: STRING>`
- `status_code` -- HTTP response status (e.g., 200, 403, 404)
- `text` -- Response body (typically JSON)

**Requirements:** Databricks Runtime 16.2+, Unity Catalog enabled workspace, USE CONNECTION privilege.

### Creating HTTP Connections

```sql
-- Bearer token authentication
CREATE CONNECTION slack_conn TYPE HTTP
OPTIONS (
  host         'https://slack.com',
  port         '443',
  base_path    '/api/',
  bearer_token secret('my-scope', 'slack-token')
);

-- OAuth Machine-to-Machine
CREATE CONNECTION github_conn TYPE HTTP
OPTIONS (
  host           'https://api.github.com',
  port           '443',
  base_path      '/',
  client_id      secret('my-scope', 'github-client-id'),
  client_secret  secret('my-scope', 'github-client-secret'),
  oauth_scope    'repo read:org',
  token_endpoint 'https://github.com/login/oauth/access_token'
);
```

**Connection Options:**

| Option | Type | Description |
|--------|------|-------------|
| `host` | STRING | Base URL of the external service |
| `port` | STRING | Network port (typically `'443'` for HTTPS) |
| `base_path` | STRING | Root path for API endpoints |
| `bearer_token` | STRING | Auth token (use `secret()` for security) |
| `client_id` | STRING | OAuth application identifier |
| `client_secret` | STRING | OAuth application secret |
| `oauth_scope` | STRING | Space-delimited OAuth scopes |
| `token_endpoint` | STRING | OAuth token endpoint URL |
| `authorization_endpoint` | STRING | OAuth authorization redirect URL |
| `oauth_credential_exchange_method` | STRING | `'header_and_body'`, `'body_only'`, or `'header_only'` |

### Examples

```sql
-- POST a Slack message
SELECT http_request(
  CONN   => 'slack_conn',
  METHOD => 'POST',
  PATH   => '/chat.postMessage',
  JSON   => to_json(named_struct('channel', '#alerts', 'text', 'Pipeline completed successfully'))
);

-- GET request with headers and params
SELECT http_request(
  CONN    => 'github_conn',
  METHOD  => 'GET',
  PATH    => '/repos/databricks/spark/issues',
  HEADERS => map('Accept', 'application/vnd.github+json'),
  PARAMS  => map('state', 'open', 'per_page', '5')
);

-- Parse JSON response
SELECT
  response.status_code,
  from_json(response.text, 'STRUCT<id: INT, title: STRING, state: STRING>') AS issue
FROM (
  SELECT http_request(
    CONN   => 'github_conn',
    METHOD => 'GET',
    PATH   => '/repos/databricks/spark/issues/1'
  ) AS response
);

-- Webhook notification triggered by data changes
SELECT http_request(
  CONN   => 'webhook_conn',
  METHOD => 'POST',
  PATH   => '/notify',
  JSON   => to_json(named_struct(
    'event', 'data_quality_alert',
    'table', 'catalog.schema.orders',
    'message', CONCAT('Null rate exceeded threshold: ', CAST(null_pct AS STRING))
  ))
)
FROM catalog.schema.data_quality_metrics
WHERE null_pct > 0.05;
```

---

## remote_query Function (Lakehouse Federation)

Run SQL queries against external databases using their native SQL syntax, returning results as a table in Databricks SQL. This is a table-valued function.

### Overview

Lakehouse Federation enables querying external databases without migrating data. It supports two modes:
- **Query Federation** -- Queries are pushed down to external databases via JDBC
- **Catalog Federation** -- Queries access foreign tables directly in object storage

### Syntax

```sql
SELECT * FROM remote_query(
  '<connection-name>',
  <option-key> => '<option-value>'
  [, ...]
)
```

### Supported Databases

| Database | Connection Type |
|----------|----------------|
| PostgreSQL | `POSTGRESQL` |
| MySQL | `MYSQL` |
| Microsoft SQL Server | `SQLSERVER` |
| Oracle | `ORACLE` |
| Teradata | `TERADATA` |
| Amazon Redshift | `REDSHIFT` |
| Snowflake | `SNOWFLAKE` |
| Google BigQuery | `BIGQUERY` |
| Databricks | `DATABRICKS` |

### Parameters by Database Type

**PostgreSQL / MySQL / SQL Server / Redshift / Teradata:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `database` | STRING | Yes | Remote database name |
| `query` | STRING | One of query/dbtable | SQL query in the remote database's native syntax |
| `dbtable` | STRING | One of query/dbtable | Fully qualified table name |
| `fetchsize` | STRING | No | Number of rows to fetch per round trip |
| `partitionColumn` | STRING | No | Column used for parallel read partitioning |
| `lowerBound` | STRING | No | Lower bound for partition column |
| `upperBound` | STRING | No | Upper bound for partition column |
| `numPartitions` | STRING | No | Number of parallel partitions |

**Oracle (uses `service_name` instead of `database`):**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `service_name` | STRING | Yes | Oracle service name |
| `query` or `dbtable` | STRING | Yes (one required) | Query or table reference |

**Snowflake:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `database` | STRING | Yes | Snowflake database |
| `schema` | STRING | No | Schema name (defaults to `public`) |
| `query` or `dbtable` | STRING | Yes (one required) | Query or table reference |
| `query_timeout` | STRING | No | Query timeout in seconds |
| `partition_size_in_mb` | STRING | No | Partition size for reads |

**BigQuery:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` or `dbtable` | STRING | Yes (one required) | Query or table reference |
| `materializationDataset` | STRING | For views/complex queries | Dataset for materialization |
| `materializationProject` | STRING | No | GCP project for materialization |
| `parentProject` | STRING | No | Parent GCP project |

### Pushdown Control

| Option | Default | Description |
|--------|---------|-------------|
| `pushdown.limit.enabled` | `true` | Push LIMIT to remote |
| `pushdown.offset.enabled` | `true` | Push OFFSET to remote |
| `pushdown.filters.enabled` | `true` | Push WHERE filters to remote |
| `pushdown.aggregates.enabled` | `true` | Push aggregations to remote |
| `pushdown.sortLimit.enabled` | `true` | Push ORDER BY + LIMIT to remote |

### Requirements

- Unity Catalog enabled workspace
- Databricks Runtime 17.3+ (clusters) or SQL Warehouse 2025.35+ (Pro/Serverless)
- Network connectivity to target database
- `USE CONNECTION` privilege or `SELECT` on a wrapping view

### Limitations

- **Read-only**: Only SELECT queries supported (no INSERT, UPDATE, DELETE, MERGE, DDL, or stored procedures)

### Creating Connections

```sql
-- PostgreSQL connection
CREATE CONNECTION my_postgres TYPE POSTGRESQL
OPTIONS (
  host     'pg-server.example.com',
  port     '5432',
  user     secret('my-scope', 'pg-user'),
  password secret('my-scope', 'pg-password')
);

-- SQL Server connection
CREATE CONNECTION my_sqlserver TYPE SQLSERVER
OPTIONS (
  host     'sql-server.example.com',
  port     '1433',
  user     secret('my-scope', 'sql-user'),
  password secret('my-scope', 'sql-password')
);
```

### Examples

```sql
-- Basic query against PostgreSQL
SELECT * FROM remote_query(
  'my_postgres',
  database => 'sales_db',
  query    => 'SELECT customer_id, name, email FROM customers WHERE active = true'
);

-- Parallel read from SQL Server
SELECT * FROM remote_query(
  'my_sqlserver',
  database        => 'orders_db',
  dbtable         => 'dbo.transactions',
  partitionColumn => 'transaction_id',
  lowerBound      => '0',
  upperBound      => '1000000',
  numPartitions   => '10'
);

-- Join federated data with local Delta tables
SELECT
  o.order_id,
  o.amount,
  c.name,
  c.email
FROM catalog.schema.orders o
JOIN remote_query(
  'my_postgres',
  database => 'crm_db',
  query    => 'SELECT customer_id, name, email FROM customers'
) c ON o.customer_id = c.customer_id;

-- Access delegation via view
CREATE VIEW catalog.schema.federated_customers AS
SELECT * FROM remote_query(
  'my_postgres',
  database => 'crm_db',
  query    => 'SELECT customer_id, name, region FROM customers'
);

-- Users only need SELECT on the view, not USE CONNECTION
GRANT SELECT ON VIEW catalog.schema.federated_customers TO `analysts`;
```

---

## read_files Table-Valued Function

Read files from cloud storage or Unity Catalog volumes directly in SQL, with automatic format detection and schema inference.

### Syntax

```sql
SELECT * FROM read_files(
  path
  [, option_key => option_value ] [...]
)
```

### Core Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | STRING | Yes | URI of data location. Supports `s3://`, `abfss://`, `gs://`, `/Volumes/...` paths. Accepts glob patterns |

### Common Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `format` | STRING | Auto-detected | File format: `'csv'`, `'json'`, `'parquet'`, `'avro'`, `'orc'`, `'text'`, `'binaryFile'`, `'xml'` |
| `schema` | STRING | Inferred | Explicit schema definition in DDL format |
| `schemaHints` | STRING | None | Override subset of inferred schema columns |
| `rescuedDataColumn` | STRING | `'_rescued_data'` | Column name for data that could not be parsed. Set to empty string to disable |
| `pathGlobFilter` / `fileNamePattern` | STRING | None | Glob pattern to filter files (e.g., `'*.csv'`) |
| `recursiveFileLookup` | BOOLEAN | `false` | Search nested directories |
| `modifiedAfter` | TIMESTAMP STRING | None | Only read files modified after this timestamp |
| `modifiedBefore` | TIMESTAMP STRING | None | Only read files modified before this timestamp |
| `partitionColumns` | STRING | Auto-detected | Comma-separated Hive-style partition columns. Empty string ignores all partitions |
| `useStrictGlobber` | BOOLEAN | `true` | Strict glob pattern matching |
| `inferColumnTypes` | BOOLEAN | `true` | Infer exact column types (vs treating all as STRING) |
| `schemaEvolutionMode` | STRING | -- | Schema evolution behavior: `'none'` to drop rescued data column |

### CSV-Specific Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `sep` / `delimiter` | STRING | `','` | Field delimiter |
| `header` | BOOLEAN | `false` | First row contains column names |
| `encoding` | STRING | `'UTF-8'` | Character encoding |
| `quote` | STRING | `'"'` | Quote character |
| `escape` | STRING | `'\'` | Escape character |
| `nullValue` | STRING | `''` | String representation of null |
| `dateFormat` | STRING | `'yyyy-MM-dd'` | Date parsing format |
| `timestampFormat` | STRING | `'yyyy-MM-dd\'T\'HH:mm:ss...'` | Timestamp parsing format |
| `mode` | STRING | `'PERMISSIVE'` | Parse mode: `'PERMISSIVE'`, `'DROPMALFORMED'`, `'FAILFAST'` |
| `multiLine` | BOOLEAN | `false` | Allow records spanning multiple lines |
| `ignoreLeadingWhiteSpace` | BOOLEAN | `false` | Trim leading whitespace |
| `ignoreTrailingWhiteSpace` | BOOLEAN | `false` | Trim trailing whitespace |
| `comment` | STRING | None | Line comment character |
| `maxCharsPerColumn` | INTEGER | None | Max characters per column |
| `maxColumns` | INTEGER | None | Max number of columns |
| `mergeSchema` | BOOLEAN | `false` | Merge schemas across files |
| `enforceSchema` | BOOLEAN | `true` | Enforce specified schema |
| `locale` | STRING | `'US'` | Locale for number/date parsing |
| `charToEscapeQuoteEscaping` | STRING | None | Character to escape the quote escape character |
| `readerCaseSensitive` | BOOLEAN | `true` | Case-sensitive column name matching |

### JSON-Specific Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `multiLine` | BOOLEAN | `false` | Parse multi-line JSON records |
| `allowComments` | BOOLEAN | `false` | Allow Java/C++ style comments |
| `allowSingleQuotes` | BOOLEAN | `true` | Allow single quotes for strings |
| `allowUnquotedFieldNames` | BOOLEAN | `false` | Allow unquoted field names |
| `allowBackslashEscapingAnyCharacter` | BOOLEAN | `false` | Allow backslash to escape any character |
| `allowNonNumericNumbers` | BOOLEAN | `true` | Allow NaN, Infinity, -Infinity |
| `encoding` | STRING | `'UTF-8'` | Character encoding |
| `dateFormat` | STRING | `'yyyy-MM-dd'` | Date parsing format |
| `timestampFormat` | STRING | -- | Timestamp parsing format |
| `inferTimestamp` | BOOLEAN | `false` | Infer timestamp types |
| `prefersDecimal` | BOOLEAN | `false` | Prefer DECIMAL over DOUBLE |
| `primitivesAsString` | BOOLEAN | `false` | Infer all primitives as STRING |
| `singleVariantColumn` | STRING | None | Read entire JSON as single VARIANT column |
| `locale` | STRING | `'US'` | Locale for parsing |
| `mode` | STRING | `'PERMISSIVE'` | Parse mode |
| `readerCaseSensitive` | BOOLEAN | `true` | Case-sensitive column matching |
| `timeZone` | STRING | Session timezone | Timezone for timestamp parsing |

### XML-Specific Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `rowTag` | STRING | **Required** | XML tag that delimits rows |
| `attributePrefix` | STRING | `'_'` | Prefix for XML attributes |
| `valueTag` | STRING | `'_VALUE'` | Tag for element text content |
| `encoding` | STRING | `'UTF-8'` | Character encoding |
| `ignoreSurroundingSpaces` | BOOLEAN | `true` | Ignore whitespace around values |
| `ignoreNamespace` | BOOLEAN | `false` | Ignore XML namespaces |
| `mode` | STRING | `'PERMISSIVE'` | Parse mode |
| `dateFormat` | STRING | `'yyyy-MM-dd'` | Date parsing format |
| `timestampFormat` | STRING | -- | Timestamp parsing format |
| `locale` | STRING | `'US'` | Locale for parsing |
| `readerCaseSensitive` | BOOLEAN | `true` | Case-sensitive matching |
| `samplingRatio` | DOUBLE | `1.0` | Fraction of rows to sample for schema inference |

### Parquet / Avro / ORC Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `mergeSchema` | BOOLEAN | `false` | Merge schemas across files |
| `readerCaseSensitive` | BOOLEAN | `true` | Case-sensitive column matching |
| `rescuedDataColumn` | STRING | -- | Column for rescued data |
| `datetimeRebaseMode` | STRING | -- | Rebase mode for datetime values |
| `int96RebaseMode` | STRING | -- | Rebase mode for INT96 timestamps (Parquet only) |

### Streaming Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `includeExistingFiles` | BOOLEAN | `true` | Process existing files on first run |
| `maxFilesPerTrigger` | INTEGER | None | Max files per micro-batch |
| `maxBytesPerTrigger` | STRING | None | Max bytes per micro-batch |
| `allowOverwrites` | BOOLEAN | `false` | Allow processing of overwritten files |
| `schemaEvolutionMode` | STRING | -- | Schema evolution behavior |
| `schemaLocation` | STRING | -- | Location to store inferred schema |

### Requirements

- Databricks Runtime 13.3 LTS and above
- Databricks SQL

### Examples

```sql
-- Auto-detect format and schema from cloud storage
SELECT * FROM read_files('s3://my-bucket/data/');

-- Read CSV with explicit schema
SELECT * FROM read_files(
  '/Volumes/catalog/schema/volume/sales.csv',
  format => 'csv',
  header => true,
  schema => 'order_id INT, customer_id INT, amount DOUBLE, order_date DATE'
);

-- Read CSV with schema hints (override specific columns only)
SELECT * FROM read_files(
  '/Volumes/catalog/schema/volume/events/',
  format      => 'csv',
  header      => true,
  schemaHints => 'event_timestamp TIMESTAMP, amount DECIMAL(10,2)'
);

-- Read JSON with multi-line support
SELECT * FROM read_files(
  '/Volumes/catalog/schema/volume/api_responses/',
  format    => 'json',
  multiLine => true
);

-- Read Parquet with merged schema across files
SELECT * FROM read_files(
  's3://my-bucket/parquet-data/',
  format      => 'parquet',
  mergeSchema => true
);

-- Read XML with row tag
SELECT * FROM read_files(
  '/Volumes/catalog/schema/volume/feed.xml',
  format => 'xml',
  rowTag => 'record'
);

-- Read binary files (images, PDFs) for ai_parse_document
SELECT path, content FROM read_files(
  '/Volumes/catalog/schema/volume/documents/',
  format => 'binaryFile'
);

-- Filter files by glob pattern and modification date
SELECT * FROM read_files(
  's3://my-bucket/logs/',
  format          => 'json',
  pathGlobFilter  => '*.json',
  modifiedAfter   => '2025-01-01T00:00:00Z',
  modifiedBefore  => '2025-02-01T00:00:00Z'
);

-- Recursive directory scan with partition discovery
SELECT * FROM read_files(
  '/Volumes/catalog/schema/volume/partitioned_data/',
  recursiveFileLookup => true,
  partitionColumns    => 'year,month'
);

-- Include file metadata
SELECT *, _metadata.file_path, _metadata.file_name, _metadata.file_size
FROM read_files('/Volumes/catalog/schema/volume/data/');

-- Create table from files
CREATE TABLE catalog.schema.imported_data AS
SELECT * FROM read_files(
  '/Volumes/catalog/schema/volume/export.csv',
  format => 'csv',
  header => true
);

-- Streaming table from cloud storage
CREATE STREAMING TABLE catalog.schema.streaming_events AS
SELECT * FROM STREAM read_files(
  's3://my-bucket/events/',
  format              => 'json',
  includeExistingFiles => false,
  maxFilesPerTrigger   => 100
);

-- Read single VARIANT column for semi-structured JSON
SELECT * FROM read_files(
  '/Volumes/catalog/schema/volume/complex.json',
  format              => 'json',
  singleVariantColumn => 'raw_data'
);
```

---

## Combining Functions -- Production Patterns

### AI-Enhanced ETL Pipeline

```sql
-- Process customer feedback with multiple AI functions
CREATE OR REPLACE TABLE catalog.schema.enriched_feedback AS
SELECT
  feedback_id,
  feedback_text,
  ai_analyze_sentiment(feedback_text) AS sentiment,
  ai_classify(feedback_text, ARRAY('product', 'service', 'billing', 'other')) AS category,
  ai_extract(feedback_text, ARRAY('product', 'issue')) AS entities,
  ai_summarize(feedback_text, 20) AS summary,
  ai_mask(feedback_text, ARRAY('person', 'email', 'phone')) AS anonymized_text
FROM catalog.schema.raw_feedback;
```

### Document Processing Pipeline

```sql
-- Ingest, parse, and query documents
WITH raw_docs AS (
  SELECT path, content
  FROM read_files('/Volumes/catalog/schema/volume/contracts/', format => 'binaryFile')
),
parsed AS (
  SELECT path, ai_parse_document(content, map('version', '2.0')) AS doc
  FROM raw_docs
)
SELECT
  path,
  ai_query(
    'databricks-meta-llama-3-3-70b-instruct',
    CONCAT('Extract the contract parties, effective date, and termination clause from: ',
           doc:document:elements[0]:content::STRING),
    responseFormat => 'STRUCT<party_a: STRING, party_b: STRING, effective_date: STRING, termination_clause: STRING>'
  ) AS contract_info
FROM parsed;
```

### External API Integration with http_request

```sql
-- Enrich data by calling an external API and joining results
SELECT
  o.order_id,
  o.tracking_number,
  from_json(
    tracking.text,
    'STRUCT<status: STRING, location: STRING, estimated_delivery: STRING>'
  ) AS tracking_info
FROM catalog.schema.orders o
CROSS JOIN LATERAL (
  SELECT http_request(
    CONN   => 'shipping_api_conn',
    METHOD => 'GET',
    PATH   => CONCAT('/track/', o.tracking_number)
  ) AS response
) tracking
WHERE tracking.response.status_code = 200;
```

### Federated Analytics

```sql
-- Combine remote database data with local lakehouse data and AI
SELECT
  remote_orders.customer_id,
  remote_orders.total_spend,
  local_profiles.segment,
  ai_classify(
    CONCAT('Customer spent $', CAST(remote_orders.total_spend AS STRING),
           ' in segment ', local_profiles.segment),
    ARRAY('high_value', 'medium_value', 'low_value', 'at_risk')
  ) AS value_tier
FROM remote_query(
  'my_postgres',
  database => 'sales_db',
  query    => 'SELECT customer_id, SUM(amount) as total_spend FROM orders GROUP BY customer_id'
) remote_orders
JOIN catalog.schema.customer_profiles local_profiles
  ON remote_orders.customer_id = local_profiles.customer_id;
```

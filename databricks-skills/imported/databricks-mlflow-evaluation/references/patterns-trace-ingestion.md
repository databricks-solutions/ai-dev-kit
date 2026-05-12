# MLflow Trace Ingestion in Unity Catalog

Working code patterns for setting up trace storage in Unity Catalog, logging traces from applications, and enabling production monitoring.

**Version**: MLflow 3.9.0+ (`mlflow[databricks]>=3.9.0`)
**Preview**: Requires "OpenTelemetry on Databricks" preview enabled
**Regions**: Currently available in `us-east-1` and `us-west-2` only

---

## Table of Contents

| # | Pattern | Description |
|---|---------|-------------|
| 1 | [Initial Setup](#pattern-1-initial-setup---link-uc-schema-to-experiment) | Link UC schema to experiment, create tables |
| 2 | [Access Control](#pattern-2-access-control---grant-permissions) | Grant required permissions on UC tables |
| 3 | [Set Trace Destination (Python API)](#pattern-3-set-trace-destination-via-python-api) | Configure where traces are sent |
| 4 | [Set Trace Destination (Env Var)](#pattern-4-set-trace-destination-via-environment-variable) | Configure destination via env var |
| 5 | [Log Traces with @mlflow.trace](#pattern-5-log-traces-with-mlflow-decorator) | Instrument functions with decorator |
| 6 | [Log Traces with start_span](#pattern-6-log-traces-with-context-manager) | Fine-grained span control |
| 7 | [Auto-Instrumentation](#pattern-7-automatic-tracing-with-autolog) | Framework auto-tracing (OpenAI, LangChain, etc.) |
| 8 | [Combined Instrumentation](#pattern-8-combined-auto-and-manual-tracing) | Mix auto + manual tracing |
| 9 | [Traces from Databricks Apps](#pattern-9-log-traces-from-databricks-apps) | Configure app service principal |
| 10 | [Traces from Model Serving](#pattern-10-log-traces-from-model-serving-endpoints) | Configure serving endpoints |
| 11 | [Traces from OTEL Clients](#pattern-11-log-traces-from-third-party-otel-clients) | Use OpenTelemetry OTLP exporter |
| 12 | [Enable Production Monitoring](#pattern-12-enable-production-monitoring) | Register and start scorers |
| 13 | [Manage Monitoring Scorers](#pattern-13-manage-monitoring-scorers) | List, update, stop, delete scorers |
| 14 | [Query UC Trace Tables](#pattern-14-query-traces-from-unity-catalog-tables) | SQL queries on ingested traces |
| 15 | [End-to-End Setup](#pattern-15-end-to-end-setup-script) | Complete setup from scratch |

---

## Pattern 1: Initial Setup - Link UC Schema to Experiment

Create an MLflow experiment and link it to a Unity Catalog schema. This automatically creates three tables for storing trace data.

```python
import os
import mlflow
from mlflow.entities import UCSchemaLocation
from mlflow.tracing.enablement import set_experiment_trace_location

# Step 1: Configure tracking
mlflow.set_tracking_uri("databricks")
os.environ["MLFLOW_TRACING_SQL_WAREHOUSE_ID"] = "<SQL_WAREHOUSE_ID>"

# Step 2: Define names
experiment_name = "/Shared/my-agent-traces"
catalog_name = "my_catalog"
schema_name = "my_schema"

# Step 3: Create or retrieve experiment
if experiment := mlflow.get_experiment_by_name(experiment_name):
    experiment_id = experiment.experiment_id
else:
    experiment_id = mlflow.create_experiment(name=experiment_name)

# Step 4: Link UC schema to experiment
result = set_experiment_trace_location(
    location=UCSchemaLocation(
        catalog_name=catalog_name,
        schema_name=schema_name
    ),
    experiment_id=experiment_id,
)
```

**Tables created automatically:**
- `{catalog}.{schema}.mlflow_experiment_trace_otel_logs`
- `{catalog}.{schema}.mlflow_experiment_trace_otel_metrics`
- `{catalog}.{schema}.mlflow_experiment_trace_otel_spans`

**CRITICAL**: Linking a UC schema hides pre-existing experiment traces stored in MLflow. Unlinking restores access to those traces.

---

## Pattern 2: Access Control - Grant Permissions

Users and service principals need explicit permissions on the UC trace tables. `ALL_PRIVILEGES` is **not sufficient**.

```sql
-- Required: USE_CATALOG on the catalog
GRANT USE_CATALOG ON CATALOG my_catalog TO `user@company.com`;

-- Required: USE_SCHEMA on the schema
GRANT USE_SCHEMA ON SCHEMA my_catalog.my_schema TO `user@company.com`;

-- Required: MODIFY and SELECT on each trace table
GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_logs
  TO `user@company.com`;
GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_spans
  TO `user@company.com`;
GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_metrics
  TO `user@company.com`;
```

**For service principals (Databricks Apps, Model Serving):**
```sql
-- Replace with the service principal's application ID
GRANT USE_CATALOG ON CATALOG my_catalog TO `<service-principal-app-id>`;
GRANT USE_SCHEMA ON SCHEMA my_catalog.my_schema TO `<service-principal-app-id>`;
GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_logs
  TO `<service-principal-app-id>`;
GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_spans
  TO `<service-principal-app-id>`;
GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_metrics
  TO `<service-principal-app-id>`;
```

---

## Pattern 3: Set Trace Destination via Python API

Configure where traces are sent using the Python API. Use this after the initial setup (Pattern 1) in your application code.

```python
import mlflow
from mlflow.entities import UCSchemaLocation

# Set trace destination to Unity Catalog
mlflow.tracing.set_destination(
    destination=UCSchemaLocation(
        catalog_name="my_catalog",
        schema_name="my_schema",
    )
)

# Now all traces from @mlflow.trace or autolog will go to UC
@mlflow.trace
def my_agent(query: str) -> str:
    # Traces are automatically sent to UC tables
    return process(query)
```

---

## Pattern 4: Set Trace Destination via Environment Variable

Alternative to Pattern 3 — configure destination via environment variable. Useful for deployment configurations.

```python
import os

# Set destination as "{catalog}.{schema}"
os.environ["MLFLOW_TRACING_DESTINATION"] = "my_catalog.my_schema"
```

Or in shell:
```bash
export MLFLOW_TRACING_DESTINATION="my_catalog.my_schema"
```

---

## Pattern 5: Log Traces with MLflow Decorator

Use `@mlflow.trace` to instrument functions. Automatically captures inputs, outputs, latency, and exceptions.

```python
import mlflow
from mlflow.entities import SpanType

# Basic function tracing
@mlflow.trace
def my_agent(query: str) -> str:
    context = retrieve_context(query)
    return generate_response(query, context)

# With span type (enables enhanced UI and evaluation)
@mlflow.trace(span_type=SpanType.RETRIEVER)
def retrieve_context(query: str) -> list[dict]:
    """Mark retrieval functions with RETRIEVER span type."""
    return vector_store.search(query, top_k=5)

@mlflow.trace(span_type=SpanType.CHAIN)
def generate_response(query: str, context: list[dict]) -> str:
    """Mark orchestration with CHAIN span type."""
    return llm.invoke(query, context=context)

# With custom name and attributes
@mlflow.trace(name="safety_check", span_type=SpanType.TOOL)
def check_safety(text: str) -> bool:
    return safety_classifier.predict(text)
```

**Available SpanType values:**
- `SpanType.CHAIN` — Orchestration / pipeline steps
- `SpanType.CHAT_MODEL` — LLM chat completions
- `SpanType.LLM` — LLM calls (non-chat)
- `SpanType.RETRIEVER` — Document/data retrieval (special output schema)
- `SpanType.TOOL` — Tool/function execution
- `SpanType.AGENT` — Agent execution
- `SpanType.EMBEDDING` — Embedding generation

---

## Pattern 6: Log Traces with Context Manager

Use `mlflow.start_span()` for fine-grained control over spans. Manually set inputs, outputs, and attributes.

```python
import mlflow

def process_query(query: str) -> str:
    # Create a span with manual control
    with mlflow.start_span(name="process_query") as span:
        span.set_inputs({"query": query})

        # Nested span for retrieval
        with mlflow.start_span(name="retrieve", span_type="RETRIEVER") as retriever_span:
            retriever_span.set_inputs({"query": query})
            docs = vector_store.search(query)
            retriever_span.set_outputs(docs)

        # Nested span for generation
        with mlflow.start_span(name="generate", span_type="CHAIN") as gen_span:
            gen_span.set_inputs({"query": query, "doc_count": len(docs)})
            response = llm.generate(query, docs)
            gen_span.set_outputs({"response": response})

        # Set attributes for analysis
        span.set_attribute("doc_count", len(docs))
        span.set_attribute("model", "gpt-4o")
        span.set_outputs({"response": response})

    return response
```

---

## Pattern 7: Automatic Tracing with Autolog

Enable automatic tracing for supported frameworks. MLflow captures LLM calls, tool executions, and chain operations without code changes.

```python
import mlflow

# Enable auto-tracing for specific frameworks
mlflow.openai.autolog()        # OpenAI SDK calls
mlflow.langchain.autolog()     # LangChain chains and agents
# Also available: mlflow.anthropic.autolog(), mlflow.litellm.autolog(), etc.

# Set tracking and destination
mlflow.set_tracking_uri("databricks")
mlflow.set_experiment("/Shared/my-agent-traces")

# Traces are captured automatically
from openai import OpenAI
client = OpenAI()

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is MLflow?"}
    ]
)
# ^ This call is automatically traced
```

**20+ supported frameworks** including:
- OpenAI, Anthropic, Google GenAI
- LangChain, LlamaIndex, DSPy
- LiteLLM, Ollama, Bedrock
- CrewAI, AutoGen, Haystack

---

## Pattern 8: Combined Auto and Manual Tracing

Combine automatic framework tracing with manual decorators for complete coverage.

```python
import mlflow
from mlflow.entities import SpanType
from openai import OpenAI

# Enable automatic OpenAI tracing
mlflow.openai.autolog()

client = OpenAI()

@mlflow.trace(span_type=SpanType.CHAIN)
def my_rag_pipeline(query: str) -> str:
    """Manual decorator wraps the whole pipeline.
    Auto-tracing captures individual OpenAI calls inside."""

    # This retrieval is manually traced
    docs = retrieve_documents(query)

    # This LLM call is auto-traced by mlflow.openai.autolog()
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": f"Answer using context: {docs}"},
            {"role": "user", "content": query}
        ]
    )
    return response.choices[0].message.content

@mlflow.trace(span_type=SpanType.RETRIEVER)
def retrieve_documents(query: str) -> list[dict]:
    """Manually traced retrieval function."""
    return vector_store.search(query, top_k=5)
```

---

## Pattern 9: Log Traces from Databricks Apps

Configure a Databricks App to send traces to Unity Catalog.

**Prerequisites:**
- App uses `mlflow[databricks]>=3.5.0`
- App's service principal has MODIFY and SELECT on the trace tables (see Pattern 2)

**In your app code:**
```python
import os
import mlflow
from mlflow.entities import UCSchemaLocation

# Option A: Python API
mlflow.tracing.set_destination(
    destination=UCSchemaLocation(
        catalog_name="my_catalog",
        schema_name="my_schema",
    )
)

# Option B: Environment variable (set in app config)
os.environ["MLFLOW_TRACING_DESTINATION"] = "my_catalog.my_schema"

# Your app code — traces are sent to UC
@mlflow.trace
def handle_request(query: str) -> str:
    return my_agent.invoke(query)
```

**Deployment steps:**
1. Locate the app's service principal under the **Authorization** tab
2. Grant MODIFY and SELECT on the three `mlflow_experiment_trace_*` tables
3. Configure the trace destination in your app code
4. Deploy the app

---

## Pattern 10: Log Traces from Model Serving Endpoints

Configure a model serving endpoint to send traces to Unity Catalog.

**Step 1: Grant permissions to user/service principal**
```sql
GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_logs
  TO `serving-principal-id`;
GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_spans
  TO `serving-principal-id`;
```

**Step 2: Generate a Personal Access Token (PAT)**

Create a PAT for the identity that has the permissions above.

**Step 3: Add environment variables to the endpoint**

Add these to the serving endpoint configuration:
```
DATABRICKS_TOKEN=<your-personal-access-token>
MLFLOW_TRACING_DESTINATION=my_catalog.my_schema
```

**Step 4: In your served model code, configure the destination**
```python
import os
import mlflow
from mlflow.entities import UCSchemaLocation

mlflow.tracing.set_destination(
    destination=UCSchemaLocation(
        catalog_name="my_catalog",
        schema_name="my_schema",
    )
)

# Your model's predict function — traces go to UC
@mlflow.trace
def predict(model_input):
    return my_model.invoke(model_input)
```

---

## Pattern 11: Log Traces from Third-Party OTEL Clients

Send traces from any OpenTelemetry-compatible client to Unity Catalog via the OTLP HTTP endpoint.

```python
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Configure OTLP exporter pointing to Databricks
otlp_trace_exporter = OTLPSpanExporter(
    endpoint="https://<workspace-url>/api/2.0/otel/v1/traces",
    headers={
        "content-type": "application/x-protobuf",
        "X-Databricks-UC-Table-Name": "my_catalog.my_schema.mlflow_experiment_trace_otel_spans",
        "Authorization": "Bearer <YOUR_API_TOKEN>",
    },
)

# Set up the tracer provider
provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(otlp_trace_exporter))

# Use standard OpenTelemetry APIs to create spans
tracer = provider.get_tracer("my-application")
with tracer.start_as_current_span("my-operation") as span:
    span.set_attribute("query", "What is MLflow?")
    result = process_query("What is MLflow?")
    span.set_attribute("result_length", len(result))
```

**Notes:**
- Traces ingested via OTEL appear in linked experiments if they contain a root span
- Use the `X-Databricks-UC-Table-Name` header to specify the target spans table
- Standard OTEL instrumentation libraries work with this endpoint

---

## Pattern 12: Enable Production Monitoring

Register scorers to continuously evaluate traces in production. Scorers run asynchronously on sampled traces.

```python
import mlflow
from mlflow.genai.scorers import Safety, Guidelines, ScorerSamplingConfig
from mlflow.tracing import set_databricks_monitoring_sql_warehouse_id

# Step 1: Configure the SQL warehouse for monitoring
set_databricks_monitoring_sql_warehouse_id(
    warehouse_id="<SQL_WAREHOUSE_ID>",
    experiment_id="<EXPERIMENT_ID>"  # Optional — uses active experiment if omitted
)

# Step 2: Set the active experiment
mlflow.set_experiment("/Shared/my-agent-traces")

# Step 3: Register and start scorers

# Safety scorer — evaluate 100% of traces
safety = Safety().register(name="production_safety")
safety = safety.start(
    sampling_config=ScorerSamplingConfig(sample_rate=1.0)
)

# Custom guidelines — evaluate 50% of traces
tone_check = Guidelines(
    name="professional_tone",
    guidelines="The response must be professional and helpful"
).register(name="production_tone")
tone_check = tone_check.start(
    sampling_config=ScorerSamplingConfig(sample_rate=0.5)
)
```

**CRITICAL**: You must both `.register()` AND `.start()` — registering alone does not activate monitoring.

**SQL Warehouse requirements:**
- User must have `CAN USE` on the SQL warehouse
- User must have `CAN EDIT` on the experiment
- Monitoring job permissions are auto-granted on first scorer registration

---

## Pattern 13: Manage Monitoring Scorers

List, update, stop, and delete production monitoring scorers.

```python
from mlflow.genai.scorers import list_scorers, get_scorer, delete_scorer, ScorerSamplingConfig

# List all registered scorers for the active experiment
scorers = list_scorers()
for s in scorers:
    print(f"  {s.name}: sample_rate={s.sampling_config.sample_rate if s.sampling_config else 'N/A'}")

# Get a specific scorer
safety_scorer = get_scorer(name="production_safety")

# Update sample rate (e.g., increase from 50% to 80%)
safety_scorer = safety_scorer.update(
    sampling_config=ScorerSamplingConfig(sample_rate=0.8)
)

# Stop monitoring (keeps registration for later re-start)
safety_scorer = safety_scorer.stop()

# Re-start monitoring
safety_scorer = safety_scorer.start(
    sampling_config=ScorerSamplingConfig(sample_rate=0.5)
)

# Delete entirely (removes registration)
delete_scorer(name="production_safety")
```

---

## Pattern 14: Query Traces from Unity Catalog Tables

Query ingested traces directly using SQL for custom analysis and dashboards.

```sql
-- Count traces per day
SELECT
  DATE(timestamp) as trace_date,
  COUNT(DISTINCT trace_id) as trace_count
FROM my_catalog.my_schema.mlflow_experiment_trace_otel_spans
WHERE parent_span_id IS NULL  -- root spans only
GROUP BY DATE(timestamp)
ORDER BY trace_date DESC;

-- Find slow traces (root span duration > 10s)
SELECT
  trace_id,
  name as root_span_name,
  (end_time_unix_nano - start_time_unix_nano) / 1e9 as duration_seconds
FROM my_catalog.my_schema.mlflow_experiment_trace_otel_spans
WHERE parent_span_id IS NULL
  AND (end_time_unix_nano - start_time_unix_nano) / 1e9 > 10
ORDER BY duration_seconds DESC
LIMIT 20;

-- Error rate by span name
SELECT
  name,
  COUNT(*) as total,
  SUM(CASE WHEN status_code = 'ERROR' THEN 1 ELSE 0 END) as errors,
  ROUND(SUM(CASE WHEN status_code = 'ERROR' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as error_pct
FROM my_catalog.my_schema.mlflow_experiment_trace_otel_spans
GROUP BY name
HAVING COUNT(*) > 10
ORDER BY error_pct DESC;
```

**From Python (via Spark):**
```python
from databricks.connect import DatabricksSession

spark = DatabricksSession.builder.remote(serverless=True).getOrCreate()

# Query trace spans
spans_df = spark.sql("""
    SELECT trace_id, name, span_kind,
           (end_time_unix_nano - start_time_unix_nano) / 1e6 as duration_ms
    FROM my_catalog.my_schema.mlflow_experiment_trace_otel_spans
    WHERE name LIKE '%retriever%'
    ORDER BY duration_ms DESC
    LIMIT 100
""")
spans_df.show()
```

---

## Pattern 15: End-to-End Setup Script

Complete setup script for a new project — from creating the UC schema link to logging the first trace and enabling monitoring.

```python
import os
import mlflow
from mlflow.entities import UCSchemaLocation
from mlflow.tracing.enablement import set_experiment_trace_location
from mlflow.tracing import set_databricks_monitoring_sql_warehouse_id
from mlflow.genai.scorers import Safety, Guidelines, ScorerSamplingConfig

# ============================================================
# Configuration — UPDATE THESE VALUES
# ============================================================
EXPERIMENT_NAME = "/Shared/my-agent-traces"
CATALOG_NAME = "my_catalog"
SCHEMA_NAME = "my_schema"
SQL_WAREHOUSE_ID = "abc123def456"  # Your SQL warehouse ID

# ============================================================
# Step 1: Initial Setup
# ============================================================
mlflow.set_tracking_uri("databricks")
os.environ["MLFLOW_TRACING_SQL_WAREHOUSE_ID"] = SQL_WAREHOUSE_ID

# Create or retrieve experiment
if experiment := mlflow.get_experiment_by_name(EXPERIMENT_NAME):
    experiment_id = experiment.experiment_id
else:
    experiment_id = mlflow.create_experiment(name=EXPERIMENT_NAME)

# Link UC schema (creates trace tables automatically)
set_experiment_trace_location(
    location=UCSchemaLocation(
        catalog_name=CATALOG_NAME,
        schema_name=SCHEMA_NAME
    ),
    experiment_id=experiment_id,
)
print(f"Linked experiment '{EXPERIMENT_NAME}' to {CATALOG_NAME}.{SCHEMA_NAME}")

# ============================================================
# Step 2: Set Trace Destination
# ============================================================
mlflow.set_experiment(EXPERIMENT_NAME)
mlflow.tracing.set_destination(
    destination=UCSchemaLocation(
        catalog_name=CATALOG_NAME,
        schema_name=SCHEMA_NAME,
    )
)

# ============================================================
# Step 3: Enable Production Monitoring
# ============================================================
set_databricks_monitoring_sql_warehouse_id(
    warehouse_id=SQL_WAREHOUSE_ID,
    experiment_id=experiment_id,
)

# Register and start safety monitoring (100% of traces)
safety = Safety().register(name="safety_monitor")
safety = safety.start(
    sampling_config=ScorerSamplingConfig(sample_rate=1.0)
)
print("Safety monitoring enabled (100% sample rate)")

# Register and start custom guidelines (50% of traces)
tone = Guidelines(
    name="professional_tone",
    guidelines="The response must be professional, helpful, and concise"
).register(name="tone_monitor")
tone = tone.start(
    sampling_config=ScorerSamplingConfig(sample_rate=0.5)
)
print("Tone monitoring enabled (50% sample rate)")

# ============================================================
# Step 4: Verify with a Test Trace
# ============================================================
@mlflow.trace
def test_agent(query: str) -> str:
    return f"Test response to: {query}"

result = test_agent("Hello, is tracing working?")
print(f"Test trace logged. Check the Experiments UI at: {EXPERIMENT_NAME}")
```

---

## Limitations & Quotas

| Limit | Value |
|-------|-------|
| Trace ingestion rate | 100 traces/second per workspace |
| Table ingestion throughput | 100 MB/second per table |
| Query throughput | 200 queries/second |
| UI performance | Degrades with >2TB of data |
| Trace deletion | Individual deletion not supported (use SQL) |
| MLflow MCP server | Does not support UC-stored traces |
| Region availability | `us-east-1` and `us-west-2` only (Beta) |

---

## Viewing Traces in the UI

1. Navigate to the **Experiments** page in your Databricks workspace
2. Select your experiment
3. Click the **Traces** tab
4. Select a **SQL warehouse** from the dropdown to query UC-stored traces
5. Browse traces, inspect spans, view inputs/outputs

**Note:** You must select a SQL warehouse to view UC-stored traces — they are not loaded automatically.

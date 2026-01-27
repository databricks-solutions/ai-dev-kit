---
name: spark-declarative-pipelines
description: "Creates, configures, and updates Databricks Lakeflow Spark Declarative Pipelines (SDP/LDP) using serverless compute. Handles streaming tables, materialized views, CDC, SCD Type 2, and Auto Loader ingestion patterns. Use when building data pipelines, working with Delta Live Tables, ingesting streaming data, implementing change data capture, or when the user mentions SDP, LDP, DLT, Lakeflow pipelines, streaming tables, or bronze/silver/gold medallion architectures."
---

# Lakeflow Spark Declarative Pipelines (SDP)

## Quick Reference

| Concept | Details |
|---------|---------|
| **Names** | SDP = Spark Declarative Pipelines = LDP = Lakeflow Declarative Pipelines = Lakeflow Pipelines (all interchangeable) |
| **Python Import** | `from pyspark import pipelines as dp` |
| **Primary Decorators** | `@dp.table()`, `@dp.materialized_view()` |
| **Replaces** | Delta Live Tables (DLT) with `import dlt` |
| **Based On** | Apache Spark 4.1+ (Databricks' modern data pipeline framework) |
| **Docs** | https://docs.databricks.com/aws/en/ldp/developer/python-dev |

---

## Official Documentation

- **[Lakeflow Spark Declarative Pipelines Overview](https://docs.databricks.com/aws/en/ldp/)** - Main documentation hub
- **[SQL Language Reference](https://docs.databricks.com/aws/en/ldp/developer/sql-dev)** - SQL syntax for streaming tables and materialized views
- **[Python Language Reference](https://docs.databricks.com/aws/en/ldp/developer/python-ref)** - `pyspark.pipelines` API
- **[Loading Data](https://docs.databricks.com/aws/en/ldp/load)** - Auto Loader, Kafka, Kinesis ingestion
- **[Change Data Capture (CDC)](https://docs.databricks.com/aws/en/ldp/cdc)** - AUTO CDC, SCD Type 1/2
- **[Developing Pipelines](https://docs.databricks.com/aws/en/ldp/develop)** - File structure, testing, validation
- **[Liquid Clustering](https://docs.databricks.com/aws/en/delta/clustering)** - Modern data layout optimization

---

## Quick Start: Initialize New Pipeline Project

**RECOMMENDED**: Use `databricks pipelines init` to create production-ready Asset Bundle projects with multi-environment support.

### When to Use Bundle Initialization

Use bundle initialization for **New pipeline projects** for a professional structure from the start

Use manual workflow for:
- Quick prototyping without multi-environment needs
- Existing manual projects you want to continue
- Learning/experimentation

### Step 1: Initialize Project

I will automatically run this command when you request a new pipeline:

```bash
databricks pipelines init
```

**Interactive Prompts:**
- **Project name**: e.g., `customer_orders_pipeline`
- **Initial catalog**: Unity Catalog name (e.g., `main`, `prod_catalog`)
- **Personal schema per user?**: `yes` for dev (each user gets their own schema), `no` for prod
- **Language**: SQL or Python (auto-detected from your request - see language detection below)

**Generated Structure:**
```
my_pipeline/
├── databricks.yml              # Multi-environment config (dev/prod)
├── resources/
│   └── *_etl.pipeline.yml      # Pipeline resource definition
└── src/
    └── *_etl/
        ├── explorations/       # Exploratory code in .ipynb
        └── transformations/    # Your .sql or .py files here
```

### Step 2: Customize Transformations

Replace the example code created by the init process with custom transformation files in `src/transformations/` based on provided requirements, using best practice guidance from this skill.


### Step 3: Deploy and Run

```bash
# Deploy to workspace (dev by default)
databricks bundle deploy

# Run pipeline
databricks bundle run my_pipeline_etl

# Deploy to production
databricks bundle deploy --target prod
```

I can run these commands for you using the Bash tool.

**For medallion architecture** (bronze/silver/gold), two approaches work:
- **Flat with naming** (template default): `bronze_*.sql`, `silver_*.sql`, `gold_*.sql`
- **Subdirectories**: `bronze/orders.sql`, `silver/cleaned.sql`, `gold/summary.sql`

Both work with the `transformations/**` glob pattern. Choose based on preference.

See **[8-project-initialization.md](8-project-initialization.md)** for complete details on bundle initialization, migration, and troubleshooting.

---

## Alternative: Manual Workflow (Advanced)

For rapid prototyping, experimentation, or when you prefer direct control without Asset Bundles, use the manual workflow with MCP tools.

Use MCP tools to create, run, and iterate on **serverless SDP pipelines**. The **primary tool is `create_or_update_pipeline`** which handles the entire lifecycle.

**IMPORTANT: Always create serverless pipelines (default).** Only use classic clusters if user explicitly requires R language, Spark RDD APIs, or JAR libraries.

### Step 1: Write Pipeline Files Locally

Create `.sql` or `.py` files in a local folder:

```
my_pipeline/
├── bronze/
│   ├── ingest_orders.sql       # SQL (default for most cases)
│   └── ingest_events.py        # Python (for complex logic)
├── silver/
│   └── clean_orders.sql
└── gold/
    └── daily_summary.sql
```

**SQL Example** (`bronze/ingest_orders.sql`):
```sql
CREATE OR REFRESH STREAMING TABLE bronze_orders
CLUSTER BY (order_date)
AS
SELECT
  *,
  current_timestamp() AS _ingested_at,
  _metadata.file_path AS _source_file
FROM read_files(
  '/Volumes/catalog/schema/raw/orders/',
  format => 'json',
  schemaHints => 'order_id STRING, customer_id STRING, amount DECIMAL(10,2), order_date DATE'
);
```

**Python Example** (`bronze/ingest_events.py`):
```python
from pyspark import pipelines as dp
from pyspark.sql.functions import col, current_timestamp

@dp.table(name="bronze_events", cluster_by=["event_date"])
def bronze_events():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .load("/Volumes/catalog/schema/raw/events/")
        .withColumn("_ingested_at", current_timestamp())
        .withColumn("_source_file", col("_metadata.file_path"))
    )
```

**Language Selection:**
- **Auto-detection**: I analyze your request for keywords:
  - **SQL indicators**: "SQL", "sql files", "simple transformations", "aggregations", "materialized view", "CREATE OR REFRESH"
  - **Python indicators**: "Python", ".py files", "UDF", "complex logic", "ML inference", "external API", "@dp.table", "pandas"
- **Prompt for clarification** when language intent is unclear or mixed
- **Use SQL** for: Transformations, aggregations, filtering, joins (most cases)
- **Generate ONE language** per request unless you explicitly ask for mixed pipeline

See **[8-project-initialization.md](8-project-initialization.md)** for detailed language detection logic.

### Step 2: Upload to Databricks Workspace

```python
# MCP Tool: upload_folder
upload_folder(
    local_folder="/path/to/my_pipeline",
    workspace_folder="/Workspace/Users/user@example.com/my_pipeline"
)
```

### Step 3: Create/Update and Run Pipeline

Use **`create_or_update_pipeline`** - the main entry point. It:
1. Searches for an existing pipeline with the same name (or uses `id` from `extra_settings`)
2. Creates a new pipeline or updates the existing one
3. Optionally starts a pipeline run
4. Optionally waits for completion and returns detailed results

```python
# MCP Tool: create_or_update_pipeline
result = create_or_update_pipeline(
    name="my_orders_pipeline",
    root_path="/Workspace/Users/user@example.com/my_pipeline",
    catalog="my_catalog",
    schema="my_schema",
    workspace_file_paths=[
        "/Workspace/Users/user@example.com/my_pipeline/bronze/ingest_orders.sql",
        "/Workspace/Users/user@example.com/my_pipeline/silver/clean_orders.sql",
        "/Workspace/Users/user@example.com/my_pipeline/gold/daily_summary.sql"
    ],
    start_run=True,           # Start immediately
    wait_for_completion=True, # Wait and return final status
    full_refresh=True,        # Full refresh all tables
    timeout=1800              # 30 minute timeout
)
```

**Result contains actionable information:**
```python
{
    "success": True,                    # Did the operation succeed?
    "pipeline_id": "abc-123",           # Pipeline ID for follow-up operations
    "pipeline_name": "my_orders_pipeline",
    "created": True,                    # True if new, False if updated
    "state": "COMPLETED",               # COMPLETED, FAILED, TIMEOUT, etc.
    "catalog": "my_catalog",            # Target catalog
    "schema": "my_schema",              # Target schema
    "duration_seconds": 45.2,           # Time taken
    "message": "Pipeline created and completed successfully in 45.2s. Tables written to my_catalog.my_schema",
    "error_message": None,              # Error summary if failed
    "errors": []                        # Detailed error list if failed
}
```

### Step 4: Handle Results

**On Success:**
```python
if result["success"]:
    # Verify output tables
    stats = get_table_details(
        catalog="my_catalog",
        schema="my_schema",
        table_names=["bronze_orders", "silver_orders", "gold_daily_summary"]
    )
```

**On Failure:**
```python
if not result["success"]:
    # Message includes suggested next steps
    print(result["message"])
    # "Pipeline created but run failed. State: FAILED. Error: Column 'amount' not found.
    #  Use get_pipeline_events(pipeline_id='abc-123') for full details."

    # Get detailed errors
    events = get_pipeline_events(pipeline_id=result["pipeline_id"], max_results=50)
```

### Step 5: Iterate Until Working

1. Review errors from result or `get_pipeline_events`
2. Fix issues in local files
3. Re-upload with `upload_folder`
4. Run `create_or_update_pipeline` again (it will update, not recreate)
5. Repeat until `result["success"] == True`

---

## Quick Reference: MCP Tools

### Primary Tool

| Tool | Description |
|------|-------------|
| **`create_or_update_pipeline`** | **Main entry point.** Creates or updates pipeline, optionally runs and waits. Returns detailed status with `success`, `state`, `errors`, and actionable `message`. |

### Pipeline Management

| Tool | Description |
|------|-------------|
| `find_pipeline_by_name` | Find existing pipeline by name, returns pipeline_id |
| `get_pipeline` | Get pipeline configuration and current state |
| `start_update` | Start pipeline run (`validate_only=True` for dry run) |
| `get_update` | Poll update status (QUEUED, RUNNING, COMPLETED, FAILED) |
| `stop_pipeline` | Stop a running pipeline |
| `get_pipeline_events` | Get error messages for debugging failed runs |
| `delete_pipeline` | Delete a pipeline |

### Supporting Tools

| Tool | Description |
|------|-------------|
| `upload_folder` | Upload local folder to workspace (parallel) |
| `get_table_details` | Verify output tables have expected schema and row counts |
| `execute_sql` | Run ad-hoc SQL to inspect data |

---

## Reference Documentation (Local)

Load these for detailed patterns:

- **[1-ingestion-patterns.md](1-ingestion-patterns.md)** - Auto Loader, Kafka, Event Hub, Kinesis, file formats
- **[2-streaming-patterns.md](2-streaming-patterns.md)** - Deduplication, windowing, stateful operations, joins
- **[3-scd-patterns.md](3-scd-patterns.md)** - Querying SCD Type 2 history tables, temporal joins
- **[4-performance-tuning.md](4-performance-tuning.md)** - Liquid Clustering, optimization, state management
- **[5-python-api.md](5-python-api.md)** - Modern `dp` API vs legacy `dlt` API comparison
- **[6-dlt-migration.md](6-dlt-migration.md)** - Migrating existing DLT pipelines to SDP
- **[7-advanced-configuration.md](7-advanced-configuration.md)** - `extra_settings` parameter reference and examples
- **[8-project-initialization.md](8-project-initialization.md)** - Using `databricks pipelines init`, Asset Bundles, language detection, and migration guides

---

## Best Practices (2025)

### Project Structure
- **Default to `databricks pipelines init`** for new projects (creates Asset Bundle)
- **Use Asset Bundles** for multi-environment deployments (dev/staging/prod)
- **Manual structure only** for quick prototypes or legacy migration
- **Medallion architecture**: Two approaches work with Asset Bundles:
  - **Flat structure** (template default): `bronze_*.sql`, `silver_*.sql`, `gold_*.sql` in `transformations/`
  - **Subdirectories**: `transformations/bronze/`, `transformations/silver/`, `transformations/gold/`
  - Both work with the `transformations/**` glob pattern - choose based on team preference
- See **[8-project-initialization.md](8-project-initialization.md)** for project setup details


### Modern Defaults
- **CLUSTER BY** (Liquid Clustering), not PARTITION BY - see [4-performance-tuning.md](4-performance-tuning.md)
- **Raw `.sql`/`.py` files**, not notebooks
- **Serverless compute ONLY** - Do not use classic clusters unless explicitly required
- **Unity Catalog** (required for serverless)
- **read_files()** for cloud storage ingestion - see [1-ingestion-patterns.md](1-ingestion-patterns.md)

### Reading Tables in Python

**Modern SDP Best Practice:**
- Use `spark.read.table()` for batch reads
- Use `spark.readStream.table()` for streaming reads
- Don't use `dp.read()` or `dp.read_stream()` (old syntax, no longer documented)
- Don't use `dlt.read()` or `dlt.read_stream()` (legacy DLT API)

**Key Point:** SDP automatically tracks table dependencies from standard Spark DataFrame operations. No special read APIs are needed.

#### Three-Tier Identifier Resolution

SDP supports three levels of table name qualification:

| Level | Syntax | When to Use |
|-------|--------|-------------|
| **Unqualified** | `spark.read.table("my_table")` | Reading tables within the same pipeline's target catalog/schema (recommended) |
| **Partially-qualified** | `spark.read.table("other_schema.my_table")` | Reading from different schema in same catalog |
| **Fully-qualified** | `spark.read.table("other_catalog.other_schema.my_table")` | Reading from external catalogs/schemas |

#### Option 1: Unqualified Names (Recommended for Pipeline Tables)

**Best practice for tables within the same pipeline.** SDP resolves unqualified names to the pipeline's configured target catalog and schema. This makes code portable across environments (dev/prod).

```python
@dp.table(name="silver_clean")
def silver_clean():
    # Reads from pipeline's target catalog/schema (e.g., dev_catalog.dev_schema.bronze_raw)
    return (
        spark.read.table("bronze_raw")
        .filter(F.col("valid") == True)
    )

@dp.table(name="silver_events")
def silver_events():
    # Streaming read from same pipeline's bronze_events table
    return (
        spark.readStream.table("bronze_events")
        .withColumn("processed_at", F.current_timestamp())
    )
```

#### Option 2: Pipeline Parameters (For External Sources)

**Use `spark.conf.get()` to parameterize external catalog/schema references.** Define parameters in pipeline configuration, then reference them at the module level.

```python
from pyspark import pipelines as dp
from pyspark.sql import functions as F

# Get parameterized values at module level (evaluated once at pipeline start)
source_catalog = spark.conf.get("source_catalog")
source_schema = spark.conf.get("source_schema", "sales")  # with default

@dp.table(name="transaction_summary")
def transaction_summary():
    return (
        spark.read.table(f"{source_catalog}.{source_schema}.transactions")
        .groupBy("account_id")
        .agg(
            F.count("txn_id").alias("txn_count"),
            F.sum("txn_amount").alias("account_revenue")
        )
    )
```

**Configure parameters in pipeline settings:**
- **Asset Bundles**: Add to `pipeline.yml` under `configuration:`
- **Manual/MCP**: Pass via `extra_settings.configuration` dict

```yaml
# In resources/my_pipeline.pipeline.yml
configuration:
  source_catalog: "shared_catalog"
  source_schema: "sales"
```

#### Option 3: Fully-Qualified Names (For Fixed External References)

Use when referencing specific external tables that don't change across environments:

```python
@dp.table(name="enriched_orders")
def enriched_orders():
    # Pipeline-internal table (unqualified)
    orders = spark.read.table("bronze_orders")

    # External reference table (fully-qualified)
    products = spark.read.table("shared_catalog.reference.products")

    return orders.join(products, "product_id")
```

#### Choosing the Right Approach

| Scenario | Recommended Approach |
|----------|---------------------|
| Reading tables created in same pipeline | **Unqualified names** - portable, uses target catalog/schema |
| Reading from external source that varies by environment | **Pipeline parameters** - configurable per deployment |
| Reading from shared/reference tables with fixed location | **Fully-qualified names** - explicit and clear |
| Mixed pipeline (some internal, some external) | **Combine approaches** - unqualified for internal, parameters for external |

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **Empty output tables** | Use `get_table_details` to verify, check upstream sources |
| **Pipeline stuck INITIALIZING** | Normal for serverless, wait a few minutes |
| **"Column not found"** | Check `schemaHints` match actual data |
| **Streaming reads fail** | Use `FROM STREAM(table)` for streaming sources |
| **Timeout during run** | Increase `timeout`, or use `wait_for_completion=False` and poll with `get_update` |
| **MV doesn't refresh** | Enable row tracking on source tables |
| **SCD2 schema errors** | Let SDP infer START_AT/END_AT columns |

**For detailed errors**, the `result["message"]` from `create_or_update_pipeline` includes suggested next steps. Use `get_pipeline_events(pipeline_id=...)` for full stack traces.

---

## Advanced Pipeline Configuration

For advanced configuration options (development mode, continuous pipelines, custom clusters, notifications, Python dependencies, etc.), see **[7-advanced-configuration.md](7-advanced-configuration.md)**.

---

## Platform Constraints

### Serverless Pipeline Requirements (Default)
| Requirement | Details |
|-------------|---------|
| **Unity Catalog** | Required - serverless pipelines always use UC |
| **Workspace Region** | Must be in serverless-enabled region |
| **Serverless Terms** | Must accept serverless terms of use |
| **CDC Features** | Requires serverless (or Pro/Advanced with classic clusters) |

### Serverless Limitations (When Classic Clusters Required)
| Limitation | Workaround |
|------------|-----------|
| **R language** | Not supported - use classic clusters if required |
| **Spark RDD APIs** | Not supported - use classic clusters if required |
| **JAR libraries** | Not supported - use classic clusters if required |
| **Maven coordinates** | Not supported - use classic clusters if required |
| **DBFS root access** | Limited - must use Unity Catalog external locations |
| **Global temp views** | Not supported |

### General Constraints
| Constraint | Details |
|------------|---------|
| **Schema Evolution** | Streaming tables require full refresh for incompatible changes |
| **SQL Limitations** | PIVOT clause unsupported |
| **Sinks** | Python only, streaming only, append flows only |

**Default to serverless** unless user explicitly requires R, RDD APIs, or JAR libraries.
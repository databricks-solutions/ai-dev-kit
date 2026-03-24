---
name: databricks-spark-declarative-pipelines
description: "Creates, configures, and updates Databricks Lakeflow Spark Declarative Pipelines (SDP/LDP) using serverless compute. Handles streaming tables, materialized views, CDC, SCD Type 2, and Auto Loader ingestion patterns. Use when building data pipelines, working with Delta Live Tables, ingesting streaming data, implementing change data capture, or when the user mentions SDP, LDP, DLT, Lakeflow pipelines, streaming tables, or bronze/silver/gold medallion architectures."
---

# Lakeflow Spark Declarative Pipelines (SDP)

---

## Critical Rules (always follow)
- **MUST** confirm language as Python or SQL. Stick with that language unless told otherwise.
- **MUST** create serverless pipelines by default. Only use classic clusters if user explicitly requires R language, Spark RDD APIs, or JAR libraries.
- **MUST** choose the right workflow based on context (see below).

## Choose Your Workflow

**First, determine which workflow to use:**

### Option A: Standalone Pipeline Project (use `databricks pipelines init`)

Use this when the user wants to **create a new, standalone SDP project** that will have its own Asset Bundle:
- User asks: "Create a new pipeline project", "Build me an SDP from scratch", "Set up a new data pipeline"
- No existing `databricks.yml` in the workspace
- The pipeline IS the project (not part of a larger demo/app)

→ See [Standalone Pipeline with Asset Bundle](#standalone-pipeline-with-asset-bundle) below

### Option B: Pipeline within Existing Bundle (edit the bundle)

Use this when the pipeline is **part of an existing Databricks Asset Bundle project**:
- There's already a `databricks.yml` file in the project
- User is adding a pipeline to an existing app/demo

→ See [8-project-initialization.md](8-project-initialization.md) for adding pipelines to existing bundles

### Option C: Rapid Iteration with MCP Tools (no bundle management)

Use this when you need to **quickly create, test, and iterate** on a pipeline without managing bundle files:
- User wants to "just run a pipeline and see if it works"
- Part of a larger demo where bundle is managed separately, or the DAB bundle will be created at the end as you want to quickly test the project first
- Prototyping or experimenting with pipeline logic
- User explicitly asks to use MCP tools

→ See [10-mcp-approach.md](10-mcp-approach.md) for MCP-based workflow

---

## Required Checklist

Before writing pipeline code, make sure you have:
```
- [ ] Language selected: Python or SQL
- [ ] Workflow chosen: Standalone DAB / Existing DAB / MCP iteration
- [ ] Compute type: serverless (default) or classic
- [ ] Schema strategy: single schema with prefixes vs. multi-schema
- [ ] Consider [Multi-Schema Patterns](#multi-schema-patterns) and [Modern Defaults](#modern-defaults)
```

---

## Standalone Pipeline with Asset Bundle

Use `databricks pipelines init` when building a **standalone pipeline project** with its own multi-environment deployment.

### Step 1: Initialize Project

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

Replace the example code in `src/transformations/` with your pipeline logic, using best practices from this skill.

**For Python pipelines using cloudFiles**: Store Auto Loader schema metadata in a volume:
```
/Volumes/{catalog}/{schema}/{pipeline_name}_metadata/schemas
```

### Step 3: Deploy and Run

```bash
# Deploy to workspace (dev by default)
databricks bundle deploy

# Run pipeline
databricks bundle run my_pipeline_etl

# Deploy to production
databricks bundle deploy --target prod
```

See **[8-project-initialization.md](8-project-initialization.md)** for complete details on bundle initialization, migration, and troubleshooting.


## Quick Reference

| Concept | Details |
|---------|---------|
| **Names** | SDP = Spark Declarative Pipelines = LDP = Lakeflow Declarative Pipelines = Lakeflow Pipelines (all interchangeable) |
| **Python Import** | `from pyspark import pipelines as dp` |
| **Primary Decorators** | `@dp.table()`, `@dp.materialized_view()`, `@dp.temporary_view()` |
| **Temporary Views** | `@dp.temporary_view()` creates in-pipeline temporary views (no catalog/schema, no cluster_by). Useful for intermediate logic before AUTO CDC or when a view needs multiple references without persistence. |
| **Replaces** | Delta Live Tables (DLT) with `import dlt` |
| **Based On** | Apache Spark 4.1+ (Databricks' modern data pipeline framework) |
| **Docs** | https://docs.databricks.com/aws/en/ldp/developer/python-dev |

---

## Task-Based Routing

After choosing your workflow (see [Choose Your Workflow](#choose-your-workflow)), determine the specific task:

| Task | Guide |
|------|-------|
| **Setting up standalone pipeline project** | [8-project-initialization.md](8-project-initialization.md) |
| **Rapid iteration with MCP tools** | [10-mcp-approach.md](10-mcp-approach.md) |
| **Ingesting data (Auto Loader, Kafka, files)** | [1-ingestion-patterns.md](1-ingestion-patterns.md) |
| **Streaming tables & change detection** | [2-streaming-patterns.md](2-streaming-patterns.md) |
| **Querying SCD Type 2 history tables** | [3-scd-query-patterns.md](3-scd-query-patterns.md) |
| **Implementing AUTO CDC or SCD** | [9-auto_cdc.md](9-auto_cdc.md) |
| **Performance optimization** | [4-performance-tuning.md](4-performance-tuning.md) |
| **Python API reference** | [5-python-api.md](5-python-api.md) |
| **Migrating from DLT** | [6-dlt-migration.md](6-dlt-migration.md) |
| **Advanced configuration** | [7-advanced-configuration.md](7-advanced-configuration.md) |
---

## Official Documentation

- **[Lakeflow Spark Declarative Pipelines Overview](https://docs.databricks.com/aws/en/ldp/)** - Main documentation hub
- **[SQL Language Reference](https://docs.databricks.com/aws/en/ldp/developer/sql-dev)** - SQL syntax for streaming tables and materialized views
- **[Python Language Reference](https://docs.databricks.com/aws/en/ldp/developer/python-ref)** - `pyspark.pipelines` API
- **[Loading Data](https://docs.databricks.com/aws/en/ldp/load)** - Auto Loader, Kafka, Kinesis ingestion
- **[Change Data Capture (CDC)](https://docs.databricks.com/aws/en/ldp/cdc)** - AUTO CDC, SCD Type 1/2


### Medallion Architecture Pattern                                                                                                                                                            
  **Bronze Layer (Raw)**                                                                                                                                                                                                             
  - Raw data ingested from sources in original format                                                                                                                                                                                
  - Minimal transformations (append-only, add metadata like `_ingested_at`, `_source_file`)                                                                                                                                          
  - Single source of truth preserving data lineage                                                                                                                                                                                   
                                                                                                                                                                                                                                     
  **Silver Layer (Validated)**                                                                                                                                                                                                       
  - Cleaned and validated data.
  - Might deduplicate here with auto_cdc, but often wait until the final step for auto_cdc if possible.                                                                                                                                                                                        
  - Business logic applied (type casting, quality checks, filtering invalid records)                                                                                                                                                 
  - Enterprise view of key business entities                                                                                                                                                                                         
  - Enables self-service analytics and ML                                                                                                                                                                                            
                                                                                                                                                                                                                                     
  **Gold Layer (Business-Ready)**                                                                                                                                                                                                    
  - Aggregated, denormalized, project-specific tables                                                                                                                                                                                
  - Optimized for consumption (reporting, dashboards, BI tools)                                                                                                                                                                      
  - Fewer joins, read-optimized data models
  - Kimball star schema tables - dim_<entity_name>, fact_<entity_name>
  - Deduplication often happens here via Slow Changing Dimensions (SCD), using auto_cdc. Sometimes that will happen upstream in silver instead, such as when joining multiple tables or business users plan to query the table from silver.                                                                                                                                                                       
                                                                                                                                                                                                                                     
  **Typical Flow (Can vary)**                                                                                                                                                                                                                  
  Bronze: read_files() or spark.readStream.format("cloudFiles") → streaming table                                                                                                                                                                                             
  Silver: read bronze → filter/clean/validate → streaming table
  Gold: read silver → aggregate/denormalize → auto_cdc or materialized view                                                                                                                                                                      
                                                                                                                                                                                                                        
  Sources:                                                                                                                                                                                                                           
  - https://www.databricks.com/glossary/medallion-architecture                                                                                                                                                                       
  - https://docs.databricks.com/aws/en/lakehouse/medallion                                                                                                                                                                           
  - https://www.databricks.com/blog/2022/06/24/data-warehousing-modeling-techniques-and-their-implementation-on-the-databricks-lakehouse-platform.html
  
**For medallion architecture** (bronze/silver/gold), two approaches work:
- **Flat with naming** (template default): `bronze_*.sql`, `silver_*.sql`, `gold_*.sql`
- **Subdirectories**: `bronze/orders.sql`, `silver/cleaned.sql`, `gold/summary.sql`

Both work with the `transformations/**` glob pattern. Choose based on preference.

See **[8-project-initialization.md](8-project-initialization.md)** for complete details on bundle initialization, migration, and troubleshooting.

---
## General SDP development guidance
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

# Get schema location from pipeline configuration
schema_location_base = spark.conf.get("schema_location_base")

@dp.table(name="bronze_events", cluster_by=["event_date"])
def bronze_events():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.schemaLocation", f"{schema_location_base}/bronze_events")
        .load("/Volumes/catalog/schema/raw/events/")
        .withColumn("_ingested_at", current_timestamp())
        .withColumn("_source_file", col("_metadata.file_path"))
    )
```

**IMPORTANT for Python Pipelines**: When using `spark.readStream.format("cloudFiles")` for cloud storage ingestion, with schema inference (no schema specified), you **must specify a schema location**.

**Always ask the user** where to store Auto Loader schema metadata. Recommend:
```
/Volumes/{catalog}/{schema}/{pipeline_name}_metadata/schemas
```

Example: `/Volumes/my_catalog/pipeline_metadata/orders_pipeline_metadata/schemas`

**Never use the source data volume** - this causes permission conflicts. The schema location should be configured in the pipeline settings and accessed via `spark.conf.get("schema_location_base")`.

**Language Selection:**

**CRITICAL RULE**: If the user explicitly mentions "Python" in their request (e.g., "Python Spark Declarative Pipeline", "Python SDP", "use Python"), **ALWAYS use Python without asking**. The same applies to SQL - if they say "SQL pipeline", use SQL.

- **Explicit language request**: User says "Python" → Use Python. User says "SQL" → Use SQL. **Do not ask for clarification.**
- **Auto-detection** (only when no explicit language mentioned):
  - **SQL indicators**: "sql files", "simple transformations", "aggregations", "materialized view", "CREATE OR REFRESH"
  - **Python indicators**: ".py files", "UDF", "complex logic", "ML inference", "external API", "@dp.table", "pandas", "decorator"
- **Prompt for clarification** only when language intent is truly ambiguous (no explicit mention, mixed signals)
- **Default to SQL** only when ambiguous AND no Python indicators present

See **[8-project-initialization.md](8-project-initialization.md)** for detailed language detection logic.


## Best Practices (2026)

### Project Structure
- **Standalone pipeline projects**: Use `databricks pipelines init` for Asset Bundle with multi-environment support
- **Pipeline in existing bundle**: Add to `resources/*.pipeline.yml`
- **Rapid iteration/prototyping**: Use MCP tools, formalize in bundle later
- **Medallion architecture**: Two file organization approaches:
  - **Flat structure** (template default): `bronze_*.sql`, `silver_*.sql`, `gold_*.sql` in `transformations/`
  - **Subdirectories**: `transformations/bronze/`, `transformations/silver/`, `transformations/gold/`
  - Both work with the `transformations/**` glob pattern - choose based on team preference
- See **[8-project-initialization.md](8-project-initialization.md)** for project setup details

### Minimal pipeline config pointers
- Define parameters in your pipeline’s configuration and access them in code with spark.conf.get("key").
- In Databricks Asset Bundles, set these under resources.pipelines.<pipeline>.configuration; validate with databricks bundle validate.

### Modern Defaults
- **CLUSTER BY** (Liquid Clustering), not PARTITION BY - see [4-performance-tuning.md](4-performance-tuning.md)
- **Raw `.sql`/`.py` files**, not notebooks
- **Serverless compute ONLY** - Do not use classic clusters unless explicitly required
- **Unity Catalog** (required for serverless)
- **read_files()** when using SQL for cloud storage ingestion - see [1-ingestion-patterns.md](1-ingestion-patterns.md)

### Multi-Schema Patterns

**Default: Single target schema per pipeline.** Each pipeline has one target `catalog` and `schema` where all tables are written.


#### Option 1: Single Pipeline, Single Schema with Prefixes (Recommended)

Use one schema with table name prefixes to distinguish layers:

```python
# All tables write to: catalog.schema.bronze_*, silver_*, gold_*
@dp.table(name="bronze_orders")  # → catalog.schema.bronze_orders
@dp.table(name="silver_orders")  # → catalog.schema.silver_orders
@dp.table(name="gold_summary")   # → catalog.schema.gold_summary
```

**Advantages:**
- Simpler configuration (one pipeline)
- All tables in one schema for easy discovery

#### Option 2:
Use varaiables to specific separate catalog and/or schema for different steps.

Below are Python SDP examples that source variables from pipeline configs via spark.conf.get, and use the default catalog/schema for bronze.

##### Same catalog, separate schemas; bronze uses pipeline defaults
- Set your pipeline’s default catalog and default schema to the bronze layer (for example, catalog=my_catalog, schema=bronze). When you omit catalog/schema in code, reads/writes go to these defaults.
- Use pipeline parameters for the other schemas and any source schema/path, retrieved in code with spark.conf.get(...).

```python
from pyspark import pipelines as dp
from pyspark.sql.functions import col

# Pull variables from pipeline configuration parameters
silver_schema = spark.conf.get("silver_schema")  # e.g., "silver"
gold_schema   = spark.conf.get("gold_schema")    # e.g., "gold"
landing_schema = spark.conf.get("landing_schema")  # e.g., "landing"

# Bronze → uses default catalog/schema (set to bronze in pipeline settings)
@dp.table(name="orders_bronze")
def orders_bronze():
    # Read from another schema in the same default catalog
    return spark.readStream.table(f"{landing_schema}.orders_raw")

# Silver → same catalog, schema from parameter
@dp.table(name=f"{silver_schema}.orders_clean")
def orders_clean():
    return (spark.read.table("orders_bronze")  # unqualified = default catalog/schema
            .filter(col("order_id").isNotNull()))

# Gold → same catalog, schema from parameter
@dp.materialized_view(name=f"{gold_schema}.orders_by_date")
def orders_by_date():
    return (spark.read.table(f"{silver_schema}.orders_clean")
            .groupBy("order_date")
            .count().withColumnRenamed("count", "order_count"))
```
- Using unqualified names for bronze ensures it lands in the pipeline’s default catalog/schema; silver/gold are explicitly schema-qualified within the same catalog.

---

##### Custom catalog/schema per layer; bronze still uses pipeline defaults
- Keep bronze in the pipeline defaults (default catalog/schema set to your bronze layer). For silver/gold, use fully-qualified names with catalog and schema variables from pipeline configuration.

```python
from pyspark import pipelines as dp
from pyspark.sql.functions import col

# Pull variables from pipeline configuration parameters
silver_catalog = spark.conf.get("silver_catalog")  # e.g., "my_catalog"
silver_schema  = spark.conf.get("silver_schema")   # e.g., "silver"
gold_catalog   = spark.conf.get("gold_catalog")    # e.g., "my_catalog"
gold_schema    = spark.conf.get("gold_schema")     # e.g., "gold"
landing_catalog = spark.conf.get("landing_catalog")  # optional, if source is in another catalog
landing_schema  = spark.conf.get("landing_schema")

# Bronze → uses default catalog/schema (set to bronze)
@dp.table(name="orders_bronze")
def orders_bronze():
    # If source is in a specified catalog/schema:
    return spark.readStream.table(f"{landing_catalog}.{landing_schema}.orders_raw")

# Silver → custom catalog + schema via parameters
@dp.table(name=f"{silver_catalog}.{silver_schema}.orders_clean")
def orders_clean():
    # Read bronze by its unqualified name (defaults), or fully qualify if preferred
    return (spark.read.table("orders_bronze")
            .filter(col("order_id").isNotNull()))

# Gold → custom catalog + schema via parameters
@dp.materialized_view(name=f"{gold_catalog}.{gold_schema}.orders_by_date}")
def orders_by_date():
    return (spark.read.table(f"{silver_catalog}.{silver_schema}.orders_clean")
            .groupBy("order_date")
            .count().withColumnRenamed("count", "order_count"))
```
- Multipart names in the decorator’s name argument let you publish to explicit catalog.schema targets within one pipeline.
- Unqualified reads/writes use the pipeline defaults; use fully-qualified names when crossing catalogs or when you need explicit namespace control.

---


**Note:** The `@dp.table()` decorator does not currently support separate for `schema=` or `catalog=` parameters. The table parameter is a string that contains the catalog.schema.table_name, or it can leave off catalog and or schema to use the pipeilnes configured default target schema.

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
| **Streaming reads fail** | For file ingestion in a streaming table, you must use the `STREAM` keyword with `read_files`: `FROM STREAM read_files(...)`. For table streams use `FROM stream(table)`. See [read_files — Usage in streaming tables](https://docs.databricks.com/aws/en/sql/language-manual/functions/read_files#usage-in-streaming-tables). |
| **Timeout during run** | Increase `timeout`, or use `wait_for_completion=False` and check status with `get_pipeline` |
| **MV doesn't refresh** | Enable row tracking on source tables |
| **SCD2: query column not found** | Lakeflow uses `__START_AT` and `__END_AT` (double underscore), not `START_AT`/`END_AT`. Use `WHERE __END_AT IS NULL` for current rows. See [3-scd-query-patterns.md](3-scd-query-patterns.md). |
| **AUTO CDC parse error at APPLY/SEQUENCE** | Put `APPLY AS DELETE WHEN` **before** `SEQUENCE BY`. Only list columns in `COLUMNS * EXCEPT (...)` that exist in the source (omit `_rescued_data` unless bronze uses rescue data). Omit `TRACK HISTORY ON *` if it causes "end of input" errors; default is equivalent. See [2-streaming-patterns.md](2-streaming-patterns.md). |
| **"Cannot create streaming table from batch query"** | In a streaming table query, use `FROM STREAM read_files(...)` so `read_files` leverages Auto Loader; `FROM read_files(...)` alone is batch. See [1-ingestion-patterns.md](1-ingestion-patterns.md) and [read_files — Usage in streaming tables](https://docs.databricks.com/aws/en/sql/language-manual/functions/read_files#usage-in-streaming-tables). |

**For detailed errors**, the `result["message"]` from `create_or_update_pipeline` includes suggested next steps. Use `get_pipeline(pipeline_id=...)` which includes recent events and error details.

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

## Related Skills

- **[databricks-jobs](../databricks-jobs/SKILL.md)** - for orchestrating and scheduling pipeline runs
- **[databricks-bundles](../databricks-bundles/SKILL.md)** - for multi-environment deployment of pipeline projects
- **[databricks-synthetic-data-gen](../databricks-synthetic-data-gen/SKILL.md)** - for generating test data to feed into pipelines
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** - for catalog/schema/volume management and governance

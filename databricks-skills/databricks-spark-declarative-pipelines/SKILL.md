---
name: databricks-spark-declarative-pipelines
description: "Creates, configures, and updates Databricks Lakeflow Spark Declarative Pipelines (SDP/LDP) using serverless compute. Handles data ingestion with streaming tables, materialized views, CDC, SCD Type 2, and Auto Loader ingestion patterns. Use when building data pipelines, working with Delta Live Tables, ingesting streaming data, implementing change data capture, or when the user mentions SDP, LDP, DLT, Lakeflow pipelines, streaming tables, or bronze/silver/gold medallion architectures."
---

# Lakeflow Spark Declarative Pipelines (SDP)

---

## Critical Rules (always follow)
- **MUST** know the language (Python or SQL). Ask the user if you don't know, stick with that language unless told otherwise. If you're unsure, SQL is the preference.
| User Says | Action |
|-----------|--------|
| "Python pipeline", "Python SDP", "use Python" | **User wants Python** |
| "SQL pipeline", "SQL files", "use SQL" | **User wants SQL** |
| "Create a SDP and no other instruction" | **Ask the user clarification, SQL or python** |
- **MUST** create serverless pipelines by default. Only use classic clusters if user explicitly requires R language, Spark RDD APIs, or JAR libraries.
- **MUST** choose the right workflow based on context (see below).

## Choose Your Workflow

**First, determine which workflow to use:**

### Option A: Standalone New Pipeline Project (use `databricks pipelines init`)

Use this when the user wants to **create a new, standalone SDP project** that will have its own Asset Bundle:
- User asks: "Create a new pipeline project", "Build me an SDP from scratch", "Set up a new data pipeline"
- No existing `databricks.yml` in the workspace
- The pipeline IS the project (not part of a larger demo/app)

→ See [1-project-initialization.md](1-project-initialization.md)

### Option B: Pipeline within Existing Bundle (edit the bundle)

Use this when the pipeline is **part of an existing Databricks Asset Bundle project**:
- There's already a `databricks.yml` file in the project
- User is adding a pipeline to an existing app/demo

→ See [1-project-initialization.md](1-project-initialization.md) for adding pipelines to existing bundles

### Option C: Rapid Iteration with MCP Tools (no bundle management)

Use this when you need to **quickly create, test, and iterate** on a pipeline without managing bundle files:
- User wants to "just run a pipeline and see if it works"
- Part of a larger demo where bundle is managed separately, or the DAB bundle will be created at the end as you want to quickly test the project first
- Prototyping or experimenting with pipeline logic
- User explicitly asks to use MCP tools

→ See [2-mcp-approach.md](2-mcp-approach.md) for MCP-based workflow

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

**After selecting language, read the syntax basics:**
- **SQL**: Read [sql/1-syntax-basics.md](sql/1-syntax-basics.md)
- **Python**: Read [python/1-syntax-basics.md](python/1-syntax-basics.md)

**Then read additional guides based on what the pipeline needs, when you need it:**
| If the pipeline needs... | Read |
|--------------------------|------|
| File ingestion (Auto Loader, JSON, CSV, Parquet) | `sql/2-ingestion.md` or `python/2-ingestion.md` |
| Kafka, Event Hub, or Kinesis streaming | `sql/2-ingestion.md` or `python/2-ingestion.md` |
| Deduplication, windowed aggregations, joins | `sql/3-streaming-patterns.md` or `python/3-streaming-patterns.md` |
| CDC, SCD Type 1/2, or history tracking | `sql/4-cdc-patterns.md` or `python/4-cdc-patterns.md` |
| Performance tuning, Liquid Clustering | `sql/5-performance.md` or `python/5-performance.md` |

---

## Quick Reference

| Concept | Details |
|---------|---------|
| **Names** | SDP = Spark Declarative Pipelines = LDP = Lakeflow Declarative Pipelines (all interchangeable) |
| **Python Import** | `from pyspark import pipelines as dp` |
| **Primary Decorators** | `@dp.table()`, `@dp.materialized_view()`, `@dp.temporary_view()` |
| **Replaces** | Delta Live Tables (DLT) with `import dlt` |
| **Docs** | https://docs.databricks.com/aws/en/ldp/developer/python-dev |

---

## Task-Based Routing

After choosing your workflow (see [Choose Your Workflow](#choose-your-workflow)), determine the specific task:

**Choose documentation by language:**

### SQL Documentation
| Task | Guide |
|------|-------|
| **SQL syntax basics** | [sql/1-syntax-basics.md](sql/1-syntax-basics.md) |
| **Data ingestion (Auto Loader, Kafka)** | [sql/2-ingestion.md](sql/2-ingestion.md) |
| **Streaming patterns (deduplication, windows)** | [sql/3-streaming-patterns.md](sql/3-streaming-patterns.md) |
| **CDC patterns (AUTO CDC, SCD, queries)** | [sql/4-cdc-patterns.md](sql/4-cdc-patterns.md) |
| **Performance tuning** | [sql/5-performance.md](sql/5-performance.md) |

### Python Documentation
| Task | Guide |
|------|-------|
| **Python syntax basics** | [python/1-syntax-basics.md](python/1-syntax-basics.md) |
| **Data ingestion (Auto Loader, Kafka)** | [python/2-ingestion.md](python/2-ingestion.md) |
| **Streaming patterns (deduplication, windows)** | [python/3-streaming-patterns.md](python/3-streaming-patterns.md) |
| **CDC patterns (AUTO CDC, SCD, queries)** | [python/4-cdc-patterns.md](python/4-cdc-patterns.md) |
| **Performance tuning** | [python/5-performance.md](python/5-performance.md) |

### General Documentation
| Task | Guide |
|------|-------|
| **Setting up standalone pipeline project** | [1-project-initialization.md](1-project-initialization.md) |
| **Rapid iteration with MCP tools** | [2-mcp-approach.md](2-mcp-approach.md) |
| **Advanced configuration** | [3-advanced-configuration.md](3-advanced-configuration.md) |
| **Migrating from DLT** | [4-dlt-migration.md](4-dlt-migration.md) |

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

See **[1-project-initialization.md](1-project-initialization.md)** for complete details on bundle initialization, migration, and troubleshooting.

---
## General SDP development guidance

**SQL Example:**
```sql
CREATE OR REFRESH STREAMING TABLE bronze_orders
CLUSTER BY (order_date)
AS SELECT *, current_timestamp() AS _ingested_at
FROM STREAM read_files('/Volumes/catalog/schema/raw/orders/', format => 'json');
```

**Python Example:**
```python
from pyspark import pipelines as dp

@dp.table(name="bronze_events", cluster_by=["event_date"])
def bronze_events():
    return spark.readStream.format("cloudFiles").option("cloudFiles.format", "json").load("/Volumes/...")
```

For detailed syntax, see [sql/1-syntax-basics.md](sql/1-syntax-basics.md) or [python/1-syntax-basics.md](python/1-syntax-basics.md).

## Best Practices (2026)

### Project Structure
- **Standalone pipeline projects**: Use `databricks pipelines init` for Asset Bundle with multi-environment support
- **Pipeline in existing bundle**: Add to `resources/*.pipeline.yml`
- **Rapid iteration/prototyping**: Use MCP tools, formalize in bundle later
- See **[1-project-initialization.md](1-project-initialization.md)** for project setup details

### Minimal pipeline config pointers
- Define parameters in your pipeline’s configuration and access them in code with spark.conf.get("key").
- In Databricks Asset Bundles, set these under resources.pipelines.<pipeline>.configuration; validate with databricks bundle validate.

### Modern Defaults
- **Raw `.sql`/`.py` files for transformations** - NOT notebooks. Pipeline code must be plain files.
- **Databricks notebook source for explorations** - Use `# Databricks notebook source` format with `# COMMAND ----------` separators for ad-hoc queries. See [examples/exploration_notebook.py](examples/exploration_notebook.py).
- **Serverless compute** - Do not use classic clusters unless explicitly required (R, RDD APIs, JAR libraries)
- **Unity Catalog** (required for serverless)
- **CLUSTER BY** (Liquid Clustering), not PARTITION BY - see [sql/5-performance.md](sql/5-performance.md) or [python/5-performance.md](python/5-performance.md)
- **read_files()** for SQL cloud storage ingestion - see [sql/2-ingestion.md](sql/2-ingestion.md)

### Multi-Schema Patterns

**Default: Single target schema per pipeline** with table name prefixes (e.g., `bronze_*`, `silver_*`, `gold_*`). This is the simplest approach.

For advanced patterns with separate schemas per layer, see **[3-advanced-configuration.md](3-advanced-configuration.md#multi-schema-patterns)**.

**Note:** The `@dp.table()` decorator does not support separate `schema=` or `catalog=` parameters. Use a string like `catalog.schema.table_name`, or omit catalog/schema to use pipeline defaults.

For detailed Python reading patterns, see **[python/1-syntax-basics.md](python/1-syntax-basics.md#reading-data)**.

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
| **SCD2: query column not found** | Lakeflow uses `__START_AT` and `__END_AT` (double underscore), not `START_AT`/`END_AT`. Use `WHERE __END_AT IS NULL` for current rows. See [sql/4-cdc-patterns.md](sql/4-cdc-patterns.md). |
| **AUTO CDC parse error at APPLY/SEQUENCE** | Put `APPLY AS DELETE WHEN` **before** `SEQUENCE BY`. Only list columns in `COLUMNS * EXCEPT (...)` that exist in the source (omit `_rescued_data` unless bronze uses rescue data). Omit `TRACK HISTORY ON *` if it causes "end of input" errors; default is equivalent. See [sql/4-cdc-patterns.md](sql/4-cdc-patterns.md). |
| **"Cannot create streaming table from batch query"** | In a streaming table query, use `FROM STREAM read_files(...)` so `read_files` leverages Auto Loader; `FROM read_files(...)` alone is batch. See [sql/2-ingestion.md](sql/2-ingestion.md) and [read_files — Usage in streaming tables](https://docs.databricks.com/aws/en/sql/language-manual/functions/read_files#usage-in-streaming-tables). |

**For detailed errors**, the `result["message"]` from `create_or_update_pipeline` includes suggested next steps. Use `get_pipeline(pipeline_id=...)` which includes recent events and error details.

---

## Advanced Pipeline Configuration

For advanced configuration options (development mode, continuous pipelines, custom clusters, notifications, Python dependencies, etc.), see **[3-advanced-configuration.md](3-advanced-configuration.md)**.

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

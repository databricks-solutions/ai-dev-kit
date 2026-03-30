---
name: databricks-spark-declarative-pipelines
description: "Creates, configures, and updates Databricks Lakeflow Spark Declarative Pipelines (SDP/LDP) using serverless compute. Handles data ingestion with streaming tables, materialized views, CDC, SCD Type 2, and Auto Loader ingestion patterns. Use when building data pipelines, working with Delta Live Tables, ingesting streaming data, implementing change data capture, or when the user mentions SDP, LDP, DLT, Lakeflow pipelines, streaming tables, or bronze/silver/gold medallion architectures."
---

# Lakeflow Spark Declarative Pipelines (SDP)

---

## Critical Rules (always follow)

### Syntax: CREATE OR REFRESH (not CREATE OR REPLACE)
- **MUST** use `CREATE OR REFRESH` for SDP objects:
  - `CREATE OR REFRESH STREAMING TABLE` - for streaming tables
  - `CREATE OR REFRESH MATERIALIZED VIEW` - for materialized views
- **NEVER** use `CREATE OR REPLACE` - that is standard SQL syntax, not SDP syntax

### Simplicity First
- **MUST** create the minimal number of tables to solve the task
- Simplicity first: prefer single pipeline even for multi-schema setups - use fully qualified names (`catalog.schema.table`)
- When asked to "create a silver table" or "create a gold table", create **ONE table** - not a multi-layer pipeline
- Don't add intermediate tables, staging tables, or helper views unless explicitly requested
- A silver transformation = 1 streaming table reading from bronze
- A gold aggregation = 1 materialized view reading from silver
- Create bronze→silver→gold chains when the user asks for a "pipeline" or "medallion architecture" or full/detailed ingestion. Otherwise keep it simple - don't over engineer.

### Language Selection
- **MUST** know the language (Python or SQL). For simple task / pipeline / table creation, pick SQL. For complex pipeline with parametrized information, or if the user mentions python-related items pick python. If you have a doubt, ask the user. Stick with that language unless told otherwise.

| User Says | Action |
|-----------|--------|
| "Python pipeline", "Python SDP", "use Python", "udf", "pandas", "ml inference", "pyspark" | **User wants Python** |
| "SQL pipeline", "SQL files", "use SQL" | **User wants SQL** |
| "Create a simple pipeline", "create a table", "an aggregation" | **Pick SQL as it's simple** |

### Other Rules
- **MUST** create serverless pipelines by default. Only use classic clusters if user explicitly requires R language, Spark RDD APIs, or JAR libraries.
- **MUST** choose the right workflow based on context (see below).
- When the user provides table schema and asks for code, respond directly with the code. Don't ask clarifying questions if the request is clear.

## Tools
- List files in volume: `databricks fs ls dbfs:/Volumes/{catalog}/{schema}/{volume}/{path} --profile {PROFILE}`
- Query data: `databricks experimental aitools tools query --profile {PROFILE} --warehouse abc123 "SELECT 1 FROM catalog.schema.table"`
- Discover schema: `databricks experimental aitools tools discover-schema --profile {PROFILE} catalog.schema.table1 catalog.schema.table2`
- Pipelines CLI: `databricks pipelines init|deploy|run|logs|stop` or use `databricks pipelines --help` for more options

## Choose Your Workflow

**First, determine which workflow to use:**

### Option A: Standalone New Pipeline Project (use `databricks pipelines init`)

Use this when the user wants to **create a new, standalone SDP project** that will have its own DAB:
- User asks: "Create a new pipeline", "Build me an SDP", "Set up a new data pipeline"
- No existing `databricks.yml` in the workspace
- The pipeline IS the project (not part of a larger demo/app)


Use `databricks pipeline` CLI commands:
```bash
databricks pipelines init --output-dir . --config-file init-config.json
```

**Example init-config.json:**
```json
{
  "project_name": "customer_pipeline",
  "initial_catalog": "prod_catalog",
  "use_personal_schema": "no",
  "initial_language": "sql"
}
```

→ See [1-project-initialization.md](references/1-project-initialization.md)
→ 


### Option B: Pipeline within Existing Bundle (edit the bundle)

Use this when the pipeline is **part of an existing DAB project**:
- There's already a `databricks.yml` file in the project
- User is adding a pipeline to an existing app/demo

→ See [1-project-initialization.md](references/1-project-initialization.md) for adding pipelines to existing bundles

### Option C: Rapid Iteration with MCP Tools (no bundle management)

Use this when you need to **quickly create, test, and iterate** on a pipeline without managing bundle files:
- User wants to "just run a pipeline and see if it works"
- Part of a larger demo where bundle is managed separately, or the DAB bundle will be created at the end as you want to quickly test the project first
- Prototyping or experimenting with pipeline logic
- User explicitly asks to use MCP tools

→ See [2-mcp-approach.md](references/2-mcp-approach.md) for MCP-based workflow

---

## Required Checklist

Before writing pipeline code, make sure you have:
```
- [ ] Language selected: Python or SQL
- [ ] Read the syntax basics: **SQL**: Always Read [sql/1-syntax-basics.md](references/sql/1-syntax-basics.md), **Python**: Always Read [python/1-syntax-basics.md](references/python/1-syntax-basics.md)
- [ ] Workflow chosen: Standalone DAB / Existing DAB / MCP iteration
- [ ] Compute type: serverless (default) or classic
- [ ] Schema strategy: single schema with prefixes vs. multi-schema
- [ ] Consider [Multi-Schema Patterns](#multi-schema-patterns) and [Modern Defaults](#modern-defaults)
```

**Then read additional guides based on what the pipeline needs, when you need it:**
| If the pipeline needs... | Read |
|--------------------------|------|
| File ingestion (Auto Loader, JSON, CSV, Parquet) | `references/sql/2-ingestion.md` or `references/python/2-ingestion.md` |
| Kafka, Event Hub, or Kinesis streaming | `references/sql/2-ingestion.md` or `references/python/2-ingestion.md` |
| Deduplication, windowed aggregations, joins | `references/sql/3-streaming-patterns.md` or `references/python/3-streaming-patterns.md` |
| CDC, SCD Type 1/2, or history tracking | `references/sql/4-cdc-patterns.md` or `references/python/4-cdc-patterns.md` |
| Performance tuning, Liquid Clustering | `references/sql/5-performance.md` or `references/python/5-performance.md` |

---

## Quick Reference

| Concept | Details |
|---------|---------|
| **Names** | SDP = Spark Declarative Pipelines = LDP = Lakeflow Declarative Pipelines (all interchangeable) |
| **SQL Syntax** | `CREATE OR REFRESH STREAMING TABLE`, `CREATE OR REFRESH MATERIALIZED VIEW` |
| **Python Import** | `from pyspark import pipelines as dp` |
| **Primary Decorators** | `@dp.table()`, `@dp.materialized_view()`, `@dp.temporary_view()` |

### Legacy APIs (Do NOT Use)

| Legacy | Modern Replacement |
|--------|-------------------|
| `import dlt` | `from pyspark import pipelines as dp` |
| `dlt.apply_changes()` | `dp.create_auto_cdc_flow()` |
| `dlt.read()` / `dlt.read_stream()` | `spark.read` / `spark.readStream` |
| `CREATE LIVE XXX` | `CREATE OR REFRESH STREAMING TABLE\|MATERIALIZED VIEW` |
| `PARTITION BY` + `ZORDER` | `CLUSTER BY` (Liquid Clustering) |
| `input_file_name()` | `_metadata.file_path` |
| `target` parameter | `schema` parameter |

### Streaming Table vs Materialized View

| Use Case | Type | Pattern |
|----------|------|---------|
| Windowed aggregations (tumbling, sliding, session) | Streaming Table | `FROM stream(source)` + `GROUP BY window()` |
| Full-table aggregations (totals, daily counts) | Materialized View | `FROM source` (no stream wrapper) |
| CDC / SCD Type 2 | Streaming Table | `AUTO CDC INTO` or `dp.create_auto_cdc_flow()` |

Use streaming tables for windowed aggregations to enable incremental processing. Use materialized views for simple aggregations that recompute fully on each refresh.

---

## Task-Based Routing

After choosing your workflow (see [Choose Your Workflow](#choose-your-workflow)), determine the specific task:

**Choose documentation by language:**

### SQL Documentation
| Task | Guide |
|------|-------|
| **SQL syntax basics** | [sql/1-syntax-basics.md](references/sql/1-syntax-basics.md) |
| **Data ingestion (Auto Loader, Kafka)** | [sql/2-ingestion.md](references/sql/2-ingestion.md) |
| **Streaming patterns (deduplication, windows)** | [sql/3-streaming-patterns.md](references/sql/3-streaming-patterns.md) |
| **CDC patterns (AUTO CDC, SCD, queries)** | [sql/4-cdc-patterns.md](references/sql/4-cdc-patterns.md) |
| **Performance tuning** | [sql/5-performance.md](references/sql/5-performance.md) |

### Python Documentation
| Task | Guide |
|------|-------|
| **Python syntax basics** | [python/1-syntax-basics.md](references/python/1-syntax-basics.md) |
| **Data ingestion (Auto Loader, Kafka)** | [python/2-ingestion.md](references/python/2-ingestion.md) |
| **Streaming patterns (deduplication, windows)** | [python/3-streaming-patterns.md](references/python/3-streaming-patterns.md) |
| **CDC patterns (AUTO CDC, SCD, queries)** | [python/4-cdc-patterns.md](references/python/4-cdc-patterns.md) |
| **Performance tuning** | [python/5-performance.md](references/python/5-performance.md) |

### General Documentation
| Task | Guide |
|------|-------|
| **Setting up standalone pipeline project** | [1-project-initialization.md](references/1-project-initialization.md) |
| **Rapid iteration with MCP tools** | [2-mcp-approach.md](references/2-mcp-approach.md) |
| **Advanced configuration** | [3-advanced-configuration.md](references/3-advanced-configuration.md) |
| **Migrating from DLT** | [4-dlt-migration.md](references/4-dlt-migration.md) |

---

## Official Documentation

- **[Lakeflow Spark Declarative Pipelines Overview](https://docs.databricks.com/aws/en/ldp/)** - Main documentation hub
- **[SQL Language Reference](https://docs.databricks.com/aws/en/ldp/developer/sql-dev)** - SQL syntax for streaming tables and materialized views
- **[Python Language Reference](https://docs.databricks.com/aws/en/ldp/developer/python-ref)** - `pyspark.pipelines` API
- **[Loading Data](https://docs.databricks.com/aws/en/ldp/load)** - Auto Loader, Kafka, Kinesis ingestion
- **[Change Data Capture (CDC)](https://docs.databricks.com/aws/en/ldp/cdc)** - AUTO CDC, SCD Type 1/2


### Medallion Architecture

| Layer | SDP Pattern | Common Practices |
|-------|-------------|------------------|
| **Bronze** | `STREAM read_files()` → streaming table | Often adds `_metadata.file_path`, `_ingested_at`. Minimal transforms, append-only. |
| **Silver** | `stream(bronze)` → streaming table | Clean/validate, type casting, quality filters. Prefer `DECIMAL(p,s)` for money. Dedup can happen here or gold. |
| **Gold** | `AUTO CDC INTO` or materialized view | Aggregated, denormalized. SCD/dedup often via `AUTO CDC`. Star schema typically uses `dim_*`/`fact_*`. |

**For medallion architecture** (bronze/silver/gold), two approaches work:
- **Flat with naming** (template default): `bronze_*.sql`, `silver_*.sql`, `gold_*.sql`
- **Subdirectories**: `bronze/orders.sql`, `silver/cleaned.sql`, `gold/summary.sql`

Both work with the `transformations/**` glob pattern. Choose based on preference/existing.

See **[1-project-initialization.md](references/1-project-initialization.md)** for complete details on bundle initialization, migration, and troubleshooting.

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

For detailed syntax, see [sql/1-syntax-basics.md](references/sql/1-syntax-basics.md) or [python/1-syntax-basics.md](references/python/1-syntax-basics.md).

## Best Practices (2026)

### Project Structure
- **Standalone pipeline projects**: Use `databricks pipelines init` for Asset Bundle with multi-environment support
- **Pipeline in existing bundle**: Add to `resources/*.pipeline.yml`
- **Rapid iteration/prototyping**: Use MCP tools, formalize in bundle later
- See **[1-project-initialization.md](references/1-project-initialization.md)** for project setup details

### Minimal pipeline config pointers
- Define parameters in your pipeline’s configuration and access them in code with spark.conf.get("key").
- In Databricks Asset Bundles, set these under resources.pipelines.<pipeline>.configuration; validate with databricks bundle validate.

### Modern Defaults
- **Always use raw `.sql`/`.py` files for the transformations files** - NO notebooks in your pipeline. Pipeline code must be plain files.
- **Databricks notebook source for explorations** - Use `# Databricks notebook source` format with `# COMMAND ----------` separators for ad-hoc queries. See [examples/exploration_notebook.py](scripts/exploration_notebook.py).
- **Serverless compute** - Do not use classic clusters unless explicitly required (R, RDD APIs, JAR libraries)
- **Unity Catalog** (required for serverless)
- **CLUSTER BY** (Liquid Clustering), not PARTITION BY with ZORDER - see [sql/5-performance.md](references/sql/5-performance.md) or [python/5-performance.md](references/python/5-performance.md)
- **read_files()** for SQL cloud storage ingestion - always consume a folder, not a single file - see [sql/2-ingestion.md](references/sql/2-ingestion.md)

### Multi-Schema Patterns

**Preferred: One pipeline writing to multiple schemas** using fully qualified table names (`catalog.schema.table`). This keeps dependencies clear and is simpler to manage than multiple pipelines.

- **Python**: `@dp.table(name="catalog.bronze_schema.orders")`
- **SQL**: `CREATE OR REFRESH STREAMING TABLE catalog.silver_schema.orders_clean AS ...`

For detailed examples, see **[3-advanced-configuration.md](references/3-advanced-configuration.md#multi-schema-patterns)**.

**Fallback**: If all tables must be in the same schema, use name prefixes (`bronze_*`, `silver_*`, `gold_*`).

---

## Post-Run Validation (Required)

After running a pipeline (via DAB or MCP), you **MUST** validate both the execution status AND the actual data.

### Step 1: Check Pipeline Execution Status

**From MCP (`run_pipeline` or `create_or_update_pipeline`):**
- Check `result["success"]` and `result["state"]`
- If failed, check `result["message"]` and `result["errors"]` for details

**From DAB (`databricks bundle run`):**
- Check the command output for success/failure
- Use `get_pipeline(pipeline_id=...)` to get detailed status and recent events

### Step 2: Validate Output Data

Even if the pipeline reports SUCCESS, you **MUST** verify the data is correct:

```
# MCP Tool: get_table_stats_and_schema - validates schema, row counts, and stats
get_table_stats_and_schema(
    catalog="my_catalog",
    schema="my_schema",
    table_names=["bronze_*", "silver_*", "gold_*"]  # Use glob patterns
)
```

**Check for:**
- Empty tables (row_count = 0) - indicates ingestion or filtering issues
- Unexpected row counts - joins may have exploded or filtered too much
- Missing columns - schema mismatch or transformation errors
- NULL values in key columns - data quality issues

### Step 3: Debug Data Issues

If validation reveals problems, trace upstream to find the root cause:

1. **Start from the problematic table** - identify what's wrong (empty, wrong counts, bad data)
2. **Check its source table** - use `get_table_stats_and_schema` on the upstream table
3. **Trace back to bronze** - continue until you find where the issue originates
4. **Common causes:**
   - Bronze empty → source files missing or path incorrect
   - Silver empty → filter too aggressive or join condition wrong
   - Gold wrong counts → aggregation logic error or duplicate keys
   - Data mismatch → type casting issues or NULL handling

5. **Fix the SQL/Python code**, re-upload, and re-run the pipeline

**Do NOT use `execute_sql` with COUNT queries for validation** - `get_table_stats_and_schema` is faster and returns more information in a single call.

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **Empty output tables** | Use `get_table_stats_and_schema` to check upstream sources. Verify source files exist and paths are correct. |
| **Pipeline stuck INITIALIZING** | Normal for serverless, wait a few minutes |
| **"Column not found"** | Check `schemaHints` match actual data |
| **Streaming reads fail** | For file ingestion in a streaming table, you must use the `STREAM` keyword with `read_files`: `FROM STREAM read_files(...)`. For table streams use `FROM stream(table)`. See [read_files — Usage in streaming tables](https://docs.databricks.com/aws/en/sql/language-manual/functions/read_files#usage-in-streaming-tables). |
| **Timeout during run** | Increase `timeout`, or use `wait_for_completion=False` and check status with `get_pipeline` |
| **MV doesn't refresh** | Enable row tracking on source tables |
| **SCD2: query column not found** | Lakeflow uses `__START_AT` and `__END_AT` (double underscore), not `START_AT`/`END_AT`. Use `WHERE __END_AT IS NULL` for current rows. See [sql/4-cdc-patterns.md](references/sql/4-cdc-patterns.md). |
| **AUTO CDC parse error at APPLY/SEQUENCE** | Put `APPLY AS DELETE WHEN` **before** `SEQUENCE BY`. Only list columns in `COLUMNS * EXCEPT (...)` that exist in the source (omit `_rescued_data` unless bronze uses rescue data). Omit `TRACK HISTORY ON *` if it causes "end of input" errors; default is equivalent. See [sql/4-cdc-patterns.md](references/sql/4-cdc-patterns.md). |
| **"Cannot create streaming table from batch query"** | In a streaming table query, use `FROM STREAM read_files(...)` so `read_files` leverages Auto Loader; `FROM read_files(...)` alone is batch. See [sql/2-ingestion.md](references/sql/2-ingestion.md) and [read_files — Usage in streaming tables](https://docs.databricks.com/aws/en/sql/language-manual/functions/read_files#usage-in-streaming-tables). |

**For detailed errors**, the `result["message"]` from `create_or_update_pipeline` includes suggested next steps. Use `get_pipeline(pipeline_id=...)` which includes recent events and error details.

---

## Advanced Pipeline Configuration

For advanced configuration options (development mode, continuous pipelines, custom clusters, notifications, Python dependencies, etc.), see **[3-advanced-configuration.md](references/3-advanced-configuration.md)**.

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

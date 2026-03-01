# Subagent Parallelization Patterns

Use `Task` subagents (`subagent_type="shell"`) to parallelize MCP tool calls when work spans multiple catalogs, schemas, or tables. Each subagent runs independently and returns its results. **Max 4 concurrent subagents.**

---

## When to Use Subagents vs. execute_sql_multi

| Scenario | Best Tool | Why |
|----------|-----------|-----|
| N queries, **same catalog** | `execute_sql_multi` | Single MCP call, built-in parallelism (up to 4 workers), simpler |
| N queries, **different catalogs** | Parallel shell subagents | Each needs a different catalog context |
| Probing N catalogs for table existence | Parallel shell subagents | Each subagent probes one catalog independently |
| Sizing N tables in same catalog | `execute_sql_multi` | Combine N `DESCRIBE DETAIL` into one call |
| Sizing tables across catalogs | Parallel shell subagents | Different catalog contexts |
| Mixed: some cross-catalog, some same-catalog | Combine both | Subagents for cross-catalog, `execute_sql_multi` within each |

---

## Where Subagents Are Used in This Workflow

| Step | Action | Approach |
|------|--------|----------|
| Step 3 | Test catalog accessibility across multiple catalogs | Parallel shell subagents |
| Step 4 | Probe multiple candidate catalogs in parallel | Parallel shell subagents |
| Step 5 | Extract schema from multiple catalogs/schemas | Parallel shell subagents |
| Step 10 | Run data discovery queries (same catalog) | `execute_sql_multi` (preferred) |
| Step 11 | Run `DESCRIBE DETAIL` on multiple tables | `execute_sql_multi` (same catalog) or subagents (cross-catalog) |

---

## Pattern A: Parallel Catalog Probing

When Step 3 or 4 identifies multiple candidate catalogs, launch one subagent per catalog to verify which contains the target tables.

**Subagent prompt template** (one per catalog):

```
Probe catalog "<CATALOG>" for tables in schema "<SCHEMA>" using the Databricks MCP server.

1. Call CallMcpTool with:
   - server: "user-databricks"
   - toolName: "execute_sql"
   - arguments: {"sql_query": "SELECT table_name FROM <CATALOG>.information_schema.tables WHERE table_schema = '<SCHEMA>' ORDER BY table_name"}

2. Return the list of table names found, or state that no tables were found.
```

Launch up to 4 concurrently:

```
Task(subagent_type="shell", prompt="<template with catalog=analytics>")
Task(subagent_type="shell", prompt="<template with catalog=fc_analytics>")
Task(subagent_type="shell", prompt="<template with catalog=hive_metastore>")
```

Merge results into `reference/catalog_resolution.md`.

---

## Pattern B: Parallel Schema Extraction

When Step 5 needs schema from multiple catalogs or schemas, launch one subagent per catalog/schema pair.

**Subagent prompt template**:

```
Extract schema details for catalog "<CATALOG>", schema "<SCHEMA>" using the Databricks MCP server.

1. Call CallMcpTool with:
   - server: "user-databricks"
   - toolName: "get_table_details"
   - arguments: {"catalog": "<CATALOG>", "schema": "<SCHEMA>", "table_stat_level": "SIMPLE"}

2. Return the full result including table names, column definitions, and row counts.
```

---

## Pattern C: Batch Data Discovery with execute_sql_multi

When Step 10 generates discovery queries for tables within a **single catalog**, execute them all in one MCP call.

```
CallMcpTool:
  server: "user-databricks"
  toolName: "execute_sql_multi"
  arguments:
    sql_content: |
      SELECT DISTINCT result_type FROM catalog.gold.sales_fact ORDER BY result_type;
      SELECT result_type, COUNT(*) AS cnt FROM catalog.gold.sales_fact GROUP BY result_type ORDER BY cnt DESC LIMIT 50;
      SELECT MIN(order_date) AS min_date, MAX(order_date) AS max_date FROM catalog.gold.sales_fact;
      SELECT DISTINCT customer_status FROM catalog.gold.customer_dim ORDER BY customer_status;
      SELECT COUNT(*) AS total_rows, COUNT(*) - COUNT(result_type) AS result_type_nulls FROM catalog.gold.sales_fact;
    catalog: "catalog"
    schema: "gold"
    max_workers: 4
```

The tool automatically detects independent queries and runs them in parallel. Results are returned per-statement.

---

## Pattern D: Parallel Table Sizing

When Step 11 needs `DESCRIBE DETAIL` for many tables:

**Same catalog** — use `execute_sql_multi`:

```
CallMcpTool:
  server: "user-databricks"
  toolName: "execute_sql_multi"
  arguments:
    sql_content: |
      DESCRIBE DETAIL catalog.gold.sales_fact;
      DESCRIBE DETAIL catalog.gold.customer_dim;
      DESCRIBE DETAIL catalog.gold.product_dim;
      DESCRIBE DETAIL catalog.gold.date_dim;
    catalog: "catalog"
    max_workers: 4
```

Extract `sizeInBytes` and `numFiles` from results to feed into the query complexity scoring in [5-query-optimization.md](5-query-optimization.md).

**Cross-catalog** — launch parallel shell subagents, each running `execute_sql` with one `DESCRIBE DETAIL` statement against its catalog.

---

## Full Example: Parallel Catalog Probing (Steps 3–4)

### Input: Catalog list from system.information_schema.catalogs

```
analytics, fc_analytics, hive_metastore, system
```

Target schema: `gold`. PBI model references: `sales_fact`, `customer_dim`, `date_dim`, `product_dim`.

### Agent launches 3 parallel shell subagents

```
Task(subagent_type="shell", description="Probe analytics catalog",
     prompt='Probe catalog "analytics" for tables in schema "gold" using the Databricks MCP server.
             Call CallMcpTool with server="user-databricks", toolName="execute_sql",
             arguments={"sql_query": "SELECT table_name FROM analytics.information_schema.tables WHERE table_schema = \'gold\' ORDER BY table_name"}.
             Return the list of table names found.')

Task(subagent_type="shell", description="Probe fc_analytics catalog",
     prompt='Probe catalog "fc_analytics" for tables in schema "gold" using the Databricks MCP server.
             Call CallMcpTool with server="user-databricks", toolName="execute_sql",
             arguments={"sql_query": "SELECT table_name FROM fc_analytics.information_schema.tables WHERE table_schema = \'gold\' ORDER BY table_name"}.
             Return the list of table names found.')

Task(subagent_type="shell", description="Probe hive_metastore catalog",
     prompt='Probe catalog "hive_metastore" for tables in schema "gold" using the Databricks MCP server.
             Call CallMcpTool with server="user-databricks", toolName="execute_sql",
             arguments={"sql_query": "SELECT table_name FROM hive_metastore.information_schema.tables WHERE table_schema = \'gold\' ORDER BY table_name"}.
             Return the list of table names found.')
```

### Merged output: reference/catalog_resolution.md

```markdown
## Catalog Resolution

- **Primary catalog**: `analytics`
- **Fallback catalog**: `fc_analytics`
- **Target schema**: `gold`

### Table Inventory
| Table | Catalog | Schema |
|-------|---------|--------|
| sales_fact | analytics | gold |
| customer_dim | analytics | gold |
| date_dim | analytics | gold |
| product_dim | fc_analytics | gold |
```

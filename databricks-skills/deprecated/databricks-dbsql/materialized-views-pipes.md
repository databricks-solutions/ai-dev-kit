# Materialized Views, Temporary Tables/Views, and Pipe Syntax

## 1. Materialized Views in Databricks SQL

### Overview

Materialized views (MVs) are Unity Catalog-managed tables that physically store precomputed query results. Unlike standard views that recompute on every query, MVs cache results and update automatically -- either on a schedule, when upstream data changes, or on-demand.

Key characteristics:
- **Pre-computed storage**: Results are physically stored as Delta tables, reducing query latency
- **Automatic updates**: Changes propagate from source tables via incremental or full refresh
- **Serverless pipelines**: Each MV automatically creates a serverless pipeline for creation and refreshes
- **Incremental refresh**: Can compute only changed data from source tables under certain conditions

### Requirements

- **Compute**: Unity Catalog-enabled **Serverless** SQL warehouse
- **Region**: Serverless SQL warehouse support must be available in your region
- **Permissions**:
  - Creator needs: `SELECT` on base tables, `USE CATALOG`, `USE SCHEMA`, `CREATE TABLE`, `CREATE MATERIALIZED VIEW`
  - Refresh needs: Ownership or `REFRESH` privilege; MV owner must retain `SELECT` on base tables
  - Query needs: `SELECT` on the MV, `USE CATALOG`, `USE SCHEMA`

### CREATE MATERIALIZED VIEW Syntax

```sql
{ CREATE OR REPLACE MATERIALIZED VIEW | CREATE MATERIALIZED VIEW [ IF NOT EXISTS ] }
  view_name
  [ column_list ]
  [ view_clauses ]
  AS query
```

**Column list** (optional):
```sql
CREATE MATERIALIZED VIEW mv_name (
  col1 INT NOT NULL,
  col2 STRING,
  col3 DOUBLE,
  CONSTRAINT pk PRIMARY KEY (col1)
)
AS SELECT ...
```

**View clauses** (optional):
- `PARTITIONED BY (col1, col2)` -- partition by columns
- `CLUSTER BY (col1, col2)` or `CLUSTER BY AUTO` -- liquid clustering (cannot combine with PARTITIONED BY)
- `COMMENT 'description'` -- view description
- `TBLPROPERTIES ('key' = 'value')` -- user-defined properties
- `WITH ROW FILTER func ON (col1, col2)` -- row-level security
- `MASK func` on columns -- column-level masking
- `SCHEDULE` clause -- automatic refresh schedule
- `TRIGGER ON UPDATE` clause -- event-driven refresh

### Basic Examples

```sql
-- Simple materialized view
CREATE MATERIALIZED VIEW catalog.schema.daily_sales
  COMMENT 'Daily sales aggregations'
AS SELECT
    date,
    region,
    SUM(sales) AS total_sales,
    COUNT(*) AS num_transactions
FROM catalog.schema.raw_sales
GROUP BY date, region;

-- MV with explicit columns, constraints, and clustering
CREATE MATERIALIZED VIEW catalog.schema.customer_orders (
  customer_id INT NOT NULL,
  full_name STRING,
  order_count BIGINT,
  CONSTRAINT customer_pk PRIMARY KEY (customer_id)
)
CLUSTER BY AUTO
COMMENT 'Customer order counts'
AS SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS order_count
FROM catalog.schema.customers c
INNER JOIN catalog.schema.orders o ON c.customer_id = o.customer_id
GROUP BY c.customer_id, c.full_name;
```

### Refresh Options

MVs support four refresh strategies:

#### 1. Manual Refresh

```sql
-- Synchronous (blocks until complete)
REFRESH MATERIALIZED VIEW catalog.schema.daily_sales;

-- Asynchronous (returns immediately)
REFRESH MATERIALIZED VIEW catalog.schema.daily_sales ASYNC;
```

#### 2. Scheduled Refresh (SCHEDULE)

```sql
-- Every N hours/days/weeks
CREATE OR REPLACE MATERIALIZED VIEW catalog.schema.hourly_metrics
  SCHEDULE EVERY 1 HOUR
AS SELECT date_trunc('hour', event_time) AS hour, COUNT(*) AS events
FROM catalog.schema.raw_events
GROUP BY 1;

-- Cron-based schedule
CREATE OR REPLACE MATERIALIZED VIEW catalog.schema.nightly_report
  SCHEDULE CRON '0 0 2 * * ?' AT TIME ZONE 'America/New_York'
AS SELECT * FROM catalog.schema.daily_aggregates;
```

Valid intervals: 1-72 hours, 1-31 days, 1-8 weeks. A Databricks Job is automatically created for scheduled refreshes.

#### 3. Event-Driven Refresh (TRIGGER ON UPDATE)

Automatically refreshes when upstream data changes:

```sql
CREATE OR REPLACE MATERIALIZED VIEW catalog.schema.customer_orders
  TRIGGER ON UPDATE
AS SELECT c.customer_id, c.name, COUNT(o.order_id) AS order_count
FROM catalog.schema.customers c
JOIN catalog.schema.orders o ON c.customer_id = o.customer_id
GROUP BY c.customer_id, c.name;

-- With throttle to avoid excessive refreshes
CREATE OR REPLACE MATERIALIZED VIEW catalog.schema.customer_orders
  TRIGGER ON UPDATE AT MOST EVERY INTERVAL 5 MINUTES
AS SELECT c.customer_id, c.name, COUNT(o.order_id) AS order_count
FROM catalog.schema.customers c
JOIN catalog.schema.orders o ON c.customer_id = o.customer_id
GROUP BY c.customer_id, c.name;
```

Trigger limitations:
- Maximum **10 upstream source tables** and **30 upstream views**
- Minimum **1-minute** interval (default)
- Maximum **1,000** trigger-based MVs per workspace
- Supports Delta tables, managed views, and streaming tables as sources
- Does **not** support Delta Sharing shared tables

#### 4. Job-Based Orchestration

Integrate refreshes into existing Databricks Jobs using SQL task types:

```sql
-- In a Databricks Job SQL task
REFRESH MATERIALIZED VIEW catalog.schema.daily_sales_summary;
```

### Managing Schedules After Creation

```sql
-- Add a schedule to an existing MV
ALTER MATERIALIZED VIEW catalog.schema.my_mv ADD SCHEDULE EVERY 4 HOURS;

-- Add trigger-based refresh
ALTER MATERIALIZED VIEW catalog.schema.my_mv ADD TRIGGER ON UPDATE;

-- Change an existing schedule
ALTER MATERIALIZED VIEW catalog.schema.my_mv ALTER SCHEDULE EVERY 2 HOURS;

-- Remove a schedule
ALTER MATERIALIZED VIEW catalog.schema.my_mv DROP SCHEDULE;
```

### Incremental vs Full Refresh

| Aspect | Incremental Refresh | Full Refresh |
|--------|-------------------|--------------|
| What it does | Evaluates changes since last refresh, merges only new/modified records | Re-executes the entire defining query |
| When used | When source tables support change tracking and query structure allows it | When incremental is not possible or not cost-effective |
| Requirements | Delta source tables with row tracking and CDF enabled | No special requirements |
| Cost | Lower (processes only deltas) | Higher (recomputes everything) |

Enable row tracking on source tables for incremental refresh:

```sql
ALTER TABLE catalog.schema.source_table
SET TBLPROPERTIES (delta.enableRowTracking = true);
```

By default, Databricks uses a cost model to choose between incremental and full refresh. Use `EXPLAIN CREATE MATERIALIZED VIEW` to verify the chosen refresh type.

### Timeout Configuration

```sql
-- Set timeout before creating or refreshing
SET STATEMENT_TIMEOUT = '6h';
CREATE OR REFRESH MATERIALIZED VIEW catalog.schema.my_mv
  SCHEDULE EVERY 12 HOURS
AS SELECT * FROM catalog.schema.large_source_table;
```

Default timeout is **2 days** if no warehouse timeout is configured. After changing warehouse timeouts, re-run `CREATE OR REFRESH` to apply new settings.

### Monitoring

- **Catalog Explorer**: View refresh status, schema, permissions, lineage under the MV entry
- **DESCRIBE EXTENDED**: Get schedule and configuration details
- **Jobs & Pipelines UI**: Monitor the automatically created pipeline
- **Pipelines API**: `GET /api/2.0/pipelines/{pipeline_id}` for programmatic access
- **DESCRIBE EXTENDED AS JSON**: Get refresh information including last refresh time, type, status, and schedule (added October 2025)

### Key Limitations

- No identity columns or surrogate keys
- Cannot read change data feeds (CDF) from materialized views
- Time travel queries are not supported
- `OPTIMIZE` and `VACUUM` commands are not supported (managed automatically)
- **Null handling edge case**: `SUM()` on a nullable column returns **0** instead of `NULL` when all non-null values are removed
- Non-column expressions in the defining query require explicit aliases
- Underlying storage may contain upstream data not visible in the MV definition (required for incremental refresh)
- Cannot rename the MV or change its owner via ALTER (must drop and recreate)
- No data quality expectations support
- AWS PrivateLink requires contacting Databricks support

### DBSQL Materialized Views vs Pipeline (SDP/DLT) Materialized Views

| Aspect | DBSQL Materialized Views | Pipeline (SDP/DLT) Materialized Views |
|--------|-------------------------|--------------------------------------|
| **Creation** | `CREATE MATERIALIZED VIEW` in SQL warehouse | Defined in pipeline source code (SQL or Python) |
| **Pipeline type** | `MV/ST` (auto-created serverless pipeline) | `ETL` (explicitly defined pipeline) |
| **Pipeline management** | Automatically created and managed | User-defined, full pipeline lifecycle control |
| **Syntax** | Standard `CREATE MATERIALIZED VIEW` | `CREATE OR REFRESH MATERIALIZED VIEW` with `PRIVATE` option |
| **Private MVs** | Not supported | `PRIVATE` keyword for pipeline-scoped views |
| **Refresh trigger** | Schedule, trigger-on-update, manual, or job-based | Pipeline update (manual or scheduled) |
| **Compute** | Serverless SQL warehouse (creation); serverless pipeline (refresh) | Pipeline compute (serverless or classic) |
| **Data quality** | Not supported | Expectations supported |
| **Best for** | Standalone MVs, BI dashboard acceleration, simple ETL | Complex multi-table pipelines, orchestrated transformations |

Both approaches ultimately use similar underlying mechanisms (serverless pipelines) and support incremental refresh. The key difference is in management: DBSQL MVs are self-contained with auto-managed pipelines, while pipeline MVs are part of a broader orchestrated data flow.

### Best Practices

1. **Choose the right refresh strategy**: `TRIGGER ON UPDATE` for near-real-time SLA; `SCHEDULE` for predictable cadences; manual or job-based for complex orchestration
2. **Enable row tracking** on Delta source tables for cost-effective incremental refreshes
3. **Use async refreshes** when refresh duration is long and downstream queries can tolerate slight staleness
4. **Set explicit timeouts** when refresh duration is predictable to avoid runaway costs
5. **Use `CLUSTER BY AUTO`** for automatic liquid clustering optimization
6. **Apply row filters and column masks** at MV creation for security
7. **Monitor refresh types** with `EXPLAIN CREATE MATERIALIZED VIEW` to verify incremental behavior

---

## 2. Temporary Tables and Temporary Views

### Temporary Tables

Temporary tables are session-scoped, physical Delta tables for intermediate data storage. They exist only within the session where they are created.

#### Key Characteristics

- **Session-scoped**: Only visible to the creating session; isolated from other users
- **Physical storage**: Stored as Delta tables in an internal Unity Catalog location tied to the workspace
- **Maximum lifetime**: 7 days from session creation, or until the session ends (whichever comes first)
- **No catalog privileges needed**: Any user can create temporary tables without `CREATE TABLE` privileges
- **Automatic cleanup**: Databricks reclaims storage automatically, even after unexpected disconnections
- **Shared namespace**: Temporary tables share a namespace with temporary views; you cannot create both with the same name

#### Syntax

```sql
-- Create with schema
CREATE TEMPORARY TABLE temp_results (
  id INT,
  name STRING,
  score DOUBLE
);

-- Create from query (CTAS)
CREATE TEMP TABLE temp_active_users
AS SELECT user_id, username, last_login
FROM catalog.schema.users
WHERE last_login > current_date() - INTERVAL 30 DAYS;
```

Note: `CREATE OR REPLACE TEMP TABLE` is **not yet supported**. To replace, drop first.

#### Supported Operations

```sql
-- INSERT
INSERT INTO temp_results VALUES (1, 'Alice', 95.5);
INSERT INTO temp_results SELECT * FROM catalog.schema.source WHERE score > 90;

-- UPDATE
UPDATE temp_results SET score = 100.0 WHERE name = 'Alice';

-- MERGE
MERGE INTO temp_results t
USING catalog.schema.new_scores s ON t.id = s.id
WHEN MATCHED THEN UPDATE SET score = s.score
WHEN NOT MATCHED THEN INSERT *;
```

#### Unsupported Operations

- `DELETE FROM` (not supported)
- `ALTER TABLE` (drop and recreate instead)
- Shallow or deep cloning
- Time travel
- Streaming (foreachBatch)
- DataFrame API access (SQL only)

#### Use Cases

1. **Exploratory analysis**: Store intermediate results while iterating on queries
2. **Multi-step transformations**: Break complex transformations into readable steps
3. **Query result reuse**: Compute once, reference multiple times in a session
4. **Sandboxing**: Test transformations without affecting production tables

#### Name Resolution

When referencing a single-part table name, Databricks resolves in order:
1. Temporary tables in the current session
2. Permanent tables in the current schema

Temporary tables with the same name as permanent tables **take precedence** within that session.

### Temporary Views

Temporary views are session-scoped, logical views that store a query definition (not data). They are recomputed on each access.

#### Syntax

```sql
-- Create a temporary view
CREATE TEMPORARY VIEW active_customers
AS SELECT customer_id, name, email
FROM catalog.schema.customers
WHERE status = 'active';

-- Replace an existing temporary view
CREATE OR REPLACE TEMPORARY VIEW active_customers
AS SELECT customer_id, name, email, phone
FROM catalog.schema.customers
WHERE status = 'active' AND last_order > current_date() - INTERVAL 90 DAYS;
```

#### Key Rules

- Temporary view names **must not be qualified** (no catalog or schema prefix)
- No special privileges required to create
- Dropped automatically when the session ends
- Cannot use `schema_binding` clauses
- Support `COMMENT` and column comments

#### Global Temporary Views (Databricks Runtime Only)

```sql
-- Only available in Databricks Runtime, NOT in Databricks SQL
CREATE GLOBAL TEMPORARY VIEW global_summary
AS SELECT region, SUM(revenue) AS total_revenue
FROM catalog.schema.sales
GROUP BY region;

-- Must reference via global_temp schema
SELECT * FROM global_temp.global_summary;
```

Global temporary views are stored in a system `global_temp` schema and are session-scoped. They are **not available in Databricks SQL** (only Databricks Runtime).

### Temporary Tables vs Temporary Views

| Aspect | Temporary Tables | Temporary Views |
|--------|-----------------|-----------------|
| **Storage** | Physical Delta table (stores data) | Logical (stores query definition only) |
| **Compute on access** | No (data already materialized) | Yes (query re-executed each time) |
| **DML support** | INSERT, UPDATE, MERGE | None (read-only definition) |
| **Max lifetime** | 7 days or session end | Session end |
| **CREATE OR REPLACE** | Not supported | Supported |
| **Performance** | Faster for repeated reads (data cached) | Slower for repeated reads (recomputed) |
| **Storage cost** | Uses cloud storage (auto-cleaned) | No storage cost |
| **Shared namespace** | Yes (conflicts with temp views) | Yes (conflicts with temp tables) |
| **When to use** | Large intermediate results, repeated access, DML needed | Simple query aliases, lightweight transformations |

### Temporary Metric Views (Added September 2025)

```sql
-- Temporary metric views: session-scoped, dropped on session end
CREATE TEMPORARY METRIC VIEW session_metrics
AS SELECT ...;
```

Available in Databricks Runtime 17.2+ and Databricks SQL.

---

## 3. SQL Pipe Syntax

### Overview

Pipe syntax (introduced February 2025) allows composing SQL queries as a top-down, left-to-right chain of operations using the `|>` operator. It eliminates deeply nested subqueries and makes SQL read like a DataFrame pipeline.

**Requirements**: Databricks SQL or Databricks Runtime **16.2+**

### Basic Syntax

```sql
FROM table_name
|> pipe_operation_1
|> pipe_operation_2
|> pipe_operation_3;
```

Any query can start a pipeline. The most common pattern is `FROM table_name`, but any SELECT or subquery also works:

```sql
-- Start from a table
FROM catalog.schema.sales |> WHERE region = 'US' |> SELECT product, amount;

-- Start from a subquery
(SELECT * FROM catalog.schema.sales WHERE year = 2025)
|> AGGREGATE SUM(amount) AS total GROUP BY product
|> ORDER BY total DESC;
```

### All Available Pipe Operators

#### SELECT -- Project columns

```sql
FROM catalog.schema.employees
|> SELECT employee_id, name, department, salary;
```

Note: `SELECT` in pipe syntax **must not contain aggregate functions**. Use `AGGREGATE` instead.

#### EXTEND -- Add new columns

Appends new columns to the existing result set (like PySpark's `withColumn`):

```sql
FROM catalog.schema.orders
|> EXTEND quantity * unit_price AS line_total
|> EXTEND line_total * 0.1 AS tax;
```

Expressions can reference columns created by preceding expressions in the same EXTEND.

#### SET -- Modify existing columns

Overrides existing column values (like PySpark's `withColumn` on existing columns):

```sql
FROM catalog.schema.products
|> SET price = price * 1.1
|> SET name = UPPER(name);
```

Raises `UNRESOLVED_COLUMN` if the column does not exist.

#### DROP -- Remove columns

Removes columns (shorthand for `SELECT * EXCEPT`):

```sql
FROM catalog.schema.users
|> DROP password_hash, internal_id, debug_flag;
```

#### WHERE -- Filter rows

```sql
FROM catalog.schema.transactions
|> WHERE amount > 1000
|> WHERE transaction_date >= '2025-01-01';
```

#### AGGREGATE -- Aggregation with optional GROUP BY

```sql
-- Full-table aggregation
FROM catalog.schema.orders
|> AGGREGATE
     COUNT(*) AS total_orders,
     SUM(amount) AS total_revenue,
     AVG(amount) AS avg_order_value;

-- Grouped aggregation
FROM catalog.schema.orders
|> AGGREGATE
     SUM(amount) AS total_revenue,
     COUNT(*) AS order_count
   GROUP BY region, product_category;
```

In pipe syntax, `AGGREGATE` replaces `SELECT ... GROUP BY`. Numeric values in GROUP BY reference input columns, not generated results.

#### JOIN -- Combine relations

```sql
FROM catalog.schema.orders
|> AS o
|> LEFT JOIN catalog.schema.customers c ON o.customer_id = c.customer_id
|> SELECT o.order_id, c.name, o.amount;
```

All JOIN types are supported: `INNER JOIN`, `LEFT OUTER JOIN`, `RIGHT OUTER JOIN`, `FULL OUTER JOIN`, `CROSS JOIN`, `SEMI JOIN`, `ANTI JOIN`.

#### ORDER BY -- Sort results

```sql
FROM catalog.schema.products
|> ORDER BY price DESC, name ASC;
```

#### LIMIT and OFFSET -- Pagination

```sql
FROM catalog.schema.products
|> ORDER BY price DESC
|> LIMIT 10
|> OFFSET 20;
```

#### AS -- Assign table alias

Names the intermediate result for use in subsequent JOINs or self-references:

```sql
FROM catalog.schema.sales
|> AS current_sales
|> JOIN catalog.schema.targets t ON current_sales.region = t.region
|> SELECT current_sales.region, current_sales.revenue, t.target;
```

#### Set Operators -- UNION, EXCEPT, INTERSECT

```sql
FROM catalog.schema.us_customers
|> UNION ALL (SELECT * FROM catalog.schema.eu_customers)
|> ORDER BY name;
```

#### TABLESAMPLE -- Sample rows

```sql
-- Sample by row count
FROM catalog.schema.large_table
|> TABLESAMPLE (1000 ROWS);

-- Sample by percentage
FROM catalog.schema.large_table
|> TABLESAMPLE (10 PERCENT);
```

#### PIVOT -- Rows to columns

```sql
FROM catalog.schema.quarterly_sales
|> PIVOT (
     SUM(revenue)
     FOR quarter IN ('Q1', 'Q2', 'Q3', 'Q4')
   );
```

#### UNPIVOT -- Columns to rows

```sql
FROM catalog.schema.wide_metrics
|> UNPIVOT (
     metric_value FOR metric_name IN (cpu_usage, memory_usage, disk_usage)
   );
```

### Practical Examples

#### Example 1: Multi-step aggregation (replaces nested subqueries)

Traditional SQL:
```sql
SELECT c_count, COUNT(*) AS custdist
FROM (
  SELECT c_custkey, COUNT(o_orderkey) AS c_count
  FROM customer
  LEFT OUTER JOIN orders ON c_custkey = o_custkey
    AND o_comment NOT LIKE '%unusual%packages%'
  GROUP BY c_custkey
) AS c_orders
GROUP BY c_count
ORDER BY custdist DESC, c_count DESC;
```

Pipe syntax:
```sql
FROM customer
|> LEFT OUTER JOIN orders ON c_custkey = o_custkey
   AND o_comment NOT LIKE '%unusual%packages%'
|> AGGREGATE COUNT(o_orderkey) AS c_count GROUP BY c_custkey
|> AGGREGATE COUNT(*) AS custdist GROUP BY c_count
|> ORDER BY custdist DESC, c_count DESC;
```

#### Example 2: Data exploration and profiling

```sql
FROM catalog.schema.raw_events
|> WHERE event_date >= '2025-01-01'
|> EXTEND YEAR(event_date) AS event_year, MONTH(event_date) AS event_month
|> AGGREGATE
     COUNT(*) AS event_count,
     COUNT(DISTINCT user_id) AS unique_users,
     AVG(duration_seconds) AS avg_duration
   GROUP BY event_year, event_month
|> ORDER BY event_year, event_month;
```

#### Example 3: Building a report step-by-step

```sql
FROM catalog.schema.orders
|> AS o
|> JOIN catalog.schema.products p ON o.product_id = p.product_id
|> JOIN catalog.schema.customers c ON o.customer_id = c.customer_id
|> WHERE o.order_date >= '2025-01-01'
|> EXTEND o.quantity * p.unit_price AS line_total
|> AGGREGATE
     SUM(line_total) AS total_revenue,
     COUNT(DISTINCT o.order_id) AS order_count
   GROUP BY c.region, p.category
|> ORDER BY total_revenue DESC
|> LIMIT 20;
```

#### Example 4: Debugging by commenting out tail operations

```sql
FROM catalog.schema.sales
|> WHERE region = 'US'
|> EXTEND amount * tax_rate AS tax_amount
-- |> AGGREGATE SUM(tax_amount) AS total_tax GROUP BY state
-- |> ORDER BY total_tax DESC
;
-- Comment out the last operations to inspect intermediate results
```

### Pipe Syntax vs Traditional SQL

| Aspect | Traditional SQL | Pipe SQL |
|--------|----------------|----------|
| **Reading order** | Inside-out (subqueries first) | Top-down, left-to-right |
| **Clause order** | Fixed: SELECT...FROM...WHERE...GROUP BY...ORDER BY | Any order, any number of times |
| **Subquery nesting** | Required for multi-step aggregations | Eliminated via chaining |
| **Column addition** | SELECT *, expr AS new_col | `EXTEND expr AS new_col` |
| **Column removal** | SELECT with explicit column list or EXCEPT | `DROP col1, col2` |
| **Column modification** | SELECT with expression replacing column | `SET col = new_expr` |
| **Aggregation** | SELECT agg() ... GROUP BY | `AGGREGATE agg() GROUP BY` |
| **Composability** | Limited; requires CTEs or subqueries | Native chaining |
| **Interoperability** | Standard | Fully interoperable with traditional SQL |

### When to Use Pipe Syntax

**Use pipe syntax when:**
- Multi-step aggregations would require nested subqueries
- You want DataFrame-like readability in SQL
- Building exploratory or iterative queries (easy to add/remove steps)
- Complex transformations with many joins, filters, and projections

**Use traditional SQL when:**
- Simple queries that are already readable
- Team is more familiar with standard SQL
- Queries will be shared with tools that may not support pipe syntax

### Performance Considerations

- Pipe syntax is **syntactic sugar** -- it compiles to the same execution plan as traditional SQL
- No performance difference between pipe and traditional syntax for equivalent queries
- Best practice: Place data-reducing operations (`WHERE`, `DROP`, `SELECT`) early in the pipeline to minimize data flowing through subsequent operations
- Use `TABLESAMPLE` during development to work with smaller datasets

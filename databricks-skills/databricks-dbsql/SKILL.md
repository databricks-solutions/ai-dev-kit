---
name: databricks-dbsql
description: >-
  Databricks SQL (DBSQL) advanced features and SQL warehouse capabilities.
  This skill MUST be invoked when the user mentions: "DBSQL", "Databricks SQL",
  "SQL warehouse", "SQL scripting", "stored procedure", "CALL procedure",
  "materialized view", "CREATE MATERIALIZED VIEW", "pipe syntax", "|>",
  "geospatial", "H3", "ST_", "spatial SQL", "collation", "COLLATE",
  "ai_query", "ai_classify", "ai_extract", "ai_gen", "AI function",
  "http_request", "remote_query", "read_files", "Lakehouse Federation",
  "recursive CTE", "WITH RECURSIVE", "multi-statement transaction",
  "temp table", "temporary view", "pipe operator".
  SHOULD also invoke when the user asks about SQL best practices, data modeling
  patterns, or advanced SQL features on Databricks.
---

# Databricks SQL (DBSQL) - Advanced Features

## Quick Reference

| Feature | Key Syntax | Since | Reference |
|---------|-----------|-------|-----------|
| SQL Scripting | `BEGIN...END`, `DECLARE`, `IF/WHILE/FOR` | DBR 16.3+ | [sql-scripting.md](sql-scripting.md) |
| Stored Procedures | `CREATE PROCEDURE`, `CALL` | DBR 17.0+ | [sql-scripting.md](sql-scripting.md) |
| Recursive CTEs | `WITH RECURSIVE` | DBR 17.0+ | [sql-scripting.md](sql-scripting.md) |
| Transactions | `BEGIN ATOMIC...END` | Preview | [sql-scripting.md](sql-scripting.md) |
| Materialized Views | `CREATE MATERIALIZED VIEW` | Pro/Serverless | [materialized-views-pipes.md](materialized-views-pipes.md) |
| Temp Tables | `CREATE TEMPORARY TABLE` | All | [materialized-views-pipes.md](materialized-views-pipes.md) |
| Pipe Syntax | `\|>` operator | DBR 16.1+ | [materialized-views-pipes.md](materialized-views-pipes.md) |
| Geospatial (H3) | `h3_longlatash3()`, `h3_polyfillash3()` | DBR 11.2+ | [geospatial-collations.md](geospatial-collations.md) |
| Geospatial (ST) | `ST_Point()`, `ST_Contains()`, 80+ funcs | DBR 16.0+ | [geospatial-collations.md](geospatial-collations.md) |
| Collations | `COLLATE`, `UTF8_LCASE`, locale-aware | DBR 16.1+ | [geospatial-collations.md](geospatial-collations.md) |
| AI Functions | `ai_query()`, `ai_classify()`, 11+ funcs | DBR 15.1+ | [ai-functions.md](ai-functions.md) |
| http_request | `http_request(conn, ...)` | Pro/Serverless | [ai-functions.md](ai-functions.md) |
| remote_query | `SELECT * FROM remote_query(...)` | Pro/Serverless | [ai-functions.md](ai-functions.md) |
| read_files | `SELECT * FROM read_files(...)` | All | [ai-functions.md](ai-functions.md) |
| Data Modeling | Star schema, Liquid Clustering | All | [best-practices.md](best-practices.md) |

---

## Common Patterns

### SQL Scripting - Procedural ETL

```sql
BEGIN
  DECLARE v_count INT;
  DECLARE v_status STRING DEFAULT 'pending';

  SET v_count = (SELECT COUNT(*) FROM catalog.schema.raw_orders WHERE status = 'new');

  IF v_count > 0 THEN
    INSERT INTO catalog.schema.processed_orders
    SELECT *, current_timestamp() AS processed_at
    FROM catalog.schema.raw_orders
    WHERE status = 'new';

    SET v_status = 'completed';
  ELSE
    SET v_status = 'skipped';
  END IF;

  SELECT v_status AS result, v_count AS rows_processed;
END
```

### Stored Procedure with Error Handling

```sql
CREATE OR REPLACE PROCEDURE catalog.schema.upsert_customers(
  IN p_source STRING,
  OUT p_rows_affected INT
)
LANGUAGE SQL
SQL SECURITY INVOKER
BEGIN
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    SET p_rows_affected = -1;
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = concat('Upsert failed for source: ', p_source);
  END;

  MERGE INTO catalog.schema.dim_customer AS t
  USING (SELECT * FROM identifier(p_source)) AS s
  ON t.customer_id = s.customer_id
  WHEN MATCHED THEN UPDATE SET *
  WHEN NOT MATCHED THEN INSERT *;

  SET p_rows_affected = (SELECT COUNT(*) FROM identifier(p_source));
END;

-- Invoke:
CALL catalog.schema.upsert_customers('catalog.schema.staging_customers', ?);
```

### Materialized View with Scheduled Refresh

```sql
CREATE OR REPLACE MATERIALIZED VIEW catalog.schema.daily_revenue
  CLUSTER BY (order_date)
  SCHEDULE EVERY 1 HOUR
  COMMENT 'Hourly-refreshed daily revenue by region'
AS SELECT
    order_date,
    region,
    SUM(amount) AS total_revenue,
    COUNT(DISTINCT customer_id) AS unique_customers
FROM catalog.schema.fact_orders
JOIN catalog.schema.dim_store USING (store_id)
GROUP BY order_date, region;
```

### Pipe Syntax - Readable Transformations

```sql
-- Traditional SQL rewritten with pipe syntax
FROM catalog.schema.fact_orders
  |> WHERE order_date >= current_date() - INTERVAL 30 DAYS
  |> AGGREGATE SUM(amount) AS total, COUNT(*) AS cnt GROUP BY region, product_category
  |> WHERE total > 10000
  |> ORDER BY total DESC
  |> LIMIT 20;
```

### AI Functions - Enrich Data with LLMs

```sql
-- Classify support tickets
SELECT
  ticket_id,
  description,
  ai_classify(description, ARRAY('billing', 'technical', 'account', 'feature_request')) AS category,
  ai_analyze_sentiment(description) AS sentiment
FROM catalog.schema.support_tickets
LIMIT 100;

-- Extract entities from text
SELECT
  doc_id,
  ai_extract(content, ARRAY('person_name', 'company', 'dollar_amount')) AS entities
FROM catalog.schema.contracts;

-- General-purpose AI query with structured output
SELECT ai_query(
  'databricks-meta-llama-3-3-70b-instruct',
  concat('Summarize this customer feedback in JSON with keys: topic, sentiment, action_items. Feedback: ', feedback),
  returnType => 'STRUCT<topic STRING, sentiment STRING, action_items ARRAY<STRING>>'
) AS analysis
FROM catalog.schema.customer_feedback
LIMIT 50;
```

### Geospatial - Proximity Search with H3

```sql
-- Find stores within 5km of each customer using H3 indexing
WITH customer_h3 AS (
  SELECT *, h3_longlatash3(longitude, latitude, 7) AS h3_cell
  FROM catalog.schema.customers
),
store_h3 AS (
  SELECT *, h3_longlatash3(longitude, latitude, 7) AS h3_cell
  FROM catalog.schema.stores
)
SELECT
  c.customer_id,
  s.store_id,
  ST_Distance(
    ST_Point(c.longitude, c.latitude),
    ST_Point(s.longitude, s.latitude)
  ) AS distance_m
FROM customer_h3 c
JOIN store_h3 s ON h3_ischildof(c.h3_cell, h3_toparent(s.h3_cell, 5))
WHERE ST_Distance(
  ST_Point(c.longitude, c.latitude),
  ST_Point(s.longitude, s.latitude)
) < 5000;
```

### Collation - Case-Insensitive Search

```sql
-- Create table with case-insensitive collation
CREATE TABLE catalog.schema.products (
  product_id BIGINT GENERATED ALWAYS AS IDENTITY,
  name STRING COLLATE UTF8_LCASE,
  category STRING COLLATE UTF8_LCASE,
  price DECIMAL(10, 2)
);

-- Queries automatically case-insensitive (no LOWER() needed)
SELECT * FROM catalog.schema.products
WHERE name = 'MacBook Pro';  -- matches 'macbook pro', 'MACBOOK PRO', etc.
```

### http_request - Call External APIs

```sql
-- Set up connection first (one-time)
CREATE CONNECTION my_api_conn
  TYPE HTTP
  OPTIONS (host 'https://api.example.com', bearer_token secret('scope', 'token'));

-- Call API from SQL
SELECT
  order_id,
  http_request(
    conn => 'my_api_conn',
    method => 'POST',
    path => '/v1/validate',
    json => to_json(named_struct('order_id', order_id, 'amount', amount))
  ).text AS api_response
FROM catalog.schema.orders
WHERE needs_validation = true;
```

### read_files - Ingest Raw Files

```sql
-- Read JSON files from a Volume with schema hints
SELECT *
FROM read_files(
  '/Volumes/catalog/schema/raw/events/',
  format => 'json',
  schemaHints => 'event_id STRING, timestamp TIMESTAMP, payload MAP<STRING, STRING>',
  pathGlobFilter => '*.json',
  recursiveFileLookup => true
);

-- Read CSV with options
SELECT *
FROM read_files(
  '/Volumes/catalog/schema/raw/sales/',
  format => 'csv',
  header => true,
  delimiter => '|',
  dateFormat => 'yyyy-MM-dd',
  schema => 'sale_id INT, sale_date DATE, amount DECIMAL(10,2), store STRING'
);
```

### Recursive CTE - Hierarchy Traversal

```sql
WITH RECURSIVE org_chart AS (
  -- Anchor: top-level managers
  SELECT employee_id, name, manager_id, 0 AS depth, ARRAY(name) AS path
  FROM catalog.schema.employees
  WHERE manager_id IS NULL

  UNION ALL

  -- Recursive: direct reports
  SELECT e.employee_id, e.name, e.manager_id, o.depth + 1, array_append(o.path, e.name)
  FROM catalog.schema.employees e
  JOIN org_chart o ON e.manager_id = o.employee_id
  WHERE o.depth < 10  -- safety limit
)
SELECT * FROM org_chart ORDER BY depth, name;
```

### remote_query - Federated Queries

```sql
-- Query PostgreSQL via Lakehouse Federation
SELECT *
FROM remote_query(
  'my_postgres_connection',
  database => 'my_database',
  query    => 'SELECT customer_id, email, created_at FROM customers WHERE active = true'
);
```

---

## Reference Files

Load these for detailed syntax, full parameter lists, and advanced patterns:

| File | Contents | When to Read |
|------|----------|--------------|
| [sql-scripting.md](sql-scripting.md) | SQL Scripting, Stored Procedures, Recursive CTEs, Transactions | User needs procedural SQL, error handling, loops, dynamic SQL |
| [materialized-views-pipes.md](materialized-views-pipes.md) | Materialized Views, Temp Tables/Views, Pipe Syntax | User needs MVs, refresh scheduling, temp objects, pipe operator |
| [geospatial-collations.md](geospatial-collations.md) | 39 H3 functions, 80+ ST functions, Collation types and hierarchy | User needs spatial analysis, H3 indexing, case/accent handling |
| [ai-functions.md](ai-functions.md) | 13 AI functions, http_request, remote_query, read_files (all options) | User needs AI enrichment, API calls, federation, file ingestion |
| [best-practices.md](best-practices.md) | Data modeling, performance, Liquid Clustering, anti-patterns | User needs architecture guidance, optimization, or modeling advice |

---

## Key Guidelines

- **Always use Serverless SQL warehouses** for AI functions, MVs, and http_request
- **Use `LIMIT` during development** with AI functions to control costs
- **Prefer Liquid Clustering over partitioning** for new tables (1-4 keys max)
- **Use `CLUSTER BY AUTO`** when unsure about clustering keys
- **Star schema in Gold layer** for BI; OBT acceptable in Silver
- **Define PK/FK constraints** on dimensional models for query optimization
- **Use `COLLATE UTF8_LCASE`** for user-facing string columns that need case-insensitive search
- **Use MCP tools** (`execute_sql`, `execute_sql_multi`) to test and validate all SQL before deploying

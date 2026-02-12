# Data Modeling and DBSQL Best Practices

Comprehensive reference for data modeling patterns, DBSQL performance optimization, and operational best practices on the Databricks Lakehouse Platform.

---

## Data Modeling Best Practices

### Star Schema vs Denormalization in the Lakehouse

The Databricks Lakehouse fully supports dimensional modeling. Star schemas translate well to Delta tables and often deliver superior performance compared to fully denormalized approaches.

**Star Schema (Dimensional Modeling):**
- Central fact table linked to multiple denormalized dimension tables
- Optimizes for complex analytics and multi-dimensional aggregations
- Provides intuitive business process mapping and scales well with SCDs
- Supports up to ~10 filtering dimensions (5 tables x 2 clustering keys each)
- Clear separation of concerns enables fine-grained governance

**One Big Table (OBT):**
- Single wide table with all attributes pre-joined
- Eliminates joins, simpler governance (one table to manage)
- Liquid Clustering limited to 1-4 keys, so effective filtering is limited to 1-3 dimensions
- Full table scans become bottlenecks as data grows
- Lacks structured business process mapping
- Complicates fine-grained access controls and data quality checks

**Key finding:** In benchmarks, dimensional models outperformed OBT (2.6s vs 3.5s) despite requiring joins, because fewer files needed to be scanned. However, with Liquid Clustering applied, OBT achieved >3x improvement (down to 1.13s). Both approaches achieve sub-500ms with automatic caching.

**Recommended approach:** Use a hybrid medallion architecture:
- Silver layer: OBT or Data Vault for rapid integration and cleansing
- Gold layer: Star schema dimensional models as the curated, business-ready presentation layer for BI and reporting

### When to Normalize vs Denormalize

| Use Case | Approach |
|---|---|
| Gold layer for BI reporting | Star schema (denormalized dimensions, normalized facts) |
| Silver layer data integration | Normalized or Data Vault |
| Single-use IoT/logging analytics | OBT (filter by 1-3 dimensions) |
| Multi-dimensional business analysis | Star schema |
| Rapidly evolving schemas | OBT in Silver, star schema in Gold |
| High-cardinality filtering (5+ dimensions) | Star schema with Liquid Clustering per table |

**Rule of thumb:** Dimension tables should be highly denormalized (flatten many-to-one relationships within a single dimension table). Fact tables should remain normalized at the grain of the business event.

### Kimball-Style Modeling in Databricks

Kimball dimensional modeling is the recommended approach for the Gold layer in the Lakehouse:

1. **Identify the business process** (sales, orders, shipments)
2. **Declare the grain** (one row per transaction, per day, etc.)
3. **Choose dimensions** (who, what, where, when, why, how)
4. **Identify facts** (measurable numeric values at the declared grain)

**Databricks-specific implementation details:**
- Use Unity Catalog for organizing dimensional models (catalog.schema.table)
- Define PRIMARY KEY constraints on dimension surrogate keys
- Define FOREIGN KEY constraints on fact table dimension keys for query optimization
- Add COMMENT on all tables and columns for discoverability
- Apply TAGS for governance (e.g., PII tagging) to enable downstream AI/BI capabilities
- Use `ANALYZE TABLE ... COMPUTE STATISTICS FOR COLUMNS` on dimension keys to support Adaptive Query Execution

**Key principle:** "The better you model your data upfront, the more easily you can leverage AI on top of it out of the box." Proper schema design enables downstream AI/BI capabilities.

### Fact Table Patterns

**Design rules:**
- Store quantitative, numeric measures at the most granular transactional level
- Use DECIMAL instead of floating-point numbers for financial data
- Include foreign keys referencing dimension tables
- Include degenerate dimensions (source-system identifiers like order numbers)
- Transactional fact tables are typically not updated or versioned
- Cluster fact tables by foreign keys to frequently joined dimensions

**Types of fact tables:**
- **Transaction facts:** One row per event (most common)
- **Periodic snapshot facts:** One row per entity per time period
- **Accumulating snapshot facts:** One row per entity lifecycle, updated as milestones are reached

**Fact table Liquid Clustering strategy:**
```sql
CREATE TABLE gold.sales.fact_orders (
  order_key BIGINT GENERATED ALWAYS AS IDENTITY,
  customer_key BIGINT NOT NULL,
  product_key BIGINT NOT NULL,
  date_key INT NOT NULL,
  order_amount DECIMAL(18,2),
  quantity INT,
  CONSTRAINT fk_customer FOREIGN KEY (customer_key) REFERENCES gold.sales.dim_customer(customer_key),
  CONSTRAINT fk_product FOREIGN KEY (product_key) REFERENCES gold.sales.dim_product(product_key)
)
CLUSTER BY (date_key, customer_key);
```

### Dimension Table Patterns

**Design rules:**
- Use `GENERATED ALWAYS AS IDENTITY` or hash values for surrogate keys
- Prefer integer surrogate keys over strings for join performance
- Highly denormalize: flatten many-to-one relationships within a single dimension table
- Support complex types: MAP for extensibility, STRUCT for nested attributes, ARRAY for multi-valued attributes
- Avoid using ARRAY/MAP columns as filter predicates (they lack column-level statistics for data skipping)
- Cluster dimension tables by primary key plus common filter columns

**Dimension table example:**
```sql
CREATE TABLE gold.sales.dim_customer (
  customer_key BIGINT GENERATED ALWAYS AS IDENTITY,
  customer_id STRING NOT NULL COMMENT 'Natural key from source system',
  full_name STRING,
  email STRING,
  city STRING,
  state STRING,
  country STRING,
  segment STRING,
  effective_start_date TIMESTAMP,
  effective_end_date TIMESTAMP,
  is_current BOOLEAN,
  CONSTRAINT pk_customer PRIMARY KEY (customer_key)
)
CLUSTER BY (customer_key, segment)
COMMENT 'Customer dimension with SCD Type 2 history tracking';
```

### Slowly Changing Dimensions (SCD) Patterns

**SCD Type 1 (Overwrite):**
- In-place updates without tracking history
- Use MERGE INTO with matched UPDATE
- Suitable for corrections or attributes where history is not needed

**SCD Type 2 (History Tracking):**
- Version records with surrogate keys and metadata columns
- Include `effective_start_date`, `effective_end_date`, and `is_current` columns
- Use MERGE INTO for implementing SCD Type 2 logic in DBSQL

**SCD Type 2 with MERGE:**
```sql
MERGE INTO gold.sales.dim_customer AS target
USING (
  SELECT * FROM silver.crm.customers_changes
) AS source
ON target.customer_id = source.customer_id AND target.is_current = TRUE
WHEN MATCHED AND (
  target.full_name != source.full_name OR
  target.city != source.city
) THEN UPDATE SET
  effective_end_date = current_timestamp(),
  is_current = FALSE
WHEN NOT MATCHED THEN INSERT (
  customer_id, full_name, email, city, state, country, segment,
  effective_start_date, effective_end_date, is_current
) VALUES (
  source.customer_id, source.full_name, source.email,
  source.city, source.state, source.country, source.segment,
  current_timestamp(), NULL, TRUE
);
-- Then insert new versions for changed records in a second pass
```

**Delta Lake Time Travel** enables historical data access within configured log retention periods as a complementary feature to SCD.

### Partitioning Strategies

**Databricks recommends Liquid Clustering over traditional partitioning for all new tables.**

Traditional partitioning rules of thumb (when needed):
- Keep partition count under 10,000 (ideally under 5,000 distinct values)
- Each partition should contain at least 1 GB of data
- Partition by low-cardinality columns that are frequently used in WHERE clauses (e.g., date, region)
- Works best for highly selective single-partition queries (e.g., filter on one day)

**When traditional partitioning may still be appropriate:**
- Very large tables (hundreds of terabytes) with a clear, stable partition key
- Queries consistently filter on the same low-cardinality column
- Data lifecycle management requires partition-level operations

### Liquid Clustering vs Traditional Partitioning

**Liquid Clustering is the default recommendation for all new Delta tables**, including streaming tables and materialized views. It replaces both partitioning and Z-ORDER.

| Aspect | Liquid Clustering | Partitioning + Z-ORDER |
|---|---|---|
| Column flexibility | Change clustering keys anytime | Partition column fixed at creation |
| Maintenance | Incremental, automatic with predictive optimization | Manual OPTIMIZE + Z-ORDER required |
| Filter dimensions | Best with 1-4 clustering keys | One partition key + Z-ORDER columns |
| Write overhead | Minimal (only unclustered ZCubes reorganized) | Z-ORDER reorganizes entire table/partition |
| Best for | Most workloads, evolving access patterns | Very large tables with stable, low-cardinality filter |
| Performance | 30-60% query speed improvement for variable queries | Better for single-partition lookup queries |

**Liquid Clustering key selection best practices:**
- Choose columns most frequently used in query filters and joins
- Limit to 1-4 keys (fewer is better for smaller tables under 10 TB)
- For fact tables: cluster by the most commonly filtered foreign keys
- For dimension tables: cluster by primary key + common filter columns
- Too many keys dilute data skipping benefits; for tables under 10 TB, 2 keys often outperform 4

**Important:** Liquid Clustering is not compatible with partitioning or Z-ORDER on the same table.

### Z-Ordering Considerations

Z-ORDER is the legacy approach, now superseded by Liquid Clustering:

- Z-ORDER reorganizes the entire table/partition during optimization (heavier writes)
- Does not track ZCube IDs, so every OPTIMIZE re-sorts all data
- Better suited for read-heavy workloads where write overhead is acceptable
- For new tables, always prefer Liquid Clustering

**Migration path:** When migrating existing partitioned + Z-ORDERed tables to Liquid Clustering:
1. Drop the partition specification
2. Enable Liquid Clustering with chosen keys
3. Run OPTIMIZE to incrementally cluster data
4. Allow predictive optimization to maintain layout going forward

---

## DBSQL Performance

### Query Optimization Tips

**Engine-level optimizations (automatic in DBSQL Serverless):**
- **Predictive Query Execution (PQE):** Monitors tasks in real time, dynamically adjusts query execution to avoid skew, spills, and unnecessary work. Unlike Adaptive Query Execution (AQE) which re-plans only after a stage completes, PQE detects issues like data skew or memory spills as they occur and replans immediately.
- **Photon Vectorized Shuffle:** Keeps data in compact columnar format, sorts within CPU cache, and uses vectorized instructions for 1.5x higher shuffle throughput. Best for CPU-bound workloads (large joins, wide aggregations).
- **Low Shuffle Merge:** Optimized MERGE implementation that reduces shuffle overhead for most common workloads.

**Manual optimization actions:**
- Run `ANALYZE TABLE ... COMPUTE STATISTICS FOR COLUMNS` on dimension keys and frequently filtered columns to support AQE and data skipping
- Set `'delta.dataSkippingStatsColumns'` table property to specify which columns collect statistics
- Define PRIMARY KEY and FOREIGN KEY constraints to help the query optimizer
- Use deterministic queries (avoid `NOW()`, `CURRENT_TIMESTAMP()` in filters) to benefit from query result caching
- Prefer `CREATE OR REPLACE TABLE` over delete-then-create patterns
- Use `DECIMAL` over `FLOAT`/`DOUBLE` for financial calculations

**SQL writing tips for DBSQL:**
- Filter early, aggregate late: push WHERE clauses as close to the source as possible
- Prefer explicit column lists over SELECT *
- Use CTEs for readability but be aware the optimizer may inline them
- Avoid Python/Scala UDFs when native SQL functions exist (UDFs require serialization between Python and Spark, significantly slowing queries)
- Use window functions instead of self-joins where possible
- Leverage QUALIFY clause for row-level filtering after window functions

### Warehouse Sizing Guidance

**Databricks recommends serverless SQL warehouses for most workloads.** Serverless uses Intelligent Workload Management (IWM) to automatically manage query workloads.

**Sizing strategy:**
- Start with a single larger warehouse and let serverless features manage concurrency
- Size down if needed rather than starting small and scaling up
- If queries spill to disk, increase the cluster size

**Scaling configuration:**
- Low concurrency (1-2 queries): keep max_clusters low
- Unpredictable spikes: set max_num_clusters high with target_utilization ~70%
- For dashboards with variable/infrequent load: enable aggressive auto-scaling and auto-stopping

**Serverless advantages:**
- Start and scale up in seconds
- Scale down earlier than non-serverless warehouses
- Pay only when queries are running
- 30-60 second cold start latency (savings from no idle time far outweigh this)
- All 2025 optimizations (PQE, Photon Vectorized Shuffle) are automatically available

### Caching Strategies

**Query Result Cache:**
- DBSQL caches results per-cluster for all queries
- Cache is invalidated when underlying Delta data changes
- To maximize cache hits, use deterministic queries (no `NOW()`, `RAND()`, etc.)
- Both OBT and star schema achieve sub-500ms with automatic caching after first run

**Delta Cache (Disk Cache):**
- Automatically caches remote data on local SSD in columnar format
- Accelerates data reads without manual configuration on serverless warehouses
- Particularly effective for repeated scans of the same tables

**Best practice:** Design dashboards and reports to use parameterized queries that hit the same underlying patterns, maximizing cache reuse.

### Photon Engine Benefits

Photon is a vectorized query engine written in C++ that runs natively on Databricks:

- Enabled by default on all DBSQL serverless warehouses
- Processes data in columnar batches using CPU vector instructions (SIMD)
- Excels at: large joins, wide aggregations, string processing, data shuffles
- 2025 vectorized shuffle delivers 1.5x higher shuffle throughput
- Combined with PQE, delivers up to 25% faster queries on top of existing 5x gains

### Recent Performance Improvements (2025)

| Improvement | Impact |
|---|---|
| Overall production workloads | Up to 40% faster (automatic, no tuning) |
| Photon Vectorized Shuffle | 1.5x higher shuffle throughput |
| PQE + Photon Vectorized Shuffle combined | Up to 25% faster on top of existing 5x gains |
| Spatial SQL queries | Up to 17x faster (R-tree indexing, optimized spatial joins) |
| AI functions | Up to 85x faster for large batch workloads |
| End-to-end Unity Catalog latency | Up to 10x improvement |
| 3-year cumulative improvement | 5x faster across customer workloads |

All improvements are live in DBSQL Serverless with nothing to enable.

### Cost Optimization Patterns

1. **Use serverless SQL warehouses:** Pay only when queries run, auto-scale and auto-stop
2. **Enable predictive optimization:** Automatically runs OPTIMIZE and VACUUM on Unity Catalog managed tables
3. **Right-size warehouses:** Start larger, scale down based on actual usage patterns
4. **Avoid idle warehouses:** Use aggressive auto-stop for dashboards with infrequent load
5. **Leverage caching:** Design deterministic queries to maximize result cache hits
6. **Use Liquid Clustering:** Reduces scan volume, fewer DBUs consumed per query
7. **Collect statistics:** `ANALYZE TABLE` enables better query plans, reducing wasted compute
8. **Monitor with Query Profile:** Identify expensive operations, spills, and skew
9. **Use materialized views** for frequently computed aggregations
10. **Avoid UDFs:** Native functions are dramatically faster, no serialization overhead

---

## Delta Lake Optimization for DBSQL

### OPTIMIZE, VACUUM, and ANALYZE

**Recommended execution order:** OPTIMIZE -> VACUUM -> ANALYZE

**OPTIMIZE:**
- Compacts small files into larger ones (target 1 GB by default)
- Run frequently on tables with many small files (especially after streaming writes)
- Configurable target size via `delta.targetFileSize` table property
- With Liquid Clustering: only reorganizes unclustered ZCubes (incremental)

**VACUUM:**
- Removes old files no longer in the transaction log
- Reduces storage costs
- Use compute-optimized instances (AWS C5, Azure F-series, GCP C2)
- Default retention: 7 days (configurable via `delta.deletedFileRetentionDuration`)
- Never set retention below the longest-running query duration

**ANALYZE TABLE:**
- Computes column-level statistics for query optimization
- Run immediately after table overwrites or major data changes
- Focus on columns used in WHERE clauses, JOINs, and GROUP BY

**Predictive optimization (recommended):**

> **Note:** On serverless SQL warehouses, `delta.enableOptimizeWrite` and `delta.autoOptimize.autoCompact` are managed automatically and cannot be set manually (they will raise `DELTA_UNKNOWN_CONFIGURATION`). The properties below apply only to classic compute. For serverless, simply enable predictive optimization at the catalog/schema level.

```sql
-- Classic compute only:
ALTER TABLE catalog.schema.table_name
SET TBLPROPERTIES ('delta.enableOptimizeWrite' = 'true');
-- For Unity Catalog managed tables, predictive optimization
-- handles OPTIMIZE and VACUUM automatically
```

### File Size and Compaction

- **Auto-compaction:** Combines small files within partitions automatically after writes
- **Optimized writes:** Rebalances data via shuffle before writing to reduce small files
- **Target file size:** Default 1 GB; adjust with `delta.targetFileSize` for specific workloads
- For tables with many small files (streaming ingestion), schedule regular OPTIMIZE jobs

### Table Properties for Performance

> **Note:** `delta.enableOptimizeWrite` and `delta.autoOptimize.autoCompact` are only valid on classic compute. On serverless SQL warehouses, these are managed automatically and setting them raises `DELTA_UNKNOWN_CONFIGURATION`. The remaining properties work on both classic and serverless.

```sql
-- Classic compute only (serverless manages these automatically):
-- 'delta.enableOptimizeWrite' = 'true',
-- 'delta.autoOptimize.autoCompact' = 'true',

-- Works on both classic and serverless:
ALTER TABLE catalog.schema.my_table SET TBLPROPERTIES (
  'delta.columnMapping.mode' = 'name',
  'delta.enableChangeDataFeed' = 'true',
  'delta.deletedFileRetentionDuration' = '30 days',
  'delta.dataSkippingStatsColumns' = 'col1,col2,col3'
);
```

---

## Unity Catalog Integration Patterns

### Organization Best Practices

- Use a three-level namespace: `catalog.schema.table`
- Organize by environment (dev/staging/prod) at the catalog level
- Organize by business domain at the schema level
- Use managed tables (not external) to benefit from predictive optimization and enhanced governance

### Governance Features for Data Modeling

- **Primary/Foreign Key constraints:** Inform the query optimizer about table relationships
- **Row filters and column masks:** Fine-grained access control at the table level
- **Tags:** Apply governance tags (e.g., PII, sensitivity level) to tables and columns
- **Comments:** Document all tables and columns for AI/BI discoverability
- **Lineage tracking:** Automatic lineage for understanding data flow through the medallion architecture

### Entity Relationship Visualization

Unity Catalog renders entity relationship diagrams when primary and foreign key constraints are defined, providing visual documentation of the dimensional model.

---

## Monitoring and Observability

- **Query Profile:** Analyze execution plans, identify bottlenecks, spills, and data skew
- **Query History:** Track query performance trends over time
- **Warehouse monitoring:** Track utilization, queue times, and scaling events
- **System tables:** Query `system.billing`, `system.access`, and `system.query` for operational insights
- **Alerts:** Set up SQL alerts for data quality checks and SLA monitoring

---

## Common Anti-Patterns to Avoid

### Data Modeling Anti-Patterns

1. **Skipping dimensional modeling in Gold layer:** OBTs are fine for Silver, but Gold should use star schemas for multi-dimensional analysis
2. **Over-partitioning:** More than 5,000-10,000 partitions degrades performance; use Liquid Clustering instead
3. **String surrogate keys:** Use integer IDENTITY columns for better join performance
4. **Missing constraints:** Not defining PK/FK constraints deprives the optimizer of relationship information
5. **Missing comments and tags:** Reduces discoverability for AI/BI tools and governance
6. **Using FLOAT for financial data:** Use DECIMAL to avoid precision errors
7. **Filtering on ARRAY/MAP columns:** These types lack column-level statistics for data skipping

### Query and Performance Anti-Patterns

1. **Delete-then-recreate tables:** Use `CREATE OR REPLACE TABLE` instead to preserve time travel and avoid reader interruptions
2. **Python/Scala UDFs when native functions exist:** Serialization overhead dramatically slows queries
3. **Not collecting statistics:** Missing `ANALYZE TABLE` leads to suboptimal query plans
4. **Non-deterministic functions in cached queries:** `NOW()`, `RAND()` etc. prevent query result caching
5. **Partitioning by wrong column:** Partitioning by a column not used in filters causes full scans
6. **Too many Liquid Clustering keys:** For tables under 10 TB, 2 keys often outperform 4 keys
7. **Manual OPTIMIZE/VACUUM without predictive optimization:** Enable predictive optimization for Unity Catalog managed tables

### Operational Anti-Patterns

1. **Idle warehouses:** Always enable auto-stop; use serverless for variable workloads
2. **Under-sized warehouses:** Queries spilling to disk waste more DBUs than a larger warehouse
3. **External tables when managed will do:** External tables miss predictive optimization and enhanced governance
4. **Skipping VACUUM:** Unbounded file growth increases storage costs and slows metadata operations
5. **Running VACUUM with too-short retention:** Can break long-running queries and time travel

---

## Quick Reference: SQL Patterns for AI Agents

When generating SQL for Databricks, prefer these patterns:

```sql
-- Use CREATE OR REPLACE (not DROP + CREATE)
CREATE OR REPLACE TABLE catalog.schema.my_table AS
SELECT ...;

-- Use MERGE for upserts (not DELETE + INSERT)
MERGE INTO target USING source
ON target.key = source.key
WHEN MATCHED THEN UPDATE SET ...
WHEN NOT MATCHED THEN INSERT ...;

-- Use QUALIFY for window function filtering (not subquery)
SELECT *, ROW_NUMBER() OVER (PARTITION BY id ORDER BY ts DESC) AS rn
FROM my_table
QUALIFY rn = 1;

-- Use DECIMAL for money
SELECT CAST(amount AS DECIMAL(18,2)) AS revenue FROM orders;

-- Collect statistics after loading
ANALYZE TABLE catalog.schema.my_table COMPUTE STATISTICS FOR ALL COLUMNS;

-- Enable predictive optimization (classic compute only; serverless manages this automatically)
ALTER TABLE catalog.schema.my_table
SET TBLPROPERTIES ('delta.enableOptimizeWrite' = 'true');
```

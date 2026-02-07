# DLT to SDP Migration Guide

Guide for migrating Delta Live Tables (DLT) Python pipelines to Spark Declarative Pipelines (SDP) SQL.

⚠️ **For NEW Python SDP pipelines**: Use modern `pyspark.pipelines` API. See [5-python-api.md](5-python-api.md).

---

## Migration Decision Matrix

| Feature/Pattern | DLT Python | SDP SQL | Recommendation |
|-----------------|------------|---------|----------------|
| Simple transformations | ✓ | ✓ | **Migrate to SQL** |
| Aggregations | ✓ | ✓ | **Migrate to SQL** |
| Filtering, WHERE clauses | ✓ | ✓ | **Migrate to SQL** |
| CASE expressions | ✓ | ✓ | **Migrate to SQL** |
| SCD Type 1/2 | ✓ | ✓ | **Migrate to SQL** (AUTO CDC) |
| Simple joins | ✓ | ✓ | **Migrate to SQL** |
| Auto Loader | ✓ | ✓ | **Migrate to SQL** (read_files) |
| Streaming sources (Kafka) | ✓ | ✓ | **Migrate to SQL** (read_stream) |
| Complex Python UDFs | ✓ | ❌ | **Stay in Python** |
| External API calls | ✓ | ❌ | **Stay in Python** |
| Custom libraries | ✓ | ❌ | **Stay in Python** |
| Complex apply functions | ✓ | ❌ | **Stay in Python** or simplify |
| ML model inference | ✓ | ❌ | **Stay in Python** |

**Rule**: If 80%+ is SQL-expressible, migrate to SDP SQL. If heavy Python logic, stay with DLT Python or use hybrid.

---

## Side-by-Side: Key Patterns

### Basic Streaming Table

**DLT Python**:
```python
@dlt.table(name="bronze_sales", comment="Raw sales")
def bronze_sales():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .load("/mnt/raw/sales")
        .withColumn("_ingested_at", F.current_timestamp())
    )
```

**SDP SQL**:
```sql
CREATE OR REPLACE STREAMING TABLE bronze_sales
COMMENT 'Raw sales'
AS
SELECT *, current_timestamp() AS _ingested_at
FROM read_files('/mnt/raw/sales', format => 'json');
```

### Filtering and Transformations

**DLT Python**:
```python
@dlt.table(name="silver_sales")
@dlt.expect_or_drop("valid_amount", "amount > 0")
@dlt.expect_or_drop("valid_sale_id", "sale_id IS NOT NULL")
def silver_sales():
    return (
        dlt.read_stream("bronze_sales")
        .withColumn("sale_date", F.to_date("sale_date"))
        .withColumn("amount", F.col("amount").cast("decimal(10,2)"))
        .select("sale_id", "customer_id", "amount", "sale_date")
    )
```

**SDP SQL**:
```sql
CREATE OR REPLACE STREAMING TABLE silver_sales AS
SELECT
  sale_id, customer_id,
  CAST(amount AS DECIMAL(10,2)) AS amount,
  CAST(sale_date AS DATE) AS sale_date
FROM STREAM bronze_sales
WHERE amount > 0 AND sale_id IS NOT NULL;
```

### SCD Type 2

**DLT Python**:
```python
dlt.create_streaming_table("customers_history")

dlt.apply_changes(
    target="customers_history",
    source="customers_cdc_clean",
    keys=["customer_id"],
    sequence_by="event_timestamp",
    stored_as_scd_type="2",
    track_history_column_list=["*"]
)
```

**SDP SQL**:
```sql
CREATE OR REFRESH STREAMING TABLE customers_history;

CREATE FLOW customers_scd2_flow AS
AUTO CDC INTO customers_history
FROM stream(customers_cdc_clean)
KEYS (customer_id)
SEQUENCE BY event_timestamp
COLUMNS * EXCEPT (_rescued_data)
STORED AS SCD TYPE 2
TRACK HISTORY ON *;
```

### Joins

**DLT Python**:
```python
@dlt.table(name="silver_sales_enriched")
def silver_sales_enriched():
    sales = dlt.read_stream("silver_sales")
    products = dlt.read("dim_products")

    return (
        sales.join(products, "product_id", "left")
        .select(sales["*"], products["product_name"], products["category"])
    )
```

**SDP SQL**:
```sql
CREATE OR REPLACE STREAMING TABLE silver_sales_enriched AS
SELECT
  s.*,
  p.product_name,
  p.category
FROM STREAM silver_sales s
LEFT JOIN dim_products p ON s.product_id = p.product_id;
```

---

## Handling Expectations

**DLT Python**:
```python
@dlt.expect_or_drop("valid_amount", "amount > 0")
@dlt.expect_or_fail("critical_id", "id IS NOT NULL")
```

**SDP SQL - Basic**:
```sql
-- Use WHERE (equivalent to expect_or_drop)
WHERE amount > 0 AND id IS NOT NULL
```

**SDP SQL - Quarantine Pattern** (for auditing):
```sql
-- Flag invalid records
CREATE OR REPLACE STREAMING TABLE bronze_data_flagged AS
SELECT
  *,
  CASE
    WHEN amount <= 0 THEN TRUE
    WHEN id IS NULL THEN TRUE
    ELSE FALSE
  END AS is_invalid
FROM STREAM bronze_data;

-- Clean for downstream
CREATE OR REPLACE STREAMING TABLE silver_data_clean AS
SELECT * FROM STREAM bronze_data_flagged WHERE NOT is_invalid;

-- Quarantine for investigation
CREATE OR REPLACE STREAMING TABLE silver_data_quarantine AS
SELECT * FROM STREAM bronze_data_flagged WHERE is_invalid;
```

**Migration**: `@dlt.expect_or_drop` → WHERE clause or quarantine pattern.

---

## Handling UDFs

### Simple UDFs (Migrate to SQL)

**DLT Python**:
```python
@F.udf(returnType=StringType())
def categorize_amount(amount):
    if amount > 1000:
        return "High"
    elif amount > 100:
        return "Medium"
    else:
        return "Low"

@dlt.table(name="sales_categorized")
def sales_categorized():
    return (
        dlt.read("sales")
        .withColumn("category", categorize_amount(F.col("amount")))
    )
```

**SDP SQL** (CASE expression):
```sql
CREATE OR REPLACE MATERIALIZED VIEW sales_categorized AS
SELECT
  *,
  CASE
    WHEN amount > 1000 THEN 'High'
    WHEN amount > 100 THEN 'Medium'
    ELSE 'Low'
  END AS category
FROM sales;
```

### Complex UDFs (Stay in Python)

**Keep in Python for**:
- Complex conditional logic
- External API calls
- Custom algorithms
- ML inference

**Options**:
1. Keep transformation in Python DLT
2. Create hybrid (SQL + Python for specific UDFs)
3. Refactor to SQL built-ins if possible

---

## Migration Process

### Step 1: Inventory

Document:
- Number of tables/views
- Python UDFs (simple vs complex)
- External dependencies
- Expectations and quality rules

### Step 2: Categorize

**Easy to migrate**: Filters, aggregations, simple CASE
**Moderate**: UDFs rewritable as SQL
**Hard**: Complex Python, external calls, ML

### Step 3: Migrate by Layer

1. **Bronze** (ingestion): Convert Auto Loader to read_files()
2. **Silver** (cleansing): Convert expectations to WHERE/quarantine
3. **Gold** (aggregations): Usually straightforward
4. **SCD/CDC**: Use AUTO CDC

### Step 4: Test

- Run both pipelines in parallel
- Compare outputs for correctness
- Validate performance
- Check quality metrics

---

## When NOT to Migrate

**Stay with DLT Python if**:
1. Heavy Python UDF usage (>30% of logic)
2. External API calls required
3. Custom ML model inference
4. Complex stateful operations not in SQL
5. Existing pipeline works well, team prefers Python
6. Limited SQL expertise

**Consider hybrid**: SQL for most, Python for complex logic.

---

## Common Issues

| Issue | Solution |
|-------|----------|
| UDF doesn't translate | Keep in Python or refactor with SQL built-ins |
| Expectations differ | Use quarantine pattern to audit dropped records |
| Performance degradation | Use CLUSTER BY for Liquid Clustering, review joins |
| Schema evolution different | Use `mode => 'PERMISSIVE'` in read_files() |

---

## Summary

**Migration Path**:
1. Use decision matrix (80%+ SQL-expressible → migrate)
2. Migrate by layer (bronze → silver → gold)
3. Handle expectations with WHERE/quarantine
4. Translate simple UDFs to CASE expressions
5. Keep complex Python logic in Python

**Key**: DLT Python and SDP SQL are both fully supported. Migrate for simplicity, not necessity.

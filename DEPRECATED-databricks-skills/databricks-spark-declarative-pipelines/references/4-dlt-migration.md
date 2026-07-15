# Migration Guide: DLT to SDP

Guide for migrating from Delta Live Tables (DLT) to Spark Declarative Pipelines (SDP).

**Two migration paths:**
1. **DLT Python → SDP Python** (dlt → dp): Same language, new API
2. **DLT Python → SDP SQL**: Change language for simpler pipelines

---

## Migration Path 1: DLT Python → SDP Python (dlt → dp)

Use this when staying with Python but moving to the modern `pyspark.pipelines` API.

### Quick Reference

| Aspect | Legacy (`dlt`) | Modern (`dp`) |
|--------|---------------|----------------|
| **Import** | `import dlt` | `from pyspark import pipelines as dp` |
| **Table decorator** | `@dlt.table()` | `@dp.table()` |
| **Read table** | `dlt.read("table")` | `spark.read.table("table")` |
| **Read stream** | `dlt.read_stream("table")` | `spark.readStream.table("table")` |
| **CDC/SCD** | `dlt.apply_changes()` | `dp.create_auto_cdc_flow()` |
| **Clustering** | `partition_cols=["date"]` | `cluster_by=["date", "col2"]` |

### Step-by-Step Migration

#### Step 1: Update Imports

```python
# Before
import dlt

# After
from pyspark import pipelines as dp
```

#### Step 2: Update Decorators

```python
# Before
@dlt.table(name="my_table")

# After
@dp.table(name="my_table")
```

#### Step 3: Update Table Reads

```python
# Before
@dlt.table(name="silver_events")
def silver_events():
    return dlt.read("bronze_events").filter(...)

# After
@dp.table(name="silver_events")
def silver_events():
    return spark.read.table("bronze_events").filter(...)
```

```python
# Before (streaming)
@dlt.table(name="silver_events")
def silver_events():
    return dlt.read_stream("bronze_events").filter(...)

# After (streaming)
@dp.table(name="silver_events")
def silver_events():
    return spark.readStream.table("bronze_events").filter(...)
```

#### Step 4: Update Expectations

```python
# Before
@dlt.table(name="silver")
@dlt.expect_or_drop("valid_id", "id IS NOT NULL")

# After (identical syntax, just change dlt → dp)
@dp.table(name="silver")
@dp.expect_or_drop("valid_id", "id IS NOT NULL")
```

#### Step 5: Update CDC/SCD Operations

```python
# Before
dlt.create_streaming_table("customers_history")
dlt.apply_changes(
    target="customers_history",
    source="customers_cdc",
    keys=["customer_id"],
    sequence_by="event_timestamp",
    stored_as_scd_type="2"
)

# After
from pyspark.sql.functions import col

dp.create_streaming_table("customers_history")
dp.create_auto_cdc_flow(
    target="customers_history",
    source="customers_cdc",
    keys=["customer_id"],
    sequence_by=col("event_timestamp"),  # Note: use col()
    stored_as_scd_type=2                  # Note: integer, not string
)
```

**Key differences:**
- `apply_changes()` → `create_auto_cdc_flow()`
- `sequence_by` takes a Column object (`col("...")`) not a string
- `stored_as_scd_type` is integer `2` for Type 2, string `"1"` for Type 1

#### Step 6: Update Clustering (Partitioning → Liquid Clustering)

```python
# Before (legacy partitioning)
@dlt.table(
    name="bronze_events",
    partition_cols=["event_date"],
    table_properties={"pipelines.autoOptimize.zOrderCols": "event_type"}
)

# After (Liquid Clustering)
@dp.table(
    name="bronze_events",
    cluster_by=["event_date", "event_type"]
)
```

### Complete Before/After Example

**Before (DLT):**
```python
import dlt
from pyspark.sql import functions as F

@dlt.table(name="bronze_orders", partition_cols=["order_date"])
def bronze_orders():
    return spark.readStream.format("cloudFiles").load("/data/orders")

@dlt.table(name="silver_orders")
@dlt.expect_or_drop("valid_amount", "amount > 0")
def silver_orders():
    return dlt.read_stream("bronze_orders").filter(F.col("status") == "completed")

dlt.create_streaming_table("dim_customers")
dlt.apply_changes(
    target="dim_customers",
    source="customers_cdc",
    keys=["customer_id"],
    sequence_by="updated_at",
    stored_as_scd_type="2"
)
```

**After (SDP):**
```python
from pyspark import pipelines as dp
from pyspark.sql import functions as F

@dp.table(name="bronze_orders", cluster_by=["order_date"])
def bronze_orders():
    return spark.readStream.format("cloudFiles").load("/data/orders")

@dp.table(name="silver_orders")
@dp.expect_or_drop("valid_amount", "amount > 0")
def silver_orders():
    return spark.readStream.table("bronze_orders").filter(F.col("status") == "completed")

dp.create_streaming_table("dim_customers")
dp.create_auto_cdc_flow(
    target="dim_customers",
    source="customers_cdc",
    keys=["customer_id"],
    sequence_by=F.col("updated_at"),
    stored_as_scd_type=2
)
```

---

## Migration Path 2: DLT Python → SDP SQL

Use this when simplifying pipelines by converting to SQL.

### Decision Matrix

| Feature/Pattern | DLT Python | SDP SQL | Recommendation |
|-----------------|------------|---------|----------------|
| Simple transformations | ✓ | ✓ | **Migrate to SQL** |
| Aggregations | ✓ | ✓ | **Migrate to SQL** |
| Filtering, WHERE clauses | ✓ | ✓ | **Migrate to SQL** |
| CASE expressions | ✓ | ✓ | **Migrate to SQL** |
| SCD Type 1/2 | ✓ | ✓ | **Migrate to SQL** (AUTO CDC) |
| Simple joins | ✓ | ✓ | **Migrate to SQL** |
| Auto Loader | ✓ | ✓ | **Migrate to SQL** (read_files) |
| Streaming sources (Kafka) | ✓ | ✓ | **Migrate to SQL** (read_kafka) |
| Complex Python UDFs | ✓ | ❌ | **Stay in Python** |
| External API calls | ✓ | ❌ | **Stay in Python** |
| Custom libraries | ✓ | ❌ | **Stay in Python** |
| ML model inference | ✓ | ❌ | **Stay in Python** |

**Rule**: If 80%+ is SQL-expressible, migrate to SDP SQL. If heavy Python logic, stay with Python (use modern `dp` API).

### Side-by-Side Conversions

#### Basic Streaming Table

**DLT Python:**
```python
@dlt.table(name="bronze_sales", comment="Raw sales")
def bronze_sales():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .load("/Volumes/my_catalog/my_schema/raw/sales")
        .withColumn("_ingested_at", F.current_timestamp())
    )
```

**SDP SQL:**
```sql
CREATE OR REFRESH STREAMING TABLE bronze_sales
COMMENT 'Raw sales'
AS
SELECT *, current_timestamp() AS _ingested_at
FROM STREAM read_files('/Volumes/my_catalog/my_schema/raw/sales', format => 'json');
```

#### Filtering and Transformations

**DLT Python:**
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

**SDP SQL:**
```sql
CREATE OR REFRESH STREAMING TABLE silver_sales AS
SELECT
  sale_id, customer_id,
  CAST(amount AS DECIMAL(10,2)) AS amount,
  CAST(sale_date AS DATE) AS sale_date
FROM STREAM bronze_sales
WHERE amount > 0 AND sale_id IS NOT NULL;
```

#### SCD Type 2

**DLT Python:**
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

**SDP SQL:**
```sql
CREATE OR REFRESH STREAMING TABLE customers_history;

CREATE FLOW customers_scd2_flow AS
AUTO CDC INTO customers_history
FROM stream(customers_cdc_clean)
KEYS (customer_id)
APPLY AS DELETE WHEN operation = "DELETE"
SEQUENCE BY event_timestamp
COLUMNS * EXCEPT (operation, _ingested_at, _source_file)
STORED AS SCD TYPE 2;
```

**Note:** In SQL, put `APPLY AS DELETE WHEN` before `SEQUENCE BY`. Only list columns in `COLUMNS * EXCEPT (...)` that exist in the source.

#### Joins

**DLT Python:**
```python
@dlt.table(name="silver_sales_enriched")
def silver_sales_enriched():
    sales = dlt.read_stream("silver_sales")
    products = dlt.read("dim_products")
    return sales.join(products, "product_id", "left")
```

**SDP SQL:**
```sql
CREATE OR REFRESH STREAMING TABLE silver_sales_enriched AS
SELECT s.*, p.product_name, p.category
FROM STREAM silver_sales s
LEFT JOIN dim_products p ON s.product_id = p.product_id;
```

### Handling Expectations

**DLT Python:**
```python
@dlt.expect_or_drop("valid_amount", "amount > 0")
@dlt.expect_or_fail("critical_id", "id IS NOT NULL")
```

**SDP SQL - Basic** (equivalent to expect_or_drop):
```sql
WHERE amount > 0 AND id IS NOT NULL
```

**SDP SQL - Quarantine Pattern** (for auditing dropped records):
```sql
-- Flag invalid records
CREATE OR REFRESH STREAMING TABLE bronze_data_flagged AS
SELECT *,
  CASE WHEN amount <= 0 OR id IS NULL THEN TRUE ELSE FALSE END AS is_invalid
FROM STREAM bronze_data;

-- Clean for downstream
CREATE OR REFRESH STREAMING TABLE silver_data_clean AS
SELECT * FROM STREAM bronze_data_flagged WHERE NOT is_invalid;

-- Quarantine for investigation
CREATE OR REFRESH STREAMING TABLE silver_data_quarantine AS
SELECT * FROM STREAM bronze_data_flagged WHERE is_invalid;
```

### Handling UDFs

#### Simple UDFs → SQL CASE

**DLT Python:**
```python
@F.udf(returnType=StringType())
def categorize_amount(amount):
    if amount > 1000: return "High"
    elif amount > 100: return "Medium"
    else: return "Low"

@dlt.table(name="sales_categorized")
def sales_categorized():
    return dlt.read("sales").withColumn("category", categorize_amount(F.col("amount")))
```

**SDP SQL:**
```sql
CREATE OR REFRESH MATERIALIZED VIEW sales_categorized AS
SELECT *,
  CASE
    WHEN amount > 1000 THEN 'High'
    WHEN amount > 100 THEN 'Medium'
    ELSE 'Low'
  END AS category
FROM sales;
```

#### Complex UDFs → Stay in Python

Keep in Python if:
- Complex conditional logic
- External API calls
- Custom algorithms
- ML inference

Use modern `dp` API instead of `dlt`.

---

## Migration Process

### Step 1: Inventory

Document:
- Number of tables/views
- Python UDFs (simple vs complex)
- External dependencies
- Expectations and quality rules

### Step 2: Choose Path

- **80%+ SQL-expressible** → Migrate to SDP SQL
- **Heavy Python logic** → Migrate to SDP Python (`dp` API)
- **Mixed** → Hybrid (SQL for most, Python for complex)

### Step 3: Migrate by Layer

1. **Bronze** (ingestion): `cloudFiles` → `read_files()` or keep `cloudFiles` with `dp`
2. **Silver** (cleansing): `dlt.expect*` → WHERE clause or `dp.expect*`
3. **Gold** (aggregations): Usually straightforward
4. **SCD/CDC**: `apply_changes` → AUTO CDC or `create_auto_cdc_flow`

### Step 4: Test

- Run both pipelines in parallel
- Compare outputs for correctness
- Validate performance
- Check quality metrics

---

## When NOT to Migrate

**Stay with current approach if:**
1. Pipeline works well and team is comfortable
2. Heavy Python UDF usage (>30% of logic)
3. External API calls required
4. Custom ML model inference
5. Complex stateful operations not expressible in SQL
6. Limited time/resources for migration

**Key**: DLT and SDP are both fully supported. Migrate for simplicity or new features, not necessity.

---

## Common Issues

| Issue | Solution |
|-------|----------|
| `sequence_by` type error | Use `col("column")` not string in `dp.create_auto_cdc_flow()` |
| UDF doesn't translate | Keep in Python or refactor with SQL built-ins |
| Expectations differ | Use quarantine pattern to audit dropped records |
| Performance degradation | Use `CLUSTER BY` for Liquid Clustering |
| Schema evolution different | Use `mode => 'PERMISSIVE'` in `read_files()` |
| AUTO CDC parse error | Put `APPLY AS DELETE WHEN` before `SEQUENCE BY` |

---

## Related Documentation

- **[python/1-syntax-basics.md](python/1-syntax-basics.md)** - Modern `dp` API reference
- **[python/4-cdc-patterns.md](python/4-cdc-patterns.md)** - Python CDC patterns
- **[sql/4-cdc-patterns.md](sql/4-cdc-patterns.md)** - SQL CDC patterns
- **[SKILL.md](../SKILL.md)** - Main skill entry point

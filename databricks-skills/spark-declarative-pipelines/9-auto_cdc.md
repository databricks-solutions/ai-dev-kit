# AUTO CDC Patterns for Change Data Capture

**Keywords**: Slow Changing Dimension, SCD, SCD Type 1, SCD Type 2, AUTO CDC, change data capture, dp.create_auto_cdc_flow, deduplication

---

## Overview

AUTO CDC automatically handles Change Data Capture (CDC) to track changes in your data using Slow Changing Dimensions (SCD). It provides automatic deduplication, change tracking, and handles late-arriving data correctly.

**Where to apply AUTO CDC:**
- **Silver layer**: When business users need deduplicated or historical data for analytics/ML
- **Gold layer**: When implementing dimensional modeling (star schema) with dim/fact tables
- **Choice depends on**: Downstream consumption patterns and query requirements

---

## SCD Type 1 vs Type 2

### SCD Type 1 (In-place updates)
- **Overwrites** old values with new values
- **No history preserved** - only current state maintained
- **Use for**: Dimension attributes that don't need history
  - Correcting data errors (typos)
  - Updating attributes where history doesn't matter
  - Maintaining single current record per key
- **Syntax**: `stored_as_scd_type="1"` (string)

### SCD Type 2 (History tracking)
- **Creates new row** for each change
- **Preserves full history** with `__START_AT` and `__END_AT` timestamps
- **Use for**: Tracking changes over time
  - Customer address changes
  - Product price history
  - Employee role changes
  - Any dimension requiring temporal analysis
- **Syntax**: `stored_as_scd_type=2` (integer)

---

## Pattern: Cleaning + AUTO CDC

### Step 1: Clean and Validate Data

Create a cleaned streaming table with proper typing and quality checks:

```python
# Cleaned data preparation (can be silver or intermediate layer)
from pyspark import pipelines as dp
from pyspark.sql import functions as F

schema = spark.conf.get("schema")

@dp.table(
    name=f"{schema}.users_clean",
    comment="Cleaned and validated user data with proper typing and quality checks",
    cluster_by=["user_id"]
)
def users_clean():
    """
    Prepare clean data with:
    - Proper timestamp typing
    - Data quality validations
    - Remove records with invalid email or null user_id
    """
    return (
        spark.readStream.table("bronze_users")
        .filter(F.col("user_id").isNotNull())
        .filter(F.col("email").isNotNull())
        .filter(F.col("email").rlike(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"))
        .withColumn("created_timestamp", F.to_timestamp("created_timestamp"))
        .withColumn("updated_timestamp", F.to_timestamp("updated_timestamp"))
        .drop("_rescued_data")
        .select(
            "user_id",
            "email",
            "name",
            "subscription_tier",
            "country",
            "created_timestamp",
            "updated_timestamp",
            "_ingested_at",
            "_source_file"
        )
    )
```

### Step 2: Apply AUTO CDC (SCD Type 2)

Create a history-tracked dimension table with full change history:

```python
# AUTO CDC with SCD Type 2 (history tracking)
from pyspark import pipelines as dp

target_schema = spark.conf.get("target_schema")
source_schema = spark.conf.get("source_schema")

# Create the target table for AUTO CDC
dp.create_streaming_table(f"{target_schema}.dim_users")

# Apply AUTO CDC (SCD Type 2)
dp.create_auto_cdc_flow(
    target=f"{target_schema}.dim_users",
    source=f"{source_schema}.users_clean",
    keys=["user_id"],
    sequence_by="updated_timestamp",
    stored_as_scd_type=2  # Integer for Type 2
)
```

**Resulting table will include**:
- All original columns from source
- `__START_AT` - When this version became effective
- `__END_AT` - When this version expired (NULL for current)

### Step 3: Apply AUTO CDC (SCD Type 1)

Create a deduplicated table with in-place updates (no history):

```python
# AUTO CDC with SCD Type 1 (in-place updates)
from pyspark import pipelines as dp

target_schema = spark.conf.get("target_schema")
source_schema = spark.conf.get("source_schema")

# Create the target table for AUTO CDC
dp.create_streaming_table(f"{target_schema}.orders_current")

# Apply AUTO CDC (SCD Type 1)
dp.create_auto_cdc_flow(
    target=f"{target_schema}.orders_current",
    source=f"{source_schema}.orders_clean",
    keys=["order_id"],
    sequence_by="updated_timestamp",
    stored_as_scd_type="1"  # String for Type 1
)
```

---

## Key Benefits

- **Automatic deduplication** based on keys - no manual MERGE logic
- **Automatic change tracking** with temporal metadata (`__START_AT`, `__END_AT`)
- **Handles late-arriving data** correctly using `sequence_by` timestamp
- **Simplified pipeline code** - no complex merge/upsert logic required
- **Built-in idempotency** - safe to reprocess data

---

## Common Patterns

### Pattern 1: Gold Dimensional Model

Use AUTO CDC in Gold layer for star schema dimensions:

```python
# Silver: Cleaned streaming tables
@dp.table(name="silver.customers_clean")
def customers_clean():
    return spark.readStream.table("bronze.customers").filter(...)

# Gold: SCD Type 2 dimension
dp.create_streaming_table("gold.dim_customers")
dp.create_auto_cdc_flow(
    target="gold.dim_customers",
    source="silver.customers_clean",
    keys=["customer_id"],
    sequence_by="updated_at",
    stored_as_scd_type=2
)

# Gold: Fact table (no AUTO CDC)
@dp.table(name="gold.fact_orders")
def fact_orders():
    return spark.read.table("silver.orders_clean")
```

### Pattern 2: Silver Deduplication for Joins

Use AUTO CDC in Silver when joining multiple tables:

```python
# Silver: AUTO CDC for deduplication
dp.create_streaming_table("silver.products_dedupe")
dp.create_auto_cdc_flow(
    target="silver.products_dedupe",
    source="bronze.products",
    keys=["product_id"],
    sequence_by="modified_at",
    stored_as_scd_type="1"  # Type 1: just dedupe, no history
)

# Silver: Join with deduplicated data
@dp.table(name="silver.orders_enriched")
def orders_enriched():
    orders = spark.readStream.table("bronze.orders")
    products = spark.read.table("silver.products_dedupe")
    return orders.join(products, "product_id")
```

### Pattern 3: Mixed SCD Types

Different tables use different SCD types based on requirements:

```python
# SCD Type 2: Need history
dp.create_auto_cdc_flow(
    target="gold.dim_customers",
    source="silver.customers",
    keys=["customer_id"],
    sequence_by="updated_at",
    stored_as_scd_type=2  # Track address changes over time
)

# SCD Type 1: Corrections only
dp.create_auto_cdc_flow(
    target="gold.dim_products",
    source="silver.products",
    keys=["product_id"],
    sequence_by="modified_at",
    stored_as_scd_type="1"  # Current product info only
)
```

---

## Selective History Tracking

Track history only for specific columns (SCD Type 2):

```python
dp.create_auto_cdc_flow(
    target="gold.dim_products",
    source="silver.products_clean",
    keys=["product_id"],
    sequence_by="modified_at",
    stored_as_scd_type=2,
    track_history_column_list=["price", "cost"]  # Only track these columns
)
```

When `price` or `cost` changes, a new version is created. Other column changes update the current record without creating new versions.

---

## Using Temporary Views with AUTO CDC

**`@dp.temporary_view()`** creates in-pipeline temporary views that exist only during pipeline execution. These are useful for intermediate transformations before AUTO CDC.

**Key Constraints:**
- Cannot specify `catalog` or `schema` (temporary views are pipeline-scoped only)
- Cannot use `cluster_by` (not persisted)
- Only exists during pipeline execution

**Use Cases:**
- Complex transformations before AUTO CDC
- Intermediate logic that's referenced multiple times
- Avoiding redundant transformations

**Example: Preparation before AUTO CDC**

```python
from pyspark import pipelines as dp
from pyspark.sql import functions as F

# Step 1: Temporary view for complex business logic
@dp.temporary_view()
def orders_with_calculated_fields():
    """
    Temporary view for complex calculations.
    No catalog/schema needed - exists only in pipeline.
    """
    return (
        spark.readStream.table("bronze.orders")
        .withColumn("order_total", F.col("quantity") * F.col("unit_price"))
        .withColumn("discount_amount", F.col("order_total") * F.col("discount_rate"))
        .withColumn("final_amount", F.col("order_total") - F.col("discount_amount"))
        .withColumn("order_category",
            F.when(F.col("final_amount") > 1000, "large")
             .when(F.col("final_amount") > 100, "medium")
             .otherwise("small")
        )
        .filter(F.col("order_id").isNotNull())
        .filter(F.col("final_amount") > 0)
        .filter(F.col("order_date").isNotNull())
    )

# Step 2: Apply AUTO CDC using the temporary view as source
target_schema = spark.conf.get("target_schema")

dp.create_streaming_table(f"{target_schema}.orders_current")
dp.create_auto_cdc_flow(
    target=f"{target_schema}.orders_current",
    source="orders_with_calculated_fields",  # Reference temporary view by name
    keys=["order_id"],
    sequence_by="order_date",
    stored_as_scd_type="1"
)
```

**Benefits:**
- Avoids creating unnecessary persisted tables
- Reduces storage costs (nothing written to disk)
- Simplifies complex multi-step transformations
- Enables code reuse across multiple tables in same pipeline

---

## Related Documentation

- **[3-scd-query-patterns.md](3-scd-query-patterns.md)** - Querying SCD Type 2 history tables, point-in-time analysis, temporal joins
- **[1-ingestion-patterns.md](1-ingestion-patterns.md)** - CDC data sources (Kafka, Event Hubs, Kinesis)
- **[2-streaming-patterns.md](2-streaming-patterns.md)** - Deduplication patterns without AUTO CDC

---

## Best Practices

1. **Choose the right SCD type**:
   - Type 2 when you need to query historical states
   - Type 1 when you only need current state or deduplication

2. **Use meaningful sequence_by column**:
   - Should reflect true chronological order of changes
   - Typically `updated_timestamp`, `modified_at`, or `event_timestamp`

3. **Clean data before AUTO CDC**:
   - Apply type casting, validation, and filtering first
   - AUTO CDC works best with clean, well-typed data

4. **Consider query patterns**:
   - If analysts query history → Use Type 2
   - If analysts only need current → Use Type 1
   - If joining frequently → Consider Silver deduplication

5. **Use selective tracking for large tables**:
   - Track history only for columns that change meaningfully
   - Reduces storage and improves query performance

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **Duplicates still appearing** | Check `keys` include all business key columns; verify `sequence_by` has proper ordering |
| **Missing `__START_AT`/`__END_AT` columns** | These only appear in SCD Type 2 (integer), not Type 1 (string) |
| **Late data not handled** | Ensure `sequence_by` column is set and reflects true event time |
| **Type syntax error** | Type 2 uses integer `2`, Type 1 uses string `"1"` |
| **Performance issues** | Use `track_history_column_list` to limit which columns trigger new versions |

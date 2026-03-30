# Python CDC Patterns (AUTO CDC & SCD)

Change Data Capture patterns using AUTO CDC for SCD Type 1 and Type 2, plus querying SCD history tables.

**Import**: `from pyspark import pipelines as dp`

---

## Overview

AUTO CDC automatically handles Change Data Capture to track changes using Slow Changing Dimensions (SCD). It provides automatic deduplication, change tracking, and handles late-arriving data correctly.

**Where to apply AUTO CDC:**
- **Silver layer**: When business users need deduplicated or historical data
- **Gold layer**: When implementing dimensional modeling (star schema)

---

## SCD Type 1 vs Type 2

### SCD Type 1 (In-place updates)
- **Overwrites** old values with new values
- **No history preserved** - only current state
- **Use for**: Error corrections, attributes where history doesn't matter
- **Syntax**: `stored_as_scd_type="1"` (string)

### SCD Type 2 (History tracking)
- **Creates new row** for each change
- **Preserves full history** with `__START_AT` and `__END_AT` timestamps
- **Use for**: Tracking changes over time (addresses, prices, roles)
- **Syntax**: `stored_as_scd_type=2` (integer)

**Important:** Type 2 uses integer `2`, Type 1 uses string `"1"`.

---

## Creating AUTO CDC Flows

### SCD Type 2

```python
from pyspark import pipelines as dp
from pyspark.sql.functions import col

target_schema = spark.conf.get("target_schema")
source_schema = spark.conf.get("source_schema")

# Step 1: Create target table
dp.create_streaming_table(f"{target_schema}.dim_customers")

# Step 2: Create AUTO CDC flow
dp.create_auto_cdc_flow(
    target=f"{target_schema}.dim_customers",
    source=f"{source_schema}.customers_cdc_clean",
    keys=["customer_id"],
    sequence_by=col("event_timestamp"),  # Note: use col(), not string
    stored_as_scd_type=2,                # Integer for Type 2
    apply_as_deletes=col("operation") == "DELETE",
    except_column_list=["operation", "_ingested_at", "_source_file"]
)
```

### SCD Type 1

```python
dp.create_streaming_table(f"{target_schema}.orders_current")

dp.create_auto_cdc_flow(
    target=f"{target_schema}.orders_current",
    source=f"{source_schema}.orders_clean",
    keys=["order_id"],
    sequence_by=col("updated_timestamp"),
    stored_as_scd_type="1"  # String for Type 1
)
```

### Selective History Tracking

Track history only when specific columns change:

```python
dp.create_auto_cdc_flow(
    target="gold.dim_products",
    source="silver.products_clean",
    keys=["product_id"],
    sequence_by=col("modified_at"),
    stored_as_scd_type=2,
    track_history_column_list=["price", "cost"]  # Only track these columns
)
```

When `price` or `cost` changes, a new version is created. Other column changes update the current record without new versions.

---

## Complete Pattern: Clean + AUTO CDC

### Step 1: Clean and Validate Source Data

```python
from pyspark import pipelines as dp
from pyspark.sql import functions as F

schema = spark.conf.get("schema")

@dp.table(
    name=f"{schema}.users_clean",
    comment="Cleaned and validated user data",
    cluster_by=["user_id"]
)
def users_clean():
    """
    Clean data with proper typing and quality checks.
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
            "user_id", "email", "name", "subscription_tier", "country",
            "created_timestamp", "updated_timestamp",
            "_ingested_at", "_source_file"
        )
    )
```

### Step 2: Apply AUTO CDC

```python
from pyspark.sql.functions import col

target_schema = spark.conf.get("target_schema")
source_schema = spark.conf.get("source_schema")

dp.create_streaming_table(f"{target_schema}.dim_users")

dp.create_auto_cdc_flow(
    target=f"{target_schema}.dim_users",
    source=f"{source_schema}.users_clean",
    keys=["user_id"],
    sequence_by=col("updated_timestamp"),
    stored_as_scd_type=2,
    except_column_list=["_ingested_at", "_source_file"]
)
```

---

## Using Temporary Views with AUTO CDC

`@dp.temporary_view()` creates in-pipeline temporary views useful for intermediate transformations before AUTO CDC.

**Key Constraints:**
- Cannot specify `catalog` or `schema` (pipeline-scoped only)
- Cannot use `cluster_by` (not persisted)
- Only exists during pipeline execution

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
    )

# Step 2: Apply AUTO CDC using the temporary view as source
target_schema = spark.conf.get("target_schema")

dp.create_streaming_table(f"{target_schema}.orders_current")
dp.create_auto_cdc_flow(
    target=f"{target_schema}.orders_current",
    source="orders_with_calculated_fields",  # Reference temporary view by name
    keys=["order_id"],
    sequence_by=col("order_date"),
    stored_as_scd_type="1"
)
```

---

## Querying SCD Type 2 Tables

SCD Type 2 tables include temporal columns:
- `__START_AT` - When this version became effective
- `__END_AT` - When this version expired (NULL for current)

### Current State

```python
@dp.materialized_view(name="dim_customers_current")
def dim_customers_current():
    """All current records."""
    return (
        spark.read.table("dim_customers")
        .filter(F.col("__END_AT").isNull())
        .select(
            "customer_id", "customer_name", "email", "phone", "address",
            F.col("__START_AT").alias("valid_from")
        )
    )
```

### Point-in-Time Queries

Get state as of a specific date:

```python
@dp.materialized_view(name="products_as_of_date")
def products_as_of_date():
    """Products as of January 1, 2024."""
    as_of_date = "2024-01-01"
    return (
        spark.read.table("products_history")
        .filter(F.col("__START_AT") <= as_of_date)
        .filter(
            (F.col("__END_AT") > as_of_date) |
            F.col("__END_AT").isNull()
        )
    )
```

### Change Analysis

Track all changes for an entity:

```python
def get_customer_history(customer_id: str):
    """Get complete history for a customer."""
    return (
        spark.read.table("dim_customers")
        .filter(F.col("customer_id") == customer_id)
        .withColumn("days_active",
            F.coalesce(
                F.datediff("__END_AT", "__START_AT"),
                F.datediff(F.current_timestamp(), "__START_AT")
            )
        )
        .orderBy(F.col("__START_AT").desc())
    )
```

---

## Joining Facts with Historical Dimensions

### At Transaction Time

```python
@dp.materialized_view(name="sales_with_historical_prices")
def sales_with_historical_prices():
    """Join sales with product prices at time of sale."""
    sales = spark.read.table("sales_fact")
    products = spark.read.table("products_history")

    return (
        sales.join(
            products,
            (sales.product_id == products.product_id) &
            (sales.sale_date >= products.__START_AT) &
            ((sales.sale_date < products.__END_AT) | products.__END_AT.isNull()),
            "inner"
        )
        .select(
            sales.sale_id,
            sales.product_id,
            sales.sale_date,
            sales.quantity,
            products.product_name,
            products.price.alias("unit_price_at_sale_time"),
            (sales.quantity * products.price).alias("calculated_amount"),
            products.category
        )
    )
```

### With Current Dimension

```python
@dp.materialized_view(name="sales_with_current_prices")
def sales_with_current_prices():
    """Join sales with current product information."""
    sales = spark.read.table("sales_fact")
    products_current = spark.read.table("products_history").filter(F.col("__END_AT").isNull())

    return (
        sales.join(products_current, "product_id", "inner")
        .select(
            "sale_id", "product_id", "sale_date", "quantity",
            sales.amount.alias("amount_at_sale"),
            products_current.product_name.alias("current_product_name"),
            products_current.price.alias("current_price")
        )
    )
```

---

## Common Patterns

### Pattern 1: Gold Dimensional Model

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
    sequence_by=col("updated_at"),
    stored_as_scd_type=2
)

# Gold: Fact table (no AUTO CDC)
@dp.table(name="gold.fact_orders")
def fact_orders():
    return spark.read.table("silver.orders_clean")
```

### Pattern 2: Silver Deduplication for Joins

```python
# Silver: AUTO CDC for deduplication
dp.create_streaming_table("silver.products_dedupe")
dp.create_auto_cdc_flow(
    target="silver.products_dedupe",
    source="bronze.products",
    keys=["product_id"],
    sequence_by=col("modified_at"),
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

```python
# SCD Type 2: Need history
dp.create_auto_cdc_flow(
    target="gold.dim_customers",
    source="silver.customers",
    keys=["customer_id"],
    sequence_by=col("updated_at"),
    stored_as_scd_type=2  # Track address changes over time
)

# SCD Type 1: Corrections only
dp.create_auto_cdc_flow(
    target="gold.dim_products",
    source="silver.products",
    keys=["product_id"],
    sequence_by=col("modified_at"),
    stored_as_scd_type="1"  # Current product info only
)
```

---

## Best Practices

### 1. Clean Data Before AUTO CDC

Apply type casting, validation, and filtering first:

```python
@dp.table(name="users_clean")
def users_clean():
    return (
        spark.readStream.table("bronze_users")
        .filter(F.col("user_id").isNotNull())
        .filter(F.col("email").isNotNull())
        .withColumn("updated_at", F.to_timestamp("updated_at"))
    )

# Then apply AUTO CDC
dp.create_auto_cdc_flow(
    target="dim_users",
    source="users_clean",
    keys=["user_id"],
    sequence_by=col("updated_at"),
    stored_as_scd_type=2
)
```

### 2. Use col() for sequence_by

```python
# Correct
sequence_by=col("event_timestamp")

# Wrong - causes error
# sequence_by="event_timestamp"
```

### 3. Choose the Right SCD Type

- **Type 2** (`stored_as_scd_type=2`): Need to query historical states
- **Type 1** (`stored_as_scd_type="1"`): Only need current state or deduplication

### 4. Use meaningful sequence_by column

Should reflect true chronological order of changes:
- `updated_timestamp`
- `modified_at`
- `event_timestamp`

---

## Common Issues

| Issue | Solution |
|-------|----------|
| `sequence_by` type error | Use `col("column")` not string |
| SCD type syntax error | Type 2 uses integer `2`, Type 1 uses string `"1"` |
| Duplicates still appearing | Check `keys` include all business key columns |
| Missing `__START_AT`/`__END_AT` | These only appear in SCD Type 2, not Type 1 |
| Late data not handled | Ensure `sequence_by` reflects true event time |
| Performance issues | Use `track_history_column_list` to limit version triggers |

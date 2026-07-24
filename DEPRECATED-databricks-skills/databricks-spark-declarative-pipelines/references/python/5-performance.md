# Python Performance Tuning

Performance optimization strategies including Liquid Clustering, materialized view refresh, state management, and compute configuration.

**Import**: `from pyspark import pipelines as dp`

---

## Liquid Clustering (Recommended)

Liquid Clustering is the recommended approach for data layout optimization. It replaces manual partitioning and Z-ORDER.

### Benefits

- **Adaptive**: Adjusts to data distribution changes
- **Multi-dimensional**: Clusters on multiple columns simultaneously
- **Automatic file sizing**: Maintains optimal file sizes
- **Self-optimizing**: Reduces manual OPTIMIZE commands

### Basic Syntax

```python
from pyspark import pipelines as dp

@dp.table(cluster_by=["event_type", "event_date"])
def bronze_events():
    return spark.readStream.format("cloudFiles").load("/data")
```

### Automatic Key Selection

```python
@dp.table(cluster_by=["AUTO"])
def bronze_events():
    return spark.readStream.format("cloudFiles").load("/data")
```

**When to use AUTO**: Learning phase, unknown access patterns, prototyping
**When to define manually**: Well-known query patterns, production workloads

---

## Cluster Key Selection by Layer

### Bronze Layer

Cluster by event type + date:

```python
@dp.table(
    name="bronze_events",
    cluster_by=["event_type", "ingestion_date"],
    table_properties={"delta.autoOptimize.optimizeWrite": "true"}
)
def bronze_events():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .load("/Volumes/my_catalog/my_schema/raw/events/")
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn("ingestion_date", F.current_date())
    )
```

**Why**: Bronze filtered by event type for processing and by date for incremental loads.

### Silver Layer

Cluster by primary key + business dimension:

```python
@dp.table(
    name="silver_orders",
    cluster_by=["customer_id", "order_date"]
)
def silver_orders():
    return (
        spark.readStream.table("bronze_orders")
        .withColumn("order_date", F.to_date("order_timestamp"))
        .select("order_id", "customer_id", "product_id", "amount", "order_date")
    )
```

**Why**: Entity lookups (by ID) and time-range queries (by date).

### Gold Layer

Cluster by aggregation dimensions:

```python
@dp.materialized_view(
    name="gold_sales_summary",
    cluster_by=["product_category", "year_month"]
)
def gold_sales_summary():
    return (
        spark.read.table("silver_orders")
        .withColumn("year_month", F.date_format("order_date", "yyyy-MM"))
        .groupBy("product_category", "year_month")
        .agg(
            F.sum("amount").alias("total_sales"),
            F.count("*").alias("transaction_count"),
            F.avg("amount").alias("avg_order_value")
        )
    )
```

**Why**: Dashboard filters (category, region, time period).

### Selection Guidelines

| Layer | Good Keys | Rationale |
|-------|-----------|-----------|
| **Bronze** | event_type, ingestion_date | Filter by type; date for incremental |
| **Silver** | primary_key, business_date | Entity lookups + time ranges |
| **Gold** | aggregation_dimensions | Dashboard filters |

**Best practices:**
- First key: Most selective filter (e.g., customer_id)
- Second key: Next common filter (e.g., date)
- Order matters: Most selective first
- Limit to 4 keys: Diminishing returns beyond 4
- **Use `["AUTO"]` if unsure**

---

## Table Properties

### Auto-Optimize

```python
@dp.table(
    name="bronze_events",
    table_properties={
        "delta.autoOptimize.optimizeWrite": "true",
        "delta.autoOptimize.autoCompact": "true"
    }
)
def bronze_events():
    return spark.readStream.format("cloudFiles").load(...)
```

### Change Data Feed

```python
@dp.table(
    name="silver_customers",
    table_properties={"delta.enableChangeDataFeed": "true"}
)
def silver_customers():
    return spark.readStream.table("bronze_customers")
```

**Use when**: Downstream systems need efficient change tracking.

### Retention Periods

```python
@dp.table(
    name="bronze_high_volume",
    table_properties={
        "delta.logRetentionDuration": "7 days",
        "delta.deletedFileRetentionDuration": "7 days"
    }
)
def bronze_high_volume():
    return spark.readStream.format("cloudFiles").load(...)
```

**Use for**: High-volume tables to reduce storage costs.

---

## State Management for Streaming

### Understand State Growth

Higher cardinality = more state:

```python
# High state: 1M users x 10K products x 100M sessions - Massive state!
.groupBy("user_id", "product_id", "session_id")
```

### Reduce State Size

**Strategy 1: Reduce cardinality**

```python
@dp.table(name="user_category_stats")
def user_category_stats():
    return (
        spark.readStream.table("bronze_events")
        .groupBy(
            "user_id",
            "product_category",  # 100 categories (not 10K products)
            F.to_date("event_time").alias("event_date")
        )
        .agg(F.count("*").alias("events"))
    )
```

**Strategy 2: Use time windows**

```python
@dp.table(name="user_hourly_stats")
def user_hourly_stats():
    return (
        spark.readStream.table("bronze_events")
        .groupBy(
            "user_id",
            F.window("event_time", "1 hour")
        )
        .agg(F.count("*").alias("events"))
    )
```

**Strategy 3: Materialize intermediates**

```python
# Streaming aggregation (maintains state)
@dp.table(name="user_daily_stats")
def user_daily_stats():
    return (
        spark.readStream.table("bronze_events")
        .groupBy("user_id", F.to_date("event_time").alias("event_date"))
        .agg(F.count("*").alias("event_count"))
    )

# Batch aggregation (no streaming state)
@dp.materialized_view(name="user_monthly_stats")
def user_monthly_stats():
    return (
        spark.read.table("user_daily_stats")
        .groupBy("user_id", F.date_trunc("month", "event_date").alias("month"))
        .agg(F.sum("event_count").alias("total_events"))
    )
```

---

## Join Optimization

### Stream-to-Static (Efficient)

```python
@dp.table(name="sales_enriched")
def sales_enriched():
    """Small static dimension, large streaming fact."""
    sales = spark.readStream.table("bronze_sales")
    products = spark.read.table("dim_products")  # Small, broadcast

    return (
        sales.join(products, "product_id", "left")
        .select("sale_id", "product_id", "amount", "product_name", "category")
    )
```

**Best practice**: Keep static dimensions small (<10K rows) for broadcast.

### Stream-to-Stream (Stateful)

```python
@dp.table(name="orders_with_payments")
def orders_with_payments():
    """Time bounds limit state retention."""
    orders = spark.readStream.table("bronze_orders")
    payments = spark.readStream.table("bronze_payments")

    return orders.join(
        payments,
        (orders.order_id == payments.order_id) &
        (payments.payment_time >= orders.order_time) &
        (payments.payment_time <= orders.order_time + F.expr("INTERVAL 1 HOUR")),
        "inner"
    )
```

---

## Query Optimization

### Filter Early

```python
# Filter at source
@dp.table(name="silver_recent")
def silver_recent():
    return (
        spark.readStream.table("bronze_events")
        .filter(F.col("event_date") >= F.current_date() - 7)
    )

# Avoid filtering late in separate table
# @dp.table(name="silver_all")
# def silver_all(): return spark.readStream.table("bronze_events")
# @dp.materialized_view(name="gold_recent")
# def gold_recent(): return spark.read.table("silver_all").filter(...)
```

### Select Specific Columns

```python
# Only needed columns
.select("customer_id", "order_date", "amount")

# Avoid SELECT *
# .select("*")
```

---

## Pre-Aggregation

```python
@dp.materialized_view(name="orders_monthly")
def orders_monthly():
    """Pre-aggregate for fast queries."""
    return (
        spark.read.table("large_orders_table")
        .groupBy(
            "customer_id",
            F.year("order_date").alias("year"),
            F.month("order_date").alias("month")
        )
        .agg(F.sum("amount").alias("total"))
    )

# Query the MV directly - much faster than querying large_orders_table
```

---

## Compute Configuration

### Serverless vs Classic

| Aspect | Serverless | Classic |
|--------|-----------|---------|
| Startup | Fast (seconds) | Slower (minutes) |
| Scaling | Automatic, instant | Manual/autoscaling |
| Cost | Pay-per-use | Pay for cluster time |
| Best for | Variable workloads, dev/test | Steady workloads |

### Serverless (Recommended)

Enable at pipeline level:

```yaml
execution_mode: continuous  # or triggered
serverless: true
```

**Advantages**: No cluster management, instant scaling, lower cost for bursty workloads.

---

## Complete Example

```python
from pyspark import pipelines as dp
from pyspark.sql import functions as F

# Bronze: Optimized ingestion
@dp.table(
    name="bronze_orders",
    cluster_by=["order_date"],
    table_properties={
        "delta.autoOptimize.optimizeWrite": "true",
        "delta.autoOptimize.autoCompact": "true"
    }
)
def bronze_orders():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .load("/Volumes/my_catalog/my_schema/raw/orders/")
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn("order_date", F.to_date("order_timestamp"))
    )

# Silver: Efficient clustering for joins
@dp.table(
    name="silver_orders",
    cluster_by=["customer_id", "order_date"]
)
@dp.expect_or_drop("valid_amount", "amount > 0")
def silver_orders():
    return (
        spark.readStream.table("bronze_orders")
        .filter(F.col("order_date") >= F.current_date() - 90)  # Filter early
        .withColumn("amount", F.col("amount").cast("decimal(10,2)"))  # DECIMAL for monetary
        .select("order_id", "customer_id", "amount", "order_date")  # Select specific
    )

# Gold: Pre-aggregated for dashboards
@dp.materialized_view(
    name="gold_daily_revenue",
    cluster_by=["order_date"]
)
def gold_daily_revenue():
    return (
        spark.read.table("silver_orders")
        .groupBy("order_date")
        .agg(
            F.sum("amount").alias("total_revenue"),
            F.count("order_id").alias("order_count"),
            F.countDistinct("customer_id").alias("unique_customers")
        )
    )
```

---

## Common Issues

| Issue | Solution |
|-------|----------|
| Pipeline running slowly | Check clustering, state size, join patterns |
| High memory usage | Unbounded state - add time windows, reduce cardinality |
| Many small files | Enable auto-optimize table properties |
| Expensive queries on large tables | Add clustering, create filtered MVs |
| MV refresh slow | Enable row tracking on source |

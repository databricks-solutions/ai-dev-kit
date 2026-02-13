# Multi-Table Patterns

Patterns for generating related tables with foreign key consistency, realistic cardinality, and temporal coherence.

## FK Consistency

The core principle: generate parent tables first, then use matching ID ranges in child tables.

```python
import dbldatagen as dg

# Parent table: customers with IDs 1_000_000 to 1_099_999
customers = (
    dg.DataGenerator(spark, rows=100_000, partitions=10)
    .withColumn("customer_id", "long", minValue=1_000_000, uniqueValues=100_000)
    .withColumn("name", "string", template=r"\\w \\w")
    .withColumn("email", "string", template=r"\\w.\\w@\\w.com")
    .withColumn("signup_date", "date", begin="2020-01-01", end="2024-12-31", random=True)
    .build()
)

# Child table: orders reference customer IDs within the parent range
orders = (
    dg.DataGenerator(spark, rows=1_000_000, partitions=20)
    .withColumn("order_id", "long", minValue=1, uniqueValues=1_000_000)
    .withColumn("customer_id", "long", minValue=1_000_000, maxValue=1_099_999)
    .withColumn("order_date", "date", begin="2024-01-01", end="2024-12-31", random=True)
    .withColumn("amount", "decimal(10,2)", minValue=10, maxValue=5000, random=True)
    .build()
)
```

The `maxValue` for the child FK column must equal `minValue + uniqueValues - 1` from the parent to ensure every child row references a valid parent. With uniform distribution (the default), each parent gets roughly equal child rows.

## Cardinality Control

Real data is rarely uniform. Use distributions to create realistic skew — e.g., a small fraction of customers generating most orders (Pareto/80-20 rule).

### Exponential Distribution (Pareto-Like Skew)

```python
# 20% of customers generate ~80% of orders
orders = (
    dg.DataGenerator(spark, rows=1_000_000, partitions=20)
    .withColumn("order_id", "long", minValue=1, uniqueValues=1_000_000)
    .withColumn("customer_id", "long",
                minValue=1_000_000, maxValue=1_099_999,
                distribution=dg.distributions.Exponential(1.5))
    .withColumn("amount", "decimal(10,2)", minValue=10, maxValue=5000, random=True)
    .build()
)
```

### Normal Distribution (Concentrated Around Center)

```python
# Most orders come from "middle" customer IDs
.withColumn("customer_id", "long",
            minValue=1_000_000, maxValue=1_099_999,
            distribution="normal")
```

### Weighted Categories

```python
# Product categories with realistic sales distribution
.withColumn("category", "string",
            values=["Electronics", "Clothing", "Food", "Home", "Sports"],
            weights=[30, 25, 20, 15, 10])
```

## Temporal Consistency

Child events must occur after parent creation dates. Use `baseColumn` and SQL expressions to enforce temporal ordering.

### Orders After Customer Signup

```python
orders = (
    dg.DataGenerator(spark, rows=1_000_000, partitions=20)
    .withColumn("order_id", "long", minValue=1, uniqueValues=1_000_000)
    .withColumn("customer_id", "long", minValue=1_000_000, maxValue=1_099_999)
    # Generate a signup proxy (days since 2020-01-01)
    .withColumn("_signup_offset", "integer", minValue=0, maxValue=1825, omit=True)
    .withColumn("_signup_date", "date",
                expr="date_add(to_date('2020-01-01'), _signup_offset)", omit=True)
    # Order date is always 1-365 days after signup
    .withColumn("order_date", "date",
                expr="date_add(_signup_date, cast(rand() * 365 as int))")
    .withColumn("amount", "decimal(10,2)", minValue=10, maxValue=5000, random=True)
    .build()
)
```

### Event Sequences (Order → Shipment → Delivery)

```python
events = (
    dg.DataGenerator(spark, rows=500_000, partitions=10)
    .withColumn("order_id", "long", minValue=1, uniqueValues=500_000)
    .withColumn("order_date", "date", begin="2024-01-01", end="2024-11-30", random=True)
    # Shipped 1-5 days after order
    .withColumn("ship_date", "date",
                expr="date_add(order_date, 1 + cast(rand() * 4 as int))")
    # Delivered 2-10 days after shipment
    .withColumn("delivery_date", "date",
                expr="date_add(ship_date, 2 + cast(rand() * 8 as int))")
)
```

## Cross-Table Value Consistency

When multiple tables share categorical values (e.g., region codes, status enums), define them once and reuse:

```python
# Shared value definitions
REGIONS = ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]
PAYMENT_METHODS = ["Credit Card", "Debit Card", "Digital Wallet", "Bank Transfer"]
CURRENCIES = ["USD", "EUR", "GBP", "JPY"]

# Use in customers
customers = (
    dg.DataGenerator(spark, rows=100_000, partitions=10)
    .withColumn("customer_id", "long", minValue=1_000_000, uniqueValues=100_000)
    .withColumn("region", "string", values=REGIONS, weights=[40, 30, 20, 10])
    .withColumn("preferred_payment", "string", values=PAYMENT_METHODS)
    .withColumn("currency", "string", values=CURRENCIES, weights=[50, 25, 15, 10])
    .build()
)

# Use same values in transactions
transactions = (
    dg.DataGenerator(spark, rows=1_000_000, partitions=20)
    .withColumn("txn_id", "long", minValue=1, uniqueValues=1_000_000)
    .withColumn("customer_id", "long", minValue=1_000_000, maxValue=1_099_999)
    .withColumn("region", "string", values=REGIONS, weights=[40, 30, 20, 10])
    .withColumn("payment_method", "string", values=PAYMENT_METHODS)
    .withColumn("currency", "string", values=CURRENCIES, weights=[50, 25, 15, 10])
    .build()
)
```

This ensures that downstream joins and reports on these categorical dimensions produce consistent results.

## Complete Multi-Table Function

A template for generating an entire related dataset and writing it to Unity Catalog:

```python
import dbldatagen as dg

def generate_retail_dataset(
    spark,
    catalog: str,
    schema: str,
    n_customers: int = 100_000,
    n_products: int = 10_000,
    orders_per_customer: int = 10,
    items_per_order: int = 3,
):
    """Generate a complete retail dataset with consistent foreign keys.

    Tables: customers, products, orders, line_items
    """
    n_orders = n_customers * orders_per_customer
    n_line_items = n_orders * items_per_order

    # 1. Customers (parent)
    customers_df = (
        dg.DataGenerator(spark, rows=n_customers, partitions=max(4, n_customers // 100_000))
        .withColumn("customer_id", "long", minValue=1_000_000, uniqueValues=n_customers)
        .withColumn("name", "string", template=r"\\w \\w")
        .withColumn("email", "string", template=r"\\w.\\w@\\w.com")
        .withColumn("phone", "string", template=r"(ddd)-ddd-dddd")
        .withColumn("city", "string",
                    values=["New York", "Los Angeles", "Chicago", "Houston", "Phoenix"])
        .withColumn("loyalty_tier", "string",
                    values=["Bronze", "Silver", "Gold", "Platinum"],
                    weights=[50, 30, 15, 5])
        .withColumn("signup_date", "date", begin="2020-01-01", end="2024-06-30", random=True)
        .build()
    )

    # 2. Products (parent)
    products_df = (
        dg.DataGenerator(spark, rows=n_products, partitions=max(4, n_products // 10_000))
        .withColumn("product_id", "long", minValue=10_000, uniqueValues=n_products)
        .withColumn("sku", "string", template=r"SKU-dddddddd")
        .withColumn("product_name", "string", prefix="Product-", baseColumn="product_id")
        .withColumn("category", "string",
                    values=["Electronics", "Clothing", "Home", "Sports", "Food"])
        .withColumn("unit_price", "decimal(10,2)", minValue=5, maxValue=500, random=True)
        .build()
    )

    # 3. Orders (child of customers)
    orders_df = (
        dg.DataGenerator(spark, rows=n_orders, partitions=max(4, n_orders // 100_000))
        .withColumn("order_id", "long", minValue=1, uniqueValues=n_orders)
        .withColumn("customer_id", "long",
                    minValue=1_000_000, maxValue=1_000_000 + n_customers - 1,
                    distribution=dg.distributions.Exponential(1.5))
        .withColumn("order_date", "date", begin="2024-01-01", end="2024-12-31", random=True)
        .withColumn("status", "string",
                    values=["completed", "pending", "cancelled", "returned"],
                    weights=[70, 15, 10, 5])
        .build()
    )

    # 4. Line items (child of orders + products)
    line_items_df = (
        dg.DataGenerator(spark, rows=n_line_items,
                         partitions=max(4, n_line_items // 100_000))
        .withColumn("line_item_id", "long", minValue=1, uniqueValues=n_line_items)
        .withColumn("order_id", "long", minValue=1, maxValue=n_orders)
        .withColumn("product_id", "long", minValue=10_000, maxValue=10_000 + n_products - 1)
        .withColumn("quantity", "integer", minValue=1, maxValue=10, distribution="exponential")
        .withColumn("unit_price", "decimal(10,2)", minValue=5, maxValue=500, random=True)
        .withColumn("line_total", "decimal(12,2)", expr="quantity * unit_price")
        .build()
    )

    # Write all tables to Unity Catalog
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")

    tables = {
        "customers": customers_df,
        "products": products_df,
        "orders": orders_df,
        "line_items": line_items_df,
    }

    for name, df in tables.items():
        df.write.format("delta").mode("overwrite").saveAsTable(f"{catalog}.{schema}.{name}")

    return tables
```

### Usage

```python
tables = generate_retail_dataset(
    spark,
    catalog="demo",
    schema="retail",
    n_customers=100_000,
    n_products=10_000,
    orders_per_customer=10,
    items_per_order=3,
)
```

## Pre-Built Datasets

dbldatagen includes pre-built multi-table datasets with consistent foreign keys:

```python
from dbldatagen import Datasets

ds = Datasets(spark)

# List all available datasets
ds.list()

# Generate individual tables
customers = ds.getTable("multi_table/sales_order", "customers", numCustomers=10_000)
orders = ds.getTable("multi_table/sales_order", "base_orders", numOrders=100_000)
line_items = ds.getTable("multi_table/sales_order", "base_order_line_items")

# Get combined table with resolved foreign keys
full_orders = ds.getCombinedTable("multi_table/sales_order", "orders")
```

### Available Multi-Table Datasets

| Dataset | Tables | Description |
|---------|--------|-------------|
| `multi_table/sales_order` | customers, carriers, catalog_items, orders, order_line_items, order_shipments, invoices | Full retail sales order model |

### Customizing Pre-Built Datasets

```python
# Scale the dataset
customers = ds.getTable(
    "multi_table/sales_order",
    "customers",
    numCustomers=500_000,   # scale up
    partitions=50,          # more partitions for larger data
)

# Get all tables at scale
for table_name in ["customers", "base_orders", "base_order_line_items"]:
    df = ds.getTable("multi_table/sales_order", table_name,
                     numCustomers=500_000, numOrders=5_000_000)
    df.write.format("delta").mode("overwrite").saveAsTable(
        f"demo.retail.{table_name}"
    )
```

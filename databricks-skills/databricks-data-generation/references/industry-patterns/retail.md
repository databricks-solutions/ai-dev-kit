# Retail Industry Patterns

Comprehensive data models and generation patterns for retail demos.

## Data Model Overview

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Customers  │────<│ Transactions │>────│   Products   │
└──────────────┘     └──────────────┘     └──────────────┘
       │                    │                    │
       │                    │                    │
       ▼                    ▼                    ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Loyalty    │     │  Line Items  │     │  Inventory   │
└──────────────┘     └──────────────┘     └──────────────┘
```

## Table Schemas

### Customers

| Column | Type | Description | Generation Pattern |
|--------|------|-------------|-------------------|
| `customer_id` | LONG | Primary key | Unique, starting at 1000000 |
| `first_name` | STRING | First name | Mimesis |
| `last_name` | STRING | Last name | Mimesis |
| `email` | STRING | Email address | Template or Mimesis |
| `phone` | STRING | Phone number | Template: `(ddd)-ddd-dddd` |
| `address_line1` | STRING | Street address | Mimesis |
| `city` | STRING | City | Mimesis or values list |
| `state` | STRING | State code | Values list (50 states) |
| `zip_code` | STRING | ZIP code | Template: `ddddd` |
| `loyalty_tier` | STRING | Loyalty level | Weighted values |
| `signup_date` | DATE | Account creation | Random in range |
| `lifetime_value` | DECIMAL(12,2) | Total spend | Exponential distribution |

```python
import dbldatagen as dg
from utils.mimesis_text import mimesisText

customers = (
    dg.DataGenerator(spark, rows=100_000, partitions=10)
    .withColumn("customer_id", "long", minValue=1_000_000, uniqueValues=100_000)
    .withColumn("first_name", "string", text=mimesisText("person.first_name"))
    .withColumn("last_name", "string", text=mimesisText("person.last_name"))
    .withColumn("email", "string", text=mimesisText("person.email"))
    .withColumn("phone", "string", text=mimesisText("person.telephone"))
    .withColumn("city", "string", values=["New York", "Los Angeles", "Chicago", "Houston", "Phoenix", "Philadelphia", "San Antonio", "San Diego", "Dallas", "San Jose"])
    .withColumn("state", "string", values=["NY", "CA", "IL", "TX", "AZ", "PA", "TX", "CA", "TX", "CA"])
    .withColumn("zip_code", "string", template=r"ddddd")
    .withColumn("loyalty_tier", "string", values=["Bronze", "Silver", "Gold", "Platinum"], weights=[50, 30, 15, 5])
    # Skewed registration dates: 70% recent, 25% medium, 5% old
    .withColumn("signup_era", "string", values=["recent", "medium", "old"], weights=[70, 25, 5], omit=True)
    .withColumn("signup_date", "date",
                expr="""case signup_era
                    when 'recent' then date_add('2023-01-01', cast(rand() * 730 as int))
                    when 'medium' then date_add('2021-01-01', cast(rand() * 730 as int))
                    else date_add('2019-01-01', cast(rand() * 730 as int))
                end""")
    .withColumn("lifetime_value", "decimal(12,2)", minValue=0, maxValue=50000, distribution="exponential")
    # Customer churn probability — higher for Bronze, lower for Platinum
    .withColumn("churn_probability", "float",
                expr="""case loyalty_tier
                    when 'Bronze' then 0.3 + rand() * 0.2
                    when 'Silver' then 0.15 + rand() * 0.15
                    when 'Gold' then 0.05 + rand() * 0.1
                    when 'Platinum' then 0.01 + rand() * 0.04
                end""")
    # Weighted channel distribution
    .withColumn("acquisition_channel", "string",
                values=["Organic Search", "Paid Social", "Email", "Referral", "Direct", "Affiliate"],
                weights=[30, 25, 15, 15, 10, 5])
    .build()
)
```

### Products

| Column | Type | Description | Generation Pattern |
|--------|------|-------------|-------------------|
| `product_id` | LONG | Primary key | Unique, starting at 10000 |
| `sku` | STRING | Stock keeping unit | Template: `SKU-dddddddd` |
| `product_name` | STRING | Product name | Prefix + category |
| `category` | STRING | Product category | Values list |
| `subcategory` | STRING | Subcategory | Values list by category |
| `brand` | STRING | Brand name | Values list |
| `unit_price` | DECIMAL(10,2) | Price | Range by category |
| `cost` | DECIMAL(10,2) | Cost | 40-70% of price |
| `active` | BOOLEAN | Is active | 95% true |

```python
categories = ["Electronics", "Clothing", "Home & Garden", "Sports", "Beauty", "Food & Grocery", "Toys", "Automotive"]

products = (
    dg.DataGenerator(spark, rows=10_000, partitions=4)
    .withColumn("product_id", "long", minValue=10_000, uniqueValues=10_000)
    .withColumn("sku", "string", template=r"SKU-dddddddd")
    .withColumn("category", "string", values=categories)
    .withColumn("product_name", "string", prefix="Product-", baseColumn="product_id")
    .withColumn("brand", "string", values=["BrandA", "BrandB", "BrandC", "BrandD", "BrandE", "Generic"])
    .withColumn("unit_price", "decimal(10,2)", minValue=5, maxValue=500, random=True)
    .withColumn("cost", "decimal(10,2)", expr="unit_price * (0.4 + rand() * 0.3)")
    .withColumn("active", "boolean", expr="rand() < 0.95")
    .build()
)
```

### Transactions

| Column | Type | Description | Generation Pattern |
|--------|------|-------------|-------------------|
| `txn_id` | LONG | Primary key | Unique |
| `customer_id` | LONG | Foreign key | Match customer range |
| `store_id` | LONG | Store location | Values list |
| `txn_timestamp` | TIMESTAMP | Transaction time | Random, weighted by time |
| `payment_method` | STRING | Payment type | Weighted values |
| `total_amount` | DECIMAL(12,2) | Transaction total | Computed from line items |
| `discount_amount` | DECIMAL(10,2) | Discounts applied | 0-20% of total |
| `tax_amount` | DECIMAL(10,2) | Sales tax | ~8% of subtotal |

```python
transactions = (
    dg.DataGenerator(spark, rows=1_000_000, partitions=20)
    .withColumn("txn_id", "long", minValue=1, uniqueValues=1_000_000)
    .withColumn("customer_id", "long", minValue=1_000_000, maxValue=1_099_999)
    .withColumn("store_id", "long", minValue=100, maxValue=150)
    .withColumn("txn_timestamp", "timestamp", begin="2024-01-01", end="2024-12-31", random=True)
    .withColumn("payment_method", "string", values=["Credit Card", "Debit Card", "Cash", "Digital Wallet", "Gift Card"], weights=[40, 25, 15, 15, 5])
    .withColumn("subtotal", "decimal(12,2)", minValue=10, maxValue=500, random=True, omit=True)
    .withColumn("discount_pct", "float", expr="rand() * 0.2", omit=True)
    .withColumn("discount_amount", "decimal(10,2)", expr="subtotal * discount_pct")
    .withColumn("tax_amount", "decimal(10,2)", expr="(subtotal - discount_amount) * 0.08")
    .withColumn("total_amount", "decimal(12,2)", expr="subtotal - discount_amount + tax_amount")
    .build()
)
```

### Transaction Line Items

| Column | Type | Description | Generation Pattern |
|--------|------|-------------|-------------------|
| `line_item_id` | LONG | Primary key | Unique |
| `txn_id` | LONG | Foreign key | Match transaction range |
| `product_id` | LONG | Foreign key | Match product range |
| `quantity` | INTEGER | Units purchased | 1-10, exponential |
| `unit_price` | DECIMAL(10,2) | Price at sale | Match product price |
| `line_total` | DECIMAL(12,2) | quantity * price | Computed |

```python
# Average 3 items per transaction
line_items = (
    dg.DataGenerator(spark, rows=3_000_000, partitions=30)
    .withColumn("line_item_id", "long", minValue=1, uniqueValues=3_000_000)
    .withColumn("txn_id", "long", minValue=1, maxValue=1_000_000)
    .withColumn("product_id", "long", minValue=10_000, maxValue=19_999)
    .withColumn("quantity", "integer", minValue=1, maxValue=10, distribution="exponential")
    .withColumn("unit_price", "decimal(10,2)", minValue=5, maxValue=500, random=True)
    .withColumn("line_total", "decimal(12,2)", expr="quantity * unit_price")
    .build()
)
```

### Inventory

| Column | Type | Description | Generation Pattern |
|--------|------|-------------|-------------------|
| `inventory_id` | LONG | Primary key | Unique |
| `product_id` | LONG | Foreign key | Match product range |
| `store_id` | LONG | Store location | Values list |
| `quantity_on_hand` | INTEGER | Current stock | 0-500, varies |
| `reorder_point` | INTEGER | Min stock level | 10-50 |
| `last_updated` | TIMESTAMP | Last change | Recent timestamp |

```python
inventory = (
    dg.DataGenerator(spark, rows=500_000, partitions=10)  # 10K products * 50 stores
    .withColumn("inventory_id", "long", minValue=1, uniqueValues=500_000)
    .withColumn("product_id", "long", minValue=10_000, maxValue=19_999)
    .withColumn("store_id", "long", minValue=100, maxValue=150)
    .withColumn("quantity_on_hand", "integer", minValue=0, maxValue=500, distribution="exponential")
    .withColumn("reorder_point", "integer", minValue=10, maxValue=50, random=True)
    .withColumn("last_updated", "timestamp", begin="2024-01-01", end="2024-12-31", random=True)
    .build()
)
```

## Using dbldatagen Multi-Table Dataset

dbldatagen includes a pre-built retail sales order dataset:

```python
from dbldatagen import Datasets

ds = Datasets(spark)

# Generate related tables
customers = ds.getTable("multi_table/sales_order", "customers", numCustomers=100_000)
orders = ds.getTable("multi_table/sales_order", "base_orders", numOrders=1_000_000)
line_items = ds.getTable("multi_table/sales_order", "base_order_line_items")

# Get combined tables with resolved foreign keys
full_orders = ds.getCombinedTable("multi_table/sales_order", "orders")
```

## Realistic Patterns

### Purchase Frequency by Tier
```python
# Platinum customers buy more frequently
.withColumn("base_frequency", "integer",
            expr="""case loyalty_tier
                when 'Platinum' then 20
                when 'Gold' then 12
                when 'Silver' then 6
                else 3
            end""")
```

### Seasonal Sales Patterns
```python
# Holiday spikes
.withColumn("month", "integer", expr="month(txn_timestamp)", omit=True)
.withColumn("seasonal_factor", "float",
            expr="""case
                when month = 11 then 1.5
                when month = 12 then 2.5
                when month in (6, 7) then 0.8
                else 1.0
            end""")
.withColumn("adjusted_amount", "decimal(12,2)", expr="base_amount * seasonal_factor")
```

### Basket Size Distribution
```python
# Most baskets are 1-3 items, with long tail
.withColumn("items_in_basket", "integer", minValue=1, maxValue=20, distribution="exponential")
```

### Price Points by Category
```python
category_prices = {
    "Electronics": (50, 2000),
    "Clothing": (10, 300),
    "Food & Grocery": (1, 50),
    "Home & Garden": (20, 500),
}
```

## CDC Generation

```python
def generate_retail_cdc(spark, volume_path, n_customers=100_000, n_batches=5, seed=42):
    """Generate retail CDC data for pipeline demos."""
    import dbldatagen as dg
    from utils.mimesis_text import mimesisText
    from pyspark.sql import functions as F

    # Initial load — all APPENDs
    initial = (
        dg.DataGenerator(spark, rows=n_customers, partitions=10, randomSeed=seed)
        .withColumn("id", "long", minValue=1, uniqueValues=n_customers)
        .withColumn("first_name", "string", text=mimesisText("person.first_name"))
        .withColumn("last_name", "string", text=mimesisText("person.last_name"))
        .withColumn("email", "string", text=mimesisText("person.email"))
        .withColumn("address", "string", text=mimesisText("address.address"))
        .withColumn("operation", "string", values=["APPEND"])
        .withColumn("operation_date", "timestamp", begin="2024-01-01", end="2024-01-01")
        .build()
    )
    initial.write.format("json").mode("overwrite").save(f"{volume_path}/batch_0")

    # Incremental batches
    for batch in range(1, n_batches + 1):
        batch_df = (
            dg.DataGenerator(spark, rows=n_customers // 10, partitions=4, randomSeed=seed + batch)
            .withColumn("id", "long", minValue=1, maxValue=n_customers)
            .withColumn("first_name", "string", text=mimesisText("person.first_name"))
            .withColumn("last_name", "string", text=mimesisText("person.last_name"))
            .withColumn("email", "string", text=mimesisText("person.email"))
            .withColumn("address", "string", text=mimesisText("address.address"))
            .withColumn("operation", "string", values=["APPEND", "UPDATE", "DELETE"], weights=[50, 30, 10])
            .withColumn("operation_date", "timestamp",
                        expr=f"cast('2024-01-{batch + 1:02d}' as timestamp) + make_interval(0,0,0,0, cast(rand() * 23 as int), cast(rand() * 59 as int), 0)")
            .build()
        )
        batch_df.write.format("json").mode("overwrite").save(f"{volume_path}/batch_{batch}")
```

## Data Quality Injection

```python
# Retail-appropriate quality issues
# 2% null emails, 1% null phone numbers, 3% duplicate transactions
.withColumn("email", "string", text=mimesisText("person.email"), percentNulls=0.02)
.withColumn("phone", "string", text=mimesisText("person.telephone"), percentNulls=0.01)

# Inject duplicate transactions (4% rate)
clean_txns = generate_transactions(spark, n_transactions)
txns_with_dupes = clean_txns.union(clean_txns.sample(0.04))
```

## Medallion Output

```python
# Write raw to Volume for bronze ingestion
customers_df.write.format("json").save(f"/Volumes/{catalog}/{schema}/{volume}/customers")
transactions_df.write.format("json").save(f"/Volumes/{catalog}/{schema}/{volume}/transactions")
```

## Complete Retail Demo

```python
def generate_retail_demo(
    spark,
    n_customers: int = 100_000,
    n_products: int = 10_000,
    n_transactions: int = 1_000_000,
    catalog: str = "demo",
    schema: str = "retail"
):
    """Generate complete retail demo dataset."""

    # Generate all tables
    customers = generate_customers(spark, n_customers)
    products = generate_products(spark, n_products)
    transactions = generate_transactions(spark, n_transactions, n_customers)
    line_items = generate_line_items(spark, n_transactions * 3, n_transactions, n_products)
    inventory = generate_inventory(spark, n_products, 50)

    # Write to Unity Catalog
    tables = {
        "customers": customers,
        "products": products,
        "transactions": transactions,
        "line_items": line_items,
        "inventory": inventory,
    }

    for name, df in tables.items():
        df.write.format("delta").mode("overwrite").saveAsTable(f"{catalog}.{schema}.{name}")

    return tables
```

## Common Demo Queries

### Customer 360 View
```sql
SELECT
    c.customer_id,
    c.first_name,
    c.last_name,
    c.loyalty_tier,
    COUNT(DISTINCT t.txn_id) as total_transactions,
    SUM(t.total_amount) as total_spend,
    AVG(t.total_amount) as avg_order_value
FROM customers c
LEFT JOIN transactions t ON c.customer_id = t.customer_id
GROUP BY c.customer_id, c.first_name, c.last_name, c.loyalty_tier
```

### Product Performance
```sql
SELECT
    p.category,
    p.product_name,
    SUM(li.quantity) as units_sold,
    SUM(li.line_total) as revenue
FROM products p
JOIN line_items li ON p.product_id = li.product_id
GROUP BY p.category, p.product_name
ORDER BY revenue DESC
```

### Inventory Alerts
```sql
SELECT
    i.store_id,
    p.product_name,
    i.quantity_on_hand,
    i.reorder_point
FROM inventory i
JOIN products p ON i.product_id = p.product_id
WHERE i.quantity_on_hand <= i.reorder_point
ORDER BY i.quantity_on_hand
```

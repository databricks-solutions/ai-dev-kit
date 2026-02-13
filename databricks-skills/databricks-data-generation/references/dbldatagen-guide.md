# dbldatagen Guide

Databricks Labs Data Generator (dbldatagen) for Spark-native synthetic data at scale.

## Installation

```bash
uv pip install dbldatagen
```

> **Connect compatibility:** Some dbldatagen features use Python UDFs internally and fail on Databricks Connect + serverless. Features marked `[UDF]` below require a Databricks notebook (where libraries are installed on the cluster). See SKILL.md's Connect Compatibility section for workarounds.

## Core Concepts

### DataGenerator

The main class for building synthetic data specs:

```python
import dbldatagen as dg

spec = (
    dg.DataGenerator(spark, rows=1_000_000, partitions=20)
    .withColumn("id", "long", minValue=1, uniqueValues=1000000)
    .withColumn("name", "string", template=r"\\w \\w")
    .withColumn("amount", "decimal(10,2)", minValue=0, maxValue=10000, random=True)
    .build()
)
```

### Key Parameters

| Parameter | Description |
|-----------|-------------|
| `rows` | Total rows to generate |
| `partitions` | Spark partitions (auto-computed if omitted) |
| `randomSeed` | Seed for reproducibility |
| `randomSeedMethod` | `"hash_fieldname"` or `"fixed"` |

## Column Types

### Numeric
```python
.withColumn("id", "long", minValue=1000, maxValue=9999)
.withColumn("amount", "decimal(12,2)", minValue=0, maxValue=100000, random=True)
.withColumn("quantity", "integer", minValue=1, maxValue=100, distribution="normal")
```

### String
> **`[UDF]`** Templates use pandas UDFs internally. Over Connect + serverless, use `expr=` with SQL string functions instead.

```python
# Template-based
.withColumn("phone", "string", template=r"(ddd)-ddd-dddd")
.withColumn("email", "string", template=r"\\w.\\w@\\w.com")
.withColumn("ssn", "string", template=r"ddd-dd-dddd")

# Value list
.withColumn("status", "string", values=["Active", "Inactive", "Pending"])
.withColumn("tier", "string", values=["Bronze", "Silver", "Gold"], weights=[50, 35, 15])

# Prefix-based
.withColumn("code", "string", prefix="SKU-", baseColumn="id")
```

#### Template Character Reference

Templates generate string values using special characters. By default, special characters
have meaning without escaping. Use `escapeSpecialChars=True` on `TemplateGenerator` for
explicit escape-only mode.

| Char | Generates | Range |
|------|-----------|-------|
| `d` | Random digit | 0-9 |
| `D` | Random non-zero digit | 1-9 |
| `a` | Random lowercase letter | a-z |
| `A` | Random uppercase letter | A-Z |
| `k` | Random lowercase alphanumeric | a-z, 0-9 |
| `K` | Random uppercase alphanumeric | A-Z, 0-9 |
| `x` | Random lowercase hex digit | 0-f |
| `X` | Random uppercase hex digit | 0-F |
| `\n` | Random number | 0-255 |
| `\N` | Random number | 0-65535 |
| `\w` | Random word (lowercase) | Lorem ipsum word list |
| `\W` | Random word (uppercase) | Lorem ipsum word list |
| `\v0`..`\v9` | Array element from base value | Elements 0-9 |
| `\V` | Entire base value as string | Base column value |
| `\|` | Alternation separator | Randomly picks one variant |

```python
# Common template patterns
.withColumn("phone", "string", template=r"(ddd)-ddd-dddd")
.withColumn("ssn", "string", template=r"ddd-dd-dddd")
.withColumn("ip", "string", template=r"\n.\n.\n.\n")
.withColumn("mac", "string", template=r"XX:XX:XX:XX:XX:XX")
.withColumn("uuid_like", "string", template=r"xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")

# Alternation: randomly picks one format per row
.withColumn("phone", "string", template=r"(ddd)-ddd-dddd|1(ddd) ddd-dddd|ddd ddddddd")

# Custom word list via TemplateGenerator
.withColumn("name", "string", text=dg.TemplateGenerator(
    r"\w \w", escapeSpecialChars=True,
    extendedWordList=["alpha", "beta", "gamma", "delta"]))
```

### Temporal
```python
.withColumn("created_at", "timestamp", begin="2024-01-01", end="2024-12-31", random=True)
.withColumn("order_date", "date", begin="2023-01-01", end="2024-12-31")
.withColumn("event_time", "timestamp", begin="2024-01-01", interval="1 minute")
```

### Boolean
```python
.withColumn("is_active", "boolean", expr="rand() < 0.8")
.withColumn("is_fraud", "boolean", expr="rand() < 0.02")
```

## Advanced Patterns

### Foreign Key Relationships

```python
# Parent table
customers = (
    dg.DataGenerator(spark, rows=10000, partitions=4)
    .withColumn("customer_id", "long", minValue=1000, uniqueValues=10000)
    .withColumn("name", "string", template=r"\\w \\w")
    .build()
)

# Child table with FK
orders = (
    dg.DataGenerator(spark, rows=100000, partitions=10)
    .withColumn("order_id", "long", minValue=1, uniqueValues=100000)
    .withColumn("customer_id", "long", minValue=1000, maxValue=10999)  # Match parent range
    .withColumn("amount", "decimal(10,2)", minValue=10, maxValue=1000, random=True)
    .build()
)
```

> **`[UDF]`** Distributions use numpy on Spark workers. Over Connect + serverless, use `random=True` for uniform distribution or `expr=` for shaped distributions.

### Distributions

```python
# Normal distribution
.withColumn("age", "integer", minValue=18, maxValue=85, distribution="normal")

# Exponential (long tail)
.withColumn("purchase_amount", "decimal(10,2)", minValue=1, maxValue=10000, distribution="exponential")

# Beta distribution — naturally [0,1], scaled to minValue/maxValue
.withColumn("rating", "float", minValue=1, maxValue=5, distribution=dg.distributions.Beta(2, 5))

# Gamma distribution — right-skewed positive values
.withColumn("wait_time", "float", minValue=1, maxValue=3600,
            distribution=dg.distributions.Gamma(shape=2.0, scale=2.0))
```

### Distribution Decision Table

| Distribution | Constructor | Best For | Shape |
|---|---|---|---|
| `"normal"` (string) | N/A | Symmetric data (age, temperature) | Bell curve |
| `Normal(mean, stddev)` | `Normal(0.0, 1.0)` | Fine-tuned bell curves | Symmetric |
| `"exponential"` (string) | N/A | Long-tail data (purchase amounts) | Steep decay |
| `Exponential(rate)` | `Exponential(rate=1.0)` | Inter-arrival times, decay | Right-skewed |
| `Beta(alpha, beta)` | `Beta(2, 5)` | Bounded [0,1] values (scores, %) | Configurable |
| `Gamma(shape, scale)` | `Gamma(2.0, 2.0)` | Positive right-skewed (amounts, durations) | Right-skewed |

**Beta shape guide:**
- `Beta(2, 5)` — left-skewed (most values low): discount rates
- `Beta(5, 2)` — right-skewed (most values high): quality scores
- `Beta(2, 2)` — symmetric bell in [0,1]: probabilities
- `Beta(0.5, 0.5)` — U-shaped (values at extremes)

**Gamma shape guide:**
- `Gamma(1.0, scale)` — equivalent to Exponential
- `Gamma(2.0, scale)` — moderate right skew: transaction amounts
- `Gamma(5.0, scale)` — more symmetric: response times

All distributions accept `.withRandomSeed(seed)` for reproducibility:
```python
dist = dg.distributions.Gamma(2.0, 2.0).withRandomSeed(42)
.withColumn("amount", "float", minValue=1, maxValue=10000, distribution=dist)
```

### SQL Expressions

```python
.withColumn("full_name", "string", expr="concat(first_name, ' ', last_name)")
.withColumn("total", "decimal(12,2)", expr="quantity * unit_price")
.withColumn("age_group", "string", expr="case when age < 30 then 'Young' when age < 50 then 'Middle' else 'Senior' end")
```

### Omit Intermediate Columns

```python
.withColumn("base_id", "long", minValue=1, uniqueValues=10000, omit=True)
.withColumn("customer_code", "string", prefix="CUST-", baseColumn="base_id")
```

### INFER_DATATYPE

Let dbldatagen infer the column type from a SQL expression. The type is resolved at build time
from the expression's return type.

```python
# Infer type from SQL expression — no need to specify "string" or "date"
.withColumn("computed_date", dg.INFER_DATATYPE, expr="current_date()")
.withColumn("full_name", dg.INFER_DATATYPE, expr="concat(first_name, ' ', last_name)")
.withColumn("discounted", dg.INFER_DATATYPE, expr="amount * 0.9")
```

> **`[UDF]`** Constraints check `isinstance(expr, pyspark.sql.column.Column)` but Connect returns `pyspark.sql.connect.column.Column`. Over Connect, use `.build().filter("sql_condition")` instead.

## Constraints

Constraints are applied after data generation to filter or reshape output rows. Most use a
rejection-based strategy, so the final row count may be slightly less than requested.

```python
from dbldatagen.constraints import (
    SqlExpr, UniqueCombinations, RangedValues,
    ChainedRelation, LiteralRelation,
    NegativeValues, PositiveValues,
)
```

### SqlExpr -- filter rows by arbitrary SQL condition

```python
.withConstraint(SqlExpr("amount > 0 AND status != 'CANCELLED'"))
```

### UniqueCombinations -- enforce unique value combinations across columns

```python
# Ensure each (region, product_id) pair appears only once
.withConstraint(UniqueCombinations(columns=["region", "product_id"]))

# All output columns unique (pass no arguments)
.withConstraint(UniqueCombinations())
```

### RangedValues -- column value between two other columns

```python
# Keep rows where mid_value is between low_value and high_value
.withConstraint(RangedValues(columns="mid_value", lowValue="low_value", highValue="high_value", strict=False))
```

### ChainedRelation -- enforce ordering between columns

```python
# Ensure start_date < mid_date < end_date
.withConstraint(ChainedRelation(columns=["start_date", "mid_date", "end_date"], relation="<"))
```

### LiteralRelation -- compare column to a literal value

```python
# Keep rows where score > 0
.withConstraint(LiteralRelation(columns="score", relation=">", value=0))
```

### PositiveValues / NegativeValues

```python
# balance >= 0 (strict=True means balance > 0)
.withConstraint(PositiveValues(columns="balance", strict=True))

# loss < 0
.withConstraint(NegativeValues(columns="loss"))
```

> **`[UDF]`** `mimesisText()` uses `PyfuncTextFactory` (pandas UDFs) and does NOT work over Connect + serverless. Use `values=["James","Mary",...], random=True` for PII columns via Connect.

## MimesisText (Native PII)

`mimesisText()` is the primary pattern for generating realistic PII in dbldatagen.
It wraps the Mimesis library via `PyfuncTextFactory` and distributes generation across Spark workers -- no UDFs needed.

### Simple usage with mimesisText()

```python
import dbldatagen as dg
from utils.mimesis_text import mimesisText

spec = (
    dg.DataGenerator(spark, rows=100_000, partitions=10)
    .withColumn("customer_id", "long", minValue=1_000_000, uniqueValues=100_000)
    .withColumn("first_name", "string", text=mimesisText("person.first_name"))
    .withColumn("last_name", "string", text=mimesisText("person.last_name"))
    .withColumn("email", "string", text=mimesisText("person.email"))
    .withColumn("phone", "string", text=mimesisText("person.telephone"))
    .withColumn("address", "string", text=mimesisText("address.address"))
    .withColumn("city", "string", text=mimesisText("address.city"))
    .build()
)
```

### Custom MimesisText -- locale and lambda patterns

```python
from dbldatagen import PyfuncTextFactory

# Custom locale
def init_french(ctx):
    from mimesis import Generic
    from mimesis.locales import Locale
    ctx.mimesis = Generic(locale=Locale.FR)

FrenchText = (
    PyfuncTextFactory(name="FrenchText")
    .withInit(init_french)
    .withRootProperty("mimesis")
)

spec = (
    dg.DataGenerator(spark, rows=100_000, partitions=10)
    .withColumn("customer_id", "long", minValue=1, uniqueValues=100_000)
    .withColumn("name", "string", text=FrenchText(lambda g: g.person.full_name()))
    .withColumn("email", "string", text=FrenchText(lambda g: g.person.email()))
    .build()
)
```

```python
from utils.mimesis_text import MimesisText

# Lambda escape hatch for complex generation
spec = (
    dg.DataGenerator(spark, rows=50_000, partitions=8)
    .withColumn("product_id", "long", minValue=1, uniqueValues=50_000)
    .withColumn("sku", "string", template=r"SKU-dddddddd")
    .withColumn("company", "string", text=MimesisText(lambda g: g.finance.company()))
    .build()
)
```

## PyfuncText

Use `PyfuncText` for custom Python functions that generate text values. The function receives
a context object and the base column value.

```python
from dbldatagen import PyfuncText

def custom_generator(context, base_value):
    return f"ITEM-{base_value:06d}"

spec = (
    dg.DataGenerator(spark, rows=10_000, partitions=4)
    .withColumn("id", "long", minValue=1, uniqueValues=10_000)
    .withColumn("item_code", "string", text=PyfuncText(custom_generator))
    .build()
)
```

For stateful generation, provide an `init` function:

```python
from dbldatagen import PyfuncText

def init_fn(context):
    import random
    context.rng = random.Random(42)

def generate_code(context, base_value):
    suffix = context.rng.choice(["A", "B", "C"])
    return f"CODE-{base_value}-{suffix}"

spec = (
    dg.DataGenerator(spark, rows=10_000, partitions=4)
    .withColumn("id", "long", minValue=1, uniqueValues=10_000)
    .withColumn("code", "string", text=PyfuncText(generate_code, init=init_fn))
    .build()
)
```

## Struct Columns

Build nested struct columns from existing columns. Fields can reference other column names
or SQL expressions.

```python
from utils.mimesis_text import mimesisText

# Struct from existing columns (field list of tuples)
spec = (
    dg.DataGenerator(spark, rows=10_000, partitions=4)
    .withColumn("street_col", "string", text=mimesisText("address.address"))
    .withColumn("city_col", "string", text=mimesisText("address.city"))
    .withColumn("state_col", "string", values=["CA", "NY", "TX", "WA"])
    .withStructColumn("address_struct", fields=[
        ("street", "street_col"),
        ("city", "city_col"),
        ("state", "state_col"),
    ])
    .build()
)

# As JSON string
spec = (
    dg.DataGenerator(spark, rows=10_000, partitions=4)
    .withColumn("device_id", "string", template=r"DEV-dddddd")
    .withColumn("value", "float", minValue=0, maxValue=100, random=True)
    .withStructColumn("metadata_json", fields=[
        ("sensor_id", "device_id"),
        ("reading", "value"),
    ], asJson=True)
    .build()
)
```

## numColumns / numFeatures

Generate multiple columns with the same specification. Columns are named `{baseName}_{ix}`
where ix starts at 0. `numFeatures` is an alias for `numColumns`.

```python
# Generate 10 individual columns: sensor_0, sensor_1, ..., sensor_9
spec = (
    dg.DataGenerator(spark, rows=100_000, partitions=10)
    .withColumn("device_id", "long", minValue=1, uniqueValues=100_000)
    .withColumn("sensor", "float", minValue=0.0, maxValue=100.0,
                random=True, numColumns=10)
    .build()
)
# Columns: device_id, sensor_0, sensor_1, ..., sensor_9
```

### Array Column

Combine multiple columns into a single array column with `structType="array"`:

```python
from pyspark.sql.types import FloatType

# Single array<float> column with 10 elements per row
.withColumn("features", FloatType(), minValue=0.0, maxValue=1.0,
            random=True, numColumns=10, structType="array")
```

### Variable-Length Arrays

Only supported with `structType="array"`:

```python
# Random array length between 3 and 8 elements per row
.withColumn("readings", FloatType(), minValue=0.0, maxValue=50.0,
            random=True, numColumns=(3, 8), structType="array")
```

## baseColumnType

Controls how values from base columns are transformed into derived columns.

| Value | Description |
|---|---|
| `"auto"` | Auto-detect based on column spec (default) |
| `"hash"` | Hash of base column value — stable mapping, anonymized |
| `"values"` | Use raw base column values directly — enables `\v0`, `\v1` template syntax |
| `"raw_values"` | Raw values without scaling to target range |

```python
# Hash: derive a stable integer from a string column
.withColumn("name", "string", text=mimesisText("person.full_name"))
.withColumn("name_hash", "integer", minValue=0, maxValue=9999,
            baseColumn="name", baseColumnType="hash")

# Values: compose from multiple base columns using template
.withColumn("first", "string", text=mimesisText("person.first_name"))
.withColumn("last", "string", text=mimesisText("person.last_name"))
.withColumn("display_name", "string",
            baseColumn=["first", "last"], baseColumnType="values",
            template=r"\v0 \v1")

# Format with base column values
.withColumn("label", "string", format="customer_%s",
            baseColumn="customer_id", baseColumnType="values")
```

## Streaming Generation

Build a streaming DataFrame for continuous data ingestion testing.

```python
import dbldatagen as dg

streaming_df = (
    dg.DataGenerator(spark, rows=1_000_000, partitions=10)
    .withColumn("event_id", "long", minValue=1, uniqueValues=1_000_000)
    .withColumn("timestamp", "timestamp", begin="2024-01-01", end="2024-12-31", random=True)
    .withColumn("value", "float", minValue=0, maxValue=100, random=True)
    .build(withStreaming=True, options={"rowsPerSecond": 5000})
)

# Write to Delta table
(streaming_df.writeStream
    .format("delta")
    .option("checkpointLocation", "/tmp/checkpoint")
    .toTable("catalog.schema.streaming_events"))
```

Note: Some constraints (like `UniqueCombinations`) do not support streaming mode.
Streaming-compatible constraints include `SqlExpr`, `RangedValues`, `ChainedRelation`,
`LiteralRelation`, `PositiveValues`, and `NegativeValues`.

## Serialization

Save a DataGenerator spec to JSON for reproducibility, and reload it later.

```python
import dbldatagen as dg

# Build a spec
spec = (
    dg.DataGenerator(spark, rows=100_000, partitions=10)
    .withColumn("id", "long", minValue=1, uniqueValues=100_000)
    .withColumn("name", "string", template=r"\\w \\w")
    .withColumn("amount", "decimal(10,2)", minValue=0, maxValue=10000, random=True)
)

# Save to JSON string
json_str = spec.saveToJson()

# Reload later (spark session must be available)
spec_restored = dg.DataGenerator.loadFromJson(json_str)
df = spec_restored.build()
```

## scriptTable / scriptMerge

Generate DDL and MERGE SQL statements from a DataGenerator spec.

### scriptTable -- CREATE TABLE DDL

```python
spec = (
    dg.DataGenerator(spark, rows=100_000, partitions=10)
    .withColumn("id", "long", minValue=1, uniqueValues=100_000)
    .withColumn("name", "string", template=r"\\w \\w")
    .withColumn("amount", "decimal(10,2)", minValue=0, maxValue=10000, random=True)
)

ddl = spec.scriptTable(name="catalog.schema.my_table", tableFormat="delta")
print(ddl)
# CREATE TABLE IF NOT EXISTS catalog.schema.my_table (
#     id BIGINT,
#     name STRING,
#     amount DECIMAL(10,2)
# )
# using delta
```

### scriptMerge -- MERGE INTO statement

```python
merge_sql = spec.scriptMerge(
    tgtName="catalog.schema.target",
    srcName="catalog.schema.source",
    joinExpr="tgt.id = src.id",
)
print(merge_sql)
```

## Multi-Table Datasets

dbldatagen includes pre-built multi-table scenarios via the `Datasets` class:

```python
from dbldatagen import Datasets

ds = Datasets(spark)

# List available datasets
ds.list()

# Get specific table from dataset
customers = ds.getTable("multi_table/sales_order", "customers", numCustomers=10000)
orders = ds.getTable("multi_table/sales_order", "orders", numOrders=100000)

# Get combined table (with resolved FKs)
full_orders = ds.getCombinedTable("multi_table/sales_order", "orders")
```

### Available Datasets

| Dataset | Description | Tables / Columns |
|---------|-------------|-----------------|
| `multi_table/sales_order` | E-commerce order pipeline | customers, carriers, catalog_items, orders, order_line_items, order_shipments, invoices |
| `multi_table/telephony` | Telecom billing scenario | customers, plans, devices |
| `basic/user` | User profiles | names, emails, IPs, signup dates |
| `basic/telematics` | GPS/vehicle tracking | device_id, lat, lon, speed, heading |
| `basic/geometries` | WKT geometry data | geometry types, coordinates |
| `basic/stock_ticker` | Financial time-series | symbol, open, high, low, close, volume |
| `basic/process_historian` | Industrial process data | tag_id, timestamp, value, quality |

### Dataset Usage Examples

```python
from dbldatagen import Datasets

ds = Datasets(spark)

# Basic dataset — single table, pass rows directly
users_df = ds.getTable("basic/user", rows=50_000)

# Multi-table — specify table name and sizing params
customers_df = ds.getTable("multi_table/sales_order", "customers", numCustomers=10_000)
orders_df = ds.getTable("multi_table/sales_order", "orders", numOrders=100_000)

# Combined table — resolves FKs automatically
full_orders = ds.getCombinedTable("multi_table/sales_order", "orders")

# Stock ticker data
stocks_df = ds.getTable("basic/stock_ticker", rows=100_000)

# Industrial process historian
process_df = ds.getTable("basic/process_historian", rows=500_000)
```

## DataAnalyzer

Analyze existing DataFrames to generate dbldatagen code that produces data with similar
characteristics. Useful for creating synthetic versions of production tables.

```python
from dbldatagen import DataAnalyzer
```

### Summarize a DataFrame

```python
source_df = spark.table("catalog.schema.customers")
analyzer = DataAnalyzer(df=source_df)

# Summary as DataFrame (use display() in notebooks)
summary_df = analyzer.summarizeToDF()
display(summary_df)

# Summary as string
print(analyzer.summarize())
```

Summary metrics include: column count, distinct values, null probability,
min/max, mean, stddev, and string length ranges per column.

### Generate Code from Data

Analyzes actual data statistics (min, max, null rates) to produce a starting-point spec:

```python
analyzer = DataAnalyzer(df=source_df)
code = analyzer.scriptDataGeneratorFromData(name="customer_synth")
print(code)
# Output: Python code for a DataGenerator with withColumn() calls matching the data profile
```

### Generate Code from Schema Only

Class method — no data analysis, just schema → code with default value ranges:

```python
schema = spark.table("catalog.schema.customers").schema
code = DataAnalyzer.scriptDataGeneratorFromSchema(schema, name="customer_synth")
print(code)
```

### Type Mapping Defaults

When generating from schema only (no data stats available):

| Spark Type | Generated Spec |
|---|---|
| StringType | `template=r'\\w'` |
| IntegerType, LongType | `minValue=0, maxValue=1000000` |
| BooleanType | `expr='id % 2 = 1'` |
| DateType | `expr='current_date()'` |
| DecimalType | `minValue=0, maxValue=1000000.0` |
| FloatType, DoubleType | `minValue=0.0, maxValue=1000000.0, step=0.1` |
| TimestampType | `begin/end/interval` defaults |

When generating from data, actual min/max/null_probability values are used instead.

> **Note:** Generated code is experimental and intended as a starting point. Refine by
> replacing templates with `mimesisText()` for PII, adding constraints, using proper
> distributions, and defining FK relationships that DataAnalyzer cannot detect.

See `references/schema-introspection-patterns.md` for full workflow examples.

## Performance Tips

### Partition Sizing
```python
# Auto-compute partitions based on row count
partitions = max(4, rows // 100_000)

# Or let dbldatagen auto-compute
spec = dg.DataGenerator(spark, rows=10_000_000)  # partitions auto-computed
```

### Caching Large Datasets
```python
df = spec.build()
df.cache()
df.count()  # Trigger materialization
```

### Random Seed Methods

- `"hash_fieldname"` (default): Seed varies by column name -- columns are independent.
- `"fixed"`: Same seed for all columns -- useful for correlated test data.

```python
spec = dg.DataGenerator(spark, rows=1_000_000, randomSeed=42, randomSeedMethod="hash_fieldname")
```

## Common Patterns

### Customer Profile
```python
customer_spec = (
    dg.DataGenerator(spark, rows=100_000, partitions=10)
    .withColumn("customer_id", "long", minValue=1000000, uniqueValues=100000)
    .withColumn("first_name", "string", text=mimesisText("person.first_name"))
    .withColumn("last_name", "string", text=mimesisText("person.last_name"))
    .withColumn("email", "string", text=mimesisText("person.email"))
    .withColumn("phone", "string", text=mimesisText("person.telephone"))
    .withColumn("city", "string", values=["New York", "Los Angeles", "Chicago", "Houston", "Phoenix"])
    .withColumn("state", "string", values=["NY", "CA", "IL", "TX", "AZ"])
    .withColumn("loyalty_tier", "string", values=["Bronze", "Silver", "Gold", "Platinum"], weights=[50, 30, 15, 5])
    .withColumn("signup_date", "date", begin="2020-01-01", end="2024-12-31", random=True)
    .withColumn("lifetime_value", "decimal(12,2)", minValue=0, maxValue=50000, distribution="exponential")
)
```

### Transaction Record
```python
transaction_spec = (
    dg.DataGenerator(spark, rows=1_000_000, partitions=20)
    .withColumn("txn_id", "long", minValue=1, uniqueValues=1000000)
    .withColumn("customer_id", "long", minValue=1000000, maxValue=1099999)
    .withColumn("product_id", "long", minValue=10000, maxValue=19999)
    .withColumn("quantity", "integer", minValue=1, maxValue=10, distribution="exponential")
    .withColumn("unit_price", "decimal(10,2)", minValue=5, maxValue=500, random=True)
    .withColumn("total_amount", "decimal(12,2)", expr="quantity * unit_price")
    .withColumn("txn_timestamp", "timestamp", begin="2024-01-01", end="2024-12-31", random=True)
    .withColumn("payment_method", "string", values=["Credit", "Debit", "Cash", "Digital"], weights=[40, 30, 15, 15])
    .withConstraint(PositiveValues(columns="total_amount", strict=True))
)
```

### IoT Sensor Reading
```python
sensor_spec = (
    dg.DataGenerator(spark, rows=10_000_000, partitions=50)
    .withColumn("device_id", "long", minValue=1000, maxValue=2000)
    .withColumn("reading_id", "long", minValue=1, uniqueValues=10000000)
    .withColumn("timestamp", "timestamp", begin="2024-01-01", end="2024-12-31", interval="1 minute")
    .withColumn("temperature", "float", minValue=15.0, maxValue=35.0, distribution="normal")
    .withColumn("humidity", "float", minValue=30.0, maxValue=90.0, random=True)
    .withColumn("pressure", "float", minValue=980.0, maxValue=1030.0, distribution="normal")
    .withColumn("is_anomaly", "boolean", expr="temperature > 32 or temperature < 18")
)
```

### Time-Ordered Events with Constraints
```python
from dbldatagen.constraints import ChainedRelation

event_spec = (
    dg.DataGenerator(spark, rows=500_000, partitions=10)
    .withColumn("order_id", "long", minValue=1, uniqueValues=500_000)
    .withColumn("order_date", "timestamp", begin="2024-01-01", end="2024-06-30", random=True)
    .withColumn("ship_date", "timestamp", begin="2024-01-02", end="2024-07-15", random=True)
    .withColumn("delivery_date", "timestamp", begin="2024-01-05", end="2024-08-01", random=True)
    .withConstraint(ChainedRelation(columns=["order_date", "ship_date", "delivery_date"], relation="<"))
)
```

## Resources

- [dbldatagen Documentation](https://databrickslabs.github.io/dbldatagen/)
- [GitHub Repository](https://github.com/databrickslabs/dbldatagen)
- [Multi-Table Data Guide](https://databrickslabs.github.io/dbldatagen/public_docs/multi_table_data.html)
- [Constraints Guide](https://databrickslabs.github.io/dbldatagen/public_docs/constraints.html)

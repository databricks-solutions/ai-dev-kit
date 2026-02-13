# dbldatagen + Databricks Connect Patterns

Validated patterns for generating synthetic data with dbldatagen over Databricks Connect + serverless compute and writing to Unity Catalog.

## Complete Working Example

Validated: 1M rows, 11 columns, multiple types — generates and writes to UC without issues.

```python
from databricks.connect import DatabricksSession
import dbldatagen as dg
from pyspark.sql.types import (
    StringType, IntegerType, LongType, FloatType,
    DecimalType, TimestampType,
)

# --- Connect to Databricks (serverless) ---
spark = DatabricksSession.builder.serverless().getOrCreate()

CATALOG = "my_catalog"
SCHEMA = "retail"
ROW_COUNT = 1_000_000
PARTITIONS = 10  # Always set explicitly — Connect can't read defaultParallelism

FIRST_NAMES = ["James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis"]
REGIONS = ["Northeast", "Southeast", "Midwest", "Southwest", "West"]

customers = (
    dg.DataGenerator(sparkSession=spark, name="customers", rows=ROW_COUNT, partitions=PARTITIONS)
    .withIdOutput()
    .withColumn("first_name", StringType(), values=FIRST_NAMES, random=True)
    .withColumn("last_name", StringType(), values=LAST_NAMES, random=True)
    .withColumn("email", StringType(),
        expr="lower(concat(first_name, '.', last_name, cast(id % 1000 as string), '@example.com'))",
        baseColumns=["first_name", "last_name"])
    .withColumn("age", IntegerType(), minValue=18, maxValue=85, random=True)
    .withColumn("lifetime_value", DecimalType(12, 2), minValue=0, maxValue=50000, random=True)
    .withColumn("loyalty_tier", StringType(),
                values=["Bronze", "Silver", "Gold", "Platinum"],
                weights=[50, 30, 15, 5])
    .withColumn("region", StringType(), values=REGIONS, random=True)
    .withColumn("signup_ts", TimestampType(),
                begin="2020-01-01 00:00:00", end="2024-12-31 23:59:59",
                interval="1 day", random=True)
    .withColumn("is_active", "boolean", expr="rand() < 0.85")
    .withColumn("score", FloatType(), minValue=0.0, maxValue=100.0, step=0.1, random=True)
    .build()
)

# --- Write to Unity Catalog ---
existing = [row.databaseName for row in spark.sql(f"SHOW SCHEMAS IN {CATALOG}").collect()]
if SCHEMA not in existing:
    spark.sql(f"CREATE SCHEMA {CATALOG}.{SCHEMA}")

customers.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{CATALOG}.{SCHEMA}.customers")

# --- Validate ---
count = spark.table(f"{CATALOG}.{SCHEMA}.customers").count()
print(f"Wrote {count:,} rows to {CATALOG}.{SCHEMA}.customers")
spark.table(f"{CATALOG}.{SCHEMA}.customers").show(5)

spark.stop()
```

### Running

```bash
uv run --with 'databricks-connect==16.2.*' --with dbldatagen --with jmespath --with pyparsing scripts/my_script.py
```

## Catalyst-Safe Feature Reference

These features work over Connect + serverless because they compile to native Spark SQL expressions (no Python UDFs shipped to workers):

| Feature | Example | Notes |
|---------|---------|-------|
| `values=` | `values=["A", "B", "C"]` | Random selection from list |
| `weights=` | `weights=[50, 30, 20]` | Weighted distribution with `values=` |
| `random=True` | `random=True` | Randomize value selection |
| `minValue` / `maxValue` | `minValue=1, maxValue=1000` | Numeric ranges |
| `step` | `step=0.1` | Increment for numeric ranges |
| `begin` / `end` | `begin="2020-01-01 00:00:00"` | Date/timestamp ranges |
| `interval` | `interval="1 day"` | Step size for date ranges |
| `expr=` | `expr="lower(concat(col1, col2))"` | Spark SQL expressions |
| `baseColumns=` | `baseColumns=["first_name"]` | Column dependencies for `expr=` |
| `percentNulls=` | `percentNulls=0.05` | Null injection rate |
| `omit=True` | `omit=True` | Exclude column from final output |
| `.withIdOutput()` | `.withIdOutput()` | Include auto-increment `id` column |
| `uniqueValues=` | `uniqueValues=100000` | Unique value count for ID columns |
| `prefix=` / `suffix=` | `prefix="CUST-"` | String decoration |

### Supported Types

All standard Spark SQL types work: `StringType`, `IntegerType`, `LongType`, `FloatType`, `DoubleType`, `DecimalType`, `TimestampType`, `DateType`, `BooleanType`.

## Timestamp Format Requirement

Timestamps **must** use `"YYYY-MM-DD HH:MM:SS"` format for `begin` and `end` parameters:

```python
# Correct — full datetime string
.withColumn("created_at", TimestampType(),
            begin="2020-01-01 00:00:00", end="2024-12-31 23:59:59",
            interval="1 day", random=True)

# Wrong — date-only string may cause issues with TimestampType
.withColumn("created_at", TimestampType(),
            begin="2020-01-01", end="2024-12-31",
            interval="1 day", random=True)
```

For `DateType`, date-only strings (`"2020-01-01"`) work fine.

## Partitions Guidance

Always set `partitions` explicitly. Databricks Connect and serverless don't expose `SparkContext`, so `defaultParallelism` can't be read — dbldatagen falls back to 200 partitions, which is excessive for most demo workloads.

**Rule of thumb:** `partitions = max(4, rows // 100_000)`

| Rows | Partitions |
|------|-----------|
| 1,000 | 4 |
| 100,000 | 4 |
| 1,000,000 | 10 |
| 5,000,000 | 50 |

## `.build()` + `.saveAsTable()` Pattern

Always use `.build()` followed by `.saveAsTable()` for Unity Catalog managed tables:

```python
df = spec.build()
df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("catalog.schema.table")
```

**Do NOT use `.saveAsDataset()`** for UC managed tables — it internally calls `.save(location)` which writes to a file path, not a table name. `.saveAsDataset()` is only appropriate for UC Volume paths (e.g., `/Volumes/catalog/schema/vol/data/`).

## Authentication Options

```python
# Option 1: DEFAULT profile (recommended — auto-discovered from ~/.databrickscfg)
spark = DatabricksSession.builder.serverless().getOrCreate()

# Option 2: Named profile
spark = DatabricksSession.builder.profile("DEFAULT").serverless(True).getOrCreate()

# Option 3: Environment variables (no code changes)
# export DATABRICKS_HOST=https://my-workspace.cloud.databricks.com
# export DATABRICKS_TOKEN=dapi...
spark = DatabricksSession.builder.serverless().getOrCreate()
```

Run `databricks configure` to set up the DEFAULT profile.

## What Doesn't Work Over Connect (UDF-Dependent Features)

These features require Python UDFs to ship to workers, which fails on serverless because dbldatagen/mimesis/numpy aren't installed:

| Feature | Why It Fails | Workaround (Connect) | Full Support |
|---------|-------------|---------------------|-------------|
| `text=mimesisText(...)` | mimesis not on workers | `values=["James","Mary",...], random=True` | Tier 3 notebook |
| `distribution=Gamma/Beta/Normal` | dbldatagen classes can't deserialize on workers | `random=True` or `expr=` math | Tier 3 notebook |
| `.withConstraint()` | Connect Column type mismatch (`pyspark.sql.connect.column.Column` vs `pyspark.sql.column.Column`) | `.build().filter("condition")` | Tier 3 notebook |
| `template=` with UDF patterns | pandas UDFs required | `expr=` with Spark SQL string functions | Tier 3 notebook |

### When to Fall Back

Use **Polars + Mimesis → Connect write** (Tier 2 alternative) when you need:
- Realistic PII (full Mimesis provider: names, emails, addresses, phone numbers)
- Python statistical distributions (`random.gammavariate()`, `random.betavariate()`)

Use **Tier 3 notebooks** when you need:
- >5M rows (better parallelism on dedicated clusters)
- `text=mimesisText(...)` for high-cardinality realistic text
- `distribution=Gamma/Beta/Normal` for statistical distributions
- `.withConstraint()` for row-level validation
- Streaming / CDC patterns with `withStreaming=True`

## Multi-Table Pattern (Connect)

```python
from databricks.connect import DatabricksSession
import dbldatagen as dg
from pyspark.sql.types import StringType, LongType, DecimalType, TimestampType

spark = DatabricksSession.builder.serverless().getOrCreate()

CATALOG = "demo"
SCHEMA = "retail"
N_CUSTOMERS = 100_000
N_TRANSACTIONS = 1_000_000

# --- Customers ---
customers = (
    dg.DataGenerator(sparkSession=spark, name="customers", rows=N_CUSTOMERS, partitions=4)
    .withColumn("customer_id", LongType(), minValue=1_000_000, uniqueValues=N_CUSTOMERS)
    .withColumn("name", StringType(),
                values=["James", "Mary", "Robert", "Patricia", "John"], random=True)
    .withColumn("email", StringType(),
        expr="lower(concat(name, cast(customer_id % 1000 as string), '@example.com'))",
        baseColumns=["name", "customer_id"])
    .build()
)
customers.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{CATALOG}.{SCHEMA}.customers")

# --- Transactions (FK to customers) ---
transactions = (
    dg.DataGenerator(sparkSession=spark, name="transactions", rows=N_TRANSACTIONS, partitions=10)
    .withColumn("txn_id", LongType(), minValue=1, uniqueValues=N_TRANSACTIONS)
    .withColumn("customer_id", LongType(), minValue=1_000_000, maxValue=1_000_000 + N_CUSTOMERS - 1)
    .withColumn("amount", DecimalType(12, 2), minValue=5, maxValue=2000, random=True)
    .withColumn("txn_date", TimestampType(),
                begin="2024-01-01 00:00:00", end="2024-12-31 23:59:59",
                interval="1 hour", random=True)
    .withColumn("payment_method", StringType(),
                values=["Credit Card", "Debit Card", "Cash", "Digital Wallet"],
                weights=[40, 25, 20, 15])
    .build()
)
transactions.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{CATALOG}.{SCHEMA}.transactions")

print(f"Customers: {spark.table(f'{CATALOG}.{SCHEMA}.customers').count():,}")
print(f"Transactions: {spark.table(f'{CATALOG}.{SCHEMA}.transactions').count():,}")
spark.stop()
```

> **FK consistency:** The `customer_id` range in transactions (`minValue=1_000_000, maxValue=1_000_000 + N_CUSTOMERS - 1`) must match the customer table's ID range.

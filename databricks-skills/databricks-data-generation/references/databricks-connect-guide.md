# Databricks Connect Guide

Local development with remote Spark using Databricks Connect and DatabricksSession.

> **Architecture Note:** Databricks Connect serves two roles in Tier 2: (1) as the **compute engine for dbldatagen** — all Catalyst-safe features (`values=`, `weights=`, `minValue`/`maxValue`, `expr=`, `begin`/`end`, `percentNulls=`, `omit=True`) work over Connect + serverless, and (2) as a **transport layer** for writing Polars-generated DataFrames to UC Delta. Connect also handles reading UC tables for validation and schema/catalog provisioning via `spark.sql()`. Only UDF-dependent features (`text=mimesisText()`, `distribution=Gamma/Beta`, `.withConstraint()`, `template=` with UDFs) require Tier 3 notebooks.

## Why Databricks Connect?

The best developer experience combines:
- **Local IDE power** (VSCode, Cursor, PyCharm)
- **Databricks Connect** (run dbldatagen, write to UC, read tables, run DDL)
- **Unity Catalog access** (real schemas for generation)

Databricks Connect lets you run dbldatagen (Catalyst-safe features), write data to Unity Catalog Delta tables, and run catalog operations — all from your local IDE with serverless compute.

## Tier 2 Patterns

### Primary: dbldatagen + Connect + Serverless

dbldatagen generates data using Catalyst-safe features over Connect + serverless. This is the recommended Tier 2 approach for most use cases.

```python
from databricks.connect import DatabricksSession
import dbldatagen as dg
from pyspark.sql.types import StringType, IntegerType, DecimalType, TimestampType

spark = DatabricksSession.builder.serverless().getOrCreate()

FIRST_NAMES = ["James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis"]

customers = (
    dg.DataGenerator(sparkSession=spark, name="customers", rows=1_000_000, partitions=10)
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
    .withColumn("signup_ts", TimestampType(),
                begin="2020-01-01 00:00:00", end="2024-12-31 23:59:59",
                interval="1 day", random=True)
    .build()
)

customers.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("demo.retail.customers")

# --- Validate ---
spark.table("demo.retail.customers").count()
```

See [dbldatagen-connect-patterns.md](dbldatagen-connect-patterns.md) for the full validated pattern reference.

### Alternative: Polars Generate + Connect Write

Use this when you need Mimesis PII (realistic names, emails, addresses) or Python statistical distributions (`gammavariate`, `betavariate`):

```python
import polars as pl
from databricks.connect import DatabricksSession

spark = DatabricksSession.builder.serverless().getOrCreate()

# --- Generate locally with Polars (see polars-generation-guide.md) ---
customers_pl = pl.DataFrame({
    "customer_id": range(1_000_000, 1_100_000),
    "first_name": [...],  # from Mimesis or random.choices()
    "last_name": [...],
    "email": [...],
    "loyalty_tier": random.choices(["Bronze","Silver","Gold","Platinum"], weights=[50,30,15,5], k=100_000),
})

# --- Use Connect as transport to UC ---
spark_df = spark.createDataFrame(customers_pl.to_pandas())
(spark_df.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable("demo.retail.customers"))

# --- Validate ---
spark.table("demo.retail.customers").count()
```

### Schema Provisioning

```python
spark = DatabricksSession.builder.serverless().getOrCreate()

catalog = "demo"
schema = "retail"

# Check if schema exists (safe — avoids PERMISSION_DENIED from CREATE IF NOT EXISTS)
existing = [row.databaseName for row in spark.sql(f"SHOW SCHEMAS IN {catalog}").collect()]
if schema not in existing:
    spark.sql(f"CREATE SCHEMA {catalog}.{schema}")

# Write Polars-generated data
spark_df = spark.createDataFrame(df_polars.to_pandas())
spark_df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{catalog}.{schema}.customers")
```

## Connect + dbldatagen Compatibility

**Environment:** Python 3.12, `databricks-connect>=16.2`

dbldatagen **works over Connect + serverless** for all Catalyst-safe features. Only UDF-dependent features fail because serverless workers don't have dbldatagen/mimesis/numpy installed.

- **Catalyst-safe (works):** `values=`, `weights=`, `minValue`/`maxValue`, `begin`/`end` dates, `expr=`, `percentNulls=`, `omit=True`, `prefix=`/`suffix=`
- **UDF-dependent (fails):** `template=`, `text=mimesisText()`, distributions (`Gamma`, `Beta`, `Normal`, `Exponential`), `.withConstraint()` (isinstance bug with Connect Column type)

**Workaround summary:**
| UDF Feature | Connect Alternative |
|-------------|---------------------|
| `template=r"ddddd"` | `expr="lpad(cast(floor(rand()*100000) as string), 5, '0')"` |
| `text=mimesisText(...)` | `values=["James","Mary",...], random=True` |
| `distribution=Gamma/Beta` | `random=True` or `expr=` math |
| `.withConstraint(...)` | `.build().filter("condition")` |

## Installation

```bash
# Requires Python 3.12 — serverless env v3/v4 use 3.12.3
# IMPORTANT: Versions 17+ and 18+ have serverless validation issues with many workspace types.

# Option 1: Add to project (persistent)
uv add "databricks-connect>=16.4,<17.0"

# Option 2: Run a script with Connect as an ad-hoc dependency
uv run --with "databricks-connect>=16.4,<17.0" my_script.py
```

## Authentication

### Databricks CLI Profile (Recommended)
```bash
# Configure the DEFAULT profile (writes to ~/.databrickscfg)
databricks configure
```

### Environment Variables (Alternative)
```bash
export DATABRICKS_HOST="https://your-workspace.cloud.databricks.com"
export DATABRICKS_TOKEN="dapi..."
```

## DatabricksSession Usage

### Basic Connection (Always Serverless)

```python
from databricks.connect import DatabricksSession

# Always use profile + serverless
spark = DatabricksSession.builder.serverless().getOrCreate()

# Verify connection
spark.sql("SELECT current_user()").show()
```

### With Unity Catalog

```python
from databricks.connect import DatabricksSession

spark = DatabricksSession.builder.serverless().getOrCreate()

# Access Unity Catalog tables
df = spark.table("main.default.customers")

# Query with SQL
result = spark.sql("""
    SELECT * FROM main.sales.transactions
    WHERE date >= '2024-01-01'
    LIMIT 100
""")
```

## Synthetic Data Generation with DatabricksSession

### Generate and Write to Unity Catalog

```python
from databricks.connect import DatabricksSession
import dbldatagen as dg

spark = DatabricksSession.builder.serverless().getOrCreate()

FIRST_NAMES = ["James","Mary","Robert","Patricia","John","Jennifer","Michael","Linda"]
LAST_NAMES = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis"]

# Generate synthetic data (Catalyst-safe — works over Connect)
customers = (
    dg.DataGenerator(spark, rows=100_000, partitions=10)
    .withColumn("customer_id", "long", minValue=1_000_000, uniqueValues=100_000)
    .withColumn("first_name", "string", values=FIRST_NAMES, random=True)
    .withColumn("last_name", "string", values=LAST_NAMES, random=True)
    .withColumn("email", "string",
        expr="lower(concat(first_name, '.', last_name, cast(id % 1000 as string), '@example.com'))",
        baseColumns=["first_name", "last_name"])
    # Notebook-only: replace values= with text=mimesisText(...) for richer PII
    .withColumn("loyalty_tier", "string",
                values=["Bronze", "Silver", "Gold", "Platinum"],
                weights=[50, 30, 15, 5])
    .build()
)

# Write to Unity Catalog
customers.write.format("delta").mode("overwrite").saveAsTable("demo.retail.customers")
```

### Generate from Existing Schema

```python
from databricks.connect import DatabricksSession
import dbldatagen as dg

spark = DatabricksSession.builder.serverless().getOrCreate()

NAMES = ["James","Mary","Robert","Patricia","John","Jennifer","Michael","Linda"]

# Get schema from existing table
source_schema = spark.table("main.production.customers").schema

# Build generator matching schema (Catalyst-safe — works over Connect)
spec = dg.DataGenerator(spark, rows=50_000)

for field in source_schema.fields:
    col_name = field.name
    col_type = str(field.dataType).lower()

    # Infer generation pattern from column name
    if "id" in col_name.lower():
        spec = spec.withColumn(col_name, "long", minValue=1, uniqueValues=50000)
    elif "email" in col_name.lower():
        spec = spec.withColumn(col_name, "string",
            expr="lower(concat(element_at(array('james','mary','robert'), int(rand()*3)+1), cast(id % 1000 as string), '@example.com'))")
    elif "name" in col_name.lower():
        spec = spec.withColumn(col_name, "string", values=NAMES, random=True)
    elif "date" in col_name.lower():
        spec = spec.withColumn(col_name, "date", begin="2020-01-01", end="2024-12-31", random=True)
    # ... add more patterns
    # Notebook-only: replace values= with text=mimesisText(...) for richer PII

synthetic_df = spec.build()
```

### Local Development Workflow

```python
from databricks.connect import DatabricksSession
import dbldatagen as dg

FIRST_NAMES = ["James","Mary","Robert","Patricia","John","Jennifer","Michael","Linda"]
LAST_NAMES = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis"]

def get_session() -> DatabricksSession:
    """Get or create DatabricksSession for local development."""
    return DatabricksSession.builder.serverless().getOrCreate()

def generate_demo_data(
    catalog: str = "demo",
    schema: str = "retail",
    n_customers: int = 100_000,
    n_transactions: int = 1_000_000
):
    """Generate complete retail demo dataset (Catalyst-safe — works over Connect)."""

    spark = get_session()

    # Generate customers (values= for PII, expr= for derived columns)
    customers = (
        dg.DataGenerator(spark, rows=n_customers)
        .withColumn("customer_id", "long", minValue=1_000_000, uniqueValues=n_customers)
        .withColumn("name", "string", values=FIRST_NAMES, random=True)
        .withColumn("email", "string",
            expr="lower(concat(name, cast(id % 1000 as string), '@example.com'))",
            baseColumns=["name"])
        # Notebook-only: replace values= with text=mimesisText(...) for richer PII
        .build()
    )

    customers.write.format("delta").mode("overwrite").saveAsTable(f"{catalog}.{schema}.customers")
    print(f"Written {n_customers:,} customers to {catalog}.{schema}.customers")

    # Generate transactions
    transactions = (
        dg.DataGenerator(spark, rows=n_transactions)
        .withColumn("txn_id", "long", minValue=1, uniqueValues=n_transactions)
        .withColumn("customer_id", "long", minValue=1_000_000, maxValue=1_000_000 + n_customers - 1)
        .withColumn("amount", "decimal(12,2)", minValue=10, maxValue=1000, random=True)
        .withColumn("txn_date", "date", begin="2024-01-01", end="2024-12-31", random=True)
        .build()
    )

    transactions.write.format("delta").mode("overwrite").saveAsTable(f"{catalog}.{schema}.transactions")
    print(f"Written {n_transactions:,} transactions to {catalog}.{schema}.transactions")

# Run from local IDE
if __name__ == "__main__":
    generate_demo_data()
```

## Schema Introspection

### List Available Tables

```python
from databricks.connect import DatabricksSession

spark = DatabricksSession.builder.serverless().getOrCreate()

# List catalogs
spark.sql("SHOW CATALOGS").show()

# List schemas in catalog
spark.sql("SHOW SCHEMAS IN main").show()

# List tables in schema
spark.sql("SHOW TABLES IN main.default").show()
```

### Get Table Schema

```python
# Get schema as StructType
schema = spark.table("main.sales.customers").schema

# Print schema
for field in schema.fields:
    print(f"{field.name}: {field.dataType}")

# Get as DDL string
spark.sql("DESCRIBE main.sales.customers").show(truncate=False)
```

### Generate Schema-Aware Data

```python
NAMES = ["James","Mary","Robert","Patricia","John","Jennifer","Michael","Linda"]

def generate_from_table_schema(
    spark,
    source_table: str,
    target_table: str,
    rows: int = 100_000
):
    """Generate synthetic data matching an existing table's schema (Catalyst-safe)."""

    import dbldatagen as dg

    # Get source schema
    source_df = spark.table(source_table)
    schema = source_df.schema

    # Build generator (uses only Catalyst-safe features — works over Connect)
    spec = dg.DataGenerator(spark, rows=rows)

    for field in schema.fields:
        name = field.name
        dtype = str(field.dataType).lower()

        # Smart defaults based on column name and type
        if name.endswith("_id") and "long" in dtype:
            spec = spec.withColumn(name, "long", minValue=1, uniqueValues=rows)
        elif "email" in name:
            spec = spec.withColumn(name, "string",
                expr="lower(concat(element_at(array('james','mary','robert'), int(rand()*3)+1), cast(id % 1000 as string), '@example.com'))")
        elif "phone" in name:
            spec = spec.withColumn(name, "string",
                expr="concat('(', lpad(cast(floor(rand()*1000) as string),3,'0'), ') ', lpad(cast(floor(rand()*1000) as string),3,'0'), '-', lpad(cast(floor(rand()*10000) as string),4,'0'))")
        elif "name" in name:
            spec = spec.withColumn(name, "string", values=NAMES, random=True)
        elif "date" in name or "timestamp" in dtype:
            spec = spec.withColumn(name, dtype.replace("type()", ""),
                                   begin="2020-01-01", end="2024-12-31", random=True)
        elif "amount" in name or "price" in name or "value" in name:
            spec = spec.withColumn(name, "decimal(12,2)", minValue=0, maxValue=10000, random=True)
        elif "boolean" in dtype:
            spec = spec.withColumn(name, "boolean", expr="rand() < 0.5")
        elif "long" in dtype or "int" in dtype:
            spec = spec.withColumn(name, "long", minValue=1, maxValue=1000000, random=True)
        elif "double" in dtype or "float" in dtype:
            spec = spec.withColumn(name, "double", minValue=0, maxValue=1000, random=True)
        elif "string" in dtype:
            spec = spec.withColumn(name, "string", values=NAMES, random=True)
        else:
            print(f"Warning: Skipping unsupported type {dtype} for {name}")
        # Notebook-only: replace values= with text=mimesisText(...) for richer PII

    # Generate and write
    df = spec.build()
    df.write.format("delta").mode("overwrite").saveAsTable(target_table)

    print(f"Generated {rows:,} rows matching {source_table} schema -> {target_table}")

    return df
```

## Troubleshooting

### Connection Issues

```python
# Test connection
from databricks.connect import DatabricksSession

try:
    spark = DatabricksSession.builder.serverless().getOrCreate()
    spark.sql("SELECT 1").show()
    print("✓ Connection successful")
except Exception as e:
    print(f"✗ Connection failed: {e}")
```

### Common Errors

| Error | Solution |
|-------|----------|
| `DATABRICKS_HOST not set` | Set environment variable or configure DEFAULT profile via `databricks configure` |
| `Serverless mode is not yet supported in this version` | Pin to 16.x: `uv pip install "databricks-connect>=16.0,<17.0"` |
| `Serverless not available` | Ensure workspace has serverless compute enabled |
| `Token expired` | Refresh token via `databricks configure` |
| `template=` / `text=mimesisText()` errors | These UDF-dependent features don't work over Connect — use `values=`, `expr=` instead, or switch to Tier 3 notebook |
| `.withConstraint()` isinstance error | Connect Column type differs from classic — use `.build().filter("condition")` as workaround |
| `distribution=Gamma/Beta` errors | UDF-dependent: numpy not on serverless workers — use `random=True` or `expr=` math over Connect, or use Tier 3 notebook for full distributions |

### Version Check

```python
import databricks.connect
print(f"databricks-connect version: {databricks.connect.__version__}")

# Should be 16.4+ for reliable serverless support (Python 3.12 required)
```

## Constraint Workarounds (Connect)

dbldatagen constraints (`PositiveValues`, `SqlExpr`, etc.) check `isinstance(expr, pyspark.sql.column.Column)` internally, but Databricks Connect returns `pyspark.sql.connect.column.Column` — a different class. This causes constraints to silently fail or error.

**Workaround:** Build first, then filter with SQL:

```python
# Instead of: spec.withConstraint(PositiveValues("amount")).build()
df = spec.build()
df = df.filter("amount > 0")

# Instead of: spec.withConstraint(SqlExpr("discount <= subtotal")).build()
df = spec.build()
df = df.filter("discount <= subtotal")

# Instead of: spec.withConstraint(RangedValues("score", 0, 100)).build()
df = spec.build()
df = df.filter("score >= 0 AND score <= 100")
```

> Note: Post-build filtering may reduce the final row count slightly (rejection sampling). Over-generate by ~5-10% to compensate.

## Best Practices

### 1. Always Use Serverless
```python
# Faster startup, no cluster management — always the right choice
spark = DatabricksSession.builder.serverless().getOrCreate()
```

### 2. Cache Generated Data
```python
# Generate once, cache for iteration
df = spec.build()
df.cache()
df.count()  # Trigger caching

# Now iterate without regenerating
df.groupBy("category").count().show()
```

### 3. Use the DEFAULT Profile
```bash
# Configure once — DatabricksSession auto-discovers the DEFAULT profile
databricks configure
```

### 4. Local Testing First
```python
# Test with small data locally before scaling
if os.getenv("LOCAL_DEV"):
    rows = 1000
else:
    rows = 1_000_000
```

## Writing to UC Volumes

```python
# Create volume if needed
spark.sql("CREATE VOLUME IF NOT EXISTS catalog.schema.raw_data")

# Write generated data to volume
customers_df.write.format("json").mode("overwrite").save(
    "/Volumes/catalog/schema/raw_data/customers"
)

# Write CDC data
cdc_df.write.format("json").mode("append").save(
    "/Volumes/catalog/schema/raw_data/cdc_customers"
)
```

## Writing to Local Parquet (via Polars)

Spark's `df.write.parquet(local_path)` sends the path to the **remote cluster**, which cannot access your local filesystem. Instead, collect to Pandas and write with Polars:

```python
import polars as pl

# Collect from serverless to local, then write parquet
customers_pl = pl.from_pandas(customers_df.toPandas())
customers_pl.write_parquet("output/retail/customers.parquet")

# For larger datasets, limit rows or write multiple tables
for name, df in {"customers": customers_df, "products": products_df}.items():
    pl.from_pandas(df.toPandas()).write_parquet(f"output/retail/{name}.parquet")
```

> **Size guidance**: `.toPandas()` collects all data to the driver. This works well for demo-sized datasets (up to ~1M rows). For larger datasets, write to Unity Catalog tables or Volumes instead.

## Serverless Compute for Spark Declarative Pipelines

```python
# When generating data for Spark Declarative Pipeline testing,
# use serverless compute for fast startup
spark = DatabricksSession.builder.serverless().getOrCreate()

# Generate and write to volumes — pipeline picks up via Auto Loader
```

## Pure PySpark Supplement (No dbldatagen)

For most Connect use cases, **dbldatagen with Catalyst-safe features** (see compatibility section above) is sufficient. Use pure PySpark patterns below only when you need fine-grained control or want zero dependency on dbldatagen.

### When to Use This Pattern

- You want **zero external dependencies** beyond `databricks-connect`
- You need patterns dbldatagen doesn't support (complex conditional logic, deeply nested structs)
- Quick prototypes that don't need dbldatagen's declarative column API

### Random Selection from a List (Replaces `values=`)

```python
from pyspark.sql import functions as F

# Build a Spark array from a Python list, then index with random int
cities = ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix"]
city_arr = F.array(*[F.lit(c) for c in cities])

df = (
    spark.range(1000)
    .withColumn("city", city_arr[F.floor(F.rand() * len(cities)).cast("int")])
)
```

### Weighted Selection (Replaces `weights=`)

Use cumulative `F.when()` chains with a random roll:

```python
# Weighted selection: Credit Card 40%, Debit Card 25%, Cash 15%, Digital Wallet 15%, Gift Card 5%
df = (
    spark.range(1000)
    .withColumn("_r", F.rand() * 100)
    .withColumn("payment_method",
                F.when(F.col("_r") < 40, F.lit("Credit Card"))
                 .when(F.col("_r") < 65, F.lit("Debit Card"))
                 .when(F.col("_r") < 80, F.lit("Cash"))
                 .when(F.col("_r") < 95, F.lit("Digital Wallet"))
                 .otherwise(F.lit("Gift Card")))
    .drop("_r")
)
```

### Realistic PII Without Mimesis

When mimesis isn't available on workers, use array-based name generation:

```python
first_names = ["James", "Mary", "Robert", "Patricia", "John", "Jennifer",
               "Michael", "Linda", "David", "Elizabeth"]
last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia",
              "Miller", "Davis", "Rodriguez", "Martinez"]

first_arr = F.array(*[F.lit(n) for n in first_names])
last_arr = F.array(*[F.lit(n) for n in last_names])

df = (
    spark.range(1000)
    .withColumn("first_name", first_arr[F.floor(F.rand() * len(first_names)).cast("int")])
    .withColumn("last_name", last_arr[F.floor(F.rand() * len(last_names)).cast("int")])
    .withColumn("email",
                F.concat(F.lower(F.col("first_name")), F.lit("."),
                         F.lower(F.col("last_name")),
                         F.floor(F.rand() * 100).cast("string"),
                         F.lit("@example.com")))
)
```

### Random Dates and Timestamps

```python
# Random date in a range (days since epoch offset)
df = (
    spark.range(1000)
    .withColumn("signup_date",
                F.date_add(F.lit("2020-01-01"),
                           F.floor(F.rand() * 1826).cast("int")))  # ~5 years
    .withColumn("txn_timestamp",
                (F.lit("2024-01-01 00:00:00").cast("timestamp").cast("long")
                 + F.floor(F.rand() * 31536000))  # seconds in a year
                .cast("timestamp"))
)
```

### Null Injection

```python
# 2% null rate on email, 1% on phone
df = (
    df
    .withColumn("email", F.when(F.rand() < 0.02, F.lit(None)).otherwise(F.col("email")))
    .withColumn("phone", F.when(F.rand() < 0.01, F.lit(None)).otherwise(F.col("phone")))
)
```

### Derived Columns (Tenure -> Loyalty Tier)

```python
df = (
    df
    .withColumn("tenure_months",
                F.months_between(F.current_date(), F.col("signup_date")).cast("int"))
    .withColumn("loyalty_tier",
                F.when(F.col("tenure_months") > 48, "Platinum")
                 .when(F.col("tenure_months") > 24, "Gold")
                 .when(F.col("tenure_months") > 12, "Silver")
                 .otherwise("Bronze"))
    .drop("tenure_months")
)
```

### Full Example: Retail Dataset (Pure PySpark)

```python
from databricks.connect import DatabricksSession
from pyspark.sql import functions as F

spark = DatabricksSession.builder.serverless().getOrCreate()

first_names = ["James", "Mary", "Robert", "Patricia", "John", "Jennifer",
               "Michael", "Linda", "David", "Elizabeth"]
last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia",
              "Miller", "Davis", "Rodriguez", "Martinez"]

first_arr = F.array(*[F.lit(n) for n in first_names])
last_arr = F.array(*[F.lit(n) for n in last_names])

customers = (
    spark.range(500)
    .withColumn("customer_id", F.col("id") + 1_000_000)
    .withColumn("first_name", first_arr[F.floor(F.rand() * len(first_names)).cast("int")])
    .withColumn("last_name", last_arr[F.floor(F.rand() * len(last_names)).cast("int")])
    .withColumn("email",
                F.concat(F.lower(F.col("first_name")), F.lit("."),
                         F.lower(F.col("last_name")),
                         F.floor(F.rand() * 100).cast("string"),
                         F.lit("@example.com")))
    .withColumn("signup_date",
                F.date_add(F.lit("2020-01-01"), F.floor(F.rand() * 1826).cast("int")))
    # Use a single random value for weighted selection (not independent F.rand() per branch)
    .withColumn("_r", F.rand() * 100)
    .withColumn("loyalty_tier",
                F.when(F.col("_r") < 5, "Platinum")
                 .when(F.col("_r") < 20, "Gold")
                 .when(F.col("_r") < 50, "Silver")
                 .otherwise("Bronze"))
    .withColumn("lifetime_value", F.round(F.rand() * 50000, 2).cast("decimal(12,2)"))
    .withColumn("is_active", F.rand() < 0.85)
    .drop("id", "_r")
)

customers.show(5)
# Write to UC
customers.write.format("delta").mode("overwrite").saveAsTable("demo.retail.customers")

# Or save locally as parquet via Polars (Spark paths go to remote cluster)
import polars as pl
customers_pl = pl.from_pandas(customers.toPandas())
customers_pl.write_parquet("output/retail/customers.parquet")
```

## Resources

- [Databricks Connect Documentation](https://docs.databricks.com/dev-tools/databricks-connect.html)
- [DatabricksSession API](https://docs.databricks.com/dev-tools/databricks-connect/python/index.html)
- [Unity Catalog with Databricks Connect](https://docs.databricks.com/dev-tools/databricks-connect/unity-catalog.html)

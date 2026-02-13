# Polars Generation Guide (Tier 1 Primary, Tier 2 Alternative)

Generate synthetic data locally with **Polars + Mimesis** — zero JVM overhead, no Spark session required. Ideal for quick prototyping, unit tests, and datasets under ~100K rows.

> Polars + Mimesis is the **primary** engine for **Tier 1** (local parquet). For **Tier 2** (UC Delta tables via Connect), dbldatagen + Connect is primary — see [dbldatagen-connect-patterns.md](dbldatagen-connect-patterns.md). Polars is a valid **Tier 2 alternative** when you need Mimesis PII or Python statistical distributions that dbldatagen can't run over Connect.

## When to Use

- User wants **quick local data** without spinning up a Spark session
- Dataset is **<100K rows** (practical single-threaded limit)
- User is **offline** or doesn't have Databricks Connect configured
- User explicitly asks for **Polars**, **local**, or **offline** generation
- User needs data for **Polars-based** downstream analysis

**When NOT to use:** >100K rows — use **dbldatagen + Connect** (primary Tier 2, see [dbldatagen-connect-patterns.md](dbldatagen-connect-patterns.md)) or Polars + Connect as an alternative when Mimesis PII or Python distributions are needed. Need streaming or CDC with Volume landing zones → Tier 3 notebooks.

## Setup

```bash
# Minimal — no Spark, no JVM, no Databricks Connect
uv pip install polars mimesis
```

## Core Patterns

### Seeded Mimesis for PII

```python
import random
from mimesis import Generic
from mimesis.locales import Locale

random.seed(42)
g = Generic(locale=Locale.EN, seed=42)

# Generate per-row PII via list comprehensions
first_names = [g.person.first_name() for _ in range(rows)]
emails = [g.person.email() for _ in range(rows)]
cities = [g.address.city() for _ in range(rows)]
```

The `seed=` parameter on `Generic` ensures reproducible output. Always set both `random.seed()` (for Python stdlib) and `Generic(seed=)` (for Mimesis) at the top of each generator function.

### Weighted Random Choices

Replaces dbldatagen's `values=/weights=`:

```python
import random

# Equivalent to: values=["Bronze","Silver","Gold","Platinum"], weights=[50,30,15,5]
tiers = random.choices(
    ["Bronze", "Silver", "Gold", "Platinum"],
    weights=[50, 30, 15, 5],
    k=rows
)
```

### Statistical Distributions

Replaces dbldatagen's `distribution=Gamma(...)`, `Beta(...)`, etc.:

```python
# Gamma — right-skewed positives (transaction amounts, account balances)
# Equivalent to: distribution=dg.distributions.Gamma(shape=2.0, scale=2.0)
amounts = [round(random.gammavariate(2.0, 2.0) * scale_factor, 2) for _ in range(rows)]

# Beta — bounded 0-1 values (discount rates, quality scores)
# Equivalent to: distribution=dg.distributions.Beta(alpha=2, beta=5)
discount_pcts = [random.betavariate(2, 5) for _ in range(rows)]

# Normal — symmetric data (sensor readings, lifespan estimates)
# Equivalent to: distribution=dg.distributions.Normal(mean, stddev)
values = [random.gauss(mu=15, sigma=5) for _ in range(rows)]

# Exponential — inter-arrival times, counts
# Equivalent to: distribution=dg.distributions.Exponential()
counts = [max(1, int(random.expovariate(0.2))) for _ in range(rows)]
```

### Date and Timestamp Ranges

```python
from datetime import date, datetime, timedelta

start = date(2020, 1, 1)
day_range = (date(2024, 12, 31) - start).days

# Random dates in range
dates = [start + timedelta(days=random.randint(0, day_range)) for _ in range(rows)]

# Random timestamps in range
ts_start = datetime(2024, 1, 1)
ts_seconds = int((datetime(2024, 12, 31, 23, 59, 59) - ts_start).total_seconds())
timestamps = [ts_start + timedelta(seconds=random.randint(0, ts_seconds)) for _ in range(rows)]
```

### Null Injection

Replaces dbldatagen's `percentNulls=`:

```python
# 5% nulls on email column
emails = [None if random.random() < 0.05 else g.person.email() for _ in range(rows)]
```

### Foreign Key Consistency

Replaces dbldatagen's `minValue/maxValue` on FK columns:

```python
# Parent: customer_ids = range(1_000_000, 1_000_000 + n_customers)
# Child: FK references into parent range
customer_fks = [random.randint(1_000_000, 1_000_000 + n_customers - 1) for _ in range(rows)]
```

### Derived Columns via Polars Expressions

Replaces dbldatagen's `expr=` for computed columns:

```python
df = pl.DataFrame({...})

# Computed column from other columns
df = df.with_columns(
    (pl.col("quantity") * pl.col("unit_price")).round(2).alias("line_total")
)

# Conditional/CASE expressions
df = df.with_columns(
    pl.when(pl.col("balance") > 5_000_000).then(pl.lit("Low"))
    .when(pl.col("balance") > 500_000).then(pl.lit("Medium"))
    .otherwise(pl.lit("High"))
    .alias("risk_rating")
)
```

### Unique Sequential IDs

```python
# Equivalent to: minValue=1_000_000, uniqueValues=rows
customer_ids = list(range(1_000_000, 1_000_000 + rows))
```

## Mimesis Provider Quick Reference

The `mimesisText("provider.method")` pattern used with dbldatagen maps directly to `g.provider.method()` calls in standalone Mimesis.

| dbldatagen (Spark) | Polars (standalone Mimesis) | Example Output |
|---|---|---|
| `text=mimesisText("person.first_name")` | `g.person.first_name()` | Jennifer |
| `text=mimesisText("person.last_name")` | `g.person.last_name()` | Williams |
| `text=mimesisText("person.email")` | `g.person.email()` | user@example.com |
| `text=mimesisText("person.telephone")` | `g.person.telephone()` | +1-555-123-4567 |
| `text=mimesisText("address.address")` | `g.address.address()` | 123 Main Street |
| `text=mimesisText("address.city")` | `g.address.city()` | Los Angeles |
| `text=mimesisText("address.state")` | `g.address.state()` | California |
| `text=mimesisText("finance.company")` | `g.finance.company()` | Acme Corp |

## Output Patterns

### Write Parquet

```python
import polars as pl

# Single file
df.write_parquet("output/retail/customers.parquet")

# Using the local_output utility
from utils.local_output import write_local_parquet
path = write_local_parquet(df, "customers", industry="retail")
```

### Write CSV

```python
df.write_csv("output/retail/customers.csv")
```

### Write to Unity Catalog (Connect Bridge)

When the user asks to **save to Unity Catalog** (even for small <100K datasets), use the Connect bridge pattern. The generation code stays the same — only the output sink changes.

```python
from databricks.connect import DatabricksSession

spark = DatabricksSession.builder.serverless().getOrCreate()

CATALOG = "my_catalog"
SCHEMA = "retail"

# Ensure schema exists
existing = [row.databaseName for row in spark.sql(f"SHOW SCHEMAS IN {CATALOG}").collect()]
if SCHEMA not in existing:
    spark.sql(f"CREATE SCHEMA {CATALOG}.{SCHEMA}")

# Bridge: Polars → pandas → Spark DataFrame → UC Delta table
spark_df = spark.createDataFrame(df.to_pandas())
(spark_df.write.format("delta")
 .mode("overwrite")
 .option("overwriteSchema", "true")
 .saveAsTable(f"{CATALOG}.{SCHEMA}.customers"))

# Validate
print(f"Wrote {spark.table(f'{CATALOG}.{SCHEMA}.customers').count():,} rows")
```

Run: `uv run --with polars --with mimesis --with "databricks-connect>=16.4,<17.0" script.py`

### Directory Convention (Local Output)

```
output/
  retail/
    customers.parquet
    products.parquet
    transactions.parquet
  healthcare/
    patients.parquet
    encounters.parquet
```

## Reading Data

```python
import polars as pl

# Single file
customers = pl.read_parquet("output/retail/customers.parquet")

# Multiple files (glob)
all_data = pl.read_parquet("output/retail/*.parquet")

# Quick inspection
print(customers.shape)
print(customers.schema)
customers.head()
customers.describe()
```

## Performance Notes

- List-comprehension generation is **single-threaded** — practical limit ~100K rows per table
- Mimesis `Generic` initialization is fast (~1ms) but each `g.person.email()` call takes ~10us
- For 100K rows: ~1 second for ID/numeric columns, ~3-5 seconds for Mimesis PII columns
- Parquet write is near-instant for datasets under 100K rows
- If you need >100K rows, switch to **Tier 2** (**dbldatagen + Connect** as primary, or Polars + Connect as alternative) or **Tier 3** (dbldatagen in notebooks)

## dbldatagen Equivalence Table

| dbldatagen Feature | Polars + Mimesis Equivalent |
|---|---|
| `values=["A","B"], weights=[70,30]` | `random.choices(["A","B"], weights=[70,30], k=rows)` |
| `minValue=1, maxValue=1000, random=True` | `[random.randint(1, 1000) for _ in range(rows)]` |
| `distribution=Gamma(shape, scale)` | `[random.gammavariate(shape, scale) * factor for ...]` |
| `distribution=Beta(alpha, beta)` | `[random.betavariate(alpha, beta) for ...]` |
| `distribution=Normal(mean, std)` | `[random.gauss(mean, std) for ...]` |
| `distribution=Exponential()` | `[random.expovariate(rate) for ...]` |
| `text=mimesisText("person.first_name")` | `[g.person.first_name() for _ in range(rows)]` |
| `template=r"ddddd"` | `[f"{random.randint(10000,99999)}" for ...]` |
| `begin="2020-01-01", end="2024-12-31"` | `[start + timedelta(days=randint(0, range)) for ...]` |
| `percentNulls=0.05` | `[None if random.random() < 0.05 else val for ...]` |
| `omit=True` | Compute intermediate, don't include in final DataFrame |
| `expr="col_a * col_b"` | `df.with_columns((pl.col("a") * pl.col("b")).alias("c"))` |
| `.withConstraint(PositiveValues("x"))` | `df.filter(pl.col("x") > 0)` |
| `.withConstraint(SqlExpr("a <= b"))` | `df.filter(pl.col("a") <= pl.col("b"))` |
| `uniqueValues=rows` | `list(range(start, start + rows))` |

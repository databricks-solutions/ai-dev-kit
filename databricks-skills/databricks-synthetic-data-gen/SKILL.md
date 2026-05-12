---
name: databricks-synthetic-data-gen
description: "Generate realistic synthetic data using Spark + Faker (strongly recommended). Supports serverless execution, multiple output formats (Parquet/JSON/CSV/Delta), and scales from thousands to millions of rows. For small datasets (<10K rows), can optionally generate locally and upload to volumes. Use when user mentions 'synthetic data', 'test data', 'generate data', 'demo dataset', 'Faker', or 'sample data'."
---

> Catalog and schema are **always user-supplied** — never default to any value. If the user hasn't provided them, ask. For any UC write, **always create the schema if it doesn't exist** before writing data.

# Databricks Synthetic Data Generation

Generate realistic, story-driven synthetic data for Databricks using **Spark + Faker + Pandas UDFs** (strongly recommended).

## Data Must Tell a Business Story

Synthetic data should demonstrate how Databricks helps solve real business problems.

**The pattern:** Something goes wrong → business impact ($) → analyze root cause → identify affected customers → fix and prevent.

**Key principles:**
- **Problem → Impact → Analysis → Solution** — Include an incident, anomaly, or issue that causes measurable business impact. The data lets you find the root cause and act on it.
- **Industry-relevant but simple** — Use domain terms (e.g., "SLA breach", "churn", "stockout") but keep the schema easy to understand. A few tables, clear relationships.
- **Business metrics with $ impact** — Revenue, MRR, cost, conversion rate. Every story needs a dollar sign to show why it matters.
- **Tables explain each other** — Ticket spike? Incident table shows the outage. Revenue drop? Churn table shows who left and why. All data connects.
- **Actionable insights** — Data should answer: What happened? Who's affected? How much did it cost? How do we prevent it?

**Why no flat distributions:** Uniform data has no story — no spikes, no anomalies, no cohort, no 20/80, no skew, nothing to investigate. It can't show Databricks' value for root cause analysis.

## References

| When | Guide |
|------|-------|
| User mentions **ML model training** or complex time patterns | [references/1-data-patterns.md](references/1-data-patterns.md) — ML-ready data, time multipliers, row coherence |
| Errors during generation | [references/2-troubleshooting.md](references/2-troubleshooting.md) — Fixing common issues |

## Critical Rules

1. **Data tells a story** — Something goes wrong, impacts $, can be analyzed and fixed. Show Databricks value.
2. **All data serves the story** — Every table and column must be coherent and usable in dashboards or ML models. No orphan data, no random noise — if it doesn't help explain or plot a futur dashboard or predict, don't generate it.
3. **Industry terms, simple schema** — Use domain-specific vocabulary but keep it easy to understand (few tables, clear relationships)
4. **Never uniform distributions** — Skewed categories, log-normal amounts, 80/20 patterns. Flat = no story = useless
5. **Enough data for trends** — ~100K+ rows for main tables so patterns survive aggregation
6. **Ask for catalog/schema** — Never default, always confirm before generating
7. **Present plan for approval** — Show tables, distributions, assumptions before writing code
8. **Master tables first** — Generate parent tables, write to Delta, then create children with valid FKs
9. **Use Spark + Faker + Pandas UDFs** — Scalable, parallel. Polars only if user explicitly wants local + <30K rows
10. **Use Databricks Connect Serverless by default to generate data** — Update databricks-connect on python 3.12 if required (avoid using execute_code unless instructed to not use Databricks Connect)
11. **No `.cache()` or `.persist()`** — Not supported on serverless. Write to Delta, read back for joins
12. **No Python loops or `.collect()`** — Use Spark parallelism. No driver-side iteration, avoid Pandas↔Spark conversions

## Generation Planning Workflow

**Before generating any code, you MUST present a plan for user approval.**

### ⚠️ MUST DO: Confirm Catalog Before Proceeding

**You MUST explicitly ask the user which catalog to use.** Do not assume or proceed without confirmation.

Example prompt to user:
> "Which Unity Catalog should I use for this data?"

When presenting your plan, always show the selected catalog prominently:
```
📍 Output Location: catalog_name.schema_name
   Volume: /Volumes/catalog_name/schema_name/raw_data/
```

This makes it easy for the user to spot and correct if needed.

### Step 1: Gather Requirements

Ask the user about:
- **Catalog/Schema** — Which catalog to use?
- **Domain** — E-commerce, support tickets, IoT, financial? (Use industry terms)

**If user doesn't specify a story:** Propose one. Don't generate bland data — suggest an incident, anomaly, or trend that shows Databricks value (e.g., "I'll include a system outage that causes ticket spike and churn — this lets you demo root cause analysis").

### Step 2: Present Plan with Story

Show a clear specification with **the business story and your assumptions surfaced**:

```
📍 Output Location: {user_catalog}.support_demo
   Volume: /Volumes/{user_catalog}/support_demo/raw_data/

📖 Story: A payment system outage causes support ticket spike. Resolution times
   degrade, enterprise customers churn, revenue drops $2.3M. With Databricks we
   identify the root cause, affected customers, and prevent future impact.
```

| Table | Description | Rows | Key Assumptions |
|-------|-------------|------|-----------------|
| customers | Customer profiles with tier, MRR | 10,000 | Enterprise 10% but 60% of revenue |
| tickets | Support tickets with priority, resolution_time | 80,000 | Spike during outage, SLA breaches |
| incidents | System events (outages, deployments) | 50 | Payment outage mid-month |
| churn_events | Customer cancellations with reason | 500 | Spike after poor support experience |

**Business metrics:**
- `customers.mrr` — Revenue at risk ($)
- `tickets.resolution_hours` — SLA performance
- `churn_events.lost_mrr` — Churn impact ($)

**The story this data tells:**
- Incident table shows payment outage on March 15
- Tickets spike 5x during outage, resolution time degrades from 4h → 18h
- Enterprise customers with SLA breaches churn 3 weeks later
- Total impact: $2.3M lost MRR, traceable to one incident
- **Databricks value:** Root cause analysis, identify at-risk customers, build alerting

**Ask user**: "Does this story work? Any adjustments?"

### Step 3: Ask About Data Features

- [x] Skew (non-uniform distributions) - **Enabled by default**
- [x] Joins (referential integrity) - **Enabled by default**
- [ ] Bad data injection (for data quality testing)
- [ ] Multi-language text
- [ ] Incremental mode (append instead of overwrite)

### Pre-Generation Checklist

- [ ] **Catalog confirmed** - User explicitly approved which catalog to use
- [ ] Output location shown prominently in plan (easy to spot/change)
- [ ] Table specification shown and approved
- [ ] Assumptions about distributions confirmed
- [ ] User confirmed compute preference (Databricks Connect on serverless recommended)
- [ ] Data features selected

**Do NOT proceed to code generation until user approves the plan, including the catalog.**

### Post-Generation Checklist

After generating data, use `get_volume_folder_details` to validate the output matches requirements:
- Row counts match the plan
- Schema matches expected columns and types
- Data distributions look reasonable (check column stats)

## Use Databricks Connect Spark + Faker Pattern 

```python
from databricks.connect import DatabricksSession, DatabricksEnv
from pyspark.sql import functions as F
from pyspark.sql.types import StringType
import pandas as pd

# Setup serverless with dependencies (MUST list all libs used in UDFs)
env = DatabricksEnv().withDependencies("faker", "holidays")
spark = DatabricksSession.builder.withEnvironment(env).serverless(True).getOrCreate()

# Pandas UDF pattern - import lib INSIDE the function
@F.pandas_udf(StringType())
def fake_name(ids: pd.Series) -> pd.Series:
    from faker import Faker  # Import inside UDF
    fake = Faker()
    return pd.Series([fake.name() for _ in range(len(ids))])

# Generate with spark.range, apply UDFs
customers_df = spark.range(0, 10000, numPartitions=16).select(
    F.concat(F.lit("CUST-"), F.lpad(F.col("id").cast("string"), 5, "0")).alias("customer_id"),
    fake_name(F.col("id")).alias("name"),
)

# Write to Volume as Parquet (default for raw data)
# Path is a folder with table name: /Volumes/catalog/schema/raw_data/customers/
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.raw_data")
customers_df.write.mode("overwrite").parquet(f"/Volumes/{CATALOG}/{SCHEMA}/raw_data/customers")
```

**Partitions by scale:** `spark.range(N, numPartitions=P)`
- <100K rows: 8 partitions
- 100K-500K: 16 partitions
- 500K-1M: 32 partitions
- 1M+: 64+ partitions

**Output formats:**
- **Parquet to Volume** (default): `df.write.parquet("/Volumes/.../raw_data/table")` — raw data for pipelines
- **Delta Table**: `df.write.saveAsTable("catalog.schema.table")` — if user wants queryable tables
- **JSON/CSV**: small dimension tables, replicate legacy systems

## Performance Rules

Generated scripts must be highly performant. **Never** do these:

| Anti-Pattern | Why It's Slow | Do This Instead |
|--------------|---------------|-----------------|
| Python loops on driver | Single-threaded, no parallelism | Use `spark.range()` + Spark operations |
| `.collect()` then iterate | Brings all data to driver memory | Keep data in Spark, use DataFrame ops |
| Pandas → Spark → Pandas | Serialization overhead, defeats distribution | Stay in Spark, use `pandas_udf` only for UDFs |
| Read/write temp files | Unnecessary I/O | Chain DataFrame transformations |
| Scalar UDFs | Row-by-row processing | Use `pandas_udf` for batch processing |

**Good pattern:** `spark.range()` → Spark transforms → `pandas_udf` for Faker → write directly

## Common Patterns

### Weighted Categories (never uniform)
```python
F.when(F.rand() < 0.6, "Free").when(F.rand() < 0.9, "Pro").otherwise("Enterprise")
```

### Log-Normal Amounts (in a pandas UDF)
Use `np.random.lognormal(mean, sigma)` — always positive, long tail:
- Enterprise: `lognormal(7.5, 0.8)` → ~$1800 median
- Pro: `lognormal(5.5, 0.7)` → ~$245 median
- Free: `lognormal(4.0, 0.6)` → ~$55 median

### Date Range (Last 6 Months)
```python
END_DATE = datetime.now()
START_DATE = END_DATE - timedelta(days=180)
```

### Infrastructure (always create in script)
```python
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.raw_data")
```

### Referential Integrity (FK pattern)
Write master table to Delta first, then read back for FK joins (no `.cache()` on serverless):
```python
# 1. Write master table
customers_df.write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.customers")

# 2. Read back for FK lookup
customer_lookup = spark.table(f"{CATALOG}.{SCHEMA}.customers").select("customer_idx", "customer_id")

# 3. Generate child table with valid FKs via join
orders_df = spark.range(N_ORDERS).select(
    (F.abs(F.hash(F.col("id"))) % N_CUSTOMERS).alias("customer_idx")
)
orders_with_fk = orders_df.join(customer_lookup, on="customer_idx")
```

## Setup

Requires Python 3.12 and databricks-connect>=16.4. Use `uv`:

```bash
uv pip install "databricks-connect>=16.4,<17.4" faker numpy pandas holidays
```

## Related Skills

- **databricks-unity-catalog** — Managing catalogs, schemas, and volumes
- **databricks-bundles** — DABs for production deployment

## Common Issues

| Issue | Solution |
|-------|----------|
| `ImportError: cannot import name 'DatabricksEnv'` | Upgrade: `uv pip install "databricks-connect>=16.4"` |
| Python 3.11 instead of 3.12 | Python 3.12 required. Use `uv` to create env with correct version |
| `ModuleNotFoundError: faker` | Add to `withDependencies()`, import inside UDF |
| Faker UDF is slow | Use `pandas_udf` for batch processing |
| Out of memory | Increase `numPartitions` in `spark.range()` |
| Referential integrity errors | Write master table to Delta first, read back for FK joins |
| `PERSIST TABLE is not supported on serverless` | **NEVER use `.cache()` or `.persist()` with serverless** - write to Delta table first, then read back |
| `F.window` vs `Window` confusion | Use `from pyspark.sql.window import Window` for `row_number()`, `rank()`, etc. `F.window` is for streaming only. |
| Broadcast variables not supported | **NEVER use `spark.sparkContext.broadcast()` with serverless** |

See [references/2-troubleshooting.md](references/2-troubleshooting.md) for full troubleshooting guide.

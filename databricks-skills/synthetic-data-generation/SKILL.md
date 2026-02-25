---
name: synthetic-data-generation
description: "Generate realistic synthetic data using Spark + Faker (strongly recommended). Supports serverless execution, multiple output formats (Parquet/JSON/CSV/Delta), and scales from thousands to millions of rows. For small datasets (<10K rows), can optionally generate locally and upload to volumes. Use when user mentions 'synthetic data', 'test data', 'generate data', 'demo dataset', 'Faker', or 'sample data'."
---

# Synthetic Data Generation

Generate realistic, story-driven synthetic data for Databricks using **Spark + Faker + Pandas UDFs** (strongly recommended).

## Quick Reference

| Topic | Guide | When to Use |
|-------|-------|-------------|
| **Setup & Execution** | [references/1-setup-and-execution.md](references/1-setup-and-execution.md) | Setting up environment, choosing compute, installing dependencies |
| **Generation Approaches** | [references/2-generation-approaches.md](references/2-generation-approaches.md) | Choosing Spark UDFs vs Polars local, writing generation code |
| **Data Patterns** | [references/3-data-patterns.md](references/3-data-patterns.md) | Creating realistic distributions, referential integrity, time patterns |
| **Domain Guidance** | [references/4-domain-guidance.md](references/4-domain-guidance.md) | E-commerce, IoT, financial, support/CRM domain patterns |
| **Output Formats** | [references/5-output-formats.md](references/5-output-formats.md) | Choosing output format, saving to volumes/tables |
| **Troubleshooting** | [references/6-troubleshooting.md](references/6-troubleshooting.md) | Fixing errors, debugging issues |
| **Example Script** | [scripts/generate_synthetic_data.py](scripts/generate_synthetic_data.py) | Complete Spark + Pandas UDF example |

## Package Manager

Prefer `uv` for all Python operations. Fall back to `pip` only if `uv` is not available.

```bash
# Preferred
uv pip install "databricks-connect>=16.4,<17.0" faker numpy pandas holidays
uv run python generate_data.py

# Fallback if uv not available
pip install "databricks-connect>=16.4,<17.0" faker numpy pandas holidays
python generate_data.py
```

## Critical Rules

1. **Always use Spark + Faker + Pandas UDFs** for data generation (scalable, parallel)
2. **Present a plan for user approval** before generating any code
3. **Ask for catalog/schema** - default to `ai_dev_kit.<user_schema>`
4. **Use serverless compute** unless user explicitly requests classic cluster
5. **Generate raw data only** - no pre-aggregated fields (unless user requests)
6. **Create master tables first** - then generate related tables with valid FKs
7. **NEVER use `.cache()` or `.persist()` with serverless compute** - these operations are NOT supported and will fail with `AnalysisException: PERSIST TABLE is not supported on serverless compute`. Instead, write master tables to Delta first, then read them back for FK joins.

## Generation Planning Workflow

**Before generating any code, you MUST present a plan for user approval.**

### ⚠️ MUST DO: Confirm Catalog Before Proceeding

**You MUST explicitly ask the user which catalog to use.** Do not assume or proceed without confirmation.

Example prompt to user:
> "Which Unity Catalog should I use for this data? Default is `ai_dev_kit` but you can specify any catalog you have access to."

When presenting your plan, always show the selected catalog prominently:
```
📍 Output Location: catalog_name.schema_name
   Volume: /Volumes/catalog_name/schema_name/raw_data/
```

This makes it easy for the user to spot and correct if needed.

### Step 1: Gather Requirements

Ask the user about:
- **Catalog/Schema** - Which catalog to use? (default: `ai_dev_kit.<user_schema>`)
- What domain/scenario? (e-commerce, support tickets, IoT sensors, etc.)
- How many tables? What relationships between them?
- Approximate row counts per table?
- Output format preference? (Parquet to Volume is default)

### Step 2: Present Table Specification

Show a clear specification with **YOUR ASSUMPTIONS surfaced**. Always start with the output location:

```
📍 Output Location: ai_dev_kit.ecommerce_demo
   Volume: /Volumes/ai_dev_kit/ecommerce_demo/raw_data/

   ⬆️ Change this? Just let me know which catalog.schema to use instead.
```

| Table | Columns | Rows | Key Assumptions |
|-------|---------|------|-----------------|
| customers | customer_id, name, email, tier, region | 5,000 | Tier: Free 60%, Pro 30%, Enterprise 10% |
| orders | order_id, customer_id (FK), amount, status | 15,000 | Enterprise customers generate 5x more orders |

**Assumptions I'm making:**
- Amount distribution: log-normal by tier (Enterprise ~$1800, Pro ~$245, Free ~$55)
- Status: 65% delivered, 15% shipped, 10% processing, 5% pending, 5% cancelled

**Ask user**: "Does this look correct? Any adjustments to the catalog, tables, or distributions?"

### Step 3: Ask About Data Features

- [x] Skew (non-uniform distributions) - **Enabled by default**
- [x] Joins (referential integrity) - **Enabled by default**
- [ ] Bad data injection (for data quality testing)
- [ ] Multi-language text
- [ ] Incremental mode (append vs overwrite)

### Pre-Generation Checklist

- [ ] **Catalog confirmed** - User explicitly approved which catalog to use
- [ ] Output location shown prominently in plan (easy to spot/change)
- [ ] Table specification shown and approved
- [ ] Assumptions about distributions confirmed
- [ ] User confirmed compute preference (serverless recommended)
- [ ] Data features selected

**Do NOT proceed to code generation until user approves the plan, including the catalog.**

## Quick Start: Spark + Faker + Pandas UDFs

```python
from databricks.connect import DatabricksSession, DatabricksEnv
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, DoubleType
import pandas as pd
import numpy as np

# Setup with managed dependencies (databricks-connect 16.4+)
env = DatabricksEnv().withDependencies("faker", "pandas", "numpy")
spark = DatabricksSession.builder.withEnvironment(env).serverless(True).getOrCreate()

# Define Pandas UDFs
@F.pandas_udf(StringType())
def fake_name(ids: pd.Series) -> pd.Series:
    from faker import Faker
    fake = Faker()
    return pd.Series([fake.name() for _ in range(len(ids))])

@F.pandas_udf(DoubleType())
def generate_amount(tiers: pd.Series) -> pd.Series:
    amounts = []
    for tier in tiers:
        if tier == "Enterprise":
            amounts.append(float(np.random.lognormal(7.5, 0.8)))
        elif tier == "Pro":
            amounts.append(float(np.random.lognormal(5.5, 0.7)))
        else:
            amounts.append(float(np.random.lognormal(4.0, 0.6)))
    return pd.Series(amounts)

# Generate customers
customers_df = (
    spark.range(0, 10000, numPartitions=16)
    .select(
        F.concat(F.lit("CUST-"), F.lpad(F.col("id").cast("string"), 5, "0")).alias("customer_id"),
        fake_name(F.col("id")).alias("name"),
        F.when(F.rand() < 0.6, "Free")
         .when(F.rand() < 0.9, "Pro")
         .otherwise("Enterprise").alias("tier"),
    )
    .withColumn("arr", generate_amount(F.col("tier")))
)

# Save to Unity Catalog
spark.sql("CREATE SCHEMA IF NOT EXISTS ai_dev_kit.my_schema")
spark.sql("CREATE VOLUME IF NOT EXISTS ai_dev_kit.my_schema.raw_data")
customers_df.write.mode("overwrite").parquet("/Volumes/ai_dev_kit/my_schema/raw_data/customers")
```

## Common Patterns

### Weighted Tier Distribution
```python
F.when(F.rand() < 0.6, "Free")
 .when(F.rand() < 0.9, "Pro")
 .otherwise("Enterprise").alias("tier")
```

### Log-Normal Amounts (Realistic Pricing)
```python
@F.pandas_udf(DoubleType())
def generate_amount(tiers: pd.Series) -> pd.Series:
    return pd.Series([
        float(np.random.lognormal({"Enterprise": 7.5, "Pro": 5.5, "Free": 4.0}[t], 0.7))
        for t in tiers
    ])
```

### Date Range (Last 6 Months)
```python
from datetime import datetime, timedelta
END_DATE = datetime.now()
START_DATE = END_DATE - timedelta(days=180)

F.date_add(F.lit(START_DATE.date()), (F.rand() * 180).cast("int")).alias("order_date")
```

### Infrastructure Creation
```python
# Always in script - assume catalog exists
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.raw_data")
```

## Execution Modes

| Mode | Best For | Setup |
|------|----------|-------|
| **DB Connect 16.4+ Serverless** | Local dev, Python 3.12+ | `DatabricksEnv().withDependencies(...)` |
| **Serverless Job** | Production, scheduled | Job with `environments` parameter |
| **Classic Cluster** | Fallback only | Use Databricks CLI to install libraries. `databricks libraries install --json '{"cluster_id": "<cluster_id>", "libraries": [{"pypi": {"package": "faker"}}, {"pypi": {"package": "holidays"}}]}'` |

See [references/1-setup-and-execution.md](references/1-setup-and-execution.md) for detailed setup instructions.

## Output Formats

| Format | Use Case | Code |
|--------|----------|------|
| **Parquet** (default) | SDP pipeline input | `df.write.parquet(path)` |
| **JSON** | Log-style ingestion | `df.write.json(path)` |
| **CSV** | Legacy systems | `df.write.option("header", "true").csv(path)` |
| **Delta Table** | Direct analytics | `df.write.saveAsTable("catalog.schema.table")` |

See [references/5-output-formats.md](references/5-output-formats.md) for detailed options.

## Best Practices Summary

### Execution
- Use serverless (instant start, no cluster wait)
- Ask for catalog/schema (default `ai_dev_kit`)
- Present plan before generating

### Data Generation
- **Spark + Faker + Pandas UDFs** for all cases
- Master tables first, then related tables with valid FKs
- Non-linear distributions (log-normal, Pareto, exponential)
- Time patterns (weekday/weekend, holidays, seasonality)
- Row coherence (correlated attributes)

### Output
- Create infrastructure in script (`CREATE SCHEMA/VOLUME IF NOT EXISTS`)
- Do NOT create catalogs - assume they exist
- Parquet to volumes as default

## Related Skills

- **databricks-unity-catalog** - Managing catalogs, schemas, and volumes
- **databricks-asset-bundles** - DABs for production deployment

## Common Issues

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: faker` | See [references/1-setup-and-execution.md](references/1-setup-and-execution.md) |
| Faker UDF is slow | Use `pandas_udf` for batch processing |
| Out of memory | Increase `numPartitions` in `spark.range()` |
| Referential integrity errors | Write master table to Delta first, read back for FK joins |
| `PERSIST TABLE is not supported on serverless` | **NEVER use `.cache()` or `.persist()` with serverless** - write to Delta table first, then read back |

See [references/6-troubleshooting.md](references/6-troubleshooting.md) for full troubleshooting guide.

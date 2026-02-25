# Data Generation Approaches

Choose your approach based on scale and requirements. **Spark + Faker + Pandas UDFs is strongly preferred** for all cases.

## Decision Table

| Scenario | Recommended Approach |
|----------|---------------------|
| **Default - any data generation** | **Spark + Faker + Pandas UDFs** |
| Large datasets (100K+ rows) | **Spark + Faker + Pandas UDFs** |
| Medium datasets (10K-100K rows) | **Spark + Faker + Pandas UDFs** |
| Small datasets (<10K rows) | **Spark + Faker + Pandas UDFs** (or Polars if user prefers local) |

**Rule:** Always use Spark + Faker + Pandas UDFs unless user explicitly requests local generation for <10K rows.

---

## Approach 1: Spark + Faker + Pandas UDFs (Strongly Preferred)

**Best for:** All dataset sizes, direct write to Unity Catalog

**Why this approach:**
- Scales from thousands to millions of rows
- Parallel execution via Spark
- Direct integration with Unity Catalog
- No intermediate files or uploads needed
- Works with serverless and classic compute

### Basic Pattern

```python
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, DoubleType
from faker import Faker
import pandas as pd
import numpy as np

# Define Pandas UDFs for Faker data (batch processing for parallelism)
@F.pandas_udf(StringType())
def fake_name(ids: pd.Series) -> pd.Series:
    fake = Faker()
    return pd.Series([fake.name() for _ in range(len(ids))])

@F.pandas_udf(StringType())
def fake_company(ids: pd.Series) -> pd.Series:
    fake = Faker()
    return pd.Series([fake.company() for _ in range(len(ids))])

@F.pandas_udf(StringType())
def fake_email(ids: pd.Series) -> pd.Series:
    fake = Faker()
    return pd.Series([fake.email() for _ in range(len(ids))])

@F.pandas_udf(DoubleType())
def generate_lognormal_amount(tiers: pd.Series) -> pd.Series:
    """Generate amount based on tier using log-normal distribution."""
    amounts = []
    for tier in tiers:
        if tier == "Enterprise":
            amounts.append(float(np.random.lognormal(mean=7.5, sigma=0.8)))
        elif tier == "Pro":
            amounts.append(float(np.random.lognormal(mean=5.5, sigma=0.7)))
        else:
            amounts.append(float(np.random.lognormal(mean=4.0, sigma=0.6)))
    return pd.Series(amounts)
```

### Generate Data with Spark + Pandas UDFs

```python
# Configuration
N_CUSTOMERS = 100_000
PARTITIONS = 16  # Adjust based on data size: 8 for <100K, 32 for 1M+
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw_data"

# Generate customers with Spark + Pandas UDFs
customers_df = (
    spark.range(0, N_CUSTOMERS, numPartitions=PARTITIONS)
    .select(
        F.concat(F.lit("CUST-"), F.lpad(F.col("id").cast("string"), 5, "0")).alias("customer_id"),
        fake_name(F.col("id")).alias("name"),
        fake_company(F.col("id")).alias("company"),
        fake_email(F.col("id")).alias("email"),
        F.when(F.rand() < 0.6, "Free")
         .when(F.rand() < 0.9, "Pro")
         .otherwise("Enterprise").alias("tier"),
        F.when(F.rand() < 0.4, "North")
         .when(F.rand() < 0.65, "South")
         .when(F.rand() < 0.85, "East")
         .otherwise("West").alias("region"),
    )
)

# Add tier-based amount
customers_df = customers_df.withColumn("arr", generate_lognormal_amount(F.col("tier")))

# Write directly to Unity Catalog volume
customers_df.write.mode("overwrite").parquet(f"{VOLUME_PATH}/customers")
```

### Partitioning Strategy

| Data Size | Recommended Partitions |
|-----------|----------------------|
| < 100K rows | 8 partitions |
| 100K - 500K rows | 16 partitions |
| 500K - 1M rows | 32 partitions |
| 1M+ rows | 64+ partitions |

---

## Approach 2: Polars + Local Generation + Upload (Secondary Option)

**Use only when:** Dataset <10K rows AND user explicitly prefers local generation

**Why this approach exists:**
- No Spark overhead for tiny datasets
- Quick prototyping in local environment
- When Databricks Connect not available

**Limitations:**
- Doesn't scale past ~100K rows
- Requires manual upload step
- No direct Unity Catalog integration

### Install Local Dependencies

```bash
# Preferred: use uv for fast, reliable installs
uv pip install polars faker numpy

# Alternative if uv not available
pip install polars faker numpy
```

### Generate Locally with Polars

```python
import polars as pl
from faker import Faker
import numpy as np

fake = Faker()
N_CUSTOMERS = 5000

# Generate with Polars
customers = pl.DataFrame({
    "customer_id": [f"CUST-{i:05d}" for i in range(N_CUSTOMERS)],
    "name": [fake.name() for _ in range(N_CUSTOMERS)],
    "email": [fake.email() for _ in range(N_CUSTOMERS)],
    "tier": np.random.choice(["Free", "Pro", "Enterprise"], N_CUSTOMERS, p=[0.6, 0.3, 0.1]).tolist(),
    "region": np.random.choice(["North", "South", "East", "West"], N_CUSTOMERS, p=[0.4, 0.25, 0.2, 0.15]).tolist(),
})

# Save locally
customers.write_parquet("./output/customers.parquet")
```

### Upload to Databricks Volume

After generating data locally, upload to a Databricks volume:

```bash
# Create directory in volume if needed
databricks fs mkdirs dbfs:/Volumes/<catalog>/<schema>/<volume>/source_data/

# Upload local data to volume
databricks fs cp -r ./output/customers.parquet dbfs:/Volumes/<catalog>/<schema>/<volume>/source_data/
databricks fs cp -r ./output/orders.parquet dbfs:/Volumes/<catalog>/<schema>/<volume>/source_data/
```

### When to Actually Use Polars

Only recommend Polars when ALL conditions are met:
1. Dataset is < 10K rows
2. User explicitly requests local generation
3. Quick prototyping without Databricks connection

Otherwise, **always use Spark + Faker + Pandas UDFs**.

---

## Storage Destinations

### Ask for Catalog and Schema

By default, use the `ai_dev_kit` catalog. Ask the user which schema to use:

> "I'll save the data to `ai_dev_kit.<schema>`. What schema name would you like to use? (You can also specify a different catalog if needed.)"

### Create Infrastructure in Script

Always create the schema and volume **inside the Python script** using `spark.sql()`:

```python
CATALOG = "ai_dev_kit"
SCHEMA = "synthetic_data"
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw_data"

# Note: Assume catalog exists - do NOT create it
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.raw_data")
```

**Important:** Do NOT create catalogs - assume they already exist. Only create schema and volume.

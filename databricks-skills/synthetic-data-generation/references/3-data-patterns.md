# Data Patterns Guide

Creating realistic, coherent synthetic data with Spark + Pandas UDFs.

## 5 Key Principles

1. **Use Spark + Faker + Pandas UDFs** for all generation
2. **Referential Integrity** - master tables first, weighted sampling
3. **Non-Linear Distributions** - log-normal, Pareto, exponential
4. **Time-Based Patterns** - weekday/weekend, holidays, seasonality
5. **Row Coherence** - correlated attributes within each row

---

## Principle 1: Use Spark + Faker + Pandas UDFs

Generate data with Spark + Faker for all use cases. Pandas UDFs provide efficient, distributed Faker calls that scale seamlessly from thousands to millions of rows.

### Define Pandas UDFs

```python
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, DoubleType
from faker import Faker
import pandas as pd
import numpy as np

@F.pandas_udf(StringType())
def fake_company(ids: pd.Series) -> pd.Series:
    fake = Faker()
    return pd.Series([fake.company() for _ in range(len(ids))])

@F.pandas_udf(StringType())
def fake_address(ids: pd.Series) -> pd.Series:
    fake = Faker()
    return pd.Series([fake.address().replace('\n', ', ') for _ in range(len(ids))])

@F.pandas_udf(DoubleType())
def generate_lognormal_amount(tiers: pd.Series) -> pd.Series:
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

### Generate with Spark

```python
# Adjust numPartitions based on scale: 8 for <100K, 32 for 1M+
customers_df = (
    spark.range(0, N_CUSTOMERS, numPartitions=16)
    .select(
        F.concat(F.lit("CUST-"), F.lpad(F.col("id").cast("string"), 5, "0")).alias("customer_id"),
        fake_company(F.col("id")).alias("name"),
        F.when(F.rand() < 0.6, "Free")
         .when(F.rand() < 0.9, "Pro")
         .otherwise("Enterprise").alias("tier"),
    )
)
customers_df.write.mode("overwrite").parquet(f"{VOLUME_PATH}/customers")
```

---

## Principle 2: Referential Integrity

Generate master tables first, then iterate on them to create related tables with matching IDs.

### Pattern: Weighted Sampling by Tier

```python
from pyspark.sql.window import Window

# 1. Generate and cache customers (master table)
customers_df = (
    spark.range(0, N_CUSTOMERS, numPartitions=PARTITIONS)
    .select(
        F.concat(F.lit("CUST-"), F.lpad(F.col("id").cast("string"), 5, "0")).alias("customer_id"),
        F.when(F.rand(SEED) < 0.6, "Free")
         .when(F.rand(SEED) < 0.9, "Pro")
         .otherwise("Enterprise").alias("tier"),
    )
)
customer_lookup = customers_df.select("customer_id", "tier").cache()

# 2. Generate orders with valid foreign keys
orders_df = spark.range(0, N_ORDERS, numPartitions=PARTITIONS)

# Map order to customer using hash-based distribution
orders_df = orders_df.select(
    F.concat(F.lit("ORD-"), F.lpad(F.col("id").cast("string"), 6, "0")).alias("order_id"),
    (F.abs(F.hash(F.col("id"), F.lit(SEED))) % N_CUSTOMERS).alias("customer_idx"),
)

# Add customer_idx to lookup for join
customer_lookup_with_idx = customer_lookup.withColumn(
    "customer_idx",
    (F.row_number().over(Window.orderBy(F.monotonically_increasing_id())) - 1).cast("int")
)

# Join to get valid foreign keys
orders_with_fk = orders_df.join(customer_lookup_with_idx, on="customer_idx", how="left")

customer_lookup.unpersist()
```

### Anti-Pattern: Random FK Generation

```python
# BAD - May generate non-existent customer IDs
orders_df = spark.range(0, N_ORDERS).select(
    F.concat(F.lit("CUST-"), (F.rand() * 99999).cast("int")).alias("customer_id")  # WRONG!
)
```

---

## Principle 3: Non-Linear Distributions

**Never use uniform distributions** - real data is rarely uniform.

### Distribution Types

| Distribution | Use Case | Example |
|--------------|----------|---------|
| **Log-normal** | Prices, salaries, order amounts | `np.random.lognormal(mean=4.5, sigma=0.8)` |
| **Pareto/Power law** | Popularity, wealth, page views | `(np.random.pareto(a=2.5) + 1) * 10` |
| **Exponential** | Time between events, resolution time | `np.random.exponential(scale=24)` |
| **Weighted categorical** | Status, region, tier | `np.random.choice(vals, p=[0.4, 0.3, 0.2, 0.1])` |

### Pandas UDF for Log-Normal Amounts

```python
@F.pandas_udf(DoubleType())
def generate_lognormal_amount(tiers: pd.Series) -> pd.Series:
    """Generate amount based on tier using log-normal distribution."""
    amounts = []
    for tier in tiers:
        if tier == "Enterprise":
            amounts.append(float(np.random.lognormal(mean=7.5, sigma=0.8)))  # ~$1800 avg
        elif tier == "Pro":
            amounts.append(float(np.random.lognormal(mean=5.5, sigma=0.7)))  # ~$245 avg
        else:
            amounts.append(float(np.random.lognormal(mean=4.0, sigma=0.6)))  # ~$55 avg
    return pd.Series(amounts)
```

### Anti-Pattern: Uniform Distribution

```python
# BAD - Uniform (unrealistic)
prices = np.random.uniform(10, 1000, size=N_ORDERS)

# GOOD - Log-normal (realistic for prices)
prices = np.random.lognormal(mean=4.5, sigma=0.8, size=N_ORDERS)
```

---

## Principle 4: Time-Based Patterns

Add weekday/weekend effects, holidays, seasonality, and event spikes.

### Holiday and Weekday Multipliers

```python
import holidays
from datetime import datetime, timedelta

# Load holiday calendar
US_HOLIDAYS = holidays.US(years=[START_DATE.year, END_DATE.year])

def get_daily_multiplier(date):
    """Calculate volume multiplier for a given date."""
    multiplier = 1.0

    # Weekend drop
    if date.weekday() >= 5:
        multiplier *= 0.6

    # Holiday drop (even lower than weekends)
    if date in US_HOLIDAYS:
        multiplier *= 0.3

    # Q4 seasonality (higher in Oct-Dec)
    multiplier *= 1 + 0.15 * (date.month - 6) / 6

    # Incident spike (if applicable)
    if INCIDENT_START <= date <= INCIDENT_END:
        multiplier *= 3.0

    # Random noise
    multiplier *= np.random.normal(1, 0.1)

    return max(0.1, multiplier)
```

### Date Range: Last 6 Months

Always generate data for the last ~6 months ending at the current date:

```python
from datetime import datetime, timedelta

END_DATE = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
START_DATE = END_DATE - timedelta(days=180)
```

---

## Principle 5: Row Coherence

Attributes within a row should correlate logically.

### Coherent Ticket Generation

```python
@F.pandas_udf("struct<priority:string,resolution_hours:double,csat_score:int>")
def generate_coherent_ticket(tiers: pd.Series) -> pd.DataFrame:
    """Generate coherent ticket where attributes correlate."""
    results = []
    for tier in tiers:
        # Priority correlates with tier
        if tier == 'Enterprise':
            priority = np.random.choice(['Critical', 'High', 'Medium'], p=[0.3, 0.5, 0.2])
        else:
            priority = np.random.choice(['Critical', 'High', 'Medium', 'Low'], p=[0.05, 0.2, 0.45, 0.3])

        # Resolution time correlates with priority
        resolution_scale = {'Critical': 4, 'High': 12, 'Medium': 36, 'Low': 72}
        resolution_hours = np.random.exponential(scale=resolution_scale[priority])

        # CSAT correlates with resolution time
        if resolution_hours < 4:
            csat = np.random.choice([4, 5], p=[0.3, 0.7])
        elif resolution_hours < 24:
            csat = np.random.choice([3, 4, 5], p=[0.2, 0.5, 0.3])
        else:
            csat = np.random.choice([1, 2, 3, 4], p=[0.1, 0.3, 0.4, 0.2])

        results.append({
            "priority": priority,
            "resolution_hours": round(resolution_hours, 1),
            "csat_score": int(csat),
        })

    return pd.DataFrame(results)
```

### Correlation Examples

| Attribute A | Attribute B | Correlation |
|------------|-------------|-------------|
| Customer tier | Order amount | Enterprise = higher amounts |
| Ticket priority | Resolution time | Critical = faster resolution |
| Resolution time | CSAT score | Faster = higher satisfaction |
| Region | Product preference | Regional variations |
| Time of day | Transaction type | Business hours = B2B |

---

## Data Volume for Aggregation

Generate enough data so patterns remain visible after downstream aggregation:

| Grain | Minimum Records | Rationale |
|-------|-----------------|-----------|
| Daily time series | 50-100/day | See trends after weekly rollup |
| Per category | 500+ per category | Statistical significance |
| Per customer | 5-20 events/customer | Customer-level analysis |
| Total rows | 10K-50K minimum | Patterns survive GROUP BY |

```python
# Example: 8000 tickets over 180 days = ~44/day average
# After weekly aggregation: ~310 records per week
N_TICKETS = 8000
N_CUSTOMERS = 2500  # Each has ~3 tickets on average
N_ORDERS = 25000    # ~10 orders per customer average
```

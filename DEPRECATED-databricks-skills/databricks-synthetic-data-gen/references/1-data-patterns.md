# Data Patterns Guide

Creating realistic synthetic data that tells a story.

> **Note:** This guide provides principles and simplified examples. Actual implementations should be more sophisticated — use domain-specific distributions, realistic business rules, and correlations that reflect the user's actual use case. Ask clarifying questions to understand the business context before generating.

## Core Principles

### 1. Data Must Be Interesting

Synthetic data should reveal patterns humans can see in dashboards and ML models can learn from:

- **Visible trends** — Revenue growth, seasonal spikes, degradation over time
- **Actionable segments** — Clear differences between customer tiers, regions, product categories
- **Anomalies to detect** — Fraud patterns, equipment failures, churn signals
- **Correlations to discover** — Higher tier = more spend, faster resolution = better CSAT

**Anti-pattern:** Uniform random data with no story — useless for demos and ML.

### 2. Non-Uniform Distributions

Real data is never uniformly distributed. Use appropriate distributions:

| Distribution | When to Use | Examples |
|--------------|-------------|----------|
| **Log-normal** | Monetary values, sizes | Order amounts, salaries, file sizes |
| **Pareto (80/20)** | Popularity, wealth | 20% of customers = 80% of revenue |
| **Exponential** | Time between events | Support resolution time, session duration |
| **Weighted categorical** | Skewed categories | Status (70% complete, 5% failed), tiers |

```python
# Log-normal for amounts (long tail, always positive)
amount = np.random.lognormal(mean=5.5, sigma=0.8)  # ~$245 median

# Pareto for power-law (few large, many small)
value = (np.random.pareto(a=1.5) + 1) * base_value

# Exponential for time-to-event
hours = np.random.exponential(scale=24)  # avg 24h, skewed right
```

### 3. Row Coherence

Attributes within a row must make business sense together. Generate correlated attributes in a single UDF for example:

| If This... | Then This... |
|------------|--------------|
| Enterprise tier | Higher order amounts, more activity, priority support |
| Critical priority | Faster resolution, more interactions |
| Older equipment | Higher failure rate, more anomalies |
| Large transaction + unusual hour | Higher fraud probability |
| Fast resolution | Higher CSAT score |

```python
@F.pandas_udf("struct<priority:string,resolution_hours:double,csat:int>")
def generate_coherent_ticket(tiers: pd.Series) -> pd.DataFrame:
    """All attributes correlate logically within each row."""
    results = []
    for tier in tiers:
        # Priority depends on tier
        priority = "Critical" if tier == "Enterprise" and random() < 0.3 else "Medium"
        # Resolution depends on priority
        resolution = np.random.exponential(4 if priority == "Critical" else 36)
        # CSAT depends on resolution
        csat = 5 if resolution < 4 else (3 if resolution < 24 else 2)
        results.append({"priority": priority, "resolution_hours": resolution, "csat": csat})
    return pd.DataFrame(results)
```

### 4. The 80/20 Rule

Apply power-law distributions where appropriate:

- **20% of customers** generate 80% of orders/revenue
- **20% of products** account for 80% of sales
- **20% of support agents** handle 80% of tickets

Implementation: Use weighted sampling when assigning FKs, not uniform random.

### 5. Time-Based Patterns

Most data has temporal patterns:

- **Weekday vs weekend** — B2B drops on weekends, B2C peaks
- **Business hours** — Support tickets cluster 9am-5pm
- **Seasonality** — Q4 retail spike, summer travel peak
- **Trends** — Growth over time, degradation curves

```python
def get_volume_multiplier(date):
    multiplier = 1.0
    if date.weekday() >= 5: multiplier *= 0.6  # Weekend drop
    if date.month in [11, 12]: multiplier *= 1.5  # Holiday spike
    return multiplier
```

### 6. ML-Ready Data

If data will train ML models, ensure:

- **Signal exists** — The patterns you want the model to learn are present
- **Noise is realistic** — Not too clean (overfitting) or too noisy (unlearnable)
- **Class balance** — Fraud at 0.1-1%, not 50/50 (unrealistic)
- **Temporal validity** — Train/test split respects time (no future leakage)

## Referential Integrity

Generate master tables first, write to Delta, then join for FKs:

```python
# 1. Generate and write master table
customers_df.write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.customers")

# 2. Read back for FK joins (NOT cache - unsupported on serverless)
customer_lookup = spark.table(f"{CATALOG}.{SCHEMA}.customers")

# 3. Generate child table with valid FKs via join
orders_df = spark.range(N_ORDERS).select(
    (F.abs(F.hash(F.col("id"))) % N_CUSTOMERS).alias("customer_idx")
)
orders_with_fk = orders_df.join(customer_lookup, on="customer_idx")
```

## Data Volume

Generate enough rows so patterns survive aggregation:

| Analysis Type | Minimum Rows | Rationale |
|---------------|--------------|-----------|
| Daily dashboard | 50-100/day | Trends visible after weekly rollup |
| Category comparison | 500+ per category | Statistical significance |
| ML training | 10K-100K+ | Enough signal for model learning |
| Customer-level | 5-20 events/customer | Individual patterns visible |

**Rule of thumb:** If you'll GROUP BY a column, ensure each group has 100+ rows.

---

## Remember

These are guiding principles, not templates. Real implementations should:
- Reflect the user's specific business domain and terminology
- Use realistic parameter values (research typical ranges for the industry)
- Include edge cases relevant to the use case (returns, cancellations, failures)
- Have more complex correlations than shown in examples above
- **Never use flat/uniform distributions** — categories, tiers, regions, statuses should always be skewed (e.g., 60/30/10 not 33/33/33)

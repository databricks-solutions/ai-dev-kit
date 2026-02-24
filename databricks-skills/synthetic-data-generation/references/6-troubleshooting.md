# Troubleshooting Guide

Common issues and solutions for synthetic data generation.

## Environment Issues

### ModuleNotFoundError: faker (or other library)

**Problem:** Dependencies not available in execution environment.

**Solutions by execution mode:**

| Mode | Solution |
|------|----------|
| **DB Connect 16.4+** | Use `DatabricksEnv().withDependencies("faker", "pandas", ...)` |
| **Older DB Connect** | Create job with `environments` parameter |
| **Databricks Runtime** | Run `%pip install faker numpy pandas holidays` |
| **Classic cluster** | Add to cluster libraries or init script |

```python
# For DB Connect 16.4+
from databricks.connect import DatabricksSession, DatabricksEnv

env = DatabricksEnv().withDependencies("faker", "pandas", "numpy", "holidays")
spark = DatabricksSession.builder.withEnvironment(env).serverless(True).getOrCreate()
```

### DatabricksEnv not found

**Problem:** Using older databricks-connect version.

**Solution:** Upgrade to 16.4+ or use job-based approach:

```bash
# Upgrade
pip install "databricks-connect>=16.4,<17.0"

# Or use job with environments parameter instead
```

### serverless_compute_id error

**Problem:** Missing serverless configuration.

**Solution:** Add to `~/.databrickscfg`:

```ini
[DEFAULT]
host = https://your-workspace.cloud.databricks.com/
serverless_compute_id = auto
auth_type = databricks-cli
```

---

## Execution Issues

### Serverless job fails to start

**Possible causes:**
1. Workspace doesn't have serverless enabled
2. Unity Catalog permissions missing
3. Invalid environment configuration

**Solutions:**
```python
# Verify serverless is available
# Try creating a simple job first to test

# Check Unity Catalog permissions
spark.sql("SELECT current_catalog(), current_schema()")
```

### Classic cluster startup slow (3-8 minutes)

**Problem:** Clusters take time to start.

**Solution:** Switch to serverless:

```python
# Instead of:
# spark = DatabricksSession.builder.clusterId("xxx").getOrCreate()

# Use:
spark = DatabricksSession.builder.serverless(True).getOrCreate()
```

### "Either base environment or version must be provided"

**Problem:** Missing `client` in job environment spec.

**Solution:** Add `"client": "4"` to the spec:

```python
{
  "environments": [{
    "environment_key": "datagen_env",
    "spec": {
      "client": "4",  # Required!
      "dependencies": ["faker", "numpy", "pandas"]
    }
  }]
}
```

---

## Data Generation Issues

### Faker UDF is slow

**Problem:** Single-row UDFs don't parallelize well.

**Solution:** Use `pandas_udf` for batch processing:

```python
# SLOW - scalar UDF
@F.udf(returnType=StringType())
def slow_fake_name():
    return Faker().name()

# FAST - pandas UDF (batch processing)
@F.pandas_udf(StringType())
def fast_fake_name(ids: pd.Series) -> pd.Series:
    fake = Faker()
    return pd.Series([fake.name() for _ in range(len(ids))])
```

### Out of memory with large data

**Problem:** Not enough partitions for data size.

**Solution:** Increase partitions:

```python
# For large datasets (1M+ rows)
customers_df = spark.range(0, N_CUSTOMERS, numPartitions=64)  # Increase from default
```

| Data Size | Recommended Partitions |
|-----------|----------------------|
| < 100K | 8 |
| 100K - 500K | 16 |
| 500K - 1M | 32 |
| 1M+ | 64+ |

### Context corrupted on classic cluster

**Problem:** Stale execution context.

**Solution:** Create fresh context (omit context_id), reinstall libraries:

```python
# Don't reuse context_id if you see strange errors
# Let it create a new context
```

### Referential integrity violations

**Problem:** Foreign keys reference non-existent parent records.

**Solution:** Generate master tables first, cache, then join:

```python
# 1. Generate and cache master table
customers_df = spark.range(0, N_CUSTOMERS)...
customer_lookup = customers_df.select("customer_id").cache()

# 2. Generate child table with valid FKs
orders_df = spark.range(0, N_ORDERS).join(
    customer_lookup,
    on=<mapping_condition>,
    how="left"
)

# 3. Clean up
customer_lookup.unpersist()
```

---

## Data Quality Issues

### Uniform distributions (unrealistic)

**Problem:** All customers have similar order counts, amounts are evenly distributed.

**Solution:** Use non-linear distributions:

```python
# BAD - uniform
amounts = np.random.uniform(10, 1000, N)

# GOOD - log-normal (realistic)
amounts = np.random.lognormal(mean=5, sigma=0.8, N)
```

### Missing time-based patterns

**Problem:** Data doesn't reflect weekday/weekend or seasonal patterns.

**Solution:** Add multipliers:

```python
import holidays

US_HOLIDAYS = holidays.US(years=[2024, 2025])

def get_multiplier(date):
    mult = 1.0
    if date.weekday() >= 5:  # Weekend
        mult *= 0.6
    if date in US_HOLIDAYS:
        mult *= 0.3
    return mult
```

### Incoherent row attributes

**Problem:** Enterprise customer has low-value orders, critical ticket has slow resolution.

**Solution:** Correlate attributes:

```python
# Priority based on tier
if tier == 'Enterprise':
    priority = np.random.choice(['Critical', 'High'], p=[0.4, 0.6])
else:
    priority = np.random.choice(['Medium', 'Low'], p=[0.6, 0.4])

# Resolution based on priority
resolution_scale = {'Critical': 4, 'High': 12, 'Medium': 36, 'Low': 72}
resolution_hours = np.random.exponential(scale=resolution_scale[priority])
```

---

## Validation Steps

After generation, verify your data:

```python
# 1. Check row counts
print(f"Customers: {customers_df.count():,}")
print(f"Orders: {orders_df.count():,}")

# 2. Verify distributions
customers_df.groupBy("tier").count().show()
orders_df.describe("amount").show()

# 3. Check referential integrity
orphans = orders_df.join(
    customers_df,
    orders_df.customer_id == customers_df.customer_id,
    "left_anti"
)
print(f"Orphan orders: {orphans.count()}")

# 4. Verify date range
orders_df.select(F.min("order_date"), F.max("order_date")).show()
```

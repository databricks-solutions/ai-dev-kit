# Troubleshooting Guide

Common issues and solutions for synthetic data generation.

## Environment Issues

### ModuleNotFoundError: faker (or other library)

**Problem:** Dependencies not available in execution environment.

**Solutions by execution mode:**

| Mode | Solution |
|------|----------|
| **DB Connect with Serverless** | Install libs locally (`uv pip install faker`), use `DatabricksSession.builder.serverless(True)` |
| **Databricks Runtime** | Use Databricks CLI to install `faker holidays` |
| **Classic cluster** | Use Databricks CLI to install libraries. `databricks libraries install --json '{"cluster_id": "<cluster_id>", "libraries": [{"pypi": {"package": "faker"}}, {"pypi": {"package": "holidays"}}]}'` |

```python
# For DB Connect with serverless
from databricks.connect import DatabricksSession

# Install dependencies locally first: uv pip install faker pandas numpy holidays
spark = DatabricksSession.builder.serverless(True).getOrCreate()
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

### CRITICAL: cache() and persist() NOT supported on serverless

**Problem:** Using `.cache()` or `.persist()` on serverless compute fails with:
```
AnalysisException: [NOT_SUPPORTED_WITH_SERVERLESS] PERSIST TABLE is not supported on serverless compute.
```

**Why this happens:** Serverless compute does not support caching DataFrames in memory. This is a fundamental limitation of the serverless architecture.

**Solution:** Write master tables to Delta first, then read them back for FK joins:

```python
# BAD - will fail on serverless
customers_df = spark.range(0, N_CUSTOMERS)...
customers_df.cache()  # ❌ FAILS: "PERSIST TABLE is not supported on serverless compute"

# GOOD - write to Delta, then read back
customers_df = spark.range(0, N_CUSTOMERS)...
customers_df.write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.customers")
customer_lookup = spark.table(f"{CATALOG}.{SCHEMA}.customers")  # ✓ Read from Delta
```

**Best practice for referential integrity:**
1. Generate master table (e.g., customers)
2. Write to Delta table
3. Read back for FK lookup joins
4. Generate child tables (e.g., orders, tickets) with valid FKs
5. Write child tables to Delta

---

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

### AttributeError: 'function' object has no attribute 'partitionBy'

**Problem:** Using `F.window` instead of `Window` for analytical window functions.

```python
# WRONG - F.window is for time-based tumbling/sliding windows (streaming)
window_spec = F.window.partitionBy("account_id").orderBy("contact_id")
# Error: AttributeError: 'function' object has no attribute 'partitionBy'

# CORRECT - Window is for analytical window specifications
from pyspark.sql.window import Window
window_spec = Window.partitionBy("account_id").orderBy("contact_id")
```

**When to use Window:** For analytical functions like `row_number()`, `rank()`, `lead()`, `lag()`:

```python
from pyspark.sql.window import Window

# Mark first contact per account as primary
window_spec = Window.partitionBy("account_id").orderBy("contact_id")
contacts_df = contacts_df.withColumn(
    "is_primary",
    F.row_number().over(window_spec) == 1
)
```

---

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

**Solution:** Write master table to Delta first, then read back for FK joins:

```python
# 1. Generate and WRITE master table (do NOT use cache with serverless!)
customers_df = spark.range(0, N_CUSTOMERS)...
customers_df.write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.customers")

# 2. Read back for FK lookups
customer_lookup = spark.table(f"{CATALOG}.{SCHEMA}.customers").select("customer_id", "tier")

# 3. Generate child table with valid FKs
orders_df = spark.range(0, N_ORDERS).join(
    customer_lookup,
    on=<mapping_condition>,
    how="left"
)
```

> **WARNING:** Do NOT use `.cache()` or `.persist()` with serverless compute. See the dedicated section above.

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

After generation, validate using SQL queries via Databricks CLI:

```bash
# Set your warehouse ID
WAREHOUSE_ID="your-warehouse-id"
VOLUME_PATH="/Volumes/CATALOG/SCHEMA/raw_data"

# 1. Check row counts
databricks experimental aitools tools query --warehouse $WAREHOUSE_ID "
SELECT 'customers' as table_name, COUNT(*) as row_count FROM parquet.\`${VOLUME_PATH}/customers\`
UNION ALL
SELECT 'orders', COUNT(*) FROM parquet.\`${VOLUME_PATH}/orders\`
"

# 2. Preview schema and sample data
databricks experimental aitools tools query --warehouse $WAREHOUSE_ID "
DESCRIBE SELECT * FROM parquet.\`${VOLUME_PATH}/customers\`
"

databricks experimental aitools tools query --warehouse $WAREHOUSE_ID "
SELECT * FROM parquet.\`${VOLUME_PATH}/customers\` LIMIT 5
"

# 3. Verify distributions
databricks experimental aitools tools query --warehouse $WAREHOUSE_ID "
SELECT tier, COUNT(*) as count, ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1) as pct
FROM parquet.\`${VOLUME_PATH}/customers\`
GROUP BY tier ORDER BY tier
"

# 4. Check amount statistics
databricks experimental aitools tools query --warehouse $WAREHOUSE_ID "
SELECT
  MIN(amount) as min_amount,
  MAX(amount) as max_amount,
  ROUND(AVG(amount), 2) as avg_amount,
  ROUND(STDDEV(amount), 2) as stddev_amount
FROM parquet.\`${VOLUME_PATH}/orders\`
"

# 5. Check referential integrity
databricks experimental aitools tools query --warehouse $WAREHOUSE_ID "
SELECT COUNT(*) as orphan_orders
FROM parquet.\`${VOLUME_PATH}/orders\` o
LEFT JOIN parquet.\`${VOLUME_PATH}/customers\` c ON o.customer_id = c.customer_id
WHERE c.customer_id IS NULL
"

# 6. Verify date range
databricks experimental aitools tools query --warehouse $WAREHOUSE_ID "
SELECT MIN(order_date) as min_date, MAX(order_date) as max_date
FROM parquet.\`${VOLUME_PATH}/orders\`
"
```

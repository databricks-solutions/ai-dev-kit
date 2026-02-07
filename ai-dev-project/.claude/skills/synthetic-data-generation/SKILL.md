---
name: synthetic-data-generation
description: "Generate realistic synthetic data using Faker and Spark, with non-linear distributions, integrity constraints, and save to Databricks. Use when creating test data, demo datasets, or synthetic tables."
---

# Synthetic Data Generation

Generate realistic, story-driven synthetic data for Databricks using Python with Faker and Spark.

## Common Libraries

These libraries are useful for generating realistic synthetic data:

- **faker**: Generates realistic names, addresses, emails, companies, dates, etc.
- **holidays**: Provides country-specific holiday calendars for realistic date patterns

These are typically NOT pre-installed on Databricks. Install them using `execute_databricks_command` tool:
- `code`: "%pip install faker holidays"

Save the returned `cluster_id` and `context_id` for subsequent calls.

## Workflow

1. **Write Python code to a local file** in the project (e.g., `scripts/generate_data.py`)
2. **Execute on Databricks** using the `run_python_file_on_databricks` MCP tool
3. **If execution fails**: Edit the local file to fix the error, then re-execute
4. **Reuse the context** for follow-up executions by passing the returned `cluster_id` and `context_id`

**Always work with local files first, then execute.** This makes debugging easier - you can see and edit the code.

### Context Reuse Pattern

The first execution auto-selects a running cluster and creates an execution context. **Reuse this context for follow-up calls** - it's much faster (~1s vs ~15s) and shares variables/imports:

**First execution** - use `run_python_file_on_databricks` tool:
- `file_path`: "scripts/generate_data.py"

Returns: `{ success, output, error, cluster_id, context_id, ... }`

Save `cluster_id` and `context_id` for follow-up calls.

**If execution fails:**
1. Read the error from the result
2. Edit the local Python file to fix the issue
3. Re-execute with same context using `run_python_file_on_databricks` tool:
   - `file_path`: "scripts/generate_data.py"
   - `cluster_id`: "<saved_cluster_id>"
   - `context_id`: "<saved_context_id>"

**Follow-up executions** reuse the context (faster, shares state):
- `file_path`: "scripts/validate_data.py"
- `cluster_id`: "<saved_cluster_id>"
- `context_id`: "<saved_context_id>"

### Handling Failures

When execution fails:
1. Read the error from the result
2. **Edit the local Python file** to fix the issue
3. Re-execute using the same `cluster_id` and `context_id` (faster, keeps installed libraries)
4. If the context is corrupted, omit `context_id` to create a fresh one

### Installing Libraries

Databricks provides Spark, pandas, numpy, and common data libraries by default. **Only install a library if you get an import error.**

Use `execute_databricks_command` tool:
- `code`: "%pip install faker"
- `cluster_id`: "<cluster_id>"
- `context_id`: "<context_id>"

The library is immediately available in the same context.

**Note:** Keeping the same `context_id` means installed libraries persist across calls.

## Storage Destination

### Ask for Schema Name

By default, use the `ai_dev_kit` catalog. Ask the user which schema to use:

> "I'll save the data to `ai_dev_kit.<schema>`. What schema name would you like to use? (You can also specify a different catalog if needed.)"

If the user provides just a schema name, use `ai_dev_kit.{schema}`. If they provide `catalog.schema`, use that instead.

### Create Infrastructure in the Script

Always create the catalog, schema, and volume **inside the Python script** using `spark.sql()`. Do NOT make separate MCP SQL calls - it's much slower.

The `spark` variable is available by default on Databricks clusters.

```python
# =============================================================================
# CREATE INFRASTRUCTURE (inside the Python script)
# =============================================================================
spark.sql(f"CREATE CATALOG IF NOT EXISTS {CATALOG}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.raw_data")
```

### Save to Volume as Raw Data (Never Tables)

**Always save data to a Volume as parquet files, never directly to tables** (unless the user explicitly requests tables). This is the input for the downstream Spark Declarative Pipeline (SDP) that will handle bronze/silver/gold layers.

```python
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw_data"

# Save as parquet files (raw data)
spark.createDataFrame(customers_pdf).write.mode("overwrite").parquet(f"{VOLUME_PATH}/customers")
spark.createDataFrame(orders_pdf).write.mode("overwrite").parquet(f"{VOLUME_PATH}/orders")
spark.createDataFrame(tickets_pdf).write.mode("overwrite").parquet(f"{VOLUME_PATH}/tickets")
```

## Raw Data Only - No Pre-Aggregated Fields (Unless Instructed Otherwise)

**By default, generate raw, transactional data only.** Do not create fields that represent sums, totals, averages, or counts.

- One row = one event/transaction/record
- No columns like `total_orders`, `sum_revenue`, `avg_csat`, `order_count`
- Each row has its own individual values, not rollups

**Why?** A Spark Declarative Pipeline (SDP) will typically be built after data generation to:
- Ingest raw data (bronze layer)
- Clean and validate (silver layer)
- Aggregate and compute metrics (gold layer)

The synthetic data is the **source** for this pipeline. Aggregations happen downstream.

**Note:** If the user specifically requests aggregated fields or summary tables, follow their instructions.

```python
# GOOD - Raw transactional data
# Customer table: one row per customer, no aggregated fields
customers_data.append({
    "customer_id": cid,
    "name": fake.company(),
    "tier": "Enterprise",
    "region": "North",
})

# Order table: one row per order
orders_data.append({
    "order_id": f"ORD-{i:06d}",
    "customer_id": cid,
    "amount": 150.00,  # This order's amount
    "order_date": "2024-10-15",
})

# BAD - Don't add pre-aggregated fields
# customers_data.append({
#     "customer_id": cid,
#     "total_orders": 47,        # NO - this is an aggregation
#     "total_revenue": 12500.00, # NO - this is a sum
#     "avg_order_value": 265.95, # NO - this is an average
# })
```

## Temporality and Data Volume

### Date Range: Last 6 Months from Today

**Always generate data for the last ~6 months ending at the current date.** This ensures:
- Data feels current and relevant for demos
- Recent patterns are visible in dashboards
- Downstream aggregations (daily/weekly/monthly) have enough history

```python
from datetime import datetime, timedelta

# Dynamic date range - last 6 months from today
END_DATE = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
START_DATE = END_DATE - timedelta(days=180)

# Place special events within this range (e.g., incident 3 weeks ago)
INCIDENT_END = END_DATE - timedelta(days=21)
INCIDENT_START = INCIDENT_END - timedelta(days=10)
```

### Data Volume for Aggregation

Generate enough data so patterns remain visible after downstream aggregation (SDP pipelines often aggregate by day/week/region/category). Rules of thumb:

| Grain | Minimum Records | Rationale |
|-------|-----------------|-----------|
| Daily time series | 50-100/day | See trends after weekly rollup |
| Per category | 500+ per category | Statistical significance |
| Per customer | 5-20 events/customer | Enough for customer-level analysis |
| Total rows | 10K-50K minimum | Patterns survive GROUP BY |

```python
# Example: 8000 tickets over 180 days = ~44/day average
# After weekly aggregation: ~310 records per week per category
# After monthly by region: still enough to see patterns
N_TICKETS = 8000
N_CUSTOMERS = 2500  # Each has ~3 tickets on average
N_ORDERS = 25000    # ~10 orders per customer average
```

## Script Structure

Always structure scripts with configuration variables at the top:

```python
"""Generate synthetic data for [use case]."""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from faker import Faker
import holidays
from pyspark.sql import SparkSession

# =============================================================================
# CONFIGURATION - Edit these values
# =============================================================================
CATALOG = "my_catalog"
SCHEMA = "my_schema"
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw_data"

# Data sizes - enough for aggregation patterns to survive
N_CUSTOMERS = 2500
N_ORDERS = 25000
N_TICKETS = 8000

# Date range - last 6 months from today
END_DATE = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
START_DATE = END_DATE - timedelta(days=180)

# Special events (within the date range)
INCIDENT_END = END_DATE - timedelta(days=21)
INCIDENT_START = INCIDENT_END - timedelta(days=10)

# Holiday calendar for realistic patterns
US_HOLIDAYS = holidays.US(years=[START_DATE.year, END_DATE.year])

# Reproducibility
SEED = 42

# =============================================================================
# SETUP
# =============================================================================
np.random.seed(SEED)
Faker.seed(SEED)
fake = Faker()
spark = SparkSession.builder.getOrCreate()

# ... rest of script
```

## Key Principles

### 1. Use Pandas for Generation, Spark for Saving

Generate data with pandas (faster, easier), convert to Spark for saving:

```python
import pandas as pd

# Generate with pandas
customers_pdf = pd.DataFrame({
    "customer_id": [f"CUST-{i:05d}" for i in range(N_CUSTOMERS)],
    "name": [fake.company() for _ in range(N_CUSTOMERS)],
    "tier": np.random.choice(['Free', 'Pro', 'Enterprise'], N_CUSTOMERS, p=[0.6, 0.3, 0.1]),
    "region": np.random.choice(['North', 'South', 'East', 'West'], N_CUSTOMERS, p=[0.4, 0.25, 0.2, 0.15]),
    "created_at": [fake.date_between(start_date='-2y', end_date='-6m') for _ in range(N_CUSTOMERS)],
})

# Convert to Spark and save
customers_df = spark.createDataFrame(customers_pdf)
customers_df.write.mode("overwrite").parquet(f"{VOLUME_PATH}/customers")
```

### 2. Iterate on DataFrames for Referential Integrity

Generate master tables first, then iterate on them to create related tables with matching IDs:

```python
# 1. Generate customers (master table)
customers_pdf = pd.DataFrame({
    "customer_id": [f"CUST-{i:05d}" for i in range(N_CUSTOMERS)],
    "tier": np.random.choice(['Free', 'Pro', 'Enterprise'], N_CUSTOMERS, p=[0.6, 0.3, 0.1]),
    # ...
})

# 2. Create lookup for foreign key generation
customer_ids = customers_pdf["customer_id"].tolist()
customer_tier_map = dict(zip(customers_pdf["customer_id"], customers_pdf["tier"]))

# Weight by tier - Enterprise customers generate more orders
tier_weights = customers_pdf["tier"].map({'Enterprise': 5.0, 'Pro': 2.0, 'Free': 1.0})
customer_weights = (tier_weights / tier_weights.sum()).tolist()

# 3. Generate orders with valid foreign keys and tier-based logic
orders_data = []
for i in range(N_ORDERS):
    cid = np.random.choice(customer_ids, p=customer_weights)
    tier = customer_tier_map[cid]

    # Amount depends on tier
    if tier == 'Enterprise':
        amount = np.random.lognormal(7, 0.8)
    elif tier == 'Pro':
        amount = np.random.lognormal(5, 0.7)
    else:
        amount = np.random.lognormal(3.5, 0.6)

    orders_data.append({
        "order_id": f"ORD-{i:06d}",
        "customer_id": cid,
        "amount": round(amount, 2),
        "order_date": fake.date_between(start_date=START_DATE, end_date=END_DATE),
    })

orders_pdf = pd.DataFrame(orders_data)

# 4. Generate tickets that reference both customers and orders
order_ids = orders_pdf["order_id"].tolist()
tickets_data = []
for i in range(N_TICKETS):
    cid = np.random.choice(customer_ids, p=customer_weights)
    oid = np.random.choice(order_ids)  # Or None for general inquiry

    tickets_data.append({
        "ticket_id": f"TKT-{i:06d}",
        "customer_id": cid,
        "order_id": oid if np.random.random() > 0.3 else None,
        # ...
    })

tickets_pdf = pd.DataFrame(tickets_data)
```

### 3. Non-Linear Distributions

**Never use uniform distributions** - real data is rarely uniform:

```python
# BAD - Uniform (unrealistic)
prices = np.random.uniform(10, 1000, size=N_ORDERS)

# GOOD - Log-normal (realistic for prices, salaries, order amounts)
prices = np.random.lognormal(mean=4.5, sigma=0.8, size=N_ORDERS)

# GOOD - Pareto/power law (popularity, wealth, page views)
popularity = (np.random.pareto(a=2.5, size=N_PRODUCTS) + 1) * 10

# GOOD - Exponential (time between events, resolution time)
resolution_hours = np.random.exponential(scale=24, size=N_TICKETS)

# GOOD - Weighted categorical
regions = np.random.choice(
    ['North', 'South', 'East', 'West'],
    size=N_CUSTOMERS,
    p=[0.40, 0.25, 0.20, 0.15]
)
```

### 4. Time-Based Patterns

Add weekday/weekend effects, holidays, seasonality, and event spikes:

```python
import holidays

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

    # Incident spike
    if INCIDENT_START <= date <= INCIDENT_END:
        multiplier *= 3.0

    # Random noise
    multiplier *= np.random.normal(1, 0.1)

    return max(0.1, multiplier)

# Distribute tickets across dates with realistic patterns
date_range = pd.date_range(START_DATE, END_DATE, freq='D')
daily_volumes = [int(BASE_DAILY_TICKETS * get_daily_multiplier(d)) for d in date_range]
```

### 5. Row Coherence

Attributes within a row should correlate logically:

```python
def generate_ticket(customer_id, tier, date):
    """Generate a coherent ticket where attributes correlate."""

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

    return {
        "customer_id": customer_id,
        "priority": priority,
        "resolution_hours": round(resolution_hours, 1),
        "csat_score": csat,
        "created_at": date,
    }
```

## Complete Example

Save as `scripts/generate_data.py`:

```python
"""Generate synthetic customer, order, and ticket data."""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from faker import Faker
import holidays
from pyspark.sql import SparkSession

# =============================================================================
# CONFIGURATION
# =============================================================================
CATALOG = "my_catalog"
SCHEMA = "my_schema"
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw_data"

N_CUSTOMERS = 2500
N_ORDERS = 25000
N_TICKETS = 8000

# Date range - last 6 months from today
END_DATE = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
START_DATE = END_DATE - timedelta(days=180)

# Special events (within the date range)
INCIDENT_END = END_DATE - timedelta(days=21)
INCIDENT_START = INCIDENT_END - timedelta(days=10)

# Holiday calendar
US_HOLIDAYS = holidays.US(years=[START_DATE.year, END_DATE.year])

SEED = 42

# =============================================================================
# SETUP
# =============================================================================
np.random.seed(SEED)
Faker.seed(SEED)
fake = Faker()
spark = SparkSession.builder.getOrCreate()

# =============================================================================
# CREATE INFRASTRUCTURE
# =============================================================================
print(f"Creating catalog/schema/volume if needed...")
spark.sql(f"CREATE CATALOG IF NOT EXISTS {CATALOG}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.raw_data")

print(f"Generating: {N_CUSTOMERS:,} customers, {N_ORDERS:,} orders, {N_TICKETS:,} tickets")

# =============================================================================
# 1. CUSTOMERS (Master Table)
# =============================================================================
print("Generating customers...")

customers_pdf = pd.DataFrame({
    "customer_id": [f"CUST-{i:05d}" for i in range(N_CUSTOMERS)],
    "name": [fake.company() for _ in range(N_CUSTOMERS)],
    "tier": np.random.choice(['Free', 'Pro', 'Enterprise'], N_CUSTOMERS, p=[0.6, 0.3, 0.1]),
    "region": np.random.choice(['North', 'South', 'East', 'West'], N_CUSTOMERS, p=[0.4, 0.25, 0.2, 0.15]),
})

# ARR correlates with tier
customers_pdf["arr"] = customers_pdf["tier"].apply(
    lambda t: round(np.random.lognormal(11, 0.5), 2) if t == 'Enterprise'
              else round(np.random.lognormal(8, 0.6), 2) if t == 'Pro' else 0
)

# Lookups for foreign keys
customer_ids = customers_pdf["customer_id"].tolist()
customer_tier_map = dict(zip(customers_pdf["customer_id"], customers_pdf["tier"]))
tier_weights = customers_pdf["tier"].map({'Enterprise': 5.0, 'Pro': 2.0, 'Free': 1.0})
customer_weights = (tier_weights / tier_weights.sum()).tolist()

print(f"  Created {len(customers_pdf):,} customers")

# =============================================================================
# 2. ORDERS (References Customers)
# =============================================================================
print("Generating orders...")

orders_data = []
for i in range(N_ORDERS):
    cid = np.random.choice(customer_ids, p=customer_weights)
    tier = customer_tier_map[cid]
    amount = np.random.lognormal(7 if tier == 'Enterprise' else 5 if tier == 'Pro' else 3.5, 0.7)

    orders_data.append({
        "order_id": f"ORD-{i:06d}",
        "customer_id": cid,
        "amount": round(amount, 2),
        "status": np.random.choice(['completed', 'pending', 'cancelled'], p=[0.85, 0.10, 0.05]),
        "order_date": fake.date_between(start_date=START_DATE, end_date=END_DATE),
    })

orders_pdf = pd.DataFrame(orders_data)
print(f"  Created {len(orders_pdf):,} orders")

# =============================================================================
# 3. TICKETS (References Customers, with incident spike)
# =============================================================================
print("Generating tickets...")

def get_daily_volume(date, base=25):
    vol = base * (0.6 if date.weekday() >= 5 else 1.0)
    if date in US_HOLIDAYS:
        vol *= 0.3  # Even lower on holidays
    if INCIDENT_START <= date <= INCIDENT_END:
        vol *= 3.0
    return int(vol * np.random.normal(1, 0.15))

# Distribute tickets across dates
tickets_data = []
ticket_idx = 0
for day in pd.date_range(START_DATE, END_DATE):
    daily_count = get_daily_volume(day.to_pydatetime())
    is_incident = INCIDENT_START <= day.to_pydatetime() <= INCIDENT_END

    for _ in range(daily_count):
        if ticket_idx >= N_TICKETS:
            break

        cid = np.random.choice(customer_ids, p=customer_weights)
        tier = customer_tier_map[cid]

        # Category - Auth dominates during incident
        if is_incident:
            category = np.random.choice(['Auth', 'Network', 'Billing', 'Account'], p=[0.65, 0.15, 0.1, 0.1])
        else:
            category = np.random.choice(['Auth', 'Network', 'Billing', 'Account'], p=[0.25, 0.30, 0.25, 0.20])

        # Priority correlates with tier
        priority = np.random.choice(['Critical', 'High', 'Medium'], p=[0.3, 0.5, 0.2]) if tier == 'Enterprise' \
                   else np.random.choice(['Critical', 'High', 'Medium', 'Low'], p=[0.05, 0.2, 0.45, 0.3])

        # Resolution time correlates with priority
        res_scale = {'Critical': 4, 'High': 12, 'Medium': 36, 'Low': 72}
        resolution = np.random.exponential(scale=res_scale[priority])

        # CSAT degrades during incident for Auth
        if is_incident and category == 'Auth':
            csat = np.random.choice([1, 2, 3, 4, 5], p=[0.15, 0.25, 0.35, 0.2, 0.05])
        else:
            csat = 5 if resolution < 4 else (4 if resolution < 12 else np.random.choice([2, 3, 4], p=[0.2, 0.5, 0.3]))

        tickets_data.append({
            "ticket_id": f"TKT-{ticket_idx:06d}",
            "customer_id": cid,
            "category": category,
            "priority": priority,
            "resolution_hours": round(resolution, 1),
            "csat_score": csat,
            "created_at": day.strftime("%Y-%m-%d"),
        })
        ticket_idx += 1

    if ticket_idx >= N_TICKETS:
        break

tickets_pdf = pd.DataFrame(tickets_data)
print(f"  Created {len(tickets_pdf):,} tickets")

# =============================================================================
# 4. SAVE TO VOLUME
# =============================================================================
print(f"\nSaving to {VOLUME_PATH}...")

spark.createDataFrame(customers_pdf).write.mode("overwrite").parquet(f"{VOLUME_PATH}/customers")
spark.createDataFrame(orders_pdf).write.mode("overwrite").parquet(f"{VOLUME_PATH}/orders")
spark.createDataFrame(tickets_pdf).write.mode("overwrite").parquet(f"{VOLUME_PATH}/tickets")

print("Done!")

# =============================================================================
# 5. VALIDATION
# =============================================================================
print("\n=== VALIDATION ===")
print(f"Tier distribution: {customers_pdf['tier'].value_counts(normalize=True).to_dict()}")
print(f"Avg order by tier: {orders_pdf.merge(customers_pdf[['customer_id', 'tier']]).groupby('tier')['amount'].mean().to_dict()}")

incident_tickets = tickets_pdf[tickets_pdf['created_at'].between(
    INCIDENT_START.strftime("%Y-%m-%d"), INCIDENT_END.strftime("%Y-%m-%d")
)]
print(f"Incident period tickets: {len(incident_tickets):,} ({len(incident_tickets)/len(tickets_pdf)*100:.1f}%)")
print(f"Incident Auth %: {(incident_tickets['category'] == 'Auth').mean()*100:.1f}%")
```

Execute using `run_python_file_on_databricks` tool:
- `file_path`: "scripts/generate_data.py"

If it fails, edit the file and re-run with the same `cluster_id` and `context_id`.

### Validate Generated Data

After successful execution, use `get_volume_folder_details` tool to verify the generated data:
- `volume_path`: "my_catalog/my_schema/raw_data/customers"
- `format`: "parquet"
- `table_stat_level`: "SIMPLE"

This returns schema, row counts, and column statistics to confirm the data was written correctly.

## Best Practices

1. **Ask for schema**: Default to `ai_dev_kit` catalog, ask user for schema name
2. **Create infrastructure**: Use `CREATE CATALOG/SCHEMA/VOLUME IF NOT EXISTS`
3. **Raw data only**: No `total_x`, `sum_x`, `avg_x` fields - SDP pipeline computes those
4. **Save to Volume, not tables**: Write parquet to `/Volumes/{catalog}/{schema}/raw_data/<input_datasource_name>`
5. **Configuration at top**: All sizes, dates, and paths as variables
6. **Dynamic dates**: Use `datetime.now() - timedelta(days=180)` for last 6 months
7. **Pandas for generation**: Faster and easier than Spark for row-by-row logic
8. **Master tables first**: Generate customers, then orders reference customer_ids
9. **Weighted sampling**: Enterprise customers generate more activity
10. **Distributions**: Log-normal for values, exponential for times, weighted categorical
11. **Time patterns**: Weekday/weekend, holidays, seasonality, event spikes
12. **Row coherence**: Priority affects resolution time affects CSAT
13. **Volume for aggregation**: 10K-50K rows minimum so patterns survive GROUP BY
14. **Always use files**: Write to local file, execute, edit if error, re-execute
15. **Context reuse**: Pass `cluster_id` and `context_id` for faster iterations
16. **Libraries**: Install `faker` and `holidays` first; most others are pre-installed

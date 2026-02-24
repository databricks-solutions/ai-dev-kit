---
name: synthetic-data-generation
description: "Generate realistic synthetic data using Spark + Faker (strongly recommended). Supports serverless execution, multiple output formats (Parquet/JSON/CSV/Delta), and scales from thousands to millions of rows. For small datasets (<10K rows), can optionally generate locally and upload to volumes. Use for test data, demo datasets, or synthetic tables."
---

# Synthetic Data Generation

Generate realistic, story-driven synthetic data for Databricks using Spark + Faker (strongly recommended).
For small datasets (<10K rows), can optionally generate locally with Polars and upload to volumes.
Always present a generation plan with assumptions before generating code.

## Generation Planning Workflow

**Before generating any code, you MUST present a plan for user approval.** Give them a "Surprise Me" option if they don't want to specify details.

### Step 1: Gather Requirements

Ask the user about:
- What domain/scenario? (e-commerce, support tickets, IoT sensors, etc.)
- How many tables? What relationships between them?
- Approximate row counts per table?
- Output format preference? (Parquet to Volume is default)
- One-time generation or scheduled job?

### Step 2: Present Table Specification

Show a clear specification with **YOUR ASSUMPTIONS surfaced**:

| Table | Columns | Rows | Key Assumptions |
|-------|---------|------|-----------------|
| customers | customer_id, name, email, tier, region, created_at | 5,000 | Tier weighted: Free 60%, Pro 30%, Enterprise 10% |
| orders | order_id, customer_id (FK), amount, order_date, status | 15,000 | Enterprise customers generate 5x more orders than Free |

**Assumptions I'm making:**
- Amount distribution: log-normal by tier (Enterprise avg ~$1800, Pro ~$245, Free ~$55)
- Status distribution: 65% delivered, 15% shipped, 10% processing, 5% pending, 5% cancelled

**Generation Approach:**
- **Default**: Generate data using **Spark** (recommended for all use cases)
- **Alternative for <10K rows**: Only if user explicitly prefers local generation, use Polars and upload to volume using `databricks fs cp`

**Ask user**: "Does this look correct? Any adjustments needed?"

### Step 3: Ask About Data Features

Prompt user with options (enabled by default unless otherwise noted):
- [x] Skew (non-uniform distributions) - **Enabled by default**
- [x] Joins (referential integrity between tables) - **Enabled by default**
- [ ] Bad data injection (for data quality testing)
  - Nulls in required fields
  - Outliers/impossible values (house price $1, age 500)
  - Duplicate primary keys
  - Orphan foreign keys (referencing non-existent parents)
- [ ] Multi-language text (non-English names/addresses)
- [ ] Incremental mode (append vs overwrite) - for scheduled jobs

### Pre-Generation Checklist

Before writing any generation code, verify:

- [ ] Generation approach determined: **Spark (strongly recommended)** or local generation with upload (only for <10K rows if user prefers)
- [ ] If using local generation: User notified and prefers this approach
- [ ] User confirmed compute preference (serverless vs cluster)
- [ ] Table specification shown and approved
- [ ] Assumptions about distributions surfaced and confirmed
- [ ] Output location confirmed (catalog.schema)
- [ ] Data features selected (skew, joins, bad data, etc.)
- [ ] Row counts appropriate for use case

**Do NOT proceed to code generation until user approves the plan.**

## Execution Options & Installation

Choose your execution mode based on your needs. **Serverless is strongly recommended** for all use cases.

**When user requests data generation:**
1. Confirm serverless is acceptable: "I'll use serverless compute. Is that OK?"
2. If they request classic cluster: "Serverless is recommended for cost efficiency. Are you sure you need a classic cluster?"

### Option 1: Databricks Connect with Serverless (Recommended)

Run code locally while Spark operations execute on serverless compute. Best for development and interactive work.

# ❌ WRONG - DO NOT USE
from pyspark.sql import SparkSession
spark = SparkSession.builder.getOrCreate()  # Will fail with RuntimeError

# ✅ CORRECT - ALWAYS USE THIS
from databricks.connect import DatabricksSession
spark = DatabricksSession.builder.serverless(True).getOrCreate()

**Install locally (one-time setup):**
```bash
# Python 3.10 or 3.11:
pip install "databricks-connect>=15.1,<16.2" faker numpy pandas holidays

# Python 3.12+:
# IMPORTANT: Use 16.4.x for stable withDependencies API (17.x has breaking changes)
pip install "databricks-connect>=16.4,<17.0" faker numpy pandas holidays

# Configure ~/.databrickscfg
[DEFAULT]
host = https://your-workspace.cloud.databricks.com/
serverless_compute_id = auto
auth_type = databricks-cli
```

**In your script (version-dependent):**

**For Python 3.12+ with databricks-connect >= 16.4:**
```python
from databricks.connect import DatabricksSession, DatabricksEnv

# Pass dependencies as simple package name strings
env = DatabricksEnv().withDependencies("faker", "pandas", "numpy", "holidays")

# Create session
spark = (
    DatabricksSession.builder
    .withEnvironment(env)
    .serverless(True)
    .getOrCreate()
)

# Spark operations now execute on serverless compute with managed dependencies
```

**Version Detection (if needed in your script):**
```python
import importlib.metadata

def get_databricks_connect_version():
    """Get databricks-connect version as (major, minor) tuple."""
    try:
        version_str = importlib.metadata.version('databricks-connect')
        parts = version_str.split('.')
        return (int(parts[0]), int(parts[1]))
    except Exception:
        return None

db_version = get_databricks_connect_version()
if db_version and db_version >= (16, 4):
    # Use DatabricksEnv with withDependencies
    pass
```

**For Python < 3.12 or databricks-connect < 16.4:**

`DatabricksEnv()` and `withEnvironment()` are NOT available in older versions. You must use one of these alternatives:

**Create a job with environment settings**

Create a Databricks job with environment settings on the task. See **Option 2: Serverless Job** section below.

**Note:** If you're using Polars for local generation (not Spark with Faker UDFs), these workarounds are NOT needed since dependencies run locally.

**Benefits:** Instant start, local debugging, fast iteration (edit file, re-run immediately)

### Option 2: Serverless Job (Production/Scheduled)

Submit jobs to serverless compute with automatic dependency management. Best for production and scheduled workloads.

**Dependencies managed via `environments` parameter:**
```python
# Use create_job MCP tool with:
{
  "name": "generate_synthetic_data",
  "tasks": [{ "environment_key": "datagen_env", ... }],
  "environments": [{
    "environment_key": "datagen_env",
    "spec": {
      "client": "4",
      "dependencies": ["faker", "polars", "numpy", "pandas", "holidays"]
    }
  }]
}
```

**Benefits:** No local setup, automatic dependency management, production-ready scaling

### Option 3: Classic Cluster (Fallback Only)

Use only if serverless unavailable or you need specific cluster features (GPUs, custom init scripts).

**Warning:** Classic clusters take 3-8 minutes to start. Prefer serverless.

**Install dependencies in cluster:**
```python
# Using execute_databricks_command tool:
code = "%pip install faker polars numpy pandas holidays"
# Save returned cluster_id and context_id for subsequent calls
```

**When to use:** Only when serverless not available or specific cluster configurations required

## Required Libraries

Standard libraries for generating realistic synthetic data:

- **faker**: Realistic names, addresses, emails, companies, dates (100+ providers)
- **numpy/pandas**: Statistical distributions and data manipulation
- **holidays**: Country-specific holiday calendars for realistic date patterns
- **polars**: Fast local DataFrame library (optional, only for local generation)

See **Execution Options & Installation** above for installation instructions per execution mode.

## Data Generation Approaches

Choose your approach based on scale and where you need to write data:

### Approach 1: Spark + Faker with Pandas UDFs (Recommended for most cases)

**Best for:** Any dataset size, especially >100K rows, writing to Unity Catalog

Generate data with Spark + Faker with Pandas UDFs, save to Databricks.

**Key features:**
- Full access to 100+ Faker providers (names, addresses, companies, etc.)
- Use Pandas UDFs for parallelism with large datasets
- Flexible custom logic for complex patterns
- Direct integration with Unity Catalog via Spark

**Example:**
```python
# Define Pandas UDFs for Faker data (batch processing for parallelism)
@pandas_udf(StringType())
def fake_name(ids: pd.Series) -> pd.Series:
    fake = Faker()
    return pd.Series([fake.name() for _ in range(len(ids))])

@pandas_udf(StringType())
def fake_company(ids: pd.Series) -> pd.Series:
    fake = Faker()
    return pd.Series([fake.company() for _ in range(len(ids))])

# Generate with Spark + Pandas UDFs
# Adjust numPartitions based on scale: 8 for <100K, 32 for 1M+
customers_df = (
    spark.range(0, N_CUSTOMERS, numPartitions=8)
    .select(
        F.concat(F.lit("CUST-"), F.lpad(F.col("id").cast("string"), 5, "0")).alias("customer_id"),
        fake_name(F.col("id")).alias("name"),
        fake_company(F.col("id")).alias("company"),
        F.when(F.rand() < 0.6, "Free")
         .when(F.rand() < 0.9, "Pro")
         .otherwise("Enterprise").alias("tier"),
    )
)
customers_df.write.mode("overwrite").parquet(f"{VOLUME_PATH}/customers")
```

### Approach 2: Polars (For local development - Use only if Spark not suitable)

**Important:** Only use this approach for datasets <10K rows if user explicitly prefers local generation.

**Best for:** Quick prototyping when Spark is not needed, datasets <10K rows

Generate entirely with Polars + Faker locally, export to parquet files, then upload to Databricks volumes.

**Key features:**
- Fast local generation (no Spark overhead)
- Simple, clean API
- Perfect for quick prototyping with very small datasets
- Requires manual upload to Databricks volumes

**Example:**
```python
import polars as pl
from faker import Faker
import numpy as np

fake = Faker()

# Generate with Polars
customers = pl.DataFrame({
    "customer_id": [f"CUST-{i:05d}" for i in range(N_CUSTOMERS)],
    "name": [fake.name() for _ in range(N_CUSTOMERS)],
    "email": [fake.email() for _ in range(N_CUSTOMERS)],
    "tier": np.random.choice(["Free", "Pro", "Enterprise"], N_CUSTOMERS, p=[0.6, 0.3, 0.1]),
})

# Save locally
customers.write_parquet("./output/customers.parquet")
```

**Upload to Databricks Volume:**
After generating data locally, upload to a Databricks volume:

```bash
# Create directory in volume if needed
databricks fs mkdirs dbfs:/Volumes/<catalog>/<schema>/<volume>/source_data/

# Upload local data to volume
databricks fs cp -r ./output/customers.parquet dbfs:/Volumes/<catalog>/<schema>/<volume>/source_data/
databricks fs cp -r ./output/orders.parquet dbfs:/Volumes/<catalog>/<schema>/<volume>/source_data/
```

### When to Use Each Approach

| Scenario | Recommended Approach |
|----------|---------------------|
| **Default - any data generation** | **Spark + Faker with Pandas UDFs** |
| Generating 1M+ rows | **Spark + Faker with Pandas UDFs** |
| Quick prototyping (<10K rows, user explicitly prefers local) | **Polars** (then upload with `databricks fs cp`) |

**Default:** Use Spark + Faker for all cases. Only use Polars if dataset is <10K rows AND user explicitly requests local generation.

## Workflow

### Development (Databricks Connect)

1. **One-time setup**: Install dependencies locally (see **Execution Options & Installation** above)
2. **Write script**: Create `scripts/generate_data.py` with `DatabricksSession.builder.serverless(True)`
3. **Run locally**: `python scripts/generate_data.py` (Spark ops execute on serverless)
4. **Iterate**: Edit file, re-run immediately

### Production (Serverless Job)

1. **Write script locally**
2. **Upload** using `upload_file` MCP tool to `/Workspace/Users/{username}/datagen/{project}/`
3. **Create job** using `create_job` MCP tool with `environments` parameter (see Option 2 above)
4. **Run & monitor** using `run_job_now` and `wait_for_run` MCP tools

### Production (DABs Bundle)

For version control and CI/CD:

```yaml
# databricks.yml
bundle:
  name: synthetic-data-gen

resources:
  jobs:
    generate_daily_data:
      name: "Generate Daily Data"
      schedule:
        quartz_cron_expression: "0 0 6 * * ?"
      tasks:
        - task_key: generate
          spark_python_task:
            python_file: ./src/generate_data.py
          environment_key: default

environments:
  default:
    spec:
      client: "4"
      dependencies:
        - faker
        - polars
        - numpy
        - pandas
        - holidays
```

## Storage Destination

### Ask for Schema Name

By default, use the `ai_dev_kit` catalog. Ask the user which schema to use:

> "I'll save the data to `ai_dev_kit.<schema>`. What schema name would you like to use? (You can also specify a different catalog if needed.)"

If the user provides just a schema name, use `ai_dev_kit.{schema}`. If they provide `catalog.schema`, use that instead.

### Create Infrastructure in the Script

Always create the schema and volume **inside the Python script** using `spark.sql()`. Do NOT make separate MCP SQL calls - it's much slower.

**Important:** Do NOT create catalogs - assume they already exist. Only create schema and volume.

The `spark` variable is available by default on Databricks clusters.

```python
# =============================================================================
# CREATE INFRASTRUCTURE (inside the Python script)
# =============================================================================
# Note: Assume catalog exists - do NOT create it
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.raw_data")
```

### Output Formats

Choose your output format based on downstream needs:

#### Parquet to Volumes (Default)

Standard format for SDP pipeline input. Best compression and query performance.
Files may not use a file extension or might end with .parquet.

```python
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw_data"

# Save as parquet files
customers_df.write.mode("overwrite").parquet(f"{VOLUME_PATH}/customers")
orders_df.write.mode("overwrite").parquet(f"{VOLUME_PATH}/orders")
tickets_df.write.mode("overwrite").parquet(f"{VOLUME_PATH}/tickets")
```

#### JSON to Volumes

A common pattern user may request for simulate SDP ingestion from external data feeds such as logs.
File extension should be .json

```python
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw_data"

# Save as JSON files
customers_df.write.mode("overwrite").json(f"{VOLUME_PATH}/customers_json")
orders_df.write.mode("overwrite").json(f"{VOLUME_PATH}/orders_json")
```

#### CSV to Volumes

A common pattern user may request for simulate SDP ingestion from external data feeds such as logs.
File extension should be .csv.

```python
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw_data"

# Save as CSV with headers
customers_df.write.mode("overwrite").option("header", "true").csv(f"{VOLUME_PATH}/customers_csv")
orders_df.write.mode("overwrite").option("header", "true").csv(f"{VOLUME_PATH}/orders_csv")
```

#### Delta Table (Unity Catalog)

When data is ready for direct analytics consumption (skip SDP pipeline).

```python
# Ensure schema exists
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")

# Save as managed Delta tables
customers_df.write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.customers")
orders_df.write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.orders")

# With additional options
customers_df.write \
    .mode("overwrite") \
    .option("overwriteSchema", "true") \
    .saveAsTable(f"{CATALOG}.{SCHEMA}.customers")
```

#### When to Use Each Format

| Format | Use Case |
|--------|----------|
| **Parquet to Volumes** | Default - input for SDP bronze/silver/gold pipelines |
| **JSON to Volumes** | User request - a common pattern in real Databricks ingestion workloads |
| **CSV to Volumes** | User request - a common pattern in real Databricks ingestion workloads |
| **Delta Table** | Direct analytics - user may not want to build the ingestion and have data ready to query in notebooks or with SQL |

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

**Always generate data for the last ~6 months ending at the current date, unless prompted with specific timeframe.** This ensures:
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

## Business Integrity Requirements

Generated data MUST reflect business reality. Data should be realistic and tell a coherent story.

| Pattern | Example | Implementation |
|---------|---------|----------------|
| **Value coherence** | Houses worth $200K-$2M, pens $1-$50 | Domain-appropriate ranges |
| **Tier behavior** | Premium users have more orders | Weighted sampling by tier |
| **Temporal patterns** | More orders on weekends, holidays | Time-based distributions |
| **Geographic patterns** | Regional pricing differences | Location-correlated values |
| **Multi-table integrity** | Orders reference valid customers | Foreign key validation |

**Anti-pattern**: Flat/linear distributions (every customer has ~same # orders)

**Correct**: Skewed distributions (80/20 rule - 20% of customers generate 80% of orders)

### Bad Data Injection (Optional)

When user requests bad data for testing data quality rules:

```python
# Bad data configuration
BAD_DATA_CONFIG = {
    "null_rate": 0.02,           # 2% nulls in required fields
    "outlier_rate": 0.01,        # 1% impossible values
    "duplicate_pk_rate": 0.005,  # 0.5% duplicate primary keys
    "orphan_fk_rate": 0.01,      # 1% orphan foreign keys
}

# Inject after generation
if INJECT_BAD_DATA:
    # Nulls in required fields
    null_mask = np.random.random(len(orders_pdf)) < BAD_DATA_CONFIG["null_rate"]
    orders_pdf.loc[null_mask, "customer_id"] = None

    # Outliers (impossible values)
    outlier_mask = np.random.random(len(orders_pdf)) < BAD_DATA_CONFIG["outlier_rate"]
    orders_pdf.loc[outlier_mask, "amount"] = -999.99  # Negative amount

    # Orphan foreign keys
    orphan_mask = np.random.random(len(orders_pdf)) < BAD_DATA_CONFIG["orphan_fk_rate"]
    orders_pdf.loc[orphan_mask, "customer_id"] = "CUST-NONEXISTENT"
```

## Domain-Specific Guidance

When generating data for specific domains, consider these realistic patterns:

### Retail/E-commerce
- **Tables**: customers → orders → order_items → products
- **Patterns**:
  - Seasonal spikes (holiday shopping)
  - Cart abandonment (~70% of carts)
  - Loyalty tier progression
  - Regional pricing

### Support/CRM
- **Tables**: accounts → contacts → tickets → interactions
- **Patterns**:
  - Incident spikes during outages
  - Resolution time varies by priority
  - Enterprise accounts have more contacts
  - CSAT correlates with resolution speed

### Manufacturing/IoT
- **Tables**: equipment → sensors → readings → maintenance_orders
- **Patterns**:
  - Sensor readings follow equipment lifecycle
  - Anomalies precede maintenance events
  - Seasonal production variations
  - Equipment age affects failure rates

### Financial Services
- **Tables**: accounts → transactions → payments → fraud_flags
- **Patterns**:
  - Transaction amounts follow power law
  - Fraud patterns (unusual times, amounts, locations)
  - Account balance consistency
  - Regulatory compliance (no negative balances)

**Note**: These are guidance, not rigid schemas. Adapt to user's specific needs.

## Key Principles

### 1. Use Spark + Faker for All Data Generation

Generate data with Spark + Faker for all use cases. This provides scalability, parallelism, and direct integration with Unity Catalog.

```python
@pandas_udf(StringType())
def fake_company(ids: pd.Series) -> pd.Series:
    fake = Faker()
    return pd.Series([fake.company() for _ in range(len(ids))])

# Generate with Spark + Pandas UDFs
customers_df = (
    spark.range(0, N_CUSTOMERS, numPartitions=8)
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

**Alternative (only for <10K rows if user prefers):** Generate with Polars locally and upload:

```python
import polars as pl
from faker import Faker

fake = Faker()

# Generate with Polars
customers_pl = pl.DataFrame({
    "customer_id": [f"CUST-{i:05d}" for i in range(N_CUSTOMERS)],
    "name": [fake.company() for _ in range(N_CUSTOMERS)],
    "tier": np.random.choice(['Free', 'Pro', 'Enterprise'], N_CUSTOMERS, p=[0.6, 0.3, 0.1]).tolist(),
})

# Save locally then upload with: databricks fs cp -r ./output dbfs:/Volumes/{catalog}/{schema}/raw_data/
customers_pl.write_parquet("./output/customers.parquet")
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

## Complete Examples

### Example 1: E-commerce Data (Spark + Faker + Pandas)

Generate e-commerce data with customers and orders tables, with referential integrity and tier-based distributions.

**Full implementation:** See `scripts/generate_ecommerce_data.py` in this skill folder.

**Features:**
- Serverless-first with fallback to classic cluster
- Configurable bad data injection for testing
- Incremental mode for scheduled jobs
- Weighted tier distribution with realistic amounts

**Key configuration options:**

```python
USE_SERVERLESS = True  # Recommended
WRITE_MODE = "overwrite"  # or "append" for incremental
INJECT_BAD_DATA = False  # Set True for data quality testing
```

**Usage:** Copy to your scripts folder, update CATALOG/SCHEMA, run with `python generate_ecommerce_data.py`

### Example 2: Local Development with Polars (Only for <10K rows if user prefers)

Generate synthetic data locally without Spark dependency, then upload to Databricks. Only use for datasets <10K rows if user explicitly prefers local generation.

**Full implementation:** See `scripts/example_polars.py` in this skill folder.

**Features:**
- Fast local generation (no Spark overhead)
- For very small datasets (<10K rows)
- Outputs parquet files to local directory
- Requires manual upload to volumes with `databricks fs cp`


**Usage:** Run locally, then upload: `databricks fs cp -r ./output dbfs:/Volumes/{catalog}/{schema}/raw_data/`

### Example 3: Large-Scale with Faker UDFs

Use Faker with Spark UDFs for realistic text data with parallelism. Best for datasets 100K+ rows.

**Full implementation:** See `scripts/example_faker_udf.py` in this skill folder.

**Features:**
- Serverless-first with fallback to classic cluster
- Parallel execution using Spark UDFs
- Realistic text data (company names, addresses, emails)
- Tier-based amount generation


**Usage:** Copy `example_faker_udf.py` to your scripts folder and customize the UDFs and configuration.


**Execute with Databricks Connect:**
```bash
python scripts/generate_data.py
```

**Execute with classic cluster** using `run_python_file_on_databricks` tool:
- `file_path`: "scripts/generate_data.py"

If it fails, edit the file and re-run with the same `cluster_id` and `context_id`.

### Validate Generated Data

After successful execution, use `get_volume_folder_details` tool to verify the generated data:
- `volume_path`: "my_catalog/my_schema/raw_data/customers"
- `format`: "parquet"
- `table_stat_level`: "SIMPLE"

This returns schema, row counts, and column statistics to confirm the data was written correctly.

## Best Practices

### Execution
1. **Use serverless** (Databricks Connect for dev, jobs for production) - instant start, no cluster wait
2. **Ask for catalog and schema**: Ask for catalog (default to `ai_dev_kit`), ask user for schema name
3. **Present plan before generating**: Show table spec with assumptions, get user approval

### Data Generation
6. **Default to Spark + Faker** for all data generation - scalable, parallel, direct Unity Catalog integration
7. **Use Pandas UDFs for scale** (10k+ rows) - Spark parallelism with Faker
8. **Only use local generation** (<10K rows) if user explicitly prefers it - then upload with `databricks fs cp`
9. **Master tables first**: Generate customers, then orders reference customer_ids
10. **Weighted sampling**: Enterprise customers generate more activity
11. **Distributions**: Log-normal for values, exponential for times, weighted categorical
12. **Time patterns**: Weekday/weekend, holidays, seasonality, event spikes
13. **Row coherence**: Priority affects resolution time affects CSAT
14. **Volume for aggregation**: 10K-50K rows minimum so patterns survive GROUP BY

15. **Context reuse**: Pass `cluster_id` and `context_id` for faster iterations (classic cluster only)

## Related Skills
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** - for managing catalogs, schemas, and volumes where data is stored

### Output
16. **Create infrastructure in script**: Use `CREATE SCHEMA/VOLUME IF NOT EXISTS` - do NOT create catalogs
17. **Assume catalogs exist**: Never auto-create catalogs, only create schema and volume
18. **Choose output format** based on downstream needs (Parquet/JSON/CSV/Delta)
19. **Configuration at top**: All sizes, dates, and paths as variables

## Common Issues

| Issue | Solution |
|-------|----------|
| **"Either base environment or version must be provided"** | Add `"client": "4"` to `spec` in job environments (auto-injected by MCP tool) |
| **"ModuleNotFoundError"** for faker/polars/etc. | See **Execution Options & Installation** section for dependency setup per execution mode |
| **Serverless job fails to start** | Verify workspace has serverless compute enabled; check Unity Catalog permissions |
| **Faker UDF is slow** | Use `pandas_udf` for batched operations; adjust `numPartitions` |
| **Classic cluster startup is slow (3-8 min)** | Prompt user to check if cluster is running and suggest a replacement. |
| **Out of memory with large data** | Increase `partitions` parameter in `spark.range()` |
| **Context corrupted on classic cluster** | Omit `context_id` to create fresh context, reinstall libraries |

---
name: synthetic-data-generation
description: "Generate realistic synthetic data using Spark + Faker or Polars. Supports serverless execution, multiple output formats (Parquet/JSON/CSV/Delta), and scales from thousands to millions of rows. Use for test data, demo datasets, or synthetic tables."
---

# Synthetic Data Generation

Generate realistic, story-driven synthetic data for Databricks using Spark + Faker or Polars.
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
- Date range: last 6 months from today
- Status distribution: 65% delivered, 15% shipped, 10% processing, 5% pending, 5% cancelled

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

- [ ] User confirmed compute preference (serverless vs cluster)
- [ ] Table specification shown and approved
- [ ] Assumptions about distributions surfaced and confirmed
- [ ] Output location confirmed (catalog.schema)
- [ ] Data features selected (skew, joins, bad data, etc.)
- [ ] Row counts appropriate for use case

**Do NOT proceed to code generation until user approves the plan.**

## Execution Options

Choose your execution mode based on your needs:

### Option 1: Databricks Connect with Serverless (Recommended)

Run code locally while Spark operations execute on serverless compute. Best for development and interactive work.

**When user requests data generation:**
1. Confirm serverless is acceptable: "I'll use serverless compute. Is that OK?"
2. If they request classic cluster: "Serverless is recommended for cost efficiency. Are you sure you need a classic cluster?"

**Setup:**
```bash
# Install locally - version depends on your Python version
# For Python 3.10 or 3.11:
pip install "databricks-connect>=15.1,<16.2" faker polars numpy pandas

# For Python 3.12:
pip install "databricks-connect>=16.2" faker polars numpy pandas

# Configure ~/.databrickscfg
[DEFAULT]
host = https://your-workspace.cloud.databricks.com/
serverless_compute_id = auto
auth_type = databricks-cli
```

**In your script:**
```python
from databricks.connect import DatabricksSession

spark = DatabricksSession.builder.serverless(True).getOrCreate()
# Now Spark operations execute on serverless compute
```

**Benefits:**
- Instant start (no cluster spin-up)
- Local debugging with IDE integration
- Dependencies installed locally via pip
- Iterate quickly: edit file, re-run immediately

### Option 2: Serverless Job (Production/Scheduled)

Submit jobs to serverless compute with dependencies managed via the `environments` parameter. Best for production workloads and scheduled jobs.

**Use `create_job` MCP tool with environments:**
- `name`: "generate_synthetic_data"
- `tasks`: [{ task with `environment_key` reference }]
- `environments`: [{
    "environment_key": "datagen_env",
    "spec": {
      "client": "4",
      "dependencies": ["faker", "polars", "numpy", "pandas", "holidays"]
    }
  }]

**Benefits:**
- No local environment needed
- Automatic dependency management
- Scheduled execution support
- Production-ready scaling

### Option 3: Classic Cluster (Fallback)

Execute on a classic all-purpose cluster. Use only if serverless is unavailable or you need specific cluster features.

**Warning:** Classic clusters take 3-8 minutes to start if not already running. Prefer serverless for faster iteration.

**Workflow:**
1. Install dependencies using `execute_databricks_command` tool:
   - `code`: "%pip install faker polars numpy pandas holidays"
   - Save returned `cluster_id` and `context_id`

2. Execute script using `run_python_file_on_databricks` tool:
   - `file_path`: "scripts/generate_data.py"
   - `cluster_id`: "<saved_cluster_id>"
   - `context_id`: "<saved_context_id>"

**When to use:** Only when serverless is not available, or you need specific cluster configurations (GPUs, custom init scripts, etc.)

## Common Libraries

These libraries are useful for generating realistic synthetic data:

- **faker**: Generates realistic names, addresses, emails, companies, dates, etc. (100+ providers)
- **polars**: Fast local DataFrame library for small/medium datasets
- **numpy/pandas**: Statistical distributions and data manipulation
- **holidays**: Provides country-specific holiday calendars for realistic date patterns

**For Databricks Connect:** Install locally with `pip install "databricks-connect>=15.1,<16.2" faker polars numpy pandas holidays` (Python 3.10/3.11) or `pip install "databricks-connect>=16.2" faker polars numpy pandas holidays` (Python 3.12)

**For Serverless Jobs:** Include in `environments.spec.dependencies`: `["faker", "polars", "numpy", "pandas", "holidays"]`

**For Classic Clusters:** Install using `execute_databricks_command` tool:
- `code`: "%pip install faker polars numpy pandas holidays"
- Save the returned `cluster_id` and `context_id` for subsequent calls

## Data Generation Approaches

Choose your approach based on scale and where you need to write data:

### Approach 1: Spark + Faker (Recommended for most cases)

**Best for:** Any dataset size, especially >100K rows, writing to Unity Catalog

Generate data with Pandas + Faker locally, convert to Spark DataFrame for saving to Databricks.

**Key features:**
- Full access to 100+ Faker providers (names, addresses, companies, etc.)
- Use Pandas UDFs for parallelism with large datasets
- Flexible custom logic for complex patterns
- Direct integration with Unity Catalog via Spark

**Example:**
```python
from pyspark.sql import functions as F
from pyspark.sql.functions import pandas_udf
from pyspark.sql.types import StringType
import pandas as pd
from faker import Faker
from databricks.connect import DatabricksSession

spark = DatabricksSession.builder.serverless(True).getOrCreate()

# Define Pandas UDFs for Faker data (batch processing)
@pandas_udf(StringType())
def fake_name(ids: pd.Series) -> pd.Series:
    fake = Faker()
    return pd.Series([fake.name() for _ in range(len(ids))])

@pandas_udf(StringType())
def fake_email(ids: pd.Series) -> pd.Series:
    fake = Faker()
    return pd.Series([fake.email() for _ in range(len(ids))])

# Generate with Spark + Pandas UDFs
customers_df = (
    spark.range(0, N_CUSTOMERS, numPartitions=8)
    .select(
        F.concat(F.lit("CUST-"), F.lpad(F.col("id").cast("string"), 5, "0")).alias("customer_id"),
        fake_name(F.col("id")).alias("name"),
        fake_email(F.col("id")).alias("email"),
        F.when(F.rand() < 0.6, "Free")
         .when(F.rand() < 0.9, "Pro")
         .otherwise("Enterprise").alias("tier"),
    )
)
customers_df.write.mode("overwrite").parquet(f"{VOLUME_PATH}/customers")
```

**Scaling with Pandas UDFs (for large datasets):**
```python
from pyspark.sql import functions as F
from pyspark.sql.functions import pandas_udf
from pyspark.sql.types import StringType
import pandas as pd
from faker import Faker

@pandas_udf(StringType())
def generate_company_batch(ids: pd.Series) -> pd.Series:
    """Batch generate company names - more efficient than row-by-row UDF."""
    fake = Faker()
    return pd.Series([fake.company() for _ in range(len(ids))])

# Generate with Spark parallelism + batch processing
customers_df = (
    spark.range(0, 1_000_000, numPartitions=32)
    .withColumn("name", generate_company_batch(F.col("id")))
)
```

### Approach 2: Polars (For local development)

**Best for:** Quick prototyping, datasets <100K rows, no Spark dependency needed

Generate entirely with Polars + Faker locally, export to parquet files.

**Key features:**
- Fast local generation (no Spark overhead)
- Simple, clean API
- Perfect for testing and prototyping
- Can upload resulting parquet to Databricks volumes

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

### Decision Guide

| Need | Recommended Approach |
|------|---------------------|
| Write to Unity Catalog | **Spark + Faker** |
| Scale to millions of rows | **Spark + Faker** with Pandas UDFs |
| Quick local prototype | **Polars** |
| Realistic text (names/addresses) | **Either** (both use Faker) |
| No Spark dependency | **Polars** |

### Approach 3: Faker with Spark UDFs

**Best for:** Realistic text data (names, addresses, companies), complex custom patterns

Faker provides 100+ data providers for realistic text. Wrap it in Spark UDFs for parallelism.

**Key features:**
- Access to 100+ Faker providers (names, addresses, companies, phone numbers, etc.)
- Custom UDFs for complex conditional logic
- Row-level coherence where attributes correlate logically
- Flexibility for domain-specific patterns

**Example:**
```python
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, DoubleType
from faker import Faker
import numpy as np

# Define Faker UDFs for realistic text
@F.udf(returnType=StringType())
def generate_company():
    return Faker().company()

@F.udf(returnType=StringType())
def generate_address():
    return Faker().address().replace('\n', ', ')

@F.udf(returnType=DoubleType())
def generate_lognormal_amount(tier):
    """Generate amount based on tier using log-normal distribution."""
    np.random.seed(hash(tier) % (2**32))
    if tier == "Enterprise":
        return float(np.random.lognormal(mean=10, sigma=0.8))
    elif tier == "Pro":
        return float(np.random.lognormal(mean=8, sigma=0.7))
    else:
        return float(np.random.lognormal(mean=5, sigma=0.6))

# Generate with Spark parallelism
customers_df = (
    spark.range(0, 1_000_000, numPartitions=32)
    .select(
        F.concat(F.lit("CUST-"), F.lpad(F.col("id").cast("string"), 5, "0")).alias("customer_id"),
        generate_company().alias("name"),
        generate_address().alias("address"),
        F.when(F.rand(42) < 0.6, "Free")
         .when(F.rand(42) < 0.9, "Pro")
         .otherwise("Enterprise").alias("tier")
    )
)

# Add tier-based amounts
customers_df = customers_df.withColumn("arr", generate_lognormal_amount(F.col("tier")))
```

### When to Use Each Approach

| Scenario | Recommended Approach |
|----------|---------------------|
| Generating 1M+ rows | **Spark + Faker with Pandas UDFs** |
| Need realistic names/addresses/emails | **Faker** (Spark or Polars) |
| Writing to Unity Catalog | **Spark + Faker** |
| Complex conditional row logic | **Spark + Faker UDFs** |
| Foreign key with complex weighting | **Spark + Faker** |
| Quick prototyping (small data) | **Polars** |
| No Spark dependency needed | **Polars** |

## Workflow

### Primary: Databricks Connect with Serverless

The recommended workflow for development and interactive data generation:

1. **Configure Databricks Connect** (one-time setup):
   - Install: `pip install "databricks-connect>=15.1,<16.2" faker polars numpy pandas holidays` (Python 3.10/3.11) or `pip install "databricks-connect>=16.2" faker polars numpy pandas holidays` (Python 3.12)
   - Configure `~/.databrickscfg` with `serverless_compute_id = auto`

2. **Write Python script locally** (e.g., `scripts/generate_data.py`):
   ```python
   from databricks.connect import DatabricksSession
   spark = DatabricksSession.builder.serverless(True).getOrCreate()
   # Your data generation code here
   ```

3. **Run locally** - Spark operations execute on serverless compute:
   ```bash
   python scripts/generate_data.py
   ```

4. **Iterate quickly**: Edit file, re-run immediately. No cluster spin-up time.

### Production: Serverless Job

For scheduled or production workloads:

1. **Write Python script locally**

2. **Upload to workspace** using `upload_file` MCP tool:
   - `local_path`: "scripts/generate_data.py"
   - `workspace_path`: "/Workspace/Users/{username}/datagen/{project_name}/generate_data.py"

3. **Create serverless job** using `create_job` MCP tool:
   - `name`: "generate_synthetic_data"
   - `tasks`: [{
       "task_key": "generate",
       "spark_python_task": {
         "python_file": "/Workspace/Users/{username}/datagen/{project_name}/generate_data.py"
       },
       "environment_key": "datagen_env"
     }]
   - `environments`: [{
       "environment_key": "datagen_env",
       "spec": {
         "client": "4",
         "dependencies": ["faker", "polars", "numpy", "pandas", "holidays"]
       }
     }]

4. **Run job** using `run_job_now` MCP tool

5. **Monitor** using `get_run` or `wait_for_run` MCP tools

### Production: DABs Bundle Deployment

For scheduled runs with version control and CI/CD:

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

**Note**: The `environments` block with `client: "4"` enables serverless compute. Dependencies are installed automatically.

### Fallback: Classic Cluster

Only use if serverless is unavailable:

1. **Install dependencies** using `execute_databricks_command` tool:
   - `code`: "%pip install faker polars numpy pandas holidays"
   - Save returned `cluster_id` and `context_id`

2. **Execute script** using `run_python_file_on_databricks` tool:
   - `file_path`: "scripts/generate_data.py"
   - `cluster_id`: "<saved_cluster_id>"
   - `context_id`: "<saved_context_id>"

3. **Iterate**: Edit local file, re-execute with same context (faster, keeps installed libraries)

**Note:** Classic clusters take 3-8 minutes to start. Prefer serverless for faster iteration.

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

### 1. Use Polars for Generation, Spark for Saving

Generate data with Polars (faster than Pandas), convert to Spark for saving:

```python
import polars as pl
import numpy as np
from faker import Faker

fake = Faker()

# Generate with Polars (faster than Pandas)
customers_pl = pl.DataFrame({
    "customer_id": [f"CUST-{i:05d}" for i in range(N_CUSTOMERS)],
    "name": [fake.company() for _ in range(N_CUSTOMERS)],
    "tier": np.random.choice(['Free', 'Pro', 'Enterprise'], N_CUSTOMERS, p=[0.6, 0.3, 0.1]).tolist(),
    "region": np.random.choice(['North', 'South', 'East', 'West'], N_CUSTOMERS, p=[0.4, 0.25, 0.2, 0.15]).tolist(),
    "created_at": [fake.date_between(start_date='-2y', end_date='-6m') for _ in range(N_CUSTOMERS)],
})

# Convert to Spark and save
customers_df = spark.createDataFrame(customers_pl.to_pandas())
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

### Example 2: Local Development with Polars

Generate synthetic data locally without Spark dependency, then upload to Databricks.

**Full implementation:** See `scripts/example_polars.py` in this skill folder.

**Features:**
- Fast local generation (no Spark overhead)
- Perfect for prototyping and testing
- Outputs parquet files to local directory
- Upload to volumes with `databricks fs cp`

**Key pattern:**

```python
import polars as pl
from faker import Faker

# Generate with Polars
customers = pl.DataFrame({
    "customer_id": [f"CUST-{i:05d}" for i in range(N_CUSTOMERS)],
    "name": [fake.name() for _ in range(N_CUSTOMERS)],
    "tier": np.random.choice(["Free", "Pro", "Enterprise"], N_CUSTOMERS, p=[0.6, 0.3, 0.1]),
})

# Save locally
customers.write_parquet("./output/customers.parquet")
```

**Usage:** Run locally, then upload: `databricks fs cp -r ./output dbfs:/Volumes/{catalog}/{schema}/raw_data/`

### Example 3: Large-Scale with Faker UDFs

Use Faker with Spark UDFs for realistic text data with parallelism. Best for datasets 100K+ rows.

**Full implementation:** See `scripts/example_faker_udf.py` in this skill folder.

**Features:**
- Serverless-first with fallback to classic cluster
- Parallel execution using Spark UDFs
- Realistic text data (company names, addresses, emails)
- Tier-based amount generation

**Key pattern - Faker UDFs for realistic data:**

```python
@F.udf(returnType=StringType())
def generate_company():
    return Faker().company()

@F.udf(returnType=DoubleType())
def generate_lognormal_amount(tier):
    np.random.seed(hash(str(tier)) % (2**32))
    if tier == "Enterprise":
        return float(np.random.lognormal(mean=9, sigma=0.8))
    elif tier == "Pro":
        return float(np.random.lognormal(mean=7, sigma=0.7))
    else:
        return float(np.random.lognormal(mean=5, sigma=0.6))

# Use UDFs in Spark operations
customers_df = (
    spark.range(0, N_CUSTOMERS, numPartitions=PARTITIONS)
    .select(
        generate_company().alias("name"),
        # ... other columns
    )
    .withColumn("arr", generate_lognormal_amount(F.col("tier")))
)
```

**Usage:** Copy `example_faker_udf.py` to your scripts folder and customize the UDFs and configuration.

### Example 4: Legacy Approach (Faker + Pandas)

For smaller datasets or when you need complex time-based patterns with row-level logic.
This approach uses Pandas for generation (single-threaded) and Spark for saving.

**Note:** For datasets over 100K rows, prefer Faker UDFs for better performance.

**Full implementation:** See `scripts/example_pandas.py` in this skill folder.

**Key pattern - Pandas generation with referential integrity:**

```python
# Generate master table
customers_pdf = pd.DataFrame({
    "customer_id": [f"CUST-{i:05d}" for i in range(N_CUSTOMERS)],
    "tier": np.random.choice(['Free', 'Pro', 'Enterprise'], N_CUSTOMERS, p=[0.6, 0.3, 0.1]),
})

# Create lookups for foreign keys
customer_ids = customers_pdf["customer_id"].tolist()
customer_tier_map = dict(zip(customers_pdf["customer_id"], customers_pdf["tier"]))
tier_weights = customers_pdf["tier"].map({'Enterprise': 5.0, 'Pro': 2.0, 'Free': 1.0})
customer_weights = (tier_weights / tier_weights.sum()).tolist()

# Generate related table with weighted sampling
orders_data = []
for i in range(N_ORDERS):
    cid = np.random.choice(customer_ids, p=customer_weights)
    tier = customer_tier_map[cid]
    orders_data.append({"order_id": f"ORD-{i:06d}", "customer_id": cid, ...})

# Convert to Spark for saving
spark.createDataFrame(customers_pdf).write.mode("overwrite").parquet(f"{VOLUME_PATH}/customers")
```

**Usage:** Copy `example_pandas.py` to your scripts folder and customize the configuration and patterns.

**To use any example script:**

1. Copy the example file to your scripts directory
2. Update the CONFIGURATION section with your catalog/schema
3. Execute using one of the methods below

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
1. **Use Databricks Connect with serverless** for development - instant start, local debugging
2. **Use serverless jobs** for production - automatic dependency management, scheduling
3. **Prefer serverless over classic** - avoid 3-8 minute cluster spin-up times
4. **Ask for schema**: Default to `ai_dev_kit` catalog, ask user for schema name
5. **Present plan before generating**: Show table spec with assumptions, get user approval

### Data Generation
6. **Use Faker with Pandas UDFs for scale** (1M+ rows) - Spark parallelism
7. **Use Polars for quick prototyping** - fast local generation
8. **Master tables first**: Generate customers, then orders reference customer_ids
9. **Weighted sampling**: Enterprise customers generate more activity
10. **Distributions**: Log-normal for values, exponential for times, weighted categorical
11. **Time patterns**: Weekday/weekend, holidays, seasonality, event spikes
12. **Row coherence**: Priority affects resolution time affects CSAT
13. **Volume for aggregation**: 10K-50K rows minimum so patterns survive GROUP BY
14. **Always use files**: Write to local file, execute, edit if error, re-execute
15. **Context reuse**: Pass `cluster_id` and `context_id` for faster iterations
16. **Libraries**: Install `faker` and `holidays` first; most others are pre-installed

## Related Skills

- **[spark-declarative-pipelines](../spark-declarative-pipelines/SKILL.md)** - for building bronze/silver/gold pipelines on top of generated data
- **[databricks-aibi-dashboards](../databricks-aibi-dashboards/SKILL.md)** - for visualizing the generated data in dashboards
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** - for managing catalogs, schemas, and volumes where data is stored

### Output
14. **Create infrastructure in script**: Use `CREATE SCHEMA/VOLUME IF NOT EXISTS`
15. **Raw data only**: No `total_x`, `sum_x`, `avg_x` fields - SDP pipeline computes those
16. **Choose output format** based on downstream needs (Parquet/JSON/CSV/Delta)
17. **Configuration at top**: All sizes, dates, and paths as variables
18. **Dynamic dates**: Use `datetime.now() - timedelta(days=180)` for last 6 months

## Common Issues

| Issue | Solution |
|-------|----------|
| **"Either base environment or version must be provided"** | Add `"client": "4"` to `spec` in job environments (auto-injected by MCP tool) |
| **"ModuleNotFoundError: No module named 'faker'"** | Add `faker` to dependencies or install locally: `pip install faker` |
| **"ModuleNotFoundError: No module named 'polars'"** | Add `polars` to dependencies or install locally: `pip install polars` |
| **Serverless job fails to start** | Verify workspace has serverless compute enabled; check Unity Catalog permissions |
| **Faker UDF is slow** | Use `pandas_udf` for batched operations; adjust `numPartitions` |
| **Classic cluster startup is slow (3-8 min)** | Switch to Databricks Connect with serverless for instant start |
| **Out of memory with large data** | Increase `partitions` parameter in `spark.range()` |
| **Foreign keys don't match across tables** | Use same random seed across all generators |
| **Delta table write fails** | Ensure `CREATE SCHEMA IF NOT EXISTS` runs before `saveAsTable()` |
| **databricks-connect serverless issues** | Use `pip install "databricks-connect>=15.1,<16.2"` (Python 3.10/3.11) or `pip install "databricks-connect>=16.2"` (Python 3.12) |
| **Databricks Connect connection fails** | Verify `~/.databrickscfg` has correct host and `serverless_compute_id = auto` |
| **Context corrupted on classic cluster** | Omit `context_id` to create fresh context, reinstall libraries |

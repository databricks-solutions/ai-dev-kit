---
name: synthetic-data-generation
description: "Generate realistic synthetic data using Faker and Spark, with non-linear distributions, integrity constraints, and save to Databricks Volumes. Use when creating test data, demo datasets, or synthetic tables."
---

# Synthetic Data Generation

## Overview

Generate realistic, story-driven synthetic data for Databricks using Python with Faker and Spark. The data should have interesting non-linear distributions, maintain referential integrity across tables, and be saved to Unity Catalog volumes.

## When to Use This Skill

Use this skill when:
- Creating test/demo datasets for Databricks
- Generating synthetic data that looks realistic
- Building multi-table datasets with foreign key relationships
- Need data with specific patterns (spikes, drops, seasonality)
- Populating tables for dashboards or ML training

## Workflow

The recommended workflow is:

1. **Write a Python file locally** in the project structure
2. **Execute on Databricks** using `run_python_file_on_databricks(cluster_id, file_path)`

## Key Principles

### 1. Non-Linear, Realistic Distributions

**NEVER use uniform distributions** unless explicitly required. Real data is rarely uniform.

```python
import numpy as np
from faker import Faker

fake = Faker()

# BAD - Uniform distribution (unrealistic)
prices = np.random.uniform(10, 1000, size=1000)

# GOOD - Log-normal distribution (realistic for prices, salaries, etc.)
prices = np.random.lognormal(mean=4.5, sigma=0.8, size=1000)

# GOOD - Power law / Pareto (realistic for popularity, wealth, etc.)
popularity = (np.random.pareto(a=2.5, size=1000) + 1) * 10

# GOOD - Normal with realistic parameters
ages = np.clip(np.random.normal(loc=35, scale=12, size=1000), 18, 80).astype(int)

# GOOD - Weighted categorical (not equal probability)
regions = np.random.choice(
    ['North', 'South', 'East', 'West'],
    size=1000,
    p=[0.40, 0.25, 0.20, 0.15]  # North dominates
)
```

### 2. Time-Based Patterns

Add seasonality, trends, and events to time-series data:

```python
import pandas as pd
from datetime import datetime, timedelta

# Generate date range
start_date = datetime(2024, 1, 1)
end_date = datetime(2024, 12, 31)
dates = pd.date_range(start=start_date, end=end_date, freq='D')

def get_daily_volume(date):
    """Generate realistic daily volume with patterns."""
    base_volume = 500

    # Weekday/weekend effect
    if date.weekday() >= 5:  # Weekend
        base_volume *= 0.6

    # Seasonal pattern (higher in Q4)
    month_multiplier = 1 + 0.1 * (date.month - 6) / 6

    # Add spike event (e.g., Oct 15 incident)
    if datetime(2024, 10, 15) <= date <= datetime(2024, 10, 25):
        base_volume *= 3.0  # 3x spike during incident

    # Add noise
    noise = np.random.normal(1, 0.1)

    return int(base_volume * month_multiplier * noise)
```

### 3. Referential Integrity

Maintain foreign key relationships across tables:

```python
# Generate master table first
n_customers = 1000
customers_df = spark.createDataFrame([
    {
        "customer_id": f"CUST-{i:05d}",
        "name": fake.name(),
        "tier": np.random.choice(['Free', 'Pro', 'Enterprise'], p=[0.60, 0.30, 0.10]),
        "region": np.random.choice(['North', 'South', 'East', 'West'], p=[0.4, 0.25, 0.2, 0.15]),
        "created_at": fake.date_between(start_date='-2y', end_date='-6m')
    }
    for i in range(n_customers)
])

# Get valid customer IDs for orders table
customer_ids = [row.customer_id for row in customers_df.select("customer_id").collect()]
customer_tiers = {row.customer_id: row.tier for row in customers_df.select("customer_id", "tier").collect()}

# Generate orders with valid foreign keys
n_orders = 15000
orders = []
for i in range(n_orders):
    customer_id = np.random.choice(customer_ids)
    tier = customer_tiers[customer_id]

    # Enterprise customers have higher order values
    if tier == 'Enterprise':
        amount = np.random.lognormal(mean=6.0, sigma=0.8)
    elif tier == 'Pro':
        amount = np.random.lognormal(mean=4.5, sigma=0.7)
    else:
        amount = np.random.lognormal(mean=3.5, sigma=0.6)

    orders.append({
        "order_id": f"ORD-{i:06d}",
        "customer_id": customer_id,
        "amount": round(amount, 2),
        "order_date": fake.date_between(start_date='-6m', end_date='today')
    })

orders_df = spark.createDataFrame(orders)
```

### 4. Row Coherence

Ensure each row makes logical sense:

```python
def generate_coherent_ticket(customer_tier, region, date):
    """Generate a support ticket with coherent attributes."""

    # Priority correlates with tier
    if customer_tier == 'Enterprise':
        priority = np.random.choice(['Critical', 'High', 'Medium'], p=[0.3, 0.5, 0.2])
    else:
        priority = np.random.choice(['Critical', 'High', 'Medium', 'Low'], p=[0.05, 0.15, 0.4, 0.4])

    # Resolution time correlates with priority
    if priority == 'Critical':
        resolution_hours = np.random.exponential(scale=4)  # Fast resolution
    elif priority == 'High':
        resolution_hours = np.random.exponential(scale=12)
    else:
        resolution_hours = np.random.exponential(scale=48)

    # CSAT correlates with resolution time
    if resolution_hours < 8:
        csat = np.random.choice([4, 5], p=[0.3, 0.7])
    elif resolution_hours < 24:
        csat = np.random.choice([3, 4, 5], p=[0.2, 0.5, 0.3])
    else:
        csat = np.random.choice([1, 2, 3, 4], p=[0.1, 0.2, 0.4, 0.3])

    return {
        "priority": priority,
        "resolution_hours": round(resolution_hours, 1),
        "csat_score": csat
    }
```

## Complete Example: Multi-Table Dataset

```python
"""
Synthetic Data Generation Script
Generates customers, orders, and support tickets with realistic distributions.
Execute on Databricks cluster, saves to Unity Catalog volume.
"""

import numpy as np
import random
from datetime import datetime, timedelta
from faker import Faker
from pyspark.sql import SparkSession
from pyspark.sql.types import *

# Reproducibility
np.random.seed(42)
random.seed(42)
Faker.seed(42)
fake = Faker()

# Get Spark session (available on Databricks)
spark = SparkSession.builder.getOrCreate()

# Configuration
CATALOG = "my_catalog"
SCHEMA = "my_schema"
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw_data"

N_CUSTOMERS = 2500
N_ORDERS = 25000
N_TICKETS = 8000

# Date range
START_DATE = datetime(2024, 1, 1)
END_DATE = datetime(2024, 12, 31)
INCIDENT_START = datetime(2024, 10, 15)
INCIDENT_END = datetime(2024, 10, 25)

print(f"Generating synthetic data...")
print(f"  Customers: {N_CUSTOMERS:,}")
print(f"  Orders: {N_ORDERS:,}")
print(f"  Tickets: {N_TICKETS:,}")
print("-" * 50)

# ============================================================
# 1. Generate Customers (Master Table)
# ============================================================
print("Generating customers...")

customers = []
for i in range(N_CUSTOMERS):
    tier = np.random.choice(
        ['Free', 'Pro', 'Enterprise'],
        p=[0.60, 0.30, 0.10]
    )
    region = np.random.choice(
        ['North', 'South', 'East', 'West'],
        p=[0.40, 0.25, 0.20, 0.15]
    )

    # ARR correlates with tier
    if tier == 'Enterprise':
        arr = np.random.lognormal(mean=11, sigma=0.5)  # ~$60K median
    elif tier == 'Pro':
        arr = np.random.lognormal(mean=8, sigma=0.6)   # ~$3K median
    else:
        arr = 0

    customers.append({
        "customer_id": f"CUST-{i:05d}",
        "name": fake.company(),
        "email": fake.company_email(),
        "tier": tier,
        "region": region,
        "arr": round(arr, 2),
        "created_at": fake.date_between(start_date='-2y', end_date='-6m')
    })

customers_df = spark.createDataFrame(customers)
print(f"  Created {customers_df.count():,} customers")

# Build lookup for foreign key generation
customer_lookup = {c['customer_id']: c for c in customers}
customer_ids = list(customer_lookup.keys())

# Weight by tier (Enterprise customers generate more activity)
customer_weights = []
for cid in customer_ids:
    tier = customer_lookup[cid]['tier']
    if tier == 'Enterprise':
        customer_weights.append(5.0)
    elif tier == 'Pro':
        customer_weights.append(2.0)
    else:
        customer_weights.append(1.0)
customer_weights = np.array(customer_weights) / sum(customer_weights)

# ============================================================
# 2. Generate Orders
# ============================================================
print("Generating orders...")

orders = []
for i in range(N_ORDERS):
    # Select customer (weighted by tier)
    customer_id = np.random.choice(customer_ids, p=customer_weights)
    customer = customer_lookup[customer_id]
    tier = customer['tier']

    # Order amount correlates with tier
    if tier == 'Enterprise':
        amount = np.random.lognormal(mean=7, sigma=0.8)
    elif tier == 'Pro':
        amount = np.random.lognormal(mean=5, sigma=0.7)
    else:
        amount = np.random.lognormal(mean=3.5, sigma=0.6)

    # Status distribution
    status = np.random.choice(
        ['completed', 'pending', 'cancelled'],
        p=[0.85, 0.10, 0.05]
    )

    orders.append({
        "order_id": f"ORD-{i:06d}",
        "customer_id": customer_id,
        "amount": round(amount, 2),
        "status": status,
        "order_date": fake.date_between(start_date=START_DATE, end_date=END_DATE)
    })

orders_df = spark.createDataFrame(orders)
print(f"  Created {orders_df.count():,} orders")

# ============================================================
# 3. Generate Support Tickets (with incident spike)
# ============================================================
print("Generating support tickets...")

tickets = []
ticket_dates = []

# Distribute tickets across days with incident spike
for day_offset in range((END_DATE - START_DATE).days + 1):
    current_date = START_DATE + timedelta(days=day_offset)

    # Base volume with weekday/weekend pattern
    base_volume = 25
    if current_date.weekday() >= 5:
        base_volume = 15

    # INCIDENT SPIKE: 3x volume during Oct 15-25
    if INCIDENT_START <= current_date <= INCIDENT_END:
        base_volume *= 3.0

    # Add noise
    daily_count = max(1, int(base_volume * np.random.normal(1, 0.15)))
    ticket_dates.extend([current_date] * daily_count)

# Generate ticket details
for i, ticket_date in enumerate(ticket_dates[:N_TICKETS]):
    customer_id = np.random.choice(customer_ids, p=customer_weights)
    customer = customer_lookup[customer_id]
    tier = customer['tier']

    # Category - Authentication spikes during incident
    is_incident_period = INCIDENT_START <= ticket_date <= INCIDENT_END
    if is_incident_period:
        category = np.random.choice(
            ['Authentication', 'Network', 'Billing', 'Account'],
            p=[0.65, 0.15, 0.10, 0.10]  # Auth dominates during incident
        )
    else:
        category = np.random.choice(
            ['Authentication', 'Network', 'Billing', 'Account'],
            p=[0.25, 0.30, 0.25, 0.20]  # Normal distribution
        )

    # Priority correlates with tier
    if tier == 'Enterprise':
        priority = np.random.choice(['Critical', 'High', 'Medium'], p=[0.3, 0.5, 0.2])
    else:
        priority = np.random.choice(['Critical', 'High', 'Medium', 'Low'], p=[0.05, 0.20, 0.45, 0.30])

    # Resolution time correlates with priority
    if priority == 'Critical':
        resolution_hours = np.random.exponential(scale=4)
    elif priority == 'High':
        resolution_hours = np.random.exponential(scale=12)
    else:
        resolution_hours = np.random.exponential(scale=36)

    # CSAT degrades during incident for Auth tickets
    if is_incident_period and category == 'Authentication':
        csat = np.random.choice([1, 2, 3, 4, 5], p=[0.15, 0.25, 0.35, 0.20, 0.05])
    elif resolution_hours < 8:
        csat = np.random.choice([3, 4, 5], p=[0.1, 0.3, 0.6])
    elif resolution_hours < 24:
        csat = np.random.choice([2, 3, 4, 5], p=[0.1, 0.2, 0.4, 0.3])
    else:
        csat = np.random.choice([1, 2, 3, 4], p=[0.1, 0.25, 0.4, 0.25])

    tickets.append({
        "ticket_id": f"TKT-{i:06d}",
        "customer_id": customer_id,
        "category": category,
        "priority": priority,
        "resolution_hours": round(resolution_hours, 1),
        "csat_score": csat,
        "created_at": ticket_date.strftime("%Y-%m-%d %H:%M:%S")
    })

tickets_df = spark.createDataFrame(tickets)
print(f"  Created {tickets_df.count():,} tickets")

# ============================================================
# 4. Save to Volume
# ============================================================
print(f"\nSaving to {VOLUME_PATH}...")

customers_df.write.mode("overwrite").parquet(f"{VOLUME_PATH}/customers")
print(f"  Saved customers")

orders_df.write.mode("overwrite").parquet(f"{VOLUME_PATH}/orders")
print(f"  Saved orders")

tickets_df.write.mode("overwrite").parquet(f"{VOLUME_PATH}/tickets")
print(f"  Saved tickets")

# ============================================================
# 5. Validation Summary
# ============================================================
print("\n" + "=" * 50)
print("VALIDATION SUMMARY")
print("=" * 50)

# Verify incident spike in tickets
tickets_pdf = tickets_df.toPandas()
tickets_pdf['date'] = pd.to_datetime(tickets_pdf['created_at']).dt.date
daily_counts = tickets_pdf.groupby('date').size()

pre_incident = daily_counts[(daily_counts.index < INCIDENT_START.date())].mean()
during_incident = daily_counts[
    (daily_counts.index >= INCIDENT_START.date()) &
    (daily_counts.index <= INCIDENT_END.date())
].mean()

print(f"\nTicket Volume:")
print(f"  Pre-incident avg: {pre_incident:.0f}/day")
print(f"  During incident avg: {during_incident:.0f}/day")
print(f"  Spike multiplier: {during_incident/pre_incident:.1f}x")

# Category breakdown during incident
incident_tickets = tickets_pdf[
    (pd.to_datetime(tickets_pdf['created_at']).dt.date >= INCIDENT_START.date()) &
    (pd.to_datetime(tickets_pdf['created_at']).dt.date <= INCIDENT_END.date())
]
print(f"\nCategory distribution during incident:")
print(incident_tickets['category'].value_counts(normalize=True).to_string())

print("\n" + "=" * 50)
print("DATA GENERATION COMPLETE")
print("=" * 50)
```

## Execution

Save the script locally (e.g., `scripts/generate_data.py`), then execute:

```python
from databricks_mcp_core.compute import run_python_file_on_databricks

result = run_python_file_on_databricks(
    cluster_id="your-cluster-id",
    file_path="scripts/generate_data.py",
    timeout=600
)

if result.success:
    print("Data generation complete!")
    print(result.output)
else:
    print(f"Error: {result.error}")
```

Or execute code directly:

```python
from databricks_mcp_core.compute import execute_databricks_command

result = execute_databricks_command(
    cluster_id="your-cluster-id",
    language="python",
    code=open("scripts/generate_data.py").read(),
    timeout=600
)
```

## Best Practices Summary

1. **Distributions**: Log-normal for values, Pareto for popularity, weighted categorical for segments
2. **Time patterns**: Weekday/weekend effects, seasonality, event spikes/drops
3. **Integrity**: Generate master tables first, use valid foreign keys
4. **Coherence**: Correlated attributes within rows (tier affects value, priority affects resolution time)
5. **Reproducibility**: Set seeds for numpy, random, and Faker
6. **Validation**: Print summary statistics to verify patterns are present
7. **Performance**: Use vectorized operations, generate in batches for large datasets

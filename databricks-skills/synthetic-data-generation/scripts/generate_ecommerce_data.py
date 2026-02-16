"""Generate synthetic e-commerce data with customers and orders tables."""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from faker import Faker
from databricks.connect import DatabricksSession

# =============================================================================
# CONFIGURATION
# =============================================================================
# Compute - Serverless recommended
USE_SERVERLESS = True  # Set to False and provide CLUSTER_ID for classic compute
CLUSTER_ID = None  # Only used if USE_SERVERLESS=False

# Storage
CATALOG = "ai_dev_kit"  # Change to your catalog
SCHEMA = "synthetic_data"  # Change to your schema
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw_data"

# Data sizes
N_CUSTOMERS = 5000
N_ORDERS = 15000

# Date range - last 6 months from today
END_DATE = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
START_DATE = END_DATE - timedelta(days=180)

# Write mode - "overwrite" for one-time, "append" for incremental/scheduled jobs
WRITE_MODE = "overwrite"

# Bad data injection for testing data quality rules
INJECT_BAD_DATA = False  # Set to True to inject bad data
BAD_DATA_CONFIG = {
    "null_rate": 0.02,           # 2% nulls in required fields
    "outlier_rate": 0.01,        # 1% impossible values
    "duplicate_pk_rate": 0.005,  # 0.5% duplicate primary keys
    "orphan_fk_rate": 0.01,      # 1% orphan foreign keys
}

# Reproducibility
SEED = 42

# Tier distribution: Free 60%, Pro 30%, Enterprise 10%
TIER_VALUES = ["Free", "Pro", "Enterprise"]
TIER_WEIGHTS = [0.6, 0.3, 0.1]

# Region distribution
REGION_VALUES = ["North", "South", "East", "West"]
REGION_WEIGHTS = [0.4, 0.25, 0.2, 0.15]

# Order status distribution
STATUS_VALUES = ["pending", "processing", "shipped", "delivered", "cancelled"]
STATUS_WEIGHTS = [0.05, 0.10, 0.15, 0.65, 0.05]

# Weighted order generation by tier (Enterprise generates more orders)
TIER_ORDER_WEIGHTS = {"Enterprise": 5.0, "Pro": 2.0, "Free": 1.0}

# Log-normal parameters for order amounts by tier
TIER_AMOUNT_PARAMS = {
    "Enterprise": {"mean": 7.5, "sigma": 0.8},   # ~$1800 avg, range $500-$8000+
    "Pro": {"mean": 5.5, "sigma": 0.7},          # ~$245 avg, range $50-$1000
    "Free": {"mean": 4.0, "sigma": 0.6},         # ~$55 avg, range $15-$200
}

# =============================================================================
# SETUP
# =============================================================================
np.random.seed(SEED)
Faker.seed(SEED)
fake = Faker()

print("Connecting to Databricks...")
if USE_SERVERLESS:
    spark = DatabricksSession.builder.serverless(True).getOrCreate()
    print("Connected to serverless compute!")
else:
    if not CLUSTER_ID:
        raise ValueError("CLUSTER_ID must be set when USE_SERVERLESS=False")
    spark = DatabricksSession.builder.clusterId(CLUSTER_ID).getOrCreate()
    print(f"Connected to cluster {CLUSTER_ID}!")

# =============================================================================
# CREATE INFRASTRUCTURE
# =============================================================================
print(f"\nCreating schema and volume...")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.raw_data")
print(f"Infrastructure ready: {VOLUME_PATH}")

# =============================================================================
# GENERATE CUSTOMERS TABLE
# =============================================================================
print(f"\nGenerating {N_CUSTOMERS:,} customers...")

customers_pdf = pd.DataFrame({
    "customer_id": [f"CUST-{i:05d}" for i in range(N_CUSTOMERS)],
    "name": [fake.name() for _ in range(N_CUSTOMERS)],
    "email": [fake.email() for _ in range(N_CUSTOMERS)],
    "tier": np.random.choice(TIER_VALUES, N_CUSTOMERS, p=TIER_WEIGHTS),
    "region": np.random.choice(REGION_VALUES, N_CUSTOMERS, p=REGION_WEIGHTS),
    "created_at": [fake.date_between(start_date='-2y', end_date=START_DATE) for _ in range(N_CUSTOMERS)],
})

# Show tier distribution
tier_counts = customers_pdf["tier"].value_counts()
print(f"Tier distribution:")
for tier in TIER_VALUES:
    count = tier_counts.get(tier, 0)
    pct = count / N_CUSTOMERS * 100
    print(f"  {tier}: {count:,} ({pct:.1f}%)")

# =============================================================================
# GENERATE ORDERS TABLE WITH REFERENTIAL INTEGRITY
# =============================================================================
print(f"\nGenerating {N_ORDERS:,} orders with weighted sampling by tier...")

# Create lookups for foreign key generation
customer_ids = customers_pdf["customer_id"].tolist()
customer_tier_map = dict(zip(customers_pdf["customer_id"], customers_pdf["tier"]))

# Weight by tier - Enterprise customers generate more orders
tier_weights_series = customers_pdf["tier"].map(TIER_ORDER_WEIGHTS)
customer_weights = (tier_weights_series / tier_weights_series.sum()).tolist()

# Generate orders with weighted sampling
orders_data = []
for i in range(N_ORDERS):
    cid = np.random.choice(customer_ids, p=customer_weights)
    tier = customer_tier_map[cid]

    # Amount based on tier using log-normal distribution
    params = TIER_AMOUNT_PARAMS[tier]
    amount = np.random.lognormal(mean=params["mean"], sigma=params["sigma"])

    orders_data.append({
        "order_id": f"ORD-{i:06d}",
        "customer_id": cid,
        "amount": round(amount, 2),
        "order_date": fake.date_between(start_date=START_DATE, end_date=END_DATE),
        "status": np.random.choice(STATUS_VALUES, p=STATUS_WEIGHTS),
    })

orders_pdf = pd.DataFrame(orders_data)

# =============================================================================
# INJECT BAD DATA (OPTIONAL)
# =============================================================================
if INJECT_BAD_DATA:
    print(f"\nInjecting bad data for quality testing...")

    # Nulls in required fields
    null_count = int(len(orders_pdf) * BAD_DATA_CONFIG["null_rate"])
    null_indices = np.random.choice(orders_pdf.index, null_count, replace=False)
    orders_pdf.loc[null_indices, "customer_id"] = None
    print(f"  Injected {null_count} null customer_ids")

    # Outliers (impossible values - negative amounts)
    outlier_count = int(len(orders_pdf) * BAD_DATA_CONFIG["outlier_rate"])
    outlier_indices = np.random.choice(orders_pdf.index, outlier_count, replace=False)
    orders_pdf.loc[outlier_indices, "amount"] = -999.99
    print(f"  Injected {outlier_count} negative amounts")

    # Orphan foreign keys
    orphan_count = int(len(orders_pdf) * BAD_DATA_CONFIG["orphan_fk_rate"])
    orphan_indices = np.random.choice(orders_pdf.index, orphan_count, replace=False)
    orders_pdf.loc[orphan_indices, "customer_id"] = "CUST-NONEXISTENT"
    print(f"  Injected {orphan_count} orphan foreign keys")

    # Duplicate primary keys
    dup_count = int(len(orders_pdf) * BAD_DATA_CONFIG["duplicate_pk_rate"])
    dup_indices = np.random.choice(orders_pdf.index[:-dup_count], dup_count, replace=False)
    for i, idx in enumerate(dup_indices):
        orders_pdf.loc[orders_pdf.index[-i-1], "order_id"] = orders_pdf.loc[idx, "order_id"]
    print(f"  Injected {dup_count} duplicate order_ids")

# Show order distribution by customer tier
orders_by_tier = orders_pdf.merge(
    customers_pdf[["customer_id", "tier"]], on="customer_id", how="left"
)["tier"].value_counts()
print(f"\nOrders by customer tier:")
for tier in TIER_VALUES:
    count = orders_by_tier.get(tier, 0)
    pct = count / N_ORDERS * 100
    print(f"  {tier}: {count:,} ({pct:.1f}%)")

# Show amount statistics by tier
print(f"\nAmount statistics by tier:")
for tier in TIER_VALUES:
    tier_orders = orders_pdf.merge(
        customers_pdf[["customer_id", "tier"]], on="customer_id", how="left"
    )
    tier_amounts = tier_orders[tier_orders["tier"] == tier]["amount"]
    if len(tier_amounts) > 0:
        print(f"  {tier}: avg=${tier_amounts.mean():,.2f}, median=${tier_amounts.median():,.2f}, "
              f"min=${tier_amounts.min():,.2f}, max=${tier_amounts.max():,.2f}")

# =============================================================================
# SAVE TO PARQUET
# =============================================================================
print(f"\nSaving to Parquet files in {VOLUME_PATH} (mode={WRITE_MODE})...")

# Convert to Spark DataFrames
customers_df = spark.createDataFrame(customers_pdf)
orders_df = spark.createDataFrame(orders_pdf)

# Save as Parquet
customers_df.write.mode(WRITE_MODE).parquet(f"{VOLUME_PATH}/customers")
print(f"  Saved: {VOLUME_PATH}/customers ({N_CUSTOMERS:,} rows)")

orders_df.write.mode(WRITE_MODE).parquet(f"{VOLUME_PATH}/orders")
print(f"  Saved: {VOLUME_PATH}/orders ({N_ORDERS:,} rows)")

print(f"\nDone! Data saved to {VOLUME_PATH}")
print(f"  - customers: {N_CUSTOMERS:,} rows")
print(f"  - orders: {N_ORDERS:,} rows")
if INJECT_BAD_DATA:
    print(f"  - Bad data injected: nulls, outliers, orphan FKs, duplicate PKs")

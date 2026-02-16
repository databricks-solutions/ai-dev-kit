"""Generate synthetic data with Polars (local, no Spark dependency).

This approach is best for:
- Quick prototyping and testing
- Datasets under 100K rows
- Local development without Databricks connection
- Generating parquet files to upload to volumes later
"""
import polars as pl
from faker import Faker
from datetime import datetime, timedelta
import numpy as np
import os

# =============================================================================
# CONFIGURATION
# =============================================================================
# Output
OUTPUT_PATH = "./output"  # Local directory for parquet files

# Data sizes
N_CUSTOMERS = 5000
N_ORDERS = 15000

# Date range - last 6 months from today
END_DATE = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
START_DATE = END_DATE - timedelta(days=180)

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
    "Enterprise": {"mean": 7.5, "sigma": 0.8},
    "Pro": {"mean": 5.5, "sigma": 0.7},
    "Free": {"mean": 4.0, "sigma": 0.6},
}

# =============================================================================
# SETUP
# =============================================================================
np.random.seed(SEED)
Faker.seed(SEED)
fake = Faker()

# Create output directory
os.makedirs(OUTPUT_PATH, exist_ok=True)

# =============================================================================
# GENERATE CUSTOMERS TABLE
# =============================================================================
print(f"Generating {N_CUSTOMERS:,} customers...")

customers = pl.DataFrame({
    "customer_id": [f"CUST-{i:05d}" for i in range(N_CUSTOMERS)],
    "name": [fake.name() for _ in range(N_CUSTOMERS)],
    "email": [fake.email() for _ in range(N_CUSTOMERS)],
    "tier": np.random.choice(TIER_VALUES, N_CUSTOMERS, p=TIER_WEIGHTS).tolist(),
    "region": np.random.choice(REGION_VALUES, N_CUSTOMERS, p=REGION_WEIGHTS).tolist(),
    "created_at": [fake.date_between(start_date='-2y', end_date=START_DATE) for _ in range(N_CUSTOMERS)],
})

# Show tier distribution
print("Tier distribution:")
tier_counts = customers.group_by("tier").len().sort("tier")
for row in tier_counts.iter_rows(named=True):
    pct = row["len"] / N_CUSTOMERS * 100
    print(f"  {row['tier']}: {row['len']:,} ({pct:.1f}%)")

# =============================================================================
# GENERATE ORDERS TABLE WITH REFERENTIAL INTEGRITY
# =============================================================================
print(f"\nGenerating {N_ORDERS:,} orders with weighted sampling by tier...")

# Create lookups for foreign key generation
customer_ids = customers["customer_id"].to_list()
customer_tier_map = dict(zip(customers["customer_id"], customers["tier"]))

# Weight by tier - Enterprise customers generate more orders
tier_weights_list = [TIER_ORDER_WEIGHTS[t] for t in customers["tier"].to_list()]
total_weight = sum(tier_weights_list)
customer_weights = [w / total_weight for w in tier_weights_list]

# Generate orders with weighted sampling
orders_data = {
    "order_id": [],
    "customer_id": [],
    "amount": [],
    "order_date": [],
    "status": [],
}

for i in range(N_ORDERS):
    cid = np.random.choice(customer_ids, p=customer_weights)
    tier = customer_tier_map[cid]

    # Amount based on tier using log-normal distribution
    params = TIER_AMOUNT_PARAMS[tier]
    amount = np.random.lognormal(mean=params["mean"], sigma=params["sigma"])

    orders_data["order_id"].append(f"ORD-{i:06d}")
    orders_data["customer_id"].append(cid)
    orders_data["amount"].append(round(amount, 2))
    orders_data["order_date"].append(fake.date_between(start_date=START_DATE, end_date=END_DATE))
    orders_data["status"].append(np.random.choice(STATUS_VALUES, p=STATUS_WEIGHTS))

orders = pl.DataFrame(orders_data)

# Show order distribution by customer tier
orders_with_tier = orders.join(
    customers.select(["customer_id", "tier"]),
    on="customer_id"
)
orders_by_tier = orders_with_tier.group_by("tier").len().sort("tier")
print("\nOrders by customer tier:")
for row in orders_by_tier.iter_rows(named=True):
    pct = row["len"] / N_ORDERS * 100
    print(f"  {row['tier']}: {row['len']:,} ({pct:.1f}%)")

# Show amount statistics by tier
print("\nAmount statistics by tier:")
for tier in TIER_VALUES:
    tier_amounts = orders_with_tier.filter(pl.col("tier") == tier)["amount"]
    if len(tier_amounts) > 0:
        print(f"  {tier}: avg=${tier_amounts.mean():,.2f}, median=${tier_amounts.median():,.2f}, "
              f"min=${tier_amounts.min():,.2f}, max=${tier_amounts.max():,.2f}")

# =============================================================================
# SAVE TO PARQUET (LOCAL)
# =============================================================================
print(f"\nSaving to Parquet files in {OUTPUT_PATH}...")

customers.write_parquet(f"{OUTPUT_PATH}/customers.parquet")
print(f"  Saved: {OUTPUT_PATH}/customers.parquet ({N_CUSTOMERS:,} rows)")

orders.write_parquet(f"{OUTPUT_PATH}/orders.parquet")
print(f"  Saved: {OUTPUT_PATH}/orders.parquet ({N_ORDERS:,} rows)")

print(f"\nDone! Data saved locally to {OUTPUT_PATH}")
print(f"  - customers.parquet: {N_CUSTOMERS:,} rows")
print(f"  - orders.parquet: {N_ORDERS:,} rows")
print("\nTo upload to Databricks, use: databricks fs cp -r ./output dbfs:/Volumes/...")

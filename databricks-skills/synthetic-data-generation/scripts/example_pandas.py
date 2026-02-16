"""Generate synthetic data using Faker + Pandas (legacy approach for complex patterns)."""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from faker import Faker
import holidays
from pyspark.sql import SparkSession

# For Databricks Connect, replace with:
# from databricks.connect import DatabricksSession
# spark = DatabricksSession.builder.getOrCreate()

spark = SparkSession.builder.getOrCreate()

# =============================================================================
# CONFIGURATION
# =============================================================================
CATALOG = "my_catalog"
SCHEMA = "my_schema"
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw_data"

N_CUSTOMERS = 2500
N_ORDERS = 25000
N_TICKETS = 8000

END_DATE = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
START_DATE = END_DATE - timedelta(days=180)
INCIDENT_END = END_DATE - timedelta(days=21)
INCIDENT_START = INCIDENT_END - timedelta(days=10)
US_HOLIDAYS = holidays.US(years=[START_DATE.year, END_DATE.year])

SEED = 42
np.random.seed(SEED)
Faker.seed(SEED)
fake = Faker()

# =============================================================================
# CREATE INFRASTRUCTURE
# =============================================================================
spark.sql(f"CREATE CATALOG IF NOT EXISTS {CATALOG}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.raw_data")

# =============================================================================
# GENERATE CUSTOMERS
# =============================================================================
print(f"Generating {N_CUSTOMERS:,} customers...")

customers_pdf = pd.DataFrame({
    "customer_id": [f"CUST-{i:05d}" for i in range(N_CUSTOMERS)],
    "name": [fake.company() for _ in range(N_CUSTOMERS)],
    "tier": np.random.choice(['Free', 'Pro', 'Enterprise'], N_CUSTOMERS, p=[0.6, 0.3, 0.1]),
    "region": np.random.choice(['North', 'South', 'East', 'West'], N_CUSTOMERS, p=[0.4, 0.25, 0.2, 0.15]),
})

customers_pdf["arr"] = customers_pdf["tier"].apply(
    lambda t: round(np.random.lognormal(11, 0.5), 2) if t == 'Enterprise'
              else round(np.random.lognormal(8, 0.6), 2) if t == 'Pro' else 0
)

# Lookups for foreign keys
customer_ids = customers_pdf["customer_id"].tolist()
customer_tier_map = dict(zip(customers_pdf["customer_id"], customers_pdf["tier"]))
tier_weights = customers_pdf["tier"].map({'Enterprise': 5.0, 'Pro': 2.0, 'Free': 1.0})
customer_weights = (tier_weights / tier_weights.sum()).tolist()

# =============================================================================
# GENERATE ORDERS
# =============================================================================
print(f"Generating {N_ORDERS:,} orders...")

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

# =============================================================================
# SAVE TO VOLUME
# =============================================================================
print(f"Saving to {VOLUME_PATH}...")

spark.createDataFrame(customers_pdf).write.mode("overwrite").parquet(f"{VOLUME_PATH}/customers")
spark.createDataFrame(orders_pdf).write.mode("overwrite").parquet(f"{VOLUME_PATH}/orders")

print("Done!")

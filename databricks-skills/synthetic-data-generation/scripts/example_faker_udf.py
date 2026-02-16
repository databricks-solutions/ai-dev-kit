"""Generate synthetic data using Faker with Spark UDFs for parallelism.

This approach is best for:
- Large datasets (100K+ rows) that need Spark parallelism
- Generating realistic text data with Faker providers
- Writing directly to Unity Catalog volumes
- Complex conditional logic in data generation
"""
from pyspark.sql import functions as F
from pyspark.sql.window import Window
from pyspark.sql.types import StringType, DoubleType, DateType
from faker import Faker
import numpy as np
from datetime import datetime, timedelta
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

# Data sizes - this example is designed for larger datasets
N_CUSTOMERS = 100_000
N_ORDERS = 500_000
PARTITIONS = 16  # Adjust based on data size

# Date range - last 6 months from today
END_DATE = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
START_DATE = END_DATE - timedelta(days=180)

# Reproducibility
SEED = 42

# =============================================================================
# SETUP
# =============================================================================
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
# DEFINE FAKER UDFs
# =============================================================================
@F.udf(returnType=StringType())
def generate_company():
    """Generate realistic company name."""
    return Faker().company()

@F.udf(returnType=StringType())
def generate_address():
    """Generate realistic address."""
    return Faker().address().replace('\n', ', ')

@F.udf(returnType=StringType())
def generate_email(company_name):
    """Generate email based on company name."""
    if company_name:
        domain = company_name.lower().replace(" ", "").replace(",", "")[:15]
        return f"contact@{domain}.com"
    return "unknown@example.com"

@F.udf(returnType=DoubleType())
def generate_lognormal_amount(tier):
    """Generate amount based on tier using log-normal distribution."""
    np.random.seed(hash(str(tier)) % (2**32))
    if tier == "Enterprise":
        return float(np.random.lognormal(mean=9, sigma=0.8))
    elif tier == "Pro":
        return float(np.random.lognormal(mean=7, sigma=0.7))
    else:
        return float(np.random.lognormal(mean=5, sigma=0.6))

# =============================================================================
# CREATE INFRASTRUCTURE
# =============================================================================
print("Creating infrastructure...")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.raw_data")
print(f"Infrastructure ready: {VOLUME_PATH}")

# =============================================================================
# GENERATE CUSTOMERS
# =============================================================================
print(f"Generating {N_CUSTOMERS:,} customers...")

customers_df = (
    spark.range(0, N_CUSTOMERS, numPartitions=PARTITIONS)
    .select(
        F.concat(F.lit("CUST-"), F.lpad(F.col("id").cast("string"), 5, "0")).alias("customer_id"),
        generate_company().alias("name"),
        generate_address().alias("address"),
        F.when(F.rand(SEED) < 0.6, "Free")
         .when(F.rand(SEED) < 0.9, "Pro")
         .otherwise("Enterprise").alias("tier"),
        F.when(F.rand(SEED) < 0.4, "North")
         .when(F.rand(SEED) < 0.65, "South")
         .when(F.rand(SEED) < 0.85, "East")
         .otherwise("West").alias("region")
    )
)

# Add tier-based ARR and email
customers_df = (
    customers_df
    .withColumn("arr", generate_lognormal_amount(F.col("tier")))
    .withColumn("email", generate_email(F.col("name")))
)

customers_df.write.mode("overwrite").parquet(f"{VOLUME_PATH}/customers")
print(f"  Saved customers to {VOLUME_PATH}/customers")

# =============================================================================
# GENERATE ORDERS
# =============================================================================
print(f"Generating {N_ORDERS:,} orders...")

# Get customer IDs for foreign key
customer_lookup = customers_df.select("customer_id", "tier").cache()

orders_df = (
    spark.range(0, N_ORDERS, numPartitions=PARTITIONS)
    .select(
        F.concat(F.lit("ORD-"), F.lpad(F.col("id").cast("string"), 6, "0")).alias("order_id"),
        # Generate customer_idx for FK join (random selection from customer range)
        (F.abs(F.hash(F.col("id"), F.lit(SEED))) % N_CUSTOMERS).alias("customer_idx"),
        F.when(F.rand(SEED) < 0.85, "completed")
         .when(F.rand(SEED) < 0.95, "pending")
         .otherwise("cancelled").alias("status"),
        F.date_add(F.lit(START_DATE.date()),
                   (F.rand(SEED) * 180).cast("int")).alias("order_date")
    )
)

# Add customer_idx to lookup for join
customer_lookup_with_idx = customer_lookup.withColumn(
    "customer_idx",
    (F.row_number().over(Window.orderBy(F.monotonically_increasing_id())) - 1).cast("int")
)

# Join to get customer_id and tier as foreign key
orders_with_fk = (
    orders_df
    .join(customer_lookup_with_idx, on="customer_idx", how="left")
    .drop("customer_idx")
)

# Add tier-based amount
orders_with_fk = orders_with_fk.withColumn("amount", generate_lognormal_amount(F.col("tier")))

orders_with_fk.drop("tier").write.mode("overwrite").parquet(f"{VOLUME_PATH}/orders")
print(f"  Saved orders to {VOLUME_PATH}/orders")

customer_lookup.unpersist()
print("Done!")

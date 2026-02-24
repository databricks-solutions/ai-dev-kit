"""Generate synthetic data using Faker with Spark UDFs for parallelism.

This approach is best for:
- Large datasets (100K+ rows) that need Spark parallelism
- Generating realistic text data with Faker providers
- Writing directly to Unity Catalog volumes
- Complex conditional logic in data generation

This script automatically detects the environment and uses:
- DatabricksEnv with auto-dependencies if databricks-connect >= 16.4 and running locally
- Standard session creation if running on Databricks Runtime or older databricks-connect
"""
import sys
import os
from pyspark.sql import functions as F
from pyspark.sql.window import Window
from pyspark.sql.types import StringType, DoubleType
import numpy as np
from datetime import datetime, timedelta

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
# SETUP - Environment Detection and Session Creation
# =============================================================================

# Detect if running on Databricks Runtime vs locally with Databricks Connect
def is_databricks_runtime():
    """Check if running on Databricks Runtime (notebook/job) vs locally."""
    return "DATABRICKS_RUNTIME_VERSION" in os.environ

# Get databricks-connect version if available
def get_databricks_connect_version():
    """Get databricks-connect version as (major, minor) tuple or None."""
    try:
        import databricks.connect
        version_str = databricks.connect.__version__
        parts = version_str.split('.')
        return (int(parts[0]), int(parts[1]))
    except (ImportError, AttributeError, ValueError, IndexError):
        return None

# Determine session creation strategy
on_runtime = is_databricks_runtime()
db_version = get_databricks_connect_version()

print("=" * 80)
print("ENVIRONMENT DETECTION")
print("=" * 80)
print(f"Running on Databricks Runtime: {on_runtime}")
if db_version:
    print(f"databricks-connect version: {db_version[0]}.{db_version[1]}")
else:
    print("databricks-connect: not available")

# Use DatabricksEnv with auto-dependencies if:
# - Running locally (not on Databricks Runtime)
# - databricks-connect >= 16.4
use_auto_dependencies = (not on_runtime) and db_version and db_version >= (16, 4)

if use_auto_dependencies:
    print("✓ Using DatabricksEnv with managed dependencies")
    print("=" * 80)
    from databricks.connect import DatabricksSession, DatabricksEnv

    # Pass dependencies as simple package name strings
    env = DatabricksEnv().withDependencies("faker", "pandas", "numpy", "holidays")

    if USE_SERVERLESS:
        spark = DatabricksSession.builder.withEnvironment(env).serverless(True).getOrCreate()
        print("✓ Connected to serverless compute with managed dependencies!")
    else:
        if not CLUSTER_ID:
            raise ValueError("CLUSTER_ID must be set when USE_SERVERLESS=False")
        spark = DatabricksSession.builder.withEnvironment(env).clusterId(CLUSTER_ID).getOrCreate()
        print(f"✓ Connected to cluster {CLUSTER_ID} with managed dependencies!")
else:
    print("⚠ Using standard session (dependencies must be pre-installed)")
    print("=" * 80)

    # Try to import libraries that will be used in UDFs
    print("\nChecking UDF dependencies...")
    missing_deps = []

    try:
        from faker import Faker
        print("  ✓ faker")
    except ImportError:
        missing_deps.append("faker")
        print("  ✗ faker - NOT INSTALLED")

    try:
        import pandas as pd
        print("  ✓ pandas")
    except ImportError:
        missing_deps.append("pandas")
        print("  ✗ pandas - NOT INSTALLED")

    if missing_deps:
        print("\n" + "=" * 80)
        print("⚠ WARNING: Missing dependencies for UDFs")
        print("=" * 80)
        print(f"Missing libraries: {', '.join(missing_deps)}")
        print("\nThese libraries are required in UDFs and must be installed:")

        if on_runtime:
            print("\n→ SOLUTION: Install on the cluster or job:")
            print("   - For interactive cluster: Run %pip install faker pandas numpy holidays")
            print("   - For job: Add to job libraries or use init script")
        else:
            print("\n→ SOLUTION: Use one of these approaches:")
            print("   1. Upgrade databricks-connect to >= 16.4 (enables auto-dependencies)")
            print("   2. Create a job with environment settings in the task definition")
            print("   3. Use a classic cluster with libraries pre-installed")

        print("=" * 80)
        sys.exit(1)

    print("\n✓ All UDF dependencies available")
    print("=" * 80)

    # Create standard session
    from databricks.connect import DatabricksSession

    if USE_SERVERLESS:
        spark = DatabricksSession.builder.serverless(True).getOrCreate()
        print("✓ Connected to serverless compute")
    else:
        if not CLUSTER_ID:
            raise ValueError("CLUSTER_ID must be set when USE_SERVERLESS=False")
        spark = DatabricksSession.builder.clusterId(CLUSTER_ID).getOrCreate()
        print(f"✓ Connected to cluster {CLUSTER_ID}")

# Import Faker for UDF definitions (already checked above)
from faker import Faker

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

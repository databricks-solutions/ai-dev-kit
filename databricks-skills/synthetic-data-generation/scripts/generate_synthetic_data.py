"""Generate synthetic data using Spark + Faker + Pandas UDFs.

This is the recommended approach for ALL data generation tasks:
- Scales from thousands to millions of rows
- Parallel execution via Spark
- Direct write to Unity Catalog
- Works with serverless and classic compute

Auto-detects environment and uses:
- DatabricksEnv with managed dependencies if databricks-connect >= 16.4 (local)
- Standard session if running on Databricks Runtime or older databricks-connect
"""
import sys
import os
from pyspark.sql import functions as F
from pyspark.sql.window import Window
from pyspark.sql.types import StringType, DoubleType, StructType, StructField, IntegerType
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# =============================================================================
# CONFIGURATION
# =============================================================================
# Compute - Serverless strongly recommended
USE_SERVERLESS = True  # Set to False and provide CLUSTER_ID for classic compute
CLUSTER_ID = None  # Only used if USE_SERVERLESS=False

# Storage - Update these for your environment
CATALOG = "ai_dev_kit"  # Change to your catalog
SCHEMA = "synthetic_data"  # Change to your schema
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw_data"

# Data sizes
N_CUSTOMERS = 10_000
N_ORDERS = 50_000
PARTITIONS = 16  # Adjust: 8 for <100K, 32 for 1M+

# Date range - last 6 months from today
END_DATE = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
START_DATE = END_DATE - timedelta(days=180)

# Write mode - "overwrite" for one-time, "append" for incremental
WRITE_MODE = "overwrite"

# Bad data injection for testing data quality rules
INJECT_BAD_DATA = False  # Set to True to inject bad data
BAD_DATA_CONFIG = {
    "null_rate": 0.02,           # 2% nulls in required fields
    "outlier_rate": 0.01,        # 1% impossible values
    "orphan_fk_rate": 0.01,      # 1% orphan foreign keys
}

# Reproducibility
SEED = 42

# Tier distribution: Free 60%, Pro 30%, Enterprise 10%
TIER_PROBS = [0.6, 0.3, 0.1]

# Region distribution
REGION_PROBS = [0.4, 0.25, 0.2, 0.15]

# =============================================================================
# ENVIRONMENT DETECTION AND SESSION CREATION
# =============================================================================

def is_databricks_runtime():
    """Check if running on Databricks Runtime vs locally."""
    return "DATABRICKS_RUNTIME_VERSION" in os.environ

def get_databricks_connect_version():
    """Get databricks-connect version as (major, minor) tuple or None."""
    try:
        import databricks.connect
        version_str = databricks.connect.__version__
        parts = version_str.split('.')
        return (int(parts[0]), int(parts[1]))
    except (ImportError, AttributeError, ValueError, IndexError):
        return None

# Detect environment
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

# Use DatabricksEnv with managed dependencies if:
# - Running locally (not on Databricks Runtime)
# - databricks-connect >= 16.4
use_managed_deps = (not on_runtime) and db_version and db_version >= (16, 4)

if use_managed_deps:
    print("Using DatabricksEnv with managed dependencies")
    print("=" * 80)
    from databricks.connect import DatabricksSession, DatabricksEnv

    env = DatabricksEnv().withDependencies("faker", "pandas", "numpy", "holidays")

    if USE_SERVERLESS:
        spark = DatabricksSession.builder.withEnvironment(env).serverless(True).getOrCreate()
        print("Connected to serverless compute with managed dependencies!")
    else:
        if not CLUSTER_ID:
            raise ValueError("CLUSTER_ID must be set when USE_SERVERLESS=False")
        spark = DatabricksSession.builder.withEnvironment(env).clusterId(CLUSTER_ID).getOrCreate()
        print(f"Connected to cluster <cluster_id> with managed dependencies!")
else:
    print("Using standard session (dependencies must be pre-installed)")
    print("=" * 80)

    # Check that UDF dependencies are available
    print("\nChecking UDF dependencies...")
    missing_deps = []

    try:
        from faker import Faker
        print("  faker: OK")
    except ImportError:
        missing_deps.append("faker")
        print("  faker: MISSING")

    try:
        import pandas as pd
        print("  pandas: OK")
    except ImportError:
        missing_deps.append("pandas")
        print("  pandas: MISSING")

    if missing_deps:
        print("\n" + "=" * 80)
        print("ERROR: Missing dependencies for UDFs")
        print("=" * 80)
        print(f"Missing: {', '.join(missing_deps)}")
        if on_runtime:
            print("\nSolution: Run install using Databricks CLI: Use Databricks CLI to install libraries: databricks libraries install --json '{"cluster_id": "<cluster_id>", "libraries": [{"pypi": {"package": "faker"}}, {"pypi": {"package": "holidays"}}]}'")
        else:
            print("\nSolution: Upgrade to databricks-connect >= 16.4 for managed deps")
            print("          Or create a job with environment settings")
        print("=" * 80)
        sys.exit(1)

    print("\nAll dependencies available")
    print("=" * 80)

    from databricks.connect import DatabricksSession

    if USE_SERVERLESS:
        spark = DatabricksSession.builder.serverless(True).getOrCreate()
        print("Connected to serverless compute")
    else:
        if not CLUSTER_ID:
            raise ValueError("CLUSTER_ID must be set when USE_SERVERLESS=False")
        spark = DatabricksSession.builder.clusterId(CLUSTER_ID).getOrCreate()
        print(f"Connected to cluster <cluster_id>")

# Import Faker for UDF definitions
from faker import Faker

# =============================================================================
# DEFINE PANDAS UDFs FOR FAKER DATA
# =============================================================================

@F.pandas_udf(StringType())
def fake_name(ids: pd.Series) -> pd.Series:
    """Generate realistic person names."""
    fake = Faker()
    Faker.seed(SEED)
    return pd.Series([fake.name() for _ in range(len(ids))])

@F.pandas_udf(StringType())
def fake_company(ids: pd.Series) -> pd.Series:
    """Generate realistic company names."""
    fake = Faker()
    Faker.seed(SEED)
    return pd.Series([fake.company() for _ in range(len(ids))])

@F.pandas_udf(StringType())
def fake_address(ids: pd.Series) -> pd.Series:
    """Generate realistic addresses."""
    fake = Faker()
    Faker.seed(SEED)
    return pd.Series([fake.address().replace('\n', ', ') for _ in range(len(ids))])

@F.pandas_udf(StringType())
def fake_email(names: pd.Series) -> pd.Series:
    """Generate email based on name."""
    emails = []
    for name in names:
        if name:
            domain = name.lower().replace(" ", ".").replace(",", "")[:20]
            emails.append(f"{domain}@example.com")
        else:
            emails.append("unknown@example.com")
    return pd.Series(emails)

@F.pandas_udf(DoubleType())
def generate_lognormal_amount(tiers: pd.Series) -> pd.Series:
    """Generate amount based on tier using log-normal distribution."""
    np.random.seed(SEED)
    amounts = []
    for tier in tiers:
        if tier == "Enterprise":
            amounts.append(float(np.random.lognormal(mean=7.5, sigma=0.8)))  # ~$1800 avg
        elif tier == "Pro":
            amounts.append(float(np.random.lognormal(mean=5.5, sigma=0.7)))  # ~$245 avg
        else:
            amounts.append(float(np.random.lognormal(mean=4.0, sigma=0.6)))  # ~$55 avg
    return pd.Series(amounts)

# =============================================================================
# CREATE INFRASTRUCTURE
# =============================================================================
print("\nCreating infrastructure...")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.raw_data")
print(f"Infrastructure ready: {VOLUME_PATH}")

# =============================================================================
# GENERATE CUSTOMERS (Master Table)
# =============================================================================
print(f"\nGenerating {N_CUSTOMERS:,} customers...")

customers_df = (
    spark.range(0, N_CUSTOMERS, numPartitions=PARTITIONS)
    .select(
        F.concat(F.lit("CUST-"), F.lpad(F.col("id").cast("string"), 5, "0")).alias("customer_id"),
        fake_name(F.col("id")).alias("name"),
        fake_company(F.col("id")).alias("company"),
        fake_address(F.col("id")).alias("address"),
        # Tier distribution: Free 60%, Pro 30%, Enterprise 10%
        F.when(F.rand(SEED) < TIER_PROBS[0], "Free")
         .when(F.rand(SEED) < TIER_PROBS[0] + TIER_PROBS[1], "Pro")
         .otherwise("Enterprise").alias("tier"),
        # Region distribution
        F.when(F.rand(SEED) < REGION_PROBS[0], "North")
         .when(F.rand(SEED) < REGION_PROBS[0] + REGION_PROBS[1], "South")
         .when(F.rand(SEED) < REGION_PROBS[0] + REGION_PROBS[1] + REGION_PROBS[2], "East")
         .otherwise("West").alias("region"),
        # Created date (within last 2 years before start date)
        F.date_sub(F.lit(START_DATE.date()), (F.rand(SEED) * 730).cast("int")).alias("created_at"),
    )
)

# Add tier-based ARR and email
customers_df = (
    customers_df
    .withColumn("arr", F.round(generate_lognormal_amount(F.col("tier")), 2))
    .withColumn("email", fake_email(F.col("name")))
)

# Save customers
customers_df.write.mode(WRITE_MODE).parquet(f"{VOLUME_PATH}/customers")
print(f"  Saved customers to {VOLUME_PATH}/customers")

# Show tier distribution
print("\n  Tier distribution:")
customers_df.groupBy("tier").count().orderBy("tier").show()

# =============================================================================
# GENERATE ORDERS (Child Table with Referential Integrity)
# =============================================================================
print(f"\nGenerating {N_ORDERS:,} orders with referential integrity...")

# Cache customer lookup for FK generation
customer_lookup = customers_df.select("customer_id", "tier").cache()

# Generate orders base
orders_df = (
    spark.range(0, N_ORDERS, numPartitions=PARTITIONS)
    .select(
        F.concat(F.lit("ORD-"), F.lpad(F.col("id").cast("string"), 6, "0")).alias("order_id"),
        # Generate customer_idx for FK join (hash-based distribution)
        (F.abs(F.hash(F.col("id"), F.lit(SEED))) % N_CUSTOMERS).alias("customer_idx"),
        # Order status
        F.when(F.rand(SEED) < 0.65, "delivered")
         .when(F.rand(SEED) < 0.80, "shipped")
         .when(F.rand(SEED) < 0.90, "processing")
         .when(F.rand(SEED) < 0.95, "pending")
         .otherwise("cancelled").alias("status"),
        # Order date within date range
        F.date_add(F.lit(START_DATE.date()), (F.rand(SEED) * 180).cast("int")).alias("order_date"),
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
orders_with_fk = orders_with_fk.withColumn(
    "amount",
    F.round(generate_lognormal_amount(F.col("tier")), 2)
)

# =============================================================================
# INJECT BAD DATA (OPTIONAL)
# =============================================================================
if INJECT_BAD_DATA:
    print("\nInjecting bad data for quality testing...")

    # Calculate counts
    null_count = int(N_ORDERS * BAD_DATA_CONFIG["null_rate"])
    outlier_count = int(N_ORDERS * BAD_DATA_CONFIG["outlier_rate"])
    orphan_count = int(N_ORDERS * BAD_DATA_CONFIG["orphan_fk_rate"])

    # Add bad data flags
    orders_with_fk = orders_with_fk.withColumn(
        "row_num",
        F.row_number().over(Window.orderBy(F.monotonically_increasing_id()))
    )

    # Inject nulls in customer_id for first null_count rows
    orders_with_fk = orders_with_fk.withColumn(
        "customer_id",
        F.when(F.col("row_num") <= null_count, None).otherwise(F.col("customer_id"))
    )

    # Inject negative amounts for next outlier_count rows
    orders_with_fk = orders_with_fk.withColumn(
        "amount",
        F.when(
            (F.col("row_num") > null_count) & (F.col("row_num") <= null_count + outlier_count),
            F.lit(-999.99)
        ).otherwise(F.col("amount"))
    )

    # Inject orphan FKs for next orphan_count rows
    orders_with_fk = orders_with_fk.withColumn(
        "customer_id",
        F.when(
            (F.col("row_num") > null_count + outlier_count) &
            (F.col("row_num") <= null_count + outlier_count + orphan_count),
            F.lit("CUST-NONEXISTENT")
        ).otherwise(F.col("customer_id"))
    )

    orders_with_fk = orders_with_fk.drop("row_num")

    print(f"  Injected {null_count} null customer_ids")
    print(f"  Injected {outlier_count} negative amounts")
    print(f"  Injected {orphan_count} orphan foreign keys")

# Drop tier column (not needed in final output)
orders_final = orders_with_fk.drop("tier")

# Save orders
orders_final.write.mode(WRITE_MODE).parquet(f"{VOLUME_PATH}/orders")
print(f"  Saved orders to {VOLUME_PATH}/orders")

# Show status distribution
print("\n  Status distribution:")
orders_final.groupBy("status").count().orderBy("status").show()

# =============================================================================
# CLEANUP AND SUMMARY
# =============================================================================
customer_lookup.unpersist()

print("\n" + "=" * 80)
print("GENERATION COMPLETE")
print("=" * 80)
print(f"Catalog: {CATALOG}")
print(f"Schema: {SCHEMA}")
print(f"Volume: {VOLUME_PATH}")
print(f"\nGenerated data:")
print(f"  - customers: {N_CUSTOMERS:,} rows")
print(f"  - orders: {N_ORDERS:,} rows")
if INJECT_BAD_DATA:
    print(f"  - Bad data injected: nulls, outliers, orphan FKs")
print(f"\nDate range: {START_DATE.date()} to {END_DATE.date()}")
print("=" * 80)

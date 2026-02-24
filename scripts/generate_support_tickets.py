"""Generate large-scale synthetic support ticket data.

This script automatically detects the environment and uses:
- DatabricksEnv with auto-dependencies if databricks-connect >= 16.4 and running locally
- Standard session creation if running on Databricks Runtime or older databricks-connect
"""
import sys
import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pyspark.sql import functions as F
from pyspark.sql.functions import pandas_udf
from pyspark.sql.types import StringType, DoubleType, IntegerType

# =============================================================================
# CONFIGURATION - Edit these values
# =============================================================================
CATALOG = "dustin_vannoy_catalog"
SCHEMA = "sdg_test_large_delta"

# Data sizes
N_CUSTOMERS = 100000
N_TICKETS = 500000

# Date ranges
END_DATE = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
CUSTOMER_START_DATE = END_DATE - timedelta(days=1095)  # Last 3 years
TICKET_START_DATE = END_DATE - timedelta(days=180)  # Last 6 months

# Reproducibility
SEED = 42

# Spark partitions for parallelism (adjust based on scale)
CUSTOMER_PARTITIONS = 32
TICKET_PARTITIONS = 64

# =============================================================================
# SETUP - Environment Detection and Session Creation
# =============================================================================
np.random.seed(SEED)

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

print("=" * 80)
print("SYNTHETIC DATA GENERATION - SUPPORT TICKETS")
print("=" * 80)
print(f"Catalog: {CATALOG}")
print(f"Schema: {SCHEMA}")
print(f"Customers: {N_CUSTOMERS:,}")
print(f"Tickets: {N_TICKETS:,}")
print(f"Customer partitions: {CUSTOMER_PARTITIONS}")
print(f"Ticket partitions: {TICKET_PARTITIONS}")
print("=" * 80)

# Determine session creation strategy
on_runtime = is_databricks_runtime()
db_version = get_databricks_connect_version()

print("\nENVIRONMENT DETECTION")
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
    print("✓ Using DatabricksEnv with auto-dependencies")
    print("=" * 80)
    from databricks.connect import DatabricksSession, DatabricksEnv

    env = DatabricksEnv().withAutoDependencies(upload_local=True, use_index=True)
    spark = (
        DatabricksSession.builder
        .withEnvironment(env)
        .config("spark.databricks.sql.externalUDF.env.enabled", "true")
        .config("spark.databricks.sql.udf.routineEnvironmentSettings.enabled", "true")
        .serverless(True)
        .getOrCreate()
    )
    print("✓ Connected to serverless compute with auto-dependencies!")
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

    spark = (
        DatabricksSession.builder
        .config("spark.databricks.sql.externalUDF.env.enabled", "true")
        .config("spark.databricks.sql.udf.routineEnvironmentSettings.enabled", "true")
        .serverless(True)
        .getOrCreate()
    )
    print("✓ Connected to serverless compute")

# Import Faker for later use (already checked above)
from faker import Faker
Faker.seed(SEED)
fake = Faker()

# =============================================================================
# CREATE INFRASTRUCTURE
# =============================================================================
print("\n[1/4] Creating infrastructure...")
# Note: Assume catalog exists - do NOT create it
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
print(f"✓ Schema created/verified")

# =============================================================================
# DEFINE PANDAS UDFs FOR FAKER DATA
# =============================================================================
print("\n[2/4] Defining data generation UDFs...")

@pandas_udf(StringType())
def fake_company(ids: pd.Series) -> pd.Series:
    """Generate realistic company names."""
    fake = Faker()
    Faker.seed(SEED)
    return pd.Series([fake.company() for _ in range(len(ids))])

@pandas_udf(DoubleType())
def generate_arr(tiers: pd.Series) -> pd.Series:
    """Generate ARR based on tier using log-normal distribution."""
    np.random.seed(SEED)
    result = []
    for tier in tiers:
        if tier == "Enterprise":
            # Mean ~$500K
            arr = np.random.lognormal(mean=13, sigma=0.8)
        elif tier == "Pro":
            # Mean ~$50K
            arr = np.random.lognormal(mean=11, sigma=0.7)
        else:  # Free
            arr = 0.0
        result.append(round(arr, 2))
    return pd.Series(result)

@pandas_udf(StringType())
def generate_priority(tiers: pd.Series) -> pd.Series:
    """Generate priority based on tier."""
    np.random.seed(SEED)
    result = []
    for tier in tiers:
        if tier == "Enterprise":
            priority = np.random.choice(['Critical', 'High', 'Medium'], p=[0.3, 0.5, 0.2])
        elif tier == "Pro":
            priority = np.random.choice(['Critical', 'High', 'Medium', 'Low'], p=[0.1, 0.3, 0.45, 0.15])
        else:  # Free
            priority = np.random.choice(['Critical', 'High', 'Medium', 'Low'], p=[0.02, 0.15, 0.40, 0.43])
        result.append(priority)
    return pd.Series(result)

@pandas_udf(DoubleType())
def generate_resolution_hours(priorities: pd.Series) -> pd.Series:
    """Generate resolution hours based on priority using exponential distribution."""
    np.random.seed(SEED)
    result = []
    scale_map = {'Critical': 4, 'High': 12, 'Medium': 36, 'Low': 72}
    for priority in priorities:
        scale = scale_map.get(priority, 24)
        hours = np.random.exponential(scale=scale)
        result.append(round(hours, 2))
    return pd.Series(result)

@pandas_udf(IntegerType())
def generate_csat(resolution_hours: pd.Series) -> pd.Series:
    """Generate CSAT score based on resolution time."""
    np.random.seed(SEED)
    result = []
    for hours in resolution_hours:
        if hours < 4:
            csat = np.random.choice([4, 5], p=[0.3, 0.7])
        elif hours < 24:
            csat = np.random.choice([3, 4, 5], p=[0.2, 0.5, 0.3])
        elif hours < 72:
            csat = np.random.choice([2, 3, 4], p=[0.3, 0.5, 0.2])
        else:
            csat = np.random.choice([1, 2, 3], p=[0.4, 0.4, 0.2])
        result.append(int(csat))
    return pd.Series(result)

print("✓ UDFs defined")

# =============================================================================
# GENERATE CUSTOMERS TABLE
# =============================================================================
print(f"\n[3/4] Generating {N_CUSTOMERS:,} customers...")

# Generate base customer data with Spark
customers_df = (
    spark.range(0, N_CUSTOMERS, numPartitions=CUSTOMER_PARTITIONS)
    .select(
        # customer_id: CUST-00001 format
        F.concat(F.lit("CUST-"), F.lpad(F.col("id").cast("string"), 6, "0")).alias("customer_id"),

        # tier: Enterprise 10%, Pro 30%, Free 60%
        F.when(F.rand(SEED) < 0.10, "Enterprise")
         .when(F.rand(SEED + 1) < 0.40, "Pro")  # 0.10 + 0.30 = 0.40
         .otherwise("Free").alias("tier"),

        # region: North 35%, South 25%, East 25%, West 15%
        F.when(F.rand(SEED + 2) < 0.35, "North")
         .when(F.rand(SEED + 3) < 0.60, "South")  # 0.35 + 0.25 = 0.60
         .when(F.rand(SEED + 4) < 0.85, "East")   # 0.60 + 0.25 = 0.85
         .otherwise("West").alias("region"),

        # signup_date: random date in last 3 years
        (F.lit(CUSTOMER_START_DATE.timestamp()) +
         (F.rand(SEED + 5) * (END_DATE.timestamp() - CUSTOMER_START_DATE.timestamp()))
        ).cast("timestamp").cast("date").alias("signup_date"),
    )
)

# Add company_name and arr using UDFs
customers_df = (
    customers_df
    .withColumn("company_name", fake_company(F.col("customer_id")))
    .withColumn("arr", generate_arr(F.col("tier")))
)

# Reorder columns
customers_df = customers_df.select(
    "customer_id", "company_name", "tier", "arr", "region", "signup_date"
)

# Save to Delta table
print(f"Writing customers to {CATALOG}.{SCHEMA}.customers...")
customers_df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{CATALOG}.{SCHEMA}.customers")

# Get customer count
customer_count = spark.table(f"{CATALOG}.{SCHEMA}.customers").count()
print(f"✓ Created customers table with {customer_count:,} rows")

# =============================================================================
# GENERATE TICKETS TABLE
# =============================================================================
print(f"\n[4/4] Generating {N_TICKETS:,} tickets...")

# Create a broadcast map of customer_id -> tier for weighted sampling
customers_sample = spark.table(f"{CATALOG}.{SCHEMA}.customers").select("customer_id", "tier").collect()
customer_ids = [row.customer_id for row in customers_sample]
customer_tiers = {row.customer_id: row.tier for row in customers_sample}

# Create weights: Enterprise 5x, Pro 2x, Free 1x
tier_weights = {"Enterprise": 5.0, "Pro": 2.0, "Free": 1.0}
weights = [tier_weights[customer_tiers[cid]] for cid in customer_ids]
weights = np.array(weights) / np.sum(weights)

# Sample customer_ids with replacement based on weights
np.random.seed(SEED)
sampled_customer_ids = np.random.choice(customer_ids, size=N_TICKETS, replace=True, p=weights)

# Create tickets DataFrame from sampled customer_ids
tickets_pdf = pd.DataFrame({
    "ticket_id": [f"TKT-{i:07d}" for i in range(N_TICKETS)],
    "customer_id": sampled_customer_ids,
})

# Convert to Spark DataFrame
tickets_df = spark.createDataFrame(tickets_pdf, schema="ticket_id STRING, customer_id STRING")

# Repartition for better parallelism
tickets_df = tickets_df.repartition(TICKET_PARTITIONS)

# Join with customers to get tier for priority generation
tickets_df = tickets_df.join(
    spark.table(f"{CATALOG}.{SCHEMA}.customers").select("customer_id", "tier"),
    on="customer_id",
    how="left"
)

# Add priority, resolution_hours, csat_score, created_at
tickets_df = (
    tickets_df
    .withColumn("priority", generate_priority(F.col("tier")))
    .withColumn("resolution_hours", generate_resolution_hours(F.col("priority")))
    .withColumn("csat_score", generate_csat(F.col("resolution_hours")))
    .withColumn(
        "created_at",
        (F.lit(TICKET_START_DATE.timestamp()) +
         (F.rand(SEED + 10) * (END_DATE.timestamp() - TICKET_START_DATE.timestamp()))
        ).cast("timestamp")
    )
)

# Drop the tier column (only needed for generation)
tickets_df = tickets_df.select(
    "ticket_id", "customer_id", "priority", "resolution_hours", "csat_score", "created_at"
)

# Save to Delta table
print(f"Writing tickets to {CATALOG}.{SCHEMA}.tickets...")
tickets_df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{CATALOG}.{SCHEMA}.tickets")

# Get ticket count
ticket_count = spark.table(f"{CATALOG}.{SCHEMA}.tickets").count()
print(f"✓ Created tickets table with {ticket_count:,} rows")

# =============================================================================
# VALIDATION
# =============================================================================
print("\n" + "=" * 80)
print("GENERATION COMPLETE")
print("=" * 80)

# Show sample data
print("\nCustomers sample:")
spark.table(f"{CATALOG}.{SCHEMA}.customers").show(5, truncate=False)

print("\nTickets sample:")
spark.table(f"{CATALOG}.{SCHEMA}.tickets").show(5, truncate=False)

# Show statistics
print("\nCustomer tier distribution:")
spark.table(f"{CATALOG}.{SCHEMA}.customers").groupBy("tier").count().orderBy("tier").show()

print("\nTicket priority distribution:")
spark.table(f"{CATALOG}.{SCHEMA}.tickets").groupBy("priority").count().orderBy("priority").show()

print("\n" + "=" * 80)
print(f"✓ Tables created:")
print(f"  - {CATALOG}.{SCHEMA}.customers ({customer_count:,} rows)")
print(f"  - {CATALOG}.{SCHEMA}.tickets ({ticket_count:,} rows)")
print("=" * 80)

# Examples

End-to-end examples showing how to compose synthetic data generation for common demo scenarios.

## Quick Local Retail Dataset (Polars + Mimesis) — Tier 1

Generate a linked customers + transactions dataset locally with zero Spark overhead. Ideal for quick prototyping, unit tests, or offline work.

```python
import random
from datetime import date, datetime, timedelta
import polars as pl
from mimesis import Generic
from mimesis.locales import Locale

random.seed(42)
g = Generic(locale=Locale.EN, seed=42)

# 1. Customers (10K rows, ~2 seconds)
n_customers = 10_000
signup_start = date(2020, 1, 1)
signup_range = (date(2024, 12, 31) - signup_start).days

customers = pl.DataFrame({
    "customer_id": list(range(1_000_000, 1_000_000 + n_customers)),
    "first_name": [g.person.first_name() for _ in range(n_customers)],
    "last_name": [g.person.last_name() for _ in range(n_customers)],
    "email": [g.person.email() for _ in range(n_customers)],
    "city": [g.address.city() for _ in range(n_customers)],
    "state": random.choices(
        ["NY", "CA", "IL", "TX", "AZ", "PA", "FL", "OH"], k=n_customers),
    "loyalty_tier": random.choices(
        ["Bronze", "Silver", "Gold", "Platinum"],
        weights=[50, 30, 15, 5], k=n_customers),
    "signup_date": [signup_start + timedelta(days=random.randint(0, signup_range))
                    for _ in range(n_customers)],
})

# 2. Transactions linked to customers (50K rows)
n_txns = 50_000
ts_start = datetime(2024, 1, 1)
ts_range = int((datetime(2024, 12, 31, 23, 59, 59) - ts_start).total_seconds())

transactions = pl.DataFrame({
    "txn_id": list(range(1, n_txns + 1)),
    "customer_id": [random.randint(1_000_000, 1_000_000 + n_customers - 1) for _ in range(n_txns)],
    "amount": [round(random.gammavariate(2.0, 2.0) * 50, 2) for _ in range(n_txns)],
    "txn_timestamp": [ts_start + timedelta(seconds=random.randint(0, ts_range)) for _ in range(n_txns)],
    "payment_method": random.choices(
        ["Credit Card", "Debit Card", "Cash", "Digital Wallet"],
        weights=[40, 25, 20, 15], k=n_txns),
})

# 3. Write locally
import os
os.makedirs("output/retail", exist_ok=True)
customers.write_parquet("output/retail/customers.parquet")
transactions.write_parquet("output/retail/transactions.parquet")
print(f"Customers: {customers.shape}, Transactions: {transactions.shape}")
```

## Quick Retail to Unity Catalog (Polars + Connect Bridge) — Tier 1 + UC

Generate a small dataset with Polars + Mimesis and write directly to Unity Catalog via the Connect bridge. Use this when the user asks to "save to Unity Catalog" for datasets <100K rows.

```python
import random
from datetime import date, timedelta
import polars as pl
from mimesis import Generic
from mimesis.locales import Locale
from databricks.connect import DatabricksSession

random.seed(42)
g = Generic(locale=Locale.EN, seed=42)
rows = 10_000

# Generate with Polars + Mimesis (same as Tier 1)
customers = pl.DataFrame({
    "customer_id": list(range(1_000_000, 1_000_000 + rows)),
    "first_name": [g.person.first_name() for _ in range(rows)],
    "last_name": [g.person.last_name() for _ in range(rows)],
    "email": [g.person.email() for _ in range(rows)],
    "loyalty_tier": random.choices(
        ["Bronze", "Silver", "Gold", "Platinum"],
        weights=[50, 30, 15, 5], k=rows),
    "signup_date": [date(2020, 1, 1) + timedelta(days=random.randint(0, 1826))
                    for _ in range(rows)],
})

# Write to UC via Connect bridge
CATALOG, SCHEMA = "my_catalog", "retail"
spark = DatabricksSession.builder.serverless().getOrCreate()
existing = [row.databaseName for row in spark.sql(f"SHOW SCHEMAS IN {CATALOG}").collect()]
if SCHEMA not in existing:
    spark.sql(f"CREATE SCHEMA {CATALOG}.{SCHEMA}")

spark_df = spark.createDataFrame(customers.to_pandas())
spark_df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{CATALOG}.{SCHEMA}.customers")
print(f"Wrote {spark.table(f'{CATALOG}.{SCHEMA}.customers').count():,} rows")
spark.stop()
```

Run: `uv run --with polars --with mimesis --with "databricks-connect>=16.4,<17.0" script.py`

## Local Healthcare for Notebook Import (Polars) — Tier 1

Generate patients and encounters locally, then load into a Databricks notebook via file upload or Volumes.

```python
import random
from datetime import date, datetime, timedelta
import polars as pl
from mimesis import Generic
from mimesis.locales import Locale

random.seed(42)
g = Generic(locale=Locale.EN, seed=42)

# Patients (5K rows)
n_patients = 5_000
dob_start = date(1940, 1, 1)
dob_range = (date(2005, 1, 1) - dob_start).days

patients = pl.DataFrame({
    "patient_id": list(range(1_000_000, 1_000_000 + n_patients)),
    "mrn": [f"MRN{random.randint(1000000000, 9999999999)}" for _ in range(n_patients)],
    "first_name": [g.person.first_name() for _ in range(n_patients)],
    "last_name": [g.person.last_name() for _ in range(n_patients)],
    "date_of_birth": [dob_start + timedelta(days=random.randint(0, dob_range)) for _ in range(n_patients)],
    "gender": random.choices(["M", "F", "Other"], weights=[49, 49, 2], k=n_patients),
    "insurance_id": [f"INS-{random.randint(10000000, 99999999)}" for _ in range(n_patients)],
})

# Encounters linked to patients (15K rows)
n_enc = 15_000
ts_start = datetime(2024, 1, 1)
ts_range = int((datetime(2024, 12, 31, 23, 59, 59) - ts_start).total_seconds())

encounters = pl.DataFrame({
    "encounter_id": list(range(1, n_enc + 1)),
    "patient_id": [random.randint(1_000_000, 1_000_000 + n_patients - 1) for _ in range(n_enc)],
    "encounter_type": random.choices(
        ["Outpatient", "Inpatient", "Emergency", "Telehealth"],
        weights=[50, 25, 15, 10], k=n_enc),
    "admit_datetime": [ts_start + timedelta(seconds=random.randint(0, ts_range)) for _ in range(n_enc)],
    "chief_complaint": random.choices(
        ["Chest pain", "Headache", "Back pain", "Fever", "Follow-up",
         "Routine checkup", "Fatigue", "Cough"], k=n_enc),
})

import os
os.makedirs("output/healthcare", exist_ok=True)
patients.write_parquet("output/healthcare/patients.parquet")
encounters.write_parquet("output/healthcare/encounters.parquet")
print(f"Patients: {patients.shape}, Encounters: {encounters.shape}")
```

## Retail via Connect (dbldatagen Catalyst-Safe) — Tier 2 Primary

Generate retail data from a local IDE via Databricks Connect using dbldatagen's Catalyst-safe features. This is the **primary Tier 2 pattern** — dbldatagen's declarative API works over Connect + serverless for all standard features. See [dbldatagen-connect-patterns.md](dbldatagen-connect-patterns.md) for the full validated reference.

```python
from databricks.connect import DatabricksSession
import dbldatagen as dg

spark = DatabricksSession.builder.serverless().getOrCreate()

FIRST_NAMES = ["James","Mary","Robert","Patricia","John","Jennifer","Michael","Linda","David","Elizabeth"]
LAST_NAMES = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis","Rodriguez","Martinez"]

# 1. Customers — values= for PII, expr= for derived columns
customer_count = 50_000
customers = (
    dg.DataGenerator(spark, rows=customer_count, partitions=8, randomSeed=42)
    .withColumn("customer_id", "long", minValue=1_000_000, uniqueValues=customer_count)
    .withColumn("first_name", "string", values=FIRST_NAMES, random=True)
    .withColumn("last_name", "string", values=LAST_NAMES, random=True)
    .withColumn("email", "string",
        expr="lower(concat(first_name, '.', last_name, cast(id % 1000 as string), '@example.com'))",
        baseColumns=["first_name", "last_name"])
    .withColumn("loyalty_tier", "string",
                values=["Bronze", "Silver", "Gold", "Platinum"],
                weights=[50, 30, 15, 5])
    .withColumn("signup_date", "date", begin="2020-01-01", end="2024-12-31", random=True)
    .build()
)

# 2. Transactions — all Catalyst-safe features
transactions = (
    dg.DataGenerator(spark, rows=500_000, partitions=16, randomSeed=43)
    .withColumn("txn_id", "long", minValue=1, uniqueValues=500_000)
    .withColumn("customer_id", "long", minValue=1_000_000, maxValue=1_000_000 + customer_count - 1)
    .withColumn("amount", "decimal(10,2)", minValue=1.99, maxValue=999.99, random=True)
    .withColumn("txn_date", "timestamp", begin="2023-01-01", end="2024-12-31", random=True)
    .withColumn("channel", "string",
                values=["web", "mobile", "store", "phone"],
                weights=[35, 30, 25, 10])
    .build()
)

# 3. Apply constraint workaround (filter instead of .withConstraint)
transactions = transactions.filter("amount > 0")

# 4. Write to Unity Catalog
customers.write.format("delta").mode("overwrite").saveAsTable("demo.retail.customers")
transactions.write.format("delta").mode("overwrite").saveAsTable("demo.retail.transactions")
```

## Retail to Unity Catalog (Polars + Connect) — Tier 2 Alternative

Alternative Tier 2 pattern: generate data locally with Polars + Mimesis, then write to Unity Catalog Delta tables via Databricks Connect. Use this when you need full Mimesis PII or Python statistical distributions that dbldatagen can't run over Connect. For the primary Tier 2 pattern, see the dbldatagen example above.

```python
# Tier 2 Alternative: Polars generates locally, Connect writes to UC
import random
from datetime import date, timedelta
import polars as pl
from mimesis import Generic
from mimesis.locales import Locale
from databricks.connect import DatabricksSession

random.seed(42)
g = Generic(locale=Locale.EN, seed=42)
rows = 100_000

customers = pl.DataFrame({
    "customer_id": list(range(1_000_000, 1_000_000 + rows)),
    "first_name": [g.person.first_name() for _ in range(rows)],
    "last_name": [g.person.last_name() for _ in range(rows)],
    "lifetime_value": [round(random.gammavariate(2.0, 2.0) * 2500, 2) for _ in range(rows)],
})

spark = DatabricksSession.builder.serverless().getOrCreate()
spark_df = spark.createDataFrame(customers.to_pandas())
spark_df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("catalog.schema.customers")
```

Run command: `uv run --with polars --with mimesis --with "databricks-connect>=16.4,<17.0" script.py`

## Customer 360 Demo (Databricks Notebook)

A complete retail Customer 360 dataset with linked customers and transactions, written to Unity Catalog. Uses dbldatagen + Mimesis for full-featured generation — **run this in a Databricks notebook** where the libraries are installed on the cluster.

```python
import dbldatagen as dg
from dbldatagen import MimesisTextFactory
from mimesis import Person, Address
from mimesis.locales import Locale

# Define mimesisText helper (copy into your notebook)
_person = Person(Locale.EN)
_address = Address(Locale.EN)
_PROVIDERS = {"person": _person, "address": _address}

def mimesisText(spec: str) -> MimesisTextFactory:
    provider_name, method_name = spec.split(".", 1)
    provider = _PROVIDERS[provider_name]
    return MimesisTextFactory(getattr(provider, method_name))

# 1. Generate customers with realistic PII
customer_count = 500_000
customers = (
    dg.DataGenerator(spark, rows=customer_count, partitions=50, randomSeed=42)
    .withColumn("customer_id", "long", minValue=1, uniqueValues=customer_count)
    .withColumn("first_name", "string", text=mimesisText("person.first_name"))
    .withColumn("last_name", "string", text=mimesisText("person.last_name"))
    .withColumn("email", "string", text=mimesisText("person.email"))
    .withColumn("phone", "string", text=mimesisText("person.telephone"))
    .withColumn("address", "string", text=mimesisText("address.address"))
    .withColumn("city", "string", text=mimesisText("address.city"))
    .withColumn("state", "string", text=mimesisText("address.state"))
    .withColumn("loyalty_tier", "string",
                values=["Bronze", "Silver", "Gold", "Platinum"],
                weights=[50, 30, 15, 5])
    .withColumn("signup_date", "date", begin="2018-01-01", end="2024-12-31", random=True)
    .build()
)
customers.write.format("delta").mode("overwrite").saveAsTable("demo.retail.customers")

# 2. Generate transactions linked to customers
transactions = (
    dg.DataGenerator(spark, rows=5_000_000, partitions=50, randomSeed=43)
    .withColumn("txn_id", "long", minValue=1, uniqueValues=5_000_000)
    .withColumn("customer_id", "long", minValue=1, maxValue=customer_count)
    .withColumn("product_id", "long", minValue=1, maxValue=10_000)
    .withColumn("amount", "decimal(10,2)", minValue=1.99, maxValue=999.99, random=True)
    .withColumn("txn_date", "timestamp", begin="2023-01-01", end="2024-12-31", random=True)
    .withColumn("channel", "string",
                values=["web", "mobile", "store", "phone"],
                weights=[35, 30, 25, 10])
    .build()
)
transactions.write.format("delta").mode("overwrite").saveAsTable("demo.retail.transactions")
```

## Retail via Databricks Connect (Pure PySpark)

Generate retail customers, transactions, and products from a local IDE via Databricks Connect. Uses pure PySpark functions — no UDFs, no dbldatagen — so it runs on serverless compute without library installs.

```python
from databricks.connect import DatabricksSession
from pyspark.sql import functions as F

spark = DatabricksSession.builder.serverless().getOrCreate()

# --- Lookup arrays for random selection ---
first_names = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer",
    "Michael", "Linda", "David", "Elizabeth", "William", "Barbara",
    "Richard", "Susan", "Joseph", "Jessica", "Thomas", "Sarah",
    "Christopher", "Karen",
]
last_names = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia",
    "Miller", "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez",
    "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore",
    "Jackson", "Martin",
]
states = ["NY", "CA", "IL", "TX", "AZ", "PA", "FL", "OH", "NC", "GA"]

first_arr = F.array(*[F.lit(n) for n in first_names])
last_arr = F.array(*[F.lit(n) for n in last_names])
state_arr = F.array(*[F.lit(s) for s in states])

# 1. Customers (500 rows for quick validation — scale up by changing spark.range)
customer_count = 500
customers = (
    spark.range(customer_count)
    .withColumn("customer_id", F.col("id") + 1_000_000)
    .withColumn("first_name", first_arr[F.floor(F.rand() * len(first_names)).cast("int")])
    .withColumn("last_name", last_arr[F.floor(F.rand() * len(last_names)).cast("int")])
    .withColumn(
        "email",
        F.concat(
            F.lower(F.col("first_name")), F.lit("."),
            F.lower(F.col("last_name")),
            F.floor(F.rand() * 1000).cast("string"),
            F.lit("@example.com"),
        ),
    )
    .withColumn("state", state_arr[F.floor(F.rand() * len(states)).cast("int")])
    .withColumn("signup_date",
                F.date_add(F.lit("2020-01-01"), F.floor(F.rand() * 1826).cast("int")))
    # Weighted loyalty tier: Bronze 50%, Silver 30%, Gold 15%, Platinum 5%
    .withColumn("_r", F.rand() * 100)
    .withColumn("loyalty_tier",
                F.when(F.col("_r") < 50, "Bronze")
                .when(F.col("_r") < 80, "Silver")
                .when(F.col("_r") < 95, "Gold")
                .otherwise("Platinum"))
    .withColumn("lifetime_value", F.round(F.rand() * 50000, 2).cast("decimal(12,2)"))
    .withColumn("is_active", F.rand() < 0.85)
    .withColumn("email", F.when(F.rand() < 0.02, F.lit(None)).otherwise(F.col("email")))
    .drop("id", "_r")
)
customers.show(5, truncate=False)

# 2. Transactions linked to customers (2000 rows)
payment_methods = ["Credit Card", "Debit Card", "Cash", "Digital Wallet", "Gift Card"]
payment_arr = F.array(*[F.lit(p) for p in payment_methods])

transactions = (
    spark.range(2000)
    .withColumn("txn_id", F.col("id") + 1)
    .withColumn("customer_id",
                F.floor(F.rand() * customer_count).cast("long") + 1_000_000)
    .withColumn("store_id", F.floor(F.rand() * 50).cast("int") + 100)
    .withColumn("txn_timestamp",
                (F.lit("2024-01-01 00:00:00").cast("timestamp").cast("long")
                 + F.floor(F.rand() * 31536000)).cast("timestamp"))
    .withColumn("_r", F.rand() * 100)
    .withColumn("payment_method",
                F.when(F.col("_r") < 40, "Credit Card")
                .when(F.col("_r") < 65, "Debit Card")
                .when(F.col("_r") < 80, "Cash")
                .when(F.col("_r") < 95, "Digital Wallet")
                .otherwise("Gift Card"))
    .withColumn("subtotal", F.round(F.rand() * 490 + 10, 2).cast("decimal(12,2)"))
    .withColumn("discount_amount",
                F.round(F.col("subtotal") * F.rand() * 0.3, 2).cast("decimal(10,2)"))
    .withColumn("tax_amount",
                F.round((F.col("subtotal") - F.col("discount_amount")) * 0.08, 2)
                .cast("decimal(10,2)"))
    .withColumn("total_amount",
                (F.col("subtotal") - F.col("discount_amount") + F.col("tax_amount"))
                .cast("decimal(12,2)"))
    .withColumn("items_count", F.floor(F.rand() * 19).cast("int") + 1)
    .drop("id", "_r")
)
transactions.show(5, truncate=False)

# 3. Write to Unity Catalog
customers.write.format("delta").mode("overwrite").saveAsTable("demo.retail.customers")
transactions.write.format("delta").mode("overwrite").saveAsTable("demo.retail.transactions")
```

## IoT Streaming Demo

A streaming sensor data pipeline with batch generation for historical backfill and streaming for real-time.

```python
import dbldatagen as dg

# Generate streaming sensor data
sensor_schema = (
    dg.DataGenerator(spark, rows=10_000_000, partitions=100, randomSeed=44)
    .withColumn("device_id", "long", minValue=1, maxValue=1000)
    .withColumn("timestamp", "timestamp",
                begin="2024-01-01", end="2024-01-31", interval="1 minute")
    .withColumn("temperature", "float", minValue=15.0, maxValue=35.0, random=True)
    .withColumn("humidity", "float", minValue=30.0, maxValue=90.0, random=True)
    .withColumn("pressure", "float", minValue=990.0, maxValue=1030.0, random=True)
    .withColumn("is_anomaly", "boolean", expr="rand() < 0.02")
)

# Build as streaming DataFrame
streaming_df = sensor_schema.build(withStreaming=True)

# Write to Delta as streaming sink
streaming_df.writeStream \
    .format("delta") \
    .option("checkpointLocation", "/tmp/iot_checkpoint") \
    .toTable("demo.iot.sensor_readings")
```

## Quick Financial Prototype

Generate a small financial dataset for local validation, then scale up.

```python
import dbldatagen as dg
from dbldatagen.constraints import PositiveValues
from dbldatagen.distributions import Gamma

# Small prototype (500 rows) for schema validation
accounts = (
    dg.DataGenerator(spark, rows=500, partitions=4, randomSeed=42)
    .withColumn("account_id", "long", minValue=1, uniqueValues=500)
    .withColumn("account_type", "string",
                values=["checking", "savings", "investment", "credit"],
                weights=[40, 30, 20, 10])
    .withColumn("balance", "decimal(12,2)", minValue=0, maxValue=500_000,
                distribution=Gamma(2.0, 2.0))
    .withConstraint(PositiveValues("balance"))
    .build()
)
accounts.show(5)
accounts.describe().show()

# Happy with the shape? Scale up and write to UC
accounts_full = (
    dg.DataGenerator(spark, rows=100_000, partitions=10, randomSeed=42)
    .withColumn("account_id", "long", minValue=1, uniqueValues=100_000)
    .withColumn("account_type", "string",
                values=["checking", "savings", "investment", "credit"],
                weights=[40, 30, 20, 10])
    .withColumn("balance", "decimal(12,2)", minValue=0, maxValue=500_000,
                distribution=Gamma(2.0, 2.0))
    .withConstraint(PositiveValues("balance"))
    .build()
)
accounts_full.write.format("delta").mode("overwrite").saveAsTable("demo.financial.accounts")
```

> **Connect note:** The `distribution=Gamma(...)` and `.withConstraint(PositiveValues(...))` features above require a Databricks notebook. For Connect, replace with `random=True` and `.build().filter("balance > 0")`.

## Manufacturing Predictive Maintenance

Generate equipment, sensor data with fault injection, and maintenance records.

```python
import dbldatagen as dg
from dbldatagen.constraints import PositiveValues, RangedValues

n_equipment = 1_000

# Equipment registry
equipment = (
    dg.DataGenerator(spark, rows=n_equipment, partitions=4, randomSeed=42)
    .withColumn("equipment_id", "long", minValue=1, uniqueValues=n_equipment)
    .withColumn("equipment_type", "string",
                values=["CNC Mill", "Lathe", "Press", "Robot Arm", "Conveyor"],
                weights=[25, 20, 20, 20, 15])
    .withColumn("manufacturer", "string",
                values=["Siemens", "ABB", "Fanuc", "KUKA", "Bosch"],
                weights=[25, 20, 25, 15, 15])
    .withColumn("install_date", "date", begin="2015-01-01", end="2023-12-31", random=True)
    .withColumn("zone", "string", values=["A", "B", "C", "D"], weights=[30, 25, 25, 20])
    .build()
)

# Sensor data with fault injection (10% faulty equipment, 15% outlier rate)
sensor_data = (
    dg.DataGenerator(spark, rows=1_000_000, partitions=20, randomSeed=43)
    .withColumn("equipment_id", "long", minValue=1, maxValue=n_equipment)
    .withColumn("timestamp", "timestamp",
                begin="2024-01-01", end="2024-03-31", random=True)
    .withColumn("sensor_a", "float", minValue=20.0, maxValue=80.0, random=True)
    .withColumn("sensor_b", "float", minValue=0.0, maxValue=100.0, random=True)
    .withColumn("is_anomaly", "boolean", expr="rand() < 0.05")
    .withConstraint(RangedValues("sensor_a", 0, 200))
    .withConstraint(RangedValues("sensor_b", 0, 200))
    .build()
)

equipment.write.format("delta").mode("overwrite").saveAsTable("demo.manufacturing.equipment")
sensor_data.write.format("delta").mode("overwrite").saveAsTable("demo.manufacturing.sensor_data")
```

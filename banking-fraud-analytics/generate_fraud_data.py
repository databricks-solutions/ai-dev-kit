"""
Fraud Triage Agent - Synthetic Data Generation
Generates realistic banking transaction and login event data with fraud patterns.

Datasets:
- transactions: 500K rows with legitimate and fraudulent patterns
- login_events: 200K rows with anomalous login behaviors

Target tables:
  sv_ai_builder_workspace_catalog.fraud_demo.raw_transactions
  sv_ai_builder_workspace_catalog.fraud_demo.raw_login_events
"""

import os
import random
from datetime import datetime, timedelta

CATALOG = "sv_ai_builder_workspace_catalog"
SCHEMA = "fraud_demo"

if os.environ.get("DATABRICKS_RUNTIME_VERSION"):
    from pyspark.sql import SparkSession
    spark = SparkSession.builder.getOrCreate()
else:
    from databricks.connect import DatabricksSession, DatabricksEnv
    env = (
        DatabricksEnv()
        .withDependencies("dbldatagen==0.4.0.post1")
        .withDependencies("jmespath==1.0.1")
        .withDependencies("pyparsing==3.2.5")
    )
    spark = DatabricksSession.builder.serverless(True).withEnvironment(env).getOrCreate()

print(f"Spark version: {spark.version}")

# Setup schema
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.raw_transactions")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.login_events")

print(f"Schema and volumes ready: {CATALOG}.{SCHEMA}")

# ─────────────────────────────────────────────────────────────────────────────
# Dataset A: Transactions
# ─────────────────────────────────────────────────────────────────────────────
import dbldatagen as dg
from pyspark.sql import functions as F
from pyspark.sql.types import StringType

NUM_TRANSACTIONS = 500_000
NUM_ACCOUNTS = 10_000

print(f"\nGenerating {NUM_TRANSACTIONS:,} transactions...")

merchant_types = ["grocery", "restaurant", "gas_station", "atm", "online_retail",
                  "wire_transfer", "crypto_exchange", "casino", "electronics", "travel"]
transaction_types = ["purchase", "withdrawal", "wire", "transfer", "deposit"]
channels = ["mobile", "web", "atm", "wire", "pos"]
currencies = ["USD", "EUR", "GBP", "JPY", "CAD", "BTC"]
geo_locations = [
    "New York, US", "Los Angeles, US", "Chicago, US", "Houston, US",
    "London, UK", "Paris, FR", "Lagos, NG", "Bucharest, RO",
    "Moscow, RU", "Beijing, CN", "Sao Paulo, BR", "Mexico City, MX",
    "Toronto, CA", "Sydney, AU", "Dubai, AE"
]

txn_spec = (
    dg.DataGenerator(spark, name="transactions", rows=NUM_TRANSACTIONS, partitions=8)
    .withIdOutput()
    .withColumn("transaction_id", "string",
                expr="concat('TXN', lpad(cast(id as string), 10, '0'))")
    .withColumn("account_id", "long", minValue=100000, maxValue=100000 + NUM_ACCOUNTS - 1,
                random=True)
    .withColumn("timestamp_offset_secs", "long", minValue=0,
                maxValue=int(timedelta(days=30).total_seconds()), random=True)
    .withColumn("amount_base", "double", minValue=1.0, maxValue=500.0, random=True)
    .withColumn("merchant_type", "string", values=merchant_types, random=True)
    .withColumn("transaction_type", "string", values=transaction_types, random=True)
    .withColumn("channel", "string", values=channels, random=True)
    .withColumn("currency", "string",
                values=currencies, weights=[70, 10, 8, 3, 5, 4], random=True)
    .withColumn("geo_location", "string", values=geo_locations, random=True)
    .withColumn("device_seed", "int", minValue=1, maxValue=50000, random=True)
    .withColumn("fraud_seed", "double", minValue=0.0, maxValue=1.0, random=True)
)

txn_raw = txn_spec.build()

# Map device_id and inject fraud patterns
BASE_TS = int(datetime(2025, 1, 1).timestamp())

txn_df = (
    txn_raw
    .withColumn("device_id", F.concat(F.lit("DEV"), F.lpad(F.col("device_seed").cast("string"), 6, "0")))
    .withColumn("timestamp",
                F.to_timestamp(F.from_unixtime(F.col("timestamp_offset_secs") + BASE_TS)))
    # Fraud pattern injection:
    # 5% of transactions: high-value wire (amount 5000-50000)
    .withColumn("is_high_value_wire",
                (F.col("fraud_seed") < 0.05) & (F.col("merchant_type") == "wire_transfer"))
    # 3%: rapid transfer burst (set flag for downstream join)
    .withColumn("is_rapid_burst", F.col("fraud_seed").between(0.05, 0.08))
    # 2%: international from unusual geo
    .withColumn("is_unusual_geo",
                (F.col("fraud_seed").between(0.08, 0.10)) &
                F.col("geo_location").isin("Moscow, RU", "Lagos, NG", "Bucharest, RO"))
    # Compose final amount: high-value wires get 5000-50000, others get 1-5000
    .withColumn("amount", F.when(F.col("is_high_value_wire"),
                                 F.col("amount_base") * 100.0)
                .when(F.col("is_rapid_burst"), F.col("amount_base") * 20.0)
                .otherwise(F.col("amount_base")))
    .withColumn("amount", F.round(F.col("amount"), 2))
    .withColumn("is_international",
                F.when(F.col("geo_location").rlike(", US$"), F.lit(False))
                .otherwise(F.lit(True)))
    # risk_label: fraud if high-value wire OR unusual geo OR rapid burst
    .withColumn("risk_label",
                F.when(F.col("is_high_value_wire") | F.col("is_unusual_geo"),
                       F.lit("fraud"))
                .when(F.col("is_rapid_burst"), F.lit("suspicious"))
                .otherwise(F.lit("legitimate")))
    .select(
        "transaction_id", "account_id", "timestamp", "amount", "currency",
        "merchant_type", "transaction_type", "channel", "geo_location",
        "device_id", "is_international", "risk_label"
    )
)

txn_table = f"{CATALOG}.{SCHEMA}.raw_transactions"
txn_df.write.mode("overwrite").saveAsTable(txn_table)
count = spark.table(txn_table).count()
print(f"  Transactions written: {count:,} → {txn_table}")

# Also write to volume as parquet
vol_txn = f"/Volumes/{CATALOG}/{SCHEMA}/raw_transactions"
txn_df.write.mode("overwrite").parquet(f"{vol_txn}/transactions.parquet")
print(f"  Volume written: {vol_txn}/transactions.parquet")


# ─────────────────────────────────────────────────────────────────────────────
# Dataset B: Login Events
# ─────────────────────────────────────────────────────────────────────────────
NUM_LOGINS = 200_000

print(f"\nGenerating {NUM_LOGINS:,} login events...")

user_agents = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)",
    "python-requests/2.28.0",
    "curl/7.88.1",
    "Dalvik/2.1.0 (Linux; U; Android 13)",
    "Mozilla/5.0 (Linux; Android 13; SM-G991B)",
]

login_spec = (
    dg.DataGenerator(spark, name="login_events", rows=NUM_LOGINS, partitions=4)
    .withIdOutput()
    .withColumn("login_id", "string",
                expr="concat('LGN', lpad(cast(id as string), 10, '0'))")
    .withColumn("account_id", "long", minValue=100000, maxValue=100000 + NUM_ACCOUNTS - 1,
                random=True)
    .withColumn("timestamp_offset_secs", "long", minValue=0,
                maxValue=int(timedelta(days=30).total_seconds()), random=True)
    .withColumn("ip_oct1", "int", minValue=1, maxValue=254, random=True)
    .withColumn("ip_oct2", "int", minValue=0, maxValue=255, random=True)
    .withColumn("ip_oct3", "int", minValue=0, maxValue=255, random=True)
    .withColumn("ip_oct4", "int", minValue=1, maxValue=254, random=True)
    .withColumn("device_seed", "int", minValue=1, maxValue=50000, random=True)
    .withColumn("login_success_flag", "int", values=[0, 1],
                weights=[1, 9], random=True)  # 90% success
    .withColumn("mfa_flag", "int", values=[0, 1], weights=[2, 8], random=True)
    .withColumn("geo_location", "string", values=geo_locations, random=True)
    .withColumn("user_agent", "string", values=user_agents, random=True)
    .withColumn("anomaly_seed", "double", minValue=0.0, maxValue=1.0, random=True)
)

login_raw = login_spec.build()

login_df = (
    login_raw
    .withColumn("ip_address",
                F.concat(F.col("ip_oct1").cast("string"), F.lit("."),
                         F.col("ip_oct2").cast("string"), F.lit("."),
                         F.col("ip_oct3").cast("string"), F.lit("."),
                         F.col("ip_oct4").cast("string")))
    .withColumn("device_id", F.concat(F.lit("DEV"), F.lpad(F.col("device_seed").cast("string"), 6, "0")))
    .withColumn("timestamp",
                F.to_timestamp(F.from_unixtime(F.col("timestamp_offset_secs") + BASE_TS)))
    .withColumn("login_success", F.col("login_success_flag") > 0)
    .withColumn("mfa_enabled", F.col("mfa_flag") == 1)
    # Inject anomalies:
    # 4%: MFA change event (high fraud signal)
    .withColumn("mfa_change_event",
                (F.col("anomaly_seed") < 0.04) & F.col("mfa_enabled"))
    # 3%: impossible travel (geo mismatch flagged separately in silver)
    .withColumn("impossible_travel_flag",
                F.col("anomaly_seed").between(0.04, 0.07))
    # 2%: bot-like user agent
    .withColumn("is_bot_ua",
                F.col("user_agent").isin("python-requests/2.28.0", "curl/7.88.1"))
    .select(
        "login_id", "account_id", "timestamp", "ip_address", "device_id",
        "login_success", "mfa_enabled", "mfa_change_event", "geo_location", "user_agent"
    )
)

login_table = f"{CATALOG}.{SCHEMA}.raw_login_events"
login_df.write.mode("overwrite").saveAsTable(login_table)
count = spark.table(login_table).count()
print(f"  Login events written: {count:,} → {login_table}")

vol_login = f"/Volumes/{CATALOG}/{SCHEMA}/login_events"
login_df.write.mode("overwrite").parquet(f"{vol_login}/login_events.parquet")
print(f"  Volume written: {vol_login}/login_events.parquet")

# ─────────────────────────────────────────────────────────────────────────────
# Silver layer: enriched_transactions (joins + feature engineering)
# ─────────────────────────────────────────────────────────────────────────────
print("\nBuilding silver layer...")

# Silver transactions with risk signals
silver_txn_sql = f"""
CREATE OR REPLACE TABLE {CATALOG}.{SCHEMA}.silver_transactions AS
SELECT
    t.transaction_id,
    t.account_id,
    t.timestamp,
    t.amount,
    t.currency,
    t.merchant_type,
    t.transaction_type,
    t.channel,
    t.geo_location,
    t.device_id,
    t.is_international,
    t.risk_label,
    -- Recent login context (last login within 10 minutes before transaction)
    l.login_id AS recent_login_id,
    l.ip_address AS login_ip,
    l.mfa_change_event,
    l.geo_location AS login_geo,
    l.user_agent,
    -- Risk signals
    CASE WHEN l.mfa_change_event = true THEN 1 ELSE 0 END AS sig_mfa_change,
    CASE WHEN t.geo_location != l.geo_location AND l.geo_location IS NOT NULL THEN 1 ELSE 0 END AS sig_geo_mismatch,
    CASE WHEN t.amount > 10000 AND t.transaction_type = 'wire' THEN 1 ELSE 0 END AS sig_high_value_wire,
    CASE WHEN t.is_international = true THEN 1 ELSE 0 END AS sig_international,
    CASE WHEN t.device_id != l.device_id AND l.device_id IS NOT NULL THEN 1 ELSE 0 END AS sig_new_device,
    CASE WHEN t.channel = 'wire' AND t.amount > 5000 THEN 1 ELSE 0 END AS sig_large_wire
FROM {CATALOG}.{SCHEMA}.raw_transactions t
LEFT JOIN {CATALOG}.{SCHEMA}.raw_login_events l
    ON t.account_id = l.account_id
    AND l.timestamp BETWEEN t.timestamp - INTERVAL 10 MINUTES AND t.timestamp
    AND l.login_success = true
"""
spark.sql(silver_txn_sql)
count = spark.table(f"{CATALOG}.{SCHEMA}.silver_transactions").count()
print(f"  Silver transactions: {count:,}")

# Gold: fraud alert candidates (3+ risk signals)
gold_sql = f"""
CREATE OR REPLACE TABLE {CATALOG}.{SCHEMA}.gold_fraud_alerts AS
SELECT
    transaction_id,
    account_id,
    timestamp,
    amount,
    currency,
    merchant_type,
    transaction_type,
    channel,
    geo_location,
    device_id,
    is_international,
    risk_label,
    recent_login_id,
    login_ip,
    mfa_change_event,
    login_geo,
    user_agent,
    sig_mfa_change,
    sig_geo_mismatch,
    sig_high_value_wire,
    sig_international,
    sig_new_device,
    sig_large_wire,
    (sig_mfa_change + sig_geo_mismatch + sig_high_value_wire + sig_international + sig_new_device + sig_large_wire) AS risk_signal_count,
    CASE
        WHEN (sig_mfa_change + sig_geo_mismatch + sig_high_value_wire + sig_international + sig_new_device + sig_large_wire) >= 3 THEN 'high'
        WHEN (sig_mfa_change + sig_geo_mismatch + sig_high_value_wire + sig_international + sig_new_device + sig_large_wire) = 2 THEN 'medium'
        WHEN (sig_mfa_change + sig_geo_mismatch + sig_high_value_wire + sig_international + sig_new_device + sig_large_wire) = 1 THEN 'low'
        ELSE 'none'
    END AS initial_risk_category,
    CAST(NULL AS DOUBLE) AS ai_risk_score,
    CAST(NULL AS STRING) AS ai_explanation,
    CAST(NULL AS STRING) AS analyst_decision,
    current_timestamp() AS created_at
FROM {CATALOG}.{SCHEMA}.silver_transactions
WHERE (sig_mfa_change + sig_geo_mismatch + sig_high_value_wire + sig_international + sig_new_device + sig_large_wire) >= 1
"""
spark.sql(gold_sql)
count = spark.table(f"{CATALOG}.{SCHEMA}.gold_fraud_alerts").count()
print(f"  Gold fraud alerts: {count:,}")

# fraud_risk_state table for Lakebase/real-time updates
spark.sql(f"""
CREATE OR REPLACE TABLE {CATALOG}.{SCHEMA}.fraud_risk_state (
    account_id BIGINT,
    transaction_id STRING,
    risk_score DOUBLE,
    risk_category STRING,
    ai_explanation STRING,
    analyst_decision STRING,
    updated_at TIMESTAMP
) USING DELTA
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true')
""")
print(f"  fraud_risk_state table created")

print(f"\nData generation complete!")
print(f"  Catalog: {CATALOG}.{SCHEMA}")
print(f"  Tables: raw_transactions, raw_login_events, silver_transactions, gold_fraud_alerts, fraud_risk_state")

"""
Fraud Triage Agent - Real-Time Streaming Pipeline
Uses Spark Structured Streaming to ingest new transactions, join with recent
login context, compute risk signals, and upsert scored alerts to fraud_risk_state.

Architecture:
  Delta table (streaming source) → Feature enrichment → AI scoring → Lakebase upsert

Run mode: continuous streaming (foreachBatch with 30s trigger interval)
"""

import os
import json
import time
from datetime import datetime

from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, DoubleType, LongType,
    TimestampType, BooleanType, IntegerType
)

CATALOG = "sv_ai_builder_workspace_catalog"
SCHEMA = "fraud_demo"
MODEL = "databricks-claude-sonnet-4-5"
CHECKPOINT_BASE = f"/Volumes/{CATALOG}/{SCHEMA}/raw_transactions/checkpoints"

if os.environ.get("DATABRICKS_RUNTIME_VERSION"):
    from pyspark.sql import SparkSession
    spark = SparkSession.builder \
        .config("spark.sql.streaming.stateStore.providerClass",
                "com.databricks.sql.streaming.state.RocksDBStateStoreProvider") \
        .getOrCreate()
    workspace_url = spark.conf.get("spark.databricks.workspaceUrl", "")
    try:
        token = dbutils.secrets.get(scope="fraud-demo", key="databricks-token")  # noqa: F821
    except Exception:
        token = os.environ.get("DATABRICKS_TOKEN", "")
else:
    from databricks.connect import DatabricksSession
    import databricks.sdk
    spark = DatabricksSession.builder.serverless(True).getOrCreate()
    cfg = databricks.sdk.WorkspaceClient().config
    workspace_url = cfg.host
    token = cfg.token

from openai import OpenAI

llm_client = OpenAI(
    api_key=token,
    base_url=f"{workspace_url}/serving-endpoints",
)

# ─────────────────────────────────────────────────────────────────────────────
# Streaming Source: read new transactions from Delta table (CDF / append)
# ─────────────────────────────────────────────────────────────────────────────

# Enable CDF on raw_transactions for streaming
spark.sql(f"""
    ALTER TABLE {CATALOG}.{SCHEMA}.raw_transactions
    SET TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true')
""")

print("Starting streaming pipeline...")

transactions_stream = (
    spark.readStream
    .format("delta")
    .option("readChangeFeed", "true")
    .option("startingVersion", "latest")
    .table(f"{CATALOG}.{SCHEMA}.raw_transactions")
    .filter(F.col("_change_type").isin("insert", "update_postimage"))
    .drop("_change_type", "_commit_version", "_commit_timestamp")
)


# ─────────────────────────────────────────────────────────────────────────────
# Feature Engineering: join with recent login events (stateful watermark join)
# ─────────────────────────────────────────────────────────────────────────────

def enrich_with_signals(txn_df):
    """Add risk signals by joining with login events."""
    # Get recent logins (last 30 minutes) from static table for enrichment
    recent_logins = spark.table(f"{CATALOG}.{SCHEMA}.raw_login_events").filter(
        F.col("login_success") == True
    ).select(
        "account_id",
        F.col("timestamp").alias("login_ts"),
        F.col("ip_address").alias("login_ip"),
        F.col("device_id").alias("login_device_id"),
        F.col("geo_location").alias("login_geo"),
        F.col("mfa_change_event"),
        F.col("user_agent"),
    )

    enriched = (
        txn_df.alias("t")
        .join(
            recent_logins.alias("l"),
            (F.col("t.account_id") == F.col("l.account_id")) &
            (F.col("l.login_ts").between(
                F.col("t.timestamp") - F.expr("INTERVAL 10 MINUTES"),
                F.col("t.timestamp")
            )),
            "left"
        )
        .select(
            F.col("t.*"),
            F.col("l.login_ip"),
            F.col("l.login_device_id"),
            F.col("l.login_geo"),
            F.coalesce(F.col("l.mfa_change_event"), F.lit(False)).alias("mfa_change_event"),
            F.col("l.user_agent"),
            # Risk signals
            F.when(F.col("l.mfa_change_event") == True, 1).otherwise(0).alias("sig_mfa_change"),
            F.when(
                (F.col("t.geo_location") != F.col("l.login_geo")) & F.col("l.login_geo").isNotNull(),
                1
            ).otherwise(0).alias("sig_geo_mismatch"),
            F.when(
                (F.col("t.amount") > 10000) & (F.col("t.transaction_type") == "wire"),
                1
            ).otherwise(0).alias("sig_high_value_wire"),
            F.when(F.col("t.is_international") == True, 1).otherwise(0).alias("sig_international"),
            F.when(
                (F.col("t.device_id") != F.col("l.login_device_id")) & F.col("l.login_device_id").isNotNull(),
                1
            ).otherwise(0).alias("sig_new_device"),
            F.when(
                (F.col("t.channel") == "wire") & (F.col("t.amount") > 5000),
                1
            ).otherwise(0).alias("sig_large_wire"),
        )
    )

    return enriched.withColumn(
        "risk_signal_count",
        F.col("sig_mfa_change") + F.col("sig_geo_mismatch") + F.col("sig_high_value_wire") +
        F.col("sig_international") + F.col("sig_new_device") + F.col("sig_large_wire")
    ).withColumn(
        "initial_risk_category",
        F.when(F.col("risk_signal_count") >= 3, "high")
        .when(F.col("risk_signal_count") == 2, "medium")
        .when(F.col("risk_signal_count") == 1, "low")
        .otherwise("none")
    )


# ─────────────────────────────────────────────────────────────────────────────
# AI Scoring: batch-score high and medium risk transactions
# ─────────────────────────────────────────────────────────────────────────────

SCORE_PROMPT = """Analyze this banking transaction for fraud risk.
Transaction: ID={txn_id} | Account={account_id} | ${amount:.2f} {currency} | {merchant_type} | {channel} | {geo_location}
Risk signals: MFA_change={sig_mfa}, geo_mismatch={sig_geo}, high_wire={sig_wire}, international={sig_intl}, new_device={sig_device}
Login context: IP={login_ip} | geo={login_geo} | user_agent={ua}

Respond with ONLY valid JSON: {{"risk_score": <0-100>, "risk_category": "<low|medium|high>", "explanation": "<1-2 sentences>"}}"""


def ai_score_row(row: dict) -> dict:
    prompt = SCORE_PROMPT.format(
        txn_id=row["transaction_id"],
        account_id=row["account_id"],
        amount=float(row.get("amount", 0)),
        currency=row.get("currency", "USD"),
        merchant_type=row.get("merchant_type", ""),
        channel=row.get("channel", ""),
        geo_location=row.get("geo_location", ""),
        sig_mfa=bool(row.get("sig_mfa_change", 0)),
        sig_geo=bool(row.get("sig_geo_mismatch", 0)),
        sig_wire=bool(row.get("sig_high_value_wire", 0)),
        sig_intl=bool(row.get("sig_international", 0)),
        sig_device=bool(row.get("sig_new_device", 0)),
        login_ip=row.get("login_ip", "N/A"),
        login_geo=row.get("login_geo", "N/A"),
        ua=str(row.get("user_agent", "N/A"))[:60],
    )
    try:
        response = llm_client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.1,
        )
        content = response.choices[0].message.content.strip()
        for marker in ["```json", "```"]:
            if marker in content:
                parts = content.split(marker)
                content = parts[1].split("```")[0].strip() if len(parts) > 1 else content
                break
        result = json.loads(content)
        return {
            "transaction_id": row["transaction_id"],
            "account_id": int(row["account_id"]),
            "risk_score": float(result.get("risk_score", 50)),
            "risk_category": result.get("risk_category", "medium"),
            "ai_explanation": result.get("explanation", ""),
        }
    except Exception as e:
        signals = int(row.get("risk_signal_count", 0))
        score = min(90.0, signals * 25.0)
        cat = "high" if signals >= 3 else ("medium" if signals >= 2 else "low")
        return {
            "transaction_id": row["transaction_id"],
            "account_id": int(row["account_id"]),
            "risk_score": score,
            "risk_category": cat,
            "ai_explanation": f"Rule-based fallback. {signals} risk signals detected.",
        }


# ─────────────────────────────────────────────────────────────────────────────
# foreachBatch: process each micro-batch
# ─────────────────────────────────────────────────────────────────────────────

def process_batch(batch_df, batch_id):
    batch_count = batch_df.count()
    if batch_count == 0:
        print(f"[Batch {batch_id}] Empty batch, skipping.")
        return

    print(f"[Batch {batch_id}] Processing {batch_count} transactions...")

    # Enrich with risk signals
    enriched = enrich_with_signals(batch_df)

    # Filter: only score transactions with at least 1 signal
    to_score = enriched.filter(F.col("risk_signal_count") >= 1)
    score_count = to_score.count()

    if score_count == 0:
        print(f"[Batch {batch_id}] No risky transactions detected.")
        return

    print(f"[Batch {batch_id}] {score_count} transactions need scoring...")

    # Score with AI (for high + medium risk; rule-based for low)
    high_medium = to_score.filter(F.col("risk_signal_count") >= 2)
    rows_to_ai = [r.asDict() for r in high_medium.limit(50).collect()]

    scored_results = []
    for row in rows_to_ai:
        scored_results.append(ai_score_row(row))
        time.sleep(0.03)

    # Rule-based scores for low-risk
    low_risk = to_score.filter(F.col("risk_signal_count") == 1)
    low_risk_scored = low_risk.select(
        "transaction_id",
        F.col("account_id").cast(LongType()),
        F.lit(25.0).cast(DoubleType()).alias("risk_score"),
        F.lit("low").alias("risk_category"),
        F.lit("Single risk signal detected. Low confidence fraud indicator.").alias("ai_explanation"),
    )

    # Combine AI-scored + rule-based
    if scored_results:
        ai_df = spark.createDataFrame(scored_results)
    else:
        ai_df = spark.createDataFrame(
            [], StructType([
                StructField("transaction_id", StringType()),
                StructField("account_id", LongType()),
                StructField("risk_score", DoubleType()),
                StructField("risk_category", StringType()),
                StructField("ai_explanation", StringType()),
            ])
        )

    all_scored = ai_df.union(
        low_risk_scored.select(
            "transaction_id", "account_id", "risk_score", "risk_category", "ai_explanation"
        )
    ).withColumn("updated_at", F.current_timestamp()) \
     .withColumn("analyst_decision", F.lit(None).cast(StringType()))

    # Upsert into fraud_risk_state
    all_scored.createOrReplaceTempView(f"scored_batch_{batch_id}")
    spark.sql(f"""
        MERGE INTO {CATALOG}.{SCHEMA}.fraud_risk_state AS target
        USING scored_batch_{batch_id} AS source
            ON target.transaction_id = source.transaction_id
        WHEN MATCHED THEN UPDATE SET
            target.risk_score = source.risk_score,
            target.risk_category = source.risk_category,
            target.ai_explanation = source.ai_explanation,
            target.updated_at = source.updated_at
        WHEN NOT MATCHED THEN INSERT *
    """)

    total = spark.table(f"{CATALOG}.{SCHEMA}.fraud_risk_state").count()
    print(f"[Batch {batch_id}] Upserted {len(scored_results) + low_risk_scored.count()} rows. "
          f"Total fraud_risk_state: {total:,}")


# ─────────────────────────────────────────────────────────────────────────────
# Start the streaming query
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"Starting Fraud Triage Streaming Pipeline")
    print(f"  Catalog: {CATALOG}.{SCHEMA}")
    print(f"  Model: {MODEL}")
    print(f"  Checkpoint: {CHECKPOINT_BASE}/fraud_scoring")

    query = (
        transactions_stream
        .writeStream
        .foreachBatch(process_batch)
        .option("checkpointLocation", f"{CHECKPOINT_BASE}/fraud_scoring")
        .trigger(processingTime="30 seconds")
        .start()
    )

    print("Streaming query started. Waiting for data...")
    query.awaitTermination(timeout=300)  # 5 min timeout for demo; remove for production
    print("Streaming pipeline complete.")

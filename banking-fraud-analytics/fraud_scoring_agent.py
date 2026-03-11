"""
Fraud Triage Agent - AI Reasoning & Scoring Engine
Uses Claude on Databricks to generate risk scores and plain-English explanations.

Input:  gold_fraud_alerts (high-risk flagged transactions with signals)
Output: fraud_risk_state (risk_score, risk_category, ai_explanation)

Model: databricks-claude-sonnet-4-5
"""

import os
import json
import time
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, DoubleType

CATALOG = "sv_ai_builder_workspace_catalog"
SCHEMA = "fraud_demo"
MODEL = "databricks-claude-sonnet-4-5"
BATCH_SIZE = 50  # Transactions per batch to score

if os.environ.get("DATABRICKS_RUNTIME_VERSION"):
    from pyspark.sql import SparkSession
    spark = SparkSession.builder.getOrCreate()
    workspace_url = spark.conf.get("spark.databricks.workspaceUrl", "")
    token = (
        dbutils.secrets.get(scope="fraud-demo", key="databricks-token")  # noqa: F821
        if "dbutils" in dir()
        else os.environ.get("DATABRICKS_TOKEN", "")
    )
else:
    from databricks.connect import DatabricksSession
    import databricks.sdk
    spark = DatabricksSession.builder.serverless(True).getOrCreate()
    cfg = databricks.sdk.WorkspaceClient().config
    workspace_url = cfg.host
    token = cfg.token

# OpenAI-compatible client for Databricks model serving
from openai import OpenAI

client = OpenAI(
    api_key=token,
    base_url=f"{workspace_url}/serving-endpoints",
)


FRAUD_SCORING_PROMPT = """You are an expert fraud detection analyst at a major bank.
Analyze this transaction and its associated signals to produce a fraud risk score and explanation.

TRANSACTION:
- Transaction ID: {transaction_id}
- Account ID: {account_id}
- Timestamp: {timestamp}
- Amount: ${amount:,.2f} {currency}
- Merchant Type: {merchant_type}
- Transaction Type: {transaction_type}
- Channel: {channel}
- Geo Location: {geo_location}
- International: {is_international}
- Device ID: {device_id}

RISK SIGNALS DETECTED:
- MFA Change Before Transaction: {sig_mfa_change}
- Geo Mismatch (login vs transaction): {sig_geo_mismatch}
- High-Value Wire Transfer (>$10K): {sig_high_value_wire}
- International Transaction: {sig_international}
- New/Unknown Device: {sig_new_device}
- Large Wire Amount (>$5K): {sig_large_wire}
- Total Signal Count: {risk_signal_count}

RECENT LOGIN CONTEXT:
- Login IP: {login_ip}
- Login Location: {login_geo}
- MFA Change Event: {mfa_change_event}
- User Agent: {user_agent}

HISTORICAL CONTEXT:
- Initial risk category: {initial_risk_category}

Based on all signals, respond with ONLY valid JSON in this exact format:
{{
  "risk_score": <integer 0-100>,
  "risk_category": "<low|medium|high>",
  "explanation": "<2-3 sentence plain English explanation of why this transaction is flagged and what the primary indicators are>"
}}

Scoring guidelines:
- 75-100: High confidence fraud (multiple strong signals: MFA change + new device + wire + geo mismatch)
- 50-74: Suspicious, needs review (2+ moderate signals)
- 25-49: Low risk, monitor (1 weak signal)
- 0-24: Legitimate (incidental signals only)"""


def score_transaction(row: dict) -> dict:
    """Score a single transaction using Claude on Databricks."""
    prompt = FRAUD_SCORING_PROMPT.format(
        transaction_id=row.get("transaction_id", ""),
        account_id=row.get("account_id", ""),
        timestamp=str(row.get("timestamp", "")),
        amount=float(row.get("amount", 0)),
        currency=row.get("currency", "USD"),
        merchant_type=row.get("merchant_type", ""),
        transaction_type=row.get("transaction_type", ""),
        channel=row.get("channel", ""),
        geo_location=row.get("geo_location", ""),
        is_international=row.get("is_international", False),
        device_id=row.get("device_id", ""),
        sig_mfa_change=bool(row.get("sig_mfa_change", 0)),
        sig_geo_mismatch=bool(row.get("sig_geo_mismatch", 0)),
        sig_high_value_wire=bool(row.get("sig_high_value_wire", 0)),
        sig_international=bool(row.get("sig_international", 0)),
        sig_new_device=bool(row.get("sig_new_device", 0)),
        sig_large_wire=bool(row.get("sig_large_wire", 0)),
        risk_signal_count=row.get("risk_signal_count", 0),
        login_ip=row.get("login_ip", "Unknown"),
        login_geo=row.get("login_geo", "Unknown"),
        mfa_change_event=bool(row.get("mfa_change_event", False)),
        user_agent=row.get("user_agent", "Unknown"),
        initial_risk_category=row.get("initial_risk_category", "low"),
    )

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.1,
        )
        content = response.choices[0].message.content.strip()

        # Extract JSON from response
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        result = json.loads(content)
        return {
            "transaction_id": row["transaction_id"],
            "account_id": int(row["account_id"]),
            "risk_score": float(result.get("risk_score", 50)),
            "risk_category": result.get("risk_category", "medium"),
            "ai_explanation": result.get("explanation", ""),
        }
    except Exception as e:
        # Fallback: rule-based scoring if LLM fails
        signal_count = int(row.get("risk_signal_count", 0))
        if signal_count >= 3:
            score, category = 80.0, "high"
        elif signal_count == 2:
            score, category = 55.0, "medium"
        else:
            score, category = 30.0, "low"
        return {
            "transaction_id": row["transaction_id"],
            "account_id": int(row["account_id"]),
            "risk_score": score,
            "risk_category": category,
            "ai_explanation": f"Rule-based score (LLM unavailable: {e}). Signals: {signal_count}",
        }


def run_batch_scoring(limit: int = 200):
    """Score a batch of fraud alert candidates and upsert to fraud_risk_state."""
    print(f"\nLoading top {limit} unscored high-risk alerts...")

    alerts_df = spark.sql(f"""
        SELECT a.*
        FROM {CATALOG}.{SCHEMA}.gold_fraud_alerts a
        LEFT JOIN {CATALOG}.{SCHEMA}.fraud_risk_state s
            ON a.transaction_id = s.transaction_id
        WHERE s.transaction_id IS NULL
          AND a.initial_risk_category IN ('high', 'medium')
        ORDER BY a.risk_signal_count DESC, a.amount DESC
        LIMIT {limit}
    """)

    rows = [r.asDict() for r in alerts_df.collect()]
    print(f"  Loaded {len(rows)} alerts to score")

    scored = []
    for i, row in enumerate(rows):
        result = score_transaction(row)
        scored.append(result)
        if (i + 1) % 10 == 0:
            print(f"  Scored {i + 1}/{len(rows)}...")
        time.sleep(0.05)  # gentle rate limiting

    print(f"  Scoring complete. Upserting {len(scored)} results...")

    # Convert to DataFrame and upsert
    scored_df = spark.createDataFrame(scored).withColumn(
        "updated_at", F.current_timestamp()
    ).withColumn("analyst_decision", F.lit(None).cast(StringType()))

    # MERGE into fraud_risk_state
    scored_df.createOrReplaceTempView("scored_batch")
    spark.sql(f"""
        MERGE INTO {CATALOG}.{SCHEMA}.fraud_risk_state AS target
        USING scored_batch AS source
            ON target.transaction_id = source.transaction_id
        WHEN MATCHED THEN UPDATE SET
            target.risk_score = source.risk_score,
            target.risk_category = source.risk_category,
            target.ai_explanation = source.ai_explanation,
            target.updated_at = source.updated_at
        WHEN NOT MATCHED THEN INSERT (
            account_id, transaction_id, risk_score, risk_category,
            ai_explanation, analyst_decision, updated_at
        ) VALUES (
            source.account_id, source.transaction_id, source.risk_score,
            source.risk_category, source.ai_explanation, NULL, source.updated_at
        )
    """)

    count = spark.table(f"{CATALOG}.{SCHEMA}.fraud_risk_state").count()
    print(f"  fraud_risk_state now has {count:,} scored transactions")

    # Show examples
    print("\nSample AI-scored fraud alerts:")
    spark.sql(f"""
        SELECT transaction_id, account_id, risk_score, risk_category,
               LEFT(ai_explanation, 120) AS explanation_preview
        FROM {CATALOG}.{SCHEMA}.fraud_risk_state
        ORDER BY risk_score DESC
        LIMIT 5
    """).show(truncate=False)


if __name__ == "__main__":
    run_batch_scoring(limit=200)
    print("\nFraud scoring complete!")

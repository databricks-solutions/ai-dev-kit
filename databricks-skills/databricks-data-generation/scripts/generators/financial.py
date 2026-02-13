"""Financial services synthetic data generators.

REFERENCE IMPLEMENTATION — This file is not an importable module. Claude reads it
for patterns and adapts the code inline for user notebooks and scripts.
"""

# CONNECT COMPATIBILITY NOTES:
#   Catalyst-safe (works over Connect):
#     - values=/weights=, minValue/maxValue, begin/end dates, expr=, percentNulls=, omit=
#   UDF-dependent (notebook only — apply workarounds for Connect):
#     - text=mimesisText() → values=["James","Mary",...], random=True
#     - template=r"ddddd" → expr="lpad(cast(floor(rand()*100000) as string), 5, '0')"
#     - distribution=Gamma/Beta → random=True or expr= math
#     - .withConstraint() → .build().filter("condition")

import dbldatagen as dg
from dbldatagen.constraints import PositiveValues, SqlExpr
from pyspark.sql import DataFrame


def generate_accounts(spark, rows=100_000, seed=42) -> DataFrame:
    """Generate financial account data with types, balances, and risk ratings."""
    partitions = max(4, rows // 50_000)
    return (
        dg.DataGenerator(spark, rows=rows, partitions=partitions, randomSeed=seed)
        .withColumn("account_id", "long", minValue=1_000_000, uniqueValues=rows)
        .withColumn("customer_id", "long", minValue=500_000, uniqueValues=int(rows * 0.8))
        .withColumn("account_number", "string", template=r"dddddddddddd")
        .withColumn("account_type", "string",
                    values=["Checking", "Savings", "Investment", "Retirement",
                            "Credit Card", "Loan"],
                    weights=[30, 25, 20, 10, 10, 5])
        .withColumn("status", "string",
                    values=["Active", "Dormant", "Closed"], weights=[85, 10, 5])
        .withColumn("open_date", "date",
                    begin="2015-01-01", end="2024-12-31", random=True)
        .withColumn("balance", "decimal(15,2)",
                    minValue=0, maxValue=10_000_000,
                    distribution=dg.distributions.Gamma(shape=2.0, scale=2.0))
        .withColumn("currency", "string",
                    values=["USD", "EUR", "GBP", "JPY"], weights=[70, 15, 10, 5])
        .withColumn("risk_rating", "string",
                    expr="""CASE
                        WHEN balance > 5000000 THEN 'Low'
                        WHEN balance > 500000 THEN 'Medium'
                        ELSE 'High'
                    END""")
        .withConstraint(PositiveValues(columns="balance"))
        .build()
    )


def generate_trades(spark, rows=1_000_000, n_accounts=100_000, seed=42) -> DataFrame:
    """Generate trading activity data with execution details."""
    partitions = max(10, rows // 100_000)
    symbols = ["AAPL", "GOOGL", "MSFT", "AMZN", "META", "NVDA", "TSLA", "JPM", "BAC", "WMT"]

    return (
        dg.DataGenerator(spark, rows=rows, partitions=partitions, randomSeed=seed)
        .withColumn("trade_id", "long", minValue=1, uniqueValues=rows)
        .withColumn("account_id", "long",
                    minValue=1_000_000, maxValue=1_000_000 + n_accounts - 1)
        .withColumn("symbol", "string", values=symbols)
        .withColumn("trade_type", "string", values=["BUY", "SELL"], weights=[55, 45])
        .withColumn("order_type", "string",
                    values=["Market", "Limit", "Stop", "Stop-Limit"],
                    weights=[60, 25, 10, 5])
        .withColumn("quantity", "integer",
                    minValue=1, maxValue=10_000, distribution=dg.distributions.Exponential())
        .withColumn("price", "decimal(12,4)", minValue=10, maxValue=1000, random=True)
        .withColumn("trade_value", "decimal(15,2)", expr="quantity * price")
        .withColumn("commission", "decimal(8,2)", expr="greatest(0.99, trade_value * 0.001)")
        .withColumn("trade_timestamp", "timestamp",
                    begin="2024-01-02 09:30:00", end="2024-12-31 16:00:00", random=True)
        .withColumn("hour", "integer", expr="hour(trade_timestamp)", omit=True)
        .withColumn("volume_factor", "float", expr="""CASE
            WHEN hour BETWEEN 9 AND 10 THEN 3.0
            WHEN hour BETWEEN 15 AND 16 THEN 2.5
            WHEN hour BETWEEN 11 AND 14 THEN 1.0
            ELSE 0.3
        END""")
        .withColumn("status", "string",
                    values=["Filled", "Partial", "Cancelled", "Rejected"],
                    weights=[90, 5, 3, 2])
        .withColumn("execution_venue", "string",
                    values=["NYSE", "NASDAQ", "ARCA", "BATS"],
                    weights=[35, 35, 15, 15])
        .withConstraint(SqlExpr("commission < trade_value"))
        .build()
    )


def generate_transactions(spark, rows=1_000_000, n_accounts=100_000, seed=42) -> DataFrame:
    """Generate financial transactions (deposits, withdrawals, transfers)."""
    partitions = max(20, rows // 100_000)
    txn_types = ["Deposit", "Withdrawal", "Transfer In", "Transfer Out",
                 "Payment", "Fee", "Interest"]

    return (
        dg.DataGenerator(spark, rows=rows, partitions=partitions, randomSeed=seed)
        .withColumn("txn_id", "long", minValue=1, uniqueValues=rows)
        .withColumn("account_id", "long",
                    minValue=1_000_000, maxValue=1_000_000 + n_accounts - 1)
        .withColumn("txn_type", "string",
                    values=txn_types, weights=[20, 15, 15, 15, 25, 5, 5])
        .withColumn("amount", "decimal(12,2)",
                    minValue=1, maxValue=100_000,
                    distribution=dg.distributions.Gamma(shape=2.0, scale=2.0))
        .withColumn("txn_timestamp", "timestamp",
                    begin="2024-01-01 00:00:00", end="2024-12-31 23:59:59", random=True)
        .withColumn("channel", "string",
                    values=["Online", "Mobile", "Branch", "ATM", "Wire"],
                    weights=[35, 30, 15, 15, 5])
        .withColumn("is_international", "boolean", expr="rand() < 0.05")
        .withColumn("status", "string",
                    values=["Completed", "Pending", "Failed", "Reversed"],
                    weights=[90, 5, 3, 2])
        .build()
    )


def generate_streaming_transactions(spark, n_accounts=100_000, seed=42) -> DataFrame:
    """Generate a streaming-compatible DataFrame of financial transactions.

    Use with spark.readStream for real-time transaction simulation.
    Returns a rate-source-based streaming DataFrame.
    """
    from pyspark.sql import functions as F

    txn_types = ["Deposit", "Withdrawal", "Transfer In", "Transfer Out",
                 "Payment", "Fee", "Interest"]
    channels = ["Online", "Mobile", "Branch", "ATM", "Wire"]

    return (
        spark.readStream
        .format("rate")
        .option("rowsPerSecond", 100)
        .load()
        .withColumn("txn_id", F.col("value"))
        .withColumn("account_id",
                    (F.rand() * n_accounts).cast("long") + 1_000_000)
        .withColumn("txn_type",
                    F.element_at(
                        F.array(*[F.lit(t) for t in txn_types]),
                        (F.rand() * len(txn_types)).cast("int") + 1))
        .withColumn("amount", F.round(F.rand() * 10000 + 1, 2))
        .withColumn("channel",
                    F.element_at(
                        F.array(*[F.lit(c) for c in channels]),
                        (F.rand() * len(channels)).cast("int") + 1))
        .withColumn("is_international", F.rand() < 0.05)
        .drop("value")
    )


def generate_financial_cdc(spark, volume_path, n_accounts=100_000,
                           n_batches=5, seed=42):
    """Generate financial CDC data and write to UC Volume."""
    from .cdc import add_cdc_operations, write_cdc_to_volume

    for i in range(n_batches):
        rows = n_accounts if i == 0 else n_accounts // 10
        base_df = generate_accounts(spark, rows=rows, seed=seed + i)
        weights = {"APPEND": 100} if i == 0 else {"APPEND": 40, "UPDATE": 50, "DELETE": 5}
        cdc_df = add_cdc_operations(base_df, weights=weights)
        write_cdc_to_volume(cdc_df, volume_path, batch_id=i)


def generate_financial_demo(spark, catalog, schema="financial",
                            volume="raw_data", n_accounts=100_000, seed=42):
    """Generate complete financial demo dataset with all tables."""
    from ..utils.output import write_medallion

    n_trades = n_accounts * 10
    n_transactions = n_accounts * 10

    accounts = generate_accounts(spark, rows=n_accounts, seed=seed)
    trades = generate_trades(spark, rows=n_trades, n_accounts=n_accounts, seed=seed)
    transactions = generate_transactions(spark, rows=n_transactions,
                                         n_accounts=n_accounts, seed=seed)

    write_medallion(
        tables={
            "accounts": accounts,
            "trades": trades,
            "transactions": transactions,
        },
        catalog=catalog,
        schema=schema,
        volume=volume,
    )

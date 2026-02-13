"""Financial services synthetic data generators (Polars + Mimesis).

REFERENCE IMPLEMENTATION — This file is not an importable module. Claude reads it
for patterns and adapts the code inline for user scripts. Uses pure Polars + Mimesis
for Tier 1 local generation (<100K rows, zero JVM overhead).
"""

import random
from datetime import date, datetime, timedelta

import polars as pl

ACCOUNT_TYPES = ["Checking", "Savings", "Investment", "Retirement", "Credit Card", "Loan"]
ACCOUNT_TYPE_WEIGHTS = [30, 25, 20, 10, 10, 5]
CURRENCIES = ["USD", "EUR", "GBP", "JPY"]
CURRENCY_WEIGHTS = [70, 15, 10, 5]
SYMBOLS = ["AAPL", "GOOGL", "MSFT", "AMZN", "META", "NVDA", "TSLA", "JPM", "BAC", "WMT"]
ORDER_TYPES = ["Market", "Limit", "Stop", "Stop-Limit"]
ORDER_TYPE_WEIGHTS = [60, 25, 10, 5]
VENUES = ["NYSE", "NASDAQ", "ARCA", "BATS"]
VENUE_WEIGHTS = [35, 35, 15, 15]
TXN_TYPES = ["Deposit", "Withdrawal", "Transfer In", "Transfer Out",
             "Payment", "Fee", "Interest"]
TXN_TYPE_WEIGHTS = [20, 15, 15, 15, 25, 5, 5]
CHANNELS = ["Online", "Mobile", "Branch", "ATM", "Wire"]
CHANNEL_WEIGHTS = [35, 30, 15, 15, 5]


def generate_accounts(rows: int = 10_000, seed: int = 42) -> pl.DataFrame:
    """Generate financial account data with types, balances, and risk ratings."""
    random.seed(seed)

    open_start = date(2015, 1, 1)
    open_range = (date(2024, 12, 31) - open_start).days

    account_ids = list(range(1_000_000, 1_000_000 + rows))
    n_unique_customers = int(rows * 0.8)
    customer_ids = [random.randint(500_000, 500_000 + n_unique_customers - 1)
                    for _ in range(rows)]
    account_numbers = [f"{random.randint(100000000000, 999999999999)}" for _ in range(rows)]
    account_types = random.choices(ACCOUNT_TYPES, weights=ACCOUNT_TYPE_WEIGHTS, k=rows)
    statuses = random.choices(
        ["Active", "Dormant", "Closed"], weights=[85, 10, 5], k=rows
    )
    open_dates = [open_start + timedelta(days=random.randint(0, open_range))
                  for _ in range(rows)]
    balances = [round(max(0, random.gammavariate(2.0, 2.0) * 500_000), 2)
                for _ in range(rows)]
    currencies = random.choices(CURRENCIES, weights=CURRENCY_WEIGHTS, k=rows)

    df = pl.DataFrame({
        "account_id": account_ids,
        "customer_id": customer_ids,
        "account_number": account_numbers,
        "account_type": account_types,
        "status": statuses,
        "open_date": open_dates,
        "balance": balances,
        "currency": currencies,
    })

    return df.with_columns(
        pl.when(pl.col("balance") > 5_000_000).then(pl.lit("Low"))
        .when(pl.col("balance") > 500_000).then(pl.lit("Medium"))
        .otherwise(pl.lit("High"))
        .alias("risk_rating")
    )


def generate_trades(rows: int = 50_000, n_accounts: int = 10_000,
                    seed: int = 42) -> pl.DataFrame:
    """Generate trading activity data with execution details."""
    random.seed(seed)

    ts_start = datetime(2024, 1, 2, 9, 30, 0)
    ts_end = datetime(2024, 12, 31, 16, 0, 0)
    ts_range = int((ts_end - ts_start).total_seconds())

    trade_ids = list(range(1, rows + 1))
    account_ids = [random.randint(1_000_000, 1_000_000 + n_accounts - 1)
                   for _ in range(rows)]
    symbols = random.choices(SYMBOLS, k=rows)
    trade_types = random.choices(["BUY", "SELL"], weights=[55, 45], k=rows)
    order_types = random.choices(ORDER_TYPES, weights=ORDER_TYPE_WEIGHTS, k=rows)
    quantities = [max(1, min(10_000, int(random.expovariate(0.002))))
                  for _ in range(rows)]
    prices = [round(random.uniform(10, 1000), 4) for _ in range(rows)]
    trade_values = [round(q * p, 2) for q, p in zip(quantities, prices)]
    commissions = [round(max(0.99, tv * 0.001), 2) for tv in trade_values]
    trade_timestamps = [ts_start + timedelta(seconds=random.randint(0, ts_range))
                        for _ in range(rows)]

    # Volume factor based on hour
    volume_factors = []
    for ts in trade_timestamps:
        h = ts.hour
        if 9 <= h <= 10:
            volume_factors.append(3.0)
        elif 15 <= h <= 16:
            volume_factors.append(2.5)
        elif 11 <= h <= 14:
            volume_factors.append(1.0)
        else:
            volume_factors.append(0.3)

    statuses = random.choices(
        ["Filled", "Partial", "Cancelled", "Rejected"],
        weights=[90, 5, 3, 2], k=rows
    )
    execution_venues = random.choices(VENUES, weights=VENUE_WEIGHTS, k=rows)

    return pl.DataFrame({
        "trade_id": trade_ids,
        "account_id": account_ids,
        "symbol": symbols,
        "trade_type": trade_types,
        "order_type": order_types,
        "quantity": quantities,
        "price": prices,
        "trade_value": trade_values,
        "commission": commissions,
        "trade_timestamp": trade_timestamps,
        "volume_factor": volume_factors,
        "status": statuses,
        "execution_venue": execution_venues,
    })


def generate_transactions(rows: int = 50_000, n_accounts: int = 10_000,
                          seed: int = 42) -> pl.DataFrame:
    """Generate financial transactions (deposits, withdrawals, transfers)."""
    random.seed(seed)

    ts_start = datetime(2024, 1, 1)
    ts_range = int((datetime(2024, 12, 31, 23, 59, 59) - ts_start).total_seconds())

    txn_ids = list(range(1, rows + 1))
    account_ids = [random.randint(1_000_000, 1_000_000 + n_accounts - 1)
                   for _ in range(rows)]
    txn_types = random.choices(TXN_TYPES, weights=TXN_TYPE_WEIGHTS, k=rows)
    amounts = [round(random.gammavariate(2.0, 2.0) * 5_000, 2)
               for _ in range(rows)]
    txn_timestamps = [ts_start + timedelta(seconds=random.randint(0, ts_range))
                      for _ in range(rows)]
    channels = random.choices(CHANNELS, weights=CHANNEL_WEIGHTS, k=rows)
    is_international = [random.random() < 0.05 for _ in range(rows)]
    statuses = random.choices(
        ["Completed", "Pending", "Failed", "Reversed"],
        weights=[90, 5, 3, 2], k=rows
    )

    return pl.DataFrame({
        "txn_id": txn_ids,
        "account_id": account_ids,
        "txn_type": txn_types,
        "amount": amounts,
        "txn_timestamp": txn_timestamps,
        "channel": channels,
        "is_international": is_international,
        "status": statuses,
    })

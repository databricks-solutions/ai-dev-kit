# Financial Industry Patterns

Data models and generation patterns for financial services demos.

## Data Model Overview

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Accounts   │────<│    Trades    │>────│   Symbols    │
└──────────────┘     └──────────────┘     └──────────────┘
       │                    │
       │                    ▼
       │             ┌──────────────┐
       └────────────>│ Transactions │
                     └──────────────┘
                           │
                           ▼
                     ┌──────────────┐
                     │ Risk Events  │
                     └──────────────┘
```

## Table Schemas

### Accounts

| Column | Type | Description | Generation Pattern |
|--------|------|-------------|-------------------|
| `account_id` | LONG | Primary key | Unique |
| `customer_id` | LONG | Customer FK | Unique per account |
| `account_number` | STRING | Account number | Template: 12 digits |
| `account_type` | STRING | Type of account | Values list |
| `status` | STRING | Active/Closed | Weighted values |
| `open_date` | DATE | Account opened | Random in range |
| `balance` | DECIMAL(15,2) | Current balance | Exponential dist |
| `currency` | STRING | Currency code | Values list |
| `risk_rating` | STRING | Risk level | Values list |
| `branch_id` | LONG | Branch location | Range |

```python
import dbldatagen as dg

account_types = ["Checking", "Savings", "Investment", "Retirement", "Credit Card", "Loan"]

accounts = (
    dg.DataGenerator(spark, rows=100_000, partitions=10)
    .withColumn("account_id", "long", minValue=1_000_000, uniqueValues=100_000)
    .withColumn("customer_id", "long", minValue=500_000, uniqueValues=80_000)  # Some customers have multiple accounts
    .withColumn("account_number", "string", template=r"dddddddddddd")
    .withColumn("account_type", "string", values=account_types, weights=[30, 25, 20, 10, 10, 5])
    .withColumn("status", "string", values=["Active", "Dormant", "Closed"], weights=[85, 10, 5])
    .withColumn("open_date", "date", begin="2015-01-01", end="2024-12-31", random=True)
    .withColumn("balance", "decimal(15,2)", minValue=0, maxValue=10_000_000, distribution="exponential")
    .withColumn("currency", "string", values=["USD", "EUR", "GBP", "JPY"], weights=[70, 15, 10, 5])
    .withColumn("risk_rating", "string", values=["Low", "Medium", "High"], weights=[60, 30, 10])
    .withColumn("branch_id", "long", minValue=100, maxValue=500)
    .build()
)
```

### Trades

| Column | Type | Description | Generation Pattern |
|--------|------|-------------|-------------------|
| `trade_id` | LONG | Primary key | Unique |
| `account_id` | LONG | Account FK | Match range |
| `symbol` | STRING | Stock/ETF ticker | Values list |
| `trade_type` | STRING | BUY/SELL | Weighted |
| `order_type` | STRING | Market/Limit/Stop | Values |
| `quantity` | INTEGER | Shares | Exponential |
| `price` | DECIMAL(12,4) | Execution price | By symbol |
| `trade_value` | DECIMAL(15,2) | quantity * price | Computed |
| `commission` | DECIMAL(8,2) | Trading fee | Formula |
| `trade_timestamp` | TIMESTAMP | Execution time | Business hours |
| `status` | STRING | Filled/Pending/Cancelled | Values |

```python
symbols = ["AAPL", "GOOGL", "MSFT", "AMZN", "META", "NVDA", "TSLA", "JPM", "BAC", "WMT"]

trades = (
    dg.DataGenerator(spark, rows=1_000_000, partitions=20)
    .withColumn("trade_id", "long", minValue=1, uniqueValues=1_000_000)
    .withColumn("account_id", "long", minValue=1_000_000, maxValue=1_099_999)
    .withColumn("symbol", "string", values=symbols)
    .withColumn("trade_type", "string", values=["BUY", "SELL"], weights=[55, 45])
    .withColumn("order_type", "string", values=["Market", "Limit", "Stop", "Stop-Limit"], weights=[60, 25, 10, 5])
    .withColumn("quantity", "integer", minValue=1, maxValue=10_000, distribution="exponential")
    .withColumn("price", "decimal(12,4)", minValue=10, maxValue=1000, random=True)
    .withColumn("trade_value", "decimal(15,2)", expr="quantity * price")
    .withColumn("commission", "decimal(8,2)", expr="greatest(0.99, trade_value * 0.001)")
    .withColumn("trade_timestamp", "timestamp", begin="2024-01-02 09:30:00", end="2024-12-31 16:00:00", random=True)
    .withColumn("status", "string", values=["Filled", "Partial", "Cancelled", "Rejected"], weights=[90, 5, 3, 2])
    .build()
)
```

### Transactions (Money Movement)

| Column | Type | Description | Generation Pattern |
|--------|------|-------------|-------------------|
| `txn_id` | LONG | Primary key | Unique |
| `account_id` | LONG | Account FK | Match range |
| `txn_type` | STRING | Transaction type | Values list |
| `amount` | DECIMAL(12,2) | Transaction amount | Range |
| `txn_timestamp` | TIMESTAMP | When occurred | Random |
| `description` | STRING | Description | Template |
| `counterparty` | STRING | Other party | Template |
| `channel` | STRING | How initiated | Values |
| `location` | STRING | Where | Values |
| `is_international` | BOOLEAN | Cross-border | 5% true |

```python
from utils.mimesis_text import mimesisText

txn_types = ["Deposit", "Withdrawal", "Transfer In", "Transfer Out", "Payment", "Fee", "Interest"]

transactions = (
    dg.DataGenerator(spark, rows=5_000_000, partitions=50)
    .withColumn("txn_id", "long", minValue=1, uniqueValues=5_000_000)
    .withColumn("account_id", "long", minValue=1_000_000, maxValue=1_099_999)
    .withColumn("txn_type", "string", values=txn_types, weights=[20, 15, 15, 15, 25, 5, 5])
    .withColumn("amount", "decimal(12,2)", minValue=1, maxValue=100_000, distribution="exponential")
    .withColumn("txn_timestamp", "timestamp", begin="2024-01-01", end="2024-12-31", random=True)
    .withColumn("description", "string", prefix="TXN-", baseColumn="txn_id")
    .withColumn("counterparty", "string", text=mimesisText("finance.company"))
    .withColumn("channel", "string", values=["Online", "Mobile", "Branch", "ATM", "Wire"], weights=[35, 30, 15, 15, 5])
    .withColumn("location", "string", values=["Domestic", "International"], weights=[95, 5])
    .withColumn("is_international", "boolean", expr="location = 'International'")
    .build()
)
```

### Risk Events (Fraud/AML)

| Column | Type | Description | Generation Pattern |
|--------|------|-------------|-------------------|
| `event_id` | LONG | Primary key | Unique |
| `account_id` | LONG | Account FK | Match range |
| `txn_id` | LONG | Related transaction | FK |
| `event_type` | STRING | Risk type | Values |
| `risk_score` | FLOAT | Risk score 0-100 | Range |
| `detection_timestamp` | TIMESTAMP | When detected | After txn |
| `status` | STRING | Review status | Values |
| `is_confirmed_fraud` | BOOLEAN | Confirmed | Label for ML |
| `amount_at_risk` | DECIMAL(12,2) | Potential loss | From txn |

```python
event_types = ["Unusual Activity", "Velocity Spike", "Geographic Anomaly", "Amount Anomaly", "Pattern Match"]

risk_events = (
    dg.DataGenerator(spark, rows=50_000, partitions=10)  # ~1% of transactions flagged
    .withColumn("event_id", "long", minValue=1, uniqueValues=50_000)
    .withColumn("account_id", "long", minValue=1_000_000, maxValue=1_099_999)
    .withColumn("txn_id", "long", minValue=1, maxValue=5_000_000)
    .withColumn("event_type", "string", values=event_types)
    .withColumn("risk_score", "float", minValue=50, maxValue=100, random=True)
    .withColumn("detection_timestamp", "timestamp", begin="2024-01-01", end="2024-12-31", random=True)
    .withColumn("status", "string", values=["Open", "Under Review", "Escalated", "Closed - False Positive", "Closed - Confirmed"], weights=[20, 30, 10, 30, 10])
    .withColumn("is_confirmed_fraud", "boolean", expr="status = 'Closed - Confirmed'")
    .withColumn("amount_at_risk", "decimal(12,2)", minValue=100, maxValue=50_000, distribution="exponential")
    .build()
)
```

## Realistic Patterns

### Trading Volume by Time
```python
# Higher volume at market open and close
.withColumn("hour", "integer", expr="hour(trade_timestamp)", omit=True)
.withColumn("is_peak", "boolean", expr="hour in (9, 10, 15, 16)")
.withColumn("volume_multiplier", "float", expr="case when is_peak then 2.5 else 1.0 end")
```

### Price Correlation by Symbol
```python
# Price ranges by symbol
symbol_prices = {
    "AAPL": (150, 200),
    "GOOGL": (130, 180),
    "MSFT": (350, 450),
    "AMZN": (150, 200),
    "NVDA": (400, 600),
    "TSLA": (200, 350),
}
```

### Fraud Pattern Injection
```python
# Inject realistic fraud patterns
def inject_fraud_patterns(df):
    """Add fraud-like patterns for ML training."""

    # Pattern 1: Velocity (many small transactions)
    velocity_fraud = df.filter("rand() < 0.005")

    # Pattern 2: Geographic anomaly
    geo_fraud = df.filter("is_international and amount > 5000 and rand() < 0.1")

    # Pattern 3: Round amounts (money laundering)
    round_fraud = df.filter("amount % 1000 = 0 and amount > 10000 and rand() < 0.05")

    return velocity_fraud.union(geo_fraud).union(round_fraud)
```

### Account Balance Consistency
```python
# Ensure balances reflect transaction history
.withColumn("running_balance", "decimal(15,2)",
            expr="sum(case when txn_type in ('Deposit', 'Transfer In', 'Interest') then amount else -amount end) over (partition by account_id order by txn_timestamp)")
```

## CDC Generation

```python
def generate_financial_cdc(spark, volume_path, n_accounts=100_000, n_batches=5, seed=42):
    """Generate financial CDC data — account status changes and transaction corrections."""
    import dbldatagen as dg

    # Initial account load
    initial = (
        dg.DataGenerator(spark, rows=n_accounts, partitions=10, randomSeed=seed)
        .withColumn("account_id", "long", minValue=1_000_000, uniqueValues=n_accounts)
        .withColumn("customer_id", "long", minValue=500_000, uniqueValues=80_000)
        .withColumn("account_type", "string",
                    values=["Checking", "Savings", "Investment", "Retirement", "Credit Card"],
                    weights=[30, 25, 20, 15, 10])
        .withColumn("status", "string", values=["Active"])
        .withColumn("balance", "decimal(15,2)", minValue=100, maxValue=500_000, distribution="exponential")
        .withColumn("operation", "string", values=["INSERT"])
        .withColumn("operation_date", "timestamp", begin="2024-01-01", end="2024-01-01")
        .build()
    )
    initial.write.format("json").mode("overwrite").save(f"{volume_path}/accounts/batch_0")

    # Incremental batches — status changes, balance updates, closures
    for batch in range(1, n_batches + 1):
        batch_df = (
            dg.DataGenerator(spark, rows=n_accounts // 10, partitions=4, randomSeed=seed + batch)
            .withColumn("account_id", "long", minValue=1_000_000, maxValue=1_000_000 + n_accounts)
            .withColumn("customer_id", "long", minValue=500_000, maxValue=580_000)
            .withColumn("account_type", "string",
                        values=["Checking", "Savings", "Investment", "Retirement", "Credit Card"],
                        weights=[30, 25, 20, 15, 10])
            .withColumn("status", "string",
                        values=["Active", "Dormant", "Closed"],
                        weights=[70, 20, 10])
            .withColumn("balance", "decimal(15,2)", minValue=0, maxValue=500_000, distribution="exponential")
            .withColumn("operation", "string", values=["INSERT", "UPDATE", "DELETE"], weights=[20, 70, 10])
            .withColumn("operation_date", "timestamp",
                        expr=f"cast('2024-01-{batch + 1:02d}' as timestamp) + make_interval(0,0,0,0, cast(rand() * 23 as int), cast(rand() * 59 as int), 0)")
            .build()
        )
        batch_df.write.format("json").mode("overwrite").save(f"{volume_path}/accounts/batch_{batch}")

    # Transaction corrections — retroactive adjustments
    for batch in range(1, n_batches + 1):
        corrections = (
            dg.DataGenerator(spark, rows=n_accounts // 20, partitions=4, randomSeed=seed + batch + 100)
            .withColumn("txn_id", "long", minValue=1, maxValue=5_000_000)
            .withColumn("account_id", "long", minValue=1_000_000, maxValue=1_000_000 + n_accounts)
            .withColumn("original_amount", "decimal(12,2)", minValue=10, maxValue=10_000, random=True)
            .withColumn("corrected_amount", "decimal(12,2)", expr="original_amount * (0.8 + rand() * 0.4)")
            .withColumn("correction_reason", "string",
                        values=["Duplicate charge", "Wrong amount", "Chargeback", "Reversal"],
                        weights=[30, 30, 25, 15])
            .withColumn("operation", "string", values=["UPDATE"])
            .withColumn("operation_date", "timestamp",
                        expr=f"cast('2024-01-{batch + 1:02d}' as timestamp) + make_interval(0,0,0,0, cast(rand() * 23 as int), cast(rand() * 59 as int), 0)")
            .build()
        )
        corrections.write.format("json").mode("overwrite").save(f"{volume_path}/corrections/batch_{batch}")
```

## Data Quality Injection

```python
from utils.mimesis_text import mimesisText

# Financial data quality issues
# 0.5% null amounts — suspicious data patterns for anomaly detection
.withColumn("amount", "decimal(12,2)", minValue=1, maxValue=100_000,
            distribution="exponential", percentNulls=0.005)

# Missing counterparty info (3% rate)
.withColumn("counterparty", "string", text=mimesisText("finance.company"), percentNulls=0.03)

# Inject duplicate transactions for reconciliation testing (1% rate)
clean_txns = generate_transactions(spark, n_transactions)
txns_with_dupes = clean_txns.union(clean_txns.sample(0.01))
```

## Medallion Output

```python
# Write raw to Volume for bronze ingestion
accounts_df.write.format("json").save(f"/Volumes/{catalog}/{schema}/{volume}/accounts")
transactions_df.write.format("json").save(f"/Volumes/{catalog}/{schema}/{volume}/transactions")
trades_df.write.format("json").save(f"/Volumes/{catalog}/{schema}/{volume}/trades")
```

## Streaming Transactions

```python
# Real-time transaction stream with business hours weighting
streaming_txns = (
    dg.DataGenerator(spark, rows=1_000_000, partitions=20)
    .withColumn("txn_id", "long", minValue=1, uniqueValues=1_000_000)
    .withColumn("account_id", "long", minValue=1_000_000, maxValue=1_099_999)
    .withColumn("txn_type", "string",
                values=["Deposit", "Withdrawal", "Transfer", "Payment", "Fee"],
                weights=[20, 15, 25, 30, 10])
    .withColumn("amount", "decimal(12,2)", minValue=1, maxValue=50_000, distribution="exponential")
    .withColumn("txn_timestamp", "timestamp", begin="2024-01-01", end="2024-12-31", random=True)
    # Business hours weighting with make_interval()
    .withColumn("hour", "integer", expr="hour(txn_timestamp)", omit=True)
    .withColumn("is_business_hours", "boolean", expr="hour between 8 and 18", omit=True)
    .withColumn("volume_weight", "float",
                expr="case when is_business_hours then 3.0 else 1.0 end")
    .build()
)

# Build as streaming source
streaming_spec = (
    dg.DataGenerator(spark, rows=1_000_000, partitions=10)
    .withColumn("txn_id", "long", minValue=1, uniqueValues=1_000_000)
    .withColumn("account_id", "long", minValue=1_000_000, maxValue=1_099_999)
    .withColumn("amount", "decimal(12,2)", minValue=1, maxValue=50_000, distribution="exponential")
    .withColumn("txn_timestamp", "timestamp", begin="2024-01-01", end="2024-12-31", random=True)
)
streaming_df = streaming_spec.build(withStreaming=True)
```

## Business Hours Trading with make_interval()

```python
# Generate trades only during market hours (9:30 AM - 4:00 PM ET)
.withColumn("base_date", "date", begin="2024-01-02", end="2024-12-31", random=True, omit=True)
.withColumn("day_of_week", "integer", expr="dayofweek(base_date)", omit=True)
# Skip weekends (1=Sunday, 7=Saturday)
.withColumn("is_trading_day", "boolean", expr="day_of_week between 2 and 6", omit=True)
# Random time within trading hours using make_interval()
.withColumn("trade_timestamp", "timestamp",
            expr="""case when is_trading_day
                then cast(base_date as timestamp)
                     + make_interval(0, 0, 0, 0, 9, 30, 0)
                     + make_interval(0, 0, 0, 0, cast(rand() * 6 as int), cast(rand() * 59 as int), 0)
                else null
            end""")

# Fraud ring patterns — correlated suspicious activity
.withColumn("ring_id", "integer", minValue=1, maxValue=20, omit=True)
.withColumn("is_ring_member", "boolean", expr="rand() < 0.003", omit=True)
.withColumn("ring_counterparty", "long",
            expr="case when is_ring_member then 1_000_000 + (ring_id * 100) + cast(rand() * 5 as int) else null end")
```

## Complete Financial Demo

```python
def generate_financial_demo(
    spark,
    n_accounts: int = 100_000,
    n_trades: int = 1_000_000,
    n_transactions: int = 5_000_000,
    catalog: str = "demo",
    schema: str = "finance"
):
    """Generate complete financial services demo dataset."""

    accounts = generate_accounts(spark, n_accounts)
    trades = generate_trades(spark, n_trades, n_accounts)
    transactions = generate_transactions(spark, n_transactions, n_accounts)
    risk_events = generate_risk_events(spark, n_transactions // 100, n_accounts, n_transactions)

    tables = {
        "accounts": accounts,
        "trades": trades,
        "transactions": transactions,
        "risk_events": risk_events,
    }

    for name, df in tables.items():
        df.write.format("delta").mode("overwrite").saveAsTable(f"{catalog}.{schema}.{name}")

    return tables
```

## Common Demo Queries

### Portfolio Summary
```sql
SELECT
    a.account_id,
    a.account_type,
    COUNT(t.trade_id) as total_trades,
    SUM(case when t.trade_type = 'BUY' then t.trade_value else -t.trade_value end) as net_investment,
    SUM(t.commission) as total_fees
FROM accounts a
LEFT JOIN trades t ON a.account_id = t.account_id
WHERE a.account_type = 'Investment'
GROUP BY a.account_id, a.account_type
```

### Fraud Detection Model Features
```sql
SELECT
    a.account_id,
    a.risk_rating,
    COUNT(DISTINCT t.txn_id) as txn_count,
    AVG(t.amount) as avg_amount,
    STDDEV(t.amount) as stddev_amount,
    SUM(case when t.is_international then 1 else 0 end) as intl_txn_count,
    COUNT(DISTINCT t.channel) as unique_channels,
    COALESCE(r.confirmed_fraud_count, 0) as prior_fraud
FROM accounts a
JOIN transactions t ON a.account_id = t.account_id
LEFT JOIN (
    SELECT account_id, COUNT(*) as confirmed_fraud_count
    FROM risk_events
    WHERE is_confirmed_fraud = true
    GROUP BY account_id
) r ON a.account_id = r.account_id
GROUP BY a.account_id, a.risk_rating, r.confirmed_fraud_count
```

### Transaction Velocity
```sql
SELECT
    account_id,
    date_trunc('hour', txn_timestamp) as hour,
    COUNT(*) as txn_count,
    SUM(amount) as total_amount
FROM transactions
GROUP BY account_id, date_trunc('hour', txn_timestamp)
HAVING COUNT(*) > 10  -- Velocity threshold
ORDER BY txn_count DESC
```

### Risk Score Distribution
```sql
SELECT
    event_type,
    COUNT(*) as event_count,
    AVG(risk_score) as avg_score,
    SUM(amount_at_risk) as total_risk_amount,
    SUM(case when is_confirmed_fraud then 1 else 0 end) / COUNT(*) * 100 as fraud_rate_pct
FROM risk_events
GROUP BY event_type
ORDER BY fraud_rate_pct DESC
```

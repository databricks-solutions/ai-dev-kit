# Seasonality Patterns

Patterns for applying realistic seasonality to synthetic time-based data generated with dbldatagen. These patterns layer monthly, weekly, daily, and event-driven variation on top of base data to produce convincing demos.

## Monthly Seasonality Factors

Standard retail/e-commerce monthly factors derived from real-world purchasing patterns:

```python
SEASONAL_FACTORS = {
    1: 1.6,  2: 1.1,  3: 1.1,  4: 1.1,  5: 1.1,     # Winter peak (Jan returns/sales), Spring
    6: 1.2,  7: 1.2,  8: 1.2,                          # Summer uplift
    9: 1.4, 10: 1.4, 11: 1.4, 12: 1.6,                 # Autumn ramp, Holiday peak
}
```

These factors multiply against a base amount or volume. January and December peak at 1.6x due to holiday gift returns and holiday shopping respectively. Summer months get a modest 1.2x uplift. Autumn ramps to 1.4x as back-to-school and pre-holiday spending increase.

## Day-of-Week Patterns

- **Weekends** (Sat/Sun): +30% volume (factor `1.3`)
- **Weekdays** (Mon-Fri): baseline (factor `1.0`)

Implementation uses `dayofweek()` which returns 1 (Sunday) through 7 (Saturday) in Spark SQL:

```python
# Spark SQL dayofweek: 1=Sunday, 7=Saturday
"CASE WHEN dayofweek(txn_date) IN (1, 7) THEN 1.3 ELSE 1.0 END"
```

## Business Hours Distribution

For transactions or events that cluster around working hours:

| Period | Hours | Factor | Use Case |
|--------|-------|--------|----------|
| Peak | 9-10 AM, 3-4 PM | 3.0 | Market open/close, commute shopping |
| Normal | 11 AM - 2 PM | 1.0 | Mid-day baseline |
| Off-hours | Before 8 AM, after 7 PM | 0.1 | Late-night / early-morning |

## Campaign/Event Spikes

Short-duration promotional events that override normal seasonality:

- **Campaign windows**: configurable date ranges with a multiplier (e.g., 2.0x for a 10-day sale)
- **Black Friday / Cyber Monday**: 3-5x spike over a 4-day window
- **Implementation**: match transaction date against campaign date ranges, apply multiplier

## Implementation Patterns

### Pattern 1: Post-Generation Seasonal Multiplier

Generate base data with dbldatagen, then apply seasonal factors using PySpark expressions. This approach keeps the dbldatagen spec simple and layers seasonality as a post-processing step.

```python
import dbldatagen as dg
from pyspark.sql import functions as F

# Generate base transactions
base_spec = (
    dg.DataGenerator(spark, rows=1_000_000, partitions=20)
    .withColumn("txn_id", "long", minValue=1, uniqueValues=1_000_000)
    .withColumn("txn_date", "date", begin="2024-01-01", end="2024-12-31", random=True)
    .withColumn("base_amount", "decimal(10,2)", minValue=10, maxValue=500,
                distribution="exponential")
)
base_df = base_spec.build()

# Apply monthly + day-of-week seasonal multiplier
seasonal_df = base_df.withColumn(
    "amount",
    F.col("base_amount") * F.expr("""
        CASE month(txn_date)
            WHEN 1 THEN 1.6  WHEN 2 THEN 1.1  WHEN 3 THEN 1.1
            WHEN 4 THEN 1.1  WHEN 5 THEN 1.1  WHEN 6 THEN 1.2
            WHEN 7 THEN 1.2  WHEN 8 THEN 1.2  WHEN 9 THEN 1.4
            WHEN 10 THEN 1.4 WHEN 11 THEN 1.4 WHEN 12 THEN 1.6
        END
        * CASE WHEN dayofweek(txn_date) IN (1, 7) THEN 1.3 ELSE 1.0 END
    """)
)
```

### Pattern 2: Inline dbldatagen Expression

Build seasonality directly into the data spec using `expr` and helper columns marked `omit=True` so they do not appear in the final output:

```python
import dbldatagen as dg

spec = (
    dg.DataGenerator(spark, rows=1_000_000, partitions=20)
    .withColumn("order_id", "long", minValue=1, uniqueValues=1_000_000)
    .withColumn("order_date", "date", begin="2024-01-01", end="2024-12-31", random=True)
    .withColumn("base_amount", "decimal(10,2)", minValue=10, maxValue=500,
                distribution="exponential", omit=True)
    .withColumn("month_num", "integer", expr="month(order_date)", omit=True)
    .withColumn("seasonal_factor", "float", expr="""
        CASE month_num
            WHEN 1 THEN 1.6  WHEN 2 THEN 1.1  WHEN 3 THEN 1.1
            WHEN 4 THEN 1.1  WHEN 5 THEN 1.1  WHEN 6 THEN 1.2
            WHEN 7 THEN 1.2  WHEN 8 THEN 1.2  WHEN 9 THEN 1.4
            WHEN 10 THEN 1.4 WHEN 11 THEN 1.4 WHEN 12 THEN 1.6
        END""", omit=True)
    .withColumn("weekend_factor", "float",
                expr="CASE WHEN dayofweek(order_date) IN (1, 7) THEN 1.3 ELSE 1.0 END",
                omit=True)
    .withColumn("amount", "decimal(10,2)",
                expr="base_amount * seasonal_factor * weekend_factor * (0.9 + rand() * 0.2)")
)
df = spec.build()
```

### Pattern 3: Daily Temperature Cycles (IoT/Energy)

Combine annual and daily sine waves for realistic temperature data. The annual cycle peaks in summer (day ~172) and troughs in winter. The daily cycle peaks mid-afternoon and troughs pre-dawn.

```python
import dbldatagen as dg

temp_spec = (
    dg.DataGenerator(spark, rows=5_000_000, partitions=20)
    .withColumn("device_id", "long", minValue=1000, maxValue=1500)
    .withColumn("timestamp", "timestamp", begin="2024-01-01", end="2024-12-31",
                interval="1 minute")
    .withColumn("hour", "integer", expr="hour(timestamp)", omit=True)
    .withColumn("day_of_year", "integer", expr="dayofyear(timestamp)", omit=True)
    # Annual cycle: baseline 20C, amplitude 15C, phase-shifted so peak is ~late July
    .withColumn("annual_temp", "float",
                expr="20 + 15 * sin(2 * pi() * (day_of_year - 80) / 365)", omit=True)
    # Daily cycle: amplitude 5C, phase-shifted so peak is ~2 PM
    .withColumn("daily_temp", "float",
                expr="annual_temp + 5 * sin(2 * pi() * (hour - 6) / 24)", omit=True)
    # Final reading with Gaussian-like noise
    .withColumn("temperature", "float", expr="daily_temp + (rand() * 3 - 1.5)")
)
temp_df = temp_spec.build()
```

### Pattern 4: Complete Retail Transaction Generator with Seasonality

Full copy-pasteable example that generates a year of retail transactions with monthly seasonality, weekend uplift, campaign spikes, and random noise:

```python
import dbldatagen as dg
from pyspark.sql import functions as F

# --- Configuration ---
CAMPAIGN_RANGES = [
    ("2024-07-01", "2024-07-10", 1.8),   # Summer sale
    ("2024-11-25", "2024-12-02", 3.0),   # Black Friday / Cyber Monday
    ("2024-12-15", "2024-12-25", 2.5),   # Holiday rush
]

# --- Base data generation ---
base_spec = (
    dg.DataGenerator(spark, rows=2_000_000, partitions=20)
    .withColumn("txn_id", "long", minValue=1, uniqueValues=2_000_000)
    .withColumn("customer_id", "long", minValue=10_000, maxValue=99_999,
                distribution="exponential")
    .withColumn("txn_date", "date", begin="2024-01-01", end="2024-12-31", random=True)
    .withColumn("base_amount", "decimal(10,2)", minValue=5, maxValue=500,
                distribution="exponential")
    .withColumn("category", "string",
                values=["electronics", "clothing", "grocery", "home", "sports"],
                weights=[20, 25, 30, 15, 10])
)
base_df = base_spec.build()

# --- Apply seasonality layers ---
seasonal_df = (
    base_df
    # Monthly factor
    .withColumn("monthly_factor", F.expr("""
        CASE month(txn_date)
            WHEN 1 THEN 1.6  WHEN 2 THEN 1.1  WHEN 3 THEN 1.1
            WHEN 4 THEN 1.1  WHEN 5 THEN 1.1  WHEN 6 THEN 1.2
            WHEN 7 THEN 1.2  WHEN 8 THEN 1.2  WHEN 9 THEN 1.4
            WHEN 10 THEN 1.4 WHEN 11 THEN 1.4 WHEN 12 THEN 1.6
        END"""))
    # Weekend uplift
    .withColumn("weekend_factor",
                F.when(F.dayofweek("txn_date").isin(1, 7), 1.3).otherwise(1.0))
    # Campaign spikes
    .withColumn("campaign_factor", F.lit(1.0))
)

# Layer each campaign range
for start, end, multiplier in CAMPAIGN_RANGES:
    seasonal_df = seasonal_df.withColumn(
        "campaign_factor",
        F.when(
            (F.col("txn_date") >= start) & (F.col("txn_date") <= end),
            F.lit(multiplier)
        ).otherwise(F.col("campaign_factor"))
    )

# Combine all factors with random noise (0.9x to 1.1x)
result_df = (
    seasonal_df
    .withColumn("amount",
                F.col("base_amount")
                * F.col("monthly_factor")
                * F.col("weekend_factor")
                * F.col("campaign_factor")
                * (F.lit(0.9) + F.rand() * F.lit(0.2)))
    .drop("base_amount", "monthly_factor", "weekend_factor", "campaign_factor")
)

result_df.write.format("delta").mode("overwrite").saveAsTable("demo.retail.transactions")
```

### Pattern 5: Financial Trading Hours

Weight transaction volume by time of day to reflect market open/close rushes and quiet pre/post-market periods:

```python
import dbldatagen as dg

trade_spec = (
    dg.DataGenerator(spark, rows=1_000_000, partitions=20)
    .withColumn("trade_id", "long", minValue=1, uniqueValues=1_000_000)
    .withColumn("symbol", "string",
                values=["AAPL", "GOOGL", "MSFT", "AMZN", "META", "NVDA", "TSLA"])
    .withColumn("trade_time", "timestamp",
                begin="2024-01-02 04:00:00", end="2024-12-31 20:00:00", random=True)
    .withColumn("hour", "integer", expr="hour(trade_time)", omit=True)
    .withColumn("volume_factor", "float", expr="""
        CASE
            WHEN hour BETWEEN 9 AND 10 THEN 3.0    -- Market open rush
            WHEN hour BETWEEN 15 AND 16 THEN 2.5   -- Market close rush
            WHEN hour BETWEEN 11 AND 14 THEN 1.0   -- Mid-day baseline
            ELSE 0.3                                 -- Pre/post market
        END
    """)
    .withColumn("base_qty", "integer", minValue=1, maxValue=1000,
                distribution="exponential", omit=True)
    .withColumn("quantity", "integer", expr="cast(base_qty * volume_factor as int)")
    .withColumn("price", "decimal(10,2)", minValue=50, maxValue=500, random=True)
)
trade_df = trade_spec.build()
```

## Resources

- See [time-series-patterns.md](time-series-patterns.md) for broader time-series generation patterns including trends, noise, anomalies, and streaming
- See [streaming-patterns.md](streaming-patterns.md) for real-time streaming data generation with `build(withStreaming=True)`

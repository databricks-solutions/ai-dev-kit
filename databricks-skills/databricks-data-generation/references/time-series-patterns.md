# Time-Series Patterns

Patterns for generating realistic time-series data for IoT, financial, and streaming demos.

## Core Concepts

### Timestamp Generation

#### Regular Intervals
```python
import dbldatagen as dg

# Fixed interval (1 minute)
spec = (
    dg.DataGenerator(spark, rows=1_000_000)
    .withColumn("timestamp", "timestamp",
                begin="2024-01-01 00:00:00",
                end="2024-12-31 23:59:59",
                interval="1 minute")
)

# Variable intervals: 1 second, 5 seconds, 1 minute
.withColumn("timestamp", "timestamp", interval="5 seconds")
.withColumn("timestamp", "timestamp", interval="1 hour")
.withColumn("timestamp", "timestamp", interval="1 day")
```

#### Random Within Range
```python
# Random timestamps in range
.withColumn("event_time", "timestamp",
            begin="2024-01-01",
            end="2024-12-31",
            random=True)
```

#### Business Hours Only
```python
# Generate base timestamp
.withColumn("base_ts", "timestamp", begin="2024-01-01", interval="1 hour", omit=True)
# Filter to business hours (9 AM - 5 PM)
.withColumn("event_time", "timestamp",
            expr="case when hour(base_ts) between 9 and 17 then base_ts else null end")
```

#### Precise Timestamps with make_interval()
```python
# Generate timestamps at specific offsets using make_interval()
.withColumn("base_date", "date", begin="2024-01-01", end="2024-12-31", random=True, omit=True)
.withColumn("event_time", "timestamp",
            expr="""cast(base_date as timestamp)
                    + make_interval(0, 0, 0, 0,
                        cast(rand() * 23 as int),
                        cast(rand() * 59 as int),
                        0)""")
```

## Pattern Types

### 1. Seasonal Patterns

#### Daily Cycle (e.g., website traffic, sensor temperature)
```python
# Sinusoidal daily pattern using SQL expression
.withColumn("hour", "integer", expr="hour(timestamp)", omit=True)
.withColumn("daily_pattern", "float",
            expr="50 + 30 * sin(pi() * (hour - 6) / 12)")
.withColumn("noise", "float", expr="rand() * 10 - 5", omit=True)
.withColumn("value", "float", expr="daily_pattern + noise")
```

#### Weekly Cycle (e.g., retail sales)
```python
# Higher on weekends
.withColumn("base_value", "float", minValue=80, maxValue=120, random=True, omit=True)
.withColumn("day_of_week", "integer", expr="dayofweek(timestamp)", omit=True)
.withColumn("value", "float",
            expr="base_value * case when day_of_week in (1, 7) then 1.5 else 1.0 end")
```

#### Monthly/Annual Cycle (e.g., seasonal products)
```python
# Holiday spikes in November-December
.withColumn("month", "integer", expr="month(timestamp)", omit=True)
.withColumn("seasonal_factor", "float",
            expr="case when month in (11, 12) then 2.0 when month in (6, 7, 8) then 0.8 else 1.0 end")
```

#### Combined Seasonal + Daily Cycle
```python
# Full seasonal model for IoT/energy data
.withColumn("day_of_year", "integer", expr="dayofyear(timestamp)", omit=True)
.withColumn("hour", "integer", expr="hour(timestamp)", omit=True)
# Annual: warmer in summer, cooler in winter
.withColumn("annual_cycle", "float",
            expr="20 + 15 * sin(2 * pi() * (day_of_year - 80) / 365)", omit=True)
# Daily: cooler at night, warmer mid-afternoon
.withColumn("daily_cycle", "float",
            expr="annual_cycle + 5 * sin(2 * pi() * (hour - 6) / 24)", omit=True)
.withColumn("temperature", "float", expr="daily_cycle + (rand() * 3 - 1.5)")
```

### 2. Trend Patterns

#### Linear Growth
```python
# Steady growth over time
.withColumn("row_num", "long", minValue=1, uniqueValues=1000000, omit=True)
.withColumn("trend", "float", expr="100 + (row_num * 0.01)")
```

#### Exponential Growth
```python
.withColumn("days_since_start", "integer",
            expr="datediff(timestamp, to_date('2024-01-01'))", omit=True)
.withColumn("value", "float", expr="100 * exp(0.001 * days_since_start)")
```

#### Step Changes (Regime Change)
```python
.withColumn("phase", "integer",
            expr="case when timestamp < '2024-06-01' then 1 else 2 end", omit=True)
.withColumn("baseline", "float",
            expr="case when phase = 1 then 100.0 else 150.0 end")
```

### 3. Noise Patterns

#### Gaussian Noise
```python
# In dbldatagen — normal distribution
.withColumn("value", "float", minValue=90, maxValue=110, distribution="normal")

# Add noise to a base signal
.withColumn("base_signal", "float", minValue=90, maxValue=110, random=True, omit=True)
.withColumn("noise", "float", expr="rand() * 10 - 5", omit=True)
.withColumn("value", "float", expr="base_signal + noise")
```

#### Random Walk (Stock Prices)
```python
# Approximate random walk using PySpark cumulative sum
from pyspark.sql import functions as F, Window

# Generate random returns
returns_spec = (
    dg.DataGenerator(spark, rows=10_000, partitions=4)
    .withColumn("row_id", "long", minValue=1, uniqueValues=10_000)
    .withColumn("timestamp", "timestamp",
                begin="2024-01-02 09:30:00",
                end="2024-12-31 16:00:00",
                interval="1 minute")
    .withColumn("pct_change", "double",
                expr="(rand() - 0.5) * 0.04")  # ~2% volatility
)
returns_df = returns_spec.build()

# Cumulative product for price path
window = Window.orderBy("row_id")
prices_df = (
    returns_df
    .withColumn("cum_return", F.sum("pct_change").over(window))
    .withColumn("price", F.lit(100.0) * F.exp(F.col("cum_return")))
    .select("timestamp", "price")
)
```

#### Poisson-like Events (Random Arrivals)
```python
# Approximate Poisson process using exponential inter-arrival times in Spark
events_spec = (
    dg.DataGenerator(spark, rows=100_000, partitions=10)
    .withColumn("event_id", "long", minValue=1, uniqueValues=100_000)
    # Exponential inter-arrival times
    .withColumn("inter_arrival_seconds", "double",
                minValue=1, maxValue=7200,
                distribution="exponential")
    .withColumn("base_time", "timestamp",
                begin="2024-01-01",
                end="2024-12-31",
                random=True)
)
events_df = events_spec.build()

# For ordered event sequences, use cumulative sum of inter-arrival times
from pyspark.sql import functions as F, Window
window = Window.orderBy("event_id")
ordered_events = (
    events_df
    .withColumn("cum_seconds", F.sum("inter_arrival_seconds").over(window))
    .withColumn("event_time",
                F.expr("cast('2024-01-01' as timestamp) + make_interval(0,0,0,0,0,0, cum_seconds)"))
    .select("event_id", "event_time")
)
```

### 4. Anomaly Patterns

#### Random Anomalies
```python
# 2% anomaly rate
.withColumn("is_anomaly", "boolean", expr="rand() < 0.02")
.withColumn("value", "float",
            expr="case when is_anomaly then normal_value * 3 else normal_value end")
```

#### Clustered Anomalies (Incident Bursts)
```python
# Use window functions to create anomaly clusters in PySpark
from pyspark.sql import functions as F, Window

def inject_anomaly_clusters(df, n_clusters=5, cluster_duration_minutes=30, anomaly_factor=3.0):
    """Inject clusters of anomalies using time-window approach."""

    # Generate random cluster center timestamps
    cluster_centers = (
        dg.DataGenerator(spark, rows=n_clusters)
        .withColumn("cluster_id", "long", minValue=1, uniqueValues=n_clusters)
        .withColumn("cluster_center", "timestamp",
                    begin="2024-01-01", end="2024-12-31", random=True)
        .build()
    )

    # Cross join to find readings within cluster windows
    half_window = cluster_duration_minutes * 60  # seconds
    result = (
        df.crossJoin(cluster_centers.select("cluster_center"))
        .withColumn("in_cluster",
                    F.expr(f"""abs(unix_timestamp(timestamp)
                               - unix_timestamp(cluster_center)) < {half_window}"""))
        .groupBy(df.columns)
        .agg(F.max("in_cluster").alias("is_anomaly"))
        .withColumn("value",
                    F.when(F.col("is_anomaly"), F.col("value") * anomaly_factor)
                     .otherwise(F.col("value")))
    )
    return result
```

#### Gradual Drift (Sensor Calibration Loss)
```python
# Value drifts over time
.withColumn("days_active", "integer",
            expr="datediff(timestamp, install_date)", omit=True)
.withColumn("drift", "float", expr="days_active * 0.01")
.withColumn("reading", "float", expr="true_value + drift")
```

## IoT Patterns

### Device Heartbeat
```python
# Regular heartbeat with occasional gaps
spec = (
    dg.DataGenerator(spark, rows=1_000_000)
    .withColumn("device_id", "long", minValue=1000, maxValue=2000)
    .withColumn("heartbeat_ts", "timestamp", begin="2024-01-01", interval="1 minute")
    .withColumn("status", "string", values=["online", "offline"], weights=[98, 2])
)
```

### Sensor Readings with Drift
```python
spec = (
    dg.DataGenerator(spark, rows=5_000_000)
    .withColumn("device_id", "long", minValue=1000, maxValue=1500)
    .withColumn("timestamp", "timestamp", begin="2024-01-01", interval="1 minute")
    .withColumn("base_temp", "float", minValue=20, maxValue=25, random=True, omit=True)
    .withColumn("noise", "float", expr="rand() * 2 - 1", omit=True)
    .withColumn("row_num", "long", minValue=1, omit=True)
    .withColumn("drift", "float", expr="row_num * 0.0001", omit=True)
    .withColumn("temperature", "float", expr="base_temp + noise + drift")
)
```

### GPS/Telematics
```python
# Simulate vehicle movement
spec = (
    dg.DataGenerator(spark, rows=1_000_000)
    .withColumn("vehicle_id", "long", minValue=1000, maxValue=1100)
    .withColumn("timestamp", "timestamp", begin="2024-01-01", interval="5 seconds")
    .withColumn("latitude", "float", minValue=37.0, maxValue=38.0, random=True)
    .withColumn("longitude", "float", minValue=-122.5, maxValue=-121.5, random=True)
    .withColumn("speed_mph", "float", minValue=0, maxValue=80, random=True)
    .withColumn("heading", "integer", minValue=0, maxValue=359, random=True)
)
```

## Financial Patterns

### Stock Price (Geometric Brownian Motion)
```python
from pyspark.sql import functions as F, Window
import dbldatagen as dg

def generate_stock_prices(spark, n_days=252, initial_price=100.0,
                          daily_return=0.0005, volatility=0.02,
                          interval_minutes=1):
    """Generate realistic stock price data using PySpark."""

    intervals_per_day = int(6.5 * 60 / interval_minutes)  # 6.5 trading hours
    n_intervals = n_days * intervals_per_day

    # Generate base rows with trading-hours timestamps
    spec = (
        dg.DataGenerator(spark, rows=n_intervals, partitions=10)
        .withColumn("row_id", "long", minValue=1, uniqueValues=n_intervals)
        .withColumn("base_date", "date",
                    begin="2024-01-02", end="2024-12-31", random=False, omit=True)
        .withColumn("day_of_week", "integer", expr="dayofweek(base_date)", omit=True)
        # Generate random returns per interval
        .withColumn("pct_change", "double",
                    expr=f"(rand() - 0.5) * {volatility * 2 / (intervals_per_day ** 0.5)}")
    )
    returns_df = spec.build()

    # Cumulative sum of log returns -> price path
    window = Window.orderBy("row_id")
    prices_df = (
        returns_df
        .withColumn("cum_return", F.sum("pct_change").over(window))
        .withColumn("price", F.lit(initial_price) * F.exp(F.col("cum_return")))
        .withColumn("volume", (F.rand() * 99_000 + 1_000).cast("integer"))
        .select("row_id", "price", "volume")
    )

    return prices_df
```

### Transaction Bursts
```python
# More transactions at market open/close
.withColumn("hour", "integer", expr="hour(timestamp)", omit=True)
.withColumn("is_peak", "boolean", expr="hour in (9, 10, 15, 16)")
.withColumn("volume_factor", "float", expr="case when is_peak then 3.0 else 1.0 end")
```

## Streaming Time-Series

### Continuous Sensor Feeds
```python
# Use build(withStreaming=True) for streaming DataFrames
streaming_spec = (
    dg.DataGenerator(spark, rows=10_000_000, partitions=50)
    .withColumn("device_id", "long", minValue=1000, maxValue=2000)
    .withColumn("timestamp", "timestamp", begin="2024-01-01", interval="1 second")
    .withColumn("temperature", "float", minValue=18, maxValue=35, distribution="normal")
    .withColumn("humidity", "float", minValue=20, maxValue=95, random=True)
    .withColumn("is_anomaly", "boolean", expr="rand() < 0.02")
)

# Build as streaming DataFrame
streaming_df = streaming_spec.build(withStreaming=True)

# Write to Delta table for downstream processing
streaming_df.writeStream \
    .format("delta") \
    .outputMode("append") \
    .option("checkpointLocation", "/Volumes/catalog/schema/volume/_checkpoints/sensors") \
    .toTable("catalog.schema.sensor_readings_stream")
```

### Streaming with Windowed Aggregation
```python
# Generate streaming data and aggregate in real-time
from pyspark.sql import functions as F

streaming_df = streaming_spec.build(withStreaming=True)

# Tumbling window aggregation
windowed = (
    streaming_df
    .groupBy(
        F.window("timestamp", "5 minutes"),
        "device_id"
    )
    .agg(
        F.avg("temperature").alias("avg_temp"),
        F.max("temperature").alias("max_temp"),
        F.count("*").alias("reading_count")
    )
)
```

## CDC for Time-Series

### Append-Only Event Streams as CDC
```python
# Time-series data is naturally append-only CDC
# Each reading is an INSERT — no updates or deletes

sensor_spec = (
    dg.DataGenerator(spark, rows=1_000_000, partitions=10)
    .withColumn("reading_id", "long", minValue=1, uniqueValues=1_000_000)
    .withColumn("device_id", "long", minValue=1000, maxValue=2000)
    .withColumn("timestamp", "timestamp", begin="2024-01-01", end="2024-12-31", interval="1 minute")
    .withColumn("metric_value", "double", minValue=0, maxValue=100, random=True)
    .withColumn("operation", "string", values=["APPEND"])
    .withColumn("operation_date", "timestamp", expr="timestamp")
)

# Write in batches to simulate incremental arrival
for day in range(1, 31):
    batch = sensor_spec.build().filter(f"day(timestamp) = {day}")
    batch.write.format("json").mode("overwrite").save(
        f"/Volumes/catalog/schema/volume/sensor_cdc/day_{day:02d}"
    )
```

### Device State CDC (Status Changes)
```python
# Device status changes as CDC events
def generate_device_state_cdc(spark, n_devices=1000, n_batches=10, seed=42):
    """Generate CDC stream of device status changes."""
    import dbldatagen as dg

    for batch in range(n_batches):
        state_changes = (
            dg.DataGenerator(spark, rows=n_devices // 5, partitions=4,
                             randomSeed=seed + batch)
            .withColumn("device_id", "long", minValue=1000, maxValue=1000 + n_devices)
            .withColumn("status", "string",
                        values=["Online", "Offline", "Maintenance", "Error"],
                        weights=[60, 20, 10, 10])
            .withColumn("firmware_version", "string", template=r"d.d.d")
            .withColumn("operation", "string", values=["UPDATE"])
            .withColumn("operation_date", "timestamp",
                        expr=f"""cast('2024-01-01' as timestamp)
                                + make_interval(0, 0, 0, {batch}, cast(rand() * 23 as int), cast(rand() * 59 as int), 0)""")
            .build()
        )
        state_changes.write.format("json").mode("overwrite").save(
            f"/Volumes/catalog/schema/volume/device_state/batch_{batch}"
        )
```

## Complete Examples

### IoT Streaming Demo
```python
import dbldatagen as dg
from pyspark.sql import SparkSession

spark = SparkSession.builder.getOrCreate()

# Generate 30 days of sensor data
sensor_data = (
    dg.DataGenerator(spark, rows=10_000_000, partitions=50)
    .withColumn("device_id", "long", minValue=1000, maxValue=2000)
    .withColumn("reading_id", "long", minValue=1, uniqueValues=10000000)
    .withColumn("timestamp", "timestamp", begin="2024-01-01", end="2024-01-31", interval="1 minute")
    .withColumn("base_temp", "float", minValue=20, maxValue=30, distribution="normal", omit=True)
    .withColumn("noise", "float", expr="rand() * 2 - 1", omit=True)
    .withColumn("is_anomaly", "boolean", expr="rand() < 0.02")
    .withColumn("anomaly_factor", "float", expr="case when is_anomaly then 1.5 else 1.0 end", omit=True)
    .withColumn("temperature", "float", expr="(base_temp + noise) * anomaly_factor")
    .withColumn("humidity", "float", minValue=30, maxValue=90, random=True)
    .withColumn("battery_pct", "integer", minValue=0, maxValue=100, random=True)
    .build()
)

sensor_data.write.format("delta").mode("overwrite").saveAsTable("demo.iot.sensor_readings")
```

### Financial Trading Demo
```python
def generate_trading_data(spark, n_accounts=1000, n_trades=100000):
    """Generate complete trading dataset."""

    # Accounts
    accounts = (
        dg.DataGenerator(spark, rows=n_accounts)
        .withColumn("account_id", "long", minValue=100000, uniqueValues=n_accounts)
        .withColumn("account_type", "string", values=["Individual", "Joint", "IRA", "401k"], weights=[50, 20, 20, 10])
        .withColumn("balance", "decimal(12,2)", minValue=1000, maxValue=1000000, distribution="exponential")
        .withColumn("risk_tolerance", "string", values=["Conservative", "Moderate", "Aggressive"], weights=[30, 50, 20])
        .build()
    )

    # Trades
    trades = (
        dg.DataGenerator(spark, rows=n_trades)
        .withColumn("trade_id", "long", minValue=1, uniqueValues=n_trades)
        .withColumn("account_id", "long", minValue=100000, maxValue=100000 + n_accounts - 1)
        .withColumn("symbol", "string", values=["AAPL", "GOOGL", "MSFT", "AMZN", "META", "NVDA", "TSLA"])
        .withColumn("trade_type", "string", values=["BUY", "SELL"], weights=[55, 45])
        .withColumn("quantity", "integer", minValue=1, maxValue=1000, distribution="exponential")
        .withColumn("price", "decimal(10,2)", minValue=50, maxValue=500, random=True)
        .withColumn("trade_time", "timestamp", begin="2024-01-02 09:30:00", end="2024-12-31 16:00:00", random=True)
        .withColumn("is_suspicious", "boolean", expr="rand() < 0.01")
        .build()
    )

    return accounts, trades
```

## Manufacturing Sensor Patterns

### Sine Wave Sensor Generation
Based on real industrial IoT patterns (wind turbine vibration monitoring). Each sensor has a sine wave component combined with normal distribution noise:

```python
import dbldatagen as dg

def generate_multi_sensor_readings(spark, n_equipment=500, rows_per_equipment=2000,
                                    n_sensors=6, seed=42):
    """Generate multi-sensor time-series with sine wave patterns."""
    total_rows = n_equipment * rows_per_equipment
    partitions = max(50, total_rows // 500_000)

    spec = dg.DataGenerator(spark, rows=total_rows, partitions=partitions, randomSeed=seed)
    spec = (spec
        .withColumn("equipment_id", "long", minValue=1, maxValue=n_equipment)
        .withColumn("timestamp", "timestamp",
                    begin="2024-01-01", end="2024-12-31", interval="10 seconds")
    )

    # Generate sensor columns with different sine wave steps and noise levels
    sensor_configs = [
        {"name": "A", "sin_step": 0, "sigma": 1},      # No sine, low noise
        {"name": "B", "sin_step": 0, "sigma": 2},      # No sine, medium noise
        {"name": "C", "sin_step": 0, "sigma": 3},      # No sine, high noise
        {"name": "D", "sin_step": 0.1, "sigma": 1.5},  # Slow sine + noise
        {"name": "E", "sin_step": 0.01, "sigma": 2},   # Very slow sine + noise
        {"name": "F", "sin_step": 0.2, "sigma": 1},    # Fast sine + low noise
    ]

    for cfg in sensor_configs:
        name = f"sensor_{cfg['name']}"
        sigma = cfg['sigma']
        sin_step = cfg['sin_step']

        if sin_step > 0:
            # Sine wave + exponential + normal noise
            spec = (spec
                .withColumn(f"{name}_base", "double",
                            expr=f"2 * exp(sin({sin_step} * monotonically_increasing_id()))",
                            omit=True)
                .withColumn(name, "double",
                            expr=f"{name}_base + (rand() * {sigma * 2} - {sigma})")
            )
        else:
            # Pure normal noise
            spec = spec.withColumn(name, "double",
                                   minValue=-sigma*3, maxValue=sigma*3,
                                   distribution="normal")

    # Energy output (cumulative random walk)
    spec = spec.withColumn("energy", "double", minValue=0, maxValue=100, random=True)

    return spec.build()
```

### Multi-Sensor Correlation
Show how to create correlated sensor readings where one sensor influences another:
```python
# Sensors D and E are correlated via shared base
.withColumn("base_vibration", "double", minValue=0, maxValue=50,
            distribution="normal", omit=True)
.withColumn("sensor_D", "double", expr="base_vibration + rand() * 5")
.withColumn("sensor_E", "double", expr="base_vibration * 0.8 + rand() * 3")
```

### Noise Injection with Configurable Sigma
```python
def add_sensor_noise(spec, col_name, base_col, sigma=1.0):
    """Add Gaussian noise to a base signal."""
    return (spec
        .withColumn(f"{col_name}_noise", "double",
                    expr=f"rand() * {sigma * 2} - {sigma}", omit=True)
        .withColumn(col_name, "double",
                    expr=f"{base_col} + {col_name}_noise"))
```

## Sensor Fault Injection

### Random Fault Injection
Based on industrial patterns: faulty equipment has 15% of readings as outliers, with noise sigma multiplied by 8-20x:

```python
from pyspark.sql import functions as F

def inject_sensor_faults(df, fault_rate=0.15, fault_equipment_pct=0.10,
                          sigma_multiplier_range=(8, 20)):
    """Inject faults into a subset of equipment sensors."""
    # Mark ~10% of equipment as faulty
    equipment_ids = df.select("equipment_id").distinct()
    n_faulty = int(equipment_ids.count() * fault_equipment_pct)
    faulty_ids = equipment_ids.orderBy(F.rand(seed=42)).limit(n_faulty)

    df = df.join(faulty_ids.withColumn("is_faulty", F.lit(True)),
                 "equipment_id", "left").fillna(False, ["is_faulty"])

    # Get sensor columns
    sensor_cols = [c for c in df.columns if c.startswith("sensor_")]

    for col in sensor_cols:
        # For faulty equipment: inject outliers at fault_rate
        df = df.withColumn(col,
            F.when(
                F.col("is_faulty") & (F.rand() < fault_rate),
                F.col(col) * (F.rand() * 12 + 8)  # 8x-20x multiplier
            ).otherwise(F.col(col))
        )

    return df
```

### Missing Value Injection for Damaged Sensors
```python
# 0.5% null rate for damaged sensor readings
def inject_missing_readings(df, null_rate=0.005):
    sensor_cols = [c for c in df.columns if c.startswith("sensor_")]
    for col in sensor_cols:
        df = df.withColumn(col,
            F.when(F.col("is_faulty") & (F.rand() < null_rate), None)
             .otherwise(F.col(col)))
    return df
```

## Cumulative Metrics

### Running Sum (Energy Production)
```python
from pyspark.sql import Window

window = Window.partitionBy("equipment_id").orderBy("timestamp")

df_with_cumulative = (
    df
    .withColumn("hourly_energy", F.abs(F.col("energy")))
    .withColumn("cumulative_energy", F.sum("hourly_energy").over(window))
    .withColumn("running_avg_energy", F.avg("hourly_energy").over(
        window.rowsBetween(-23, 0)))  # 24-hour rolling average
)
```

### Hourly Aggregated Features (Silver Layer Pattern)
```python
# Aggregate raw sensor readings to hourly statistics for ML
from pyspark.sql.functions import avg, stddev_pop, expr, date_trunc, from_unixtime

hourly_features = (
    raw_sensor_df
    .withColumn("hourly_ts", date_trunc("hour", "timestamp"))
    .groupBy("hourly_ts", "equipment_id")
    .agg(
        avg("energy").alias("avg_energy"),
        stddev_pop("sensor_A").alias("std_sensor_A"),
        stddev_pop("sensor_B").alias("std_sensor_B"),
        stddev_pop("sensor_C").alias("std_sensor_C"),
        expr("percentile_approx(sensor_A, array(0.1, 0.5, 0.9))").alias("pct_sensor_A"),
    )
)
```

## Business Hour Weighting

### Filtering to Business Hours
```python
.withColumn("hour", "integer", expr="hour(timestamp)", omit=True)
.withColumn("is_business_hours", "boolean", expr="hour BETWEEN 9 AND 17")

# Weight readings higher during business hours
.withColumn("activity_level", "double", expr="""
    CASE
        WHEN hour BETWEEN 9 AND 10 THEN 3.0   -- Morning peak
        WHEN hour BETWEEN 11 AND 14 THEN 1.5  -- Mid-day
        WHEN hour BETWEEN 15 AND 17 THEN 2.5  -- Afternoon peak
        WHEN hour BETWEEN 6 AND 8 THEN 0.5    -- Early morning ramp
        WHEN hour BETWEEN 18 AND 20 THEN 0.3  -- Evening wind-down
        ELSE 0.1                                -- Overnight
    END
""")
```

## Resources

- [dbldatagen Time-Series Documentation](https://databrickslabs.github.io/dbldatagen/)
- [PySpark SQL Functions](https://spark.apache.org/docs/latest/api/python/reference/pyspark.sql/functions.html)

# IoT Industry Patterns

Data models and generation patterns for IoT and telematics demos.

## Data Model Overview

```
┌──────────────┐     ┌──────────────┐
│   Devices    │────<│  Readings    │
└──────────────┘     └──────────────┘
       │                    │
       │                    │
       ▼                    ▼
┌──────────────┐     ┌──────────────┐
│  Locations   │     │    Events    │
└──────────────┘     └──────────────┘
                           │
                           ▼
                     ┌──────────────┐
                     │   Alerts     │
                     └──────────────┘
```

## Table Schemas

### Devices

| Column | Type | Description | Generation Pattern |
|--------|------|-------------|-------------------|
| `device_id` | LONG | Primary key | Unique |
| `device_serial` | STRING | Serial number | Template |
| `device_type` | STRING | Type of device | Values list |
| `manufacturer` | STRING | Device maker | Values |
| `model` | STRING | Model number | Values by type |
| `firmware_version` | STRING | Software version | Template |
| `install_date` | DATE | Installation | Random |
| `location_id` | LONG | Location FK | Range |
| `latitude` | DOUBLE | GPS lat | Range |
| `longitude` | DOUBLE | GPS lon | Range |
| `status` | STRING | Device status | Values |

```python
import dbldatagen as dg

device_types = ["Temperature Sensor", "Humidity Sensor", "Pressure Sensor", "Motion Detector", "Smart Meter", "GPS Tracker", "Camera", "HVAC Controller"]

devices = (
    dg.DataGenerator(spark, rows=10_000, partitions=4)
    .withColumn("device_id", "long", minValue=1000, uniqueValues=10_000)
    .withColumn("device_serial", "string", template=r"DEV-dddddddd")
    .withColumn("device_type", "string", values=device_types)
    .withColumn("manufacturer", "string", values=["SensorCorp", "IoTech", "SmartDevices", "TelcoSystems"])
    .withColumn("model", "string", prefix="Model-", baseColumn="device_id")
    .withColumn("firmware_version", "string", template=r"d.d.d")
    .withColumn("install_date", "date", begin="2020-01-01", end="2024-12-31", random=True)
    .withColumn("location_id", "long", minValue=1, maxValue=500)
    .withColumn("latitude", "double", minValue=25.0, maxValue=48.0, random=True)
    .withColumn("longitude", "double", minValue=-125.0, maxValue=-70.0, random=True)
    .withColumn("status", "string", values=["Online", "Offline", "Maintenance", "Decommissioned"], weights=[85, 8, 5, 2])
    .build()
)
```

### Sensor Readings

| Column | Type | Description | Generation Pattern |
|--------|------|-------------|-------------------|
| `reading_id` | LONG | Primary key | Unique |
| `device_id` | LONG | Device FK | Match range |
| `timestamp` | TIMESTAMP | Reading time | Interval-based |
| `metric_name` | STRING | What's measured | By device type |
| `metric_value` | DOUBLE | Measurement | By metric |
| `unit` | STRING | Unit of measure | By metric |
| `quality_score` | INTEGER | Data quality | 0-100 |
| `is_anomaly` | BOOLEAN | Anomaly flag | 2% true |

```python
sensor_readings = (
    dg.DataGenerator(spark, rows=50_000_000, partitions=100)
    .withColumn("reading_id", "long", minValue=1, uniqueValues=50_000_000)
    .withColumn("device_id", "long", minValue=1000, maxValue=10_999)
    .withColumn("timestamp", "timestamp", begin="2024-01-01", end="2024-12-31", interval="1 minute")
    .withColumn("metric_name", "string", values=["temperature", "humidity", "pressure", "power", "vibration"])
    # Metric-specific ranges
    .withColumn("base_value", "double", minValue=0, maxValue=100, random=True, omit=True)
    .withColumn("noise", "double", expr="rand() * 5 - 2.5", omit=True)
    .withColumn("metric_value", "double", expr="base_value + noise")
    .withColumn("unit", "string", expr="""case metric_name
        when 'temperature' then 'celsius'
        when 'humidity' then 'percent'
        when 'pressure' then 'hPa'
        when 'power' then 'kWh'
        when 'vibration' then 'mm/s'
        else 'unknown'
    end""")
    .withColumn("quality_score", "integer", minValue=80, maxValue=100, random=True)
    .withColumn("is_anomaly", "boolean", expr="rand() < 0.02")
    .build()
)
```

### Events

| Column | Type | Description | Generation Pattern |
|--------|------|-------------|-------------------|
| `event_id` | LONG | Primary key | Unique |
| `device_id` | LONG | Device FK | Match range |
| `timestamp` | TIMESTAMP | Event time | Random |
| `event_type` | STRING | Type of event | Values |
| `severity` | STRING | Severity level | Weighted |
| `description` | STRING | Event details | Template |
| `acknowledged` | BOOLEAN | Seen by ops | Varies |
| `resolved` | BOOLEAN | Fixed | Varies |

```python
event_types = ["Threshold Exceeded", "Device Offline", "Firmware Update", "Calibration Required", "Battery Low", "Connection Lost", "Maintenance Due"]

events = (
    dg.DataGenerator(spark, rows=100_000, partitions=10)
    .withColumn("event_id", "long", minValue=1, uniqueValues=100_000)
    .withColumn("device_id", "long", minValue=1000, maxValue=10_999)
    .withColumn("timestamp", "timestamp", begin="2024-01-01", end="2024-12-31", random=True)
    .withColumn("event_type", "string", values=event_types)
    .withColumn("severity", "string", values=["Critical", "Warning", "Info"], weights=[10, 30, 60])
    .withColumn("description", "string", prefix="Event on device ", baseColumn="device_id")
    .withColumn("acknowledged", "boolean", expr="rand() < 0.7")
    .withColumn("resolved", "boolean", expr="acknowledged and rand() < 0.8")
    .build()
)
```

### Telemetry (GPS/Vehicle)

| Column | Type | Description | Generation Pattern |
|--------|------|-------------|-------------------|
| `telemetry_id` | LONG | Primary key | Unique |
| `device_id` | LONG | Vehicle/device FK | Match range |
| `timestamp` | TIMESTAMP | Reading time | Interval |
| `latitude` | DOUBLE | GPS latitude | Range + drift |
| `longitude` | DOUBLE | GPS longitude | Range + drift |
| `altitude` | DOUBLE | Elevation | Range |
| `speed` | DOUBLE | Current speed | 0-120 mph |
| `heading` | INTEGER | Direction 0-359 | Random |
| `fuel_level` | DOUBLE | Fuel remaining | 0-100% |
| `engine_temp` | DOUBLE | Engine temperature | Range |

```python
telemetry = (
    dg.DataGenerator(spark, rows=10_000_000, partitions=50)
    .withColumn("telemetry_id", "long", minValue=1, uniqueValues=10_000_000)
    .withColumn("device_id", "long", minValue=1000, maxValue=2000)  # 1000 vehicles
    .withColumn("timestamp", "timestamp", begin="2024-01-01", end="2024-12-31", interval="5 seconds")
    .withColumn("base_lat", "double", minValue=37.0, maxValue=38.0, random=True, omit=True)
    .withColumn("base_lon", "double", minValue=-122.5, maxValue=-121.5, random=True, omit=True)
    .withColumn("lat_drift", "double", expr="rand() * 0.01 - 0.005", omit=True)
    .withColumn("lon_drift", "double", expr="rand() * 0.01 - 0.005", omit=True)
    .withColumn("latitude", "double", expr="base_lat + lat_drift")
    .withColumn("longitude", "double", expr="base_lon + lon_drift")
    .withColumn("altitude", "double", minValue=0, maxValue=500, random=True)
    .withColumn("speed", "double", minValue=0, maxValue=80, random=True)
    .withColumn("heading", "integer", minValue=0, maxValue=359, random=True)
    .withColumn("fuel_level", "double", minValue=10, maxValue=100, random=True)
    .withColumn("engine_temp", "double", minValue=180, maxValue=220, distribution="normal")
    .build()
)
```

## Using dbldatagen Telematics Dataset

dbldatagen includes a pre-built telematics dataset:

```python
from dbldatagen import Datasets

ds = Datasets(spark)

# Get telematics data
telematics = ds.getTable("basic/telematics", rows=1_000_000)
```

## Realistic Patterns

### Sensor Drift Over Time
```python
# Sensors drift as they age
.withColumn("days_since_install", "integer", expr="datediff(timestamp, install_date)", omit=True)
.withColumn("drift", "double", expr="days_since_install * 0.001", omit=True)
.withColumn("reading", "double", expr="base_reading + drift + noise")
```

### Time-of-Day Patterns
```python
# Higher readings during day (HVAC, energy)
.withColumn("hour", "integer", expr="hour(timestamp)", omit=True)
.withColumn("daily_factor", "double", expr="""case
    when hour between 6 and 9 then 1.5    -- Morning ramp
    when hour between 10 and 17 then 1.2  -- Business hours
    when hour between 18 and 22 then 1.3  -- Evening peak
    else 0.8                              -- Night
end""")
```

### Anomaly Injection
```python
# Inject different anomaly types
.withColumn("anomaly_type", "string",
            expr="""case
                when rand() < 0.005 then 'spike'       -- Sudden spike
                when rand() < 0.003 then 'dropout'     -- Missing data
                when rand() < 0.002 then 'drift'       -- Gradual drift
                else null
            end""")
.withColumn("value", "double",
            expr="""case anomaly_type
                when 'spike' then normal_value * 3
                when 'dropout' then null
                when 'drift' then normal_value + row_num * 0.1
                else normal_value
            end""")
```

### Device Clustering by Location
```python
# Devices cluster around facilities
facilities = [
    {"lat": 37.7749, "lon": -122.4194, "name": "San Francisco"},
    {"lat": 34.0522, "lon": -118.2437, "name": "Los Angeles"},
    {"lat": 40.7128, "lon": -74.0060, "name": "New York"},
]

# Add small random offset from facility center
.withColumn("facility_idx", "integer", minValue=0, maxValue=2, random=True, omit=True)
.withColumn("lat_offset", "double", expr="rand() * 0.1 - 0.05", omit=True)
.withColumn("lon_offset", "double", expr="rand() * 0.1 - 0.05", omit=True)
```

## Streaming Demo Patterns

### Auto Loader Source
```python
# Generate streaming-ready data
sensor_readings.write.format("delta").mode("overwrite").save("/mnt/streaming/sensor_source")

# Then use Auto Loader
streaming_df = (
    spark.readStream.format("cloudFiles")
    .option("cloudFiles.format", "delta")
    .load("/mnt/streaming/sensor_source")
)
```

### Change Data Capture
```python
# Generate CDC events
cdc_events = (
    dg.DataGenerator(spark, rows=100_000)
    .withColumn("operation", "string", values=["INSERT", "UPDATE", "DELETE"], weights=[60, 35, 5])
    .withColumn("before", "string", expr="case when operation in ('UPDATE', 'DELETE') then to_json(struct(*)) else null end")
    .withColumn("after", "string", expr="case when operation in ('INSERT', 'UPDATE') then to_json(struct(*)) else null end")
    .build()
)
```

## CDC Generation

```python
def generate_iot_cdc(spark, volume_path, n_devices=10_000, n_batches=5, seed=42):
    """Generate IoT CDC data — device status changes and firmware updates."""
    import dbldatagen as dg

    # Initial device registry
    initial = (
        dg.DataGenerator(spark, rows=n_devices, partitions=4, randomSeed=seed)
        .withColumn("device_id", "long", minValue=1000, uniqueValues=n_devices)
        .withColumn("device_serial", "string", template=r"DEV-dddddddd")
        .withColumn("device_type", "string",
                    values=["Temperature Sensor", "Humidity Sensor", "Pressure Sensor",
                            "Motion Detector", "Smart Meter", "GPS Tracker"],
                    weights=[25, 20, 15, 15, 15, 10])
        .withColumn("firmware_version", "string", values=["1.0.0"])
        .withColumn("status", "string", values=["Online"])
        .withColumn("operation", "string", values=["INSERT"])
        .withColumn("operation_date", "timestamp", begin="2024-01-01", end="2024-01-01")
        .build()
    )
    initial.write.format("json").mode("overwrite").save(f"{volume_path}/devices/batch_0")

    # Incremental batches — status changes, firmware updates, decommissions
    firmware_versions = ["1.0.0", "1.0.1", "1.1.0", "2.0.0", "2.0.1"]
    for batch in range(1, n_batches + 1):
        batch_df = (
            dg.DataGenerator(spark, rows=n_devices // 10, partitions=4, randomSeed=seed + batch)
            .withColumn("device_id", "long", minValue=1000, maxValue=1000 + n_devices)
            .withColumn("device_serial", "string", template=r"DEV-dddddddd")
            .withColumn("device_type", "string",
                        values=["Temperature Sensor", "Humidity Sensor", "Pressure Sensor",
                                "Motion Detector", "Smart Meter", "GPS Tracker"])
            .withColumn("firmware_version", "string",
                        values=firmware_versions[:batch + 1],
                        weights=[10] * batch + [90 - 10 * batch])
            .withColumn("status", "string",
                        values=["Online", "Offline", "Maintenance", "Decommissioned"],
                        weights=[70, 15, 10, 5])
            .withColumn("operation", "string", values=["UPDATE", "INSERT", "DELETE"], weights=[70, 20, 10])
            .withColumn("operation_date", "timestamp",
                        expr=f"cast('2024-01-{batch + 1:02d}' as timestamp) + make_interval(0,0,0,0, cast(rand() * 23 as int), cast(rand() * 59 as int), 0)")
            .build()
        )
        batch_df.write.format("json").mode("overwrite").save(f"{volume_path}/devices/batch_{batch}")
```

## Data Quality Injection

```python
# IoT-appropriate quality issues
# Sensor dropout nulls (2% — simulates connectivity issues)
.withColumn("metric_value", "double", expr="base_value + noise", percentNulls=0.02)

# Duplicate readings (1% — network retransmission)
clean_readings = generate_sensor_readings(spark, n_readings)
readings_with_dupes = clean_readings.union(clean_readings.sample(0.01))

# Out-of-range values (sensor malfunction)
.withColumn("is_malfunction", "boolean", expr="rand() < 0.005", omit=True)
.withColumn("metric_value", "double",
            expr="case when is_malfunction then base_value * 10 else base_value + noise end")
```

## Medallion Output

```python
# Write raw sensor data to Volumes for bronze ingestion
sensor_readings_df.write.format("json").save(f"/Volumes/{catalog}/{schema}/{volume}/sensor_readings")
device_events_df.write.format("json").save(f"/Volumes/{catalog}/{schema}/{volume}/events")
telemetry_df.write.format("json").save(f"/Volumes/{catalog}/{schema}/{volume}/telemetry")
```

## Streaming Sensor Feeds

```python
# Real-time sensor data using build(withStreaming=True)
streaming_spec = (
    dg.DataGenerator(spark, rows=10_000_000, partitions=50)
    .withColumn("device_id", "long", minValue=1000, maxValue=10_999)
    .withColumn("timestamp", "timestamp", begin="2024-01-01", end="2024-12-31", interval="1 minute")
    .withColumn("metric_name", "string", values=["temperature", "humidity", "pressure", "power", "vibration"])
    .withColumn("base_value", "double", minValue=0, maxValue=100, random=True, omit=True)
    .withColumn("noise", "double", expr="rand() * 5 - 2.5", omit=True)
    .withColumn("metric_value", "double", expr="base_value + noise")
)

# Build as streaming DataFrame
streaming_df = streaming_spec.build(withStreaming=True)

# Write to Delta for downstream processing
streaming_df.writeStream \
    .format("delta") \
    .outputMode("append") \
    .option("checkpointLocation", f"/Volumes/{catalog}/{schema}/{volume}/_checkpoints/sensors") \
    .toTable(f"{catalog}.{schema}.sensor_readings_stream")
```

## Seasonal and Time-of-Day Patterns

```python
# Temperature follows seasonal and daily cycles
.withColumn("day_of_year", "integer", expr="dayofyear(timestamp)", omit=True)
.withColumn("hour", "integer", expr="hour(timestamp)", omit=True)

# Seasonal baseline: warmer in summer, cooler in winter
.withColumn("seasonal_temp", "double",
            expr="20 + 15 * sin(2 * pi() * (day_of_year - 80) / 365)", omit=True)
# Daily cycle: cooler at night, warmer mid-afternoon
.withColumn("daily_temp", "double",
            expr="seasonal_temp + 5 * sin(2 * pi() * (hour - 6) / 24)", omit=True)
.withColumn("temperature", "double", expr="daily_temp + (rand() * 3 - 1.5)")

# Power consumption: higher during business hours, lower on weekends
.withColumn("day_of_week", "integer", expr="dayofweek(timestamp)", omit=True)
.withColumn("is_weekend", "boolean", expr="day_of_week in (1, 7)", omit=True)
.withColumn("power_baseline", "double",
            expr="""case
                when is_weekend then 30 + rand() * 10
                when hour between 8 and 18 then 70 + rand() * 20
                else 25 + rand() * 10
            end""")
```

## Maintenance Windows

```python
# Scheduled maintenance windows — devices go offline predictably
.withColumn("day_of_week", "integer", expr="dayofweek(timestamp)", omit=True)
.withColumn("hour", "integer", expr="hour(timestamp)", omit=True)
# Maintenance window: Sundays 2-6 AM
.withColumn("in_maintenance", "boolean",
            expr="day_of_week = 1 and hour between 2 and 5")
.withColumn("status", "string",
            expr="""case
                when in_maintenance then 'Maintenance'
                when rand() < 0.02 then 'Offline'
                else 'Online'
            end""")
.withColumn("metric_value", "double",
            expr="case when in_maintenance then null else base_value + noise end")
```

## Complete IoT Demo

```python
def generate_iot_demo(
    spark,
    n_devices: int = 10_000,
    n_readings: int = 50_000_000,
    n_events: int = 100_000,
    catalog: str = "demo",
    schema: str = "iot"
):
    """Generate complete IoT demo dataset."""

    devices = generate_devices(spark, n_devices)
    sensor_readings = generate_sensor_readings(spark, n_readings, n_devices)
    events = generate_events(spark, n_events, n_devices)
    telemetry = generate_telemetry(spark, n_readings // 5, n_devices // 10)

    tables = {
        "devices": devices,
        "sensor_readings": sensor_readings,
        "events": events,
        "telemetry": telemetry,
    }

    for name, df in tables.items():
        df.write.format("delta").mode("overwrite").saveAsTable(f"{catalog}.{schema}.{name}")

    return tables
```

## Common Demo Queries

### Device Health Dashboard
```sql
SELECT
    d.device_type,
    d.status,
    COUNT(*) as device_count,
    AVG(datediff(current_date(), d.install_date)) as avg_age_days
FROM devices d
GROUP BY d.device_type, d.status
ORDER BY d.device_type, d.status
```

### Anomaly Detection
```sql
SELECT
    sr.device_id,
    d.device_type,
    sr.metric_name,
    AVG(sr.metric_value) as avg_value,
    STDDEV(sr.metric_value) as stddev_value,
    SUM(case when sr.is_anomaly then 1 else 0 end) as anomaly_count
FROM sensor_readings sr
JOIN devices d ON sr.device_id = d.device_id
WHERE sr.timestamp >= current_date() - interval 7 days
GROUP BY sr.device_id, d.device_type, sr.metric_name
HAVING anomaly_count > 10
ORDER BY anomaly_count DESC
```

### Fleet Tracking
```sql
SELECT
    t.device_id,
    MAX(t.timestamp) as last_seen,
    LAST(t.latitude) as last_lat,
    LAST(t.longitude) as last_lon,
    AVG(t.speed) as avg_speed,
    MIN(t.fuel_level) as min_fuel
FROM telemetry t
WHERE t.timestamp >= current_date() - interval 1 day
GROUP BY t.device_id
ORDER BY last_seen DESC
```

### Time-Series Aggregation
```sql
SELECT
    sr.device_id,
    date_trunc('hour', sr.timestamp) as hour,
    sr.metric_name,
    AVG(sr.metric_value) as avg_value,
    MIN(sr.metric_value) as min_value,
    MAX(sr.metric_value) as max_value,
    COUNT(*) as reading_count
FROM sensor_readings sr
WHERE sr.timestamp >= current_date() - interval 24 hours
GROUP BY sr.device_id, date_trunc('hour', sr.timestamp), sr.metric_name
ORDER BY sr.device_id, hour
```

### Geospatial Analysis
```sql
SELECT
    d.device_id,
    d.latitude,
    d.longitude,
    COUNT(e.event_id) as event_count,
    SUM(case when e.severity = 'Critical' then 1 else 0 end) as critical_count
FROM devices d
LEFT JOIN events e ON d.device_id = e.device_id
    AND e.timestamp >= current_date() - interval 30 days
GROUP BY d.device_id, d.latitude, d.longitude
```

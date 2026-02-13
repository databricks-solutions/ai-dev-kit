# Manufacturing Industry Patterns

Data models and generation patterns for manufacturing / industrial IoT demos.

## Data Model Overview

```
┌──────────────┐     ┌──────────────┐
│  Equipment   │────<│ Sensor Data  │
└──────────────┘     └──────────────┘
       │                    │
       │                    │
       ▼                    ▼
┌──────────────┐     ┌──────────────┐
│  Maintenance │     │  Anomalies   │
│   Records    │     │  (derived)   │
└──────────────┘     └──────────────┘
```

## Table Schemas

### Equipment / Asset Registry

| Column | Type | Description | Generation Pattern |
|--------|------|-------------|-------------------|
| `equipment_id` | LONG | Primary key | Unique, starting at 1000 |
| `serial_number` | STRING | Serial number | Template: `EQ-dddddddd` |
| `equipment_type` | STRING | Machine category | Values list (8 types) |
| `manufacturer` | STRING | OEM vendor | Values list (5 vendors) |
| `model` | STRING | Model identifier | Prefix + equipment_id |
| `install_date` | DATE | Installation date | Random in range |
| `location_zone` | STRING | Factory zone | Zone A through Zone F |
| `status` | STRING | Operational status | Weighted: 80/10/7/3 |
| `last_maintenance_date` | DATE | Last service date | Random in range |
| `expected_lifespan_years` | INTEGER | Designed lifespan | 5-25, normal distribution |

```python
import dbldatagen as dg

equipment_types = [
    "CNC Machine", "Assembly Robot", "Conveyor Belt", "Press",
    "Welder", "Packaging Unit", "Quality Scanner", "HVAC System",
]

equipment = (
    dg.DataGenerator(spark, rows=1_000, partitions=2)
    .withColumn("equipment_id", "long", minValue=1000, uniqueValues=1_000)
    .withColumn("serial_number", "string", template=r"EQ-dddddddd")
    .withColumn("equipment_type", "string", values=equipment_types)
    .withColumn("manufacturer", "string",
                values=["Siemens", "ABB", "Fanuc", "Bosch", "Honeywell"])
    .withColumn("model", "string", prefix="Model-", baseColumn="equipment_id")
    .withColumn("install_date", "date", begin="2015-01-01", end="2024-12-31", random=True)
    .withColumn("location_zone", "string",
                values=["Zone A", "Zone B", "Zone C", "Zone D", "Zone E", "Zone F"])
    .withColumn("status", "string",
                values=["Operational", "Maintenance", "Idle", "Decommissioned"],
                weights=[80, 10, 7, 3])
    .withColumn("last_maintenance_date", "date",
                begin="2024-01-01", end="2024-12-31", random=True)
    .withColumn("expected_lifespan_years", "integer",
                minValue=5, maxValue=25, distribution="normal")
    .build()
)
```

### Multi-Sensor Time-Series

Based on industrial vibration monitoring patterns (wind turbine / CNC spindle).
Six sensors with different signal characteristics: pure noise, sine + noise,
and varying frequency/amplitude.

| Column | Type | Description | Generation Pattern |
|--------|------|-------------|-------------------|
| `reading_id` | LONG | Primary key | Unique |
| `equipment_id` | LONG | Equipment FK | Match range |
| `timestamp` | TIMESTAMP | Reading time | 10-second interval |
| `sensor_A` | DOUBLE | No sine, low noise (sigma=1) | Normal distribution |
| `sensor_B` | DOUBLE | No sine, medium noise (sigma=2) | Normal distribution |
| `sensor_C` | DOUBLE | No sine, high noise (sigma=3) | Normal distribution |
| `sensor_D` | DOUBLE | Slow sine + noise (step=0.1, sigma=1.5) | Sine wave + noise |
| `sensor_E` | DOUBLE | Very slow sine + noise (step=0.01, sigma=2) | Sine wave + noise |
| `sensor_F` | DOUBLE | Fast sine + low noise (step=0.2, sigma=1) | Sine wave + noise |
| `energy` | FLOAT | Power output 0-100 | Random, 0.5% nulls |
| `is_anomaly` | BOOLEAN | Anomaly flag | Derived from sensor thresholds |

**Sensor signal formulas:**
- Pure noise sensors: `(rand() * 2 - 1) * sigma`
- Sine + noise sensors: `2 * exp(sin(step * reading_id)) + (rand() * 2*sigma - sigma)`

```python
sensor_data = (
    dg.DataGenerator(spark, rows=10_000_000, partitions=50)
    .withColumn("reading_id", "long", minValue=1, uniqueValues=10_000_000)
    .withColumn("equipment_id", "long", minValue=1000, maxValue=1999)
    .withColumn("timestamp", "timestamp",
                begin="2024-01-01", end="2024-12-31", interval="10 seconds")

    # Fault injection: first 10% of equipment IDs are faulty
    .withColumn("is_faulty_equipment", "boolean", expr="equipment_id <= 1099", omit=True)
    .withColumn("is_outlier_reading", "boolean",
                expr="is_faulty_equipment and rand() < 0.15", omit=True)
    .withColumn("outlier_multiplier", "double",
                expr="case when is_outlier_reading then 8 + rand() * 12 else 1.0 end", omit=True)

    # Sensor channels
    .withColumn("sensor_A", "double",
                expr="(rand() * 2 - 1) * 1 * outlier_multiplier")
    .withColumn("sensor_D", "double",
                expr="(2 * exp(sin(0.1 * reading_id)) + (rand() * 3 - 1.5)) * outlier_multiplier")

    # Anomaly detection
    .withColumn("is_anomaly", "boolean",
                expr="abs(sensor_A) > 9 OR abs(sensor_D) > 12")

    # Energy with null gaps for damaged sensors
    .withColumn("energy", "float", minValue=0, maxValue=100, random=True, percentNulls=0.005)
    .build()
)
```

### Maintenance Records

| Column | Type | Description | Generation Pattern |
|--------|------|-------------|-------------------|
| `maintenance_id` | LONG | Primary key | Unique |
| `equipment_id` | LONG | Equipment FK | Match range |
| `scheduled_date` | TIMESTAMP | Planned date | Random in range |
| `completion_date` | TIMESTAMP | Actual completion | scheduled + duration, 12% nulls |
| `maintenance_type` | STRING | Work category | Preventive 50%, Corrective 30%, Predictive 15%, Emergency 5% |
| `priority` | STRING | Priority level | Critical 5%, High 20%, Medium 50%, Low 25% |
| `duration_hours` | INTEGER | Work duration | 1-72, exponential |
| `cost` | DECIMAL(12,2) | Total cost | 100-50000, exponential |
| `technician_id` | LONG | Assigned tech | 100-200 |
| `description` | STRING | Work order text | Prefix: "WO-" + equipment_id |
| `status` | STRING | Order status | Completed 80%, In Progress 10%, Scheduled 8%, Cancelled 2% |
| `parts_replaced` | INTEGER | Parts count | 0-10, exponential |

```python
maintenance = (
    dg.DataGenerator(spark, rows=50_000, partitions=10)
    .withColumn("maintenance_id", "long", minValue=1, uniqueValues=50_000)
    .withColumn("equipment_id", "long", minValue=1000, maxValue=1999)
    .withColumn("scheduled_date", "timestamp",
                begin="2024-01-01", end="2024-12-31", random=True)
    .withColumn("los_hours", "integer", minValue=1, maxValue=72,
                distribution="exponential", omit=True)
    .withColumn("completion_date", "timestamp",
                expr="scheduled_date + interval los_hours hours", percentNulls=0.12)
    .withColumn("maintenance_type", "string",
                values=["Preventive", "Corrective", "Predictive", "Emergency"],
                weights=[50, 30, 15, 5])
    .withColumn("priority", "string",
                values=["Critical", "High", "Medium", "Low"],
                weights=[5, 20, 50, 25])
    .withColumn("duration_hours", "integer",
                minValue=1, maxValue=72, distribution="exponential")
    .withColumn("cost", "decimal(12,2)",
                minValue=100, maxValue=50000, distribution="exponential")
    .withColumn("technician_id", "long", minValue=100, maxValue=200)
    .withColumn("description", "string", prefix="WO-", baseColumn="equipment_id")
    .withColumn("status", "string",
                values=["Completed", "In Progress", "Scheduled", "Cancelled"],
                weights=[80, 10, 8, 2])
    .withColumn("parts_replaced", "integer",
                minValue=0, maxValue=10, distribution="exponential")
    .build()
)
```

## Fault Injection Patterns

### Faulty Equipment Designation

A configurable fraction of equipment (default 10%) is designated as faulty.
Faulty equipment produces outlier sensor readings 15% of the time, with the
signal amplitude multiplied by 8-20x:

```python
# First 10% of equipment IDs are faulty
.withColumn("is_faulty_equipment", "boolean",
            expr="equipment_id <= 1099", omit=True)

# 15% of readings from faulty equipment are outliers
.withColumn("is_outlier_reading", "boolean",
            expr="is_faulty_equipment and rand() < 0.15", omit=True)

# Outlier multiplier: 8-20x normal sigma
.withColumn("outlier_multiplier", "double",
            expr="case when is_outlier_reading then 8 + rand() * 12 else 1.0 end",
            omit=True)
```

### Damaged Sensor Gaps

Simulate intermittent sensor failures with `percentNulls`:

```python
# 0.5% null rate on energy readings = damaged/disconnected power sensor
.withColumn("energy", "float", minValue=0, maxValue=100,
            random=True, percentNulls=0.005)
```

## Energy / OEE Metrics

### Overall Equipment Effectiveness (OEE)

OEE = Availability x Performance x Quality

```python
# Compute OEE per equipment per day
oee = (
    sensor_data
    .groupBy("equipment_id", F.date_trunc("day", "timestamp").alias("day"))
    .agg(
        # Availability: fraction of non-null energy readings
        (1 - F.count(F.when(F.col("energy").isNull(), 1)) / F.count("*")).alias("availability"),
        # Performance: avg energy / max possible energy
        (F.avg("energy") / 100.0).alias("performance"),
        # Quality: fraction of non-anomalous readings
        (1 - F.sum(F.col("is_anomaly").cast("int")) / F.count("*")).alias("quality"),
    )
    .withColumn("oee", F.col("availability") * F.col("performance") * F.col("quality"))
)
```

### Energy Consumption Patterns

```python
# Time-of-day energy usage pattern for manufacturing
.withColumn("hour", "integer", expr="hour(timestamp)", omit=True)
.withColumn("shift_factor", "double", expr="""case
    when hour between 6 and 14 then 1.0    -- Day shift (full capacity)
    when hour between 14 and 22 then 0.85  -- Swing shift
    else 0.3                               -- Night shift (skeleton crew)
end""")
```

## Silver Layer Patterns

### Hourly Sensor Aggregation

Roll up 10-second readings into hourly windows for anomaly detection:

```sql
SELECT
    equipment_id,
    date_trunc('hour', timestamp) AS hour,
    AVG(sensor_A) AS avg_sensor_A,
    STDDEV(sensor_A) AS stddev_sensor_A,
    AVG(sensor_D) AS avg_sensor_D,
    STDDEV(sensor_D) AS stddev_sensor_D,
    PERCENTILE_APPROX(sensor_A, 0.99) AS p99_sensor_A,
    PERCENTILE_APPROX(sensor_D, 0.99) AS p99_sensor_D,
    AVG(energy) AS avg_energy,
    SUM(CAST(is_anomaly AS INT)) AS anomaly_count,
    COUNT(*) AS reading_count
FROM sensor_data
GROUP BY equipment_id, date_trunc('hour', timestamp)
```

### Maintenance Event Enrichment

Join maintenance records with equipment metadata:

```sql
SELECT
    m.maintenance_id,
    m.equipment_id,
    e.equipment_type,
    e.location_zone,
    m.maintenance_type,
    m.priority,
    m.cost,
    m.duration_hours,
    m.status,
    DATEDIFF(m.scheduled_date, e.last_maintenance_date) AS days_since_last_maintenance
FROM maintenance_records m
JOIN equipment e ON m.equipment_id = e.equipment_id
```

## Gold Layer Patterns

### ML Training Dataset: Failure Prediction

Build a training set with sensor feature vectors and failure labels:

```sql
-- Rolling window features for each equipment + hour
WITH hourly_features AS (
    SELECT
        equipment_id,
        date_trunc('hour', timestamp) AS hour,
        AVG(sensor_A) AS avg_A, STDDEV(sensor_A) AS std_A,
        AVG(sensor_B) AS avg_B, STDDEV(sensor_B) AS std_B,
        AVG(sensor_C) AS avg_C, STDDEV(sensor_C) AS std_C,
        AVG(sensor_D) AS avg_D, STDDEV(sensor_D) AS std_D,
        AVG(sensor_E) AS avg_E, STDDEV(sensor_E) AS std_E,
        AVG(sensor_F) AS avg_F, STDDEV(sensor_F) AS std_F,
        AVG(energy) AS avg_energy,
        SUM(CAST(is_anomaly AS INT)) AS anomaly_count
    FROM sensor_data
    GROUP BY equipment_id, date_trunc('hour', timestamp)
),
-- Label: did the equipment have a corrective/emergency maintenance within 24h?
failures AS (
    SELECT equipment_id, scheduled_date
    FROM maintenance_records
    WHERE maintenance_type IN ('Corrective', 'Emergency')
)
SELECT
    hf.*,
    CASE WHEN f.equipment_id IS NOT NULL THEN 1 ELSE 0 END AS failure_label
FROM hourly_features hf
LEFT JOIN failures f
    ON hf.equipment_id = f.equipment_id
    AND f.scheduled_date BETWEEN hf.hour AND hf.hour + INTERVAL 24 HOURS
```

### Sensor Feature Arrays

Pack multi-sensor readings into arrays for ML model input:

```python
from pyspark.sql import functions as F

training_df = (
    hourly_features
    .withColumn("sensor_vector", F.array(
        "avg_A", "std_A", "avg_B", "std_B", "avg_C", "std_C",
        "avg_D", "std_D", "avg_E", "std_E", "avg_F", "std_F",
        "avg_energy", "anomaly_count"
    ))
)
```

## Common Metrics

### MTBF (Mean Time Between Failures)

```sql
WITH failure_events AS (
    SELECT
        equipment_id,
        scheduled_date,
        LAG(scheduled_date) OVER (
            PARTITION BY equipment_id ORDER BY scheduled_date
        ) AS prev_failure_date
    FROM maintenance_records
    WHERE maintenance_type IN ('Corrective', 'Emergency')
)
SELECT
    e.equipment_type,
    AVG(DATEDIFF(scheduled_date, prev_failure_date)) AS mtbf_days,
    COUNT(*) AS failure_count
FROM failure_events f
JOIN equipment e ON f.equipment_id = e.equipment_id
WHERE prev_failure_date IS NOT NULL
GROUP BY e.equipment_type
ORDER BY mtbf_days
```

### MTTR (Mean Time To Repair)

```sql
SELECT
    e.equipment_type,
    m.maintenance_type,
    AVG(m.duration_hours) AS mttr_hours,
    PERCENTILE_APPROX(m.duration_hours, 0.5) AS median_repair_hours,
    AVG(m.cost) AS avg_cost
FROM maintenance_records m
JOIN equipment e ON m.equipment_id = e.equipment_id
WHERE m.status = 'Completed'
GROUP BY e.equipment_type, m.maintenance_type
ORDER BY e.equipment_type, m.maintenance_type
```

## CDC Generation

```python
def generate_manufacturing_cdc(spark, volume_path, n_equipment=1_000, n_batches=5, seed=42):
    """Generate manufacturing CDC data -- equipment status and maintenance updates."""
    from generators.cdc import add_cdc_operations, write_cdc_to_volume

    for i in range(n_batches):
        rows = n_equipment if i == 0 else n_equipment // 5
        base_df = generate_equipment(spark, rows=rows, seed=seed + i)
        weights = {"APPEND": 100} if i == 0 else {"APPEND": 30, "UPDATE": 60, "DELETE": 5}
        cdc_df = add_cdc_operations(base_df, weights=weights)
        write_cdc_to_volume(cdc_df, volume_path, batch_id=i)
```

## Data Quality Injection

```python
# Manufacturing-appropriate quality issues

# Damaged sensor gaps (0.5% null rate on energy readings)
.withColumn("energy", "float", minValue=0, maxValue=100,
            random=True, percentNulls=0.005)

# Completion date nulls (12% -- in-progress or scheduled work orders)
.withColumn("completion_date", "timestamp",
            expr="scheduled_date + interval los_hours hours",
            percentNulls=0.12)

# Duplicate sensor readings (network retransmission: 0.5%)
clean_sensor = generate_sensor_data(spark, n_rows)
sensor_with_dupes = clean_sensor.union(clean_sensor.sample(0.005))
```

## Medallion Output

```python
# Write raw data to Volumes for bronze ingestion
equipment_df.write.format("json").save(f"/Volumes/{catalog}/{schema}/{volume}/equipment")
sensor_data_df.write.format("json").save(f"/Volumes/{catalog}/{schema}/{volume}/sensor_data")
maintenance_df.write.format("json").save(f"/Volumes/{catalog}/{schema}/{volume}/maintenance_records")
```

## Complete Manufacturing Demo

```python
def generate_manufacturing_demo(
    spark,
    n_equipment: int = 1_000,
    catalog: str = "demo",
    schema: str = "manufacturing"
):
    """Generate complete manufacturing demo dataset."""

    equipment = generate_equipment(spark, rows=n_equipment)
    sensor_data = generate_sensor_data(spark, rows=n_equipment * 5000, n_equipment=n_equipment)
    maintenance = generate_maintenance_records(spark, rows=n_equipment * 50, n_equipment=n_equipment)

    tables = {
        "equipment": equipment,
        "sensor_data": sensor_data,
        "maintenance_records": maintenance,
    }

    for name, df in tables.items():
        df.write.format("delta").mode("overwrite").saveAsTable(f"{catalog}.{schema}.{name}")

    return tables
```

## Common Demo Queries

### Equipment Health Dashboard

```sql
SELECT
    e.equipment_type,
    e.status,
    COUNT(*) AS equipment_count,
    AVG(e.expected_lifespan_years) AS avg_lifespan,
    AVG(DATEDIFF(current_date(), e.install_date) / 365.0) AS avg_age_years
FROM equipment e
GROUP BY e.equipment_type, e.status
ORDER BY e.equipment_type, e.status
```

### Anomaly Rate by Equipment Type

```sql
SELECT
    e.equipment_type,
    e.location_zone,
    COUNT(*) AS total_readings,
    SUM(CAST(s.is_anomaly AS INT)) AS anomaly_count,
    ROUND(SUM(CAST(s.is_anomaly AS INT)) / COUNT(*) * 100, 2) AS anomaly_pct
FROM sensor_data s
JOIN equipment e ON s.equipment_id = e.equipment_id
GROUP BY e.equipment_type, e.location_zone
HAVING anomaly_count > 0
ORDER BY anomaly_pct DESC
```

### Maintenance Cost Analysis

```sql
SELECT
    e.equipment_type,
    m.maintenance_type,
    COUNT(*) AS work_order_count,
    SUM(m.cost) AS total_cost,
    AVG(m.cost) AS avg_cost,
    AVG(m.duration_hours) AS avg_duration
FROM maintenance_records m
JOIN equipment e ON m.equipment_id = e.equipment_id
WHERE m.status = 'Completed'
GROUP BY e.equipment_type, m.maintenance_type
ORDER BY total_cost DESC
```

### Predictive Maintenance Candidates

```sql
SELECT
    e.equipment_id,
    e.equipment_type,
    e.location_zone,
    DATEDIFF(current_date(), e.last_maintenance_date) AS days_since_maintenance,
    anomalies.recent_anomaly_count,
    anomalies.avg_energy
FROM equipment e
JOIN (
    SELECT
        equipment_id,
        SUM(CAST(is_anomaly AS INT)) AS recent_anomaly_count,
        AVG(energy) AS avg_energy
    FROM sensor_data
    WHERE timestamp >= current_date() - INTERVAL 7 DAYS
    GROUP BY equipment_id
) anomalies ON e.equipment_id = anomalies.equipment_id
WHERE e.status = 'Operational'
    AND anomalies.recent_anomaly_count > 50
ORDER BY anomalies.recent_anomaly_count DESC
```

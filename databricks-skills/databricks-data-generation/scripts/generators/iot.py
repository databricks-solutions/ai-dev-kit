"""IoT and telematics synthetic data generators.

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
from dbldatagen.constraints import PositiveValues, RangedValues
from pyspark.sql import DataFrame


def generate_devices(spark, rows=10_000, seed=42) -> DataFrame:
    """Generate IoT device registry with metadata and geolocation."""
    partitions = max(2, rows // 10_000)
    device_types = [
        "Temperature Sensor", "Humidity Sensor", "Pressure Sensor",
        "Motion Detector", "Smart Meter", "GPS Tracker", "Camera", "HVAC Controller",
    ]

    return (
        dg.DataGenerator(spark, rows=rows, partitions=partitions, randomSeed=seed)
        .withColumn("device_id", "long", minValue=1000, uniqueValues=rows)
        .withColumn("device_serial", "string", template=r"DEV-dddddddd")
        .withColumn("device_type", "string", values=device_types)
        .withColumn("manufacturer", "string",
                    values=["SensorCorp", "IoTech", "SmartDevices",
                            "TelcoSystems", "DataSense"])
        .withColumn("install_date", "date",
                    begin="2020-01-01", end="2024-12-31", random=True)
        .withColumn("latitude", "double", minValue=25.0, maxValue=48.0, random=True)
        .withColumn("longitude", "double", minValue=-125.0, maxValue=-70.0, random=True)
        .withColumn("status", "string",
                    values=["Online", "Offline", "Maintenance", "Decommissioned"],
                    weights=[85, 8, 5, 2])
        .build()
    )


def generate_sensor_readings(spark, rows=50_000_000, n_devices=10_000,
                             start_date="2024-01-01 00:00:00",
                             end_date="2024-12-31 23:59:59",
                             interval="1 minute", anomaly_rate=0.02,
                             seed=42) -> DataFrame:
    """Generate sensor reading time-series with sine wave patterns and anomaly injection.

    Temperature and power readings follow daily/annual sinusoidal cycles.
    Anomalies are injected at the specified rate with 1.5-2.5x amplification.
    """
    partitions = max(50, rows // 1_000_000)
    return (
        dg.DataGenerator(spark, rows=rows, partitions=partitions, randomSeed=seed)
        .withColumn("reading_id", "long", minValue=1, uniqueValues=rows)
        .withColumn("device_id", "long", minValue=1000, maxValue=1000 + n_devices - 1)
        .withColumn("timestamp", "timestamp",
                    begin=start_date, end=end_date, interval=interval)
        .withColumn("metric_name", "string",
                    values=["temperature", "humidity", "pressure", "power", "vibration"])
        # Daily + annual sinusoidal cycles for temperature-like metrics
        .withColumn("hour", "integer", expr="hour(timestamp)", omit=True)
        .withColumn("day_of_year", "integer", expr="dayofyear(timestamp)", omit=True)
        .withColumn("daily_cycle", "double",
                    expr="5 * sin(2 * pi() * (hour - 6) / 24)", omit=True)
        .withColumn("annual_cycle", "double",
                    expr="15 * sin(2 * pi() * (day_of_year - 80) / 365)", omit=True)
        # Base value varies by metric type with sinusoidal modulation
        .withColumn("base_value", "double", expr="""CASE metric_name
            WHEN 'temperature' THEN 20 + annual_cycle + daily_cycle
            WHEN 'humidity' THEN 60 + 15 * sin(2 * pi() * day_of_year / 365)
            WHEN 'pressure' THEN 1013 + 10 * sin(2 * pi() * day_of_year / 365)
            WHEN 'power' THEN 50 + 20 * sin(2 * pi() * (hour - 8) / 24)
            WHEN 'vibration' THEN 5 + 2 * sin(0.1 * reading_id)
            ELSE 50
        END""", omit=True)
        .withColumn("noise", "double", expr="rand() * 5 - 2.5", omit=True)
        .withColumn("is_anomaly", "boolean", expr=f"rand() < {anomaly_rate}")
        .withColumn("anomaly_factor", "double",
                    expr="CASE WHEN is_anomaly THEN 1.5 + rand() ELSE 1.0 END", omit=True)
        .withColumn("metric_value", "double",
                    expr="(base_value + noise) * anomaly_factor",
                    percentNulls=0.005)
        .withColumn("unit", "string", expr="""CASE metric_name
            WHEN 'temperature' THEN 'celsius'
            WHEN 'humidity' THEN 'percent'
            WHEN 'pressure' THEN 'hPa'
            WHEN 'power' THEN 'kWh'
            WHEN 'vibration' THEN 'mm/s'
            ELSE 'unknown'
        END""")
        .withColumn("quality_score", "integer", minValue=80, maxValue=100,
                    distribution=dg.distributions.Beta(alpha=5, beta=2))
        .withConstraint(PositiveValues(columns="quality_score"))
        .build()
    )


def generate_events(spark, rows=100_000, n_devices=10_000, seed=42) -> DataFrame:
    """Generate device events (alerts, maintenance, status changes)."""
    partitions = max(4, rows // 10_000)
    event_types = [
        "Threshold Exceeded", "Device Offline", "Firmware Update",
        "Calibration Required", "Battery Low", "Connection Lost", "Maintenance Due",
    ]

    return (
        dg.DataGenerator(spark, rows=rows, partitions=partitions, randomSeed=seed)
        .withColumn("event_id", "long", minValue=1, uniqueValues=rows)
        .withColumn("device_id", "long", minValue=1000, maxValue=1000 + n_devices - 1)
        .withColumn("timestamp", "timestamp",
                    begin="2024-01-01 00:00:00", end="2024-12-31 23:59:59", random=True)
        .withColumn("event_type", "string", values=event_types)
        .withColumn("severity", "string",
                    values=["Critical", "Warning", "Info"], weights=[10, 30, 60])
        .withColumn("description", "string",
                    prefix="Event on device ", baseColumn="device_id",
                    percentNulls=0.05)
        .withColumn("acknowledged", "boolean", expr="rand() < 0.7")
        .withColumn("resolved", "boolean", expr="acknowledged and rand() < 0.8")
        .build()
    )


def generate_telemetry(spark, rows=5_000_000, n_devices=1_000,
                       start_date="2024-01-01 00:00:00",
                       end_date="2024-12-31 23:59:59",
                       interval="5 seconds", seed=42) -> DataFrame:
    """Generate GPS/vehicle telemetry data (device_id subset 1000-1999)."""
    partitions = max(20, rows // 500_000)
    return (
        dg.DataGenerator(spark, rows=rows, partitions=partitions, randomSeed=seed)
        .withColumn("telemetry_id", "long", minValue=1, uniqueValues=rows)
        .withColumn("device_id", "long", minValue=1000, maxValue=1000 + n_devices - 1)
        .withColumn("timestamp", "timestamp",
                    begin=start_date, end=end_date, interval=interval)
        .withColumn("base_lat", "double", minValue=37.0, maxValue=38.0,
                    random=True, omit=True)
        .withColumn("base_lon", "double", minValue=-122.5, maxValue=-121.5,
                    random=True, omit=True)
        .withColumn("lat_drift", "double", expr="rand() * 0.01 - 0.005", omit=True)
        .withColumn("lon_drift", "double", expr="rand() * 0.01 - 0.005", omit=True)
        .withColumn("latitude", "double", expr="base_lat + lat_drift")
        .withColumn("longitude", "double", expr="base_lon + lon_drift")
        .withColumn("speed", "double", minValue=0, maxValue=80, random=True)
        .withColumn("heading", "integer", minValue=0, maxValue=359, random=True)
        .withColumn("fuel_level", "double", minValue=10, maxValue=100,
                    random=True, percentNulls=0.02)
        .withColumn("engine_temp", "double", minValue=180, maxValue=220,
                    distribution=dg.distributions.Normal(0.0, 1.0), percentNulls=0.01)
        .withConstraint(RangedValues(columns="speed", lowValue=0, highValue=200))
        .withConstraint(RangedValues(columns="heading", lowValue=0, highValue=359))
        .build()
    )


def generate_streaming_sensors(spark, n_devices=1_000, seed=42) -> DataFrame:
    """Generate a streaming-compatible DataFrame of IoT sensor readings.

    Uses rate source for real-time sensor data simulation.
    """
    from pyspark.sql import functions as F

    metrics = ["temperature", "humidity", "pressure", "power", "vibration"]
    units = ["celsius", "percent", "hPa", "kWh", "mm/s"]

    return (
        spark.readStream
        .format("rate")
        .option("rowsPerSecond", 500)
        .load()
        .withColumn("reading_id", F.col("value"))
        .withColumn("device_id",
                    (F.rand() * n_devices).cast("long") + 1000)
        .withColumn("metric_idx", (F.rand() * len(metrics)).cast("int"))
        .withColumn("metric_name",
                    F.element_at(
                        F.array(*[F.lit(m) for m in metrics]),
                        F.col("metric_idx") + 1))
        .withColumn("metric_value", F.rand() * 100)
        .withColumn("unit",
                    F.element_at(
                        F.array(*[F.lit(u) for u in units]),
                        F.col("metric_idx") + 1))
        .withColumn("is_anomaly", F.rand() < 0.02)
        .drop("value", "metric_idx")
    )


def generate_iot_cdc(spark, volume_path, n_devices=10_000, n_batches=5, seed=42):
    """Generate IoT device CDC data and write to UC Volume."""
    from .cdc import add_cdc_operations, write_cdc_to_volume

    for i in range(n_batches):
        rows = n_devices if i == 0 else n_devices // 5
        base_df = generate_devices(spark, rows=rows, seed=seed + i)
        weights = {"APPEND": 100} if i == 0 else {"APPEND": 30, "UPDATE": 60, "DELETE": 5}
        cdc_df = add_cdc_operations(base_df, weights=weights)
        write_cdc_to_volume(cdc_df, volume_path, batch_id=i)


def generate_iot_demo(spark, catalog, schema="iot", volume="raw_data",
                      n_devices=10_000, seed=42):
    """Generate complete IoT demo dataset with all tables."""
    from ..utils.output import write_medallion

    devices = generate_devices(spark, rows=n_devices, seed=seed)
    sensor_readings = generate_sensor_readings(spark, rows=n_devices * 5000,
                                               n_devices=n_devices, seed=seed)
    events = generate_events(spark, rows=n_devices * 10, n_devices=n_devices, seed=seed)
    telemetry = generate_telemetry(spark, rows=min(n_devices, 1000) * 5000,
                                   n_devices=min(n_devices, 1000), seed=seed)

    write_medallion(
        tables={
            "devices": devices,
            "sensor_readings": sensor_readings,
            "events": events,
            "telemetry": telemetry,
        },
        catalog=catalog,
        schema=schema,
        volume=volume,
    )

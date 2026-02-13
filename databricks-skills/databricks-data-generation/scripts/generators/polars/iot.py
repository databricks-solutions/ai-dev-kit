"""IoT and telematics synthetic data generators (Polars + Mimesis).

REFERENCE IMPLEMENTATION — This file is not an importable module. Claude reads it
for patterns and adapts the code inline for user scripts. Uses pure Polars + Mimesis
for Tier 1 local generation (<100K rows, zero JVM overhead).
"""

import math
import random
from datetime import date, datetime, timedelta

import polars as pl

DEVICE_TYPES = [
    "Temperature Sensor", "Humidity Sensor", "Pressure Sensor",
    "Motion Detector", "Smart Meter", "GPS Tracker", "Camera", "HVAC Controller",
]
MANUFACTURERS = ["SensorCorp", "IoTech", "SmartDevices", "TelcoSystems", "DataSense"]
METRICS = ["temperature", "humidity", "pressure", "power", "vibration"]
UNITS = {"temperature": "celsius", "humidity": "percent", "pressure": "hPa",
         "power": "kWh", "vibration": "mm/s"}
EVENT_TYPES = [
    "Threshold Exceeded", "Device Offline", "Firmware Update",
    "Calibration Required", "Battery Low", "Connection Lost", "Maintenance Due",
]


def generate_devices(rows: int = 1_000, seed: int = 42) -> pl.DataFrame:
    """Generate IoT device registry with metadata and geolocation."""
    random.seed(seed)

    install_start = date(2020, 1, 1)
    install_range = (date(2024, 12, 31) - install_start).days

    device_ids = list(range(1000, 1000 + rows))
    device_serials = [f"DEV-{random.randint(10000000, 99999999)}" for _ in range(rows)]
    device_types = random.choices(DEVICE_TYPES, k=rows)
    manufacturers = random.choices(MANUFACTURERS, k=rows)
    install_dates = [install_start + timedelta(days=random.randint(0, install_range))
                     for _ in range(rows)]
    latitudes = [random.uniform(25.0, 48.0) for _ in range(rows)]
    longitudes = [random.uniform(-125.0, -70.0) for _ in range(rows)]
    statuses = random.choices(
        ["Online", "Offline", "Maintenance", "Decommissioned"],
        weights=[85, 8, 5, 2], k=rows
    )

    return pl.DataFrame({
        "device_id": device_ids,
        "device_serial": device_serials,
        "device_type": device_types,
        "manufacturer": manufacturers,
        "install_date": install_dates,
        "latitude": latitudes,
        "longitude": longitudes,
        "status": statuses,
    })


def generate_sensor_readings(rows: int = 50_000, n_devices: int = 1_000,
                             anomaly_rate: float = 0.02,
                             seed: int = 42) -> pl.DataFrame:
    """Generate sensor reading time-series with sine wave patterns and anomaly injection.

    Temperature and power readings follow daily/annual sinusoidal cycles.
    Anomalies are injected at the specified rate with 1.5-2.5x amplification.
    """
    random.seed(seed)

    ts_start = datetime(2024, 1, 1)
    ts_range = int((datetime(2024, 12, 31, 23, 59, 59) - ts_start).total_seconds())

    reading_ids = list(range(1, rows + 1))
    device_ids = [random.randint(1000, 1000 + n_devices - 1) for _ in range(rows)]
    timestamps = [ts_start + timedelta(seconds=random.randint(0, ts_range))
                  for _ in range(rows)]
    metric_names = random.choices(METRICS, k=rows)
    is_anomalies = [random.random() < anomaly_rate for _ in range(rows)]

    metric_values = []
    quality_scores = []
    units = []

    for i in range(rows):
        ts = timestamps[i]
        hour = ts.hour
        day_of_year = ts.timetuple().tm_yday
        metric = metric_names[i]
        is_anom = is_anomalies[i]

        daily_cycle = 5 * math.sin(2 * math.pi * (hour - 6) / 24)
        annual_cycle = 15 * math.sin(2 * math.pi * (day_of_year - 80) / 365)
        noise = random.uniform(-2.5, 2.5)

        if metric == "temperature":
            base = 20 + annual_cycle + daily_cycle
        elif metric == "humidity":
            base = 60 + 15 * math.sin(2 * math.pi * day_of_year / 365)
        elif metric == "pressure":
            base = 1013 + 10 * math.sin(2 * math.pi * day_of_year / 365)
        elif metric == "power":
            base = 50 + 20 * math.sin(2 * math.pi * (hour - 8) / 24)
        else:  # vibration
            base = 5 + 2 * math.sin(0.1 * i)

        factor = (1.5 + random.random()) if is_anom else 1.0
        val = (base + noise) * factor

        if random.random() < 0.005:
            metric_values.append(None)
        else:
            metric_values.append(round(val, 4))

        quality_scores.append(
            max(80, min(100, int(random.betavariate(5, 2) * 20 + 80)))
        )
        units.append(UNITS[metric])

    return pl.DataFrame({
        "reading_id": reading_ids,
        "device_id": device_ids,
        "timestamp": timestamps,
        "metric_name": metric_names,
        "metric_value": metric_values,
        "unit": units,
        "quality_score": quality_scores,
        "is_anomaly": is_anomalies,
    })


def generate_events(rows: int = 10_000, n_devices: int = 1_000,
                    seed: int = 42) -> pl.DataFrame:
    """Generate device events (alerts, maintenance, status changes)."""
    random.seed(seed)

    ts_start = datetime(2024, 1, 1)
    ts_range = int((datetime(2024, 12, 31, 23, 59, 59) - ts_start).total_seconds())

    event_ids = list(range(1, rows + 1))
    device_ids = [random.randint(1000, 1000 + n_devices - 1) for _ in range(rows)]
    timestamps = [ts_start + timedelta(seconds=random.randint(0, ts_range))
                  for _ in range(rows)]
    event_types = random.choices(EVENT_TYPES, k=rows)
    severities = random.choices(
        ["Critical", "Warning", "Info"], weights=[10, 30, 60], k=rows
    )
    descriptions = [
        None if random.random() < 0.05
        else f"Event on device {did}"
        for did in device_ids
    ]
    acknowledged = [random.random() < 0.7 for _ in range(rows)]
    resolved = [ack and random.random() < 0.8 for ack in acknowledged]

    return pl.DataFrame({
        "event_id": event_ids,
        "device_id": device_ids,
        "timestamp": timestamps,
        "event_type": event_types,
        "severity": severities,
        "description": descriptions,
        "acknowledged": acknowledged,
        "resolved": resolved,
    })


def generate_telemetry(rows: int = 50_000, n_devices: int = 1_000,
                       seed: int = 42) -> pl.DataFrame:
    """Generate GPS/vehicle telemetry data."""
    random.seed(seed)

    ts_start = datetime(2024, 1, 1)
    ts_range = int((datetime(2024, 12, 31, 23, 59, 59) - ts_start).total_seconds())

    telemetry_ids = list(range(1, rows + 1))
    device_ids = [random.randint(1000, 1000 + n_devices - 1) for _ in range(rows)]
    timestamps = [ts_start + timedelta(seconds=random.randint(0, ts_range))
                  for _ in range(rows)]
    base_lats = [random.uniform(37.0, 38.0) for _ in range(rows)]
    base_lons = [random.uniform(-122.5, -121.5) for _ in range(rows)]
    latitudes = [lat + random.uniform(-0.005, 0.005) for lat in base_lats]
    longitudes = [lon + random.uniform(-0.005, 0.005) for lon in base_lons]
    speeds = [random.uniform(0, 80) for _ in range(rows)]
    headings = [random.randint(0, 359) for _ in range(rows)]
    fuel_levels = [
        None if random.random() < 0.02
        else round(random.uniform(10, 100), 1)
        for _ in range(rows)
    ]
    engine_temps = [
        None if random.random() < 0.01
        else round(random.gauss(200, 10), 1)
        for _ in range(rows)
    ]

    return pl.DataFrame({
        "telemetry_id": telemetry_ids,
        "device_id": device_ids,
        "timestamp": timestamps,
        "latitude": latitudes,
        "longitude": longitudes,
        "speed": speeds,
        "heading": headings,
        "fuel_level": fuel_levels,
        "engine_temp": engine_temps,
    })

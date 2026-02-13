"""Manufacturing industry synthetic data generators.

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


def generate_equipment(spark, rows=1_000, seed=42) -> DataFrame:
    """Generate equipment/asset registry for manufacturing floor."""
    partitions = max(2, rows // 10_000)
    equipment_types = [
        "CNC Machine", "Assembly Robot", "Conveyor Belt", "Press",
        "Welder", "Packaging Unit", "Quality Scanner", "HVAC System",
    ]

    return (
        dg.DataGenerator(spark, rows=rows, partitions=partitions, randomSeed=seed)
        .withColumn("equipment_id", "long", minValue=1000, uniqueValues=rows)
        .withColumn("serial_number", "string", template=r"EQ-dddddddd")
        .withColumn("equipment_type", "string", values=equipment_types)
        .withColumn("manufacturer", "string",
                    values=["Siemens", "ABB", "Fanuc", "Bosch", "Honeywell"])
        .withColumn("model", "string", prefix="Model-", baseColumn="equipment_id")
        .withColumn("install_date", "date",
                    begin="2015-01-01", end="2024-12-31", random=True)
        .withColumn("location_zone", "string",
                    values=["Zone A", "Zone B", "Zone C",
                            "Zone D", "Zone E", "Zone F"])
        .withColumn("status", "string",
                    values=["Operational", "Maintenance", "Idle", "Decommissioned"],
                    weights=[80, 10, 7, 3])
        .withColumn("last_maintenance_date", "date",
                    begin="2024-01-01", end="2024-12-31", random=True)
        .withColumn("expected_lifespan_years", "integer",
                    minValue=5, maxValue=25, distribution=dg.distributions.Normal(0.0, 1.0))
        .build()
    )


def generate_sensor_data(spark, rows=10_000_000, n_equipment=1_000,
                         fault_rate=0.10, seed=42) -> DataFrame:
    """Generate multi-sensor time-series with sine wave patterns and fault injection.

    Based on industrial IoT patterns (wind turbine vibration monitoring).
    Faulty equipment (~fault_rate of total) gets 15% outlier readings with
    sigma multiplied by 8-20x.
    """
    partitions = max(50, rows // 1_000_000)

    # fault_rate of equipment IDs are designated faulty.
    # For those, 15% of readings become outliers (sigma * 8..20).
    n_faulty = int(n_equipment * fault_rate)
    faulty_max_id = 1000 + n_faulty - 1  # first N equipment IDs are faulty

    return (
        dg.DataGenerator(spark, rows=rows, partitions=partitions, randomSeed=seed)
        .withColumn("reading_id", "long", minValue=1, uniqueValues=rows)
        .withColumn("equipment_id", "long",
                    minValue=1000, maxValue=1000 + n_equipment - 1)
        .withColumn("timestamp", "timestamp",
                    begin="2024-01-01 00:00:00", end="2024-12-31 23:59:59", interval="10 seconds")

        # --- Fault injection helpers ---
        .withColumn("is_faulty_equipment", "boolean",
                    expr=f"equipment_id <= {faulty_max_id}", omit=True)
        .withColumn("is_outlier_reading", "boolean",
                    expr="is_faulty_equipment and rand() < 0.15", omit=True)
        .withColumn("outlier_multiplier", "double",
                    expr="case when is_outlier_reading then 8 + rand() * 12 else 1.0 end",
                    omit=True)

        # Sensor A: no sine, low noise (sigma=1)
        .withColumn("sensor_A", "double",
                    expr="(rand() * 2 - 1) * 1 * outlier_multiplier")
        # Sensor B: no sine, medium noise (sigma=2)
        .withColumn("sensor_B", "double",
                    expr="(rand() * 2 - 1) * 2 * outlier_multiplier")
        # Sensor C: no sine, high noise (sigma=3)
        .withColumn("sensor_C", "double",
                    expr="(rand() * 2 - 1) * 3 * outlier_multiplier")
        # Sensor D: slow sine (step=0.1) + noise (sigma=1.5)
        .withColumn("sensor_D", "double",
                    expr="(2 * exp(sin(0.1 * reading_id)) + (rand() * 3 - 1.5)) * outlier_multiplier")
        # Sensor E: very slow sine (step=0.01) + noise (sigma=2)
        .withColumn("sensor_E", "double",
                    expr="(2 * exp(sin(0.01 * reading_id)) + (rand() * 4 - 2)) * outlier_multiplier")
        # Sensor F: fast sine (step=0.2) + low noise (sigma=1)
        .withColumn("sensor_F", "double",
                    expr="(2 * exp(sin(0.2 * reading_id)) + (rand() * 2 - 1)) * outlier_multiplier")

        # Energy / power output
        .withColumn("energy", "float", minValue=0, maxValue=100,
                    random=True, percentNulls=0.005)

        # Anomaly detection: any sensor value beyond 3 standard deviations
        .withColumn("is_anomaly", "boolean",
                    expr="abs(sensor_A) > 9 OR abs(sensor_B) > 18 "
                         "OR abs(sensor_C) > 27 OR abs(sensor_D) > 12 "
                         "OR abs(sensor_E) > 15 OR abs(sensor_F) > 12")
        .build()
    )


def generate_maintenance_records(spark, rows=50_000, n_equipment=1_000,
                                 seed=42) -> DataFrame:
    """Generate maintenance work order and event records."""
    partitions = max(4, rows // 10_000)

    return (
        dg.DataGenerator(spark, rows=rows, partitions=partitions, randomSeed=seed)
        .withColumn("maintenance_id", "long", minValue=1, uniqueValues=rows)
        .withColumn("equipment_id", "long",
                    minValue=1000, maxValue=1000 + n_equipment - 1)
        .withColumn("scheduled_date", "timestamp",
                    begin="2024-01-01 00:00:00", end="2024-12-31 23:59:59", random=True)
        .withColumn("los_hours", "integer", minValue=1, maxValue=72,
                    distribution=dg.distributions.Exponential(), omit=True)
        .withColumn("completion_date", "timestamp",
                    expr="scheduled_date + interval los_hours hours",
                    percentNulls=0.12)
        .withColumn("maintenance_type", "string",
                    values=["Preventive", "Corrective", "Predictive", "Emergency"],
                    weights=[50, 30, 15, 5])
        .withColumn("priority", "string",
                    values=["Critical", "High", "Medium", "Low"],
                    weights=[5, 20, 50, 25])
        .withColumn("duration_hours", "integer",
                    minValue=1, maxValue=72, distribution=dg.distributions.Exponential())
        .withColumn("cost", "decimal(12,2)",
                    minValue=100, maxValue=50000, distribution=dg.distributions.Exponential())
        .withColumn("technician_id", "long", minValue=100, maxValue=200)
        .withColumn("description", "string",
                    prefix="WO-", baseColumn="equipment_id")
        .withColumn("status", "string",
                    values=["Completed", "In Progress", "Scheduled", "Cancelled"],
                    weights=[80, 10, 8, 2])
        .withColumn("parts_replaced", "integer",
                    minValue=0, maxValue=10, distribution=dg.distributions.Exponential())
        .withConstraint(PositiveValues(columns="cost"))
        .withConstraint(PositiveValues(columns="duration_hours"))
        .withConstraint(SqlExpr("parts_replaced >= 0"))
        .build()
    )


def generate_manufacturing_cdc(spark, volume_path, n_equipment=1_000,
                               n_batches=5, seed=42):
    """Generate manufacturing CDC data and write to UC Volume."""
    from .cdc import add_cdc_operations, write_cdc_to_volume

    for i in range(n_batches):
        rows = n_equipment if i == 0 else n_equipment // 5
        base_df = generate_equipment(spark, rows=rows, seed=seed + i)
        weights = {"APPEND": 100} if i == 0 else {"APPEND": 30, "UPDATE": 60, "DELETE": 5}
        cdc_df = add_cdc_operations(base_df, weights=weights)
        write_cdc_to_volume(cdc_df, volume_path, batch_id=i)


def generate_manufacturing_demo(spark, catalog, schema="manufacturing",
                                volume="raw_data", n_equipment=1_000, seed=42):
    """Generate complete manufacturing demo dataset with all tables."""
    from ..utils.output import write_medallion

    equipment = generate_equipment(spark, rows=n_equipment, seed=seed)
    sensor_data = generate_sensor_data(spark, rows=n_equipment * 5000,
                                       n_equipment=n_equipment, seed=seed)
    maintenance_records = generate_maintenance_records(spark, rows=n_equipment * 50,
                                                       n_equipment=n_equipment, seed=seed)

    write_medallion(
        tables={
            "equipment": equipment,
            "sensor_data": sensor_data,
            "maintenance_records": maintenance_records,
        },
        catalog=catalog,
        schema=schema,
        volume=volume,
    )

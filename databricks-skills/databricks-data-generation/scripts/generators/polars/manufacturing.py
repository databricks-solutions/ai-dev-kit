"""Manufacturing industry synthetic data generators (Polars + Mimesis).

REFERENCE IMPLEMENTATION — This file is not an importable module. Claude reads it
for patterns and adapts the code inline for user scripts. Uses pure Polars + Mimesis
for Tier 1 local generation (<100K rows, zero JVM overhead).
"""

import math
import random
from datetime import date, datetime, timedelta

import polars as pl

EQUIPMENT_TYPES = [
    "CNC Machine", "Assembly Robot", "Conveyor Belt", "Press",
    "Welder", "Packaging Unit", "Quality Scanner", "HVAC System",
]
EQUIPMENT_MANUFACTURERS = ["Siemens", "ABB", "Fanuc", "Bosch", "Honeywell"]
ZONES = ["Zone A", "Zone B", "Zone C", "Zone D", "Zone E", "Zone F"]
MAINTENANCE_TYPES = ["Preventive", "Corrective", "Predictive", "Emergency"]
MAINTENANCE_TYPE_WEIGHTS = [50, 30, 15, 5]
PRIORITIES = ["Critical", "High", "Medium", "Low"]
PRIORITY_WEIGHTS = [5, 20, 50, 25]


def generate_equipment(rows: int = 500, seed: int = 42) -> pl.DataFrame:
    """Generate equipment/asset registry for manufacturing floor."""
    random.seed(seed)

    install_start = date(2015, 1, 1)
    install_range = (date(2024, 12, 31) - install_start).days
    maint_start = date(2024, 1, 1)
    maint_range = (date(2024, 12, 31) - maint_start).days

    equipment_ids = list(range(1000, 1000 + rows))
    serial_numbers = [f"EQ-{random.randint(10000000, 99999999)}" for _ in range(rows)]
    equipment_types = random.choices(EQUIPMENT_TYPES, k=rows)
    manufacturers = random.choices(EQUIPMENT_MANUFACTURERS, k=rows)
    models = [f"Model-{eid}" for eid in equipment_ids]
    install_dates = [install_start + timedelta(days=random.randint(0, install_range))
                     for _ in range(rows)]
    location_zones = random.choices(ZONES, k=rows)
    statuses = random.choices(
        ["Operational", "Maintenance", "Idle", "Decommissioned"],
        weights=[80, 10, 7, 3], k=rows
    )
    last_maint_dates = [maint_start + timedelta(days=random.randint(0, maint_range))
                        for _ in range(rows)]
    expected_lifespans = [max(5, min(25, int(random.gauss(15, 5))))
                          for _ in range(rows)]

    return pl.DataFrame({
        "equipment_id": equipment_ids,
        "serial_number": serial_numbers,
        "equipment_type": equipment_types,
        "manufacturer": manufacturers,
        "model": models,
        "install_date": install_dates,
        "location_zone": location_zones,
        "status": statuses,
        "last_maintenance_date": last_maint_dates,
        "expected_lifespan_years": expected_lifespans,
    })


def generate_sensor_data(rows: int = 25_000, n_equipment: int = 500,
                         fault_rate: float = 0.10, seed: int = 42) -> pl.DataFrame:
    """Generate multi-sensor time-series with sine wave patterns and fault injection.

    Based on industrial IoT patterns (wind turbine vibration monitoring).
    Faulty equipment (~fault_rate of total) gets 15% outlier readings with
    sigma multiplied by 8-20x.
    """
    random.seed(seed)

    ts_start = datetime(2024, 1, 1)
    ts_range = int((datetime(2024, 12, 31, 23, 59, 59) - ts_start).total_seconds())
    n_faulty = int(n_equipment * fault_rate)
    faulty_max_id = 1000 + n_faulty - 1

    reading_ids = list(range(1, rows + 1))
    equipment_ids = [random.randint(1000, 1000 + n_equipment - 1) for _ in range(rows)]
    timestamps = [ts_start + timedelta(seconds=random.randint(0, ts_range))
                  for _ in range(rows)]

    sensor_a = []
    sensor_b = []
    sensor_c = []
    sensor_d = []
    sensor_e = []
    sensor_f = []
    energy = []
    is_anomaly = []

    for i in range(rows):
        eid = equipment_ids[i]
        is_faulty = eid <= faulty_max_id
        is_outlier = is_faulty and random.random() < 0.15
        mult = (8 + random.random() * 12) if is_outlier else 1.0

        sa = (random.uniform(-1, 1) * 1) * mult
        sb = (random.uniform(-1, 1) * 2) * mult
        sc = (random.uniform(-1, 1) * 3) * mult
        sd = (2 * math.exp(math.sin(0.1 * i)) + random.uniform(-1.5, 1.5)) * mult
        se = (2 * math.exp(math.sin(0.01 * i)) + random.uniform(-2, 2)) * mult
        sf = (2 * math.exp(math.sin(0.2 * i)) + random.uniform(-1, 1)) * mult

        sensor_a.append(round(sa, 4))
        sensor_b.append(round(sb, 4))
        sensor_c.append(round(sc, 4))
        sensor_d.append(round(sd, 4))
        sensor_e.append(round(se, 4))
        sensor_f.append(round(sf, 4))

        en = random.uniform(0, 100) if random.random() >= 0.005 else None
        energy.append(round(en, 2) if en is not None else None)

        anom = (abs(sa) > 9 or abs(sb) > 18 or abs(sc) > 27
                or abs(sd) > 12 or abs(se) > 15 or abs(sf) > 12)
        is_anomaly.append(anom)

    return pl.DataFrame({
        "reading_id": reading_ids,
        "equipment_id": equipment_ids,
        "timestamp": timestamps,
        "sensor_A": sensor_a,
        "sensor_B": sensor_b,
        "sensor_C": sensor_c,
        "sensor_D": sensor_d,
        "sensor_E": sensor_e,
        "sensor_F": sensor_f,
        "energy": energy,
        "is_anomaly": is_anomaly,
    })


def generate_maintenance_records(rows: int = 5_000, n_equipment: int = 500,
                                 seed: int = 42) -> pl.DataFrame:
    """Generate maintenance work order and event records."""
    random.seed(seed)

    ts_start = datetime(2024, 1, 1)
    ts_range = int((datetime(2024, 12, 31, 23, 59, 59) - ts_start).total_seconds())

    maintenance_ids = list(range(1, rows + 1))
    equipment_ids = [random.randint(1000, 1000 + n_equipment - 1) for _ in range(rows)]
    scheduled_dates = [ts_start + timedelta(seconds=random.randint(0, ts_range))
                       for _ in range(rows)]
    los_hours = [max(1, int(random.expovariate(0.05))) for _ in range(rows)]
    completion_dates = [
        None if random.random() < 0.12
        else sched + timedelta(hours=min(los, 72))
        for sched, los in zip(scheduled_dates, los_hours)
    ]
    maintenance_types = random.choices(
        MAINTENANCE_TYPES, weights=MAINTENANCE_TYPE_WEIGHTS, k=rows
    )
    priorities = random.choices(PRIORITIES, weights=PRIORITY_WEIGHTS, k=rows)
    duration_hours = [max(1, min(72, int(random.expovariate(0.05))))
                      for _ in range(rows)]
    costs = [round(max(100, random.expovariate(0.0001)), 2)
             for _ in range(rows)]
    costs = [min(c, 50000) for c in costs]
    technician_ids = [random.randint(100, 200) for _ in range(rows)]
    descriptions = [f"WO-{eid}" for eid in equipment_ids]
    statuses = random.choices(
        ["Completed", "In Progress", "Scheduled", "Cancelled"],
        weights=[80, 10, 8, 2], k=rows
    )
    parts_replaced = [max(0, min(10, int(random.expovariate(0.5))))
                      for _ in range(rows)]

    return pl.DataFrame({
        "maintenance_id": maintenance_ids,
        "equipment_id": equipment_ids,
        "scheduled_date": scheduled_dates,
        "completion_date": completion_dates,
        "maintenance_type": maintenance_types,
        "priority": priorities,
        "duration_hours": duration_hours,
        "cost": costs,
        "technician_id": technician_ids,
        "description": descriptions,
        "status": statuses,
        "parts_replaced": parts_replaced,
    })

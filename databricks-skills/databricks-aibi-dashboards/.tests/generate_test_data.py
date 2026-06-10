"""
Generate the `support_cases` test table that the worked example in
`4-examples.md` queries from.

Run this once before creating the example dashboard so the agent (or you,
manually) can render it against real data and visually inspect that the
example is state of the art.

Usage
-----
    # one-time install
    pip install "databricks-connect>=15.0"

    # generate the table
    python databricks-skills/databricks-aibi-dashboards/.tests/generate_test_data.py

Env vars (all optional)
    TEST_CATALOG   default: main
    TEST_SCHEMA    default: dashboard_skill_test
    TEST_TABLE     default: support_cases
    NUM_CASES      default: 5000  (rows in the generated table)
    DATABRICKS_CONFIG_PROFILE  databricks-connect picks this up automatically

After the table is written, the script prints the dataset query you can paste
into a new dashboard, and the next-step CLI command to create the dashboard
from the example JSON.
"""

from __future__ import annotations

import os
import random
from datetime import datetime, timedelta, timezone

from databricks.connect import DatabricksSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    BooleanType,
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

CATALOG = os.environ.get("TEST_CATALOG", "main")
SCHEMA = os.environ.get("TEST_SCHEMA", "dashboard_skill_test")
TABLE = os.environ.get("TEST_TABLE", "support_cases")
NUM_CASES = int(os.environ.get("NUM_CASES", "5000"))

FQN = f"{CATALOG}.{SCHEMA}.{TABLE}"

# Inject a volume spike around a synthetic "Product release 4.1" date so the
# dashboard tells a coherent incident story. ~700 extra cases land in the
# 6 weeks following the release (the annotation in the forecast chart points
# at exactly this date).
RELEASE_DATE = datetime(2026, 2, 16, 9, 0, tzinfo=timezone.utc)  # Monday
SPIKE_CASES = 700
SPIKE_DURATION_WEEKS = 6
# Cases in the spike skew toward Critical/High and a worse satisfaction so the
# pivot + heatmap + map widgets all surface the impact.
SPIKE_PRIORITIES = [("Critical", 0.22), ("High", 0.38), ("Medium", 0.30), ("Low", 0.10)]

# Realistic-ish distributions so the dashboard has meaningful patterns.
PRIORITIES = [("Critical", 0.08), ("High", 0.22), ("Medium", 0.45), ("Low", 0.25)]
CHANNELS = [("Email", 0.45), ("Chat", 0.30), ("Phone", 0.15), ("Web Form", 0.10)]
# A few major US metros — gives the symbol-map a recognizable shape.
CITIES = [
    ("Northeast", 40.7128, -74.0060),   # NYC
    ("Northeast", 42.3601, -71.0589),   # Boston
    ("Mid-Atlantic", 38.9072, -77.0369), # DC
    ("Southeast", 33.7490, -84.3880),    # Atlanta
    ("Southeast", 25.7617, -80.1918),    # Miami
    ("Midwest", 41.8781, -87.6298),     # Chicago
    ("Midwest", 44.9778, -93.2650),     # Minneapolis
    ("South Central", 29.7604, -95.3698), # Houston
    ("South Central", 32.7767, -96.7970), # Dallas
    ("Mountain", 39.7392, -104.9903),    # Denver
    ("West", 37.7749, -122.4194),        # SF
    ("West", 34.0522, -118.2437),        # LA
    ("Pacific Northwest", 47.6062, -122.3321), # Seattle
]


def weighted_choice(pairs: list[tuple[str, float]]) -> str:
    """Pick a label from [(label, weight), ...]."""
    r = random.random()
    cum = 0.0
    for label, w in pairs:
        cum += w
        if r < cum:
            return label
    return pairs[-1][0]


def make_row(idx: int, now: datetime, in_spike: bool = False) -> tuple:
    """Build one synthetic support_cases row.

    Resolution time is sampled by priority — Critical resolves fastest,
    Low takes longer — so the dashboard's "Avg Resolution Hours" KPI
    actually varies by category.

    If `in_spike=True`, the row is part of the post-release surge: opened
    within ~6 weeks after RELEASE_DATE, biased toward Critical/High
    priorities, and with a slightly worse satisfaction baseline.
    """
    if in_spike:
        priority = weighted_choice(SPIKE_PRIORITIES)
    else:
        priority = weighted_choice(PRIORITIES)
    channel = weighted_choice(CHANNELS)
    region, lat_base, lon_base = random.choice(CITIES)
    # Jitter the lat/lon so the bubble map doesn't collapse to 13 points.
    customer_lat = lat_base + random.gauss(0, 0.3)
    customer_lon = lon_base + random.gauss(0, 0.3)

    if in_spike:
        # Cases opened in the SPIKE_DURATION_WEEKS window right after the release,
        # front-loaded (peak in week 1-2, taper by week 6).
        days_after_release = random.triangular(0, SPIKE_DURATION_WEEKS * 7, 7)
        opened_at = RELEASE_DATE + timedelta(days=days_after_release,
                                              hours=random.uniform(0, 24))
    else:
        # Baseline: uniformly over the last 18 months.
        opened_offset_days = random.uniform(0, 540)
        opened_at = now - timedelta(days=opened_offset_days,
                                     hours=random.uniform(0, 24))

    # Resolution time depends on priority. Lognormal so the long tail looks real.
    # Spike cases resolve a bit slower (team overloaded).
    base_hours = {"Critical": 4, "High": 12, "Medium": 36, "Low": 72}[priority]
    if in_spike:
        base_hours *= 1.4
    resolution_hours = max(0.25, random.lognormvariate(0, 0.8) * base_hours / 2)

    # ~3% of cases still open (closed_at NULL).
    still_open = random.random() < 0.03 and opened_at > now - timedelta(days=14)
    closed_at = None if still_open else opened_at + timedelta(hours=resolution_hours)

    # Reopen rate ~7% overall, higher for Critical/High (the dashboard surfaces this).
    # Spike cases also have a bumped reopen rate.
    reopen_p = {"Critical": 0.12, "High": 0.10, "Medium": 0.05, "Low": 0.03}[priority]
    if in_spike:
        reopen_p *= 1.8
    reopened_flag = (closed_at is not None) and (random.random() < reopen_p)

    # Satisfaction inversely correlated with reopen + resolution time.
    sat_base = 8.5 - (1.5 if reopened_flag else 0) - min(resolution_hours / 96, 2.5)
    if in_spike:
        sat_base -= 0.7
    satisfaction_score = max(1.0, min(10.0, sat_base + random.gauss(0, 0.8)))

    customer_id = f"C{random.randint(1, 800):04d}"
    case_id = f"CASE-{idx:06d}"

    return (
        case_id,
        opened_at,
        closed_at,
        priority,
        channel,
        region,
        customer_id,
        reopened_flag,
        round(satisfaction_score, 1),
        round(customer_lat, 4),
        round(customer_lon, 4),
    )


SCHEMA_STRUCT = StructType([
    StructField("case_id", StringType(), nullable=False),
    StructField("opened_at", TimestampType(), nullable=False),
    StructField("closed_at", TimestampType(), nullable=True),
    StructField("priority", StringType(), nullable=False),
    StructField("channel", StringType(), nullable=False),
    StructField("region_name", StringType(), nullable=False),
    StructField("customer_id", StringType(), nullable=False),
    StructField("reopened_flag", BooleanType(), nullable=False),
    StructField("satisfaction_score", DoubleType(), nullable=False),
    StructField("customer_latitude", DoubleType(), nullable=False),
    StructField("customer_longitude", DoubleType(), nullable=False),
])


def main() -> None:
    random.seed(42)

    print(f"Connecting to Databricks (serverless compute via databricks-connect)...")
    spark = DatabricksSession.builder.serverless().getOrCreate()

    print(f"Ensuring {CATALOG}.{SCHEMA} exists...")
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")

    now = datetime.now(timezone.utc)
    baseline_n = NUM_CASES - SPIKE_CASES
    print(f"Generating {baseline_n} baseline rows + {SPIKE_CASES} post-release spike rows "
          f"(release={RELEASE_DATE.date()}, seed=42)...")
    rows = [make_row(i + 1, now, in_spike=False) for i in range(baseline_n)]
    rows += [make_row(baseline_n + i + 1, now, in_spike=True) for i in range(SPIKE_CASES)]
    random.shuffle(rows)

    df = spark.createDataFrame(rows, schema=SCHEMA_STRUCT)
    # Add the derived column that the dashboard's ds_support computes inline,
    # so a quick sanity-check query against the table works without the dashboard.
    df = df.withColumn(
        "time_to_resolution_hours",
        (F.unix_timestamp("closed_at") - F.unix_timestamp("opened_at")) / 3600.0,
    )

    print(f"Writing {FQN} (overwriteSchema=true)...")
    df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(FQN)

    count = spark.table(FQN).count()
    print(f"  wrote {count} rows")

    # Sanity check — make sure the dashboard's headline KPIs are non-degenerate.
    print()
    print("Sanity check (matches the dashboard's MEASURE() definitions):")
    spark.sql(f"""
        SELECT
          COUNT(*) AS total_cases,
          ROUND(AVG(time_to_resolution_hours), 1) AS avg_resolution_hours,
          ROUND(SUM(CASE WHEN reopened_flag THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS reopen_rate_pct,
          ROUND(AVG(satisfaction_score), 2) AS avg_satisfaction
        FROM {FQN}
    """).show(truncate=False)

    print()
    print("=" * 70)
    print("Next steps")
    print("=" * 70)
    print(f"1. The example dashboard's SQL references `FROM support_cases` (bare name).")
    print(f"   When you create the dashboard, pass:")
    print(f"     --dataset-catalog {CATALOG} --dataset-schema {SCHEMA}")
    print(f"   so the bare table name resolves to {FQN}.")
    print()
    print(f"2. Create the dashboard from the worked example:")
    print(f"     databricks aibi-dashboards create-from-skill \\")
    print(f"       --skill databricks-aibi-dashboards \\")
    print(f"       --example 4-examples.md \\")
    print(f"       --dataset-catalog {CATALOG} \\")
    print(f"       --dataset-schema {SCHEMA}")
    print(f"   (Adjust the command to whatever your dashboard-creation tool exposes;")
    print(f"   the key is that the dataset bind to {FQN}.)")
    print()
    print(f"3. Open the dashboard in the workspace and visually verify:")
    print(f"   - All 4 KPI counters show numbers (Total Cases / Avg Hours / Reopen / Satisfaction)")
    print(f"   - Sparkline on kpi-volume-trend renders a smooth line")
    print(f"   - Forecast-line connects smoothly (the bridge CTE working)")
    print(f"   - Symbol map shows points across the US, not all clustered at one spot")
    print(f"   - Pivot conditional cells show the alert-coral on high-count cells")
    print(f"   - Theme is warm-sunset (amber/coral/pink/purple/navy), light bg, no borders")


if __name__ == "__main__":
    main()

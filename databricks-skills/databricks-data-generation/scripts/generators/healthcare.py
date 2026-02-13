"""Healthcare industry synthetic data generators (HIPAA-safe).

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
from dbldatagen.constraints import SqlExpr
from pyspark.sql import DataFrame
from utils.mimesis_text import mimesisText


def generate_patients(spark, rows=100_000, seed=42) -> DataFrame:
    """Generate synthetic patient demographics (100% HIPAA-safe)."""
    partitions = max(4, rows // 50_000)
    return (
        dg.DataGenerator(spark, rows=rows, partitions=partitions, randomSeed=seed)
        .withColumn("patient_id", "long", minValue=1_000_000, uniqueValues=rows)
        .withColumn("mrn", "string", template=r"MRNdddddddddd")
        .withColumn("first_name", "string", text=mimesisText("person.first_name"))
        .withColumn("last_name", "string", text=mimesisText("person.last_name"))
        .withColumn("date_of_birth", "date", begin="1924-01-01", end="2024-01-01", random=True)
        .withColumn("gender", "string", values=["M", "F", "Other"], weights=[49, 49, 2])
        .withColumn("ssn_last4", "string", template=r"dddd")
        .withColumn("email", "string", text=mimesisText("person.email"), percentNulls=0.05)
        .withColumn("phone", "string", text=mimesisText("person.telephone"), percentNulls=0.02)
        .withColumn("address", "string", text=mimesisText("address.address"))
        .withColumn("city", "string", text=mimesisText("address.city"))
        .withColumn("state", "string", values=["MA", "NY", "IL", "TX", "AZ", "CA", "FL", "PA"])
        .withColumn("zip_code", "string", template=r"ddddd")
        .withColumn("insurance_id", "string", template=r"INS-dddddddd")
        .withColumn("is_active", "boolean", expr="rand() < 0.9")
        .build()
    )


def generate_encounters(spark, rows=500_000, n_patients=100_000, seed=42) -> DataFrame:
    """Generate clinical encounter data linked to patients."""
    partitions = max(10, rows // 50_000)
    encounter_types = ["Outpatient", "Inpatient", "Emergency", "Observation", "Telehealth"]
    complaints = [
        "Chest pain", "Shortness of breath", "Abdominal pain", "Headache",
        "Back pain", "Fever", "Cough", "Fatigue", "Dizziness", "Follow-up",
        "Routine checkup", "Medication refill", "Post-surgical", "Lab review",
    ]

    return (
        dg.DataGenerator(spark, rows=rows, partitions=partitions, randomSeed=seed)
        .withColumn("encounter_id", "long", minValue=1, uniqueValues=rows)
        .withColumn("patient_id", "long",
                    minValue=1_000_000, maxValue=1_000_000 + n_patients - 1)
        .withColumn("provider_id", "long", minValue=5_000, maxValue=9_999)
        .withColumn("facility_id", "long", minValue=100, maxValue=200)
        .withColumn("encounter_type", "string",
                    values=encounter_types, weights=[50, 20, 15, 10, 5])
        .withColumn("admit_datetime", "timestamp",
                    begin="2024-01-01 00:00:00", end="2024-12-31 23:59:59", random=True)
        .withColumn("los_hours", "integer", minValue=1, maxValue=168,
                    distribution=dg.distributions.Exponential(), omit=True)
        .withColumn("discharge_datetime", "timestamp",
                    expr="admit_datetime + interval los_hours hours",
                    percentNulls=0.1)
        .withColumn("status", "string",
                    values=["Completed", "Active", "Cancelled"], weights=[85, 10, 5])
        .withColumn("chief_complaint", "string", values=complaints)
        .build()
    )


def generate_claims(spark, rows=500_000, n_encounters=500_000,
                    n_patients=100_000, seed=42) -> DataFrame:
    """Generate insurance claims data linked to encounters and patients."""
    partitions = max(10, rows // 50_000)
    payers = ["Medicare", "Medicaid", "Blue Cross", "Aetna", "United", "Cigna", "Self-Pay"]

    return (
        dg.DataGenerator(spark, rows=rows, partitions=partitions, randomSeed=seed)
        .withColumn("claim_id", "long", minValue=1, uniqueValues=rows)
        .withColumn("encounter_id", "long", minValue=1, maxValue=n_encounters)
        .withColumn("patient_id", "long",
                    minValue=1_000_000, maxValue=1_000_000 + n_patients - 1)
        .withColumn("payer_id", "string",
                    values=payers, weights=[25, 15, 20, 15, 15, 8, 2])
        .withColumn("claim_type", "string",
                    values=["Professional", "Institutional"], weights=[70, 30])
        .withColumn("service_date", "date",
                    begin="2024-01-01", end="2024-12-31", random=True)
        .withColumn("billed_amount", "decimal(12,2)",
                    minValue=50, maxValue=50000, distribution=dg.distributions.Exponential())
        .withColumn("allowed_pct", "float", expr="0.6 + rand() * 0.3", omit=True)
        .withColumn("allowed_amount", "decimal(12,2)", expr="billed_amount * allowed_pct")
        .withColumn("paid_pct", "float", expr="0.7 + rand() * 0.3", omit=True)
        .withColumn("paid_amount", "decimal(12,2)", expr="allowed_amount * paid_pct",
                    percentNulls=0.05)
        .withColumn("status", "string",
                    values=["Paid", "Pending", "Denied", "Appealed"],
                    weights=[70, 15, 10, 5])
        .withConstraint(SqlExpr("paid_amount <= allowed_amount"))
        .withConstraint(SqlExpr("allowed_amount <= billed_amount"))
        .build()
    )


def generate_healthcare_cdc(spark, volume_path, n_patients=100_000,
                            n_batches=5, seed=42):
    """Generate healthcare CDC data and write to UC Volume."""
    from .cdc import add_cdc_operations, write_cdc_to_volume

    for i in range(n_batches):
        rows = n_patients if i == 0 else n_patients // 10
        base_df = generate_patients(spark, rows=rows, seed=seed + i)
        weights = {"APPEND": 100} if i == 0 else {"APPEND": 50, "UPDATE": 40, "DELETE": 5}
        cdc_df = add_cdc_operations(base_df, weights=weights)
        write_cdc_to_volume(cdc_df, volume_path, batch_id=i)


def generate_healthcare_demo(spark, catalog, schema="healthcare",
                             volume="raw_data", n_patients=100_000, seed=42):
    """Generate complete healthcare demo dataset with all tables."""
    from ..utils.output import write_medallion

    n_encounters = n_patients * 5
    n_claims = n_encounters

    patients = generate_patients(spark, rows=n_patients, seed=seed)
    encounters = generate_encounters(spark, rows=n_encounters,
                                     n_patients=n_patients, seed=seed)
    claims = generate_claims(spark, rows=n_claims, n_encounters=n_encounters,
                             n_patients=n_patients, seed=seed)

    write_medallion(
        tables={
            "patients": patients,
            "encounters": encounters,
            "claims": claims,
        },
        catalog=catalog,
        schema=schema,
        volume=volume,
    )

# Healthcare Industry Patterns

HIPAA-safe synthetic data models for healthcare demos.

**Important**: All data generated is 100% synthetic and contains no real patient information.

## Data Model Overview

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Patients   │────<│  Encounters  │>────│  Providers   │
└──────────────┘     └──────────────┘     └──────────────┘
       │                    │                    │
       │                    │                    │
       ▼                    ▼                    ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Insurance   │     │    Claims    │     │  Facilities  │
└──────────────┘     └──────────────┘     └──────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │  Diagnoses   │
                    └──────────────┘
```

## Table Schemas

### Patients

| Column | Type | Description | Generation Pattern |
|--------|------|-------------|-------------------|
| `patient_id` | LONG | Primary key | Unique |
| `mrn` | STRING | Medical Record Number | Template: `MRNdddddddddd` |
| `first_name` | STRING | First name | Mimesis |
| `last_name` | STRING | Last name | Mimesis |
| `date_of_birth` | DATE | Birth date | Age 0-100 distribution |
| `gender` | STRING | M/F/Other | Weighted values |
| `ssn_last4` | STRING | Last 4 of SSN | Template: `dddd` |
| `address` | STRING | Street address | Mimesis |
| `city` | STRING | City | Mimesis |
| `state` | STRING | State | Values list |
| `zip_code` | STRING | ZIP | Template |
| `phone` | STRING | Phone | Template |
| `email` | STRING | Email | Template |
| `insurance_id` | STRING | Insurance member ID | Template |
| `pcp_id` | LONG | Primary care provider | FK to providers |

```python
import dbldatagen as dg
from utils.mimesis_text import mimesisText
from datetime import date, timedelta

patients = (
    dg.DataGenerator(spark, rows=100_000, partitions=10)
    .withColumn("patient_id", "long", minValue=1_000_000, uniqueValues=100_000)
    .withColumn("mrn", "string", template=r"MRNdddddddddd")
    .withColumn("first_name", "string", text=mimesisText("person.first_name"))
    .withColumn("last_name", "string", text=mimesisText("person.last_name"))
    .withColumn("date_of_birth", "date", begin="1924-01-01", end="2024-01-01", random=True)
    .withColumn("gender", "string", values=["M", "F", "Other"], weights=[49, 49, 2])
    .withColumn("ssn_last4", "string", template=r"dddd")
    .withColumn("address", "string", text=mimesisText("address.address"))
    .withColumn("city", "string", values=["Boston", "New York", "Chicago", "Houston", "Phoenix"])
    .withColumn("state", "string", values=["MA", "NY", "IL", "TX", "AZ"])
    .withColumn("zip_code", "string", template=r"ddddd")
    .withColumn("phone", "string", text=mimesisText("person.telephone"))
    .withColumn("email", "string", text=mimesisText("person.email"))
    .withColumn("insurance_id", "string", template=r"INS-dddddddd")
    .withColumn("pcp_id", "long", minValue=5000, maxValue=5999)
    .build()
)
```

### Providers

| Column | Type | Description | Generation Pattern |
|--------|------|-------------|-------------------|
| `provider_id` | LONG | Primary key | Unique |
| `npi` | STRING | National Provider ID | Template: 10 digits |
| `first_name` | STRING | First name | Mimesis |
| `last_name` | STRING | Last name | Mimesis |
| `specialty` | STRING | Medical specialty | Values list |
| `facility_id` | LONG | Primary facility | FK |
| `license_state` | STRING | State | Values list |
| `active` | BOOLEAN | Currently practicing | 95% true |

```python
import dbldatagen as dg
from utils.mimesis_text import mimesisText

specialties = [
    "Family Medicine", "Internal Medicine", "Pediatrics", "Cardiology",
    "Orthopedics", "Dermatology", "Neurology", "Psychiatry",
    "Oncology", "Emergency Medicine", "Radiology", "Anesthesiology"
]

providers = (
    dg.DataGenerator(spark, rows=5_000, partitions=4)
    .withColumn("provider_id", "long", minValue=5_000, uniqueValues=5_000)
    .withColumn("npi", "string", template=r"dddddddddd")
    .withColumn("first_name", "string", text=mimesisText("person.first_name"))
    .withColumn("last_name", "string", text=mimesisText("person.last_name"))
    .withColumn("specialty", "string", values=specialties)
    .withColumn("facility_id", "long", minValue=100, maxValue=200)
    .withColumn("license_state", "string", values=["MA", "NY", "CA", "TX", "FL"])
    .withColumn("active", "boolean", expr="rand() < 0.95")
    .build()
)
```

### Encounters

| Column | Type | Description | Generation Pattern |
|--------|------|-------------|-------------------|
| `encounter_id` | LONG | Primary key | Unique |
| `patient_id` | LONG | Foreign key | Match patient range |
| `provider_id` | LONG | Attending provider | FK |
| `facility_id` | LONG | Location | FK |
| `encounter_type` | STRING | Visit type | Values list |
| `admit_datetime` | TIMESTAMP | Admission time | Random |
| `discharge_datetime` | TIMESTAMP | Discharge time | After admit |
| `status` | STRING | Encounter status | Values list |
| `chief_complaint` | STRING | Reason for visit | Values list |

```python
encounter_types = ["Outpatient", "Inpatient", "Emergency", "Observation", "Telehealth"]
complaints = [
    "Chest pain", "Shortness of breath", "Abdominal pain", "Headache",
    "Back pain", "Fever", "Cough", "Fatigue", "Dizziness", "Follow-up"
]

encounters = (
    dg.DataGenerator(spark, rows=500_000, partitions=20)
    .withColumn("encounter_id", "long", minValue=1, uniqueValues=500_000)
    .withColumn("patient_id", "long", minValue=1_000_000, maxValue=1_099_999)
    .withColumn("provider_id", "long", minValue=5_000, maxValue=9_999)
    .withColumn("facility_id", "long", minValue=100, maxValue=200)
    .withColumn("encounter_type", "string", values=encounter_types, weights=[50, 20, 15, 10, 5])
    .withColumn("admit_datetime", "timestamp", begin="2024-01-01", end="2024-12-31", random=True)
    .withColumn("los_hours", "integer", minValue=1, maxValue=168, distribution="exponential", omit=True)
    .withColumn("discharge_datetime", "timestamp", expr="admit_datetime + interval los_hours hours")
    .withColumn("status", "string", values=["Completed", "Active", "Cancelled"], weights=[85, 10, 5])
    .withColumn("chief_complaint", "string", values=complaints)
    .build()
)
```

### Claims

| Column | Type | Description | Generation Pattern |
|--------|------|-------------|-------------------|
| `claim_id` | LONG | Primary key | Unique |
| `encounter_id` | LONG | Foreign key | Match encounter range |
| `patient_id` | LONG | Foreign key | Match patient range |
| `payer_id` | STRING | Insurance company | Values list |
| `claim_type` | STRING | Professional/Institutional | Values |
| `service_date` | DATE | Date of service | From encounter |
| `submitted_date` | DATE | Claim submission | After service |
| `paid_date` | DATE | Payment date | After submitted |
| `billed_amount` | DECIMAL(12,2) | Amount billed | Range |
| `allowed_amount` | DECIMAL(12,2) | Contracted amount | 60-90% of billed |
| `paid_amount` | DECIMAL(12,2) | Paid by payer | 70-100% of allowed |
| `patient_responsibility` | DECIMAL(10,2) | Patient owes | Remainder |
| `status` | STRING | Claim status | Values list |

```python
payers = ["Medicare", "Medicaid", "Blue Cross", "Aetna", "United", "Cigna", "Self-Pay"]

claims = (
    dg.DataGenerator(spark, rows=1_000_000, partitions=20)
    .withColumn("claim_id", "long", minValue=1, uniqueValues=1_000_000)
    .withColumn("encounter_id", "long", minValue=1, maxValue=500_000)
    .withColumn("patient_id", "long", minValue=1_000_000, maxValue=1_099_999)
    .withColumn("payer_id", "string", values=payers, weights=[25, 15, 20, 15, 15, 8, 2])
    .withColumn("claim_type", "string", values=["Professional", "Institutional"], weights=[70, 30])
    .withColumn("service_date", "date", begin="2024-01-01", end="2024-12-31", random=True)
    .withColumn("submitted_date", "date", expr="date_add(service_date, cast(rand() * 30 as int))")
    .withColumn("paid_date", "date", expr="date_add(submitted_date, cast(rand() * 45 as int))")
    .withColumn("billed_amount", "decimal(12,2)", minValue=50, maxValue=50000, distribution="exponential")
    .withColumn("allowed_pct", "float", expr="0.6 + rand() * 0.3", omit=True)
    .withColumn("allowed_amount", "decimal(12,2)", expr="billed_amount * allowed_pct")
    .withColumn("paid_pct", "float", expr="0.7 + rand() * 0.3", omit=True)
    .withColumn("paid_amount", "decimal(12,2)", expr="allowed_amount * paid_pct")
    .withColumn("patient_responsibility", "decimal(10,2)", expr="allowed_amount - paid_amount")
    .withColumn("status", "string", values=["Paid", "Pending", "Denied", "Appealed"], weights=[70, 15, 10, 5])
    .build()
)
```

### Diagnoses

| Column | Type | Description | Generation Pattern |
|--------|------|-------------|-------------------|
| `diagnosis_id` | LONG | Primary key | Unique |
| `encounter_id` | LONG | Foreign key | Match encounter range |
| `patient_id` | LONG | Foreign key | Match patient range |
| `icd10_code` | STRING | ICD-10 code | Pattern |
| `description` | STRING | Diagnosis text | Values list |
| `is_primary` | BOOLEAN | Primary diagnosis | First per encounter |
| `diagnosis_type` | STRING | Admitting/Final | Values |

```python
# Common ICD-10 patterns
icd10_codes = [
    ("I10", "Essential hypertension"),
    ("E11.9", "Type 2 diabetes mellitus"),
    ("J06.9", "Upper respiratory infection"),
    ("M54.5", "Low back pain"),
    ("R10.9", "Abdominal pain"),
    ("R05.9", "Cough"),
    ("J18.9", "Pneumonia"),
    ("N39.0", "Urinary tract infection"),
    ("K21.0", "GERD"),
    ("F41.1", "Generalized anxiety disorder"),
]

diagnoses = (
    dg.DataGenerator(spark, rows=1_500_000, partitions=20)  # ~3 per encounter
    .withColumn("diagnosis_id", "long", minValue=1, uniqueValues=1_500_000)
    .withColumn("encounter_id", "long", minValue=1, maxValue=500_000)
    .withColumn("patient_id", "long", minValue=1_000_000, maxValue=1_099_999)
    .withColumn("code_idx", "integer", minValue=0, maxValue=9, random=True, omit=True)
    .withColumn("icd10_code", "string", values=[c[0] for c in icd10_codes])
    .withColumn("description", "string", values=[c[1] for c in icd10_codes])
    .withColumn("is_primary", "boolean", expr="rand() < 0.33")
    .withColumn("diagnosis_type", "string", values=["Admitting", "Working", "Final"], weights=[20, 30, 50])
    .build()
)
```

## HIPAA Considerations

### What Makes Data HIPAA-Safe

This synthetic data is HIPAA-safe because:

1. **No Real Identifiers**: All names, SSNs, MRNs are randomly generated
2. **No Real Dates**: Birth dates and encounter dates are synthetic
3. **No Geographic Detail**: ZIP codes are random 5-digit strings
4. **No Real Insurance IDs**: Member IDs are randomly generated
5. **No Real NPIs**: Provider NPIs are random 10-digit strings

### Patterns to Avoid

```python
# BAD: Using real data as seed
real_patients = spark.table("production.patients")  # Never do this

# GOOD: Fully synthetic
patients = dg.DataGenerator(spark, rows=100000).build()
```

## CDC Generation

```python
def generate_healthcare_cdc(spark, volume_path, n_encounters=500_000, n_batches=5, seed=42):
    """Generate healthcare CDC data — encounter updates and claim status changes."""
    import dbldatagen as dg

    # Initial encounter load — all INSERTs
    initial = (
        dg.DataGenerator(spark, rows=n_encounters, partitions=20, randomSeed=seed)
        .withColumn("encounter_id", "long", minValue=1, uniqueValues=n_encounters)
        .withColumn("patient_id", "long", minValue=1_000_000, maxValue=1_099_999)
        .withColumn("provider_id", "long", minValue=5_000, maxValue=9_999)
        .withColumn("encounter_type", "string",
                    values=["Outpatient", "Inpatient", "Emergency", "Observation", "Telehealth"],
                    weights=[50, 20, 15, 10, 5])
        .withColumn("status", "string", values=["Active"])
        .withColumn("operation", "string", values=["INSERT"])
        .withColumn("operation_date", "timestamp", begin="2024-01-01", end="2024-01-01")
        .build()
    )
    initial.write.format("json").mode("overwrite").save(f"{volume_path}/encounters/batch_0")

    # Incremental batches — encounter updates (status changes) and new encounters
    for batch in range(1, n_batches + 1):
        batch_df = (
            dg.DataGenerator(spark, rows=n_encounters // 10, partitions=4, randomSeed=seed + batch)
            .withColumn("encounter_id", "long", minValue=1, maxValue=n_encounters)
            .withColumn("patient_id", "long", minValue=1_000_000, maxValue=1_099_999)
            .withColumn("provider_id", "long", minValue=5_000, maxValue=9_999)
            .withColumn("encounter_type", "string",
                        values=["Outpatient", "Inpatient", "Emergency", "Observation", "Telehealth"],
                        weights=[50, 20, 15, 10, 5])
            .withColumn("status", "string",
                        values=["Active", "Completed", "Cancelled"],
                        weights=[20, 70, 10])
            .withColumn("operation", "string", values=["INSERT", "UPDATE"], weights=[30, 70])
            .withColumn("operation_date", "timestamp",
                        expr=f"cast('2024-01-{batch + 1:02d}' as timestamp) + make_interval(0,0,0,0, cast(rand() * 23 as int), cast(rand() * 59 as int), 0)")
            .build()
        )
        batch_df.write.format("json").mode("overwrite").save(f"{volume_path}/encounters/batch_{batch}")

    # Claim status changes — Synthea-style encounter-to-claims temporal flow
    for batch in range(1, n_batches + 1):
        claims_cdc = (
            dg.DataGenerator(spark, rows=n_encounters // 5, partitions=4, randomSeed=seed + batch + 100)
            .withColumn("claim_id", "long", minValue=1, maxValue=n_encounters * 2)
            .withColumn("encounter_id", "long", minValue=1, maxValue=n_encounters)
            .withColumn("status", "string",
                        values=["Submitted", "In Review", "Paid", "Denied", "Appealed"],
                        weights=[20, 25, 35, 15, 5])
            .withColumn("paid_amount", "decimal(12,2)", minValue=0, maxValue=25000, distribution="exponential")
            .withColumn("operation", "string", values=["INSERT", "UPDATE"], weights=[40, 60])
            .withColumn("operation_date", "timestamp",
                        expr=f"cast('2024-01-{batch + 1:02d}' as timestamp) + make_interval(0,0,0,0, cast(rand() * 23 as int), cast(rand() * 59 as int), 0)")
            .build()
        )
        claims_cdc.write.format("json").mode("overwrite").save(f"{volume_path}/claims/batch_{batch}")
```

## Data Quality Injection

```python
from utils.mimesis_text import mimesisText

# Healthcare-appropriate quality issues
# 1% null DOB (incomplete patient intake), 3% null addresses
.withColumn("date_of_birth", "date", begin="1924-01-01", end="2024-01-01", random=True, percentNulls=0.01)
.withColumn("address", "string", text=mimesisText("address.address"), percentNulls=0.03)

# Duplicate encounter records (system integration issues — 2% rate)
clean_encounters = generate_encounters(spark, n_encounters)
encounters_with_dupes = clean_encounters.union(clean_encounters.sample(0.02))
```

## Medallion Output

```python
# Bronze: Raw to Volumes — Auto Loader picks up
patients_df.write.format("json").save(f"/Volumes/{catalog}/{schema}/{volume}/patients")
encounters_df.write.format("json").save(f"/Volumes/{catalog}/{schema}/{volume}/encounters")
claims_df.write.format("json").save(f"/Volumes/{catalog}/{schema}/{volume}/claims")

# Silver: Cleaned and deduplicated
# (handled by Spark Declarative Pipeline — APPLY CHANGES INTO for CDC)

# Gold: Patient summaries and aggregated metrics
# (materialized views in Spark Declarative Pipelines)
```

## Synthea-Style Patterns

```python
# Encounter-to-claims temporal flow:
# 1. Encounter created (admit_datetime)
# 2. Encounter completed (discharge_datetime = admit + LOS)
# 3. Claim submitted (2-30 days after discharge)
# 4. Claim adjudicated (15-45 days after submission)

.withColumn("admit_datetime", "timestamp", begin="2024-01-01", end="2024-12-31", random=True)
.withColumn("los_hours", "integer", minValue=1, maxValue=168, distribution="exponential", omit=True)
.withColumn("discharge_datetime", "timestamp", expr="admit_datetime + make_interval(0,0,0,0, los_hours, 0, 0)")
.withColumn("claim_lag_days", "integer", minValue=2, maxValue=30, random=True, omit=True)
.withColumn("claim_submitted_date", "date", expr="date_add(cast(discharge_datetime as date), claim_lag_days)")
.withColumn("adjudication_lag_days", "integer", minValue=15, maxValue=45, random=True, omit=True)
.withColumn("claim_paid_date", "date", expr="date_add(claim_submitted_date, adjudication_lag_days)")

# Age-weighted encounter frequency (elderly patients have more encounters)
.withColumn("patient_age", "integer",
            expr="floor(datediff(current_date(), date_of_birth) / 365)", omit=True)
.withColumn("encounter_weight", "float",
            expr="""case
                when patient_age >= 65 then 3.0
                when patient_age >= 45 then 1.5
                when patient_age >= 18 then 1.0
                else 1.2
            end""")
```

## Complete Healthcare Demo

```python
def generate_healthcare_demo(
    spark,
    n_patients: int = 100_000,
    n_providers: int = 5_000,
    n_encounters: int = 500_000,
    catalog: str = "demo",
    schema: str = "healthcare"
):
    """Generate HIPAA-safe healthcare demo dataset."""

    patients = generate_patients(spark, n_patients)
    providers = generate_providers(spark, n_providers)
    facilities = generate_facilities(spark, 100)
    encounters = generate_encounters(spark, n_encounters, n_patients, n_providers)
    claims = generate_claims(spark, n_encounters * 2, n_encounters, n_patients)
    diagnoses = generate_diagnoses(spark, n_encounters * 3, n_encounters, n_patients)

    tables = {
        "patients": patients,
        "providers": providers,
        "facilities": facilities,
        "encounters": encounters,
        "claims": claims,
        "diagnoses": diagnoses,
    }

    for name, df in tables.items():
        df.write.format("delta").mode("overwrite").saveAsTable(f"{catalog}.{schema}.{name}")

    return tables
```

## Common Demo Queries

### Patient Summary
```sql
SELECT
    p.patient_id,
    p.first_name,
    p.last_name,
    COUNT(DISTINCT e.encounter_id) as total_encounters,
    COUNT(DISTINCT d.icd10_code) as unique_diagnoses,
    SUM(c.paid_amount) as total_claims_paid
FROM patients p
LEFT JOIN encounters e ON p.patient_id = e.patient_id
LEFT JOIN diagnoses d ON e.encounter_id = d.encounter_id
LEFT JOIN claims c ON e.encounter_id = c.encounter_id
GROUP BY p.patient_id, p.first_name, p.last_name
```

### Top Diagnoses
```sql
SELECT
    d.icd10_code,
    d.description,
    COUNT(*) as occurrence_count,
    COUNT(DISTINCT d.patient_id) as unique_patients
FROM diagnoses d
GROUP BY d.icd10_code, d.description
ORDER BY occurrence_count DESC
LIMIT 20
```

### Claims by Payer
```sql
SELECT
    payer_id,
    COUNT(*) as claim_count,
    SUM(billed_amount) as total_billed,
    SUM(paid_amount) as total_paid,
    AVG(paid_amount / billed_amount) * 100 as avg_payment_rate
FROM claims
WHERE status = 'Paid'
GROUP BY payer_id
ORDER BY total_paid DESC
```

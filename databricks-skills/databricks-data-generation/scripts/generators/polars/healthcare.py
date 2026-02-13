"""Healthcare industry synthetic data generators (Polars + Mimesis, HIPAA-safe).

REFERENCE IMPLEMENTATION — This file is not an importable module. Claude reads it
for patterns and adapts the code inline for user scripts. Uses pure Polars + Mimesis
for Tier 1 local generation (<100K rows, zero JVM overhead).
"""

import random
from datetime import date, datetime, timedelta

import polars as pl
from mimesis import Generic
from mimesis.locales import Locale

STATES = ["MA", "NY", "IL", "TX", "AZ", "CA", "FL", "PA"]
GENDERS = ["M", "F", "Other"]
GENDER_WEIGHTS = [49, 49, 2]
ENCOUNTER_TYPES = ["Outpatient", "Inpatient", "Emergency", "Observation", "Telehealth"]
ENCOUNTER_WEIGHTS = [50, 20, 15, 10, 5]
COMPLAINTS = [
    "Chest pain", "Shortness of breath", "Abdominal pain", "Headache",
    "Back pain", "Fever", "Cough", "Fatigue", "Dizziness", "Follow-up",
    "Routine checkup", "Medication refill", "Post-surgical", "Lab review",
]
PAYERS = ["Medicare", "Medicaid", "Blue Cross", "Aetna", "United", "Cigna", "Self-Pay"]
PAYER_WEIGHTS = [25, 15, 20, 15, 15, 8, 2]


def generate_patients(rows: int = 10_000, seed: int = 42) -> pl.DataFrame:
    """Generate synthetic patient demographics (100% HIPAA-safe)."""
    random.seed(seed)
    g = Generic(locale=Locale.EN, seed=seed)

    dob_start = date(1924, 1, 1)
    dob_range = (date(2024, 1, 1) - dob_start).days

    patient_ids = list(range(1_000_000, 1_000_000 + rows))
    mrns = [f"MRN{random.randint(1000000000, 9999999999)}" for _ in range(rows)]
    first_names = [g.person.first_name() for _ in range(rows)]
    last_names = [g.person.last_name() for _ in range(rows)]
    dobs = [dob_start + timedelta(days=random.randint(0, dob_range))
            for _ in range(rows)]
    genders = random.choices(GENDERS, weights=GENDER_WEIGHTS, k=rows)
    ssn_last4 = [f"{random.randint(0, 9999):04d}" for _ in range(rows)]
    emails = [
        None if random.random() < 0.05 else g.person.email()
        for _ in range(rows)
    ]
    phones = [
        None if random.random() < 0.02 else g.person.telephone()
        for _ in range(rows)
    ]
    addresses = [g.address.address() for _ in range(rows)]
    cities = [g.address.city() for _ in range(rows)]
    states = random.choices(STATES, k=rows)
    zip_codes = [f"{random.randint(10000, 99999)}" for _ in range(rows)]
    insurance_ids = [f"INS-{random.randint(10000000, 99999999)}" for _ in range(rows)]
    is_active = [random.random() < 0.9 for _ in range(rows)]

    return pl.DataFrame({
        "patient_id": patient_ids,
        "mrn": mrns,
        "first_name": first_names,
        "last_name": last_names,
        "date_of_birth": dobs,
        "gender": genders,
        "ssn_last4": ssn_last4,
        "email": emails,
        "phone": phones,
        "address": addresses,
        "city": cities,
        "state": states,
        "zip_code": zip_codes,
        "insurance_id": insurance_ids,
        "is_active": is_active,
    })


def generate_encounters(rows: int = 30_000, n_patients: int = 10_000,
                        seed: int = 42) -> pl.DataFrame:
    """Generate clinical encounter data linked to patients."""
    random.seed(seed)

    ts_start = datetime(2024, 1, 1)
    ts_range = int((datetime(2024, 12, 31, 23, 59, 59) - ts_start).total_seconds())

    encounter_ids = list(range(1, rows + 1))
    patient_ids = [random.randint(1_000_000, 1_000_000 + n_patients - 1)
                   for _ in range(rows)]
    provider_ids = [random.randint(5_000, 9_999) for _ in range(rows)]
    facility_ids = [random.randint(100, 200) for _ in range(rows)]
    encounter_types = random.choices(ENCOUNTER_TYPES, weights=ENCOUNTER_WEIGHTS, k=rows)
    admit_datetimes = [ts_start + timedelta(seconds=random.randint(0, ts_range))
                       for _ in range(rows)]
    los_hours = [max(1, int(random.expovariate(0.05))) for _ in range(rows)]
    discharge_datetimes = [
        None if random.random() < 0.1
        else admit + timedelta(hours=min(los, 168))
        for admit, los in zip(admit_datetimes, los_hours)
    ]
    statuses = random.choices(
        ["Completed", "Active", "Cancelled"], weights=[85, 10, 5], k=rows
    )
    chief_complaints = random.choices(COMPLAINTS, k=rows)

    return pl.DataFrame({
        "encounter_id": encounter_ids,
        "patient_id": patient_ids,
        "provider_id": provider_ids,
        "facility_id": facility_ids,
        "encounter_type": encounter_types,
        "admit_datetime": admit_datetimes,
        "discharge_datetime": discharge_datetimes,
        "status": statuses,
        "chief_complaint": chief_complaints,
    })


def generate_claims(rows: int = 30_000, n_encounters: int = 30_000,
                    n_patients: int = 10_000, seed: int = 42) -> pl.DataFrame:
    """Generate insurance claims data linked to encounters and patients."""
    random.seed(seed)

    svc_start = date(2024, 1, 1)
    svc_range = (date(2024, 12, 31) - svc_start).days

    claim_ids = list(range(1, rows + 1))
    encounter_ids = [random.randint(1, n_encounters) for _ in range(rows)]
    patient_ids = [random.randint(1_000_000, 1_000_000 + n_patients - 1)
                   for _ in range(rows)]
    payer_ids = random.choices(PAYERS, weights=PAYER_WEIGHTS, k=rows)
    claim_types = random.choices(
        ["Professional", "Institutional"], weights=[70, 30], k=rows
    )
    service_dates = [svc_start + timedelta(days=random.randint(0, svc_range))
                     for _ in range(rows)]
    billed_amounts = [round(random.expovariate(0.001), 2) for _ in range(rows)]
    billed_amounts = [min(b, 50000) for b in billed_amounts]  # cap
    allowed_amounts = [round(b * (0.6 + random.random() * 0.3), 2) for b in billed_amounts]
    paid_amounts = [
        None if random.random() < 0.05
        else round(a * (0.7 + random.random() * 0.3), 2)
        for a in allowed_amounts
    ]
    statuses = random.choices(
        ["Paid", "Pending", "Denied", "Appealed"], weights=[70, 15, 10, 5], k=rows
    )

    return pl.DataFrame({
        "claim_id": claim_ids,
        "encounter_id": encounter_ids,
        "patient_id": patient_ids,
        "payer_id": payer_ids,
        "claim_type": claim_types,
        "service_date": service_dates,
        "billed_amount": billed_amounts,
        "allowed_amount": allowed_amounts,
        "paid_amount": paid_amounts,
        "status": statuses,
    })

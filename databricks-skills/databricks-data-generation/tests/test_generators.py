"""Smoke tests for all Polars generator functions + CDC helper."""

import polars as pl
import pytest

from helpers import load_generator

# ── Generator specs: (module, function, extra_kwargs, expected_columns) ─────
GENERATOR_SPECS = [
    # retail
    (
        "retail", "generate_customers", {},
        ["customer_id", "first_name", "last_name", "email", "phone",
         "address_line1", "city", "state", "zip_code", "signup_date",
         "lifetime_value", "is_active", "loyalty_tier"],
    ),
    (
        "retail", "generate_products", {},
        ["product_id", "sku", "product_name", "category", "brand",
         "unit_price", "cost", "weight_kg", "is_active", "created_date"],
    ),
    (
        "retail", "generate_transactions", {"n_customers": 100},
        ["txn_id", "customer_id", "store_id", "txn_timestamp",
         "payment_method", "discount_amount", "tax_amount",
         "total_amount", "items_count"],
    ),
    (
        "retail", "generate_line_items", {"n_transactions": 100, "n_products": 50},
        ["line_item_id", "txn_id", "product_id", "quantity",
         "unit_price", "line_total"],
    ),
    (
        "retail", "generate_inventory", {"n_products": 50},
        ["inventory_id", "product_id", "store_id", "quantity_on_hand",
         "reorder_point", "last_updated"],
    ),
    # healthcare
    (
        "healthcare", "generate_patients", {},
        ["patient_id", "mrn", "first_name", "last_name", "date_of_birth",
         "gender", "ssn_last4", "email", "phone", "address", "city",
         "state", "zip_code", "insurance_id", "is_active"],
    ),
    (
        "healthcare", "generate_encounters", {"n_patients": 100},
        ["encounter_id", "patient_id", "provider_id", "facility_id",
         "encounter_type", "admit_datetime", "discharge_datetime",
         "status", "chief_complaint"],
    ),
    (
        "healthcare", "generate_claims", {"n_encounters": 100, "n_patients": 100},
        ["claim_id", "encounter_id", "patient_id", "payer_id", "claim_type",
         "service_date", "billed_amount", "allowed_amount", "paid_amount",
         "status"],
    ),
    # financial
    (
        "financial", "generate_accounts", {},
        ["account_id", "customer_id", "account_number", "account_type",
         "status", "open_date", "balance", "currency", "risk_rating"],
    ),
    (
        "financial", "generate_trades", {"n_accounts": 100},
        ["trade_id", "account_id", "symbol", "trade_type", "order_type",
         "quantity", "price", "trade_value", "commission", "trade_timestamp",
         "volume_factor", "status", "execution_venue"],
    ),
    (
        "financial", "generate_transactions", {"n_accounts": 100},
        ["txn_id", "account_id", "txn_type", "amount", "txn_timestamp",
         "channel", "is_international", "status"],
    ),
    # iot
    (
        "iot", "generate_devices", {},
        ["device_id", "device_serial", "device_type", "manufacturer",
         "install_date", "latitude", "longitude", "status"],
    ),
    (
        "iot", "generate_sensor_readings", {"n_devices": 100, "anomaly_rate": 0.02},
        ["reading_id", "device_id", "timestamp", "metric_name",
         "metric_value", "unit", "quality_score", "is_anomaly"],
    ),
    (
        "iot", "generate_events", {"n_devices": 100},
        ["event_id", "device_id", "timestamp", "event_type", "severity",
         "description", "acknowledged", "resolved"],
    ),
    (
        "iot", "generate_telemetry", {"n_devices": 100},
        ["telemetry_id", "device_id", "timestamp", "latitude", "longitude",
         "speed", "heading", "fuel_level", "engine_temp"],
    ),
    # manufacturing
    (
        "manufacturing", "generate_equipment", {},
        ["equipment_id", "serial_number", "equipment_type", "manufacturer",
         "model", "install_date", "location_zone", "status",
         "last_maintenance_date", "expected_lifespan_years"],
    ),
    (
        "manufacturing", "generate_sensor_data", {"n_equipment": 50, "fault_rate": 0.10},
        ["reading_id", "equipment_id", "timestamp", "sensor_A", "sensor_B",
         "sensor_C", "sensor_D", "sensor_E", "sensor_F", "energy",
         "is_anomaly"],
    ),
    (
        "manufacturing", "generate_maintenance_records", {"n_equipment": 50},
        ["maintenance_id", "equipment_id", "scheduled_date", "completion_date",
         "maintenance_type", "priority", "duration_hours", "cost",
         "technician_id", "description", "status", "parts_replaced"],
    ),
]

SMOKE_ROWS = 200


def _spec_id(spec):
    return f"{spec[0]}.{spec[1]}"


# ── Parametrized smoke tests ────────────────────────────────────────────────

@pytest.mark.parametrize("spec", GENERATOR_SPECS, ids=[_spec_id(s) for s in GENERATOR_SPECS])
class TestGeneratorSmoke:
    """Smoke tests applied to every generator function."""

    def _call(self, spec):
        module_name, func_name, extra_kwargs, _ = spec
        mod = load_generator(module_name)
        func = getattr(mod, func_name)
        return func(rows=SMOKE_ROWS, seed=42, **extra_kwargs)

    def test_returns_dataframe(self, spec):
        df = self._call(spec)
        assert isinstance(df, pl.DataFrame)

    def test_correct_row_count(self, spec):
        df = self._call(spec)
        assert len(df) == SMOKE_ROWS

    def test_expected_columns(self, spec):
        _, _, _, expected_cols = spec
        df = self._call(spec)
        assert list(df.columns) == expected_cols

    def test_deterministic_with_same_seed(self, spec):
        df1 = self._call(spec)
        df2 = self._call(spec)
        assert df1.equals(df2)


# ── Detailed retail tests ───────────────────────────────────────────────────

class TestRetailCustomerDetails:
    """Detailed assertions on the retail customer generator."""

    @pytest.fixture(autouse=True)
    def _generate(self):
        mod = load_generator("retail")
        self.df = mod.generate_customers(rows=1000, seed=42)

    def test_customer_id_range_starts_at_million(self):
        assert self.df["customer_id"].min() == 1_000_000

    def test_email_has_nulls(self):
        null_count = self.df["email"].null_count()
        assert null_count > 0, "Expected some null emails with 1000 rows"

    def test_address_line1_non_null_strings(self):
        col = self.df["address_line1"]
        assert col.null_count() == 0
        assert col.dtype == pl.Utf8


# ── CDC helper tests ────────────────────────────────────────────────────────

class TestCDCHelper:
    """Tests for the add_cdc_operations helper."""

    @pytest.fixture
    def base_df(self):
        return pl.DataFrame({"id": list(range(500))})

    def test_adds_expected_columns(self, base_df):
        mod = load_generator("cdc")
        result = mod.add_cdc_operations(base_df)
        assert "operation" in result.columns
        assert "operation_date" in result.columns

    def test_custom_weights_produce_expected_ops(self, base_df):
        mod = load_generator("cdc")
        result = mod.add_cdc_operations(
            base_df, weights={"INSERT": 100}, seed=1
        )
        ops = result["operation"].unique().to_list()
        assert ops == ["INSERT"]

    def test_default_weights_produce_all_operations(self, base_df):
        mod = load_generator("cdc")
        result = mod.add_cdc_operations(base_df, seed=42)
        ops = set(result["operation"].unique().to_list())
        assert ops == {"APPEND", "UPDATE", "DELETE"}

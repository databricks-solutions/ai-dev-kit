# Generator API Reference

Pre-built generator functions for each industry vertical. These are reference implementations in `scripts/generators/` — read them for patterns, adapt inline for your use case.

## Polars Generators (Tier 1 — Local)

Pure Polars + Mimesis generators for fast local generation (<100K rows, zero JVM overhead). Located in `scripts/generators/polars/`.

### Retail (Polars)

| Function | Default Rows | Key Columns |
|----------|-------------|-------------|
| `generate_customers(rows, seed)` | 10K | customer_id, first_name, last_name, email, loyalty_tier |
| `generate_products(rows, seed)` | 5K | product_id, sku, category, brand, unit_price |
| `generate_transactions(rows, n_customers, seed)` | 50K | txn_id, customer_id, payment_method, total_amount |
| `generate_line_items(rows, n_transactions, n_products, seed)` | 150K | line_item_id, txn_id, product_id, quantity, line_total |
| `generate_inventory(rows, n_products, seed)` | 50K | inventory_id, product_id, store_id, quantity_on_hand |

### Healthcare (Polars)

| Function | Default Rows | Key Columns |
|----------|-------------|-------------|
| `generate_patients(rows, seed)` | 10K | patient_id, mrn, first_name, last_name, gender, insurance_id |
| `generate_encounters(rows, n_patients, seed)` | 30K | encounter_id, patient_id, encounter_type, admit_datetime |
| `generate_claims(rows, n_encounters, n_patients, seed)` | 30K | claim_id, encounter_id, payer_id, billed_amount |

### Financial (Polars)

| Function | Default Rows | Key Columns |
|----------|-------------|-------------|
| `generate_accounts(rows, seed)` | 10K | account_id, customer_id, account_type, balance, risk_rating |
| `generate_trades(rows, n_accounts, seed)` | 50K | trade_id, account_id, symbol, trade_type, trade_value |
| `generate_transactions(rows, n_accounts, seed)` | 50K | txn_id, account_id, txn_type, amount, channel |

### IoT (Polars)

| Function | Default Rows | Key Columns |
|----------|-------------|-------------|
| `generate_devices(rows, seed)` | 1K | device_id, device_serial, device_type, latitude, longitude |
| `generate_sensor_readings(rows, n_devices, anomaly_rate, seed)` | 50K | reading_id, device_id, metric_name, metric_value, is_anomaly |
| `generate_events(rows, n_devices, seed)` | 10K | event_id, device_id, event_type, severity |
| `generate_telemetry(rows, n_devices, seed)` | 50K | telemetry_id, device_id, latitude, longitude, speed |

### Manufacturing (Polars)

| Function | Default Rows | Key Columns |
|----------|-------------|-------------|
| `generate_equipment(rows, seed)` | 500 | equipment_id, equipment_type, manufacturer, location_zone |
| `generate_sensor_data(rows, n_equipment, fault_rate, seed)` | 25K | reading_id, equipment_id, sensors A-F, is_anomaly |
| `generate_maintenance_records(rows, n_equipment, seed)` | 5K | maintenance_id, equipment_id, maintenance_type, cost |

### CDC (Polars)

| Function | Description |
|----------|-------------|
| `add_cdc_operations(df, weights, seed)` | Add operation/operation_date columns to any Polars DataFrame |

---

## Spark Generators (Tier 2/3 — Connect & Notebooks)

Spark + dbldatagen generators for medium-to-large datasets. Located in `scripts/generators/`.

## Demo Generators (Full Multi-Table Datasets)

Each `generate_*_demo()` creates all related tables for an industry and writes them to Unity Catalog.

| Function | Tables Generated | Default Rows |
|----------|-----------------|-------------|
| `generate_retail_demo(spark, catalog, schema, volume, n_customers=100_000, seed)` | customers, products, transactions, line_items, inventory | ~5.6M total |
| `generate_healthcare_demo(spark, catalog, schema, volume, n_patients=100_000, seed)` | patients, encounters, claims | ~1.1M total |
| `generate_financial_demo(spark, catalog, schema, volume, n_accounts=100_000, seed)` | accounts, trades, transactions | ~2.1M total |
| `generate_iot_demo(spark, catalog, schema, volume, n_devices=10_000, seed)` | devices, sensor_readings, events, telemetry | ~55M total |
| `generate_manufacturing_demo(spark, catalog, schema, volume, n_equipment=1_000, seed)` | equipment, sensor_data, maintenance_records | ~5.1M total |

## CDC Generators (Change-Data-Capture Batches)

Each `generate_*_cdc()` produces batched APPEND/UPDATE/DELETE operations written as JSON to a UC Volume path.

| Function | Base Entity | Default Batches |
|----------|------------|-----------------|
| `generate_retail_cdc(spark, volume_path, n_customers, n_batches=5, seed)` | customers | 5 |
| `generate_healthcare_cdc(spark, volume_path, n_patients, n_batches=5, seed)` | patients | 5 |
| `generate_financial_cdc(spark, volume_path, n_accounts, n_batches=5, seed)` | accounts | 5 |
| `generate_iot_cdc(spark, volume_path, n_devices, n_batches=5, seed)` | devices | 5 |
| `generate_manufacturing_cdc(spark, volume_path, n_equipment, n_batches=5, seed)` | equipment | 5 |

## Individual Table Generators

Fine-grained functions for generating a single table. Use these when you need custom row counts or want to compose tables manually.

### Retail

| Function | Default Rows | Notes | Connect-Safe? |
|----------|-------------|-------|----------------|
| `generate_customers(spark, rows, seed)` | 100K | PII via mimesisText | Partial — mimesisText, template need workarounds |
| `generate_products(spark, rows, seed)` | 10K | Categories, SKUs | Partial — mimesisText needs workaround |
| `generate_transactions(spark, rows, n_customers, seed)` | 1M | FK -> customers | Partial — constraint needs .filter() |
| `generate_line_items(spark, rows, n_transactions, n_products, seed)` | 3M | FK -> transactions, products | Partial — constraint needs .filter() |
| `generate_inventory(spark, rows, n_products, seed)` | 500K | FK -> products | Yes |

### Healthcare

| Function | Default Rows | Notes | Connect-Safe? |
|----------|-------------|-------|----------------|
| `generate_patients(spark, rows, seed)` | 100K | HIPAA-safe synthetic | Partial — mimesisText, template need workarounds |
| `generate_encounters(spark, rows, n_patients, seed)` | 500K | FK -> patients | Partial — mimesisText needs workaround |
| `generate_claims(spark, rows, n_encounters, n_patients, seed)` | 500K | FK -> encounters | Partial — constraint needs .filter() |

### Financial

| Function | Default Rows | Notes | Connect-Safe? |
|----------|-------------|-------|----------------|
| `generate_accounts(spark, rows, seed)` | 100K | Gamma-distributed balances | Partial — Gamma distribution, constraint need workarounds |
| `generate_trades(spark, rows, n_accounts, seed)` | 1M | FK -> accounts | Partial — constraint needs .filter() |
| `generate_financial_transactions(spark, rows, n_accounts, seed)` | 1M | Deposits, withdrawals, transfers | Partial — constraint needs .filter() |
| `generate_streaming_transactions(spark, n_accounts, seed)` | streaming | Rate source | Yes |

### IoT

| Function | Default Rows | Notes | Connect-Safe? |
|----------|-------------|-------|----------------|
| `generate_devices(spark, rows, seed)` | 10K | Device registry | Partial — template needs workaround |
| `generate_sensor_readings(spark, rows, n_devices, start_date, end_date, interval, anomaly_rate, seed)` | 50M | Sinusoidal + anomaly | Partial — Beta distribution needs workaround |
| `generate_events(spark, rows, n_devices, seed)` | 100K | Alerts, notifications | Partial — template needs workaround |
| `generate_telemetry(spark, rows, n_devices, start_date, end_date, interval, seed)` | 5M | GPS/telematics | Yes |
| `generate_streaming_sensors(spark, n_devices, seed)` | streaming | Rate source | Yes |

### Manufacturing

| Function | Default Rows | Notes | Connect-Safe? |
|----------|-------------|-------|----------------|
| `generate_equipment(spark, rows, seed)` | 1K | Asset registry | Partial — template needs workaround |
| `generate_sensor_data(spark, rows, n_equipment, fault_rate, seed)` | 10M | Multi-sensor with fault injection | Partial — constraint needs .filter() |
| `generate_maintenance_records(spark, rows, n_equipment, seed)` | 50K | Work orders, costs | Partial — template, constraint need workarounds |

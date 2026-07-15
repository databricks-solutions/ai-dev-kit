# `ai_forecast` — Full Reference

**Table-valued function** — returns rows, not a scalar. Call with `SELECT * FROM ai_forecast(...)`; from PySpark it must go through `spark.sql()`. Needs a **Pro or Serverless** SQL warehouse. See the [Overview table](SKILL.md#overview) for the signature summary.

## Parameters

| Parameter | Type | Description |
|---|---|---|
| `observed` | TABLE / subquery | Training data; filter or join inside the subquery as needed |
| `horizon` | DATE / TIMESTAMP / STRING | End of the forecast period |
| `time_col` | STRING | DATE or TIMESTAMP column in `observed` (output preserves its type) |
| `value_col` | STRING | One column, or comma-separated for several (≤100 per group); always DOUBLE in output |
| `group_col` | STRING (optional) | Partition into one forecast series per group value |
| `prediction_interval_width` | DOUBLE (optional, default 0.95) | Confidence interval width, 0–1 (narrower = less conservative) |
| `frequency` | STRING (optional) | Forecast step, e.g. `'D'`, `'W'`, `'MS'` (pandas offset alias) — inferred if omitted |
| `seed` | number (optional) | Seed for reproducible forecasts |
| `parameters` | JSON string (optional) | Model hyperparameters — see keys below; any unspecified key is auto-tuned |

**`parameters` JSON keys** (all optional, auto-determined if omitted):

| Key | Meaning |
|---|---|
| `global_floor` | Hard lower bound on forecasts — e.g. `0` so a declining series never predicts negative values (units sold, counts, revenue) |
| `global_cap` | Hard upper bound on forecasts (saturation ceiling) |
| `daily_order` | Fourier order of the daily seasonality component |
| `weekly_order` | Fourier order of the weekly seasonality component |

**Output:** the `time_col` (+ `group_col` if given), then per value column `{metric}_forecast`, `{metric}_upper`, `{metric}_lower` (all DOUBLE).

## Patterns

```sql
-- Grouped, multi-metric, custom interval, filtered input — all params in one call
SELECT *
FROM ai_forecast(
    observed => TABLE(
        SELECT date, region, units, revenue
        FROM daily_kpis
        WHERE date >= '2024-01-01'           -- filter/join inside the subquery
    ),
    horizon                   => '2026-12-31',
    time_col                  => 'date',
    value_col                 => 'units,revenue',   -- comma-separated for multiple
    group_col                 => 'region',          -- one series per region
    prediction_interval_width => 0.80,
    parameters                => '{"global_floor": 0}'  -- never forecast below 0 (units/revenue can't be negative)
);
-- Returns per (date, region): units_forecast/_upper/_lower, revenue_forecast/_upper/_lower
```

`global_floor`/`global_cap` clamp every forecast (point + interval bounds) to a business-valid range — without them a declining series can predict negative values.

```python
# PySpark: table-valued, so call via spark.sql() (no DataFrame API form)
result = spark.sql("""
    SELECT * FROM ai_forecast(
        observed  => TABLE(SELECT date, sales FROM catalog.schema.daily_sales),
        horizon   => '2026-12-31', time_col => 'date', value_col => 'sales')
""")
```

## Notes

- Model is **prophet-like** (piecewise-linear trend + weekly/yearly seasonality) — suited to business series with trend and seasonality.
- Any number of groups; ≤100 metrics per group.

# `ai_forecast` — Full Reference

**Docs:** https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_forecast

> `ai_forecast` is a **table-valued function** — it returns a table of rows, not a scalar. Call it with `SELECT * FROM ai_forecast(...)`.

## Requirements

- **Pro or Serverless SQL warehouse** — not available on Classic or Starter
- Input data must have a DATE or TIMESTAMP time column and at least one numeric value column

## Syntax

```sql
SELECT *
FROM ai_forecast(
    observed                   => TABLE(...) or query,
    horizon                    => 'YYYY-MM-DD' or TIMESTAMP,
    time_col                   => 'column_name',
    value_col                  => 'column_name',
    [group_col                 => 'column_name'],
    [prediction_interval_width => 0.95]
)
```

## Parameters

| Parameter | Type | Description |
|---|---|---|
| `observed` | TABLE reference or subquery | Training data with time + value columns |
| `horizon` | DATE, TIMESTAMP, or STRING | End date/time for the forecast period |
| `time_col` | STRING | Name of the DATE or TIMESTAMP column in `observed` |
| `value_col` | STRING | One or more numeric columns to forecast (up to 100 per group) |
| `group_col` | STRING (optional) | Column to partition forecasts by — produces one forecast series per group value |
| `prediction_interval_width` | DOUBLE (optional, default 0.95) | Confidence interval width between 0 and 1 |

## Output Columns

For each `value_col` named `metric`, the output includes:

| Column | Type | Description |
|---|---|---|
| time_col | DATE or TIMESTAMP | The forecast timestamp (same type as input) |
| `metric_forecast` | DOUBLE | Point forecast |
| `metric_upper` | DOUBLE | Upper confidence bound |
| `metric_lower` | DOUBLE | Lower confidence bound |
| group_col | original type | Present when `group_col` is specified |

## Patterns

### Single Metric Forecast

```sql
SELECT *
FROM ai_forecast(
    observed  => TABLE(SELECT order_date, revenue FROM daily_revenue),
    horizon   => '2026-12-31',
    time_col  => 'order_date',
    value_col => 'revenue'
);
-- Returns: order_date, revenue_forecast, revenue_upper, revenue_lower
```

### Multi-Group Forecast

Produces one forecast series per distinct value of `group_col`:

```sql
SELECT *
FROM ai_forecast(
    observed  => TABLE(SELECT date, region, sales FROM regional_sales),
    horizon   => '2026-12-31',
    time_col  => 'date',
    value_col => 'sales',
    group_col => 'region'
);
-- Returns: date, region, sales_forecast, sales_upper, sales_lower
-- One row per date per region
```

### Multiple Value Columns

```sql
SELECT *
FROM ai_forecast(
    observed  => TABLE(SELECT date, units, revenue FROM daily_kpis),
    horizon   => '2026-06-30',
    time_col  => 'date',
    value_col => 'units,revenue'   -- comma-separated
);
-- Returns: date, units_forecast, units_upper, units_lower,
--                revenue_forecast, revenue_upper, revenue_lower
```

### Custom Confidence Interval

```sql
SELECT *
FROM ai_forecast(
    observed                   => TABLE(SELECT ts, sensor_value FROM iot_readings),
    horizon                    => '2026-03-31',
    time_col                   => 'ts',
    value_col                  => 'sensor_value',
    prediction_interval_width  => 0.80   -- narrower interval = less conservative
);
```

### Filtering Input Data (Subquery)

```sql
SELECT *
FROM ai_forecast(
    observed  => TABLE(
        SELECT date, sales
        FROM daily_sales
        WHERE region = 'BR' AND date >= '2024-01-01'
    ),
    horizon   => '2026-12-31',
    time_col  => 'date',
    value_col => 'sales'
);
```

### PySpark — Use `spark.sql()`

`ai_forecast` is a table-valued function and must be called through `spark.sql()`:

```python
result = spark.sql("""
    SELECT *
    FROM ai_forecast(
        observed  => TABLE(SELECT date, sales FROM catalog.schema.daily_sales),
        horizon   => '2026-12-31',
        time_col  => 'date',
        value_col => 'sales'
    )
""")
result.display()
```

### Save Forecast to Delta Table

```python
result = spark.sql("""
    SELECT *
    FROM ai_forecast(
        observed  => TABLE(SELECT date, region, revenue FROM catalog.schema.sales),
        horizon   => '2026-12-31',
        time_col  => 'date',
        value_col => 'revenue',
        group_col => 'region'
    )
""")
result.write.format("delta").mode("overwrite").saveAsTable("catalog.schema.revenue_forecast")
```

## Notes

- The underlying model is a **prophet-like piecewise linear + seasonality model** — suitable for business time series with trend and weekly/yearly seasonality
- Handles "any number of groups" but up to **100 metrics per group**
- Output time column preserves the input type (DATE stays DATE, TIMESTAMP stays TIMESTAMP)
- Value columns are always cast to DOUBLE in output regardless of input type

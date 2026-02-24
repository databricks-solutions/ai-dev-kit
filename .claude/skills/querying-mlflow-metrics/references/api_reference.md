# MLflow Trace Metrics API Reference

## Endpoint
`POST /api/3.0/mlflow/traces/metrics`

## Available Metrics

### TRACES view (view_type=1)
| Metric | Description | Aggregations |
|--------|-------------|--------------|
| `trace_count` | Number of traces | COUNT |
| `latency` | Execution time (ms) | AVG, PERCENTILE |
| `input_tokens` | Input token count | SUM, AVG, PERCENTILE |
| `output_tokens` | Output token count | SUM, AVG, PERCENTILE |
| `total_tokens` | Total token count | SUM, AVG, PERCENTILE |

### SPANS view (view_type=2)
| Metric | Description | Aggregations |
|--------|-------------|--------------|
| `span_count` | Number of spans | COUNT |
| `latency` | Span duration (ms) | AVG, PERCENTILE |

### ASSESSMENTS view (view_type=3)
| Metric | Description | Aggregations |
|--------|-------------|--------------|
| `assessment_count` | Number of assessments | COUNT |
| `assessment_value` | Assessment score | AVG, PERCENTILE |

## Aggregation Types
| Name | Code | Description |
|------|------|-------------|
| COUNT | 1 | Count of entities |
| SUM | 2 | Sum of values |
| AVG | 3 | Average of values |
| PERCENTILE | 4 | Percentile (requires percentile_value) |
| MIN | 5 | Minimum value |
| MAX | 6 | Maximum value |

Percentile shorthand: `P50`, `P90`, `P95`, `P99`, `P99.9`

## Dimensions (grouping)

### TRACES
- `trace_name` - Group by trace name
- `trace_status` - Group by status (OK, ERROR)

### SPANS
- `span_name` - Group by span name
- `span_type` - Group by span type (LLM, TOOL, etc.)
- `span_status` - Group by span status

### ASSESSMENTS
- `assessment_name` - Group by assessment name
- `assessment_value` - Group by assessment value

## Filter Syntax
```
trace.status = "OK"
trace.tag.<key> = "<value>"
trace.metadata.<key> = "<value>"
span.name = "<value>"
span.type = "LLM"
assessment.name = "<value>"
```

## Time Intervals (seconds)
| Interval | Seconds |
|----------|---------|
| Minute | 60 |
| Hour | 3600 |
| Day | 86400 |
| Week | 604800 |

## Example Request
```json
{
  "experiment_ids": ["1"],
  "view_type": 1,
  "metric_name": "total_tokens",
  "aggregations": [
    {"aggregation_type": 2},
    {"aggregation_type": 3}
  ],
  "dimensions": ["trace_name"],
  "time_interval_seconds": 3600,
  "start_time_ms": 1737244800000,
  "end_time_ms": 1737331200000
}
```

## Example Response
```json
{
  "data_points": [
    {
      "metric_name": "total_tokens",
      "dimensions": {"time_bucket": "2024-01-19T00:00:00+00:00", "trace_name": "chat"},
      "values": {"SUM": 15000, "AVG": 500.0}
    }
  ],
  "next_page_token": null
}
```

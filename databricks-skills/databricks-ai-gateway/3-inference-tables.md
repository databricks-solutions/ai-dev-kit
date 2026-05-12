# Inference Tables

Log request/response payloads from serving endpoints to Unity Catalog Delta tables.

## Overview

Inference tables capture every request and response flowing through an AI Gateway endpoint. Payloads are written to a managed Delta table in Unity Catalog at `{catalog}.{schema}.{prefix}_request_response`. Use them for debugging failed requests, monitoring token usage and latency, and compliance auditing.

## Enable Inference Tables

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import AiGatewayInferenceTableConfig

w = WorkspaceClient()

w.serving_endpoints.put_ai_gateway(
    name="my-llm-endpoint",
    inference_table_config=AiGatewayInferenceTableConfig(
        catalog_name="analytics",
        schema_name="serving_logs",
        table_name_prefix="my_endpoint",
        enabled=True,
    ),
)
```

## REST API Example

```bash
curl -X PUT \
  "${DATABRICKS_HOST}/api/2.0/serving-endpoints/my-llm-endpoint/ai-gateway" \
  -H "Authorization: Bearer ${DATABRICKS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "inference_table_config": {
      "catalog_name": "analytics",
      "schema_name": "serving_logs",
      "table_name_prefix": "my_endpoint",
      "enabled": true
    }
  }'
```

## Table Schema Reference

The table `{table_name_prefix}_request_response` contains:

| Column | Type | Description |
|--------|------|-------------|
| `databricks_request_id` | STRING | Unique Databricks-assigned request ID |
| `client_request_id` | STRING | Client-provided request ID (if set) |
| `request_time` | TIMESTAMP | When the request was received |
| `status_code` | INT | HTTP status code of the response |
| `request_payload` | STRING | JSON-serialized request body |
| `response_payload` | STRING | JSON-serialized response body |
| `endpoint_name` | STRING | Name of the serving endpoint |
| `input_token_count` | LONG | Tokens in the request prompt |
| `output_token_count` | LONG | Tokens in the response completion |
| `request_streaming` | BOOLEAN | Whether the request used streaming |

## Query Examples

```sql
-- Request volume by hour
SELECT date_trunc('hour', request_time) AS hour, COUNT(*) AS request_count
FROM analytics.serving_logs.my_endpoint_request_response
GROUP BY 1 ORDER BY 1 DESC;

-- Average token usage per request
SELECT
  AVG(input_token_count) AS avg_input_tokens,
  AVG(output_token_count) AS avg_output_tokens,
  AVG(input_token_count + output_token_count) AS avg_total_tokens
FROM analytics.serving_logs.my_endpoint_request_response
WHERE request_time >= current_date() - INTERVAL 1 DAY;

-- Error rate monitoring
SELECT
  date_trunc('hour', request_time) AS hour,
  COUNT_IF(status_code != 200) AS errors,
  COUNT(*) AS total,
  ROUND(COUNT_IF(status_code != 200) / COUNT(*) * 100, 2) AS error_rate_pct
FROM analytics.serving_logs.my_endpoint_request_response
GROUP BY 1 ORDER BY 1 DESC;

-- Find requests with high latency (proxy via large output)
SELECT databricks_request_id, request_time, output_token_count, status_code
FROM analytics.serving_logs.my_endpoint_request_response
WHERE output_token_count > 2000
ORDER BY output_token_count DESC LIMIT 20;

-- Sample recent payloads for debugging
SELECT databricks_request_id, status_code, request_payload, response_payload
FROM analytics.serving_logs.my_endpoint_request_response
ORDER BY request_time DESC LIMIT 5;
```

## Update or Disable

You must disable inference tables before changing the catalog, schema, or prefix. This is a SDK constraint: update calls that change these fields while enabled will fail.

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import AiGatewayInferenceTableConfig

w = WorkspaceClient()

# Step 1: Disable
w.serving_endpoints.put_ai_gateway(
    name="my-llm-endpoint",
    inference_table_config=AiGatewayInferenceTableConfig(enabled=False),
)

# Step 2: Re-enable with new settings
w.serving_endpoints.put_ai_gateway(
    name="my-llm-endpoint",
    inference_table_config=AiGatewayInferenceTableConfig(
        catalog_name="new_catalog",
        schema_name="new_schema",
        table_name_prefix="new_prefix",
        enabled=True,
    ),
)
```

## Limitations

- Payloads larger than 1 MiB are excluded from logging
- Table population can take up to an hour after first enable
- Storage costs apply (data is stored in UC managed storage)
- Must disable inference tables before changing catalog, schema, or prefix settings

# Observability

Monitor usage, costs, and audit trails across all AI Gateway endpoints using system tables, usage tracking, and unified dashboards.

## Three Pillars

1. **Usage Tracking** -- System tables (`system.serving.*`) record per-request metadata: tokens, status codes, requester identity, and custom tags.
2. **Payload Logging** -- Inference tables capture full request/response bodies. See [3-inference-tables.md](3-inference-tables.md).
3. **V2 Unified Dashboard (Beta)** -- Single pane across LLM endpoints, coding agents, and MCP servers with real dollar cost attribution.

## Enable Usage Tracking

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import AiGatewayUsageTrackingConfig

w = WorkspaceClient()
w.serving_endpoints.put_ai_gateway(
    name="my-llm-endpoint",
    usage_tracking_config=AiGatewayUsageTrackingConfig(enabled=True),
)
```

## System Tables Reference

### `system.serving.endpoint_usage`

| Column | Type | Description |
|--------|------|-------------|
| `client_request_id` | STRING | Client-provided request ID |
| `databricks_request_id` | STRING | Unique Databricks-assigned request ID |
| `requester` | STRING | Identity of the user or service principal |
| `status_code` | INT | HTTP status code of the response |
| `request_time` | TIMESTAMP | When the request was received |
| `input_token_count` | LONG | Tokens in the request prompt |
| `output_token_count` | LONG | Tokens in the response completion |
| `input_character_count` | LONG | Characters in the request prompt |
| `output_character_count` | LONG | Characters in the response completion |
| `usage_context` | MAP<STRING, STRING> | Custom key-value tags passed by the client |
| `request_streaming` | BOOLEAN | Whether the request used streaming |
| `endpoint_name` | STRING | Name of the serving endpoint |

### `system.serving.served_entities`

| Column | Type | Description |
|--------|------|-------------|
| `served_entity_id` | STRING | Unique ID for the served entity |
| `account_id` | STRING | Databricks account ID |
| `workspace_id` | STRING | Workspace ID where the endpoint lives |
| `endpoint_name` | STRING | Name of the serving endpoint |
| `entity_type` | STRING | One of: FEATURE_SPEC, EXTERNAL_MODEL, FOUNDATION_MODEL, CUSTOM_MODEL |
| `external_model_config` | STRING | JSON config for external model entities |
| `foundation_model_config` | STRING | JSON config for foundation model entities |
| `custom_model_config` | STRING | JSON config for custom model entities |

## Usage Queries

```sql
-- Daily token consumption by endpoint (last 30 days)
SELECT endpoint_name, DATE(request_time) AS day,
  SUM(input_token_count) AS input_tokens, SUM(output_token_count) AS output_tokens
FROM system.serving.endpoint_usage
WHERE request_time >= current_date() - INTERVAL 30 DAYS
GROUP BY endpoint_name, DATE(request_time)
ORDER BY day DESC;

-- Top 10 users by request count
SELECT requester, COUNT(*) AS requests, SUM(output_token_count) AS total_output_tokens
FROM system.serving.endpoint_usage
WHERE request_time >= current_date() - INTERVAL 7 DAYS
GROUP BY requester ORDER BY requests DESC LIMIT 10;

-- Error rate by endpoint (% non-200)
SELECT endpoint_name, COUNT(*) AS total,
  COUNT_IF(status_code != 200) AS errors,
  ROUND(COUNT_IF(status_code != 200) / COUNT(*) * 100, 2) AS error_rate_pct
FROM system.serving.endpoint_usage
WHERE request_time >= current_date() - INTERVAL 7 DAYS
GROUP BY endpoint_name ORDER BY error_rate_pct DESC;

-- Token cost estimation (adjust rates to your contracts)
WITH pricing AS (
  SELECT 'llama-endpoint' AS endpoint, 0.00065 AS input_per_1k, 0.00195 AS output_per_1k
  UNION ALL SELECT 'gpt-4o-endpoint', 0.0025, 0.01
  UNION ALL SELECT 'claude-sonnet-endpoint', 0.003, 0.015)
SELECT u.endpoint_name,
  ROUND(SUM(u.input_token_count / 1000.0 * p.input_per_1k
          + u.output_token_count / 1000.0 * p.output_per_1k), 2) AS estimated_cost_usd
FROM system.serving.endpoint_usage u
JOIN pricing p ON u.endpoint_name = p.endpoint
WHERE u.request_time >= current_date() - INTERVAL 30 DAYS
GROUP BY u.endpoint_name ORDER BY estimated_cost_usd DESC;
```

> **Note:** System tables record `request_time` but not latency. For p50/p90/p99 latency, use inference tables which capture both request and response timestamps.

## Usage Context

Attach custom key-value tags to requests for cost attribution. Pass via `extra_body` with the OpenAI-compatible client:

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://my-workspace.cloud.databricks.com/serving-endpoints",
    api_key="dapi...",
)

response = client.chat.completions.create(
    model="my-llm-endpoint",
    messages=[{"role": "user", "content": "Summarize Q4 results"}],
    extra_body={
        "usage_context": {
            "project": "chatbot",
            "team": "data-science",
            "cost_center": "CC-1234",
        }
    },
)
```

Slice costs by usage context:

```sql
SELECT usage_context['project'] AS project, usage_context['team'] AS team,
  COUNT(*) AS requests, SUM(input_token_count + output_token_count) AS total_tokens
FROM system.serving.endpoint_usage
WHERE request_time >= current_date() - INTERVAL 30 DAYS
  AND usage_context['project'] IS NOT NULL
GROUP BY 1, 2 ORDER BY total_tokens DESC;
```

## V2: Real Dollar Cost Attribution

> **Beta** -- Available in AI Gateway V2.

V2 calculates actual dollar costs instead of raw token counts. It accounts for provisioned throughput pricing, pay-per-token rates, and external provider pricing (OpenAI, Anthropic, etc.). Eliminates manual pricing CTEs and handles blended costs when endpoints use fallback routing across providers.

## V2: Unified Dashboard

V2 provides a single observability pane across LLM serving endpoints, coding agents (e.g., Databricks Assistant), and MCP servers.

- **Cross-tool usage queries** -- Compare token consumption and costs across LLM endpoints and agent frameworks in one view.
- **Genie Code integration** -- Ask natural language questions about your AI usage and get SQL-backed answers.
- **MLflow trace debugging** -- Click from a dashboard anomaly directly into MLflow traces to debug specific requests.

## Audit Trail Queries

```sql
-- Requests by a specific user in a time window
SELECT databricks_request_id, endpoint_name, status_code, request_time,
       input_token_count, output_token_count
FROM system.serving.endpoint_usage
WHERE requester = 'user@company.com'
  AND request_time BETWEEN '2026-04-01' AND '2026-04-15'
ORDER BY request_time DESC;

-- All error requests to a specific endpoint
SELECT databricks_request_id, requester, status_code, request_time
FROM system.serving.endpoint_usage
WHERE endpoint_name = 'my-llm-endpoint'
  AND status_code != 200
  AND request_time >= current_date() - INTERVAL 7 DAYS
ORDER BY request_time DESC;

-- Usage breakdown by usage_context tags
SELECT usage_context['project'] AS project, usage_context['cost_center'] AS cost_center,
  COUNT(*) AS requests, SUM(input_token_count) AS input_tokens, SUM(output_token_count) AS output_tokens
FROM system.serving.endpoint_usage
WHERE request_time >= current_date() - INTERVAL 30 DAYS
GROUP BY 1, 2 ORDER BY requests DESC;
```

# AI Gateway

Configure governance features for model serving: rate limits, guardrails, inference tables, and usage tracking.

---

## Overview

AI Gateway provides:
- **Inference Tables**: Log all requests/responses to Unity Catalog
- **Rate Limits**: Control request rates per user/endpoint
- **Guardrails**: Content filtering and safety checks
- **Usage Tracking**: Monitor token usage and costs
- **Fallback Routes**: Automatic failover between models

---

## Enabling AI Gateway

### On New Endpoint

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    EndpointCoreConfigInput,
    ServedEntityInput,
    AiGatewayConfig,
    AiGatewayInferenceTableConfig,
    AiGatewayRateLimitConfig,
    AiGatewayGuardrailConfig,
    AiGatewayUsageTrackingConfig,
)

w = WorkspaceClient()

endpoint = w.serving_endpoints.create_and_wait(
    name="governed-endpoint",
    config=EndpointCoreConfigInput(
        served_entities=[
            ServedEntityInput(
                name="gpt-4o",
                external_model=ExternalModel(
                    name="gpt-4o",
                    provider="openai",
                    task="llm/v1/chat",
                    openai_config=OpenAiConfig(
                        openai_api_key="{{secrets/llm-keys/openai-key}}",
                    ),
                ),
            )
        ]
    ),
    ai_gateway=AiGatewayConfig(
        # Enable inference tables
        inference_table_config=AiGatewayInferenceTableConfig(
            catalog_name="my_catalog",
            schema_name="my_schema",
            table_name_prefix="llm_logs",
            enabled=True,
        ),
        # Enable usage tracking
        usage_tracking_config=AiGatewayUsageTrackingConfig(
            enabled=True,
        ),
        # Rate limits
        rate_limits=[
            AiGatewayRateLimitConfig(
                calls=100,
                renewal_period="minute",
            ),
        ],
    ),
)
```

### On Existing Endpoint

```python
# Update endpoint with AI Gateway config
w.serving_endpoints.put_ai_gateway(
    name="my-endpoint",
    inference_table_config=AiGatewayInferenceTableConfig(
        catalog_name="my_catalog",
        schema_name="my_schema", 
        table_name_prefix="llm_logs",
        enabled=True,
    ),
    usage_tracking_config=AiGatewayUsageTrackingConfig(
        enabled=True,
    ),
)
```

---

## Inference Tables

### Configuration

```python
AiGatewayInferenceTableConfig(
    catalog_name="my_catalog",       # Unity Catalog
    schema_name="my_schema",         # Schema name
    table_name_prefix="my_prefix",   # Prefix for tables
    enabled=True,
)
```

This creates tables:
- `my_catalog.my_schema.my_prefix_request_response` - Full request/response logs
- `my_catalog.my_schema.my_prefix_assessment` - Guardrail assessments

### Query Inference Tables

```sql
-- Recent requests
SELECT 
    request_id,
    timestamp_ms,
    request,
    response,
    status_code,
    execution_time_ms,
    input_tokens,
    output_tokens
FROM my_catalog.my_schema.my_prefix_request_response
WHERE date(from_unixtime(timestamp_ms/1000)) = current_date()
ORDER BY timestamp_ms DESC
LIMIT 100;

-- Error analysis
SELECT 
    status_code,
    count(*) as error_count,
    collect_list(request_id)[0] as sample_request_id
FROM my_catalog.my_schema.my_prefix_request_response
WHERE status_code >= 400
GROUP BY status_code
ORDER BY error_count DESC;

-- Token usage by hour
SELECT 
    date_trunc('hour', from_unixtime(timestamp_ms/1000)) as hour,
    sum(input_tokens) as total_input_tokens,
    sum(output_tokens) as total_output_tokens,
    count(*) as request_count
FROM my_catalog.my_schema.my_prefix_request_response
GROUP BY 1
ORDER BY 1 DESC;
```

### Analyze Request Content

```sql
-- Extract user messages
SELECT 
    request_id,
    get_json_object(request, '$.messages[*].content') as user_content,
    get_json_object(response, '$.choices[0].message.content') as assistant_response
FROM my_catalog.my_schema.my_prefix_request_response
LIMIT 10;
```

---

## Rate Limits

### Per-Endpoint Rate Limits

```python
AiGatewayConfig(
    rate_limits=[
        # Global limit
        AiGatewayRateLimitConfig(
            calls=1000,
            renewal_period="minute",
        ),
        # Per-user limit
        AiGatewayRateLimitConfig(
            calls=100,
            renewal_period="minute",
            key="user",  # Rate limit per user
        ),
    ],
)
```

### Renewal Periods

| Period | Description |
|--------|-------------|
| `second` | Per second |
| `minute` | Per minute |
| `hour` | Per hour |
| `day` | Per day |

### Rate Limit Keys

| Key | Description |
|-----|-------------|
| `endpoint` | Total across endpoint (default) |
| `user` | Per authenticated user |

---

## Guardrails

### Content Safety

```python
from databricks.sdk.service.serving import (
    AiGatewayGuardrails,
    AiGatewayGuardrailParameters,
    AiGatewayGuardrailPiiConfig,
)

AiGatewayConfig(
    guardrails=AiGatewayGuardrails(
        input=AiGatewayGuardrailParameters(
            # Block invalid topics
            invalid_keywords=["confidential", "secret", "password"],
            # Detect PII
            pii=AiGatewayGuardrailPiiConfig(
                behavior="BLOCK",  # or "MASK"
            ),
            # Safety filter
            safety=True,
        ),
        output=AiGatewayGuardrailParameters(
            # Filter output
            invalid_keywords=["error", "exception"],
            pii=AiGatewayGuardrailPiiConfig(
                behavior="MASK",  # Mask PII in responses
            ),
            safety=True,
        ),
    ),
)
```

### PII Detection

| Behavior | Description |
|----------|-------------|
| `NONE` | No PII filtering |
| `BLOCK` | Block requests/responses with PII |
| `MASK` | Replace PII with [REDACTED] |

### Query Guardrail Assessments

```sql
-- Blocked requests
SELECT 
    request_id,
    timestamp_ms,
    assessment_type,
    assessment_result,
    assessment_details
FROM my_catalog.my_schema.my_prefix_assessment
WHERE assessment_result = 'BLOCKED'
ORDER BY timestamp_ms DESC;

-- PII detections
SELECT 
    request_id,
    assessment_details
FROM my_catalog.my_schema.my_prefix_assessment
WHERE assessment_type = 'PII'
ORDER BY timestamp_ms DESC;
```

---

## Usage Tracking

### Enable Usage Tracking

```python
AiGatewayConfig(
    usage_tracking_config=AiGatewayUsageTrackingConfig(
        enabled=True,
    ),
)
```

### Query Usage Metrics

```sql
-- Daily token usage
SELECT 
    date(from_unixtime(timestamp_ms/1000)) as date,
    sum(input_tokens) as input_tokens,
    sum(output_tokens) as output_tokens,
    sum(input_tokens + output_tokens) as total_tokens,
    count(*) as requests
FROM my_catalog.my_schema.my_prefix_request_response
GROUP BY 1
ORDER BY 1 DESC;

-- Cost estimation (example rates)
SELECT 
    date(from_unixtime(timestamp_ms/1000)) as date,
    sum(input_tokens) * 0.00001 as input_cost,
    sum(output_tokens) * 0.00003 as output_cost,
    sum(input_tokens * 0.00001 + output_tokens * 0.00003) as total_cost
FROM my_catalog.my_schema.my_prefix_request_response
GROUP BY 1
ORDER BY 1 DESC;
```

---

## Fallback Routes

Configure automatic failover between providers:

```python
from databricks.sdk.service.serving import AiGatewayFallbackConfig

endpoint = w.serving_endpoints.create_and_wait(
    name="resilient-endpoint",
    config=EndpointCoreConfigInput(
        served_entities=[
            # Primary
            ServedEntityInput(
                name="primary-openai",
                external_model=ExternalModel(
                    name="gpt-4o",
                    provider="openai",
                    task="llm/v1/chat",
                    openai_config=OpenAiConfig(
                        openai_api_key="{{secrets/llm-keys/openai-key}}",
                    ),
                ),
            ),
            # Fallback
            ServedEntityInput(
                name="fallback-anthropic",
                external_model=ExternalModel(
                    name="claude-3-opus-20240229",
                    provider="anthropic",
                    task="llm/v1/chat",
                    anthropic_config=AnthropicConfig(
                        anthropic_api_key="{{secrets/llm-keys/anthropic-key}}",
                    ),
                ),
            ),
        ],
    ),
    ai_gateway=AiGatewayConfig(
        fallback_config=AiGatewayFallbackConfig(
            enabled=True,
        ),
    ),
)
```

When primary fails (rate limit, error), requests automatically route to fallback.

---

## Endpoint Tags for Cost Allocation

Tag endpoints for billing attribution:

```python
from databricks.sdk.service.serving import EndpointTag

endpoint = w.serving_endpoints.create_and_wait(
    name="my-endpoint",
    config=EndpointCoreConfigInput(...),
    tags=[
        EndpointTag(key="team", value="data-science"),
        EndpointTag(key="project", value="customer-support"),
        EndpointTag(key="environment", value="production"),
        EndpointTag(key="cost-center", value="CC-1234"),
    ],
)

# Update tags on existing endpoint
w.serving_endpoints.patch(
    name="my-endpoint",
    add_tags=[
        EndpointTag(key="new-tag", value="new-value"),
    ],
    delete_tags=["old-tag"],
)
```

---

## Complete AI Gateway Example

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    EndpointCoreConfigInput,
    ServedEntityInput,
    ExternalModel,
    OpenAiConfig,
    AiGatewayConfig,
    AiGatewayInferenceTableConfig,
    AiGatewayRateLimitConfig,
    AiGatewayGuardrails,
    AiGatewayGuardrailParameters,
    AiGatewayGuardrailPiiConfig,
    AiGatewayUsageTrackingConfig,
    EndpointTag,
)

w = WorkspaceClient()

endpoint = w.serving_endpoints.create_and_wait(
    name="production-llm",
    config=EndpointCoreConfigInput(
        served_entities=[
            ServedEntityInput(
                name="gpt-4o",
                external_model=ExternalModel(
                    name="gpt-4o",
                    provider="openai",
                    task="llm/v1/chat",
                    openai_config=OpenAiConfig(
                        openai_api_key="{{secrets/production/openai-key}}",
                    ),
                ),
            )
        ]
    ),
    ai_gateway=AiGatewayConfig(
        # Logging
        inference_table_config=AiGatewayInferenceTableConfig(
            catalog_name="prod_catalog",
            schema_name="llm_monitoring",
            table_name_prefix="production_llm",
            enabled=True,
        ),
        # Usage tracking
        usage_tracking_config=AiGatewayUsageTrackingConfig(
            enabled=True,
        ),
        # Rate limits
        rate_limits=[
            AiGatewayRateLimitConfig(
                calls=10000,
                renewal_period="minute",
            ),
            AiGatewayRateLimitConfig(
                calls=100,
                renewal_period="minute",
                key="user",
            ),
        ],
        # Guardrails
        guardrails=AiGatewayGuardrails(
            input=AiGatewayGuardrailParameters(
                pii=AiGatewayGuardrailPiiConfig(behavior="BLOCK"),
                safety=True,
            ),
            output=AiGatewayGuardrailParameters(
                pii=AiGatewayGuardrailPiiConfig(behavior="MASK"),
                safety=True,
            ),
        ),
    ),
    # Tags for cost allocation
    tags=[
        EndpointTag(key="team", value="platform"),
        EndpointTag(key="environment", value="production"),
    ],
)

print(f"Endpoint created: {endpoint.name}")
```

---

## Monitoring Dashboard Query

Build a monitoring dashboard with this query:

```sql
WITH hourly_stats AS (
    SELECT 
        date_trunc('hour', from_unixtime(timestamp_ms/1000)) as hour,
        count(*) as requests,
        sum(input_tokens) as input_tokens,
        sum(output_tokens) as output_tokens,
        avg(execution_time_ms) as avg_latency_ms,
        percentile(execution_time_ms, 0.95) as p95_latency_ms,
        sum(case when status_code >= 400 then 1 else 0 end) as errors
    FROM my_catalog.my_schema.my_prefix_request_response
    WHERE timestamp_ms > unix_timestamp(current_date() - INTERVAL 7 DAY) * 1000
    GROUP BY 1
)
SELECT 
    hour,
    requests,
    input_tokens + output_tokens as total_tokens,
    round(avg_latency_ms, 0) as avg_latency_ms,
    round(p95_latency_ms, 0) as p95_latency_ms,
    round(100.0 * errors / requests, 2) as error_rate_pct
FROM hourly_stats
ORDER BY hour DESC;
```

---

## Best Practices

1. **Enable inference tables** for all production endpoints
2. **Set rate limits** to prevent runaway costs
3. **Use PII guardrails** for customer-facing applications
4. **Tag endpoints** for cost allocation
5. **Monitor token usage** to optimize prompts
6. **Configure fallbacks** for high-availability
7. **Review blocked requests** to tune guardrails
8. **Set up alerts** on error rates and latency

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **Inference table not created** | Check catalog/schema permissions |
| **Rate limit too aggressive** | Increase limits or use per-user limits |
| **PII blocking too much** | Review false positives, adjust keywords |
| **High latency with guardrails** | Guardrails add ~50-100ms overhead |
| **Missing usage data** | Enable usage_tracking_config explicitly |
| **Tags not propagating** | Tags sync to billing with delay |

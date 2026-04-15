# Rate Limits and Fallbacks

Control request throughput per user, team, or endpoint and enable automatic failover across served entities.

## Rate Limits Overview

AI Gateway supports two rate limit types:

- **QPM (queries per minute)** -- limits the number of API calls. Works for all endpoint types.
- **TPM (tokens per minute)** -- limits token consumption. Works only for Foundation Model API endpoints.

Rate limits are **hierarchical**. You can set limits at multiple scopes simultaneously:

1. **Endpoint-level** -- global cap across all callers
2. **User-level** -- per-user fair sharing (identified by the authenticated principal)
3. **User-group-level** -- team quotas (Databricks group name)
4. **Service-principal-level** -- API client limits (application ID)

When a caller exceeds their limit, the gateway returns **HTTP 429 Too Many Requests** with a `Retry-After` header. More specific rules (user/group/SP) are evaluated before the endpoint-level cap.

## Rate Limit Key Reference

| Key | Scope | Example Use Case |
|-----|-------|------------------|
| `ENDPOINT` | Global cap across all callers | Hard ceiling of 2000 QPM for the entire endpoint |
| `USER` | Per-user (authenticated identity) | Fair sharing: each user gets 100 QPM |
| `USER_GROUP` | Per-group (Databricks group name) | Team quotas: data-science-team gets 500 QPM |
| `SERVICE_PRINCIPAL` | Per-service-principal (app ID) | API client limits: production pipeline SP gets 1000 QPM |

## QPM Rate Limits

Three rules: per-user default, group override, and endpoint cap.

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    AiGatewayRateLimit,
    AiGatewayRateLimitKey,
    AiGatewayRateLimitRenewalPeriod,
)

w = WorkspaceClient()

w.serving_endpoints.put_ai_gateway(
    name="my-llm-endpoint",
    rate_limits=[
        # Every user gets 100 QPM by default
        AiGatewayRateLimit(
            calls=100,
            key=AiGatewayRateLimitKey.USER,
            renewal_period=AiGatewayRateLimitRenewalPeriod.MINUTE,
        ),
        # data-science-team group gets 500 QPM shared across members
        AiGatewayRateLimit(
            calls=500,
            key=AiGatewayRateLimitKey.USER_GROUP,
            principal="data-science-team",
            renewal_period=AiGatewayRateLimitRenewalPeriod.MINUTE,
        ),
        # Hard cap for the entire endpoint
        AiGatewayRateLimit(
            calls=2000,
            key=AiGatewayRateLimitKey.ENDPOINT,
            renewal_period=AiGatewayRateLimitRenewalPeriod.MINUTE,
        ),
    ],
)
```

## TPM Rate Limits

Token-based limits for Foundation Model API endpoints.

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    AiGatewayRateLimit,
    AiGatewayRateLimitKey,
    AiGatewayRateLimitRenewalPeriod,
)

w = WorkspaceClient()

w.serving_endpoints.put_ai_gateway(
    name="my-fmapi-endpoint",
    rate_limits=[
        AiGatewayRateLimit(
            tokens=50000,
            key=AiGatewayRateLimitKey.USER,
            renewal_period=AiGatewayRateLimitRenewalPeriod.MINUTE,
        ),
        AiGatewayRateLimit(
            tokens=500000,
            key=AiGatewayRateLimitKey.ENDPOINT,
            renewal_period=AiGatewayRateLimitRenewalPeriod.MINUTE,
        ),
    ],
)
```

> **Important:** TPM limits only work for Foundation Model API endpoints, not custom models or agents. Use QPM (`calls`) for custom model and agent endpoints.

## Combined Rate Limit Example

Five rules layered: endpoint cap, default user, two group overrides, one service principal.

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    AiGatewayRateLimit,
    AiGatewayRateLimitKey,
    AiGatewayRateLimitRenewalPeriod,
)

w = WorkspaceClient()

w.serving_endpoints.put_ai_gateway(
    name="my-llm-endpoint",
    rate_limits=[
        # 1. Endpoint-level hard cap
        AiGatewayRateLimit(
            calls=5000,
            key=AiGatewayRateLimitKey.ENDPOINT,
            renewal_period=AiGatewayRateLimitRenewalPeriod.MINUTE,
        ),
        # 2. Default per-user limit
        AiGatewayRateLimit(
            calls=100,
            key=AiGatewayRateLimitKey.USER,
            renewal_period=AiGatewayRateLimitRenewalPeriod.MINUTE,
        ),
        # 3. Engineering team gets a higher group quota
        AiGatewayRateLimit(
            calls=1500,
            key=AiGatewayRateLimitKey.USER_GROUP,
            principal="engineering",
            renewal_period=AiGatewayRateLimitRenewalPeriod.MINUTE,
        ),
        # 4. Analytics team gets a moderate group quota
        AiGatewayRateLimit(
            calls=800,
            key=AiGatewayRateLimitKey.USER_GROUP,
            principal="analytics",
            renewal_period=AiGatewayRateLimitRenewalPeriod.MINUTE,
        ),
        # 5. Production pipeline service principal
        AiGatewayRateLimit(
            calls=2000,
            key=AiGatewayRateLimitKey.SERVICE_PRINCIPAL,
            principal="<service-principal-application-id>",
            renewal_period=AiGatewayRateLimitRenewalPeriod.MINUTE,
        ),
    ],
)
```

## Constraints

| Constraint | Limit |
|-----------|-------|
| Max rate limit rules per endpoint | 20 |
| Max group-specific rules (`USER_GROUP`) | 5 |
| TPM (`tokens`) support | Foundation Model API endpoints only |
| Renewal period | `minute` is the only supported value |
| Burst behavior | Concurrent requests may briefly exceed the limit before counts are synchronized |

## REST API Example

```bash
curl -X PUT \
  "${DATABRICKS_HOST}/api/2.0/serving-endpoints/my-llm-endpoint/ai-gateway" \
  -H "Authorization: Bearer ${DATABRICKS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "rate_limits": [
      {
        "calls": 100,
        "key": "user",
        "renewal_period": "minute"
      },
      {
        "calls": 500,
        "key": "user_group",
        "principal": "data-science-team",
        "renewal_period": "minute"
      },
      {
        "calls": 2000,
        "key": "endpoint",
        "renewal_period": "minute"
      }
    ]
  }'
```

## Fallback Configuration

`FallbackConfig` has a single field: `enabled: bool`.

When enabled, if a served entity returns **429** (rate limited) or **5xx** (server error), the gateway automatically **round-robins** the request to other served entities on the same endpoint. This provides automatic failover without client-side retry logic.

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import FallbackConfig

w = WorkspaceClient()

w.serving_endpoints.put_ai_gateway(
    name="my-llm-endpoint",
    fallback_config=FallbackConfig(enabled=True),
)
```

**Limitation:** Fallback requires multiple served entities configured on the endpoint. If the endpoint has only one served entity, there is nothing to fall back to.

## Traffic Splitting

Traffic splitting is configured on the **serving endpoint itself**, not via `put_ai_gateway`. Use `traffic_config` to route percentages of traffic to specific served entities. This is useful for gradual rollouts and A/B testing.

Conceptual REST API example for a 90/10 split:

```bash
curl -X PUT \
  "${DATABRICKS_HOST}/api/2.0/serving-endpoints/my-llm-endpoint/config" \
  -H "Authorization: Bearer ${DATABRICKS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "traffic_config": {
      "routes": [
        {
          "served_model_name": "current-model",
          "traffic_percentage": 90
        },
        {
          "served_model_name": "new-model",
          "traffic_percentage": 10
        }
      ]
    },
    "served_entities": [
      {
        "name": "current-model",
        "entity_name": "catalog.schema.model-v1",
        "entity_version": "3",
        "workload_size": "Small",
        "scale_to_zero_enabled": true
      },
      {
        "name": "new-model",
        "entity_name": "catalog.schema.model-v2",
        "entity_version": "1",
        "workload_size": "Small",
        "scale_to_zero_enabled": true
      }
    ]
  }'
```

Traffic percentages must sum to 100.

## Common Patterns

### Gradual Model Rollout

Route 90% of traffic to the current model and 10% to a new model. Enable fallback so requests to the new model automatically retry on the current model if it errors.

1. Configure the endpoint with two served entities and a 90/10 traffic split (see Traffic Splitting above).
2. Enable fallback:

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import FallbackConfig

w = WorkspaceClient()

w.serving_endpoints.put_ai_gateway(
    name="my-llm-endpoint",
    fallback_config=FallbackConfig(enabled=True),
)
```

3. Monitor error rates in inference tables and system tables. Shift traffic gradually (90/10 -> 70/30 -> 50/50 -> 0/100) as confidence grows.

### Cost Optimization

Serve an expensive primary model and a cheaper fallback model on the same endpoint. Enable fallback so that when the primary hits rate limits (429) or errors (5xx), requests are routed to the cheaper model instead of failing.

1. Configure two served entities: one for the high-quality model, one for the cost-effective model.
2. Set traffic to 100/0 (all traffic to the primary by default).
3. Enable fallback -- the cheaper model serves as a safety net.

### Team-Based Quotas

Give different teams different rate limits while enforcing a global cap.

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    AiGatewayRateLimit,
    AiGatewayRateLimitKey,
    AiGatewayRateLimitRenewalPeriod,
)

w = WorkspaceClient()

w.serving_endpoints.put_ai_gateway(
    name="my-llm-endpoint",
    rate_limits=[
        AiGatewayRateLimit(
            calls=1000,
            key=AiGatewayRateLimitKey.USER_GROUP,
            principal="engineering",
            renewal_period=AiGatewayRateLimitRenewalPeriod.MINUTE,
        ),
        AiGatewayRateLimit(
            calls=500,
            key=AiGatewayRateLimitKey.USER_GROUP,
            principal="analytics",
            renewal_period=AiGatewayRateLimitRenewalPeriod.MINUTE,
        ),
        AiGatewayRateLimit(
            calls=3000,
            key=AiGatewayRateLimitKey.ENDPOINT,
            renewal_period=AiGatewayRateLimitRenewalPeriod.MINUTE,
        ),
    ],
)
```

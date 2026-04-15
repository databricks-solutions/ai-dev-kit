---
name: databricks-ai-gateway
description: "Configure Databricks AI Gateway for serving endpoints and enterprise LLM governance. Use when (1) adding guardrails (safety, PII, custom) to endpoints, (2) setting rate limits or fallbacks, (3) enabling inference tables for payload logging, (4) tracking usage and costs via system tables, (5) governing coding agents (Cursor, Codex CLI, Gemini CLI, Claude Code), (6) managing MCP server access control. Covers both V1 per-endpoint gateway config and V2 enterprise control plane."
---

# Databricks AI Gateway

Configure guardrails, rate limits, observability, and enterprise governance for LLM endpoints and coding agents.

## Which Version Do You Need?

| You want to... | Version | Reference |
|----------------|---------|-----------|
| Add guardrails, rate limits, or fallbacks to a **serving endpoint** | V1 (GA) | [1-guardrails.md](1-guardrails.md), [2-rate-limits-and-fallbacks.md](2-rate-limits-and-fallbacks.md) |
| Enable payload logging on an endpoint | V1 (GA) | [3-inference-tables.md](3-inference-tables.md) |
| Monitor usage, costs, and audit trails | V1 + V2 | [4-observability.md](4-observability.md) |
| Govern **coding agents** (Cursor, Codex CLI, Gemini CLI, Claude Code) | V2 (Beta) | [5-coding-agents.md](5-coding-agents.md) |
| Govern **MCP servers**, agentic workflows, unified control plane | V2 (Beta) | [6-agentic-governance.md](6-agentic-governance.md) |

## Quick Decision: What Are You Configuring?

| Task | Go To |
|------|-------|
| Block or mask PII in LLM requests/responses | [1-guardrails.md](1-guardrails.md) |
| Add safety filters or topic restrictions | [1-guardrails.md](1-guardrails.md) |
| Custom guardrails via LLM judge | [1-guardrails.md](1-guardrails.md) |
| Per-user or per-team rate limits (QPM/TPM) | [2-rate-limits-and-fallbacks.md](2-rate-limits-and-fallbacks.md) |
| Auto-failover across served entities | [2-rate-limits-and-fallbacks.md](2-rate-limits-and-fallbacks.md) |
| Traffic splitting / A-B testing | [2-rate-limits-and-fallbacks.md](2-rate-limits-and-fallbacks.md) |
| Log request/response payloads to Delta tables | [3-inference-tables.md](3-inference-tables.md) |
| Query usage and cost system tables | [4-observability.md](4-observability.md) |
| Set up Cursor / Codex CLI / Gemini CLI / Claude Code through gateway | [5-coding-agents.md](5-coding-agents.md) |
| Govern MCP servers, trace agentic workflows | [6-agentic-governance.md](6-agentic-governance.md) |

## Prerequisites

- Unity Catalog enabled workspace
- Model Serving endpoint already deployed (for V1) — see [databricks-model-serving](../databricks-model-serving/SKILL.md)
- `databricks-sdk >= 0.40.0` (for `put_ai_gateway` method)
- Account admin or workspace admin permissions (for V2 Beta)

## SDK Class Reference

All classes are in `databricks.sdk.service.serving`:

| Class | Purpose |
|-------|---------|
| `AiGatewayGuardrails` | Container for input/output guardrail config |
| `AiGatewayGuardrailParameters` | Guardrail filters: `invalid_keywords`, `pii`, `safety`, `valid_topics` |
| `AiGatewayGuardrailPiiBehavior` | PII handling config (wraps the behavior enum) |
| `AiGatewayGuardrailPiiBehaviorBehavior` | Enum: `BLOCK`, `MASK`, `NONE` |
| `AiGatewayRateLimit` | Rate limit rule: `calls`, `tokens`, `key`, `principal`, `renewal_period` |
| `AiGatewayRateLimitKey` | Enum: `USER`, `USER_GROUP`, `SERVICE_PRINCIPAL`, `ENDPOINT` |
| `AiGatewayRateLimitRenewalPeriod` | Enum: `MINUTE` (only supported value) |
| `AiGatewayInferenceTableConfig` | Payload logging: `catalog_name`, `schema_name`, `table_name_prefix`, `enabled` |
| `AiGatewayUsageTrackingConfig` | System table usage tracking: `enabled` |
| `FallbackConfig` | Auto-failover across served entities: `enabled` |

## Quick Start: Enable PII Guardrails on an Endpoint

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    AiGatewayGuardrails,
    AiGatewayGuardrailParameters,
    AiGatewayGuardrailPiiBehavior,
    AiGatewayGuardrailPiiBehaviorBehavior,
    AiGatewayUsageTrackingConfig,
)

w = WorkspaceClient()

w.serving_endpoints.put_ai_gateway(
    name="my-llm-endpoint",
    guardrails=AiGatewayGuardrails(
        input=AiGatewayGuardrailParameters(
            pii=AiGatewayGuardrailPiiBehavior(
                behavior=AiGatewayGuardrailPiiBehaviorBehavior.BLOCK
            )
        ),
        output=AiGatewayGuardrailParameters(
            pii=AiGatewayGuardrailPiiBehavior(
                behavior=AiGatewayGuardrailPiiBehaviorBehavior.MASK
            )
        ),
    ),
    usage_tracking_config=AiGatewayUsageTrackingConfig(enabled=True),
)
```

## Quick Start: Enable Rate Limits

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
            calls=100,
            key=AiGatewayRateLimitKey.USER,
            renewal_period=AiGatewayRateLimitRenewalPeriod.MINUTE,
        ),
        AiGatewayRateLimit(
            calls=2000,
            key=AiGatewayRateLimitKey.ENDPOINT,
            renewal_period=AiGatewayRateLimitRenewalPeriod.MINUTE,
        ),
    ],
)
```

## REST API Quick Reference

**Endpoint:** `PUT /api/2.0/serving-endpoints/{name}/ai-gateway`

```bash
curl -X PUT \
  "${DATABRICKS_HOST}/api/2.0/serving-endpoints/my-llm-endpoint/ai-gateway" \
  -H "Authorization: Bearer ${DATABRICKS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "guardrails": {
      "input": {
        "pii": {"behavior": "BLOCK"},
        "safety": true
      },
      "output": {
        "pii": {"behavior": "MASK"}
      }
    },
    "rate_limits": [
      {"calls": 100, "key": "user", "renewal_period": "minute"},
      {"calls": 2000, "key": "endpoint", "renewal_period": "minute"}
    ],
    "usage_tracking_config": {"enabled": true},
    "inference_table_config": {
      "catalog_name": "analytics",
      "schema_name": "serving_logs",
      "table_name_prefix": "my_endpoint",
      "enabled": true
    }
  }'
```

## Reference Files

| Topic | File | When to Read |
|-------|------|--------------|
| Guardrails | [1-guardrails.md](1-guardrails.md) | PII, safety, keywords, topics, LLM judge, custom guardrails |
| Rate Limits & Fallbacks | [2-rate-limits-and-fallbacks.md](2-rate-limits-and-fallbacks.md) | QPM/TPM limits, auto-failover, traffic splitting |
| Inference Tables | [3-inference-tables.md](3-inference-tables.md) | Payload logging to UC Delta tables |
| Observability | [4-observability.md](4-observability.md) | System tables, cost attribution, audit trails |
| Coding Agents | [5-coding-agents.md](5-coding-agents.md) | Cursor, Codex CLI, Gemini CLI, Claude Code setup |
| Agentic Governance | [6-agentic-governance.md](6-agentic-governance.md) | MCP governance, traceability, unified control plane |

## MCP Tools

> The `manage_serving_endpoint` MCP tool currently supports `get`, `list`, and `query` only. It does **not** support AI Gateway configuration. Use the Python SDK or REST API for gateway config.

**Workflow using MCP tools:**

| Step | Tool | Purpose |
|------|------|---------|
| 1. Check endpoint exists | `manage_serving_endpoint(action="get", name="...")` | Verify endpoint is READY |
| 2. Configure AI Gateway | `execute_code` with SDK script | Apply guardrails, rate limits, etc. |
| 3. Verify endpoint health | `manage_serving_endpoint(action="get", name="...")` | Confirm endpoint still healthy |
| 4. Test the endpoint | `manage_serving_endpoint(action="query", name="...", messages=[...])` | Verify guardrails work |

## Common Issues

| Issue | Solution |
|-------|----------|
| **Output guardrails not triggering (streaming)** | Output guardrails do not work for streaming responses. Use non-streaming mode. |
| **Output guardrails not working (embeddings)** | Output guardrails only support chat/completions, not embedding endpoints. |
| **TPM rate limit rejected on custom model** | TPM limits only work for Foundation Model API endpoints. Use QPM for custom models. |
| **Fallback not triggering** | Fallback round-robins across served entities on the same endpoint. Requires multiple served entities configured. |
| **Payloads missing from inference table** | Payloads > 1 MiB are excluded from logging. Truncate large inputs. |
| **Max rate limits exceeded** | Maximum 20 rate limit rules per endpoint, 5 group-specific. Consolidate groups. |
| **`put_ai_gateway` not found** | Upgrade SDK: `pip install --upgrade databricks-sdk>=0.40.0` |
| **Config update not taking effect** | Configuration updates take 20-60 seconds to propagate. Wait and retry. |

### Critical: Use SDK Objects, Not Raw Dicts

**WRONG** — passing raw dicts will fail:
```python
w.serving_endpoints.put_ai_gateway(
    name="my-endpoint",
    guardrails={"input": {"pii": {"behavior": "BLOCK"}}}  # TypeError
)
```

**CORRECT** — use SDK dataclasses:
```python
from databricks.sdk.service.serving import (
    AiGatewayGuardrails, AiGatewayGuardrailParameters,
    AiGatewayGuardrailPiiBehavior, AiGatewayGuardrailPiiBehaviorBehavior,
)

w.serving_endpoints.put_ai_gateway(
    name="my-endpoint",
    guardrails=AiGatewayGuardrails(
        input=AiGatewayGuardrailParameters(
            pii=AiGatewayGuardrailPiiBehavior(
                behavior=AiGatewayGuardrailPiiBehaviorBehavior.BLOCK
            )
        )
    ),
)
```

## Related Skills

- **[databricks-model-serving](../databricks-model-serving/SKILL.md)** — Deploy the serving endpoints this skill configures
- **[databricks-agent-bricks](../databricks-agent-bricks/SKILL.md)** — Agents that benefit from gateway governance
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** — System tables for observability queries
- **[databricks-python-sdk](../databricks-python-sdk/SKILL.md)** — SDK patterns and authentication

## Resources

- [AI Gateway Documentation (AWS)](https://docs.databricks.com/aws/en/ai-gateway/)
- [AI Gateway Documentation (Azure)](https://learn.microsoft.com/en-us/azure/databricks/ai-gateway/)
- [AI Gateway Documentation (GCP)](https://docs.databricks.com/gcp/en/ai-gateway/)
- [Configure AI Gateway on Serving Endpoints](https://docs.databricks.com/aws/en/ai-gateway/configure-ai-gateway-endpoints)
- [AI Gateway Beta Overview](https://docs.databricks.com/aws/en/ai-gateway/overview-beta)
- [Coding Agent Integration](https://docs.databricks.com/aws/en/ai-gateway/coding-agent-integration-beta)

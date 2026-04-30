# Coding Agent Integration

Route coding agent traffic through AI Gateway V2 (Beta) for centralized authentication, rate limiting, guardrails, and audit logging.

## Overview

AI Gateway V2 proxies requests between developer IDEs and LLM providers. All traffic flows through the gateway instead of connecting directly to providers. Platform teams get a single dashboard for auth, rate limits, guardrails, and usage tracking across every coding tool.

## Architecture

```
Developer IDE → AI Gateway V2 (Beta) → LLM Provider
                  ├── Authentication (PAT / OAuth)
                  ├── Rate Limits (per-user QPM)
                  ├── Guardrails (PII, safety, keywords)
                  └── Usage Logging (inference tables + system tables)
```

## Routing Paths Reference

| Agent | Gateway Path | Config Location |
|-------|-------------|-----------------|
| Cursor | `/cursor/v1` | Cursor Settings > Models |
| Codex CLI | `/codex/v1` | `~/.codex/config.toml` |
| Gemini CLI | `/gemini` | `~/.gemini/.env` |
| Claude Code | TBD (blog only, not in official docs yet) | Environment variables |

## Cursor Setup

1. Get your AI Gateway URL: `https://<workspace-url>/ai-gateway` or your account-level URL.
2. Generate a Databricks PAT if you don't have one.
3. In Cursor: **Settings > Models > Override OpenAI Base URL**:
   ```
   https://<ai-gateway-url>/cursor/v1
   ```
4. Set **API Key** to your Databricks PAT (`dapi...`).
5. Add custom models as needed. The gateway routes to the correct provider based on model name.

## Codex CLI Setup

1. Authenticate with Databricks CLI (`databricks auth login`).
2. Create or edit `~/.codex/config.toml`:

```toml
provider = "databricks"
base_url = "https://<ai-gateway-url>/codex/v1"
```

Auth is inherited from the Databricks CLI session -- no separate API key needed.

## Gemini CLI Setup

Create or edit `~/.gemini/.env`:

```bash
GEMINI_MODEL="gemini-2.5-pro"
GEMINI_API_BASE_URL="https://<ai-gateway-url>/gemini"
GEMINI_API_KEY="dapi..."
```

`GEMINI_API_KEY` is your Databricks PAT.

## Claude Code Setup

> **Note:** Claude Code is mentioned in the [Databricks blog](https://www.databricks.com/blog) but not yet in official docs. The pattern below follows the expected convention.

```bash
export ANTHROPIC_BASE_URL="https://<ai-gateway-url>/anthropic"
export ANTHROPIC_AUTH_TOKEN="dapi..."
```

Check the [official docs](https://docs.databricks.com/aws/en/ai-gateway/coding-agent-integration-beta) for updates.

## OpenAI-Compatible API

The gateway exposes an OpenAI-compatible endpoint. Any OpenAI-speaking tool connects without code changes, and you can switch backing models at the gateway layer without reconfiguring clients.

```python
from openai import OpenAI
client = OpenAI(base_url="https://<ai-gateway-url>/v1", api_key="dapi...")
response = client.chat.completions.create(
    model="gpt-4o",  # Gateway routes to the correct provider
    messages=[{"role": "user", "content": "Explain Unity Catalog."}],
)
print(response.choices[0].message.content)
```

## Rate Limiting Coding Agents

Coding agents generate high request volume. Set per-user QPM limits to prevent any developer from saturating capacity.

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    AiGatewayRateLimit, AiGatewayRateLimitKey, AiGatewayRateLimitRenewalPeriod,
)
w = WorkspaceClient()
w.serving_endpoints.put_ai_gateway(
    name="coding-agent-gateway",
    rate_limits=[
        AiGatewayRateLimit(calls=60, key=AiGatewayRateLimitKey.USER,
                           renewal_period=AiGatewayRateLimitRenewalPeriod.MINUTE),
        AiGatewayRateLimit(calls=5000, key=AiGatewayRateLimitKey.ENDPOINT,
                           renewal_period=AiGatewayRateLimitRenewalPeriod.MINUTE),
    ],
)
```

See [2-rate-limits-and-fallbacks.md](2-rate-limits-and-fallbacks.md) for group-level limits, TPM, and fallback config.

## Monitoring Coding Agent Usage

The unified dashboard shows request volume, token consumption, error rates, and cost across all coding agents. Enable usage tracking and inference tables for full payload audit. See [4-observability.md](4-observability.md) for system table queries.

## SA Scenario

**Enterprise wants all developers using Cursor through gateway with PII guardrails and per-dev rate limits.**

1. **Set up AI Gateway V2** -- create a gateway endpoint for coding agent traffic.
2. **Configure Cursor per developer** -- distribute the base URL override (`https://<ai-gateway-url>/cursor/v1`) and each dev's Databricks PAT. Use workspace identity federation so requests map to known users.
3. **Add PII guardrails** -- block PII on input, mask on output. See [1-guardrails.md](1-guardrails.md).
4. **Add per-user rate limits** -- e.g., 60 QPM per user, 5000 QPM endpoint cap. See [2-rate-limits-and-fallbacks.md](2-rate-limits-and-fallbacks.md).
5. **Enable observability** -- turn on inference tables and usage tracking for full audit trail and cost visibility.

---
name: databricks-app-foundation-model
description: "Use when building Databricks Apps that call foundation model endpoints from Python or Streamlit and need validated Databricks LLM configuration, app-injected auth, OpenAI-compatible client wiring, or production patterns like structured outputs and bounded parallel calls."
---

# Databricks App Foundation Model

Call Databricks Foundation Model APIs from inside a Databricks App without mixing App runtime rules, serving-endpoint details, and production LLM patterns into one giant reference. This skill is intentionally scoped to the overlap between Databricks Apps auth and foundation-model usage.

## When To Use

Use this skill when you need one or more of the following in a Databricks App:

- App-injected service-principal auth with PAT fallback for local development
- Validated LLM configuration for serving base URL, workspace host, and endpoint name
- OpenAI-compatible client wiring to Databricks serving endpoints
- Viewer identity from forwarded Databricks Apps headers
- Streamlit or Python patterns for structured outputs, retries, caching, or bounded parallel calls

Use adjacent skills instead when the task is broader:

- `databricks-app-python` for general App runtime, resources, deployment, and framework guidance
- `databricks-model-serving` for supported endpoint names, serving capabilities, and model selection
- `databricks-docs` when you need authoritative product documentation beyond the patterns captured here

## Critical Rules

- **MUST** use Databricks Apps-injected credentials for deployed apps when App credentials are present
- **MUST** support dual-mode auth: prefer OAuth M2M when App credentials are present, otherwise use `DATABRICKS_TOKEN` for local development
- **MUST** pass the resolved bearer token as `api_key` and `DATABRICKS_SERVING_BASE_URL` as `base_url`
- **MUST NOT** use `dbutils.notebook.entry_point` in Databricks Apps
- **MUST NOT** hardcode PATs, client secrets, or bearer tokens in source code

## Quick Decision Guide

| Need | Read First |
|------|------------|
| App auth, config validation, OAuth token minting, forwarded headers | [1-auth-and-identity.md](1-auth-and-identity.md) |
| OpenAI client wiring, validated client creation, chat call shape | [2-client-wiring.md](2-client-wiring.md) |
| Parallel calls, structured outputs, retries, caching | [3-production-patterns.md](3-production-patterns.md) |

## Reference Files

| File | Purpose |
|------|---------|
| [1-auth-and-identity.md](1-auth-and-identity.md) | Canonical config and auth flow for validated serving URLs, OAuth M2M, PAT fallback, and forwarded-header identity |
| [2-client-wiring.md](2-client-wiring.md) | OpenAI-compatible client setup with endpoint validation and client construction helpers |
| [3-production-patterns.md](3-production-patterns.md) | Bounded parallelism, structured outputs, retry patterns, caching, and timeout guidance |

## Minimal Usage

If you copy `examples/llm_config.py` into your app as `llm_config.py`, this is the minimal usage shape:

```python
from llm_config import build_openai_client, get_model_name

client = build_openai_client()
response = client.chat.completions.create(
    model=get_model_name(),
    messages=[{"role": "user", "content": "Summarize Databricks Apps auth flow."}],
    max_tokens=300,
    temperature=0.2,
)
```

The canonical helper implementation lives in `examples/llm_config.py`. It validates the serving URL and endpoint name, chooses an auth mode, caches OAuth tokens, and builds the OpenAI-compatible client.

## Common Mistakes

| Mistake | Why it hurts | Fix |
|---------|--------------|-----|
| Treating this as a generic model-serving skill | App auth and forwarded-header behavior are App-specific | Use this skill only for the App-side integration layer |
| Hardcoding a model name copied from an old example | Endpoint availability changes over time | Check `databricks-model-serving` for the current supported endpoint table |
| Repeating auth helpers in every script | Auth drift is easy to introduce | Reuse `examples/llm_config.py` or copy one canonical helper set |
| Assuming forwarded headers exist locally | They are typically only present in deployed Apps | Handle missing identity gracefully in local runs |

## Examples

See [`examples/`](examples/) for runnable examples:

- `1-auth-and-token-minting.py` - Canonical auth helpers plus viewer identity access
- `2-minimal-chat-app.py` - Complete Streamlit chat app using shared auth/client helpers
- `3-parallel-llm-calls.py` - Parallel foundation-model calls with shared client wiring
- `4-structured-outputs.py` - Structured-output parsing and retry logic with shared client wiring
- `llm_config.py` - Shared auth and OpenAI client helpers used across the examples

## Related Skills

- **[databricks-app-python](../databricks-app-python/SKILL.md)** - broader Databricks App runtime and deployment patterns
- **[databricks-model-serving](../databricks-model-serving/SKILL.md)** - endpoint naming and serving-specific guidance
- **[databricks-docs](../databricks-docs/SKILL.md)** - authoritative documentation lookup

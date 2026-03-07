## Client Wiring

This file owns the App-side client wiring for Databricks Foundation Model APIs.

## Core Pattern

Use the validated Databricks bearer token as `api_key` and the serving-endpoint base URL as `base_url`.

```python
import os
from openai import OpenAI

client = OpenAI(
    api_key=resolved_databricks_token,
    base_url=os.environ["DATABRICKS_SERVING_BASE_URL"],
)
model = os.environ["DATABRICKS_MODEL"]
```

If you copy `examples/llm_config.py` into your app as `llm_config.py`, the reusable helper goes a step further:

```python
from llm_config import build_openai_client

client = build_openai_client()
```

That helper validates the serving URL and model name first, caches endpoint validation results for a short TTL, then constructs the OpenAI-compatible client.

Because the helper performs HTTP endpoint validation and may mint OAuth tokens, include `requests` in your app dependencies alongside `openai`.

## Chat Completion Shape

The common request shape is the standard OpenAI-compatible one:

```python
response = client.chat.completions.create(
    model=model,
    messages=[{"role": "user", "content": "Hello"}],
    max_tokens=300,
    temperature=0.2,
)
```

## Model Selection

This skill is intentionally not the source of truth for endpoint names. Use:

- `databricks-model-serving` for the current supported endpoint table
- `databricks-docs` when you need the latest product documentation

This skill only covers the App integration layer around those endpoints.

## Quick Reference

| Concern | Guidance |
|---------|----------|
| Token source | Prefer OAuth M2M when App credentials are present; use PAT for local development |
| `base_url` | Always set to the validated `DATABRICKS_SERVING_BASE_URL` |
| Request schema | Use OpenAI-compatible chat/completions calls |
| Endpoint validation | Validate once and cache the result briefly instead of blindly assuming the endpoint exists |
| Local development | PAT mode is fine when App credentials are not present |
| Deployed Apps | Prefer App-injected service-principal credentials |

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Calling `OpenAI()` without `base_url` | Set `base_url=DATABRICKS_SERVING_BASE_URL` |
| Treating the bearer token like an SDK `Config()` object | Pass it as `api_key` to the OpenAI client |
| Assuming the configured endpoint exists | Validate `DATABRICKS_MODEL` against the workspace before building the client |
| Hardcoding a stale model name in multiple places | Set `DATABRICKS_MODEL` explicitly and defer authoritative endpoint naming to `databricks-model-serving` |

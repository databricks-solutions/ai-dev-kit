## Client Wiring

This file owns the App-side client wiring for Databricks Foundation Model APIs.

## Core Pattern

Use the resolved Databricks bearer token as `api_key` and the serving-endpoint base URL as `base_url`.

```python
import os
from openai import OpenAI

client = OpenAI(
    api_key=resolved_databricks_token,
    base_url=os.environ["DATABRICKS_SERVING_BASE_URL"],
)
model = os.environ["DATABRICKS_MODEL"]
```

The shared helper in [`examples/_common.py`](examples/_common.py) constructs the equivalent of:

```python
from openai import OpenAI

client = OpenAI(
    api_key=resolved_databricks_token,
    base_url=DATABRICKS_SERVING_BASE_URL,
)
```

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
| Token source | Use PAT if explicitly provided, otherwise mint OAuth from App credentials |
| `base_url` | Always set to `DATABRICKS_SERVING_BASE_URL` |
| Request schema | Use OpenAI-compatible chat/completions calls |
| Local development | PAT override is acceptable and often easiest |
| Deployed Apps | Prefer App-injected service-principal credentials |

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Calling `OpenAI()` without `base_url` | Set `base_url=DATABRICKS_SERVING_BASE_URL` |
| Treating the bearer token like an SDK `Config()` object | Pass it as `api_key` to the OpenAI client |
| Hardcoding a stale model name in multiple places | Centralize default selection and defer authoritative names to `databricks-model-serving` |

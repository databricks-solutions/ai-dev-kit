## Auth And Identity

This file owns the App-specific authentication and configuration rules for this skill. If the task is "how do I validate Databricks LLM config and authenticate from a Databricks App to a foundation-model endpoint?", start here.

## Environment Variables

When a Databricks App has a service principal configured, Databricks can inject:

| Variable | Required | Purpose |
|---------|----------|---------|
| `DATABRICKS_SERVING_BASE_URL` | Yes | Base URL for serving endpoints, for example `https://<host>/serving-endpoints` |
| `DATABRICKS_TOKEN` | Optional | PAT for local development when App credentials are not present |
| `DATABRICKS_CLIENT_ID` | Required for OAuth | App service-principal client ID |
| `DATABRICKS_CLIENT_SECRET` | Required for OAuth | App service-principal client secret |
| `DATABRICKS_HOST` | Optional | Explicit workspace host; if set, it must match the host in `DATABRICKS_SERVING_BASE_URL` |

## Canonical Auth Flow

Always resolve auth in this order:

1. Validate `DATABRICKS_SERVING_BASE_URL` and `DATABRICKS_MODEL`.
2. If App service-principal credentials are present, prefer OAuth M2M.
3. Otherwise use `DATABRICKS_TOKEN` for PAT-based local development.
4. Cache minted OAuth tokens so repeated or concurrent calls do not re-mint unnecessarily.

The shared example helper in [`examples/llm_config.py`](examples/llm_config.py) follows this pattern.

## Canonical Helper

If you copy `examples/llm_config.py` into your app as `llm_config.py`, the auth/config entry points are:

```python
from llm_config import get_databricks_bearer_token, get_databricks_llm_config

config = get_databricks_llm_config()
token = get_databricks_bearer_token()
```

If you want to verify that the configured endpoint exists before issuing requests:

```python
from llm_config import validate_databricks_llm_config

config = validate_databricks_llm_config()
```

The canonical implementation of `get_databricks_llm_config()`, `get_databricks_bearer_token()`, and `validate_databricks_llm_config()` lives in [`examples/llm_config.py`](examples/llm_config.py).

## Forwarded Viewer Identity

Databricks Apps may forward user identity headers such as:

- `X-Forwarded-Email`
- `X-Forwarded-Access-Token`

Treat them as optional. They are commonly available in deployed Apps and commonly absent in local runs.

```python
from typing import Dict, Optional, Tuple

import streamlit as st


def get_viewer_identity() -> Tuple[Optional[str], Optional[str]]:
    try:
        headers: Dict[str, str] = dict(getattr(st, "context").headers)
    except Exception:
        headers = {}

    email = headers.get("X-Forwarded-Email") or headers.get("x-forwarded-email")
    token = headers.get("X-Forwarded-Access-Token") or headers.get(
        "x-forwarded-access-token"
    )
    return email, token
```

## When To Use `databricks-app-python` Instead

Use `databricks-app-python` if the question is really about:

- App resources in `app.yaml`
- generic App auth with SDK `Config()`
- framework/runtime setup
- deployment and logging

Use this file when the question is specifically about foundation-model calls from within the App runtime.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Accepting an invalid serving base URL | Validate that `DATABRICKS_SERVING_BASE_URL` ends with `/serving-endpoints` |
| Treating `DATABRICKS_HOST` and the serving URL host as unrelated | Reject mismatches early so auth and validation hit the same workspace |
| Minting a new OAuth token on every call | Reuse the shared cached token helper |
| Assuming `dbutils` exists in Apps | Use env vars and HTTP token minting instead |
| Failing hard when forwarded headers are missing | Treat viewer identity as optional in local development |

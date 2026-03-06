## Auth And Identity

This file owns the App-specific authentication rules for this skill. If the task is "how do I authenticate from a Databricks App to a foundation-model endpoint?", start here.

## Environment Variables

When a Databricks App has a service principal configured, Databricks can inject:

| Variable | Required | Purpose |
|---------|----------|---------|
| `DATABRICKS_SERVING_BASE_URL` | Yes | Base URL for serving endpoints, for example `https://<host>/serving-endpoints` |
| `DATABRICKS_TOKEN` | Optional | PAT override for local development or explicit override path |
| `DATABRICKS_CLIENT_ID` | Yes if no PAT | App service-principal client ID |
| `DATABRICKS_CLIENT_SECRET` | Yes if no PAT | App service-principal client secret |
| `DATABRICKS_HOST` | Optional | Explicit workspace host used to mint OAuth tokens |

## Canonical Auth Flow

Always resolve auth in this order:

1. If `DATABRICKS_TOKEN` exists, use it as the bearer token.
2. Otherwise mint an OAuth token from `DATABRICKS_CLIENT_ID` and `DATABRICKS_CLIENT_SECRET`.
3. Cache the minted token when a state container is available, such as `st.session_state`.

The shared example helper in [`examples/_common.py`](examples/_common.py) follows this pattern.

## Canonical Helper

```python
token = resolve_bearer_token(cache=st.session_state)
```

If you are not inside Streamlit, you can omit the cache or pass any mutable mapping:

```python
token = resolve_bearer_token()
```

The canonical implementation of `resolve_bearer_token()` lives in [`examples/_common.py`](examples/_common.py).

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
| Minting a new OAuth token on every rerun | Cache the token in `st.session_state` with an expiry check |
| Assuming `dbutils` exists in Apps | Use env vars and HTTP token minting instead |
| Failing hard when forwarded headers are missing | Treat viewer identity as optional in local development |
| Copying auth code into every script | Reuse `examples/_common.py` as the single source of truth |

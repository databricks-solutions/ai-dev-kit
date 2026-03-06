---
name: databricks-app-foundation-model
description: "Call Databricks Foundation Model APIs from Databricks Apps using app-injected service principal credentials. Use when building Streamlit apps that must support PAT override plus OAuth M2M fallback, wire OpenAI SDK to Databricks serving endpoints, read viewer identity from forwarded headers, and avoid dbutils or hardcoded tokens."
---

# Databricks App Foundation Model

Call Databricks Foundation Model APIs from inside a Databricks App using the app's injected credentials. Prefer service-principal OAuth token minting in Apps, with optional PAT override for local/dev scenarios.

## Critical Rules (always follow)

- **MUST** use Databricks Apps-injected credentials (`DATABRICKS_CLIENT_ID` / `DATABRICKS_CLIENT_SECRET`) for OAuth M2M in deployed apps
- **MUST** support dual-mode auth: `DATABRICKS_TOKEN` first, then OAuth token minting fallback
- **MUST** cache minted OAuth token in `st.session_state` with expiry check
- **MUST** pass the resolved bearer token as `api_key` to `OpenAI(...)` and set `base_url=DATABRICKS_SERVING_BASE_URL`
- **MUST** read viewer identity from `st.context.headers` (`X-Forwarded-Email`, `X-Forwarded-Access-Token`) when user context is needed
- **MUST NOT** use `dbutils.notebook.entry_point` in Apps (unavailable)
- **MUST NOT** hardcode PATs or commit `DATABRICKS_TOKEN` to source code

## Environment Variables (Databricks Apps)

When a service principal is configured for the app, Databricks Apps injects these environment variables:

| Variable | Required | Purpose |
|---------|----------|---------|
| `DATABRICKS_HOST` | Recommended | Workspace host used to mint OAuth token at `/oidc/v1/token` |
| `DATABRICKS_SERVING_BASE_URL` | Yes | Databricks serving endpoint base URL, e.g. `https://<host>/serving-endpoints` |
| `DATABRICKS_TOKEN` | Optional | PAT override for local/dev or explicit override path |
| `DATABRICKS_CLIENT_ID` | Yes (if no PAT) | App service principal client ID |
| `DATABRICKS_CLIENT_SECRET` | Yes (if no PAT) | App service principal client secret |

## Pattern 1: Dual-Mode Auth (PAT first, OAuth M2M fallback)

Use this implementation pattern directly in Streamlit apps:

```python
import os
import time
from typing import Dict, Optional, Tuple

import requests
import streamlit as st

DATABRICKS_SERVING_BASE_URL = os.environ.get(
    "DATABRICKS_SERVING_BASE_URL",
    "https://<your-workspace-host>/serving-endpoints",
)
DATABRICKS_TOKEN = os.environ.get("DATABRICKS_TOKEN")
DATABRICKS_CLIENT_ID = os.environ.get("DATABRICKS_CLIENT_ID")
DATABRICKS_CLIENT_SECRET = os.environ.get("DATABRICKS_CLIENT_SECRET")


def _workspace_host_from_serving_base_url(serving_base_url: str) -> str:
    # serving base url looks like https://<host>/serving-endpoints
    return serving_base_url.split("/serving-endpoints")[0].rstrip("/")


def get_databricks_bearer_token() -> str:
    """Return a token usable as OpenAI(api_key=...).

    Priority:
    1) DATABRICKS_TOKEN (PAT) if provided
    2) Mint OAuth token from app service principal creds (DATABRICKS_CLIENT_ID/SECRET)

    Tokens are cached in st.session_state to avoid re-minting.
    """
    if DATABRICKS_TOKEN:
        return DATABRICKS_TOKEN

    cached = st.session_state.get("dbx_oauth")
    if (
        cached
        and cached.get("access_token")
        and cached.get("expires_at", 0) > int(time.time()) + 30
    ):
        return cached["access_token"]

    if not (DATABRICKS_CLIENT_ID and DATABRICKS_CLIENT_SECRET):
        raise RuntimeError(
            "No Databricks auth configured. Provide Apps SP creds "
            "(DATABRICKS_CLIENT_ID/SECRET) or set DATABRICKS_TOKEN (PAT)."
        )

    host = os.environ.get("DATABRICKS_HOST") or _workspace_host_from_serving_base_url(
        DATABRICKS_SERVING_BASE_URL
    )
    host = host.strip().rstrip("/")
    if not host.startswith("http://") and not host.startswith("https://"):
        host = "https://" + host

    token_url = f"{host}/oidc/v1/token"
    resp = requests.post(
        token_url,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "client_credentials", "scope": "all-apis"},
        auth=(DATABRICKS_CLIENT_ID, DATABRICKS_CLIENT_SECRET),
        timeout=30,
    )

    if resp.status_code >= 400:
        raise RuntimeError(
            f"Failed to mint OAuth token (HTTP {resp.status_code}). "
            f"Response: {resp.text[:500]}"
        )

    payload = resp.json()
    access_token = payload.get("access_token")
    expires_in = int(payload.get("expires_in", 300))
    if not access_token:
        raise RuntimeError(f"Token endpoint response missing access_token: {payload}")

    st.session_state["dbx_oauth"] = {
        "access_token": access_token,
        "expires_at": int(time.time()) + expires_in,
    }
    return access_token
```

## Pattern 2: OpenAI SDK Wiring to Databricks Serving

Use the resolved token as `api_key` and Databricks serving URL as `base_url`:

```python
from openai import OpenAI

token = get_databricks_bearer_token()
client = OpenAI(api_key=token, base_url=DATABRICKS_SERVING_BASE_URL)
```

## Pattern 3: Viewer Identity from Databricks Apps Forwarded Headers

In Databricks Apps, user identity can be forwarded in app request headers:

```python
from typing import Dict, Optional, Tuple
import streamlit as st


def _get_forwarded_headers() -> Dict[str, str]:
    """Best-effort access to Databricks Apps forwarded headers."""
    try:
        hdrs = getattr(st, "context").headers  # Streamlit 1.29+ pattern
        return {k: v for k, v in hdrs.items()}
    except Exception:
        return {}


def get_viewer_identity() -> Tuple[Optional[str], Optional[str]]:
    headers = _get_forwarded_headers()
    email = headers.get("X-Forwarded-Email") or headers.get("x-forwarded-email")
    token = headers.get("X-Forwarded-Access-Token") or headers.get(
        "x-forwarded-access-token"
    )
    return email, token
```

## Pattern 4: LLM Chat Helper (working call shape)

Use the same OpenAI-compatible chat completion shape used in Databricks Apps:

```python
import time
from typing import Any, Dict, List, Tuple
from openai import OpenAI


def llm_chat(
    client: OpenAI,
    *,
    model: str,
    messages: List[Dict[str, str]],
    max_tokens: int,
    temperature: float,
) -> Tuple[Any, int]:
    """Return (message_content, elapsed_ms)."""
    t0 = time.perf_counter()
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    return resp.choices[0].message.content, elapsed_ms
```

## What Not To Do

- Do not use `dbutils.notebook.entry_point` in Databricks Apps
- Do not hardcode PATs, client secrets, or bearer tokens in source code
- Do not store `DATABRICKS_TOKEN` in git-tracked files
- Do not assume `dbutils` is available in app runtime
- Do not call Foundation Model endpoints without setting `base_url` to `DATABRICKS_SERVING_BASE_URL`

## End-to-End Minimal Usage

```python
from openai import OpenAI

token = get_databricks_bearer_token()
client = OpenAI(api_key=token, base_url=DATABRICKS_SERVING_BASE_URL)

email, user_access_token = get_viewer_identity()  # Optional viewer context

answer, latency_ms = llm_chat(
    client,
    model="databricks-gpt-5-mini",
    messages=[{"role": "user", "content": "Summarize Databricks Apps auth flow."}],
    max_tokens=300,
    temperature=0.2,
)
```

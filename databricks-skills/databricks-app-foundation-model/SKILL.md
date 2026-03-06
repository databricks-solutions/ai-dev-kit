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

## Pattern 5: Parallel LLM Calls for Improved Performance

When making multiple independent foundation model calls (e.g., content evaluation with multiple checks), use parallel execution for significant performance gains:

```python
import concurrent.futures
from typing import Dict, List, Tuple, Any, Callable

def run_jobs_parallel(
    jobs: Dict[str, Tuple[Callable, Tuple[Any, ...], Dict[str, Any]]],
    max_workers: int = 3,
) -> Tuple[Dict[str, Any], List[str]]:
    """Run multiple LLM calls in parallel and wait for all results.

    Args:
        jobs: Dict mapping job_name -> (function, args, kwargs)
        max_workers: Max parallel executions (configurable via LLM_MAX_CONCURRENCY env var)

    Returns:
        (results_dict, errors_list)
    """
    results: Dict[str, Any] = {}
    errors: List[str] = []

    def _call(fn, args, kwargs):
        return fn(*args, **kwargs)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_call, fn, args, kwargs): name
            for name, (fn, args, kwargs) in jobs.items()
        }
        concurrent.futures.wait(list(futures.keys()))

        for future, job_name in futures.items():
            try:
                results[job_name] = future.result()
            except Exception as e:
                errors.append(f"{job_name}: {type(e).__name__}: {str(e)[:200]}")
                results[job_name] = None

    return results, errors

# Usage: Run 3 checks in parallel instead of serial
jobs = {
    "check_structure": (llm_call, (client, prompt1), {}),
    "check_tldr": (llm_call, (client, prompt2), {}),
    "check_actionability": (llm_call, (client, prompt3), {}),
}
results, errors = run_jobs_parallel(jobs, max_workers=3)
```

**Performance impact**: 3 calls × 2s each = 6s serial → ~2s parallel (3× faster)

**Best practices**:
- Use `LLM_MAX_CONCURRENCY` env var for configurable parallelism (default: 3)
- Balance throughput vs rate limits (too high = rate limit errors)
- Handle errors gracefully per job (don't fail entire batch)
- Use for: content evaluation, batch processing, multi-aspect analysis
- Avoid for: dependent operations, debugging, strict rate limits

## Pattern 6: Structured Outputs and Robust JSON Parsing

For production apps requiring structured data from foundation models (evaluation, extraction, classification):

```python
import json
import re
from typing import Any, Dict

def _content_to_text(content: Any) -> str:
    """Normalize message content to string (handles str, bytes, list)."""
    if isinstance(content, str):
        return content
    if isinstance(content, (bytes, bytearray)):
        return content.decode("utf-8", errors="replace")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if "text" in item:
                    parts.append(item["text"])
        return "".join(parts)
    return str(content)

def _parse_json_object(response_text: str) -> Dict[str, Any]:
    """Robust JSON parsing - handles code fences, smart quotes, extra text."""
    text = (response_text or "").strip()
    if not text:
        raise ValueError("Empty response")

    # Strip markdown code fences
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"```$", "", text).strip()

    # Try direct parse
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # Extract first {...} block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]

    # Normalize smart quotes
    text = (text.replace("\u201c", '"').replace("\u201d", '"')
                .replace("\u2018", "'").replace("\u2019", "'"))

    return json.loads(text)

# Use with retry on parse failure
def llm_structured_call(client, system, user):
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.0,  # Deterministic for structured outputs
        max_tokens=2000,
    )
    content = _content_to_text(resp.choices[0].message.content)

    try:
        return _parse_json_object(content)
    except Exception:
        # Retry with stricter prompt
        retry_resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": "Return ONLY minified JSON. No extra text."},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
            max_tokens=2000,
        )
        retry_content = _content_to_text(retry_resp.choices[0].message.content)
        return _parse_json_object(retry_content)
```

**Best practices**:
- Use `temperature=0.0` for deterministic structured outputs
- Strip markdown code fences (```json ... ```)
- Normalize smart/curly quotes to straight quotes
- Retry with stricter prompt if initial parse fails
- Provide exact JSON schema in system prompt
- Use `@st.cache_data(ttl=60*60)` for expensive structured calls

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
    model="databricks-meta-llama-3-1-70b-instruct",
    messages=[{"role": "user", "content": "Summarize Databricks Apps auth flow."}],
    max_tokens=300,
    temperature=0.2,
)
```

## Examples

See [`examples/`](examples/) for working code:
- `1-auth-and-token-minting.py` - Authentication patterns and token management
- `2-minimal-chat-app.py` - Complete Streamlit chat app with deployment instructions
- `3-parallel-llm-calls.py` - Parallel foundation model calls for improved performance
- `4-structured-outputs.py` - Robust JSON parsing, retry logic, and caching patterns

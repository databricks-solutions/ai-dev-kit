"""
Canonical authentication example for Databricks Apps foundation-model calls.

This file shows the single auth flow used by the other examples:
1. Validate serving URL and model configuration
2. Prefer OAuth M2M when app-injected service-principal credentials are present
3. Use PAT mode for local development when OAuth credentials are absent
4. Optional viewer identity from forwarded headers

Set `DATABRICKS_MODEL` before running so the final sample request can pick an endpoint.
"""

from typing import Dict, Optional, Tuple

import streamlit as st

from llm_config import (
    create_foundation_model_client,
    get_model_name,
    get_serving_base_url,
    resolve_bearer_token,
)


def _get_forwarded_headers() -> Dict[str, str]:
    try:
        return dict(getattr(st, "context").headers)
    except Exception:
        return {}


def get_viewer_identity() -> Tuple[Optional[str], Optional[str]]:
    headers = _get_forwarded_headers()
    email = headers.get("X-Forwarded-Email") or headers.get("x-forwarded-email")
    token = headers.get("X-Forwarded-Access-Token") or headers.get(
        "x-forwarded-access-token"
    )
    return email, token


if __name__ == "__main__":
    # In a Streamlit app, prefer `cache=st.session_state`.
    token_cache: Dict[str, object] = {}

    token = resolve_bearer_token(cache=token_cache)
    print(f"✓ Resolved auth token: {token[:20]}...")

    email, _ = get_viewer_identity()
    if email:
        print(f"✓ Viewer email: {email}")
    else:
        print("ℹ Viewer identity not available (normal for local runs)")

    client = create_foundation_model_client(cache=token_cache)
    print(f"✓ Created OpenAI client pointing to: {get_serving_base_url()}")

    response = client.chat.completions.create(
        model=get_model_name(),
        messages=[{"role": "user", "content": "Say hello in one sentence."}],
        max_tokens=50,
    )
    print(f"Response: {response.choices[0].message.content}")

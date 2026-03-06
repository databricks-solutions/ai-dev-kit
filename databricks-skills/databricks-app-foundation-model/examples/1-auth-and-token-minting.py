"""
Databricks Apps Foundation Model Authentication

This example demonstrates authentication patterns for calling Foundation Model APIs
from within a Databricks App. The patterns shown here are used in the working example
from databricksters-check-and-pub.

Key patterns:
1. Dual-mode auth: PAT override for local dev + OAuth M2M for deployed apps
2. OAuth token minting using app service principal credentials
3. Token caching in Streamlit session state with expiry check
4. Viewer identity extraction from Databricks Apps forwarded headers

Usage:
- Local dev: Set DATABRICKS_TOKEN env var (PAT)
- Deployed app: Service principal credentials auto-injected as env vars
"""

import os
import time
from typing import Dict, Optional, Tuple

import requests
import streamlit as st
from openai import OpenAI

# =============================================================================
# Configuration
# =============================================================================
DATABRICKS_SERVING_BASE_URL = os.environ.get(
    "DATABRICKS_SERVING_BASE_URL",
    "https://<your-workspace-host>/serving-endpoints",
)
DATABRICKS_MODEL = os.environ.get("DATABRICKS_MODEL", "databricks-meta-llama-3-1-70b-instruct")

# Auth credentials (auto-injected by Databricks Apps when SP is configured)
DATABRICKS_TOKEN = os.environ.get("DATABRICKS_TOKEN")
DATABRICKS_CLIENT_ID = os.environ.get("DATABRICKS_CLIENT_ID")
DATABRICKS_CLIENT_SECRET = os.environ.get("DATABRICKS_CLIENT_SECRET")


# =============================================================================
# Pattern 1: Dual-Mode Authentication
# =============================================================================
def _workspace_host_from_serving_base_url(serving_base_url: str) -> str:
    """Extract workspace host from serving base URL."""
    return serving_base_url.split("/serving-endpoints")[0].rstrip("/")


def get_databricks_bearer_token() -> str:
    """Return a token usable as OpenAI(api_key=...).

    Priority:
    1) DATABRICKS_TOKEN (PAT) if provided
    2) Mint OAuth token from app service principal creds (DATABRICKS_CLIENT_ID/SECRET)

    Tokens are cached in st.session_state to avoid re-minting on every rerun.
    """
    # Priority 1: PAT override (for local dev)
    if DATABRICKS_TOKEN:
        return DATABRICKS_TOKEN

    # Check cache before minting new token
    cached = st.session_state.get("dbx_oauth")
    if (
        cached
        and cached.get("access_token")
        and cached.get("expires_at", 0) > int(time.time()) + 30
    ):
        return cached["access_token"]

    # Priority 2: Mint OAuth token using service principal
    if not (DATABRICKS_CLIENT_ID and DATABRICKS_CLIENT_SECRET):
        raise RuntimeError(
            "No Databricks auth configured. Provide Apps SP creds "
            "(DATABRICKS_CLIENT_ID/SECRET) or set DATABRICKS_TOKEN (PAT)."
        )

    # Derive workspace host from serving base URL
    host = os.environ.get("DATABRICKS_HOST") or _workspace_host_from_serving_base_url(
        DATABRICKS_SERVING_BASE_URL
    )
    host = host.strip().rstrip("/")
    if not host.startswith("http://") and not host.startswith("https://"):
        host = "https://" + host

    # Mint OAuth token
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

    # Cache token with expiry
    st.session_state["dbx_oauth"] = {
        "access_token": access_token,
        "expires_at": int(time.time()) + expires_in,
    }
    return access_token


# =============================================================================
# Pattern 2: Viewer Identity from Forwarded Headers
# =============================================================================
def _get_forwarded_headers() -> Dict[str, str]:
    """Best-effort access to Databricks Apps forwarded headers.

    In Databricks Apps, the platform may forward user identity via headers like:
      - X-Forwarded-Email
      - X-Forwarded-Access-Token

    Streamlit versions differ on how headers are exposed; st.context.headers exists
    in newer Streamlit (1.29+).
    """
    try:
        hdrs = getattr(st, "context").headers
        return {k: v for k, v in hdrs.items()}
    except Exception:
        return {}


def get_viewer_identity() -> Tuple[Optional[str], Optional[str]]:
    """Extract viewer email and access token from forwarded headers.

    Returns:
        (email, access_token) tuple. Both may be None if headers not available.

    Note: Forwarded headers are only available in deployed Databricks Apps,
    not in local Streamlit runs.
    """
    headers = _get_forwarded_headers()
    email = headers.get("X-Forwarded-Email") or headers.get("x-forwarded-email")
    token = headers.get("X-Forwarded-Access-Token") or headers.get(
        "x-forwarded-access-token"
    )
    return email, token


# =============================================================================
# Pattern 3: OpenAI SDK Wiring
# =============================================================================
def create_foundation_model_client() -> OpenAI:
    """Create OpenAI client wired to Databricks serving endpoints.

    The client can be used exactly like the standard OpenAI client, but will
    call Databricks Foundation Model APIs instead.
    """
    token = get_databricks_bearer_token()
    return OpenAI(api_key=token, base_url=DATABRICKS_SERVING_BASE_URL)


# =============================================================================
# Example Usage
# =============================================================================
if __name__ == "__main__":
    # This would typically be in a Streamlit app, but shown here for demonstration

    # Get authentication token (PAT or minted OAuth)
    token = get_databricks_bearer_token()
    print(f"✓ Got auth token: {token[:20]}...")

    # Get viewer identity (only works in deployed apps)
    email, user_token = get_viewer_identity()
    if email:
        print(f"✓ Viewer email: {email}")
    else:
        print("ℹ Viewer identity not available (normal for local dev)")

    # Create OpenAI client for Foundation Model APIs
    client = create_foundation_model_client()
    print(f"✓ Created OpenAI client pointing to: {DATABRICKS_SERVING_BASE_URL}")

    # Example API call
    print(f"\nCalling model: {DATABRICKS_MODEL}")
    response = client.chat.completions.create(
        model=DATABRICKS_MODEL,
        messages=[{"role": "user", "content": "Say hello in one sentence."}],
        max_tokens=50,
    )
    print(f"Response: {response.choices[0].message.content}")

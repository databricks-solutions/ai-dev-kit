"""
Minimal Databricks Foundation Model Chat App

A complete, deployable Streamlit app demonstrating Foundation Model API integration
in Databricks Apps. This is a working example extracted from databricksters-check-and-pub.

Features:
- Dual-mode auth (PAT for local dev, OAuth M2M for deployed apps)
- OpenAI SDK wired to Databricks serving endpoints
- Token caching with expiry check
- Multi-turn chat with conversation history
- Viewer identity display
- Latency tracking

Local Development:
    export DATABRICKS_TOKEN="dapi..."
    export DATABRICKS_SERVING_BASE_URL="https://<workspace>/serving-endpoints"
    export DATABRICKS_MODEL="databricks-meta-llama-3-1-70b-instruct"
    streamlit run 2-minimal-chat-app.py

Databricks Apps Deployment:
    1. Create app.yaml:
       command: ["streamlit", "run", "2-minimal-chat-app.py"]
       env:
         - name: DATABRICKS_SERVING_BASE_URL
           value: "https://<workspace>/serving-endpoints"
         - name: DATABRICKS_MODEL
           value: "databricks-meta-llama-3-1-70b-instruct"

    2. Create requirements.txt:
       openai>=1.30,<2.0
       requests>=2.31,<3.0

    3. Deploy:
       databricks apps create foundation-chat --source-code-path .

    4. Add service principal via UI for OAuth M2M auth
"""

import os
import time
from typing import Dict, List, Optional, Tuple

import requests
import streamlit as st
from openai import OpenAI

# =============================================================================
# CONFIGURATION
# =============================================================================
DATABRICKS_SERVING_BASE_URL = os.environ.get(
    "DATABRICKS_SERVING_BASE_URL",
    "https://<your-workspace-host>/serving-endpoints",
)
DATABRICKS_MODEL = os.environ.get(
    "DATABRICKS_MODEL",
    "databricks-meta-llama-3-1-70b-instruct"
)

# Auth credentials (auto-injected by Databricks Apps)
DATABRICKS_TOKEN = os.environ.get("DATABRICKS_TOKEN")
DATABRICKS_CLIENT_ID = os.environ.get("DATABRICKS_CLIENT_ID")
DATABRICKS_CLIENT_SECRET = os.environ.get("DATABRICKS_CLIENT_SECRET")


# =============================================================================
# Auth Helpers
# =============================================================================
def _workspace_host_from_serving_base_url(serving_base_url: str) -> str:
    """Extract workspace host from serving base URL."""
    return serving_base_url.split("/serving-endpoints")[0].rstrip("/")


def _get_forwarded_headers() -> Dict[str, str]:
    """Best-effort access to Databricks Apps forwarded headers."""
    try:
        hdrs = getattr(st, "context").headers
        return {k: v for k, v in hdrs.items()}
    except Exception:
        return {}


def get_viewer_identity() -> Tuple[Optional[str], Optional[str]]:
    """Extract viewer email and access token from forwarded headers."""
    headers = _get_forwarded_headers()
    email = headers.get("X-Forwarded-Email") or headers.get("x-forwarded-email")
    token = headers.get("X-Forwarded-Access-Token") or headers.get(
        "x-forwarded-access-token"
    )
    return email, token


def get_databricks_bearer_token() -> str:
    """Return a token usable as OpenAI(api_key=...).

    Priority:
    1) DATABRICKS_TOKEN (PAT) if provided
    2) Mint OAuth token from app service principal creds

    Tokens are cached in st.session_state to avoid re-minting.
    """
    if DATABRICKS_TOKEN:
        return DATABRICKS_TOKEN

    # Check cache
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


# =============================================================================
# LLM Helper
# =============================================================================
def llm_chat(
    client: OpenAI,
    *,
    model: str,
    messages: List[Dict[str, str]],
    max_tokens: int = 1000,
    temperature: float = 0.7,
) -> Tuple[str, int]:
    """Call foundation model and return (response, latency_ms)."""
    t0 = time.perf_counter()
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    content = resp.choices[0].message.content or ""
    return content, elapsed_ms


# =============================================================================
# Streamlit App
# =============================================================================
def main():
    st.set_page_config(
        page_title="Databricks Foundation Model Chat",
        page_icon="💬",
        layout="centered",
    )

    st.title("💬 Foundation Model Chat")
    st.caption("Powered by Databricks Apps")

    # Sidebar: viewer identity
    viewer_email, _ = get_viewer_identity()
    if viewer_email:
        st.sidebar.success(f"Logged in as: {viewer_email}")
    else:
        st.sidebar.info("Local dev mode (no viewer identity)")

    # Sidebar: model config
    with st.sidebar:
        st.subheader("Configuration")
        st.code(f"Model: {DATABRICKS_MODEL}", language=None)

        if st.button("🗑️ Clear Chat History"):
            st.session_state.messages = []
            st.rerun()

        with st.expander("ℹ️ About"):
            st.markdown(
                """
                This app demonstrates calling Databricks Foundation Model APIs
                from a Streamlit app using:
                - Dual-mode auth (PAT + OAuth M2M)
                - OpenAI SDK compatibility
                - Token caching with expiry check
                - Viewer identity extraction
                """
            )

    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("latency_ms"):
                st.caption(f"⏱️ {message['latency_ms']}ms")

    # Chat input
    if prompt := st.chat_input("Ask me anything..."):
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Generate assistant response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    # Get auth token and create OpenAI client
                    token = get_databricks_bearer_token()
                    client = OpenAI(
                        api_key=token, base_url=DATABRICKS_SERVING_BASE_URL
                    )

                    # Call foundation model
                    response, latency_ms = llm_chat(
                        client,
                        model=DATABRICKS_MODEL,
                        messages=st.session_state.messages,
                        max_tokens=1000,
                        temperature=0.7,
                    )

                    # Display response
                    st.markdown(response)
                    st.caption(f"⏱️ {latency_ms}ms")

                    # Add to chat history
                    st.session_state.messages.append(
                        {
                            "role": "assistant",
                            "content": response,
                            "latency_ms": latency_ms,
                        }
                    )

                except Exception as e:
                    st.error(f"Error calling foundation model: {e}")
                    st.session_state.messages.pop()  # Remove failed user message


if __name__ == "__main__":
    main()

"""
Minimal Databricks Foundation Model Chat App

A complete, deployable Streamlit app demonstrating Foundation Model API integration
in Databricks Apps. This is a working example extracted from databricksters-check-and-pub.

Features:
- Validated dual-mode auth (OAuth M2M in Apps, PAT for local dev)
- OpenAI SDK wired to Databricks serving endpoints
- Token caching with expiry check
- Multi-turn chat with conversation history
- Viewer identity display
- Latency tracking

Local Development:
    export DATABRICKS_TOKEN="dapi..."
    export DATABRICKS_SERVING_BASE_URL="https://<workspace>/serving-endpoints"
    export DATABRICKS_MODEL="<endpoint-name>"  # See databricks-model-serving
    streamlit run 2-minimal-chat-app.py

Databricks Apps Deployment:
    1. Create app.yaml:
       command: ["streamlit", "run", "2-minimal-chat-app.py"]
       env:
         - name: DATABRICKS_SERVING_BASE_URL
           value: "https://<workspace>/serving-endpoints"
         - name: DATABRICKS_MODEL
           value: "<endpoint-name>"  # See databricks-model-serving

    2. Create requirements.txt:
       streamlit>=1.38,<2.0
       openai>=1.30,<2.0
       requests>=2.31,<3.0  # Needed for endpoint validation and OAuth fallback

    3. Deploy:
       databricks apps create foundation-chat --source-code-path .

    4. Add service principal via UI for OAuth M2M auth
"""

import time
from typing import Dict, List, Optional, Tuple

import streamlit as st
from openai import OpenAI

from llm_config import create_foundation_model_client, get_model_name


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
        st.code(f"Model: {get_model_name()}", language=None)

        if st.button("🗑️ Clear Chat History"):
            st.session_state.messages = []
            st.rerun()

        with st.expander("ℹ️ About"):
            st.markdown(
                """
                This app demonstrates calling Databricks Foundation Model APIs
                from a Streamlit app using:
                - Shared dual-mode auth (PAT + OAuth M2M)
                - Shared OpenAI client wiring
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
                    client = create_foundation_model_client(cache=st.session_state)

                    # Call foundation model
                    response, latency_ms = llm_chat(
                        client,
                        model=get_model_name(),
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

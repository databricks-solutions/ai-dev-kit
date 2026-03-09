---
name: databricks-agent-to-app
description: "Convert agents deployed on Databricks Model Serving endpoints into Databricks Apps with a web UI. Use when migrating an existing serving endpoint agent to a Streamlit/Gradio/Dash app, wrapping a ChatAgent or ResponsesAgent with a frontend, or building a chat interface for an agent endpoint."
---

# Agent-to-App Migration

Convert agents running on Databricks Model Serving endpoints into full Databricks Apps with a web UI.

## When to Use

- You have an agent deployed on a Model Serving endpoint and want to add a chat UI
- You want to move from a REST API-only agent to an interactive application
- You need to wrap an existing `ChatAgent` or `ResponsesAgent` with a frontend
- You want to add authentication, session management, or custom UI to an agent

## Migration Overview

```
┌─────────────────────┐         ┌─────────────────────────────────┐
│  Model Serving      │         │  Databricks App                 │
│  Endpoint           │         │  ┌───────────────────────────┐  │
│  ┌───────────────┐  │         │  │  Web UI (Streamlit/Gradio)│  │
│  │ ChatAgent /   │  │   →     │  │  ↓                        │  │
│  │ ResponsesAgent│  │         │  │  Serving Endpoint Client   │  │
│  └───────────────┘  │         │  │  ↓                        │  │
│  (REST API only)    │         │  │  Your Agent Endpoint       │  │
└─────────────────────┘         │  └───────────────────────────┘  │
                                └─────────────────────────────────┘
```

## Step-by-Step Migration

### Step 1: Identify Your Agent Endpoint

```python
# Find your agent's serving endpoint name
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()

for ep in w.serving_endpoints.list():
    if "agent" in ep.name.lower() or "chat" in ep.name.lower():
        print(f"  {ep.name} — state: {ep.state.ready}")
```

### Step 2: Choose a Framework

| Framework | Best For | Complexity |
|-----------|----------|------------|
| **Streamlit** | Quick chat UI, prototyping | Low |
| **Gradio** | ML demo with chat interface | Low |
| **Dash** | Production dashboard with agent | Medium |
| **FastAPI + React** | Full custom UI | High |

**Recommendation:** Start with **Streamlit** for the fastest migration.

### Step 3: Create the App

#### Streamlit Chat App (Recommended)

**`app.py`**:
```python
import streamlit as st
from databricks.sdk import WorkspaceClient
from databricks.sdk.config import Config

st.set_page_config(page_title="Agent Chat", layout="wide")
st.title("Agent Chat")

config = Config()
w = WorkspaceClient(config=config)

ENDPOINT_NAME = st.secrets.get("SERVING_ENDPOINT", "my-agent-endpoint")

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

if prompt := st.chat_input("Ask the agent..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = w.serving_endpoints.query(
                name=ENDPOINT_NAME,
                messages=[{"role": "user", "content": prompt}],
            )
            answer = response.choices[0].message.content
            st.write(answer)
            st.session_state.messages.append({"role": "assistant", "content": answer})
```

**`app.yaml`**:
```yaml
command:
  - streamlit
  - run
  - app.py
env:
  - name: SERVING_ENDPOINT
    valueFrom: serving-endpoint-name
resources:
  - name: serving-endpoint-name
    serving_endpoint: my-agent-endpoint
```

**`requirements.txt`**:
```
streamlit>=1.30.0
databricks-sdk>=0.20.0
```

#### Gradio Chat App

**`app.py`**:
```python
import os
import gradio as gr
from databricks.sdk import WorkspaceClient
from databricks.sdk.config import Config

config = Config()
w = WorkspaceClient(config=config)

ENDPOINT_NAME = os.environ.get("SERVING_ENDPOINT", "my-agent-endpoint")

def chat(message, history):
    messages = [{"role": "user", "content": m} for m, _ in history]
    messages.append({"role": "user", "content": message})

    response = w.serving_endpoints.query(
        name=ENDPOINT_NAME,
        messages=messages,
    )
    return response.choices[0].message.content

demo = gr.ChatInterface(
    fn=chat,
    title="Agent Chat",
    retry_btn=None,
    undo_btn=None,
)

port = int(os.environ.get("DATABRICKS_APP_PORT", 8000))
demo.launch(server_name="0.0.0.0", server_port=port)
```

### Step 4: Configure App Resources

The `app.yaml` must reference the serving endpoint as a resource so the app's service principal gets access:

```yaml
command:
  - streamlit
  - run
  - app.py
env:
  - name: SERVING_ENDPOINT
    valueFrom: serving-endpoint-name
resources:
  - name: serving-endpoint-name
    serving_endpoint: my-agent-endpoint
  - name: sql-warehouse
    sql_warehouse: your-warehouse-id
```

### Step 5: Deploy

```bash
# Upload app code to workspace
databricks workspace mkdirs /Workspace/Users/$USER/my-agent-app

# Deploy using MCP tool or CLI
databricks apps create my-agent-app
databricks apps deploy my-agent-app --source-code-path /Workspace/Users/$USER/my-agent-app
```

Or use the MCP tool:
```python
create_or_update_app(
    name="my-agent-app",
    source_code_path="/Workspace/Users/me/my-agent-app",
    description="Chat UI for my agent"
)
```

## Multi-Turn Conversation Support

For agents that support multi-turn conversations, pass the full message history:

```python
response = w.serving_endpoints.query(
    name=ENDPOINT_NAME,
    messages=[
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages
    ],
)
```

## Adding User Authentication

Use Databricks OAuth to identify the user and personalize responses:

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.config import Config

config = Config()
w = WorkspaceClient(config=config)
user = w.current_user.me()
st.sidebar.write(f"Logged in as: {user.display_name}")
```

## Common Issues

| Issue | Solution |
|-------|----------|
| **Endpoint returns 403** | Ensure the app's service principal has `CAN_QUERY` on the serving endpoint. Add the endpoint as a `resource` in `app.yaml` |
| **App deploys but agent calls fail** | Check that `SERVING_ENDPOINT` env var matches the actual endpoint name. Use `valueFrom` in `app.yaml` to inject it |
| **Slow first response** | Serving endpoints may scale to zero. The first request triggers cold start. Set `min_provisioned_throughput > 0` for always-on |
| **Chat history lost on page refresh** | Streamlit `session_state` is per-session. For persistent history, store messages in a Lakebase table |
| **Agent returns empty response** | Verify the endpoint is in `READY` state: `w.serving_endpoints.get(name).state.ready` |
| **Token limit exceeded** | Trim conversation history before sending. Keep only the last N messages or summarize older context |
| **App crashes after deploy** | Check logs: `get_app("my-app", include_logs=True)`. Common causes: missing dependencies in `requirements.txt`, wrong port binding |
| **CORS errors in browser** | Databricks Apps handle CORS automatically. If using FastAPI, don't add custom CORS middleware |

## Related Skills

- **[databricks-model-serving](../databricks-model-serving/SKILL.md)** — deploying agents to serving endpoints
- **[databricks-app-python](../databricks-app-python/SKILL.md)** — Python app framework patterns (Streamlit, Gradio, Dash)
- **[databricks-app-apx](../databricks-app-apx/SKILL.md)** — full-stack React + FastAPI apps
- **[databricks-agent-bricks](../databricks-agent-bricks/SKILL.md)** — building Knowledge Assistants and Genie Spaces

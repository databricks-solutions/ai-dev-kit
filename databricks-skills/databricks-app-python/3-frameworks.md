# Supported Frameworks

All frameworks below are **pre-installed** in the Databricks Apps runtime. Claude already knows how to use them — this guide covers only **Databricks-specific** patterns. For full examples and recipes, see the **[Databricks Apps Cookbook](https://apps-cookbook.dev/)**.

---

## Dash

**Best for**: Production dashboards, BI tools, complex interactive visualizations.

**Critical**: Always use `dash-bootstrap-components` for layout and styling.

```python
import dash
import dash_bootstrap_components as dbc

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.FONT_AWESOME],
    title="My Dashboard",
)
```

| Detail | Value |
|--------|-------|
| Pre-installed version | 2.18.1 |
| app.yaml command | `["python", "app.py"]` |
| Default port | 8050 (set `DATABRICKS_APP_PORT=8080` or use `app.run(port=8080)`) |
| Auth header | `request.headers.get('x-forwarded-access-token')` (Flask under the hood) |

**Databricks tips**:
- Use `dbc.themes.BOOTSTRAP` and `dbc.icons.FONT_AWESOME` for consistent styling
- Use Bootstrap badge color names (`"success"`, `"danger"`), not hex colors, for `dbc.Badge`
- Use `prevent_initial_call=True` on expensive callbacks
- Use `dcc.Store` for client-side caching

**Cookbook**: [apps-cookbook.dev/docs/category/dash](https://apps-cookbook.dev/docs/category/dash) — tables, volumes, AI/ML, workflows, dashboards, compute, auth, external services.

---

## Streamlit

**Best for**: Rapid prototyping, data science apps, internal tools, notebook-to-app workflow.

**Critical**: Always use `@st.cache_resource` for database connections.

```python
import streamlit as st
from databricks.sdk.core import Config
from databricks import sql

st.set_page_config(page_title="My App", layout="wide")  # Must be first!

@st.cache_resource(ttl=300)
def get_connection():
    cfg = Config()
    return sql.connect(
        server_hostname=cfg.host,
        http_path="/sql/1.0/warehouses/<id>",
        credentials_provider=lambda: cfg.authenticate,
    )
```

| Detail | Value |
|--------|-------|
| Pre-installed version | 1.38.0 |
| app.yaml command | `["streamlit", "run", "app.py"]` |
| Auth header | `st.context.headers.get('x-forwarded-access-token')` |

**Databricks tips**:
- `st.set_page_config()` must be the **first** Streamlit command
- `@st.cache_resource` for connections/models; `@st.cache_data(ttl=...)` for query results
- Use `st.form()` to batch inputs and prevent reruns on every keystroke
- Use `st.column_config` for formatted DataFrames (currency, dates)

**Cookbook**: [apps-cookbook.dev/docs/category/streamlit](https://apps-cookbook.dev/docs/category/streamlit) — tables, volumes, AI/ML, workflows, visualizations, dashboards, compute, auth, external services.

---

## Gradio

**Best for**: ML model demos, chat interfaces, image/audio/video processing UIs.

**Critical**: Use `gr.Request` parameter to access auth headers.

```python
import gradio as gr
import requests
from databricks.sdk.core import Config

cfg = Config()

def predict(message, request: gr.Request):
    user_token = request.headers.get("x-forwarded-access-token")
    # Query model serving endpoint
    headers = {**cfg.authenticate(), "Content-Type": "application/json"}
    resp = requests.post(
        f"https://{cfg.host}/serving-endpoints/my-model/invocations",
        headers=headers,
        json={"inputs": [{"prompt": message}]},
    )
    return resp.json()["predictions"][0]

demo = gr.Interface(fn=predict, inputs="text", outputs="text")
demo.launch(server_name="0.0.0.0", server_port=8080)
```

| Detail | Value |
|--------|-------|
| Pre-installed version | 4.44.0 |
| app.yaml command | `["python", "app.py"]` |
| Default port | 7860 (override with `server_port=8080` or `GRADIO_SERVER_PORT=8080`) |
| Auth header | `request.headers.get('x-forwarded-access-token')` via `gr.Request` |

**Databricks tips**:
- Natural fit for model serving endpoint integration
- Use `gr.ChatInterface` for conversational AI demos
- Use `gr.Blocks` for complex multi-component layouts

**Docs**: [gradio.app/docs](https://www.gradio.app/docs)

---

## Flask

**Best for**: Custom REST APIs, lightweight web apps, webhook receivers.

**Critical**: Deploy with Gunicorn — never use Flask's dev server in production.

```python
from flask import Flask, request, jsonify
from databricks.sdk.core import Config
from databricks import sql

app = Flask(__name__)
cfg = Config()

@app.route("/api/data")
def get_data():
    conn = sql.connect(
        server_hostname=cfg.host,
        http_path="/sql/1.0/warehouses/<id>",
        credentials_provider=lambda: cfg.authenticate,
    )
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM catalog.schema.table LIMIT 10")
        return jsonify(cursor.fetchall())
```

| Detail | Value |
|--------|-------|
| Pre-installed version | 3.0.3 |
| app.yaml command | `["gunicorn", "app:app", "-w", "4", "-b", "0.0.0.0:8080"]` |
| Auth header | `request.headers.get('x-forwarded-access-token')` |

**Databricks tips**:
- Use connection pooling (Flask doesn't cache connections like Streamlit)
- Gunicorn workers (`-w 4`) handle concurrent requests
- Use `request.headers` for user authorization tokens

---

## FastAPI

**Best for**: Modern async APIs, auto-generated OpenAPI/Swagger docs, high-performance backends.

**Critical**: Deploy with uvicorn.

```python
from fastapi import FastAPI, Request
from databricks.sdk.core import Config
from databricks import sql

app = FastAPI(title="My API")
cfg = Config()

@app.get("/api/data")
async def get_data(request: Request):
    user_token = request.headers.get("x-forwarded-access-token")
    conn = sql.connect(
        server_hostname=cfg.host,
        http_path="/sql/1.0/warehouses/<id>",
        access_token=user_token,
    )
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM catalog.schema.table LIMIT 10")
        return cursor.fetchall()
```

| Detail | Value |
|--------|-------|
| Pre-installed version | 0.115.0 |
| app.yaml command | `["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]` |
| Auth header | `request.headers.get('x-forwarded-access-token')` via `Request` |

**Databricks tips**:
- Auto-generates OpenAPI docs at `/docs` (Swagger) and `/redoc`
- Databricks SQL connector is synchronous — use `asyncio.to_thread()` for async endpoints
- Good choice for API backends that serve APX (FastAPI + React) apps

**Cookbook**: [apps-cookbook.dev/docs/category/fastapi](https://apps-cookbook.dev/docs/category/fastapi) — getting started, endpoint examples.

---

## Reflex

**Best for**: Full-stack Python apps with reactive UIs, no JavaScript required.

```python
import reflex as rx
from databricks.sdk.core import Config

cfg = Config()

class State(rx.State):
    data: list[dict] = []

    def load_data(self):
        from databricks import sql
        conn = sql.connect(
            server_hostname=cfg.host,
            http_path="/sql/1.0/warehouses/<id>",
            credentials_provider=lambda: cfg.authenticate,
        )
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM catalog.schema.table LIMIT 10")
            self.data = [dict(zip([d[0] for d in cursor.description], row)) for row in cursor.fetchall()]
```

| Detail | Value |
|--------|-------|
| app.yaml command | `["reflex", "run", "--env", "prod"]` |
| Auth header | `session.http_conn.headers.get('x-forwarded-access-token')` |

**Cookbook**: [apps-cookbook.dev/docs/category/reflex](https://apps-cookbook.dev/docs/category/reflex) — tables, volumes, AI/ML, workflows, dashboards, compute, auth, external services.

---

## Common: All Frameworks

- All frameworks are **pre-installed** — no need to add them to `requirements.txt`
- Add only additional packages your app needs to `requirements.txt`
- SDK `Config()` auto-detects credentials from injected environment variables
- Databricks Apps expects apps to listen on **port 8080** (configure your framework accordingly)
- For framework-specific deployment commands, see [4-deployment.md](4-deployment.md)
- For authorization integration, see [1-authorization.md](1-authorization.md)

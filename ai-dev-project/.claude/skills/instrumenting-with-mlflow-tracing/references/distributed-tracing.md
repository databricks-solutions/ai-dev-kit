# Distributed Tracing

Connect spans across multiple services into a single trace by propagating trace context over HTTP.

## Overview

MLflow provides two helper functions for distributed tracing:

- **Client**: `mlflow.tracing.get_tracing_context_headers_for_http_request()` - fetches headers to propagate
- **Server**: `mlflow.tracing.set_tracing_context_from_http_request_headers()` - extracts trace context from headers

---

## Client Example

```python
import requests
import mlflow
from mlflow.tracing import get_tracing_context_headers_for_http_request

with mlflow.start_span("client-root"):
    headers = get_tracing_context_headers_for_http_request()
    requests.post(
        "https://your.service/handle", headers=headers, json={"input": "hello"}
    )
```

---

## Server Example (Flask)

```python
import mlflow
from flask import Flask, request
from mlflow.tracing import set_tracing_context_from_http_request_headers

app = Flask(__name__)

@app.post("/handle")
def handle():
    headers = dict(request.headers)
    with set_tracing_context_from_http_request_headers(headers):
        with mlflow.start_span("server-handler") as span:
            # Your logic here
            span.set_attribute("status", "ok")
    return {"ok": True}
```

---

## Server Example (FastAPI)

```python
import mlflow
from fastapi import FastAPI, Request
from mlflow.tracing import set_tracing_context_from_http_request_headers

app = FastAPI()

@app.post("/handle")
async def handle(request: Request):
    headers = dict(request.headers)
    with set_tracing_context_from_http_request_headers(headers):
        with mlflow.start_span("server-handler") as span:
            # Your logic here
            span.set_attribute("status", "ok")
    return {"ok": True}
```

---

## Result

Spans from client and server appear as a single connected trace in MLflow UI, showing end-to-end execution across services.

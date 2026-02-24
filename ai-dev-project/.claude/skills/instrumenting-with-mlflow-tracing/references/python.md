# MLflow Tracing - Python Guide

## Contents
- Quick Start
- Instrumentation Methods (AutoLogging, Decorator, Manual Spans)
- User/Session Tracking
- Combining AutoLogging with Custom Tracing
- Common Issues

---

## Quick Start

### Install and Configure

```bash
pip install mlflow>=3.8.0
```

```python
import mlflow

mlflow.set_tracking_uri("http://localhost:5000")
mlflow.set_experiment("my-agent")
```

### Enable Tracing

**For supported frameworks** (LangChain, LangGraph, OpenAI, etc.):

```python
mlflow.langchain.autolog()  # or openai, anthropic, litellm, etc.
```

**For custom code:**

```python
from mlflow.entities import SpanType

@mlflow.trace(span_type=SpanType.CHAIN)
def my_function(query: str) -> str:
    # Your code here
    return result
```

---

## Instrumentation Methods

### Method 1: AutoLogging (Recommended for Frameworks)

Zero-code instrumentation for supported libraries. See the [Integrations page](https://mlflow.org/docs/latest/genai/tracing/integrations.md) for the complete list.

```python
import mlflow

# Enable before importing/using the library
mlflow.langchain.autolog()    # LangChain, LangGraph
mlflow.openai.autolog()       # OpenAI SDK
mlflow.anthropic.autolog()    # Anthropic SDK
mlflow.litellm.autolog()      # LiteLLM
mlflow.dspy.autolog()         # DSPy
mlflow.autogen.autolog()      # AutoGen
mlflow.crewai.autolog()       # CrewAI
```

### Method 2: Decorator (Recommended for Custom Code)

**Prefer decorator over manual spans** - it auto-captures function name, inputs, and outputs.

```python
from mlflow.entities import SpanType

@mlflow.trace(span_type=SpanType.RETRIEVER)
def retrieve_documents(query: str) -> list[str]:
    return documents

@mlflow.trace(span_type=SpanType.TOOL)
def search_database(sql: str) -> dict:
    return results
```

**Span types**: `LLM`, `CHAIN`, `TOOL`, `AGENT`, `RETRIEVER`, `EMBEDDING`, `RERANKER`, `PARSER`, `UNKNOWN`

### Method 3: Manual Spans (When Decorator Not Possible)

Use only when you can't use a decorator:
- **Tracing code not wrapped in a function** (e.g., script-level code, loop bodies)
- **Dynamic span names** computed at runtime

```python
with mlflow.start_span(name=f"process_{item_id}") as span:
    span.set_inputs({"query": query})  # Must set manually
    result = process(query)
    span.set_outputs({"result": result})  # Must set manually
```

---

## User/Session Tracking

For multi-turn applications, use standard metadata fields `mlflow.trace.user` and `mlflow.trace.session`.

```python
from fastapi import Request
from mlflow.entities import SpanType

@app.post("/chat")
def handle_chat(request: Request, body: ChatRequest):
    user_id = request.headers.get("X-User-ID", "anonymous")
    session_id = request.headers.get("X-Session-ID", "default")
    return chat(body.message, user_id, session_id)

@mlflow.trace(span_type=SpanType.CHAIN)
def chat(message: str, user_id: str, session_id: str) -> str:
    mlflow.update_current_trace(
        metadata={
            "mlflow.trace.user": user_id,
            "mlflow.trace.session": session_id,
        }
    )
    return response
```

**Query traces by user:**

```python
traces = mlflow.search_traces(
    filter_string="metadata.`mlflow.trace.user` = 'user123'"
)
```

---

## Combining AutoLogging with Custom Tracing

```python
import mlflow
from mlflow.entities import SpanType
from langchain_openai import ChatOpenAI

mlflow.langchain.autolog()

@mlflow.trace(name="rag_pipeline", span_type=SpanType.CHAIN)
def rag_query(question: str) -> str:
    docs = retrieve_documents(question)  # Custom function

    llm = ChatOpenAI()  # Auto-traced by autolog
    response = llm.invoke(format_prompt(docs, question))

    return response.content
```

---

## Common Issues

**Traces not appearing?**
1. Verify `mlflow.set_tracking_uri()` points to correct server
2. Ensure autolog is called before framework imports
3. Check experiment is set with `mlflow.set_experiment()`

**Nested spans not connected?**
- Use `@mlflow.trace` or context managers consistently
- For threading, see `advanced-patterns.md`

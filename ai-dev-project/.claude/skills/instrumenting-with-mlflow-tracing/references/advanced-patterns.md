# Advanced Tracing Patterns

## Contents
- Async Function Support
- Multi-Threading with Context Propagation
- PII Redaction with Span Processors
- Custom Span Attributes
- Error Handling and Status
- Trace Linking

For feedback collection, see `feedback-collection.md`.

---

## Async Function Support

Trace async functions using the same decorator:

```python
import mlflow
import asyncio
from mlflow.entities import SpanType

@mlflow.trace(span_type=SpanType.LLM)
async def async_llm_call(prompt: str) -> str:
    response = await llm_client.chat(prompt)
    return response.content

@mlflow.trace(name="parallel_retrieval", span_type=SpanType.RETRIEVER)
async def retrieve_parallel(queries: list[str]) -> list[list[str]]:
    tasks = [retrieve_documents(q) for q in queries]
    return await asyncio.gather(*tasks)
```

---

## Multi-Threading with Context Propagation

MLflow uses `contextvars` to track the active trace. When spawning threads, explicitly copy the context:

```python
import mlflow
from mlflow.entities import SpanType
from concurrent.futures import ThreadPoolExecutor
import contextvars

@mlflow.trace(name="parallel_processing", span_type=SpanType.CHAIN)
def process_items(items: list) -> list:
    results = []

    def process_one(item):
        with mlflow.start_span(name=f"process_{item}") as span:
            span.set_inputs({"item": item})
            result = heavy_computation(item)
            span.set_outputs({"result": result})
            return result

    with ThreadPoolExecutor(max_workers=4) as executor:
        # Copy context to each thread
        ctx = contextvars.copy_context()
        futures = [executor.submit(ctx.run, process_one, item) for item in items]
        results = [f.result() for f in futures]

    return results
```

**Using `run_in_executor` with asyncio**:

```python
import asyncio
import contextvars

async def async_with_thread_work():
    loop = asyncio.get_event_loop()
    ctx = contextvars.copy_context()

    with mlflow.start_span(name="parent") as span:
        # Run blocking code in thread while preserving trace context
        result = await loop.run_in_executor(
            None,
            ctx.run,
            blocking_function,
            arg1, arg2
        )
        return result
```

---

## PII Redaction with Span Processors

Redact sensitive data before traces are logged:

```python
import mlflow
from mlflow.tracing.processor import SpanProcessor
import re

class PIIRedactionProcessor(SpanProcessor):
    """Redact PII from span inputs and outputs."""

    PATTERNS = {
        "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "phone": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
        "credit_card": r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",
    }

    def on_start(self, span, parent_context):
        pass  # Nothing to do on start

    def on_end(self, span):
        # Redact inputs
        if span.inputs:
            span._inputs = self._redact_dict(span.inputs)

        # Redact outputs
        if span.outputs:
            span._outputs = self._redact_dict(span.outputs)

    def _redact_dict(self, data: dict) -> dict:
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self._redact_string(value)
            elif isinstance(value, dict):
                result[key] = self._redact_dict(value)
            elif isinstance(value, list):
                result[key] = [
                    self._redact_string(v) if isinstance(v, str) else v
                    for v in value
                ]
            else:
                result[key] = value
        return result

    def _redact_string(self, text: str) -> str:
        for pii_type, pattern in self.PATTERNS.items():
            text = re.sub(pattern, f"[REDACTED_{pii_type.upper()}]", text)
        return text


# Register the processor
mlflow.tracing.add_span_processor(PIIRedactionProcessor())
```

**Selective field redaction**:

```python
class SelectiveRedactionProcessor(SpanProcessor):
    """Redact specific fields by name."""

    SENSITIVE_FIELDS = {"password", "api_key", "token", "secret", "credentials"}

    def on_end(self, span):
        if span.inputs:
            span._inputs = self._redact_fields(span.inputs)
        if span.outputs:
            span._outputs = self._redact_fields(span.outputs)

    def _redact_fields(self, data: dict) -> dict:
        result = {}
        for key, value in data.items():
            if key.lower() in self.SENSITIVE_FIELDS:
                result[key] = "[REDACTED]"
            elif isinstance(value, dict):
                result[key] = self._redact_fields(value)
            else:
                result[key] = value
        return result
```

---

## Custom Span Attributes

Add custom metadata to spans for filtering and analysis:

```python
from mlflow.entities import SpanType

@mlflow.trace(span_type=SpanType.CHAIN)
def process_request(request_type: str, priority: int) -> str:
    span = mlflow.get_current_active_span()

    # Add custom attributes
    span.set_attributes({
        "request_type": request_type,
        "priority": priority,
        "environment": "production",
        "version": "1.2.3",
    })

    result = handle_request(request_type)
    return result
```

**Query by custom attributes**:

```python
client = mlflow.MlflowClient()
traces = client.search_traces(
    experiment_ids=["1"],
    filter_string="attribute.request_type = 'urgent' AND attribute.priority > 5"
)
```

---

## Error Handling and Status

Spans automatically capture exceptions, but you can add custom error handling:

```python
from mlflow.entities import SpanType

@mlflow.trace(span_type=SpanType.CHAIN)
def risky_operation(data: dict) -> str:
    span = mlflow.get_current_active_span()

    try:
        result = process(data)
        span.set_status("OK")
        return result
    except ValidationError as e:
        span.set_status("ERROR")
        span.set_attributes({
            "error_type": "validation",
            "error_message": str(e),
        })
        raise
    except Exception as e:
        span.set_status("ERROR")
        span.set_attributes({
            "error_type": "unexpected",
            "error_message": str(e),
        })
        # Log but don't re-raise for graceful degradation
        return fallback_response()
```

---

## Trace Linking

Link related traces (e.g., retry attempts, follow-up requests):

```python
from mlflow.entities import SpanType

@mlflow.trace(span_type=SpanType.CHAIN)
def process_with_retry(data: dict, parent_trace_id: str = None) -> str:
    span = mlflow.get_current_active_span()

    if parent_trace_id:
        span.set_attributes({
            "linked_trace_id": parent_trace_id,
            "link_type": "retry",
        })

    try:
        return process(data)
    except RetryableError:
        current_trace_id = span.request_id
        return process_with_retry(data, parent_trace_id=current_trace_id)
```

# Feedback Collection

Log user feedback on traces for evaluation, debugging, and fine-tuning. Essential for identifying quality issues in production.

---

## Recording User Feedback

**Python:**

```python
import mlflow

def record_feedback(trace_id: str, rating: int):
    """Record user feedback for a trace."""
    mlflow.log_feedback(
        trace_id=trace_id,
        name="user_rating",
        value=rating,
        source=mlflow.entities.feedback.FeedbackSource(
            source_type="HUMAN",
            source_id="web_ui"
        )
    )
```

**TypeScript:**

```typescript
import * as mlflow from "mlflow-tracing";

async function recordFeedback(traceId: string, rating: number) {
    await mlflow.logFeedback({
        traceId,
        name: "user_rating",
        value: rating,
        source: { sourceType: "HUMAN", sourceId: "web_ui" },
    });
}
```

---

## Capturing Trace ID for Feedback

Return the trace ID to the client so they can submit feedback later.

```python
from mlflow.entities import SpanType

@mlflow.trace(span_type=SpanType.CHAIN)
def chat(message: str) -> dict:
    response = generate_response(message)

    # Get trace ID to return to client for later feedback
    trace_id = mlflow.get_current_active_span().trace_id

    return {
        "response": response,
        "trace_id": trace_id  # Client uses this to submit feedback
    }
```


## Supported Value Types

| Type | Example | Use Case |
|------|---------|----------|
| `int` / `float` | `5`, `0.85` | Ratings (1-5), scores (0-1), latency metrics |
| `str` | `"Response was helpful"` | User comments, text feedback |
| `bool` | `True`, `False` | Thumbs up/down, binary quality flags |

```python
# Numeric rating
mlflow.log_feedback(trace_id, name="rating", value=5, source=source)

# Text comment
mlflow.log_feedback(trace_id, name="comment", value="Very helpful!", source=source)

# Boolean thumbs up/down
mlflow.log_feedback(trace_id, name="thumbs_up", value=True, source=source)
```

---

## Feedback Source Types

| Source Type | Use Case |
|-------------|----------|
| `HUMAN` | End-user ratings, manual QA reviews |
| `LLM_JUDGE` | Automated LLM evaluation |
| `CODE` | Programmatic checks (e.g., regex validation) |

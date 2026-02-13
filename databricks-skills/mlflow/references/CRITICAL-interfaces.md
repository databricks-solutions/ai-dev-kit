# CRITICAL MLflow 3 GenAI Interfaces

**Version**: MLflow 3.1.0+ (mlflow[databricks]>=3.1.0)
**Last Updated**: Based on official Databricks documentation

## Table of Contents

- [Core Evaluation API](#core-evaluation-api)
- [Data Schema](#data-schema)
- [Built-in Scorers (Prebuilt)](#built-in-scorers-prebuilt)
- [Custom Scorers](#custom-scorers)
- [Judges API (Low-level)](#judges-api-low-level)
- [Trace APIs](#trace-apis)
- [Evaluation Datasets (MLflow-managed)](#evaluation-datasets-mlflow-managed)
- [Production Monitoring](#production-monitoring)
- [Key Constants](#key-constants)
- [Installation](#installation)
- [Setup](#setup)

---

## Core Evaluation API

### mlflow.genai.evaluate()

```python
import mlflow

results = mlflow.genai.evaluate(
    data=eval_dataset,        # List[dict], DataFrame, or EvalDataset
    predict_fn=my_app,        # Callable that takes **inputs and returns outputs
    scorers=[scorer1, scorer2] # List of Scorer objects
)

# Returns: EvaluationResult with:
#   - results.run_id: str - MLflow run ID containing results
#   - results.metrics: dict - Aggregate metrics
```

**CRITICAL**: 
- `predict_fn` receives **unpacked** `inputs` dict as kwargs
- If `data` has pre-computed `outputs`, `predict_fn` is optional
- Traces are automatically created for each row

---

## Data Schema

### Evaluation Dataset Record

```python
# CORRECT format
record = {
    "inputs": {                    # REQUIRED - passed to predict_fn
        "customer_name": "Acme",
        "query": "What is X?"
    },
    "outputs": {                   # OPTIONAL - pre-computed outputs
        "response": "X is..."
    },
    "expectations": {              # OPTIONAL - ground truth for scorers
        "expected_facts": ["fact1", "fact2"],
        "expected_response": "X is...",
        "guidelines": ["Must be concise"]
    }
}
```

**CRITICAL Schema Rules**:
- `inputs` is REQUIRED - contains what's passed to your app
- `outputs` is OPTIONAL - if provided, predict_fn is skipped
- `expectations` is OPTIONAL - used by Correctness, ExpectationsGuidelines

---

## Built-in Scorers (Prebuilt)

### Import Path
```python
from mlflow.genai.scorers import (
    Guidelines,
    ExpectationsGuidelines,
    Correctness,
    RelevanceToQuery,
    RetrievalGroundedness,
    Safety,
)
```

### Guidelines Scorer
```python
Guidelines(
    name="my_guideline",              # REQUIRED - unique name
    guidelines="Response must...",     # REQUIRED - str or List[str]
    model="databricks:/endpoint-name"  # OPTIONAL - custom judge model
)

# Guidelines auto-extracts 'request' and 'response' from trace
# Reference them in guidelines: "The response must address the request"
```

### ExpectationsGuidelines Scorer
```python
ExpectationsGuidelines()  # No parameters needed

# REQUIRES expectations.guidelines in each data row:
record = {
    "inputs": {...},
    "outputs": {...},
    "expectations": {
        "guidelines": ["Must mention X", "Must not include Y"]
    }
}
```

### Correctness Scorer
```python
Correctness(
    model="databricks:/endpoint-name"  # OPTIONAL
)

# REQUIRES expectations.expected_facts OR expectations.expected_response:
record = {
    "inputs": {...},
    "outputs": {...},
    "expectations": {
        "expected_facts": ["MLflow is open-source", "Manages ML lifecycle"]
        # OR
        "expected_response": "MLflow is an open-source platform..."
    }
}
```

### Safety Scorer
```python
Safety(
    model="databricks:/endpoint-name"  # OPTIONAL
)
# No expectations required - evaluates outputs for harmful content
```

### RelevanceToQuery Scorer
```python
RelevanceToQuery(
    model="databricks:/endpoint-name"  # OPTIONAL
)
# Checks if response addresses the user's request
```

### RetrievalGroundedness Scorer
```python
RetrievalGroundedness(
    model="databricks:/endpoint-name"  # OPTIONAL
)
# REQUIRES: Trace with RETRIEVER span type
# Checks if response is grounded in retrieved documents
```

---

## Custom Scorers

### Function-based Scorer (Decorator)

```python
from mlflow.genai.scorers import scorer
from mlflow.entities import Feedback

@scorer
def my_scorer(
    inputs: dict,          # From data record
    outputs: dict,         # App outputs or pre-computed
    expectations: dict,    # From data record (optional)
    trace: Trace = None    # Full MLflow Trace object (optional)
) -> Feedback | bool | int | float | str | list[Feedback]:
    """Custom scorer implementation"""
    
    # Return options:
    # 1. Simple value (metric name = function name)
    return True
    
    # 2. Feedback object with custom name
    return Feedback(
        name="custom_metric",
        value="yes",  # or "no", True/False, int, float
        rationale="Explanation of score"
    )
    
    # 3. Multiple feedbacks
    return [
        Feedback(name="metric_1", value=True),
        Feedback(name="metric_2", value=0.85)
    ]
```

### Class-based Scorer

```python
from mlflow.genai.scorers import Scorer
from mlflow.entities import Feedback
from typing import Optional

class MyScorer(Scorer):
    name: str = "my_scorer"  # REQUIRED
    threshold: int = 50      # Custom fields allowed (Pydantic)
    
    def __call__(
        self, 
        outputs: str,
        inputs: dict = None,
        expectations: dict = None,
        trace = None
    ) -> Feedback:
        if len(outputs) > self.threshold:
            return Feedback(value=True, rationale="Meets length requirement")
        return Feedback(value=False, rationale="Too short")

# Usage
my_scorer = MyScorer(threshold=100)
```

---

## Judges API (Low-level)

### Import Path
```python
from mlflow.genai.judges import (
    meets_guidelines,
    is_correct,
    is_safe,
    is_context_relevant,
    is_grounded,
    make_judge,
)
```

### meets_guidelines()
```python
from mlflow.genai.judges import meets_guidelines

feedback = meets_guidelines(
    name="my_check",                    # Optional display name
    guidelines="Must be professional",   # str or List[str]
    context={                           # Dict with data to evaluate
        "request": "user question",
        "response": "app response",
        "retrieved_documents": [...]     # Can include any keys
    },
    model="databricks:/endpoint"        # Optional custom model
)
# Returns: Feedback(value="yes"|"no", rationale="...")
```

### is_correct()
```python
from mlflow.genai.judges import is_correct

feedback = is_correct(
    request="What is MLflow?",
    response="MLflow is an open-source platform...",
    expected_facts=["MLflow is open-source"],  # OR expected_response
    model="databricks:/endpoint"               # Optional
)
```

### make_judge() - Custom LLM Judge
```python
from mlflow.genai.judges import make_judge

issue_judge = make_judge(
    name="issue_resolution",
    instructions="""
    Evaluate if the customer's issue was resolved.
    User's messages: {{ inputs }}
    Agent's responses: {{ outputs }}
    
    Rate and respond with exactly one of:
    - 'fully_resolved'
    - 'partially_resolved' 
    - 'needs_follow_up'
    """,
    model="databricks:/databricks-gpt-5-mini"  # Optional
)

# Use in evaluation
results = mlflow.genai.evaluate(
    data=eval_dataset,
    predict_fn=my_app,
    scorers=[issue_judge]
)
```

### Trace-based Judge (with {{ trace }})
```python
# Including {{ trace }} in instructions enables trace exploration
tool_judge = make_judge(
    name="tool_correctness",
    instructions="""
    Analyze the execution {{ trace }} to determine if appropriate tools were called.
    Respond with true or false.
    """,
    model="databricks:/databricks-gpt-5-mini"  # REQUIRED for trace judges
)
```

---

## Trace APIs

### Search Traces
```python
import mlflow

traces_df = mlflow.search_traces(
    filter_string="attributes.status = 'OK'",
    order_by=["attributes.timestamp_ms DESC"],
    max_results=100,
    run_id="optional-run-id"  # Filter to specific evaluation run
)

# Common filters:
# "attributes.status = 'OK'" or "attributes.status = 'ERROR'"
# "attributes.timestamp_ms > {milliseconds}"
# "attributes.execution_time_ms > 5000"
# "tags.environment = 'production'"
# "tags.`mlflow.traceName` = 'my_function'"
```

### Trace Object Access
```python
from mlflow.entities import Trace, SpanType

@scorer
def trace_scorer(trace: Trace) -> Feedback:
    # Search spans by type
    llm_spans = trace.search_spans(span_type=SpanType.CHAT_MODEL)
    retriever_spans = trace.search_spans(span_type=SpanType.RETRIEVER)
    
    # Access span data
    for span in llm_spans:
        duration = (span.end_time_ns - span.start_time_ns) / 1e9
        inputs = span.inputs
        outputs = span.outputs
```

---

## Evaluation Datasets (MLflow-managed)

### Create Dataset
```python
import mlflow.genai.datasets
from databricks.connect import DatabricksSession

# Required for MLflow-managed datasets
spark = DatabricksSession.builder.remote(serverless=True).getOrCreate()

eval_dataset = mlflow.genai.datasets.create_dataset(
    uc_table_name="catalog.schema.my_eval_dataset"
)
```

### Add Records
```python
# From list of dicts
records = [
    {"inputs": {"query": "..."}, "expectations": {"expected_facts": [...]}},
]
eval_dataset.merge_records(records)

# From traces
traces_df = mlflow.search_traces(filter_string="...")
eval_dataset.merge_records(traces_df)
```

### Use in Evaluation
```python
results = mlflow.genai.evaluate(
    data=eval_dataset,  # Pass dataset object directly
    predict_fn=my_app,
    scorers=[...]
)
```

---

## Production Monitoring

### Register and Start Scorer
```python
from mlflow.genai.scorers import Safety, Guidelines, ScorerSamplingConfig

# Register scorer to experiment
safety = Safety().register(name="safety_monitor")

# Start monitoring with sample rate
safety = safety.start(
    sampling_config=ScorerSamplingConfig(sample_rate=0.5)  # 50% of traces
)
```

### Manage Scorers
```python
from mlflow.genai.scorers import list_scorers, get_scorer, delete_scorer

# List all registered scorers
scorers = list_scorers()

# Get specific scorer
my_scorer = get_scorer(name="safety_monitor")

# Update sample rate
my_scorer = my_scorer.update(
    sampling_config=ScorerSamplingConfig(sample_rate=0.8)
)

# Stop monitoring (keeps registration)
my_scorer = my_scorer.stop()

# Delete entirely
delete_scorer(name="safety_monitor")
```

---

## Key Constants

### Span Types
```python
from mlflow.entities import SpanType

SpanType.CHAT_MODEL      # LLM calls
SpanType.RETRIEVER       # RAG retrieval
SpanType.TOOL            # Tool/function calls
SpanType.AGENT           # Agent execution
SpanType.CHAIN           # Chain execution
```

### Feedback Values
```python
# LLM judges typically return:
"yes" | "no"     # For pass/fail assessments

# Custom scorers can return:
True | False     # Boolean
0.0 - 1.0        # Float scores
int              # Integer scores
str              # Categorical values
```

---

## Installation

```bash
pip install --upgrade "mlflow[databricks]>=3.1.0" openai
```

## Setup

```python
import mlflow

# Enable auto-tracing
mlflow.openai.autolog()  # or mlflow.langchain.autolog(), etc.

# Set tracking URI
mlflow.set_tracking_uri("databricks")

# Set experiment
mlflow.set_experiment("/Shared/my-experiment")
```

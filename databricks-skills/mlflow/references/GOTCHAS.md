# MLflow 3 GenAI - GOTCHAS & Common Mistakes

**CRITICAL**: Read this before writing any evaluation code. These are the most common mistakes that will cause failures.

## Table of Contents

- [Using Model Serving Endpoints for Development](#-wrong-using-model-serving-endpoints-for-development)
- [Wrong API Imports](#-wrong-api-imports)
- [Wrong Evaluate Function](#-wrong-evaluate-function)
- [Wrong Data Format](#-wrong-data-format)
- [Wrong predict_fn Signature](#-wrong-predict_fn-signature)
- [Wrong Scorer Decorator Usage](#-wrong-scorer-decorator-usage)
- [Wrong Feedback Return](#-wrong-feedback-return)
- [Wrong Guidelines Scorer Setup](#-wrong-guidelines-scorer-setup)
- [Wrong Trace Search Syntax](#-wrong-trace-search-syntax)
- [Wrong Expectations Usage](#-wrong-expectations-usage)
- [Wrong RetrievalGroundedness Usage](#-wrong-retrievalgroundedness-usage)
- [Wrong Custom Scorer Imports](#-wrong-custom-scorer-imports)
- [Wrong Type Hints in Scorers](#-wrong-type-hints-in-scorers)
- [Wrong Dataset Creation](#-wrong-dataset-creation)
- [Wrong Multiple Feedback Names](#-wrong-multiple-feedback-names)
- [Wrong Guidelines Context Reference](#-wrong-guidelines-context-reference)
- [Wrong Production Monitoring Setup](#-wrong-production-monitoring-setup)
- [Wrong Custom Judge Model Format](#-wrong-custom-judge-model-format)
- [Wrong Aggregation Values](#-wrong-aggregation-values)
- [Summary Checklist](#summary-checklist)

---

## ❌ WRONG: Using Model Serving Endpoints for Development

### WRONG: Calling deployed endpoint for initial testing
```python
# ❌ WRONG - Don't use model serving endpoints during development
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
client = w.serving_endpoints.get_open_ai_client()

def predict_fn(messages):
    response = client.chat.completions.create(
        model="my-agent-endpoint",  # Deployed endpoint
        messages=messages
    )
    return {"response": response.choices[0].message.content}
```

### ✅ CORRECT: Import and test agent locally
```python
# ✅ CORRECT - Import agent directly for fast iteration
from plan_execute_agent import AGENT  # Your local agent module

def predict_fn(messages):
    result = AGENT.predict({"messages": messages})
    # Extract response from ResponsesAgent format
    if isinstance(result, dict) and "messages" in result:
        for msg in reversed(result["messages"]):
            if msg.get("role") == "assistant":
                return {"response": msg.get("content", "")}
    return {"response": str(result)}
```

**Why?**
- Local testing enables faster iteration (no deployment needed)
- Full stack traces for debugging
- No serving endpoint costs
- Direct access to agent internals

**When to use endpoints**: Only for production monitoring, load testing, or A/B testing deployed versions.

---

## ❌ WRONG API IMPORTS

### WRONG: Using old MLflow 2 imports
```python
# ❌ WRONG - These don't exist in MLflow 3 GenAI
from mlflow.evaluate import evaluate
from mlflow.metrics import genai
import mlflow.llm
```

### ✅ CORRECT: MLflow 3 GenAI imports
```python
# ✅ CORRECT
import mlflow.genai
from mlflow.genai.scorers import Guidelines, Safety, Correctness, scorer
from mlflow.genai.judges import meets_guidelines, is_correct, make_judge
from mlflow.entities import Feedback, Trace
```

---

## ❌ WRONG EVALUATE FUNCTION

### WRONG: Using mlflow.evaluate()
```python
# ❌ WRONG - This is the old API for classic ML
results = mlflow.evaluate(
    model=my_model,
    data=eval_data,
    model_type="text"
)
```

### ✅ CORRECT: Using mlflow.genai.evaluate()
```python
# ✅ CORRECT - MLflow 3 GenAI evaluation
results = mlflow.genai.evaluate(
    data=eval_dataset,
    predict_fn=my_app,
    scorers=[Guidelines(name="test", guidelines="...")]
)
```

---

## ❌ WRONG DATA FORMAT

### WRONG: Flat data structure
```python
# ❌ WRONG - Missing nested structure
eval_data = [
    {"query": "What is X?", "expected": "X is..."}
]
```

### ✅ CORRECT: Proper nested structure
```python
# ✅ CORRECT - Must have 'inputs' key
eval_data = [
    {
        "inputs": {"query": "What is X?"},
        "expectations": {"expected_response": "X is..."}
    }
]
```

---

## ❌ WRONG predict_fn SIGNATURE

### WRONG: Function expects dict
```python
# ❌ WRONG - predict_fn receives **unpacked inputs
def my_app(inputs):  # Receives dict
    query = inputs["query"]
    return {"response": "..."}
```

### ✅ CORRECT: Function receives keyword args
```python
# ✅ CORRECT - inputs are unpacked as kwargs
def my_app(query, context=None):  # Receives individual keys
    return {"response": f"Answer to {query}"}

# If inputs = {"query": "What is X?", "context": "..."}
# Then my_app is called as: my_app(query="What is X?", context="...")
```

---

## ❌ WRONG SCORER DECORATOR USAGE

### WRONG: Missing decorator
```python
# ❌ WRONG - This won't work as a scorer
def my_scorer(inputs, outputs):
    return True
```

### ✅ CORRECT: Use @scorer decorator
```python
# ✅ CORRECT
from mlflow.genai.scorers import scorer

@scorer
def my_scorer(inputs, outputs):
    return True
```

---

## ❌ WRONG FEEDBACK RETURN

### WRONG: Returning wrong types
```python
@scorer
def bad_scorer(outputs):
    # ❌ WRONG - Can't return dict
    return {"score": 0.5, "reason": "..."}
    
    # ❌ WRONG - Can't return tuple
    return (True, "rationale")
```

### ✅ CORRECT: Return Feedback or primitive
```python
from mlflow.entities import Feedback

@scorer
def good_scorer(outputs):
    # ✅ CORRECT - Return primitive
    return True
    return 0.85
    return "yes"
    
    # ✅ CORRECT - Return Feedback object
    return Feedback(
        value=True,
        rationale="Explanation"
    )
    
    # ✅ CORRECT - Return list of Feedbacks
    return [
        Feedback(name="metric_1", value=True),
        Feedback(name="metric_2", value=0.9)
    ]
```

---

## ❌ WRONG GUIDELINES SCORER SETUP

### WRONG: Missing required parameters
```python
# ❌ WRONG - Missing 'name' parameter
scorer = Guidelines(guidelines="Must be professional")
```

### ✅ CORRECT: Include name and guidelines
```python
# ✅ CORRECT
scorer = Guidelines(
    name="professional_tone",  # REQUIRED
    guidelines="The response must be professional"  # REQUIRED
)
```

---

## ❌ WRONG TRACE SEARCH SYNTAX

### WRONG: Missing prefixes and wrong quotes
```python
# ❌ WRONG - Missing prefix
mlflow.search_traces("status = 'OK'")

# ❌ WRONG - Using double quotes
mlflow.search_traces('attributes.status = "OK"')

# ❌ WRONG - Missing backticks for dotted names
mlflow.search_traces("tags.mlflow.traceName = 'my_app'")

# ❌ WRONG - Using OR (not supported)
mlflow.search_traces("attributes.status = 'OK' OR attributes.status = 'ERROR'")
```

### ✅ CORRECT: Proper filter syntax
```python
# ✅ CORRECT - Use prefix and single quotes
mlflow.search_traces("attributes.status = 'OK'")

# ✅ CORRECT - Backticks for dotted names
mlflow.search_traces("tags.`mlflow.traceName` = 'my_app'")

# ✅ CORRECT - AND is supported
mlflow.search_traces("attributes.status = 'OK' AND tags.env = 'prod'")

# ✅ CORRECT - Time in milliseconds
import time
cutoff = int((time.time() - 3600) * 1000)  # 1 hour ago
mlflow.search_traces(f"attributes.timestamp_ms > {cutoff}")
```

---

## ❌ WRONG EXPECTATIONS USAGE

### WRONG: Using Correctness without expectations
```python
# ❌ WRONG - Correctness requires expected_facts or expected_response
eval_data = [
    {"inputs": {"query": "What is X?"}}
]
results = mlflow.genai.evaluate(
    data=eval_data,
    predict_fn=my_app,
    scorers=[Correctness()]  # Will fail - no ground truth!
)
```

### ✅ CORRECT: Include expectations for Correctness
```python
# ✅ CORRECT
eval_data = [
    {
        "inputs": {"query": "What is X?"},
        "expectations": {
            "expected_facts": ["X is a platform", "X is open-source"]
        }
    }
]
```

---

## ❌ WRONG RetrievalGroundedness USAGE

### WRONG: Using without RETRIEVER span
```python
# ❌ WRONG - App has no RETRIEVER span type
@mlflow.trace
def my_rag_app(query):
    docs = get_documents(query)  # Not marked as retriever
    return generate_response(docs, query)

# RetrievalGroundedness will fail - can't find retriever spans
```

### ✅ CORRECT: Mark retrieval with proper span type
```python
# ✅ CORRECT - Use span_type="RETRIEVER"
@mlflow.trace(span_type="RETRIEVER")
def retrieve_documents(query):
    return [doc1, doc2]

@mlflow.trace
def my_rag_app(query):
    docs = retrieve_documents(query)  # Now has RETRIEVER span
    return generate_response(docs, query)
```

---

## ❌ WRONG CUSTOM SCORER IMPORTS

### WRONG: External imports at module level
```python
# ❌ WRONG for production monitoring - external import outside function
import my_custom_library

@scorer
def production_scorer(outputs):
    return my_custom_library.process(outputs)
```

### ✅ CORRECT: Inline imports for production scorers
```python
# ✅ CORRECT - Import inside function for serialization
@scorer
def production_scorer(outputs):
    import json  # Import inside for production monitoring
    return len(json.dumps(outputs)) > 100
```

---

## ❌ WRONG TYPE HINTS IN SCORERS

### WRONG: Type hints requiring imports in signature
```python
# ❌ WRONG - Type hints break serialization for production monitoring
from typing import List

@scorer
def bad_scorer(outputs: List[str]) -> bool:
    return True
```

### ✅ CORRECT: Avoid complex type hints or use dict
```python
# ✅ CORRECT - Simple types work
@scorer
def good_scorer(outputs):
    return True

# ✅ CORRECT - dict is fine
@scorer
def good_scorer(outputs: dict) -> bool:
    return True
```

---

## ❌ WRONG Dataset Creation

### WRONG: Missing Spark session for MLflow datasets
```python
# ❌ WRONG - Need Spark for MLflow-managed datasets
import mlflow.genai.datasets

dataset = mlflow.genai.datasets.create_dataset(
    uc_table_name="catalog.schema.my_dataset"
)
# Error: No Spark session available
```

### ✅ CORRECT: Initialize Spark first
```python
# ✅ CORRECT
from databricks.connect import DatabricksSession

spark = DatabricksSession.builder.remote(serverless=True).getOrCreate()

dataset = mlflow.genai.datasets.create_dataset(
    uc_table_name="catalog.schema.my_dataset"
)
```

---

## ❌ WRONG Multiple Feedback Names

### WRONG: Multiple feedbacks without unique names
```python
@scorer
def bad_multi_scorer(outputs):
    # ❌ WRONG - Feedbacks will conflict
    return [
        Feedback(value=True),
        Feedback(value=0.8)
    ]
```

### ✅ CORRECT: Unique names for each Feedback
```python
@scorer
def good_multi_scorer(outputs):
    # ✅ CORRECT - Each has unique name
    return [
        Feedback(name="check_1", value=True),
        Feedback(name="check_2", value=0.8)
    ]
```

---

## ❌ WRONG Guidelines Context Reference

### WRONG: Wrong variable names in guidelines
```python
# ❌ WRONG - Guidelines use 'request' and 'response', not custom keys
Guidelines(
    name="check",
    guidelines="The output must address the query"  # 'output' and 'query' not available
)
```

### ✅ CORRECT: Use 'request' and 'response'
```python
# ✅ CORRECT - These are auto-extracted
Guidelines(
    name="check",
    guidelines="The response must address the request"
)
```

---

## ❌ WRONG Production Monitoring Setup

### WRONG: Forgetting to start after register
```python
# ❌ WRONG - Registered but not started
from mlflow.genai.scorers import Safety

safety = Safety().register(name="safety_check")
# Scorer exists but isn't running!
```

### ✅ CORRECT: Register then start
```python
# ✅ CORRECT - Both register and start
from mlflow.genai.scorers import Safety, ScorerSamplingConfig

safety = Safety().register(name="safety_check")
safety = safety.start(
    sampling_config=ScorerSamplingConfig(sample_rate=0.5)
)
```

---

## ❌ WRONG Custom Judge Model Format

### WRONG: Wrong model format
```python
# ❌ WRONG - Missing provider prefix
Guidelines(name="test", guidelines="...", model="gpt-4o")

# ❌ WRONG - Wrong separator
Guidelines(name="test", guidelines="...", model="databricks:gpt-4o")
```

### ✅ CORRECT: Use provider:/model format
```python
# ✅ CORRECT - Use :/ separator
Guidelines(name="test", guidelines="...", model="databricks:/my-endpoint")
Guidelines(name="test", guidelines="...", model="openai:/gpt-4o")
```

---

## ❌ WRONG Aggregation Values

### WRONG: Invalid aggregation names
```python
# ❌ WRONG - p50, p99, sum are not valid
@scorer(aggregations=["mean", "p50", "p99", "sum"])
def my_scorer(outputs) -> float:
    return 0.5
```

### ✅ CORRECT: Use valid aggregation names
```python
# ✅ CORRECT - Only these 6 are valid
@scorer(aggregations=["min", "max", "mean", "median", "variance", "p90"])
def my_scorer(outputs) -> float:
    return 0.5
```

**Valid aggregations:**
- `min` - minimum value
- `max` - maximum value
- `mean` - average value
- `median` - 50th percentile (NOT `p50`)
- `variance` - statistical variance
- `p90` - 90th percentile (only p90, NOT p50 or p99)

---

## Summary Checklist

Before running evaluation, verify:

- [ ] Using `mlflow.genai.evaluate()` (not `mlflow.evaluate()`)
- [ ] Data has `inputs` key (nested structure)
- [ ] `predict_fn` accepts **unpacked kwargs (not dict)
- [ ] Scorers have `@scorer` decorator
- [ ] Guidelines have both `name` and `guidelines`
- [ ] Correctness has `expectations.expected_facts` or `expected_response`
- [ ] RetrievalGroundedness has `RETRIEVER` span in trace
- [ ] Trace filters use `attributes.` prefix and single quotes
- [ ] Production scorers have inline imports
- [ ] Multiple Feedbacks have unique names
- [ ] Aggregations use valid names: min, max, mean, median, variance, p90

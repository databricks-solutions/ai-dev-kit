# Troubleshooting Guide

Common errors and solutions for agent evaluation with MLflow.

## Table of Contents

1. [Environment Setup Issues](#environment-setup-issues)
2. [Tracing Integration Issues](#tracing-integration-issues)
3. [Dataset Creation Issues](#dataset-creation-issues)
4. [Evaluation Execution Issues](#evaluation-execution-issues)
5. [Scorer Issues](#scorer-issues)

## Environment Setup Issues

### MLflow Not Found

**Error**: `mlflow: command not found` or `ModuleNotFoundError: No module named 'mlflow'`

**Cause**: MLflow is not installed or not in PATH

**Solutions**:

1. Install MLflow: `uv pip install mlflow`
2. Verify installation: `mlflow --version`
3. Check virtual environment is activated
4. For command line: Add MLflow to PATH

### Wrong API Imports

**Error/Symptoms**: `ImportError`, `AttributeError`, or methods not found

**WRONG:**
```python
# These don't exist in MLflow 3 GenAI
from mlflow.evaluate import evaluate
from mlflow.metrics import genai
import mlflow.llm
```

**CORRECT:**
```python
import mlflow.genai
from mlflow.genai.scorers import Guidelines, Safety, Correctness, scorer
from mlflow.genai.judges import meets_guidelines, is_correct, make_judge
from mlflow.entities import Feedback, Trace
```

**Why**: MLflow 3 GenAI has a completely new API structure. Old MLflow 2 imports don't exist.

### Databricks Profile Not Authenticated

**Error**: `Profile X not authenticated` or `Invalid credentials`

**Cause**: Databricks CLI is not authenticated for the selected profile

**Solutions**:

1. Run authentication: `databricks auth login -p <profile_name>`
2. Follow prompts to authenticate
3. Verify with: `databricks auth env -p <profile_name>`
4. Check profile exists: `databricks auth profiles`

### Local MLflow Server Won't Start

**Error**: `Address already in use` or port binding error

**Cause**: Another process is using the port or MLflow server already running

**Solutions**:

1. Check if server is already running: `ps aux | grep mlflow`
2. Use different port: `mlflow server --port 5051 ...`
3. Kill existing server: `pkill -f "mlflow server"`
4. Check port availability: `lsof -i :5050`

### Experiment Not Found

**Error**: `Experiment <id> not found` or `Invalid experiment ID`

**Cause**: MLFLOW_EXPERIMENT_ID refers to non-existent experiment

**Solutions**:

1. List experiments: `mlflow experiments list`
2. Create experiment: `mlflow experiments create -n <name>`
3. Verify ID: `mlflow experiments get --experiment-id <id>`
4. Update environment variable: `export MLFLOW_EXPERIMENT_ID=<correct_id>`

## Tracing Integration Issues

### No Traces Captured

**Symptoms**: `mlflow.get_last_active_trace_id()` returns None, no traces in UI

**Causes**:

1. Autolog not enabled
2. @trace decorator missing
3. Environment variables not set
4. Tracing not supported for library version

**Solutions**:

1. Check MLFLOW_TRACKING_URI is set: `echo $MLFLOW_TRACKING_URI`
2. Check MLFLOW_EXPERIMENT_ID is set: `echo $MLFLOW_EXPERIMENT_ID`
3. Verify autolog call exists: `grep -r "autolog" src/`
4. Verify decorators present: `grep -r "@mlflow.trace" src/`
5. Run validation script: `python scripts/validate_tracing_runtime.py`
   # Script will auto-detect module and entry point
6. Check MLflow version: `mlflow --version` (need >=3.6.0)

### Missing Library Spans (Autolog Not Working)

**Symptoms**: Top-level span present but no LangChain/LangGraph/OpenAI spans

**Causes**:

1. Autolog called after library imports
2. Wrong library specified (e.g., `langchain` vs `langgraph`)
3. Library not installed or wrong version
4. Autolog not supported for library

**Solutions**:

1. Move autolog call before imports:

   ```python
   # CORRECT:
   import mlflow

   mlflow.langchain.autolog()  # BEFORE library import
   from langchain import ChatOpenAI  # library imports after autolog

   # WRONG:
   from langchain import ChatOpenAI  # library imports before autolog
   import mlflow

   mlflow.langchain.autolog()  # TOO LATE
   ```

2. Verify correct library:

   - LangChain uses: `mlflow.langchain.autolog()`
   - LangGraph also uses: `mlflow.langchain.autolog()` (not langgraph)
   - OpenAI uses: `mlflow.openai.autolog()`

3. Check library installed: `pip list | grep langchain`

4. Check compatibility: Read MLflow docs for supported versions

### Missing Top-Level Span (Decorator Not Working)

**Symptoms**: Library spans present but no function span with your function name

**Causes**:

1. @mlflow.trace decorator missing
2. Decorator is `@trace` instead of `@mlflow.trace`
3. mlflow not imported in file
4. Decorator on wrong function

**Solutions**:

1. Add decorator to ALL entry points:

   ```python
   import mlflow


   @mlflow.trace  # <-- ADD THIS
   def run_agent(query: str):
       ...
   ```

2. Verify decorator spelling: `@mlflow.trace` not `@trace`

3. Check mlflow import at top of file

4. Grep for decorators: `grep -B 2 "def run_agent" src/*/agent/*.py`

### Wrong Trace Search Syntax

**Error/Symptoms**: Empty results, syntax errors, or unexpected trace filtering behavior

**WRONG:**
```python
# Missing prefix
mlflow.search_traces("status = 'OK'")

# Using double quotes
mlflow.search_traces('attributes.status = "OK"')

# Missing backticks for dotted names
mlflow.search_traces("tags.mlflow.traceName = 'my_app'")

# Using OR (not supported)
mlflow.search_traces("attributes.status = 'OK' OR attributes.status = 'ERROR'")
```

**CORRECT:**
```python
# Use prefix and single quotes
mlflow.search_traces("attributes.status = 'OK'")

# Backticks for dotted names
mlflow.search_traces("tags.`mlflow.traceName` = 'my_app'")

# AND is supported
mlflow.search_traces("attributes.status = 'OK' AND tags.env = 'prod'")

# Time in milliseconds
import time
cutoff = int((time.time() - 3600) * 1000)  # 1 hour ago
mlflow.search_traces(f"attributes.timestamp_ms > {cutoff}")
```

**Why**: MLflow trace search has specific syntax rules - attributes need prefixes, string values use single quotes, dotted tag names need backticks, and OR is not supported.

### Session ID Not Captured

**Symptoms**: Trace exists but no session_id in tags

**Causes**:

1. mlflow.set_trace_tag() not called
2. Timing issue - set_trace_tag called too late
3. trace_id is None when setting tag

**Solutions**:

1. Add session tracking code:

   ```python
   @mlflow.trace
   def run_agent(query: str, session_id: str = None):
       if session_id is None:
           session_id = str(uuid.uuid4())

       # Get trace ID and set tag IMMEDIATELY
       trace_id = mlflow.get_last_active_trace_id()
       if trace_id:
           mlflow.set_trace_tag(trace_id, "session_id", session_id)

       # Rest of function...
   ```

2. Verify timing - call early in function

3. Check trace_id is not None before calling set_trace_tag

4. Test with validation code from `references/tracing-integration.md`

### Import Errors When Testing

**Error**: `ModuleNotFoundError: No module named '<your_agent>'`

**Cause**: Agent package not installed in Python path

**Solutions**:

1. Install in editable mode: `pip install -e .` (from project root)
2. Verify package installed: `pip list | grep <package_name>`
3. Check in correct virtual environment: `which python`
4. Verify PYTHONPATH includes project: `echo $PYTHONPATH`

## Dataset Creation Issues

### Wrong Data Format

**Error/Symptoms**: Schema validation error, missing fields, or evaluation doesn't use your data correctly

**WRONG:**
```python
# Flat data structure - missing nested structure
eval_data = [
    {"query": "What is X?", "expected": "X is..."}
]
```

**CORRECT:**
```python
# Must have 'inputs' key, optionally 'expectations'
eval_data = [
    {
        "inputs": {"query": "What is X?"},
        "expectations": {"expected_response": "X is..."}
    }
]
```

**Why**: MLflow GenAI expects a specific nested structure with `inputs` containing the data passed to predict_fn and `expectations` containing ground truth for scorers.

### Wrong Dataset Creation - Spark Session

**Error/Symptoms**: `No Spark session available` or Unity Catalog dataset creation fails

**WRONG:**
```python
# Need Spark for MLflow-managed datasets
import mlflow.genai.datasets

dataset = mlflow.genai.datasets.create_dataset(
    uc_table_name="catalog.schema.my_dataset"
)
# Error: No Spark session available
```

**CORRECT:**
```python
from databricks.connect import DatabricksSession

spark = DatabricksSession.builder.remote(serverless=True).getOrCreate()

dataset = mlflow.genai.datasets.create_dataset(
    uc_table_name="catalog.schema.my_dataset"
)
```

**Why**: Unity Catalog dataset creation requires an active Spark session for table operations.

### Databricks Dataset APIs Not Supported

**Error**: `"Evaluation dataset APIs is not supported in Databricks environments"`

**Context**: When accessing `experiment_ids` or `tags` fields on Databricks

**Cause**: These fields are not supported in Databricks tracking URIs

**Solution**: Only access `name` and `dataset_id` fields:

```python
# CORRECT for Databricks:
for dataset in datasets:
    print(dataset.name)
    print(dataset.dataset_id)

# WRONG for Databricks:
for dataset in datasets:
    print(dataset.experiment_ids)  # ERROR!
    print(dataset.tags)  # ERROR!
```

### Unity Catalog Table Not Found

**Error**: `Table not found: <catalog>.<schema>.<table>`

**Causes**:

1. Table name not fully qualified
2. Catalog or schema doesn't exist
3. Insufficient permissions

**Solutions**:

1. Use fully-qualified name: `catalog.schema.table`

   ```python
   # CORRECT:
   dataset = create_dataset(name="main.default.my_eval")

   # WRONG:
   dataset = create_dataset(name="my_eval")
   ```

2. Verify catalog exists: `databricks catalogs list`

3. Verify schema exists: `databricks schemas list <catalog>`

4. Check permissions: Ensure you have CREATE TABLE permission

5. Use default location: `main.default.<your_table>`

### Invalid Dataset Schema

**Error**: Schema validation error or `Invalid record format`

**Cause**: Records don't match expected format

**Solution**: Use correct format with `inputs` key:

```python
# CORRECT:
records = [
    {"inputs": {"query": "What is MLflow?"}},
    {"inputs": {"query": "How do I log models?"}},
]

# WRONG:
records = [
    {"query": "What is MLflow?"},  # Missing "inputs" wrapper
    {"question": "How do I log models?"},  # Wrong structure
]
```

### Dataset Creation Fails Silently

**Symptoms**: No error but dataset not created or not findable

**Causes**:

1. Wrong tracking URI
2. Wrong experiment ID
3. Permissions issue (Databricks)

**Solutions**:

1. Verify environment: `echo $MLFLOW_TRACKING_URI`
2. Verify experiment: `echo $MLFLOW_EXPERIMENT_ID`
3. Check dataset was created: `client.search_datasets(experiment_ids=[exp_id])`
4. For Databricks, use Unity Catalog tools to verify table exists

## Evaluation Execution Issues

### Wrong Evaluate Function

**Error/Symptoms**: Wrong API, unexpected results, or `model_type` parameter errors

**WRONG:**
```python
# This is the old API for classic ML
results = mlflow.evaluate(
    model=my_model,
    data=eval_data,
    model_type="text"
)
```

**CORRECT:**
```python
# MLflow 3 GenAI evaluation
results = mlflow.genai.evaluate(
    data=eval_dataset,
    predict_fn=my_app,
    scorers=[Guidelines(name="test", guidelines="...")]
)
```

**Why**: `mlflow.evaluate()` is for classic ML models. GenAI agents use `mlflow.genai.evaluate()` with different parameters.

### Wrong predict_fn Signature

**Error/Symptoms**: `TypeError` about unexpected arguments, or predict_fn receives wrong data

**WRONG:**
```python
# predict_fn receives **unpacked inputs, not a dict
def my_app(inputs):  # Receives dict
    query = inputs["query"]
    return {"response": "..."}
```

**CORRECT:**
```python
# inputs are unpacked as kwargs
def my_app(query, context=None):  # Receives individual keys
    return {"response": f"Answer to {query}"}

# If inputs = {"query": "What is X?", "context": "..."}
# Then my_app is called as: my_app(query="What is X?", context="...")
```

**Why**: `mlflow.genai.evaluate()` unpacks the `inputs` dict as keyword arguments to your predict_fn.

### Using Model Serving Endpoints for Development

**Error/Symptoms**: Slow iteration, hard to debug, no stack traces

**WRONG:**
```python
# Don't use model serving endpoints during development
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

**CORRECT:**
```python
# Import agent directly for fast iteration
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

**Why**:
- Local testing enables faster iteration (no deployment needed)
- Full stack traces for debugging
- No serving endpoint costs
- Direct access to agent internals

**When to use endpoints**: Only for production monitoring, load testing, or A/B testing deployed versions.

### Agent Import Errors

**Error**: Cannot import agent module or entry point

**Causes**:

1. Module not in Python path
2. Package not installed
3. Wrong module name
4. Virtual environment issue

**Solutions**:

1. Install package: `pip install -e .` from project root
2. Verify module name: Check actual file/folder structure
3. Check virtual environment: `which python`
4. Try absolute import: `from project.agent import run_agent`
5. Add to PYTHONPATH: `export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"`

### Trace Collection Incomplete

**Symptoms**: Some queries succeed, others fail

**Causes**:

1. Agent errors on certain queries
2. Timeout issues
3. LLM rate limits
4. Resource constraints

**Solutions**:

1. Review error messages in output
2. Test failing queries individually
3. Add timeout handling:

   ```python
   try:
       response = run_agent(query, timeout=60)
   except TimeoutError:
       print("Query timed out")
   ```

4. Add retry logic for rate limits:

   ```python
   import time

   for attempt in range(3):
       try:
           response = run_agent(query)
           break
       except RateLimitError:
           time.sleep(2**attempt)
   ```

5. Check agent logs for specific errors

### LLM Provider Configuration Issues

**Error**: API key not found, invalid credentials, or authentication errors

**Causes**:

1. API keys not set
2. Wrong environment variables
3. Provider configuration missing

**Solutions**:

1. Set required API keys:

   ```bash
   export OPENAI_API_KEY="sk-..."
   export ANTHROPIC_API_KEY="sk-ant-..."
   ```

2. Check provider configuration in agent code

3. Verify credentials are valid

4. Check rate limits and quotas

## Scorer Issues

### Wrong Scorer Decorator Usage

**Error/Symptoms**: Scorer not recognized, or function not treated as a scorer

**WRONG:**
```python
# Missing @scorer decorator
def my_scorer(outputs):
    return True
```

**CORRECT:**
```python
from mlflow.genai.scorers import scorer

@scorer
def my_scorer(outputs):
    return True
```

**Why**: The `@scorer` decorator is required for MLflow to recognize and use your function as a scorer.

### Wrong Feedback Return

**Error/Symptoms**: `TypeError`, serialization errors, or scorer results not recorded

**WRONG:**
```python
@scorer
def bad_scorer(outputs):
    # Can't return dict
    return {"score": 0.5, "reason": "..."}

    # Can't return tuple
    return (True, "rationale")
```

**CORRECT:**
```python
from mlflow.entities import Feedback

@scorer
def good_scorer(outputs):
    # Return primitive
    return True
    return 0.85
    return "yes"

    # Return Feedback object
    return Feedback(
        value=True,
        rationale="Explanation"
    )

    # Return list of Feedbacks
    return [
        Feedback(name="metric_1", value=True),
        Feedback(name="metric_2", value=0.9)
    ]
```

**Why**: Scorers must return primitives (bool, float, str) or Feedback objects. Dicts and tuples are not supported.

### Wrong Guidelines Scorer Setup

**Error/Symptoms**: `TypeError` about missing required argument, or scorer doesn't work

**WRONG:**
```python
# Missing 'name' parameter
scorer = Guidelines(guidelines="Must be professional")
```

**CORRECT:**
```python
scorer = Guidelines(
    name="professional_tone",  # REQUIRED
    guidelines="The response must be professional"  # REQUIRED
)
```

**Why**: `Guidelines` requires both `name` and `guidelines` parameters.

### Wrong Custom Scorer Imports

**Error/Symptoms**: Serialization fails when registering scorer for production monitoring

**WRONG:**
```python
# External import at module level - fails for production monitoring
import my_custom_library

@scorer
def production_scorer(outputs):
    return my_custom_library.process(outputs)
```

**CORRECT:**
```python
# Import inside function for serialization
@scorer
def production_scorer(outputs):
    import json  # Import inside for production monitoring
    return len(json.dumps(outputs)) > 100
```

**Why**: Production monitoring scorers are serialized. External imports at module level break serialization. Put imports inside the function.

### Wrong Multiple Feedback Names

**Error/Symptoms**: Feedback values overwrite each other, missing metrics in results

**WRONG:**
```python
@scorer
def bad_multi_scorer(outputs):
    # Feedbacks will conflict - no unique names
    return [
        Feedback(value=True),
        Feedback(value=0.8)
    ]
```

**CORRECT:**
```python
@scorer
def good_multi_scorer(outputs):
    # Each has unique name
    return [
        Feedback(name="check_1", value=True),
        Feedback(name="check_2", value=0.8)
    ]
```

**Why**: When returning multiple Feedbacks, each must have a unique `name` to avoid conflicts.

### Wrong Guidelines Context Reference

**Error/Symptoms**: Guidelines don't see your data, or judge evaluates wrong content

**WRONG:**
```python
# Guidelines use 'request' and 'response', not custom keys
Guidelines(
    name="check",
    guidelines="The output must address the query"  # 'output' and 'query' not available
)
```

**CORRECT:**
```python
# These are auto-extracted
Guidelines(
    name="check",
    guidelines="The response must address the request"
)
```

**Why**: Guidelines scorers automatically extract `request` (input) and `response` (output) from traces. Use these variable names in your guidelines text.

### Wrong Custom Judge Model Format

**Error/Symptoms**: Model not found, or wrong LLM used for judging

**WRONG:**
```python
# Missing provider prefix
Guidelines(name="test", guidelines="...", model="gpt-4o")

# Wrong separator
Guidelines(name="test", guidelines="...", model="databricks:gpt-4o")
```

**CORRECT:**
```python
# Use :/ separator
Guidelines(name="test", guidelines="...", model="databricks:/my-endpoint")
Guidelines(name="test", guidelines="...", model="openai:/gpt-4o")
```

**Why**: Model specification requires the format `provider:/model-name` with `:/` as the separator.

### Wrong Aggregation Values

**Error/Symptoms**: `ValueError` about invalid aggregation, or aggregations silently ignored

**WRONG:**
```python
# p50, p99, sum are not valid
@scorer(aggregations=["mean", "p50", "p99", "sum"])
def my_scorer(outputs) -> float:
    return 0.5
```

**CORRECT:**
```python
# Only these 6 are valid
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

### Built-in Scorer Not Working

**Symptoms**: Built-in scorer errors or returns unexpected or null results

**Causes**:

1. Trace structure doesn't match scorer assumptions
2. Required fields missing
3. Scorer expects ground truth but dataset doesn't have it
4. MLflow version incompatibility

**Solutions**:

1. Read scorer documentation for requirements:

   - Required trace fields
   - Expected structure
   - Ground truth needs

2. Verify trace has expected fields/structure

3. Check dataset has `expectations` if scorer needs ground truth

4. Consider custom scorer if built-in doesn't match your structure

5. Test with verbose output to see what scorer received

#### Correctness Scorer Requires Expectations

**WRONG:**
```python
# Correctness requires expected_facts or expected_response
eval_data = [
    {"inputs": {"query": "What is X?"}}
]
results = mlflow.genai.evaluate(
    data=eval_data,
    predict_fn=my_app,
    scorers=[Correctness()]  # Will fail - no ground truth!
)
```

**CORRECT:**
```python
eval_data = [
    {
        "inputs": {"query": "What is X?"},
        "expectations": {
            "expected_facts": ["X is a platform", "X is open-source"]
        }
    }
]
```

**Why**: `Correctness` scorer compares agent output to expected facts/response. Without expectations, it has nothing to compare against.

#### RetrievalGroundedness Requires RETRIEVER Span

**WRONG:**
```python
# App has no RETRIEVER span type
@mlflow.trace
def my_rag_app(query):
    docs = get_documents(query)  # Not marked as retriever
    return generate_response(docs, query)

# RetrievalGroundedness will fail - can't find retriever spans
```

**CORRECT:**
```python
# Use span_type="RETRIEVER"
@mlflow.trace(span_type="RETRIEVER")
def retrieve_documents(query):
    return [doc1, doc2]

@mlflow.trace
def my_rag_app(query):
    docs = retrieve_documents(query)  # Now has RETRIEVER span
    return generate_response(docs, query)
```

**Why**: `RetrievalGroundedness` scorer looks for spans with type `RETRIEVER` to find retrieved documents. Without proper span typing, it can't locate the retrieval step.

### Scorer Returns Null

**Symptoms**: Scorer output is null, empty, or missing

**Causes**:

1. Scorer instructions unclear
2. Required inputs missing from trace
3. Trace structure doesn't match expectations
4. LLM error or timeout

**Solutions**:

1. Test scorer on single trace:

   ```bash
   uv run mlflow traces evaluate \
     --scorers MyScorer \
     --trace-ids <single_trace> \
     --output json
   ```

2. Review scorer definition and instructions

3. Check trace has required fields:

   ```python
   trace = client.get_trace(trace_id)
   print(trace.data.spans)  # Verify structure
   ```

4. Simplify scorer instructions and test again

5. Add error handling in scorer (if using programmatic scorer)

### High Failure Rate

**Symptoms**: Most traces fail scorer evaluation

**Causes**:

1. Scorer too strict
2. Agent actually has quality issues
3. Scorer misunderstands requirements
4. Instructions ambiguous

**Solutions**:

1. Manually review failing traces - do they actually fail the criterion?

2. Test on known good examples:

   ```bash
   # Test on trace you know should pass
   uv run mlflow traces evaluate \
     --scorers MyScorer \
     --trace-ids <good_trace>
   ```

3. Refine scorer instructions for clarity

4. Consider adjusting criteria if too strict

5. Add examples to scorer instructions

### Scorer Registration Fails

**Error**: Error during `mlflow scorers register-llm-judge`

**Causes**:

1. Invalid scorer name
2. Missing required parameters
3. Syntax error in instructions
4. Permissions issue

**Solutions**:

1. Check scorer name is valid identifier (no spaces, special chars)

2. Verify all required parameters provided:

   ```bash
   uv run mlflow scorers register-llm-judge \
     --name "MyScorer" \
     --definition "..." \
     --instructions "..." \
     --variables query,response \
     --output pass/fail
   ```

3. Check instructions for syntax errors (especially quotes)

4. Try programmatic registration with make_judge() for better error messages

---

**For detailed guidance on each phase**, see the respective reference files:

- `references/tracing-integration.md` - Tracing setup
- `references/dataset-preparation.md` - Dataset creation
- `references/scorers.md` - Scorer design and testing

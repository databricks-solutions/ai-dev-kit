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
- [Wrong Trace Ingestion Setup](#-wrong-trace-ingestion-setup)
- [Wrong Trace Destination Format](#-wrong-trace-destination-format)
- [Wrong MLflow Version for Trace Ingestion](#-wrong-mlflow-version-for-trace-ingestion)
- [Wrong Linking UC Schema Without SQL Warehouse](#-wrong-linking-uc-schema-without-sql-warehouse)
- [Wrong Label Schema Name — Alignment Will Fail](#-wrong-label-schema-name--alignment-will-fail)
- [Wrong Aligned Judge Score Interpretation](#-wrong-aligned-judge-score-interpretation)
- [Wrong MemAlign Embedding Model — Token Costs](#-wrong-memalign-embedding-model--token-costs)
- [Wrong MemAlign Episodic Memory — Lazy Loading](#-wrong-memalign-episodic-memory--lazy-loading)
- [Wrong GEPA Optimization Dataset — Missing expectations](#-wrong-gepa-optimization-dataset--missing-expectations)
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

## ❌ WRONG Trace Ingestion Setup

### WRONG: Using ALL_PRIVILEGES instead of explicit grants
```sql
-- ❌ WRONG - ALL_PRIVILEGES does NOT include required permissions
GRANT ALL_PRIVILEGES ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_spans
  TO `user@company.com`;
```

### ✅ CORRECT: Grant explicit MODIFY and SELECT
```sql
-- ✅ CORRECT - Explicit MODIFY and SELECT required
GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_spans
  TO `user@company.com`;
GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_logs
  TO `user@company.com`;
GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_metrics
  TO `user@company.com`;
```

---

## ❌ WRONG Trace Destination Format

### WRONG: Wrong format for environment variable
```python
# ❌ WRONG - Missing schema or wrong separator
os.environ["MLFLOW_TRACING_DESTINATION"] = "my_catalog"
os.environ["MLFLOW_TRACING_DESTINATION"] = "my_catalog/my_schema"
```

### ✅ CORRECT: Use catalog.schema format
```python
# ✅ CORRECT - Dot-separated catalog.schema
os.environ["MLFLOW_TRACING_DESTINATION"] = "my_catalog.my_schema"
```

---

## ❌ WRONG MLflow Version for Trace Ingestion

### WRONG: Using MLflow < 3.9.0 for UC trace ingestion
```bash
# ❌ WRONG - Trace ingestion requires 3.9.0+
pip install mlflow[databricks]>=3.1.0
```

### ✅ CORRECT: Use MLflow 3.9.0+ for UC traces
```bash
# ✅ CORRECT
pip install "mlflow[databricks]>=3.9.0" --upgrade --force-reinstall
```

---

## ❌ WRONG Linking UC Schema Without SQL Warehouse

### WRONG: Missing SQL warehouse configuration
```python
# ❌ WRONG - No SQL warehouse configured
mlflow.set_tracking_uri("databricks")
# Missing: os.environ["MLFLOW_TRACING_SQL_WAREHOUSE_ID"] = "..."
set_experiment_trace_location(location=UCSchemaLocation(...), ...)
```

### ✅ CORRECT: Set SQL warehouse before linking
```python
# ✅ CORRECT - Set warehouse ID first
mlflow.set_tracking_uri("databricks")
os.environ["MLFLOW_TRACING_SQL_WAREHOUSE_ID"] = "<SQL_WAREHOUSE_ID>"
set_experiment_trace_location(location=UCSchemaLocation(...), ...)
```

---

## ❌ WRONG Label Schema Name — Alignment Will Fail

### WRONG: Label schema name does not match the judge name used in evaluate()
```python
# ❌ WRONG - Judge name and label schema name don't match
# Judge is registered as "domain_quality_base" in evaluate()
domain_quality_judge = make_judge(name="domain_quality_base", ...)
registered_base_judge = domain_quality_judge.register(experiment_id=EXPERIMENT_ID)

# But label schema uses a different name
feedback_schema = label_schemas.create_label_schema(
    name="domain_quality_rating",    # ❌ Does not match judge name
    type="feedback",
    ...
)
# align() will not be able to pair SME feedback with LLM judge scores
```

### ✅ CORRECT: Label schema name matches the judge name exactly
```python
# ✅ CORRECT - Judge name and label schema name are identical
JUDGE_NAME = "domain_quality_base"

domain_quality_judge = make_judge(name=JUDGE_NAME, ...)
registered_base_judge = domain_quality_judge.register(experiment_id=EXPERIMENT_ID)

feedback_schema = label_schemas.create_label_schema(
    name=JUDGE_NAME,                 # ✅ Matches judge name exactly
    type="feedback",
    ...
)
```

**Why?** The `align()` function pairs SME feedback with LLM judge scores by matching the label schema name to the judge name on the same traces. If the names differ, `align()` cannot find the corresponding score pairs and alignment will fail or produce incorrect results.

---

## ❌ WRONG Aligned Judge Score Interpretation

### WRONG: Assuming a lower aligned judge score means the agent got worse
```python
# ❌ WRONG interpretation - panicking because aligned judge gives lower scores
# Unaligned judge: 4.2/5.0 average
# Aligned judge:   3.1/5.0 average
# "The agent regressed!" — No, the judge got more accurate.
```

### ✅ CORRECT: Understanding that a lower aligned score reflects more accurate evaluation
```python
# ✅ CORRECT interpretation
# The aligned judge now evaluates with domain-expert standards rather than generic best practices.
# A lower score from a more accurate judge is a better signal than an inflated score from
# a judge that doesn't understand your domain. The unaligned judge was underspecified.
# Use optimize_prompts() with the aligned judge to improve the agent against this standard.
```

**Why?** An unaligned judge evaluates against generic best practices and often gives inflated scores. Once aligned with SME feedback, the judge applies domain-specific criteria that are harder to satisfy. The lower score is not a regression in agent quality; it is a more honest assessment. The optimization phase (`optimize_prompts()`) will then improve the agent against this more accurate standard.

---

## ❌ WRONG MemAlign Embedding Model — Token Costs

### WRONG: Using the default embedding model without awareness of cost
```python
# ❌ COSTLY - Default embedding model may be expensive for large trace sets
optimizer = MemAlignOptimizer(
    reflection_lm=REFLECTION_MODEL,
    retrieval_k=5,
    # No embedding_model specified → defaults to "openai/text-embedding-3-small"
)
```

### ✅ CORRECT: Use a Databricks-hosted embedding model or size your trace set accordingly
```python
# ✅ CORRECT - Use a hosted model to control costs; scope trace set to labeled traces only
optimizer = MemAlignOptimizer(
    reflection_lm=REFLECTION_MODEL,
    retrieval_k=5,
    embedding_model="databricks:/databricks-gte-large-en",
)

# ✅ ALSO CORRECT - Filter to only labeled/tagged traces, not all experiment traces
traces = mlflow.search_traces(
    locations=[EXPERIMENT_ID],
    filter_string="tag.eval = 'complete'",  # Scope to relevant traces only
    return_type="list",
)
aligned_judge = base_judge.align(traces=traces, optimizer=optimizer)
```

**Why?** MemAlign embeds every trace for retrieval (`retrieval_k` nearest neighbors per evaluation). Large trace sets with an expensive embedding model multiply quickly. Databricks-hosted models (`databricks:/databricks-gte-large-en`) keep costs on-platform.

---

## ❌ WRONG MemAlign Episodic Memory — Lazy Loading

### WRONG: Expecting episodic memory to be populated immediately after get_scorer()
```python
# ❌ WRONG - Episodic memory appears empty, looks like alignment didn't work
retrieved_judge = get_scorer(name="domain_quality_base", experiment_id=EXPERIMENT_ID)
print(retrieved_judge._episodic_memory)  # Prints: [] — misleading!
print(retrieved_judge._semantic_memory)  # Prints: [] — also empty!
```

### ✅ CORRECT: Episodic memory is lazily loaded — use the judge first, then inspect
```python
# ✅ CORRECT - Semantic guidelines ARE loaded; episodic memory loads on first use
retrieved_judge = get_scorer(name="domain_quality_base", experiment_id=EXPERIMENT_ID)

# The instructions field already contains the distilled guidelines — inspect this instead
print(retrieved_judge.instructions)  # ✅ Shows full aligned instructions with guidelines

# To verify episodic memory, run the judge on a sample first, then inspect
# Memory loads lazily when the judge retrieves similar examples during scoring
```

**Why?** MemAlign's episodic memory (stored examples) is loaded on-demand when the judge needs to retrieve similar examples at scoring time. The `_episodic_memory` list is empty on deserialization. The aligned `instructions` field (which includes distilled semantic guidelines) is the reliable thing to inspect after `get_scorer()`.

---

## ❌ WRONG GEPA Optimization Dataset — Missing expectations

### WRONG: Using eval-style dataset (inputs only) for optimize_prompts()
```python
# ❌ WRONG - GEPA requires expectations; optimization will fail or produce poor results
optimization_dataset = [
    {"inputs": {"input": [{"role": "user", "content": "How does the offense attack the blitz?"}]}},
    {"inputs": {"input": [{"role": "user", "content": "What are 3rd down tendencies?"}]}},
]

result = mlflow.genai.optimize_prompts(
    predict_fn=predict_fn,
    train_data=optimization_dataset,   # ❌ Missing expectations
    prompt_uris=[prompt.uri],
    optimizer=GepaPromptOptimizer(...),
    scorers=[aligned_judge],
)
```

### ✅ CORRECT: Include expectations in every optimization dataset record
```python
# ✅ CORRECT - Each record must have both inputs AND expectations
optimization_dataset = [
    {
        "inputs": {
            "input": [{"role": "user", "content": "How does the offense attack the blitz?"}]
        },
        "expectations": {
            "expected_response": (
                "The agent should analyze blitz performance metrics, compare success "
                "rates across pressure packages, and provide concrete tactical recommendations."
            )
        }
    },
    {
        "inputs": {
            "input": [{"role": "user", "content": "What are 3rd down tendencies?"}]
        },
        "expectations": {
            "expected_response": (
                "The agent should call the appropriate tool with down=3 parameters, "
                "summarize the play distribution, and give defensive recommendations."
            )
        }
    },
]
```

**Why?** GEPA uses the `expectations` field during reflection — it compares the agent's output against the expected behavior to generate targeted prompt improvement suggestions. Without `expectations`, GEPA cannot reason about *why* the current prompt is underperforming. This is the most common cause of poor optimization results.

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
- [ ] UC trace ingestion uses `mlflow[databricks]>=3.9.0`
- [ ] UC tables have explicit MODIFY + SELECT grants (not ALL_PRIVILEGES)
- [ ] `MLFLOW_TRACING_SQL_WAREHOUSE_ID` set before linking UC schema
- [ ] `MLFLOW_TRACING_DESTINATION` uses `catalog.schema` format (dot-separated)
- [ ] Production monitoring scorers are both registered AND started
- [ ] MemAlign `embedding_model` can be explicitly set (don't rely on default for large trace sets)
- [ ] After `get_scorer()` for a MemAlign judge, inspect `.instructions` not `._episodic_memory` as episodic memory is lazily loaded
- [ ] GEPA `train_data` has both `inputs` AND `expectations` per record
- [ ] Label schema `name` matches the judge `name` used in `evaluate()` (required for `align()` to pair scores)
- [ ] Aligned judge scores may be lower than unaligned — this is expected if the judge is now more accurate
- [ ] MemAlign is scorer-agnostic (works with any `feedback_value_type` — float, bool, categorical)

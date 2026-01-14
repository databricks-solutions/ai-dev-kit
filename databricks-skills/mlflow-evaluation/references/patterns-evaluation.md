# MLflow 3 Evaluation Patterns

Working patterns for running evaluations, comparing results, and iterating on quality.

---

## Pattern 0: Local Agent Testing First (CRITICAL)

**Always test agents locally by importing them directly, NOT via model serving endpoints.**

This enables faster iteration, easier debugging, and no deployment overhead.

```python
import mlflow
from mlflow.genai.scorers import Guidelines, Safety

# ✅ CORRECT: Import agent directly from module
from plan_execute_agent import AGENT  # Or your agent module

# Enable auto-tracing
mlflow.openai.autolog()
mlflow.set_tracking_uri("databricks")
mlflow.set_experiment("/Shared/my-evaluation-experiment")

# Create evaluation data
eval_data = [
    {"inputs": {"messages": [{"role": "user", "content": "What is MLflow?"}]}},
    {"inputs": {"messages": [{"role": "user", "content": "How do I track experiments?"}]}},
]

# Define predict function using local agent
def predict_fn(messages):
    """Wrapper that calls the local agent directly."""
    result = AGENT.predict({"messages": messages})
    # Extract response from agent output format
    if isinstance(result, dict) and "messages" in result:
        # ResponsesAgent format - get last assistant message
        for msg in reversed(result["messages"]):
            if msg.get("role") == "assistant":
                return {"response": msg.get("content", "")}
    return {"response": str(result)}

# Run evaluation with local agent
results = mlflow.genai.evaluate(
    data=eval_data,
    predict_fn=predict_fn,
    scorers=[
        Safety(),
        Guidelines(name="helpful", guidelines="Response must be helpful and informative"),
    ]
)

print(f"Run ID: {results.run_id}")
print(f"Metrics: {results.metrics}")
```

### Why Local Testing First?

| Aspect | Local Agent | Model Serving Endpoint |
|--------|-------------|------------------------|
| Iteration speed | Fast (no deploy) | Slow (deploy each change) |
| Debugging | Full stack traces | Limited visibility |
| Cost | No serving costs | Endpoint compute costs |
| Dependencies | Direct access | Network latency |
| Use case | Development, testing | Production monitoring |

### When to Use Model Serving Endpoints

Only use deployed endpoints for:
- Production monitoring and quality tracking
- Load testing deployed models
- A/B testing between deployed versions
- External integration testing

---

## Pattern 1: Basic Evaluation Run

```python
import mlflow
from mlflow.genai.scorers import Guidelines, Safety

# Enable auto-tracing
mlflow.openai.autolog()

# Set experiment
mlflow.set_tracking_uri("databricks")
mlflow.set_experiment("/Shared/my-evaluation-experiment")

# Define your app
@mlflow.trace
def my_app(query: str) -> dict:
    # Your application logic
    response = call_llm(query)
    return {"response": response}

# Create evaluation data
eval_data = [
    {"inputs": {"query": "What is MLflow?"}},
    {"inputs": {"query": "How do I track experiments?"}},
    {"inputs": {"query": "What are best practices?"}},
]

# Define scorers
scorers = [
    Safety(),
    Guidelines(name="helpful", guidelines="Response must be helpful and informative"),
    Guidelines(name="concise", guidelines="Response must be under 200 words"),
]

# Run evaluation
results = mlflow.genai.evaluate(
    data=eval_data,
    predict_fn=my_app,
    scorers=scorers
)

print(f"Run ID: {results.run_id}")
print(f"Metrics: {results.metrics}")
```

---

## Pattern 2: Evaluation with Pre-computed Outputs

Use when you already have outputs (e.g., from production logs).

```python
# Data with pre-computed outputs - no predict_fn needed
eval_data = [
    {
        "inputs": {"query": "What is X?"},
        "outputs": {"response": "X is a platform for..."}
    },
    {
        "inputs": {"query": "How to use Y?"},
        "outputs": {"response": "To use Y, follow these steps..."}
    }
]

# Run evaluation without predict_fn
results = mlflow.genai.evaluate(
    data=eval_data,
    scorers=[Guidelines(name="quality", guidelines="Response must be accurate")]
)
```

---

## Pattern 3: Evaluation with Ground Truth

```python
from mlflow.genai.scorers import Correctness, Guidelines

# Data with expectations for correctness checking
eval_data = [
    {
        "inputs": {"query": "What is the capital of France?"},
        "expectations": {
            "expected_facts": ["Paris is the capital of France"]
        }
    },
    {
        "inputs": {"query": "What are MLflow's components?"},
        "expectations": {
            "expected_facts": [
                "Tracking",
                "Projects", 
                "Models",
                "Registry"
            ]
        }
    }
]

results = mlflow.genai.evaluate(
    data=eval_data,
    predict_fn=my_app,
    scorers=[
        Correctness(),  # Uses expected_facts
        Guidelines(name="format", guidelines="Must list items clearly")
    ]
)
```

---

## Pattern 4: Named Evaluation Run for Comparison

```python
import mlflow

# Version 1 evaluation
with mlflow.start_run(run_name="prompt_v1"):
    results_v1 = mlflow.genai.evaluate(
        data=eval_data,
        predict_fn=app_v1,
        scorers=scorers
    )

# Version 2 evaluation  
with mlflow.start_run(run_name="prompt_v2"):
    results_v2 = mlflow.genai.evaluate(
        data=eval_data,
        predict_fn=app_v2,
        scorers=scorers
    )

# Compare metrics
print("V1 Metrics:", results_v1.metrics)
print("V2 Metrics:", results_v2.metrics)
```

---

## Pattern 5: Analyze Evaluation Results

```python
import mlflow
import pandas as pd

# After running evaluation
results = mlflow.genai.evaluate(data=eval_data, predict_fn=my_app, scorers=scorers)

# Get detailed traces
traces_df = mlflow.search_traces(run_id=results.run_id)

# Access per-row results
for idx, row in traces_df.iterrows():
    print(f"\n--- Row {idx} ---")
    print(f"Input: {row['request']}")
    print(f"Output: {row['response']}")
    
    # Access assessments (scorer results)
    for assessment in row['assessments']:
        name = assessment['assessment_name']
        value = assessment['feedback']['value']
        rationale = assessment.get('rationale', 'N/A')
        print(f"  {name}: {value}")

# Filter to failures
def has_failures(assessments):
    return any(
        a['feedback']['value'] in ['no', False, 0] 
        for a in assessments
    )

failures = traces_df[traces_df['assessments'].apply(has_failures)]
print(f"\nFound {len(failures)} rows with failures")
```

---

## Pattern 6: Compare Two Evaluation Runs

```python
import mlflow
import pandas as pd

# Get runs
run_v1 = mlflow.search_runs(filter_string=f"run_id = '{results_v1.run_id}'")
run_v2 = mlflow.search_runs(filter_string=f"run_id = '{results_v2.run_id}'")

# Extract metrics (they end with /mean)
metric_cols = [col for col in run_v1.columns 
               if col.startswith('metrics.') and col.endswith('/mean')]

# Build comparison
comparison = []
for metric in metric_cols:
    metric_name = metric.replace('metrics.', '').replace('/mean', '')
    v1_val = run_v1[metric].iloc[0]
    v2_val = run_v2[metric].iloc[0]
    improvement = v2_val - v1_val
    
    comparison.append({
        'Metric': metric_name,
        'V1': f"{v1_val:.3f}",
        'V2': f"{v2_val:.3f}",
        'Change': f"{improvement:+.3f}",
        'Improved': '✓' if improvement >= 0 else '✗'
    })

comparison_df = pd.DataFrame(comparison)
print(comparison_df.to_string(index=False))
```

---

## Pattern 7: Find Regressions Between Versions

```python
import mlflow

# Get traces from both runs
traces_v1 = mlflow.search_traces(run_id=results_v1.run_id)
traces_v2 = mlflow.search_traces(run_id=results_v2.run_id)

# Create merge key from inputs
traces_v1['merge_key'] = traces_v1['request'].apply(lambda x: str(x))
traces_v2['merge_key'] = traces_v2['request'].apply(lambda x: str(x))

# Merge on inputs
merged = traces_v1.merge(traces_v2, on='merge_key', suffixes=('_v1', '_v2'))

# Find regressions (v1 passed, v2 failed)
regressions = []
for idx, row in merged.iterrows():
    v1_assessments = {a['assessment_name']: a for a in row['assessments_v1']}
    v2_assessments = {a['assessment_name']: a for a in row['assessments_v2']}
    
    for scorer_name in v1_assessments:
        v1_val = v1_assessments[scorer_name]['feedback']['value']
        v2_val = v2_assessments.get(scorer_name, {}).get('feedback', {}).get('value')
        
        # Check for regression (yes->no or True->False)
        if v1_val in ['yes', True] and v2_val in ['no', False]:
            regressions.append({
                'input': row['request_v1'],
                'metric': scorer_name,
                'v1_output': row['response_v1'],
                'v2_output': row['response_v2'],
                'v1_rationale': v1_assessments[scorer_name].get('rationale'),
                'v2_rationale': v2_assessments[scorer_name].get('rationale')
            })

print(f"Found {len(regressions)} regressions")
for r in regressions[:5]:  # Show first 5
    print(f"\nRegression in '{r['metric']}':")
    print(f"  Input: {r['input']}")
    print(f"  V2 Rationale: {r['v2_rationale']}")
```

---

## Pattern 8: Iterative Improvement Loop

```python
import mlflow
from mlflow.genai.scorers import Guidelines

# Define quality bar
QUALITY_THRESHOLD = 0.9  # 90% pass rate

def evaluate_and_improve(app_fn, eval_data, scorers, max_iterations=5):
    """Iteratively improve until quality threshold is met."""
    
    for iteration in range(max_iterations):
        print(f"\n=== Iteration {iteration + 1} ===")
        
        with mlflow.start_run(run_name=f"iteration_{iteration + 1}"):
            results = mlflow.genai.evaluate(
                data=eval_data,
                predict_fn=app_fn,
                scorers=scorers
            )
        
        # Calculate overall pass rate
        pass_rates = {}
        for metric, value in results.metrics.items():
            if metric.endswith('/mean'):
                metric_name = metric.replace('/mean', '')
                pass_rates[metric_name] = value
        
        avg_pass_rate = sum(pass_rates.values()) / len(pass_rates)
        print(f"Average pass rate: {avg_pass_rate:.2%}")
        
        if avg_pass_rate >= QUALITY_THRESHOLD:
            print(f"✓ Quality threshold {QUALITY_THRESHOLD:.0%} met!")
            return results
        
        # Find worst performing metric
        worst_metric = min(pass_rates, key=pass_rates.get)
        print(f"Worst metric: {worst_metric} ({pass_rates[worst_metric]:.2%})")
        
        # Analyze failures for that metric
        traces = mlflow.search_traces(run_id=results.run_id)
        failures = analyze_failures(traces, worst_metric)
        
        print(f"Sample failures for {worst_metric}:")
        for f in failures[:3]:
            print(f"  - Input: {f['input'][:50]}...")
            print(f"    Rationale: {f['rationale']}")
        
        # Here you would update app_fn based on failures
        # This could be manual or automated prompt refinement
        print("\n[Update your app based on failures before next iteration]")
    
    print(f"✗ Did not meet threshold after {max_iterations} iterations")
    return results

def analyze_failures(traces, metric_name):
    """Extract failures for a specific metric."""
    failures = []
    for _, row in traces.iterrows():
        for assessment in row['assessments']:
            if (assessment['assessment_name'] == metric_name and 
                assessment['feedback']['value'] in ['no', False]):
                failures.append({
                    'input': row['request'],
                    'output': row['response'],
                    'rationale': assessment.get('rationale', 'N/A')
                })
    return failures
```

---

## Pattern 9: Evaluation from Production Traces

```python
import mlflow
import time

# Search for recent production traces
one_day_ago = int((time.time() - 86400) * 1000)  # 24 hours in ms

prod_traces = mlflow.search_traces(
    filter_string=f"""
        attributes.status = 'OK' AND 
        attributes.timestamp_ms > {one_day_ago} AND
        tags.environment = 'production'
    """,
    order_by=["attributes.timestamp_ms DESC"],
    max_results=100
)

print(f"Found {len(prod_traces)} production traces")

# Convert to evaluation format
eval_data = []
for _, trace in prod_traces.iterrows():
    eval_data.append({
        "inputs": trace['request'],
        "outputs": trace['response']
    })

# Run evaluation on production data
results = mlflow.genai.evaluate(
    data=eval_data,
    scorers=[
        Safety(),
        Guidelines(name="quality", guidelines="Response must be helpful")
    ]
)
```

---

## Pattern 10: A/B Testing Two Prompts

```python
import mlflow
from mlflow.genai.scorers import Guidelines, Safety

# Two different system prompts
PROMPT_A = "You are a helpful assistant. Be concise."
PROMPT_B = "You are an expert assistant. Provide detailed, comprehensive answers."

def create_app(system_prompt):
    @mlflow.trace
    def app(query):
        response = client.chat.completions.create(
            model="databricks-claude-sonnet-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query}
            ]
        )
        return {"response": response.choices[0].message.content}
    return app

app_a = create_app(PROMPT_A)
app_b = create_app(PROMPT_B)

scorers = [
    Safety(),
    Guidelines(name="helpful", guidelines="Must be helpful"),
    Guidelines(name="accurate", guidelines="Must be accurate"),
    Guidelines(name="concise", guidelines="Must be under 100 words"),
]

# Run A/B test
with mlflow.start_run(run_name="prompt_a_concise"):
    results_a = mlflow.genai.evaluate(
        data=eval_data, predict_fn=app_a, scorers=scorers
    )

with mlflow.start_run(run_name="prompt_b_detailed"):
    results_b = mlflow.genai.evaluate(
        data=eval_data, predict_fn=app_b, scorers=scorers
    )

# Compare
print("Prompt A (Concise):", results_a.metrics)
print("Prompt B (Detailed):", results_b.metrics)
```

---

## Pattern 11: Evaluation with Parallelization

For large datasets or complex apps.

```python
import mlflow

# Configure parallelization via environment variable or run config
# Default is sequential; increase for faster evaluation

results = mlflow.genai.evaluate(
    data=large_eval_data,  # 1000+ records
    predict_fn=my_app,
    scorers=scorers,
    # Parallelization is handled internally
    # For complex agents, consider batching your data
)
```

---

## Pattern 12: Continuous Evaluation in CI/CD

```python
import mlflow
import sys

def run_ci_evaluation():
    """Run evaluation as part of CI/CD pipeline."""
    
    # Load test data
    eval_data = load_test_data()  # From file or test fixtures
    
    # Define quality gates
    QUALITY_GATES = {
        "safety": 1.0,           # 100% must pass
        "helpful": 0.9,          # 90% must pass
        "concise": 0.8,          # 80% must pass
    }
    
    # Run evaluation
    results = mlflow.genai.evaluate(
        data=eval_data,
        predict_fn=my_app,
        scorers=[
            Safety(),
            Guidelines(name="helpful", guidelines="Must be helpful"),
            Guidelines(name="concise", guidelines="Must be concise"),
        ]
    )
    
    # Check quality gates
    failures = []
    for metric, threshold in QUALITY_GATES.items():
        actual = results.metrics.get(f"{metric}/mean", 0)
        if actual < threshold:
            failures.append(f"{metric}: {actual:.2%} < {threshold:.2%}")
    
    if failures:
        print("❌ Quality gates failed:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("✅ All quality gates passed")
        sys.exit(0)

if __name__ == "__main__":
    run_ci_evaluation()
```

---

## Evaluation Best Practices

1. **Start Small**: Begin with 20-50 diverse test cases
2. **Cover Edge Cases**: Include adversarial, ambiguous, and out-of-scope inputs
3. **Use Multiple Scorers**: Combine safety, quality, and domain-specific checks
4. **Track Over Time**: Name runs for easy comparison
5. **Analyze Failures**: Don't just look at aggregate metrics
6. **Iterate**: Use failures to improve prompts/logic, then re-evaluate
7. **Version Your Data**: Use MLflow-managed datasets for reproducibility

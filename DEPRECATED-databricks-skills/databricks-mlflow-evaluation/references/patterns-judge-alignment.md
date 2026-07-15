# MLflow 3 Judge Alignment with MemAlign

Patterns for aligning LLM judges to domain expert preferences using MemAlign. An aligned judge is more accurate for evaluation runs, more meaningful for production monitoring, and a better guide for prompt optimization — but each of these uses is independent.

**Read `GOTCHAS.md` before implementing — especially the MemAlign sections.**

---

## When to Use Judge Alignment

Align a judge when:
- Built-in scorers don't capture domain-specific quality (e.g., "good" means expert-level tactical analysis)
- LLM judges disagree with human raters on the same examples
- You have domain experts who can rate a sample of agent outputs
- You want production monitoring that reflects actual expert standards

You do NOT need prompt optimization to benefit from aligned judges — a more accurate judge improves every evaluation run and monitoring setup you do afterward.

---

## Pattern 1: Design and Register the Base Judge

MemAlign is scorer-agnostic and works with any `feedback_value_type` (float, boolean, categorical). This example uses a Likert scale (1-5 float), but you can use whatever scoring scheme fits your domain.

```python
import mlflow
from mlflow.genai.judges import make_judge
from mlflow.genai import evaluate

mlflow.set_experiment(experiment_id=EXPERIMENT_ID)

# Define base judge using make_judge -- MemAlign works with any feedback type
# This example uses a Likert scale (1-5 float), but boolean or categorical also work
domain_quality_judge = make_judge(
    name="domain_quality_base",
    instructions=(
        "Evaluate if the response in {{ outputs }} appropriately analyzes the available data "
        "and provides an actionable recommendation to the question in {{ inputs }}. "
        "The response should be accurate, contextually relevant, and give a strategic advantage "
        "to the person making the request. "
        "Your grading criteria: "
        " 1: Completely unacceptable. Incorrect data interpretation or no recommendations. "
        " 2: Mostly unacceptable. Irrelevant or spurious feedback or weak recommendations with minimal strategic advantage. "
        " 3: Somewhat acceptable. Relevant feedback provided with some strategic advantage. "
        " 4: Mostly acceptable. Relevant feedback provided with strong strategic advantage. "
        " 5: Completely acceptable. Relevant feedback provided with excellent strategic advantage."
    ),
    feedback_value_type=float,   # Example uses a Likert scale; MemAlign works with any feedback type
    model=JUDGE_MODEL,
)

# Register to experiment — creates the persistent record used by align()
registered_base_judge = domain_quality_judge.register(experiment_id=EXPERIMENT_ID)
print(f"Registered base judge: {registered_base_judge.name}")
```

---

## Pattern 2: Run Evaluation and Tag Traces

Run evaluation to generate a set of traces that domain experts will review. Tag traces that were **successfully evaluated** in this `evaluate()` job (i.e., the agent produced a response and the judge scored it without errors).

```python
from mlflow.genai import evaluate

# Eval dataset: inputs only (no expectations needed at this stage)
eval_data = [
    {"inputs": {"input": [{"role": "user", "content": question}]}}
    for question in example_questions
]

results = evaluate(
    data=eval_data,
    predict_fn=lambda input: AGENT.predict({"input": input}),
    scorers=[domain_quality_judge],
)

# Tag traces that were successfully evaluated in this evaluate() job
# "OK" state means the agent responded AND the judge scored it without errors
ok_trace_ids = results.result_df.loc[results.result_df["state"] == "OK", "trace_id"]
for trace_id in ok_trace_ids:
    mlflow.set_trace_tag(trace_id=trace_id, key="eval", value="complete")

print(f"Tagged {len(ok_trace_ids)} successfully evaluated traces for labeling")
```

---

## Pattern 3: Build Eval Dataset and Create Labeling Session

Persist traces to a UC dataset and assign them to domain experts for review.

**CRITICAL: The label schema `name` MUST match the judge `name` used in the `evaluate()` job.** This is how `align()` pairs SME feedback with the corresponding LLM judge scores on the same traces. If these names do not match, alignment will fail or produce incorrect results.

```python
from mlflow.genai.datasets import create_dataset, get_dataset
from mlflow.genai import create_labeling_session, get_review_app
from mlflow.genai import label_schemas

# Build persistent dataset from tagged traces
try:
    eval_dataset = get_dataset(name=DATASET_NAME)
except Exception:
    eval_dataset = create_dataset(name=DATASET_NAME)

tagged_traces = mlflow.search_traces(
    locations=[EXPERIMENT_ID],
    filter_string="tag.eval = 'complete'",
    return_type="pandas",
)
# merge_records() expects 'inputs' and 'outputs' column names
if "inputs" not in tagged_traces.columns and "request" in tagged_traces.columns:
    tagged_traces = tagged_traces.rename(columns={"request": "inputs"})
if "outputs" not in tagged_traces.columns and "response" in tagged_traces.columns:
    tagged_traces = tagged_traces.rename(columns={"response": "outputs"})

eval_dataset = eval_dataset.merge_records(tagged_traces)

# CRITICAL: The label schema name MUST match the judge name used in evaluate()
# This is how align() pairs SME feedback with LLM judge scores on the same traces
LABEL_SCHEMA_NAME = "domain_quality_base"  # Must match the judge name exactly

feedback_schema = label_schemas.create_label_schema(
    name=LABEL_SCHEMA_NAME,               # Must match judge name from Pattern 1
    type="feedback",
    title=LABEL_SCHEMA_NAME,
    input=label_schemas.InputNumeric(min_value=1.0, max_value=5.0),
    instruction=(
        "Evaluate if the response appropriately analyzes the available data and provides "
        "an actionable recommendation for the question. The response should be accurate, "
        "contextually relevant, and give a strategic advantage to the person making the request. "
        "\n\n Your grading criteria should be: "
        "\n 1: Completely unacceptable. Incorrect data interpretation or no recommendations."
        "\n 2: Mostly unacceptable. Irrelevant or spurious feedback or weak recommendations with minimal strategic advantage."
        "\n 3: Somewhat acceptable. Relevant feedback provided with some strategic advantage."
        "\n 4: Mostly acceptable. Relevant feedback provided with strong strategic advantage."
        "\n 5: Completely acceptable. Relevant feedback provided with excellent strategic advantage."
    ),
    enable_comment=True,   # Allow SMEs to leave free-text rationale (used by MemAlign)
    overwrite=True,
)

# Optional: add a deployed agent to the Review App so SMEs can ask new questions
review_app = get_review_app(experiment_id=EXPERIMENT_ID)
review_app = review_app.add_agent(
    agent_name=MODEL_NAME,
    model_serving_endpoint=AGENT_ENDPOINT_NAME,
    overwrite=True,
)

# Create labeling session and attach the dataset
labeling_session = create_labeling_session(
    name=f"{LABELING_SESSION_NAME}_sme",
    assigned_users=ASSIGNED_USERS,
    label_schemas=[LABEL_SCHEMA_NAME],     # Must match judge name
)
labeling_session = labeling_session.add_dataset(dataset_name=DATASET_NAME)

print(f"Share with domain experts: {labeling_session.url}")
# Domain experts open this URL and rate each response using the 1-5 scale
```

---

## Pattern 4: Align Judge with MemAlign (Recommended)

After SMEs complete labeling, distill their feedback patterns into the judge's instructions.

Judge alignment supports multiple optimizers (e.g., SIMBA, custom optimizers), but this example uses **MemAlign**, which is the recommended approach. MemAlign is the fastest alignment method (seconds vs. minutes for alternatives), the most cost-effective, and supports **memory scaling** where quality continues to improve as feedback accumulates without re-optimization.

```python
from mlflow.genai.judges.optimizers import MemAlignOptimizer
from mlflow.genai.scorers import get_scorer

# Fetch the tagged traces (which now have SME labels attached)
traces_for_alignment = mlflow.search_traces(
    locations=[EXPERIMENT_ID],
    filter_string="tag.eval = 'complete'",
    return_type="list",   # align() requires list format
)
print(f"Aligning on {len(traces_for_alignment)} traces")

# Configure MemAlign optimizer
# Other optimizers are available (e.g., SIMBA), but MemAlign is recommended for its
# speed, cost efficiency, and ability to improve continuously as feedback accumulates
optimizer = MemAlignOptimizer(
    reflection_lm=REFLECTION_MODEL,                       # Model for guideline distillation
    retrieval_k=5,                                        # Examples to retrieve per evaluation
    embedding_model="databricks:/databricks-gte-large-en",
    # Defaults to "openai/text-embedding-3-small" if not set -- see GOTCHAS.md
)

# Load the registered base judge and run alignment
base_judge = get_scorer(name="domain_quality_base")
aligned_judge = base_judge.align(
    traces=traces_for_alignment,
    optimizer=optimizer,
)

# Inspect distilled semantic guidelines — these encode expert preferences
print("Distilled Guidelines from SME feedback:")
for i, guideline in enumerate(aligned_judge._semantic_memory, 1):
    print(f"  {i}. {guideline.guideline_text}")
    if guideline.source_trace_ids:
        print(f"     Derived from {len(guideline.source_trace_ids)} trace(s)")
```

---

## Pattern 5: Register the Aligned Judge

Persist the aligned judge to the experiment for later retrieval in evaluation or optimization runs.

```python
from mlflow.genai.scorers import ScorerSamplingConfig

# Option A: Update the existing judge record in-place (recommended for iterative alignment)
aligned_judge_registered = aligned_judge.update(
    experiment_id=EXPERIMENT_ID,
    sampling_config=ScorerSamplingConfig(sample_rate=0.0),
)
print(f"Updated judge: {aligned_judge_registered.name}")

# Option B: Register as a new named version (preserves the original for comparison)
from mlflow.genai.judges import make_judge

aligned_judge_v2 = make_judge(
    name="domain_quality_aligned_v1",
    instructions=aligned_judge.instructions,  # Includes distilled guidelines
    feedback_value_type=float,                # Match the original judge's feedback type
    model=JUDGE_MODEL,
)
aligned_judge_v2 = aligned_judge_v2.register(experiment_id=EXPERIMENT_ID)

# Retrieve in a later session
# NOTE: Episodic memory is lazily loaded — inspect .instructions, not ._episodic_memory
from mlflow.genai.scorers import get_scorer

retrieved_judge = get_scorer(name="domain_quality_base", experiment_id=EXPERIMENT_ID)
print(retrieved_judge.instructions[:500])  # Shows aligned instructions with guidelines
```

---

## Pattern 6: Re-evaluate with Aligned Judge

Run a fresh evaluation with the aligned judge. This gives a more accurate quality picture and establishes a baseline for prompt optimization if you choose to do that next.

**Important: The aligned judge score may be lower than the unaligned judge score. This is expected and correct.** It means the aligned judge is now evaluating with domain-expert standards rather than generic best practices. A lower score from a more accurate judge is a better signal than a higher score from a judge that doesn't understand your domain. The optimization phase (`optimize_prompts()`) will improve the agent against this more accurate standard.

```python
from mlflow.genai import evaluate
from mlflow.genai.scorers import get_scorer
from mlflow.genai.datasets import get_dataset

aligned_judge = get_scorer(name="domain_quality_base", experiment_id=EXPERIMENT_ID)

eval_dataset = get_dataset(name=DATASET_NAME)
df = eval_dataset.to_df()

eval_records = [
    {
        "inputs": {
            "input": [{"role": "user", "content": extract_user_message(row)}]
        }
    }
    for row in df["inputs"]
]

with mlflow.start_run(run_name="aligned_judge_baseline"):
    baseline_results = evaluate(
        data=eval_records,
        predict_fn=lambda input: AGENT.predict({"input": input}),
        scorers=[aligned_judge],
    )

print(f"Aligned judge baseline metrics: {baseline_results.metrics}")
# NOTE: If scores are lower than the unaligned judge, that is expected.
# The aligned judge is more accurate, not less generous.
```

---

## Using Aligned Judges Beyond Evaluation

Aligned judges are not just for one-time evaluation. They can be used for:

**Production monitoring:**
```python
from mlflow.genai.scorers import ScorerSamplingConfig

aligned_judge = get_scorer(name="domain_quality_base", experiment_id=EXPERIMENT_ID)
monitoring_judge = aligned_judge.start(
    sampling_config=ScorerSamplingConfig(sample_rate=0.1)  # Score 10% of production traffic
)
```

**Prompt optimization input (see `patterns-prompt-optimization.md`):**
```python
# Pass the aligned judge as the scorer in optimize_prompts()
result = mlflow.genai.optimize_prompts(
    predict_fn=predict_fn,
    train_data=optimization_dataset,
    prompt_uris=[prompt.uri],
    optimizer=GepaPromptOptimizer(reflection_model=REFLECTION_MODEL),
    scorers=[aligned_judge],   # ← aligned judge drives GEPA's reflection
)
```

**Regression detection across agent versions:**
```python
with mlflow.start_run(run_name="agent_v2"):
    v2_results = evaluate(data=eval_records, predict_fn=agent_v2, scorers=[aligned_judge])

# Metrics from aligned judge are more meaningful than unaligned LLM judge
```

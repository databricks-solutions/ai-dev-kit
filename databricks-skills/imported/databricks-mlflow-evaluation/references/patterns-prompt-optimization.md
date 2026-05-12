# MLflow 3 Prompt Optimization with GEPA

Patterns for automated prompt improvement using `optimize_prompts()` with the GEPA (Genetic-Pareto) optimizer. GEPA iteratively evolves a registered system prompt by evaluating candidates against a scorer, then promotes the best version.

**Using an aligned judge as the scorer is recommended.** An aligned judge encodes domain-expert preferences, giving GEPA a more accurate optimization signal than a generic LLM judge. See `patterns-judge-alignment.md` for the full alignment workflow.

For the full end-to-end loop (evaluate, label, align, optimize, promote), see `user-journeys.md` Journey 10. For details on the GEPA and MemAlign approaches, see the [Self-Optimizing Agent blog post](https://www.databricks.com/blog/self-optimizing-football-chatbot-guided-domain-experts-databricks).

**Read `GOTCHAS.md` before implementing -- especially the GEPA sections.**

---

## Pattern 1: Build Optimization Dataset (inputs + expectations required)

GEPA requires both `inputs` AND `expectations` in every record. This is different from the eval dataset which only needs `inputs`. The `expectations` field is what GEPA uses during reflection to reason about why the current prompt is underperforming.

```python
# optimization dataset must have both inputs AND expectations
optimization_dataset = [
    {
        "inputs": {
            "input": [{"role": "user", "content": "What are the tendencies on 3rd and short?"}]
        },
        "expectations": {
            "expected_response": (
                "The agent should identify key players and their 3rd-and-short involvement, "
                "provide relevant statistics, and give tactical recommendations. "
                "If data quality issues exist, they should be stated explicitly."
            )
        }
    },
    {
        "inputs": {
            "input": [{"role": "user", "content": "How does the offense perform against the blitz?"}]
        },
        "expectations": {
            "expected_response": (
                "The agent should analyze performance metrics vs. pressure, "
                "compare success across different blitz packages, "
                "and provide concrete defensive recommendations."
            )
        }
    },
    # Add 15-20 representative examples covering key use cases
]

# Persist to MLflow dataset
from mlflow.genai.datasets import create_dataset

optim_dataset = create_dataset(name=OPTIMIZATION_DATASET_NAME)
optim_dataset = optim_dataset.merge_records(optimization_dataset)
print(f"Created optimization dataset with {len(optimization_dataset)} records")
```

---

## Pattern 2: Run optimize_prompts() with GEPA

Use a scorer (ideally an aligned judge from `patterns-judge-alignment.md`) to drive GEPA prompt optimization of the registered system prompt.

```python
import mlflow
from mlflow.genai.optimize import GepaPromptOptimizer
from mlflow.genai.scorers import get_scorer

mlflow.set_experiment(experiment_id=EXPERIMENT_ID)

# Load prompt from registry (must be registered before optimization)
system_prompt = mlflow.genai.load_prompt(f"prompts:/{PROMPT_NAME}@production")
print(f"Loaded prompt: {system_prompt.uri}")

# Load scorer -- an aligned judge is recommended for domain-accurate optimization
# See patterns-judge-alignment.md for how to create one
aligned_judge = get_scorer(name=ALIGNED_JUDGE_NAME, experiment_id=EXPERIMENT_ID)

# Define predict_fn -- loads prompt from registry on each call so GEPA can swap it
def predict_fn(input):
    prompt = mlflow.genai.load_prompt(system_prompt.uri)
    system_content = prompt.format()

    user_message = input[0]["content"]
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_message},
    ]
    return AGENT.predict({"input": messages})

# Define aggregation to normalize judge feedback (Feedback.value) to 0-1 for GEPA
def objective_function(scores: dict) -> float:
    feedback = scores.get(ALIGNED_JUDGE_NAME)
    if feedback and hasattr(feedback, "feedback") and hasattr(feedback.feedback, "value"):
        try:
            return float(feedback.feedback.value) / 5.0  # Normalize 1-5 scale to 0-1
        except (ValueError, TypeError):
            return 0.5
    return 0.5

# Run optimization
result = mlflow.genai.optimize_prompts(
    predict_fn=predict_fn,
    train_data=optimization_dataset,  # Must have inputs + expectations
    prompt_uris=[system_prompt.uri],
    optimizer=GepaPromptOptimizer(
        reflection_model=REFLECTION_MODEL,
        max_metric_calls=75,            # Reduce for faster runs; increase for quality
        display_progress_bar=True,
    ),
    scorers=[aligned_judge],
    aggregation=objective_function,
)

optimized_prompt = result.optimized_prompts[0]
print(f"Initial score: {result.initial_eval_score}")
print(f"Final score:   {result.final_eval_score}")
print(f"\nOptimized template (first 500 chars):\n{optimized_prompt.template[:500]}...")
```

---

## Pattern 3: Register Optimized Prompt and Conditionally Promote

Only promote to the "production" alias if the optimized prompt outperforms the baseline.

```python
# Register new prompt version with optimization metadata
new_prompt_version = mlflow.genai.register_prompt(
    name=PROMPT_NAME,
    template=optimized_prompt.template,
    commit_message=f"GEPA optimization using {ALIGNED_JUDGE_NAME}",
    tags={
        "initial_score": str(result.initial_eval_score),
        "final_score": str(result.final_eval_score),
        "optimization": "GEPA",
        "judge": ALIGNED_JUDGE_NAME,
    },
)
print(f"Registered prompt version: {new_prompt_version.version}")

# Conditional promotion -- only update production alias if score improved
def promote_if_improved(prompt_name, result, new_prompt_version):
    if result.final_eval_score > result.initial_eval_score:
        mlflow.genai.set_prompt_alias(
            name=prompt_name,
            alias="production",
            version=new_prompt_version.version,
        )
        print(f"Promoted version {new_prompt_version.version} to production "
              f"({result.initial_eval_score:.3f} -> {result.final_eval_score:.3f})")
    else:
        print(f"No improvement ({result.initial_eval_score:.3f} -> "
              f"{result.final_eval_score:.3f}). Production alias unchanged.")

promote_if_improved(PROMPT_NAME, result, new_prompt_version)
```

---

## Tips for Prompt Optimization

- The optimization dataset should cover the diversity of queries your agent will handle. Include edge cases, ambiguous requests, and scenarios where tool selection matters.
- Expected responses should describe what the agent should do (which tools to call, what information to include) rather than exact output text.
- Start with `max_metric_calls` set to between 50 and 100. Higher values explore more candidates but increase cost and runtime.
- The GEPA optimizer learns from failure modes. If the aligned judge penalizes missing benchmarks or small-sample caveats, GEPA will inject those requirements into the optimized prompt.

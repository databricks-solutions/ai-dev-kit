# User Journey Guides

Step-by-step workflows for common evaluation scenarios.

---

## Journey 0: Strategy Alignment (ALWAYS START HERE)

**Starting Point**: You need to evaluate an agent
**Goal**: Align on what to evaluate before writing any code

**PRIORITY:** Before writing evaluation code, complete strategy alignment. This ensures evaluations measure what matters and provide actionable insights.

### Step 1: Understand the Agent

Before evaluating, gather context about what you're evaluating:

**Questions to ask (or investigate in the codebase):**
1. **What does this agent do?** (data analysis, RAG, multi-turn chat, task automation)
2. **What tools does it use?** (UC functions, vector search, external APIs)
3. **What is the input/output format?** (messages format, structured output)
4. **What is the current state?** (prototype, production, needs improvement)

**Actions to take:**
- Read the agent's main code file (e.g., `agent.py`)
- Review the config file for system prompts and tool definitions
- Check existing tests or evaluation scripts
- Look at CLAUDE.md or README for project context

### Step 2: Align on What to Evaluate

**Evaluation dimensions to consider:**

| Dimension | When to Use | Example Scorer |
|-----------|-------------|----------------|
| **Safety** | Always (table stakes) | `Safety()` |
| **Correctness** | When ground truth exists | `Correctness()` |
| **Relevance** | When responses should address queries | `RelevanceToQuery()` |
| **Groundedness** | RAG systems with retrieved context | `RetrievalGroundedness()` |
| **Domain Guidelines** | Domain-specific requirements | `Guidelines(name="...", guidelines="...")` |
| **Format/Structure** | Structured output requirements | Custom scorer |
| **Tool Usage** | Agents with tool calls | Custom scorer checking tool selection |

**Questions to ask the user:**
1. What are the **must-have** quality criteria? (safety, accuracy, relevance)
2. What are the **nice-to-have** criteria? (conciseness, tone, format)
3. Are there **specific failure modes** you've seen or worry about?
4. Do you have **ground truth** or expected answers for test cases?

### Step 3: Define User Scenarios (Evaluation Dataset)

**Types of test cases to include:**

| Category | Purpose | Example |
|----------|---------|---------|
| **Happy Path** | Core functionality works | Typical user questions |
| **Edge Cases** | Boundary conditions | Empty inputs, very long queries |
| **Adversarial** | Robustness testing | Prompt injection, off-topic |
| **Multi-turn** | Conversation handling | Follow-up questions, context recall |
| **Domain-specific** | Business logic | Industry terminology, specific formats |

**Questions to ask the user:**
1. What are the **most common** questions users ask?
2. What are **challenging** questions the agent should handle?
3. Are there questions it should **refuse** to answer?
4. Do you have **existing test cases** or production traces to start from?

### Step 4: Establish Success Criteria

**Define quality gates before running evaluation:**

```python
QUALITY_GATES = {
    "safety": 1.0,           # 100% - non-negotiable
    "correctness": 0.9,      # 90% - high bar for accuracy
    "relevance": 0.85,       # 85% - good relevance
    "concise": 0.8,          # 80% - nice to have
}
```

**Questions to ask the user:**
1. What pass rates are **acceptable** for each dimension?
2. Which metrics are **blocking** vs **informational**?
3. How will evaluation results **inform decisions**? (ship/no-ship, iterate, investigate)

### Strategy Alignment Checklist

Before implementing evaluation, confirm:
- [ ] Agent purpose and architecture understood
- [ ] Evaluation dimensions agreed upon
- [ ] Test case categories identified
- [ ] Success criteria defined
- [ ] Data source identified (new, traces, existing dataset)

---

## Journey 3: "Something Broke" - Regression Detection

**Starting Point**: You made changes to your agent and suspect something regressed
**Goal**: Identify what broke and verify the fix

### Steps

1. **Establish baseline metrics**
   ```bash
   # Run evaluation on the previous version (or use saved baseline)
   cd agents/tool_calling_dspy
   python run_quick_eval.py
   ```
   Record key metrics: `classifier_accuracy`, `tool_selection_accuracy`, `follows_instructions`

2. **Run evaluation on current version**
   ```bash
   python run_quick_eval.py
   ```

3. **Compare metrics**
   ```python
   from evaluation.optimization_history import OptimizationHistory

   history = OptimizationHistory()
   print(history.compare_iterations(-2, -1))  # Compare last two
   ```

4. **Identify regression source**
   - If `classifier_accuracy` dropped → Check ClassifierSignature changes
   - If `tool_selection_accuracy` dropped → Check tool descriptions, required_tools field
   - If `follows_instructions` dropped → Check ExecutorSignature output format

5. **Analyze failing traces**
   ```
   /eval:analyze-traces [experiment-id]
   ```
   Look for:
   - Error patterns in specific test categories
   - Tool call failures
   - Unexpected outputs

6. **Fix and re-evaluate**
   - Revert problematic changes or apply targeted fix
   - Re-run evaluation
   - Verify metrics restored

### Commands Used
- `python run_quick_eval.py` - Run evaluation
- `/eval:analyze-traces` - Deep trace analysis
- `OptimizationHistory.compare_iterations()` - Metric comparison

### Success Indicators
- Metrics return to baseline or improve
- No new failing test cases
- Trace analysis shows expected behavior

---

## Journey 7: "My Multi-Agent is Slow" - Performance Optimization

**Starting Point**: Your agent responses are too slow
**Goal**: Identify bottlenecks and reduce latency

### Steps

1. **Run evaluation with latency scoring**
   ```bash
   cd agents/tool_calling_dspy
   python run_quick_eval.py
   ```
   Note the latency metrics:
   - `classifier_latency_ms`
   - `rewriter_latency_ms`
   - `executor_latency_ms`
   - `total_latency_ms`

2. **Identify the bottleneck stage**
   | Latency | Typical Range | If High, Check |
   |---------|---------------|----------------|
   | classifier_latency | <5s | ClassifierSignature verbosity |
   | rewriter_latency | <10s | QueryRewriterSignature complexity |
   | executor_latency | <30s | Tool call count, response generation |

3. **Analyze traces for slow stages**
   ```
   /eval:analyze-traces [experiment-id]
   ```
   Focus on:
   - Span durations by stage
   - Number of LLM calls per stage
   - Tool execution times

4. **Run signature analysis**
   ```bash
   python -m evaluation.analyze_signatures
   ```
   Look for:
   - High total description chars (>2000)
   - Verbose OutputField descriptions
   - Missing examples (causes more retries)

5. **Apply optimizations**

   **For high classifier latency:**
   - Simplify ClassifierSignature docstring
   - Add concrete examples to reduce ambiguity

   **For high executor latency:**
   - Simplify ExecutorSignature.answer format
   - Reduce output format requirements
   - Consider caching repeated tool calls

   **For high total latency:**
   - Review if all stages are necessary
   - Consider parallel execution where possible

6. **Re-evaluate and compare**
   ```bash
   python run_quick_eval.py
   ```
   Use `OptimizationHistory.compare_iterations()` to verify improvement

### Commands Used
- `python run_quick_eval.py` - Run evaluation with latency scoring
- `/eval:analyze-traces` - Trace analysis with timing breakdown
- `python -m evaluation.analyze_signatures` - Signature verbosity analysis

### Success Indicators
- Target latencies: classifier <5s, executor <30s, total <60s
- No regression in accuracy metrics
- Consistent improvement across test categories

---

## Journey 8: "Improve My Prompts" - Systematic Prompt Optimization

**Starting Point**: Your agent works but could be more accurate
**Goal**: Systematically improve prompt quality through evaluation

### Steps

1. **Establish baseline**
   ```bash
   cd agents/tool_calling_dspy
   python run_quick_eval.py
   ```
   Record all metrics in `optimization_history.json`

2. **Run signature analysis**
   ```bash
   python -m evaluation.analyze_signatures
   ```
   Review the report for:
   - Metric correlations (which signatures affect which metrics)
   - Specific issues flagged per signature

3. **Prioritize fixes by metric impact**

   | Metric | Primary Signature | Common Issues |
   |--------|-------------------|---------------|
   | follows_instructions | ExecutorSignature | Verbose answer format, unclear structure |
   | tool_selection_accuracy | ClassifierSignature | No examples, ambiguous tool descriptions |
   | classifier_accuracy | ClassifierSignature | Verbose docstring, unclear query_type mapping |

4. **Apply ONE fix at a time**
   - Make a single, targeted change
   - Document the change in your commit message
   - Track in optimization_history.json

5. **Re-evaluate immediately**
   ```bash
   python run_quick_eval.py
   ```
   - If improved → Keep change, move to next fix
   - If regressed → Revert and try different approach
   - If unchanged → Consider if fix was necessary

6. **Iterate until targets met**

   | Metric | Target |
   |--------|--------|
   | classifier_accuracy | 95%+ |
   | tool_selection_accuracy | 90%+ |
   | follows_instructions | 80%+ |

7. **Document successful optimizations**
   ```python
   from evaluation.optimization_history import OptimizationHistory

   history = OptimizationHistory()
   print(history.summary())
   ```

### Commands Used
- `python run_quick_eval.py` - Run evaluation
- `python -m evaluation.analyze_signatures` - Identify prompt issues
- `/optimize:context --quick` - Full optimization loop (when endpoint available)

### Success Indicators
- All target metrics met
- No regressions from baseline
- Clear documentation of what changed and why
- Optimization history shows positive trend

---

## Journey 9: "Store Traces in Unity Catalog" - Trace Ingestion & Production Monitoring

**Starting Point**: You want to persist traces in Unity Catalog for long-term analysis, compliance, or production monitoring
**Goal**: Set up trace ingestion, instrument your app, and enable continuous monitoring

### Prerequisites

- Unity Catalog-enabled workspace
- "OpenTelemetry on Databricks" preview enabled
- SQL warehouse with `CAN USE` permissions
- MLflow 3.9.0+ (`pip install mlflow[databricks]>=3.9.0`)
- Workspace in `us-east-1` or `us-west-2` (Beta limitation)

### Steps

1. **Link UC schema to experiment**
   ```python
   import os
   import mlflow
   from mlflow.entities import UCSchemaLocation
   from mlflow.tracing.enablement import set_experiment_trace_location

   mlflow.set_tracking_uri("databricks")
   os.environ["MLFLOW_TRACING_SQL_WAREHOUSE_ID"] = "<SQL_WAREHOUSE_ID>"

   experiment_id = mlflow.create_experiment(name="/Shared/my-traces")
   set_experiment_trace_location(
       location=UCSchemaLocation(catalog_name="my_catalog", schema_name="my_schema"),
       experiment_id=experiment_id,
   )
   ```
   This creates three tables: `mlflow_experiment_trace_otel_logs`, `_metrics`, `_spans`

2. **Grant permissions**
   ```sql
   GRANT USE_CATALOG ON CATALOG my_catalog TO `user@company.com`;
   GRANT USE_SCHEMA ON SCHEMA my_catalog.my_schema TO `user@company.com`;
   GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_logs TO `user@company.com`;
   GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_spans TO `user@company.com`;
   GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_metrics TO `user@company.com`;
   ```
   **CRITICAL**: `ALL_PRIVILEGES` is not sufficient — explicit MODIFY + SELECT required.

3. **Set trace destination in your app**
   ```python
   mlflow.tracing.set_destination(
       destination=UCSchemaLocation(catalog_name="my_catalog", schema_name="my_schema")
   )
   # OR
   os.environ["MLFLOW_TRACING_DESTINATION"] = "my_catalog.my_schema"
   ```

4. **Instrument your application**

   Choose the appropriate approach:
   - **Auto-tracing**: `mlflow.openai.autolog()` (or langchain, anthropic, etc.)
   - **Manual tracing**: `@mlflow.trace` decorator on functions
   - **Context manager**: `mlflow.start_span()` for fine-grained control
   - **Combined**: Auto-tracing + manual decorators for full coverage

   See `patterns-trace-ingestion.md` Patterns 5-8 for detailed examples.

5. **Configure additional trace sources** (if applicable)

   | Source | Key Configuration |
   |--------|-------------------|
   | Databricks Apps | Grant SP permissions, set `MLFLOW_TRACING_DESTINATION` |
   | Model Serving | Add `DATABRICKS_TOKEN` + `MLFLOW_TRACING_DESTINATION` env vars |
   | OTEL Clients | Use OTLP exporter with `X-Databricks-UC-Table-Name` header |

   See `patterns-trace-ingestion.md` Patterns 9-11 for detailed setup per source.

6. **Enable production monitoring**
   ```python
   from mlflow.tracing import set_databricks_monitoring_sql_warehouse_id
   from mlflow.genai.scorers import Safety, ScorerSamplingConfig

   set_databricks_monitoring_sql_warehouse_id(warehouse_id="<SQL_WAREHOUSE_ID>")

   safety = Safety().register(name="safety_monitor")
   safety = safety.start(sampling_config=ScorerSamplingConfig(sample_rate=1.0))
   ```

7. **Verify in the UI**
   - Navigate to **Experiments** → your experiment → **Traces** tab
   - Select a SQL warehouse from the dropdown to load UC traces
   - Verify traces appear with correct span hierarchy

### Reference Files
- `patterns-trace-ingestion.md` — All setup and instrumentation patterns
- `CRITICAL-interfaces.md` — Trace ingestion API signatures
- `GOTCHAS.md` — Common trace ingestion mistakes

### Success Indicators
- Traces visible in the Experiments UI Traces tab
- Three UC tables populated with data
- Production monitoring scorers running and producing assessments
- No permission errors in trace ingestion

---

## Journey 10: Domain Expert Optimization Loop

**Starting Point**: You have an agent and want to incorporate domain expert feedback to continuously improve quality.
**Goal**: Run the full evaluate, label, align judge, optimize prompt, promote cycle.

For the full architecture and end-to-end walkthrough, see the [Self-Optimizing Agent blog post](https://www.databricks.com/blog/self-optimizing-football-chatbot-guided-domain-experts-databricks). For details on the MemAlign alignment approach, see the [MemAlign research blog post](https://www.databricks.com/blog/memalign-building-better-llm-judges-human-feedback-scalable-memory).

### The Loop at a Glance

```
1. Run evaluate()          -> Generate traces, score with base judge
2. Tag traces              -> Mark successfully evaluated traces for dataset
3. Build eval dataset      -> Persist traces to UC for labeling
4. Labeling session        -> SMEs review & score responses in Review App
                              (label schema name MUST match judge name)
5. Align judge (MemAlign)  -> Distill SME feedback into judge guidelines
6. Re-evaluate             -> Baseline with aligned judge (score may decrease, that's OK)
7. Build optim dataset     -> inputs + expectations (required for GEPA)
8. optimize_prompts()      -> GEPA iteratively improves system prompt
9. Conditional promote     -> Update "production" alias only if score improves
```

### Why This Works

Generic LLM judges and static prompts fail to capture domain-specific nuance. Determining what makes a response "good" requires domain knowledge that general-purpose evaluators miss. This loop solves the problem in two phases:

- **Align the judge**: Domain experts review outputs and rate quality. MemAlign distills their feedback into judge guidelines, teaching the judge what "good" means for your specific domain. This is valuable on its own -- an aligned judge improves every evaluation run and monitoring setup.
- **Optimize the prompt**: The aligned judge drives GEPA prompt optimization, automatically evolving the system prompt to maximize the domain-expert-calibrated score. Only improvements get promoted to production.

### Steps

**Phase 1: Evaluate and Collect Feedback**

1. **Design base judge, run evaluation, and tag traces**

   Create a domain-specific judge with `make_judge`, register it, run `evaluate()`, and tag traces that were successfully evaluated (agent responded AND judge scored without errors).

   See `patterns-judge-alignment.md` Patterns 1-2

2. **Build dataset and create labeling session**

   Persist tagged traces to a UC dataset and create a labeling session for domain experts.

   **CRITICAL: The label schema `name` MUST match the judge `name` used in `evaluate()`.** This is how `align()` pairs SME feedback with LLM judge scores. If they don't match, alignment will fail.

   See `patterns-judge-alignment.md` Pattern 3

3. **Wait for SMEs to complete labeling** (asynchronous step)

   Share `labeling_session.url` with domain experts. They review agent responses and submit ratings using the Review App.

**Phase 2: Align the Judge**

4. **Align judge with MemAlign (recommended)**

   MemAlign is the recommended alignment optimizer. It is the fastest (seconds vs. minutes for alternatives), most cost-effective ($0.03 vs. $1-$5), and supports memory scaling where quality continues to improve as feedback accumulates. Other optimizers (e.g., SIMBA) are also supported.

   See `patterns-judge-alignment.md` Patterns 4-5

5. **Re-evaluate with the aligned judge**

   The aligned judge score **may be lower** than the unaligned judge score. This is expected and correct -- it means the judge is now evaluating with domain-expert standards rather than generic best practices. A lower score from a more accurate judge is a better signal than an inflated score from a judge that doesn't understand your domain.

   See `patterns-judge-alignment.md` Pattern 6

6. **(Optional) Stop here** -- the aligned judge improves all future evaluations and production monitoring, independent of prompt optimization.

**Phase 3: Optimize the Prompt**

7. **Build optimization dataset with expectations** (required for GEPA)

   Unlike the eval dataset, the optimization dataset must have both `inputs` AND `expectations` per record. GEPA uses expectations during reflection to reason about why the current prompt is underperforming.

   See `patterns-prompt-optimization.md` Pattern 1

8. **Run `optimize_prompts()` with GEPA + aligned judge**

   GEPA iteratively evolves the system prompt, using the aligned judge as the scoring function.

   See `patterns-prompt-optimization.md` Pattern 2

9. **Conditionally promote**

   Register the new prompt version and only promote to the "production" alias if the score improved.

   See `patterns-prompt-optimization.md` Pattern 3

10. **Repeat from Step 1** -- each labeling session accumulates more SME signal for alignment

### Complete Loop Summary

```python
# -- PHASE 1: Evaluate and collect feedback -----------------------------------

# Step 1: Evaluate and tag successfully evaluated traces
results = evaluate(data=eval_data, predict_fn=..., scorers=[base_judge])
ok_trace_ids = results.result_df.loc[results.result_df["state"] == "OK", "trace_id"]
for trace_id in ok_trace_ids:
    mlflow.set_trace_tag(trace_id, key="eval", value="complete")

# Step 2: Build dataset and labeling session
eval_dataset = create_dataset(name=DATASET_NAME)
eval_dataset.merge_records(tagged_traces)
# CRITICAL: label schema name must match judge name for align() to work
labeling_session = create_labeling_session(
    name="sme_session", assigned_users=[...], label_schemas=[JUDGE_NAME]
)
labeling_session.add_dataset(dataset_name=DATASET_NAME)
# -> Share labeling_session.url with domain experts

# Step 3: Wait for SMEs to complete labeling

# -- PHASE 2: Align the judge -------------------------------------------------

# Step 4: Align judge (MemAlign recommended; SIMBA and others also supported)
optimizer = MemAlignOptimizer(reflection_lm=..., retrieval_k=5, embedding_model=...)
aligned_judge = base_judge.align(traces=traces, optimizer=optimizer)
aligned_judge.update(experiment_id=EXPERIMENT_ID)
# NOTE: Aligned judge scores may be lower than unaligned -- this is expected

# Step 5: Re-evaluate with aligned judge (optional but recommended)
baseline_results = evaluate(data=eval_records, predict_fn=..., scorers=[aligned_judge])

# Step 6: (Optional) Stop here if you only need an aligned judge

# -- PHASE 3: Optimize the prompt ---------------------------------------------

# Step 7: Build optimization dataset (must have inputs + expectations)
optimization_dataset = [
    {"inputs": {...}, "expectations": {"expected_response": "..."}}
]

# Step 8: Optimize prompt with GEPA + aligned judge
result = mlflow.genai.optimize_prompts(
    predict_fn=predict_fn,
    train_data=optimization_dataset,
    prompt_uris=[system_prompt.uri],
    optimizer=GepaPromptOptimizer(reflection_model=..., max_metric_calls=75),
    scorers=[aligned_judge],
    aggregation=objective_function,
)

# Step 9: Conditional promotion
new_version = mlflow.genai.register_prompt(
    name=PROMPT_NAME, template=result.optimized_prompts[0].template
)
if result.final_eval_score > result.initial_eval_score:
    mlflow.genai.set_prompt_alias(
        name=PROMPT_NAME, alias="production", version=new_version.version
    )

# -- Repeat from Step 1 with new labeling session -----------------------------
```

### Automation

The loop can be orchestrated as a Databricks job using Asset Bundles:

1. SMEs label agent outputs through the MLflow Labeling Session UI
2. The pipeline detects new labels and pulls traces with both SME feedback and baseline LLM judge scores
3. Judge alignment runs with MemAlign, producing a new judge version
4. Prompt optimization runs with GEPA, using the aligned judge
5. Conditional promotion pushes the new prompt to production if it exceeds performance thresholds
6. The agent improves automatically as the prompt registry serves the optimized version

Manual review can be injected at any step, giving developers complete control over the level of automation.

### Key Gotchas

- **Label schema name matching**: The label schema `name` MUST match the judge `name` from `evaluate()`, or `align()` cannot pair the scores
- **Score decrease after alignment**: The aligned judge may give lower scores than the unaligned judge. This is expected -- the judge is now more accurate, not the agent worse
- **MemAlign embedding costs**: Set `embedding_model` explicitly (e.g., `"databricks:/databricks-gte-large-en"`) and filter traces to labeled subset only
- **GEPA expectations**: The optimization dataset must have both `inputs` AND `expectations` per record
- **Episodic memory**: After `get_scorer()`, inspect `.instructions` not `._episodic_memory` (lazy loaded)

See `GOTCHAS.md` for the complete list.

### Reference Files

- `patterns-judge-alignment.md` -- Judge alignment workflow: design judge, evaluate, label, MemAlign, register, re-evaluate
- `patterns-prompt-optimization.md` -- GEPA optimization: build dataset, run optimize_prompts, register/promote
- `GOTCHAS.md` -- MemAlign embedding costs, episodic memory lazy loading, name matching, score interpretation, GEPA expectations

### Success Indicators

- Aligned judge instructions include domain-specific guidelines derived from SME ratings
- `result.final_eval_score > result.initial_eval_score`
- Production prompt alias updated only on genuine improvements
- Repeat sessions progressively encode more expert knowledge

---

## Quick Reference

### Which Journey Am I On?

| Symptom | Journey |
|---------|---------|
| "It was working before" | Journey 3 (Regression) |
| "It's too slow" | Journey 7 (Performance) |
| "It's not accurate enough" | Journey 8 (Prompt Optimization) |
| "I need traces in Unity Catalog" | Journey 9 (Trace Ingestion) |
| "I want SMEs to improve my judge and prompt" | Journey 10 (Domain Expert Loop) |

### Common Tools Across Journeys

| Tool | Purpose |
|------|---------|
| `run_quick_eval.py` | Fast evaluation (8 test cases) |
| `run_full_eval.py` | Full evaluation (23 test cases) |
| `analyze_signatures.py` | Signature/prompt analysis |
| `OptimizationHistory` | Track iterations |
| `/eval:analyze-traces` | Deep trace analysis |
| `/optimize:context` | Full optimization loop |

### Metric Targets

| Metric | Target | Critical Threshold |
|--------|--------|-------------------|
| classifier_accuracy | 95%+ | <80% |
| tool_selection_accuracy | 90%+ | <70% |
| follows_instructions | 80%+ | <50% |
| executor_latency | <30s | >60s |

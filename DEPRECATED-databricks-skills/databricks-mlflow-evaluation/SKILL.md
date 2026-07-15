---
name: databricks-mlflow-evaluation
description: "MLflow 3 GenAI agent evaluation. Use when writing mlflow.genai.evaluate() code, creating @scorer functions, using built-in scorers (Guidelines, Correctness, Safety, RetrievalGroundedness), building eval datasets from traces, setting up trace ingestion and production monitoring, aligning judges with MemAlign from domain expert feedback, or running optimize_prompts() with GEPA for automated prompt improvement."
---

# MLflow 3 GenAI Evaluation

## Before Writing Any Code

1. **Read GOTCHAS.md** - 15+ common mistakes that cause failures
2. **Read CRITICAL-interfaces.md** - Exact API signatures and data schemas

## End-to-End Workflows

Follow these workflows based on your goal. Each step indicates which reference files to read.

### Workflow 1: First-Time Evaluation Setup

For users new to MLflow GenAI evaluation or setting up evaluation for a new agent.

| Step | Action | Reference Files |
|------|--------|-----------------|
| 1 | Understand what to evaluate | `user-journeys.md` (Journey 0: Strategy) |
| 2 | Learn API patterns | `GOTCHAS.md` + `CRITICAL-interfaces.md` |
| 3 | Build initial dataset | `patterns-datasets.md` (Patterns 1-4) |
| 4 | Choose/create scorers | `patterns-scorers.md` + `CRITICAL-interfaces.md` (built-in list) |
| 5 | Run evaluation | `patterns-evaluation.md` (Patterns 1-3) |

### Workflow 2: Production Trace -> Evaluation Dataset

For building evaluation datasets from production traces.

| Step | Action | Reference Files |
|------|--------|-----------------|
| 1 | Search and filter traces | `patterns-trace-analysis.md` (MCP tools section) |
| 2 | Analyze trace quality | `patterns-trace-analysis.md` (Patterns 1-7) |
| 3 | Tag traces for inclusion | `patterns-datasets.md` (Patterns 16-17) |
| 4 | Build dataset from traces | `patterns-datasets.md` (Patterns 6-7) |
| 5 | Add expectations/ground truth | `patterns-datasets.md` (Pattern 2) |

### Workflow 3: Performance Optimization

For debugging slow or expensive agent execution.

| Step | Action | Reference Files |
|------|--------|-----------------|
| 1 | Profile latency by span | `patterns-trace-analysis.md` (Patterns 4-6) |
| 2 | Analyze token usage | `patterns-trace-analysis.md` (Pattern 9) |
| 3 | Detect context issues | `patterns-context-optimization.md` (Section 5) |
| 4 | Apply optimizations | `patterns-context-optimization.md` (Sections 1-4, 6) |
| 5 | Re-evaluate to measure impact | `patterns-evaluation.md` (Pattern 6-7) |

### Workflow 4: Regression Detection

For comparing agent versions and finding regressions.

| Step | Action | Reference Files |
|------|--------|-----------------|
| 1 | Establish baseline | `patterns-evaluation.md` (Pattern 4: named runs) |
| 2 | Run current version | `patterns-evaluation.md` (Pattern 1) |
| 3 | Compare metrics | `patterns-evaluation.md` (Patterns 6-7) |
| 4 | Analyze failing traces | `patterns-trace-analysis.md` (Pattern 7) |
| 5 | Debug specific failures | `patterns-trace-analysis.md` (Patterns 8-9) |

### Workflow 5: Custom Scorer Development

For creating project-specific evaluation metrics.

| Step | Action | Reference Files |
|------|--------|-----------------|
| 1 | Understand scorer interface | `CRITICAL-interfaces.md` (Scorer section) |
| 2 | Choose scorer pattern | `patterns-scorers.md` (Patterns 4-11) |
| 3 | For multi-agent scorers | `patterns-scorers.md` (Patterns 13-16) |
| 4 | Test with evaluation | `patterns-evaluation.md` (Pattern 1) |

### Workflow 6: Unity Catalog Trace Ingestion & Production Monitoring

For storing traces in Unity Catalog, instrumenting applications, and enabling continuous production monitoring.

| Step | Action | Reference Files |
|------|--------|-----------------|
| 1 | Link UC schema to experiment | `patterns-trace-ingestion.md` (Patterns 1-2) |
| 2 | Set trace destination | `patterns-trace-ingestion.md` (Patterns 3-4) |
| 3 | Instrument your application | `patterns-trace-ingestion.md` (Patterns 5-8) |
| 4 | Configure trace sources (Apps/Serving/OTEL) | `patterns-trace-ingestion.md` (Patterns 9-11) |
| 5 | Enable production monitoring | `patterns-trace-ingestion.md` (Patterns 12-13) |
| 6 | Query and analyze UC traces | `patterns-trace-ingestion.md` (Pattern 14) |

### Workflow 7: Judge Alignment with MemAlign

For aligning an LLM judge to match domain expert preferences. A well-aligned judge improves every downstream use: evaluation accuracy, production monitoring signal, and prompt optimization quality. This workflow is valuable on its own, independent of prompt optimization.

| Step | Action | Reference Files |
|------|--------|-----------------|
| 1 | Design base judge with `make_judge` (any feedback type) | `patterns-judge-alignment.md` (Pattern 1) |
| 2 | Run evaluate(), tag successful traces | `patterns-judge-alignment.md` (Pattern 2) |
| 3 | Build UC dataset + create SME labeling session | `patterns-judge-alignment.md` (Pattern 3) |
| 4 | Align judge with MemAlign after labeling completes | `patterns-judge-alignment.md` (Pattern 4) |
| 5 | Register aligned judge to experiment | `patterns-judge-alignment.md` (Pattern 5) |
| 6 | Re-evaluate with aligned judge (baseline) | `patterns-judge-alignment.md` (Pattern 6) |

### Workflow 8: Automated Prompt Optimization with GEPA

For automatically improving a registered system prompt using `optimize_prompts()`. Works with any scorer, but paired with an aligned judge (Workflow 7) gives the most domain-accurate signal. For the full end-to-end loop combining alignment and optimization, see `user-journeys.md` Journey 10.

| Step | Action | Reference Files |
|------|--------|-----------------|
| 1 | Build optimization dataset (inputs + expectations) | `patterns-prompt-optimization.md` (Pattern 1) |
| 2 | Run optimize_prompts() with GEPA + scorer | `patterns-prompt-optimization.md` (Pattern 2) |
| 3 | Register new version, promote conditionally | `patterns-prompt-optimization.md` (Pattern 3) |

## Reference Files Quick Lookup

| Reference | Purpose | When to Read |
|-----------|---------|--------------|
| `GOTCHAS.md` | Common mistakes | **Always read first** before writing code |
| `CRITICAL-interfaces.md` | API signatures, schemas | When writing any evaluation code |
| `patterns-evaluation.md` | Running evals, comparing | When executing evaluations |
| `patterns-scorers.md` | Custom scorer creation | When built-in scorers aren't enough |
| `patterns-datasets.md` | Dataset building | When preparing evaluation data |
| `patterns-trace-analysis.md` | Trace debugging | When analyzing agent behavior |
| `patterns-context-optimization.md` | Token/latency fixes | When agent is slow or expensive |
| `patterns-trace-ingestion.md` | UC trace setup, monitoring | When setting up trace storage or production monitoring |
| `patterns-judge-alignment.md` | MemAlign judge alignment, labeling sessions, SME feedback | When aligning judges to domain expert preferences |
| `patterns-prompt-optimization.md` | GEPA optimization: build dataset, optimize_prompts(), promote | When running automated prompt improvement |
| `user-journeys.md` | High-level workflows, full domain-expert optimization loop | When starting a new evaluation project or running the full align + optimize cycle |

## Critical API Facts

- **Use:** `mlflow.genai.evaluate()` (NOT `mlflow.evaluate()`)
- **Data format:** `{"inputs": {"query": "..."}}` (nested structure required)
- **predict_fn:** Receives `**unpacked kwargs` (not a dict)
- **MemAlign:** Scorer-agnostic (works with any `feedback_value_type` -- float, bool, categorical); token-heavy on the embedding model so set `embedding_model` explicitly
- **Label schema name matching:** The label schema `name` in the labeling session MUST match the judge `name` used in `evaluate()` for `align()` to pair scores
- **Aligned judge scores:** May be lower than unaligned judge scores -- this is expected and means the judge is now more accurate, not that the agent regressed
- **GEPA optimization dataset:** Must have both `inputs` AND `expectations` per record (different from eval dataset)
- **Episodic memory:** Lazily loaded -- `get_scorer()` results won't show episodic memory on print until the judge is first used
- **optimize_prompts:** Requires MLflow >= 3.5.0

See `GOTCHAS.md` for complete list.

## Related Skills

- **[databricks-docs](../databricks-docs/SKILL.md)** - General Databricks documentation reference
- **[databricks-model-serving](../databricks-model-serving/SKILL.md)** - Deploying models and agents to serving endpoints
- **[databricks-agent-bricks](../databricks-agent-bricks/SKILL.md)** - Building agents that can be evaluated with this skill
- **[databricks-python-sdk](../databricks-python-sdk/SKILL.md)** - SDK patterns used alongside MLflow APIs
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** - Unity Catalog tables for managed evaluation datasets

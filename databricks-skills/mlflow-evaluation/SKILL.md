---
name: mlflow-evaluation
description: "MLflow 3 GenAI evaluation for agent development. Use when (1) writing mlflow.genai.evaluate() code, (2) creating @scorer functions, (3) building evaluation datasets from traces, (4) using built-in scorers (Guidelines, Correctness, Safety, RetrievalGroundedness), (5) analyzing traces for latency/errors/architecture, (6) optimizing agent context/prompts/token usage, (7) debugging evaluation failures. Covers the full eval workflow: trace analysis -> dataset building -> scorer creation -> evaluation execution."
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
| `user-journeys.md` | High-level workflows | When starting a new evaluation project |

## Critical API Facts

- **Use:** `mlflow.genai.evaluate()` (NOT `mlflow.evaluate()`)
- **Data format:** `{"inputs": {"query": "..."}}` (nested structure required)
- **predict_fn:** Receives `**unpacked kwargs` (not a dict)

See `GOTCHAS.md` for complete list.

# MLflow GenAI

MLflow 3 GenAI skill for agent development. Covers tracing, evaluation, scorer creation, dataset building, trace analysis, context optimization, and debugging — the full LLMOps workflow from observability through quality assessment.

## Overview

This skill covers the full MLflow 3 GenAI evaluation workflow, from trace analysis through dataset building, scorer creation, and evaluation execution. It activates when you need to evaluate agent quality using `mlflow.genai.evaluate()`, build custom or built-in scorers, construct evaluation datasets from production traces, or optimize agent performance. The reference files provide critical API interfaces, common gotchas, and working code patterns for every stage of the evaluation lifecycle.

## What's Included

```
mlflow/
  SKILL.md
  README.md
  references/
    CRITICAL-interfaces.md
    GOTCHAS.md
    patterns-context-optimization.md
    patterns-datasets.md
    patterns-evaluation.md
    patterns-scorers.md
    patterns-trace-analysis.md
    user-journeys.md
```

## Key Topics

- Core `mlflow.genai.evaluate()` API and data schema (inputs, outputs, expectations)
- Built-in scorers: Guidelines, Correctness, Safety, RelevanceToQuery, RetrievalGroundedness, ExpectationsGuidelines
- Custom scorer development with `@scorer` decorator, class-based scorers, and `make_judge`
- Evaluation dataset creation from in-memory data, production traces, tagged traces, and Unity Catalog tables
- Trace analysis: span hierarchy, latency profiling, bottleneck detection, error patterns, tool/LLM call analysis
- Context optimization strategies: tool result management, message history compression, prompt engineering
- Production monitoring with registered scorers and sampling configuration
- Regression detection and version comparison workflows
- Common mistakes and gotchas (15+ failure modes documented)

## When to Use

- Writing `mlflow.genai.evaluate()` code to assess agent quality
- Creating `@scorer` functions or class-based scorers for custom metrics
- Building evaluation datasets from production traces or ground truth
- Using built-in scorers (Guidelines, Correctness, Safety, RetrievalGroundedness)
- Analyzing MLflow traces for latency, errors, or architecture patterns
- Optimizing agent context windows, prompts, or token usage
- Debugging evaluation failures or unexpected scorer behavior
- Comparing agent versions to detect regressions
- Setting up CI/CD quality gates for agent deployments

## Related Skills

- [Databricks Docs](../databricks-docs/) -- General Databricks documentation reference
- [Model Serving](../model-serving/) -- Deploying models and agents to serving endpoints
- [Agent Bricks](../agent-bricks/) -- Building agents that can be evaluated with this skill
- [Databricks Python SDK](../databricks-python-sdk/) -- SDK patterns used alongside MLflow APIs
- [Databricks Unity Catalog](../databricks-unity-catalog/) -- Unity Catalog tables for managed evaluation datasets

## Resources

- [MLflow GenAI Evaluation Documentation](https://docs.databricks.com/en/mlflow/llm-evaluate.html)
- [MLflow Scorers Documentation](https://docs.databricks.com/en/mlflow/llm-evaluate-scorers.html)
- [MLflow Tracing Documentation](https://docs.databricks.com/en/mlflow/mlflow-tracing.html)
- [MLflow Python Package (PyPI)](https://pypi.org/project/mlflow/)

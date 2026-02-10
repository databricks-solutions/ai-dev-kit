# Databricks Documentation Reference

Databricks documentation reference. Use as a lookup resource alongside other skills and MCP tools for comprehensive guidance.

## Overview

This skill provides access to the complete Databricks documentation index via the `llms.txt` endpoint. It activates when you need to look up Databricks concepts, APIs, or features that are not covered by a more specific skill. Rather than performing actions itself, it serves as a reference layer that informs how you use MCP tools and other action-oriented skills.

## What's Included

```
databricks-docs/
  SKILL.md
  README.md
```

## Key Topics

- Fetching and navigating the Databricks `llms.txt` documentation index
- Looking up authoritative guidance on Databricks APIs and concepts
- Complementing action skills with reference documentation
- Documentation categories: Data Engineering, SQL & Analytics, AI/ML, Governance, and Developer Tools

## When to Use

- You need reference information on a Databricks feature not covered by another skill
- You want to confirm API details or behavior before using an MCP tool
- A user asks about an unfamiliar Databricks concept or capability
- You need to supplement workflow skills (e.g., `spark-declarative-pipelines`, `databricks-python-sdk`) with deeper documentation

## Related Skills

- [Databricks Python SDK](../databricks-python-sdk/) -- SDK patterns for programmatic Databricks access
- [Spark Declarative Pipelines](../spark-declarative-pipelines/) -- DLT / Lakeflow pipeline workflows
- [Databricks Unity Catalog](../databricks-unity-catalog/) -- Governance and catalog management
- [Model Serving](../model-serving/) -- Serving endpoints and model deployment
- [MLflow Evaluation](../mlflow-evaluation/) -- MLflow 3 GenAI evaluation workflows

## Resources

- [Databricks LLMs.txt Documentation Index](https://docs.databricks.com/llms.txt)
- [Databricks Documentation Home](https://docs.databricks.com/)

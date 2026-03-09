---
name: databricks-docs
description: "Databricks documentation reference. Use as a lookup resource alongside other skills and MCP tools for comprehensive guidance."
---

# Databricks Documentation Reference

This skill provides access to the complete Databricks documentation index via llms.txt - use it as a **reference resource** to supplement other skills and inform your use of MCP tools.

## Role of This Skill

This is a **reference skill**, not an action skill. Use it to:

- Look up documentation when other skills don't cover a topic
- Get authoritative guidance on Databricks concepts and APIs
- Find detailed information to inform how you use MCP tools
- Discover features and capabilities you may not know about

**Always prefer using MCP tools for actions** (execute_sql, create_or_update_pipeline, etc.) and **load specific skills for workflows** (databricks-python-sdk, databricks-spark-declarative-pipelines, etc.). Use this skill when you need reference documentation.

## How to Use

Fetch the llms.txt documentation index:

**URL:** `https://docs.databricks.com/llms.txt`

Use WebFetch to retrieve this index, then:

1. Search for relevant sections/links
2. Fetch specific documentation pages for detailed guidance
3. Apply what you learn using the appropriate MCP tools

## Documentation Structure

The llms.txt file is organized by category:

- **Overview & Getting Started** - Basic concepts and tutorials
- **Data Engineering** - Lakeflow, Spark, Delta Lake, pipelines
- **SQL & Analytics** - Warehouses, queries, dashboards
- **AI/ML** - MLflow, model serving, GenAI
- **Governance** - Unity Catalog, permissions, security
- **Developer Tools** - SDKs, CLI, APIs, Terraform

## Example: Complementing Other Skills

**Scenario:** User wants to create a Delta Live Tables pipeline

1. Load `databricks-spark-declarative-pipelines` skill for workflow patterns
2. Use this skill to fetch docs if you need clarification on specific DLT features
3. Use `create_or_update_pipeline` MCP tool to actually create the pipeline

**Scenario:** User asks about an unfamiliar Databricks feature

1. Fetch llms.txt to find relevant documentation
2. Read the specific docs to understand the feature
3. Determine which skill/tools apply, then use them

## Common Issues

| Issue | Solution |
|-------|----------|
| **llms.txt is too large to process** | Don't fetch the entire file. Search for keywords in the URL index first, then fetch only the specific documentation pages you need |
| **Documentation page returns 404** | Databricks docs URLs change when features are renamed or restructured. Try searching llms.txt for the feature name to find the current URL |
| **Docs say feature X exists but MCP tool doesn't support it** | Not all documented features have MCP tool coverage. Fall back to the Python SDK (`databricks-python-sdk` skill) or REST API for unsupported operations |
| **Conflicting information between docs and skill** | Docs are the authoritative source. If a skill contradicts the docs, follow the docs and consider updating the skill |
| **Can't find docs for a new feature** | New features may not be in llms.txt yet. Try fetching `https://docs.databricks.com/aws/en/release-notes/` for recent additions, or search the feature name directly on the docs site |
| **Docs reference a DBR version I don't have** | Check `spark.version` on your cluster. Some features require specific DBR versions. Use serverless compute for the latest feature support |
| **Documentation is for a different cloud** | Databricks docs have cloud-specific pages. Replace `/aws/` with `/azure/` or `/gcp/` in the URL path to find the correct version |
| **Feature marked "Public Preview"** | Public Preview features are available but may change. Check the preview limitations section in the docs. Some require workspace admin opt-in |

## Related Skills

- **[databricks-python-sdk](../databricks-python-sdk/SKILL.md)** - SDK patterns for programmatic Databricks access
- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** - DLT / Lakeflow pipeline workflows
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** - Governance and catalog management
- **[databricks-model-serving](../databricks-model-serving/SKILL.md)** - Serving endpoints and model deployment
- **[databricks-mlflow-evaluation](../databricks-mlflow-evaluation/SKILL.md)** - MLflow 3 GenAI evaluation workflows

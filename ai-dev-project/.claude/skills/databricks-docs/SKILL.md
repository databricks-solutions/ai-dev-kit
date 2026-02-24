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

**Always prefer using MCP tools for actions** (execute_sql, create_or_update_pipeline, etc.) and **load specific skills for workflows** (databricks-python-sdk, spark-declarative-pipelines, etc.). Use this skill when you need reference documentation.

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

1. Load `spark-declarative-pipelines` skill for workflow patterns
2. Use this skill to fetch docs if you need clarification on specific DLT features
3. Use `create_or_update_pipeline` MCP tool to actually create the pipeline

**Scenario:** User asks about an unfamiliar Databricks feature

1. Fetch llms.txt to find relevant documentation
2. Read the specific docs to understand the feature
3. Determine which skill/tools apply, then use them

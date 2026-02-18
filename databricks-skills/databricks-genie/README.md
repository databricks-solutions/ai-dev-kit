# Databricks Genie

Create, query, analyze, benchmark, and optimize Databricks Genie Spaces for natural language SQL exploration.

## Overview

This skill now covers the full Genie lifecycle:
- Space creation and curation
- Programmatic querying via Conversation API
- Configuration quality analysis with best-practice checks
- Benchmark testing against expected SQL
- Optimized space copy creation from analysis findings

## What's Included

```
databricks-genie/
├── SKILL.md
├── spaces.md
├── conversation.md
├── references/
│   ├── best-practices-checklist.md
│   ├── space-schema.md
│   ├── workflow-analyze.md
│   ├── workflow-benchmark.md
│   └── workflow-optimize.md
└── scripts/
    ├── fetch_space.py
    ├── run_benchmark.py
    └── create_optimized_space.py
```

## Key Topics

- Create or update Genie Spaces with strong table context and sample questions
- Use `ask_genie` and `ask_genie_followup` for conversational SQL workflows
- Evaluate serialized space configuration quality against concrete criteria
- Measure SQL generation quality using space benchmark questions
- Produce and create optimized Genie Space copies while preserving originals

## When to Use

- You are building or curating a Genie Space
- You need to test conversation quality programmatically
- You need to audit why Genie is making incorrect query choices
- You want benchmark-driven optimization before promotion to broader users

## Related Skills

- [Databricks Agent Bricks](../databricks-agent-bricks/) -- Use Genie Spaces as agents in supervisor flows
- [Synthetic Data Generation](../synthetic-data-generation/) -- Generate data for Genie source tables
- [Spark Declarative Pipelines](../spark-declarative-pipelines/) -- Build bronze/silver/gold tables used by Genie
- [Databricks Unity Catalog](../databricks-unity-catalog/) -- Manage catalogs, schemas, metadata, and governance

## Resources

- [Databricks Genie Documentation](https://docs.databricks.com/genie/)
- [Genie Workspace API](https://docs.databricks.com/api/workspace/genie)

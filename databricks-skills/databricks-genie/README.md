# Databricks Genie

Create and query Databricks Genie Spaces for natural language SQL exploration.

## Overview

This skill teaches how to build Genie Spaces that let users ask natural language questions against structured data in Unity Catalog and receive SQL-generated answers. It activates when creating new Genie Spaces, adding sample questions, or programmatically querying a space via the Conversation API. Genie Spaces bridge the gap between business users and complex SQL, enabling self-service analytics through conversation.

## What's Included

```
databricks-genie/
├── SKILL.md          # Main skill reference: tools, quick start, and common issues
├── conversation.md   # Genie Conversation API: ask_genie, follow-ups, response handling
└── spaces.md         # Creating and managing Genie Spaces: table inspection, curation, best practices
```

## Key Topics

- Creating Genie Spaces with `create_or_update_genie`
- Table schema inspection workflow before space creation
- Sample question design referencing actual column names
- Conversation API for programmatic querying (`ask_genie`, `ask_genie_followup`)
- Follow-up questions with conversation context
- Auto-detection and selection of SQL warehouses
- Table selection guidance (silver/gold layers recommended)
- Space curation with instructions and certified queries
- Choosing between `ask_genie` and direct SQL (`execute_sql`)

## When to Use

- You are creating a new Genie Space for data exploration
- You need to connect Unity Catalog tables to a conversational interface
- You want to ask questions to an existing Genie Space programmatically
- You are testing a newly created Genie Space with sample queries
- You need to add or refine sample questions to improve query generation
- A user explicitly says "ask Genie" or "use my Genie Space"

## Related Skills

- [Agent Bricks](../agent-bricks/) -- Use Genie Spaces as agents inside Supervisor Agents
- [Synthetic Data Generation](../synthetic-data-generation/) -- Generate raw parquet data to populate tables for Genie
- [Spark Declarative Pipelines](../spark-declarative-pipelines/) -- Build bronze/silver/gold tables consumed by Genie Spaces
- [Databricks Unity Catalog](../databricks-unity-catalog/) -- Manage the catalogs, schemas, and tables Genie queries

## Resources

- [Databricks Genie Documentation](https://docs.databricks.com/genie/)
- [Genie Conversation API](https://docs.databricks.com/api/workspace/genie)

---
name: agent-bricks
description: "Create and manage Databricks Agent Bricks: Knowledge Assistants (KA) for document Q&A, Genie Spaces for SQL exploration, and Multi-Agent Supervisors (MAS) for multi-agent orchestration. Use when building conversational AI applications on Databricks."
---

# Agent Bricks

Create and manage Databricks Agent Bricks - pre-built AI components for building conversational applications.

## Overview

Agent Bricks are three types of pre-built AI tiles in Databricks:

| Brick | Purpose | Data Source |
|-------|---------|-------------|
| **Knowledge Assistant (KA)** | Document-based Q&A using RAG | PDF/text files in Volumes |
| **Genie Space** | Natural language to SQL | Unity Catalog tables |
| **Multi-Agent Supervisor (MAS)** | Multi-agent orchestration | Model serving endpoints |

## Prerequisites

Before creating Agent Bricks, ensure you have the required data:

### For Knowledge Assistants
- **Documents in a Volume**: PDF, text, or other files stored in a Unity Catalog volume
- Generate synthetic documents using the `unstructured-pdf-generation` skill if needed

### For Genie Spaces
- **See the `databricks-genie` skill** for comprehensive Genie Space guidance
- Tables in Unity Catalog with the data to explore
- Generate raw data using the `synthetic-data-generation` skill
- Create tables using the `spark-declarative-pipelines` skill

### For Multi-Agent Supervisors
- **Model Serving Endpoints**: Deployed agent endpoints (KA endpoints, custom agents, fine-tuned models)
- **Genie Spaces**: Existing Genie spaces can be used directly as agents for SQL-based queries
- Mix and match endpoint-based and Genie-based agents in the same MAS

## MCP Tools

### Knowledge Assistant Tools

**create_or_update_ka** - Create or update a Knowledge Assistant
- `name`: Name for the KA
- `volume_path`: Path to documents (e.g., `/Volumes/catalog/schema/volume/folder`)
- `description`: (optional) What the KA does
- `instructions`: (optional) How the KA should answer
- `tile_id`: (optional) Existing tile_id to update
- `add_examples_from_volume`: (optional, default: true) Auto-add examples from JSON files

**get_ka** - Get Knowledge Assistant details
- `tile_id`: The KA tile ID

**find_ka_by_name** - Find a Knowledge Assistant by name
- `name`: The exact name of the KA to find
- Returns: `tile_id`, `name`, `endpoint_name`, `endpoint_status`
- Use this to look up an existing KA when you know the name but not the tile_id

**delete_ka** - Delete a Knowledge Assistant
- `tile_id`: The KA tile ID to delete

### Genie Space Tools

**For comprehensive Genie guidance, use the `databricks-genie` skill.**

Basic tools available:

- `create_or_update_genie` - Create or update a Genie Space
- `get_genie` - Get Genie Space details
- `delete_genie` - Delete a Genie Space

See `databricks-genie` skill for:
- Table inspection workflow
- Sample question best practices
- Curation (instructions, certified queries)

**IMPORTANT**: There is NO system table for Genie spaces (e.g., `system.ai.genie_spaces` does not exist). To find a Genie space by name, use the `find_genie_by_name` tool.

### Multi-Agent Supervisor Tools

**create_or_update_mas** - Create or update a Multi-Agent Supervisor
- `name`: Name for the MAS
- `agents`: List of agent configurations, each with:
  - `name`: Agent identifier (required)
  - `description`: What this agent handles - critical for routing (required)
  - `ka_tile_id`: Knowledge Assistant tile ID (use for document Q&A agents - recommended for KAs)
  - `genie_space_id`: Genie space ID (use for SQL-based data agents)
  - `endpoint_name`: Model serving endpoint name (use for custom agents)
  - Note: Provide exactly one of: `ka_tile_id`, `genie_space_id`, or `endpoint_name`
- `description`: (optional) What the MAS does
- `instructions`: (optional) Routing instructions for the supervisor
- `tile_id`: (optional) Existing tile_id to update
- `examples`: (optional) List of example questions with `question` and `guideline` fields

**get_mas** - Get Multi-Agent Supervisor details
- `tile_id`: The MAS tile ID

**find_mas_by_name** - Find a Multi-Agent Supervisor by name
- `name`: The exact name of the MAS to find
- Returns: `tile_id`, `name`, `endpoint_status`, `agents_count`
- Use this to look up an existing MAS when you know the name but not the tile_id

**delete_mas** - Delete a Multi-Agent Supervisor
- `tile_id`: The MAS tile ID to delete

## Typical Workflow

### 1. Generate Source Data

Before creating Agent Bricks, generate the required source data:

**For KA (document Q&A)**:
```
1. Use `unstructured-pdf-generation` skill to generate PDFs
2. PDFs are saved to a Volume with companion JSON files (question/guideline pairs)
```

**For Genie (SQL exploration)**:
```
1. Use `synthetic-data-generation` skill to create raw parquet data
2. Use `spark-declarative-pipelines` skill to create bronze/silver/gold tables
```

### 2. Create the Agent Brick

Use the appropriate `create_or_update_*` tool with your data sources.

### 3. Wait for Provisioning

Newly created KA and MAS tiles need time to provision. The endpoint status will progress:
- `PROVISIONING` - Being created (can take 2-5 minutes)
- `ONLINE` - Ready to use
- `OFFLINE` - Not running

### 4. Add Examples (Automatic)

For KA, if `add_examples_from_volume=true`, examples are automatically extracted from JSON files in the volume and added once the endpoint is `ONLINE`.

## Best Practices

1. **Use meaningful names**: Names are sanitized automatically (spaces become underscores)
2. **Provide descriptions**: Helps users understand what the brick does
3. **Add instructions**: Guide the AI's behavior and tone
4. **Include sample questions**: Shows users how to interact with the brick
5. **Use the workflow**: Generate data first, then create the brick

## See Also

- `1-knowledge-assistants.md` - Detailed KA patterns and examples
- `databricks-genie` skill - Detailed Genie patterns, curation, and examples
- `3-multi-agent-supervisors.md` - Detailed MAS patterns and examples

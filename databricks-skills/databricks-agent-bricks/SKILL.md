---
name: databricks-agent-bricks
description: "Create and manage Databricks Agent Bricks: Knowledge Assistants (KA) for document Q&A, Genie Spaces for SQL exploration, and Supervisor Agents (MAS) for multi-agent orchestration. Use when building conversational AI applications on Databricks."
---

# Agent Bricks

Create and manage Databricks Agent Bricks - pre-built AI components for building conversational applications.

## Overview

Agent Bricks are three types of pre-built AI tiles in Databricks:

| Brick | Purpose | Data Source |
|-------|---------|-------------|
| **Knowledge Assistant (KA)** | Document-based Q&A using RAG | PDF/text files in Volumes |
| **Genie Space** | Natural language to SQL | Unity Catalog tables |
| **Supervisor Agent (MAS)** | Multi-agent orchestration | Model serving endpoints |

## Prerequisites

Before creating Agent Bricks, ensure you have the required data:

### For Knowledge Assistants
- **Documents in a Volume**: PDF, text, or other files stored in a Unity Catalog volume
- Generate synthetic documents using the `databricks-unstructured-pdf-generation` skill if needed

### For Genie Spaces
- **See the `databricks-genie` skill** for comprehensive Genie Space guidance
- Tables in Unity Catalog with the data to explore
- Generate raw data using the `databricks-synthetic-data-generation` skill
- Create tables using the `databricks-spark-declarative-pipelines` skill

### For Supervisor Agents
- **Model Serving Endpoints**: Deployed agent endpoints (KA endpoints, custom agents, fine-tuned models)
- **Genie Spaces**: Existing Genie spaces can be used directly as agents for SQL-based queries
- Mix and match endpoint-based and Genie-based agents in the same Supervisor Agent

### For Unity Catalog Functions
- **Existing UC Function**: Function already registered in Unity Catalog
- Agent service principal has `EXECUTE` privilege on the function

### For External MCP Servers
- **Existing UC HTTP Connection**: Connection configured with `is_mcp_connection: 'true'`
- Agent service principal has `USE CONNECTION` privilege on the connection

## MCP Tools

### Knowledge Assistant Tool

**manage_ka** - Manage Knowledge Assistants (KA)
- `action`: "create_or_update", "get", "find_by_name", or "delete"
- `name`: Name for the KA (for create_or_update, find_by_name)
- `volume_path`: Path to documents (e.g., `/Volumes/catalog/schema/volume/folder`) (for create_or_update)
- `description`: (optional) What the KA does (for create_or_update)
- `instructions`: (optional) How the KA should answer (for create_or_update)
- `tile_id`: The KA tile ID (for get, delete, or update via create_or_update)
- `add_examples_from_volume`: (optional, default: true) Auto-add examples from JSON files (for create_or_update)

Actions:
- **create_or_update**: Requires `name`, `volume_path`. Optionally pass `tile_id` to update.
- **get**: Requires `tile_id`. Returns tile_id, name, description, endpoint_status, knowledge_sources, examples_count.
- **find_by_name**: Requires `name` (exact match). Returns found, tile_id, name, endpoint_name, endpoint_status. Use this to look up an existing KA when you know the name but not the tile_id.
- **delete**: Requires `tile_id`.

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

### Supervisor Agent Tool

**manage_mas** - Manage Supervisor Agents (MAS)
- `action`: "create_or_update", "get", "find_by_name", or "delete"
- `name`: Name for the Supervisor Agent (for create_or_update, find_by_name)
- `agents`: List of agent configurations (for create_or_update), each with:
  - `name`: Agent identifier (required)
  - `description`: What this agent handles - critical for routing (required)
  - `ka_tile_id`: Knowledge Assistant tile ID (use for document Q&A agents - recommended for KAs)
  - `genie_space_id`: Genie space ID (use for SQL-based data agents)
  - `endpoint_name`: Model serving endpoint name (for custom agents)
  - `uc_function_name`: Unity Catalog function name in format `catalog.schema.function_name`
  - `connection_name`: Unity Catalog connection name (for external MCP servers)
  - Note: Provide exactly one of: `ka_tile_id`, `genie_space_id`, `endpoint_name`, `uc_function_name`, or `connection_name`
- `description`: (optional) What the Supervisor Agent does (for create_or_update)
- `instructions`: (optional) Routing instructions for the supervisor (for create_or_update)
- `tile_id`: The Supervisor Agent tile ID (for get, delete, or update via create_or_update)
- `examples`: (optional) List of example questions with `question` and `guideline` fields (for create_or_update)

Actions:
- **create_or_update**: Requires `name`, `agents`. Optionally pass `tile_id` to update.
- **get**: Requires `tile_id`. Returns tile_id, name, description, endpoint_status, agents, examples_count.
- **find_by_name**: Requires `name` (exact match). Returns found, tile_id, name, endpoint_status, agents_count. Use this to look up an existing Supervisor Agent when you know the name but not the tile_id.
- **delete**: Requires `tile_id`.

## Typical Workflow

### 1. Generate Source Data

Before creating Agent Bricks, generate the required source data:

**For KA (document Q&A)**:
```
1. Use `databricks-unstructured-pdf-generation` skill to generate PDFs
2. PDFs are saved to a Volume with companion JSON files (question/guideline pairs)
```

**For Genie (SQL exploration)**:
```
1. Use `databricks-synthetic-data-generation` skill to create raw parquet data
2. Use `databricks-spark-declarative-pipelines` skill to create bronze/silver/gold tables
```

### 2. Create the Agent Brick

Use `manage_ka(action="create_or_update", ...)` or `manage_mas(action="create_or_update", ...)` with your data sources.

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

## Example: Multi-Modal Supervisor Agent

```python
manage_mas(
    action="create_or_update",
    name="Enterprise Support Supervisor",
    agents=[
        {
            "name": "knowledge_base",
            "ka_tile_id": "f32c5f73-466b-...",
            "description": "Answers questions about company policies, procedures, and documentation from indexed files"
        },
        {
            "name": "analytics_engine",
            "genie_space_id": "01abc123...",
            "description": "Runs SQL analytics on usage metrics, performance stats, and operational data"
        },
        {
            "name": "ml_classifier",
            "endpoint_name": "custom-classification-endpoint",
            "description": "Classifies support tickets and predicts resolution time using custom ML model"
        },
        {
            "name": "data_enrichment",
            "uc_function_name": "support.utils.enrich_ticket_data",
            "description": "Enriches support ticket data with customer history and context"
        },
        {
            "name": "ticket_operations",
            "connection_name": "ticket_system_mcp",
            "description": "Creates, updates, assigns, and closes support tickets in external ticketing system"
        }
    ],
    description="Comprehensive enterprise support agent with knowledge retrieval, analytics, ML, data enrichment, and ticketing operations",
    instructions="""
    Route queries as follows:
    1. Policy/procedure questions → knowledge_base
    2. Data analysis requests → analytics_engine
    3. Ticket classification → ml_classifier
    4. Customer context lookups → data_enrichment
    5. Ticket creation/updates → ticket_operations

    If a query spans multiple domains, chain agents:
    - First gather information (analytics_engine or knowledge_base)
    - Then take action (ticket_operations)
    """
)
```

## Related Skills

- **[databricks-genie](../databricks-genie/SKILL.md)** - Comprehensive Genie Space creation, curation, and Conversation API guidance
- **[databricks-unstructured-pdf-generation](../databricks-unstructured-pdf-generation/SKILL.md)** - Generate synthetic PDFs to feed into Knowledge Assistants
- **[databricks-synthetic-data-generation](../databricks-synthetic-data-generation/SKILL.md)** - Create raw data for Genie Space tables
- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** - Build bronze/silver/gold tables consumed by Genie Spaces
- **[databricks-model-serving](../databricks-model-serving/SKILL.md)** - Deploy custom agent endpoints used as MAS agents
- **[databricks-vector-search](../databricks-vector-search/SKILL.md)** - Build vector indexes for RAG applications paired with KAs

## See Also

- `1-knowledge-assistants.md` - Detailed KA patterns and examples
- `databricks-genie` skill - Detailed Genie patterns, curation, and examples
- `2-supervisor-agents.md` - Detailed MAS patterns and examples

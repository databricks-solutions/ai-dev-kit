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
- Generate raw data using the `databricks-synthetic-data-gen` skill
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

## CLI Tools

### Knowledge Assistant CLI

```bash
# List all Knowledge Assistants
databricks knowledge-assistants list-knowledge-assistants

# Create a Knowledge Assistant
databricks knowledge-assistants create-knowledge-assistant "My KA Name" "Description of what the KA does"

# Get a Knowledge Assistant by name (resource name format: knowledge-assistants/{id})
databricks knowledge-assistants get-knowledge-assistant "knowledge-assistants/{ka_id}"

# Update a Knowledge Assistant
databricks knowledge-assistants update-knowledge-assistant "knowledge-assistants/{ka_id}" "*" "New Name" "New Description"

# Delete a Knowledge Assistant
databricks knowledge-assistants delete-knowledge-assistant "knowledge-assistants/{ka_id}"

# Create a Knowledge Source (volume-based documents)
databricks knowledge-assistants create-knowledge-source "knowledge-assistants/{ka_id}" "Source Name" "Description" "VOLUME" \
  --volume-config '{"volume_id": "/Volumes/catalog/schema/volume"}'

# List Knowledge Sources for a KA
databricks knowledge-assistants list-knowledge-sources "knowledge-assistants/{ka_id}"

# Sync (re-index) Knowledge Sources
databricks knowledge-assistants sync-knowledge-sources "knowledge-assistants/{ka_id}"
```

### Genie Space CLI

**For comprehensive Genie guidance, use the `databricks-genie` skill.**

```bash
# List all Genie Spaces
databricks genie list-spaces

# Create a Genie Space
databricks genie create-space --json '{"display_name": "My Genie", "description": "...", "table_identifiers": ["catalog.schema.table"]}'

# Get a Genie Space
databricks genie get-space SPACE_ID

# Update a Genie Space
databricks genie update-space SPACE_ID --json '{"display_name": "New Name"}'

# Delete (trash) a Genie Space
databricks genie trash-space SPACE_ID
```

See `databricks-genie` skill for:
- Table inspection workflow
- Sample question best practices
- Curation (instructions, certified queries)

**IMPORTANT**: There is NO system table for Genie spaces (e.g., `system.ai.genie_spaces` does not exist). Use `databricks genie list-spaces` to find spaces.

### Supervisor Agent (MAS)

**NO CLI AVAILABLE** - Supervisor Agents are managed via the self-contained `scripts/mas_manager.py` script in this skill folder.

Install requirements first:
```bash
pip install databricks-sdk requests
```

Usage:

```bash
# List all Supervisor Agents
python scripts/mas_manager.py list_mas

# Create a Supervisor Agent
python scripts/mas_manager.py create_mas "My Supervisor" '{"agents": [...], "description": "...", "instructions": "..."}'

# Get a Supervisor Agent by tile ID
python scripts/mas_manager.py get_mas TILE_ID

# Find a Supervisor Agent by name
python scripts/mas_manager.py find_mas "My Supervisor"

# Update a Supervisor Agent
python scripts/mas_manager.py update_mas TILE_ID '{"name": "New Name", "agents": [...], ...}'

# Delete a Supervisor Agent
python scripts/mas_manager.py delete_mas TILE_ID

# Add examples (MAS must be ONLINE)
python scripts/mas_manager.py add_examples TILE_ID '[{"question": "...", "guideline": "..."}]'

# Add examples with wait (for jobs - waits up to 10 min for ONLINE)
python scripts/mas_manager.py add_examples_wait TILE_ID '[{"question": "...", "guideline": "..."}]'

# List examples
python scripts/mas_manager.py list_examples TILE_ID
```

Agent configuration options (provide exactly one per agent):
- `ka_tile_id`: Knowledge Assistant tile ID (for document Q&A agents)
- `genie_space_id`: Genie space ID (for SQL-based data agents)
- `endpoint_name`: Model serving endpoint name (for custom agents)
- `uc_function_name`: Unity Catalog function name in format `catalog.schema.function_name`
- `connection_name`: Unity Catalog connection name (for external MCP servers)

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
1. Use `databricks-synthetic-data-gen` skill to create raw parquet data
2. Use `databricks-spark-declarative-pipelines` skill to create bronze/silver/gold tables
```

### 2. Create the Agent Brick

Use the CLI commands above or SDK to create your Agent Bricks with data sources.

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

Use `scripts/mas_manager.py` to create a Supervisor Agent:

```bash
python scripts/mas_manager.py create_mas "Enterprise Support Supervisor" '{
    "description": "Comprehensive enterprise support agent",
    "instructions": "Route queries as follows:\n1. Policy/procedure questions → knowledge_base\n2. Data analysis requests → analytics_engine\n3. Ticket classification → ml_classifier",
    "agents": [
        {
            "name": "knowledge_base",
            "ka_tile_id": "f32c5f73-466b-...",
            "description": "Answers questions about company policies from indexed files"
        },
        {
            "name": "analytics_engine",
            "genie_space_id": "01abc123...",
            "description": "Runs SQL analytics on usage metrics"
        },
        {
            "name": "ml_classifier",
            "endpoint_name": "custom-classification-endpoint",
            "description": "Classifies support tickets using custom ML model"
        },
        {
            "name": "data_enrichment",
            "uc_function_name": "support.utils.enrich_ticket_data",
            "description": "Enriches support ticket data with customer history"
        },
        {
            "name": "ticket_operations",
            "connection_name": "ticket_system_mcp",
            "description": "Creates and updates support tickets in external system"
        }
    ]
}'
```

## Related Skills

- **[databricks-genie](../databricks-genie/SKILL.md)** - Comprehensive Genie Space creation, curation, and Conversation API guidance
- **[databricks-unstructured-pdf-generation](../databricks-unstructured-pdf-generation/SKILL.md)** - Generate synthetic PDFs to feed into Knowledge Assistants
- **[databricks-synthetic-data-gen](../databricks-synthetic-data-gen/SKILL.md)** - Create raw data for Genie Space tables
- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** - Build bronze/silver/gold tables consumed by Genie Spaces
- **[databricks-model-serving](../databricks-model-serving/SKILL.md)** - Deploy custom agent endpoints used as MAS agents
- **[databricks-vector-search](../databricks-vector-search/SKILL.md)** - Build vector indexes for RAG applications paired with KAs

## See Also

- `1-knowledge-assistants.md` - Detailed KA patterns and examples
- `databricks-genie` skill - Detailed Genie patterns, curation, and examples
- `2-supervisor-agents.md` - Detailed MAS patterns and examples

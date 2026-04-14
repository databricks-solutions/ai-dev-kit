---
name: databricks-agent-bricks
description: "Create and manage Databricks Agent Bricks: Knowledge Assistants (KA) for document Q&A, Genie Spaces for SQL exploration, and Supervisor Agents for multi-agent orchestration."
---

# Agent Bricks

Create and manage Databricks Agent Bricks - pre-built AI components for conversational applications.

## Overview

| Brick | Purpose | Data Source |
|-------|---------|-------------|
| **Knowledge Assistant (KA)** | Document-based Q&A using RAG | PDF/text files in Volumes |
| **Genie Space** | Natural language to SQL | Unity Catalog tables |
| **Supervisor Agent** | Multi-agent orchestration | KA, Genie, endpoints, UC functions, MCP |

## Quick Reference

### Knowledge Assistant

```bash
# List volumes in a schema
databricks volumes list CATALOG SCHEMA

# Browse volume contents (via SQL)
databricks experimental aitools tools query --warehouse WH "LIST '/Volumes/catalog/schema/volume/'"

# Create KA
databricks knowledge-assistants create-knowledge-assistant "Name" "Description"

# Add knowledge source (files from volume)
databricks knowledge-assistants create-knowledge-source "knowledge-assistants/{ka_id}" \
  --json '{"display_name": "Source Name", "description": "...", "source_type": "files", "files": {"path": "/Volumes/catalog/schema/volume/"}}'

# Sync (index) documents
databricks knowledge-assistants sync-knowledge-sources "knowledge-assistants/{ka_id}"

# Check status (wait for ONLINE)
databricks knowledge-assistants get-knowledge-assistant "knowledge-assistants/{ka_id}"

# List all KAs
databricks knowledge-assistants list-knowledge-assistants
```

### Genie Space

**See `databricks-genie` skill for comprehensive guidance.**

```bash
databricks genie list-spaces
databricks genie create-space --json '{"display_name": "Name", "description": "...", "table_identifiers": ["catalog.schema.table"]}'
databricks genie get-space SPACE_ID
```

### Supervisor Agent

**No CLI** - use `scripts/mas_manager.py` (run from skill folder):

```bash
# List existing MAS
python scripts/mas_manager.py list_mas

# Create MAS with KA and Genie agents
python scripts/mas_manager.py create_mas "My Supervisor" '{
    "description": "Routes queries to specialized agents",
    "instructions": "Route data questions to analyst. Route document questions to docs_agent.",
    "agents": [
        {"name": "analyst", "genie_space_id": "01abc...", "description": "SQL analytics on data"},
        {"name": "docs_agent", "ka_tile_id": "dab408a2-...", "description": "Answers from documents"}
    ]
}'

# Check status (wait for ONLINE)
python scripts/mas_manager.py get_mas TILE_ID

# Find IDs
databricks knowledge-assistants list-knowledge-assistants --output json | jq '.[].id'
databricks genie list-spaces --output json | jq '.[].space_id'
```

---

## Knowledge Assistant Workflow

### Step 1: Find Your Volume

```bash
# List volumes in the schema
databricks volumes list skywest_airlines ops_control --output json

# Browse volume contents
databricks experimental aitools tools query --warehouse WH "LIST '/Volumes/catalog/schema/volume/'"
```

### Step 2: Create the KA

```bash
databricks knowledge-assistants create-knowledge-assistant \
  "Engineering Docs Assistant" \
  "Answers questions about engineering documents and procedures"
```

Response includes `id` (e.g., `dab408a2-f8f4-439e-b65d-cc3cc2c45bbd`).

### Step 3: Add Knowledge Source

```bash
databricks knowledge-assistants create-knowledge-source \
  "knowledge-assistants/{ka_id}" \
  --json '{
    "display_name": "Engineering Documents",
    "description": "PDFs from engineering docs folder",
    "source_type": "files",
    "files": {"path": "/Volumes/catalog/schema/volume/docs/"}
  }'
```

**Source types:**
- `files` - PDFs/text from a Volume path (`files.path`)
- `index` - Existing Vector Search index (`index.index_name`, `index.text_col`, `index.doc_uri_col`)

### Step 4: Sync and Wait

```bash
# Trigger indexing
databricks knowledge-assistants sync-knowledge-sources "knowledge-assistants/{ka_id}"

# Check status (wait for state: ONLINE)
databricks knowledge-assistants get-knowledge-assistant "knowledge-assistants/{ka_id}"
```

| State | Meaning |
|-------|---------|
| `CREATING` | Provisioning endpoint (2-5 min) |
| `ONLINE` | Ready to use |
| `OFFLINE` | Not running |

---

## Supervisor Agent Workflow

Supervisor Agents orchestrate multiple agents (KA, Genie, endpoints, UC functions, MCP).

### Prerequisites

```bash
pip install databricks-sdk requests
```

### Create a Supervisor Agent

```bash
python scripts/mas_manager.py create_mas "Support Supervisor" '{
    "description": "Routes queries to specialized agents",
    "instructions": "Route billing questions to billing_agent, technical questions to docs_agent",
    "agents": [
        {
            "name": "billing_agent",
            "genie_space_id": "01abc123...",
            "description": "SQL analytics on billing data"
        },
        {
            "name": "docs_agent",
            "ka_tile_id": "dab408a2-f8f4-439e-b65d-cc3cc2c45bbd",
            "description": "Answers questions from technical documentation"
        }
    ]
}'
```

### Agent Types

Each agent needs exactly ONE of:

| Field | Agent Type |
|-------|------------|
| `ka_tile_id` | Knowledge Assistant (document Q&A) |
| `genie_space_id` | Genie Space (SQL analytics) |
| `endpoint_name` | Model serving endpoint (custom agent) |
| `uc_function_name` | Unity Catalog function (`catalog.schema.function`) |
| `connection_name` | UC HTTP Connection (MCP server) |

### Find IDs

```bash
# KA tile ID
databricks knowledge-assistants list-knowledge-assistants --output json | jq '.[].id'

# Genie space ID
databricks genie list-spaces --output json | jq '.[].space_id'
```

### Manage Supervisor Agents

```bash
python scripts/mas_manager.py get_mas TILE_ID
python scripts/mas_manager.py update_mas TILE_ID '{"name": "New Name", ...}'
python scripts/mas_manager.py delete_mas TILE_ID

# Add examples (requires ONLINE status)
python scripts/mas_manager.py add_examples TILE_ID '[{"question": "...", "guideline": "..."}]'
```

---

## Reference Files

| Topic | File |
|-------|------|
| KA details, troubleshooting | [1-knowledge-assistants.md](1-knowledge-assistants.md) |
| Supervisor Agent details, MCP, UC functions | [2-supervisor-agents.md](2-supervisor-agents.md) |
| Genie Spaces | See `databricks-genie` skill |

## Related Skills

- **databricks-genie** - Genie Space creation, curation, Conversation API
- **databricks-unstructured-pdf-generation** - Generate synthetic PDFs for KA
- **databricks-model-serving** - Deploy custom agent endpoints

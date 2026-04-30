---
name: databricks-agent-bricks
description: "Create Agent Bricks: Knowledge Assistants (KA) for document Q&A and Supervisor Agents for multi-agent orchestration (MAS). For Genie Spaces, see databricks-genie skill."
---

# Agent Bricks

Agent Bricks are pre-built AI tiles in Databricks that provide conversational interfaces. This skill covers **Knowledge Assistants** and **Supervisor Agents**. For Genie Spaces, use the `databricks-genie` skill.

| Brick | Purpose | This Skill |
|-------|---------|------------|
| **Knowledge Assistant (KA)** | Document Q&A using RAG on PDFs/text in Volumes | ✓ |
| **Supervisor Agent** | Orchestrates multiple agents (KA, Genie, endpoints, UC functions, MCP) | ✓ |
| **Genie Space** | Natural language to SQL on Unity Catalog tables | `databricks-genie` |

---

## Knowledge Assistant

```bash
# Find volumes
databricks volumes list CATALOG SCHEMA
databricks experimental aitools tools query --warehouse WH "LIST '/Volumes/catalog/schema/volume/'"

# Create KA
databricks knowledge-assistants create-knowledge-assistant "Name" "Description"

# Add knowledge source. With --json, pass ONLY the PARENT as a positional arg
# and put display_name / description / source_type / the source body (files|index|file_table)
# inside the JSON. Mixing positional DISPLAY_NAME/DESCRIPTION/SOURCE_TYPE with --json errors.
databricks knowledge-assistants create-knowledge-source \
  "knowledge-assistants/{ka_id}" \
  --json '{
    "display_name": "Docs",
    "description": "Documentation files",
    "source_type": "files",
    "files": {"path": "/Volumes/catalog/schema/volume/"}
  }'

# Sync and check status
databricks knowledge-assistants sync-knowledge-sources "knowledge-assistants/{ka_id}"
databricks knowledge-assistants get-knowledge-assistant "knowledge-assistants/{ka_id}"

# List/manage
databricks knowledge-assistants list-knowledge-assistants
databricks knowledge-assistants delete-knowledge-assistant "knowledge-assistants/{ka_id}"
```

**Source types:** `files` (Volume path) or `index` (Vector Search: `index.index_name`, `index.text_col`, `index.doc_uri_col`)

**Status:** `CREATING` (2-5 min) → `ONLINE` → `OFFLINE`

---

## Supervisor Agent

**No CLI** — use `mas_manager.py` from this skill's `scripts/` folder. All `<SKILL_ROOT>/...` paths below are relative to the directory containing this SKILL.md (resolve to the absolute path in your install location).

```bash
# Create MAS
python <SKILL_ROOT>/scripts/mas_manager.py create_mas "My Supervisor" '{
    "description": "Routes queries to specialized agents",
    "instructions": "Route data questions to analyst, document questions to docs_agent.",
    "agents": [
        {"name": "analyst", "genie_space_id": "01abc...", "description": "SQL analytics"},
        {"name": "docs_agent", "ka_tile_id": "dab408a2-...", "description": "Answers from documents"}
    ]
}'

# Check status and manage. list_mas enumerates every MAS you can access
# and returns {tile_id, name, endpoint_status, agents_count} — use it to
# find a tile_id / see which MAS are ONLINE before operations.
python <SKILL_ROOT>/scripts/mas_manager.py list_mas
python <SKILL_ROOT>/scripts/mas_manager.py get_mas TILE_ID
python <SKILL_ROOT>/scripts/mas_manager.py update_mas TILE_ID '{"agents": [...]}'
python <SKILL_ROOT>/scripts/mas_manager.py delete_mas TILE_ID

# Add examples — requires endpoint_status=ONLINE. After create_mas the MAS is
# NOT_READY and takes up to ~10 min to reach ONLINE. Without --wait, this
# fails fast if not ONLINE yet. With --wait, it blocks until ONLINE then adds.
python <SKILL_ROOT>/scripts/mas_manager.py add_examples TILE_ID '[{"question": "...", "guideline": "..."}]' [--wait]

# Find IDs
databricks knowledge-assistants list-knowledge-assistants --output json | jq '.[].id'
databricks genie list-spaces --output json | jq '.[].space_id'
```

**Agent types** (use exactly ONE per agent):

| Field | Type |
|-------|------|
| `ka_tile_id` | Knowledge Assistant |
| `genie_space_id` | Genie Space |
| `endpoint_name` | Model serving endpoint |
| `uc_function_name` | UC function (`catalog.schema.func`) |
| `connection_name` | MCP server (UC HTTP Connection) |

**Status:** `NOT_READY` (up to ~10 min after create/big update) → `ONLINE` → `OFFLINE`

---

## Reference

| Topic | File |
|-------|------|
| KA source types, index, troubleshooting | [1-knowledge-assistants.md](1-knowledge-assistants.md) |
| UC functions, MCP servers, examples | [2-supervisor-agents.md](2-supervisor-agents.md) |

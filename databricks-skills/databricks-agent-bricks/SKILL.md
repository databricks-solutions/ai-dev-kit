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

Native CLI: `databricks supervisor-agents` (Beta, requires CLI ≥ 0.299.2). Resource paths look like `supervisor-agents/{id}` — every command takes either that full path or a `PARENT` of that shape. `list-supervisor-agents` and `list-examples`/`list-tools` return bare JSON arrays.

```bash
# Create the supervisor agent (display name positional, description/instructions as flags)
databricks supervisor-agents create-supervisor-agent "My Supervisor" \
    --description "Routes queries to specialized agents" \
    --instructions "Route data questions to analyst, document questions to docs_agent."
# → returns {name: "supervisor-agents/<uuid>", endpoint_name: "mas-<short>-endpoint", ...}

# List / get / find by name
databricks supervisor-agents list-supervisor-agents
databricks supervisor-agents get-supervisor-agent supervisor-agents/<id>
databricks supervisor-agents list-supervisor-agents | jq '.[] | select(.display_name == "My Supervisor")'

# Update — UPDATE_MASK + new DISPLAY_NAME are positional; description/instructions optional flags
databricks supervisor-agents update-supervisor-agent supervisor-agents/<id> \
    "display_name,description,instructions" "My Supervisor (v2)" \
    --description "..." --instructions "..."

# Delete
databricks supervisor-agents delete-supervisor-agent supervisor-agents/<id>
```

### Tools (the agents the supervisor routes to)

Each tool wires the supervisor to a downstream resource. `tool_type` lives in `--json` (the CLI rejects it as a positional when `--json` is used). Each type has a type-specific block (`genie_space`, `knowledge_assistant`, etc.) whose identifier field differs by type — see the table below.

```bash
# Attach a Genie space — find its space_id with `databricks genie list-spaces`
databricks supervisor-agents create-tool supervisor-agents/<id> analyst --json '{
    "tool_type": "genie_space",
    "description": "SQL analytics on the analytics warehouse",
    "genie_space": {"id": "<genie_space_id>"}
}'

# Attach a Knowledge Assistant — find ka_id with `databricks knowledge-assistants list-knowledge-assistants`
databricks supervisor-agents create-tool supervisor-agents/<id> docs_agent --json '{
    "tool_type": "knowledge_assistant",
    "description": "Answers from product documentation",
    "knowledge_assistant": {"knowledge_assistant_id": "<ka_id>"}
}'

# List / get / delete tools
databricks supervisor-agents list-tools supervisor-agents/<id>
databricks supervisor-agents get-tool supervisor-agents/<id>/tools/<tool_id>
databricks supervisor-agents delete-tool supervisor-agents/<id>/tools/<tool_id>
```

**Tool types** (`tool_type` value → type-specific block):

| `tool_type` | Block | Use for |
|---|---|---|
| `genie_space` | `{"id": "<space_id>"}` | Natural language → SQL via Genie |
| `knowledge_assistant` | `{"knowledge_assistant_id": "<ka_id>"}` | Document Q&A via a KA |
| `uc_function` | `{"name": "catalog.schema.func"}` | UC SQL/Python function |
| `uc_connection` | `{"name": "<connection_name>"}` | External MCP server via UC HTTP Connection |
| `volume` | `{"name": "<full_volume_name>"}` | UC Volume browsing |
| `app` | `{"name": "<app_name>"}` | Databricks App |
| Other types (`serving_endpoint`, `lakeview_dashboard`, `supervisor_agent`, `uc_table`, `vector_search_index`, `catalog`, `schema`, `web_search`) | Block name and field shape vary | Run `databricks supervisor-agents create-tool --help` and probe — these were not verified end-to-end here. |

### Examples (training the supervisor)

Examples must use `--json` — the positional `GUIDELINES` arg doesn't accept any encoding because guidelines is a `repeated string`.

```bash
databricks supervisor-agents create-example supervisor-agents/<id> --json '{
    "question": "What were Q4 revenue numbers?",
    "guidelines": ["Route to analyst Genie space", "Always group by region"]
}'

databricks supervisor-agents list-examples supervisor-agents/<id>
databricks supervisor-agents get-example supervisor-agents/<id>/examples/<ex_id>
databricks supervisor-agents delete-example supervisor-agents/<id>/examples/<ex_id>
```

**Endpoint readiness:** after `create-supervisor-agent`, the serving endpoint takes up to ~10 minutes to come online before it can answer queries. `get-supervisor-agent` returns the endpoint name immediately, but querying it is gated on the endpoint's own readiness — check via `databricks serving-endpoints get <endpoint_name>`.

---

## Reference

| Topic | File |
|-------|------|
| KA source types, index, troubleshooting | [1-knowledge-assistants.md](1-knowledge-assistants.md) |
| UC functions, MCP servers, examples | [2-supervisor-agents.md](2-supervisor-agents.md) |

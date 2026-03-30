---
name: tool-selection
description: >
  Evaluates whether the agent selected appropriate MCP tools instead of
  shell workarounds. Load when the trace contains Bash tool calls that
  could have used MCP tools, or when evaluating tool call efficiency.
metadata:
  category: evaluation
  version: "1.0"
  applies_to: []
---

## Tool Selection Rubric

When evaluating tool selection in agent traces:

### 1. MCP Over Bash
If a Databricks MCP tool exists for the operation, the agent MUST use it:
- SQL queries → `mcp__databricks__execute_sql` (not `Bash` + `databricks sql`)
- File uploads → `mcp__databricks__upload_to_volume` (not `Bash` + `databricks fs cp`)
- Job management → `mcp__databricks__create_job`, `mcp__databricks__run_job` (not REST API via curl)
- Cluster ops → `mcp__databricks__create_cluster` (not CLI via Bash)
- Workspace files → `mcp__databricks__workspace_get_object` (not Bash + `databricks workspace export`)

### 2. Correct Tool for Task
- SQL execution → `execute_sql` (not notebook execution)
- Reading docs → `Read` tool (not fetching via curl)
- File creation → `Write` tool for local, volume upload for remote
- Schema inspection → `execute_sql` with `DESCRIBE` or `SHOW` (not `list_tables` for column details)

### 3. No Shell Workarounds
The following patterns indicate incorrect tool selection:
- `Bash('databricks ...')` when an MCP tool exists
- `Bash('curl ...')` for Databricks REST APIs when MCP tools cover it
- `Bash('python -c ...')` for operations that have dedicated tools
- Multiple Bash calls that could be one MCP call

### 4. Reasonable Call Count
- Simple queries: 1-3 tool calls expected
- Multi-step tasks: count should be proportional to steps
- Excessive retries suggest the agent is confused, not efficient
- Reading the same file multiple times is wasteful

### 5. Error Recovery
- On tool failure, the agent should try an alternative approach
- Should NOT blindly retry the same failing call
- Should report unrecoverable errors to the user

See [MCP tool guide](references/MCP_TOOL_GUIDE.md) for the full tool catalog.

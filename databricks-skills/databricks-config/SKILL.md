---
name: databricks-config
description: "Manage Databricks workspace connections: check which workspace you're connected to, switch workspaces, list available workspaces, or authenticate to a new workspace."
---

Use the `manage_workspace` MCP tool for all workspace operations. Do NOT edit `~/.databrickscfg`, use Bash, or use the Databricks CLI.

## Steps

1. Call `ToolSearch` with query `select:mcp__databricks__manage_workspace` to load the tool.

2. Map user intent to action:
   - status / which workspace / current → `action="status"`
   - list / available workspaces → `action="list"`
   - switch to X → call `list` first to find the profile name, then `action="switch", profile="<name>"` (or `host="<url>"` if a URL was given)
   - login / connect / authenticate → `action="login", host="<url>"`

3. Call `mcp__databricks__manage_workspace` with the action and any parameters.

4. Present the result. For `status`/`switch`/`login`: show host, profile, username. For `list`: formatted table with the active profile marked.

> **Note:** The switch is session-scoped — it resets on MCP server restart. For permanent profile setup, use `databricks auth login -p <profile>` and update `~/.databrickscfg` with `cluster_id` or `serverless_compute_id = auto`.

## Secrets Management

Use Databricks Secrets to store API keys, tokens, and credentials securely. Secrets are never exposed in plaintext via the API — only metadata is returned.

### Quick Reference

```python
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()

# Create scope → store secret → retrieve in notebook
w.secrets.create_scope(scope="my-scope")
w.secrets.put_secret(scope="my-scope", key="api-key", string_value="sk-...")

# In notebooks: dbutils.secrets.get(scope="my-scope", key="api-key")
```

### Secret ACLs

```python
# Grant READ to a group
w.secrets.put_acl(scope="my-scope", principal="data-team", permission="READ")
# Permissions: READ (get values), WRITE (put/delete secrets), MANAGE (full control + ACLs)
```

### CLI Commands

```bash
databricks secrets create-scope my-scope
databricks secrets put-secret my-scope api-key --string-value "sk-..."
databricks secrets list-secrets my-scope
databricks secrets delete-secret my-scope api-key
```

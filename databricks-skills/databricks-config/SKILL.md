---
name: databricks-config
description: "Manage Databricks workspace connections: check which workspace you're connected to, switch workspaces, list available workspaces, verify connectivity, identify the current user, or authenticate to a new workspace."
---

# Databricks Workspace Configuration

Manage workspace connections, verify identity, and troubleshoot authentication using MCP tools. Do NOT edit `~/.databrickscfg` directly, use Bash, or use the Databricks CLI unless explicitly noted.

---

## Quick Start — Verify Connectivity

Run these two calls in sequence to confirm you are connected and authenticated:

1. **Get current user identity:**

```
Tool: get_current_user
Args: {}
```

Returns:

```json
{"username": "user@example.com", "home_path": "/Workspace/Users/user@example.com/"}
```

2. **List warehouses to confirm workspace access:**

```
Tool: list_warehouses
Args: {}
```

Returns a list of warehouses with `id`, `name`, `state`, `cluster_size`, `auto_stop_mins`, and `creator_name`.

If both calls succeed, the workspace connection is healthy.

---

## MCP Tools Reference

### `get_current_user`

Returns the authenticated user's identity. No parameters required.

| Field | Description | Example |
|-------|-------------|---------|
| `username` | User's email address | `user@example.com` |
| `home_path` | Workspace home directory | `/Workspace/Users/user@example.com/` |

Use this to:
- Confirm authentication is working ("who am I?")
- Determine the correct home path for creating notebooks, files, or folders
- Verify the right account is active before making changes

### `manage_workspace`

Handles all workspace switching and profile management. Map user intent to the correct action:

| User Intent | Action | Parameters |
|------------|--------|------------|
| "which workspace?" / "status" / "current" | `action="status"` | — |
| "list workspaces" / "available profiles" | `action="list"` | — |
| "switch to X" | `action="switch"` | `profile="<name>"` or `host="<url>"` |
| "login" / "connect" / "authenticate" | `action="login"` | `host="<url>"` |

**Calling the tool:**

```
Tool: manage_workspace
Args: {"action": "status"}
```

**Presenting results:**
- For `status` / `switch` / `login`: show host, profile, and username.
- For `list`: formatted table with the active profile marked.

> **Note:** The switch is session-scoped — it resets on MCP server restart. For permanent profile setup, use `databricks auth login -p <profile>` and update `~/.databrickscfg` with `cluster_id` or `serverless_compute_id = auto`.

### `list_warehouses` / `list_clusters`

List SQL warehouses or clusters. Useful as a lightweight connectivity check — if these return results, the connection and permissions are working.

### `get_best_warehouse` / `get_best_cluster`

Auto-select the best available warehouse or cluster. For detailed compute selection workflows, see the `databricks-compute` skill.

---

## Connectivity Verification Workflow

When a user asks to verify their Databricks connection, run this sequence:

### Step 1 — Identity Check

```
Tool: get_current_user
Args: {}
```

Confirm the returned `username` is not `null` and matches the expected user. If `username` is `null`, authentication is broken — skip to Troubleshooting.

### Step 2 — Workspace Info

```
Tool: manage_workspace
Args: {"action": "status"}
```

Confirm the `host` matches the expected workspace URL.

### Step 3 — Resource Access

```
Tool: list_warehouses
Args: {}
```

```
Tool: list_clusters
Args: {}
```

Confirm the user can see at least one warehouse or cluster. If both return empty lists, the user may lack permissions.

### Step 4 — SQL Connectivity (optional)

```
Tool: execute_sql
Args: {"sql_query": "SELECT current_user() AS username, current_catalog() AS catalog, current_schema() AS schema"}
```

Verifies end-to-end SQL execution. Returns:

```json
[{"username": "user@example.com", "catalog": "main", "schema": "default"}]
```

### Step 5 — Catalog Permissions (optional)

```
Tool: execute_sql
Args: {"sql_query": "SHOW CATALOGS"}
```

Returns the list of catalogs the user can access. Useful for confirming Unity Catalog visibility.

**Present a summary table:**

| Check | Status | Detail |
|-------|--------|--------|
| Identity | OK | user@example.com |
| Workspace | OK | https://xxx.cloud.databricks.com |
| Warehouses | OK | 1 found (Serverless Starter Warehouse) |
| Clusters | OK | 1 found (Personal Compute Cluster) |
| SQL Execution | OK | Connected to default schema |
| Catalogs | OK | 5 catalogs accessible |

---

## Workspace Switching Workflow

When a user asks to switch workspaces:

1. **List available profiles:**

```
Tool: manage_workspace
Args: {"action": "list"}
```

2. **Present profiles** as a table with the active profile marked.

3. **Switch** once the user confirms the target:

```
Tool: manage_workspace
Args: {"action": "switch", "profile": "<profile_name>"}
```

Or by URL:

```
Tool: manage_workspace
Args: {"action": "switch", "host": "https://target-workspace.cloud.databricks.com"}
```

4. **Verify** the switch succeeded:

```
Tool: get_current_user
Args: {}
```

Confirm the username and home_path reflect the new workspace.

---

## Troubleshooting

### Authentication Failures

| Symptom | Likely Cause | Resolution |
|---------|-------------|------------|
| `get_current_user` returns `null` username and `null` home_path | Token expired or missing | Run `databricks auth login -p <profile>` in terminal |
| "PERMISSION_DENIED" on any call | Token valid but lacks permissions | Check with workspace admin for role assignment |
| "Connection refused" or timeout | Wrong host URL or network issue | Verify host with `manage_workspace action="status"`, check VPN |
| `manage_workspace` tool not found | MCP server version mismatch | Restart the MCP server; the tool may not be available in all versions |
| Empty warehouse/cluster lists | No resources or no permissions | Ask workspace admin to grant access to compute resources |

### Token and Profile Issues

- **Expired OAuth token:** Re-authenticate with `databricks auth login -p <profile>`. OAuth tokens typically expire after 1 hour.
- **Wrong profile active:** Use `manage_workspace action="list"` to see all profiles, then `action="switch"` to the correct one.
- **Multiple config sources conflicting:** Environment variables (`DATABRICKS_HOST`, `DATABRICKS_TOKEN`) override `~/.databrickscfg`. Unset them if using profile-based auth.

### Connectivity Checks via CLI (fallback)

If MCP tools are unavailable, use the Databricks CLI directly:

```bash
# Check current auth
databricks auth describe

# List profiles
grep '^\[' ~/.databrickscfg

# Test connectivity
databricks clusters list --output json

# Re-authenticate
databricks auth login -p DEFAULT
```

### Common Misconfigurations

- **Missing `cluster_id` in profile:** Databricks Connect and notebook execution require a `cluster_id` or `serverless_compute_id = auto` in the profile. Add it to `~/.databrickscfg` under the relevant profile section.
- **HTTP 403 on SQL execution:** The user's token is valid but the warehouse denies access. Verify warehouse permissions in the Databricks workspace UI under SQL Warehouses > Permissions.
- **"No warehouses available":** The workspace may not have any SQL warehouses provisioned, or they may all be stopped. Use `list_warehouses` to check state — if all are `STOPPED`, the user or an admin needs to start one.

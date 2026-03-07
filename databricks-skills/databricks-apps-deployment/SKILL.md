---
name: databricks-apps-deployment
description: "Deploy and manage Databricks Apps using MCP tools and CLI. Covers the full lifecycle: listing apps, inspecting status, deploying from workspace paths, retrieving logs, debugging failures, and deleting apps. Use when deploying apps, checking deployment status, troubleshooting app errors, reading app logs, or managing running apps."
---

# Databricks Apps Deployment & Operations

Manage the full Databricks Apps lifecycle — deploy, monitor, debug, and delete — using MCP tools and the Databricks CLI.

> **Building an app?** This skill covers deployment and operations only. For building apps, see:
> - **[databricks-app-python](../databricks-app-python/SKILL.md)** — Streamlit, Dash, Gradio, Flask, FastAPI, Reflex
> - **[databricks-app-apx](../databricks-app-apx/SKILL.md)** — Full-stack FastAPI + React (APX framework)

---

## Critical Rules

- **MUST** upload source code to a Workspace path before deploying (MCP `deploy_app` deploys from workspace, not local)
- **MUST** verify app status after deployment — `SUCCEEDED` does not mean the app is healthy; check logs
- **MUST** use lowercase letters, numbers, and hyphens for app names (no underscores or spaces)
- **NEVER** delete an app without confirming with the user — deletion is irreversible
- **PREFER CLI** for `create_app`, `deploy_app`, and `get_app_logs` — these MCP tools have known SDK bugs (see Known MCP Tool Bugs below). Use `list_apps`, `get_app`, and `delete_app` via MCP (these work correctly).

---

## MCP Tools Reference

Six MCP tools are available via the `user-databricks` server. The CLI equivalents are shown for when MCP tools have bugs or are unavailable.

| Tool | Purpose | Required Params | Optional Params | CLI Equivalent |
|------|---------|-----------------|-----------------|----------------|
| `list_apps` | List apps in workspace | _(none)_ | `name_contains` (string), `limit` (int, default 20, 0 = all) | `databricks apps list` |
| `get_app` | Get app details + active deployment | `name` (string) | _(none)_ | `databricks apps get <name> --output json` |
| `get_app_logs` | Get logs for a deployment | `app_name` (string) | `deployment_id` (string) | `databricks apps logs <name>` |
| `create_app` | Create a new app definition | `name` (string) | `description` (string) | `databricks apps create <name>` |
| `deploy_app` | Deploy from workspace source path | `app_name` (string), `source_code_path` (string) | `mode` (string: `"SNAPSHOT"` or `"AUTO_SYNC"`) | `databricks apps deploy <name> --source-code-path <path>` |
| `delete_app` | Delete an app permanently | `name` (string) | _(none)_ | `databricks apps delete <name>` |

---

## Deployment Lifecycle

### Step 1: Check Existing Apps

Before creating or deploying, check what already exists:

```python
# List all apps (default limit: 20)
list_apps()

# Search by name substring (case-insensitive)
list_apps(name_contains="my-app")

# List all apps with no limit
list_apps(limit=0)
```

**Response structure** (`list_apps` per app / `get_app`):
```json
{
  "name": "my-app",
  "description": "My dashboard",
  "url": "https://my-app-<workspace-id>.aws.databricksapps.com",
  "compute_status": {
    "state": "ACTIVE",
    "message": "App compute is running."
  },
  "create_time": "2026-03-01T12:00:00Z",
  "update_time": "2026-03-07T01:46:15Z",
  "creator": "user@example.com",
  "updater": "user@example.com",
  "id": "64eabce9-...",
  "compute_size": "MEDIUM",
  "service_principal_client_id": "64eabce9-...",
  "active_deployment": {
    "deployment_id": "01f119c76dcc141d...",
    "source_code_path": "/Workspace/Users/user@example.com/my_app",
    "mode": "SNAPSHOT",
    "status": {
      "state": "SUCCEEDED",
      "message": "App started successfully"
    },
    "create_time": "2026-03-07T01:46:15Z",
    "update_time": "2026-03-07T01:47:00Z",
    "creator": "user@example.com"
  }
}
```

> **Note:** `get_app` returns an additional `app_status` field (not present in `list_apps`):
> ```json
> "app_status": { "state": "RUNNING", "message": "App has status: App is running" }
> ```

Key `compute_status.state` values:
- `ACTIVE` — app compute is running
- `STOPPED` — app is idle/stopped (no `active_deployment` field)

Key `app_status.state` values:
- `RUNNING` — app is serving traffic
- `UNAVAILABLE` — app status is unavailable (e.g., stopped or not yet deployed)

Key `active_deployment.status.state` values:
- `SUCCEEDED` — deployment completed
- `IN_PROGRESS` — deployment is still running
- `FAILED` — deployment failed (check `status.message`)

### Step 2: Create the App (if new)

```python
create_app(
    name="my-dashboard",
    description="Customer analytics dashboard"
)
```

Skip this step if the app already exists — `deploy_app` works on existing apps.

### Step 3: Upload Source Code to Workspace

Source code must be in a Workspace path before deploying. Use the Databricks CLI or `upload_folder` MCP tool:

```bash
# CLI approach
databricks workspace import-dir ./my_app /Workspace/Users/user@example.com/my_app --overwrite
```

```python
# MCP approach (if upload_folder tool is available)
upload_folder(
    local_folder="./my_app",
    workspace_folder="/Workspace/Users/user@example.com/my_app"
)
```

### Step 4: Deploy

```python
deploy_app(
    app_name="my-dashboard",
    source_code_path="/Workspace/Users/user@example.com/my_app"
)
```

The `source_code_path` must be a workspace path (starts with `/Workspace/`). The directory must contain an `app.yaml` file.

### Step 5: Verify Deployment

```python
# Check app status and active deployment
get_app(name="my-dashboard")
```

Look for:
- `compute_status.state` should be `ACTIVE`
- `active_deployment.status.state` should be `SUCCEEDED`
- `active_deployment.status.message` should be `"App started successfully"`

### Step 6: Check Logs

```python
# Get logs for the active deployment
get_app_logs(app_name="my-dashboard")

# Get logs for a specific deployment (use deployment_id from get_app response)
get_app_logs(app_name="my-dashboard", deployment_id="01f119c76dcc141d...")
```

> **Known issue:** `get_app_logs` may fail with an import error (`cannot import name 'get_api_client'`) in some MCP server versions. If this happens, fall back to the CLI:
> ```bash
> databricks apps logs my-dashboard
> ```

### Step 7: Iterate on Failures

If deployment fails:
1. Read logs to identify the error
2. Fix the source code locally
3. Re-upload to the workspace path
4. Re-deploy with `deploy_app` (same parameters)
5. Verify with `get_app` and `get_app_logs`

---

## CLI Fallback Commands

When MCP tools are unavailable or encounter errors, use the Databricks CLI:

```bash
# List apps
databricks apps list

# Get app details (JSON output for parsing)
databricks apps get my-dashboard --output json

# Create a new app (NAME is positional, not --name)
databricks apps create my-dashboard --description "My dashboard app"

# Deploy from workspace source path
databricks apps deploy my-dashboard --source-code-path /Workspace/Users/user@example.com/my_app

# Get logs (streams recent 200 lines by default)
databricks apps logs my-dashboard

# Follow logs in real-time
databricks apps logs my-dashboard --follow

# Delete app
databricks apps delete my-dashboard
```

---

## Deleting Apps

```python
delete_app(name="my-dashboard")
```

**This is irreversible.** Always confirm with the user before deleting. After deletion, verify with `get_app` — the app will briefly show `compute_status.state` = `DELETING`, then return an error: `App with name X does not exist or is deleted`.

> **Note:** You cannot delete an app while it is in `STARTING` state. Wait until it reaches `ACTIVE` or `STOPPED` before deleting.

---

## Troubleshooting

### Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `App with name X does not exist or is deleted` | App name is wrong or app was deleted | Run `list_apps(name_contains="...")` to find the correct name |
| `No active deployment found` | App exists but has never been deployed, or is stopped | Deploy with `deploy_app` or check if the app was recently stopped |
| `cannot import name 'get_api_client'` | MCP server bug in `get_app_logs` | Use CLI: `databricks apps logs <name>` |
| `AppsAPI.create() got an unexpected keyword argument 'name'` | MCP server bug in `create_app` (SDK parameter mismatch). Note: app may still be created server-side despite the error. | Use CLI: `databricks apps create <name> --description "..."` |
| `'source_code_path'` KeyError | MCP server bug in `deploy_app` (SDK parameter mismatch) | Use CLI: `databricks apps deploy <name> --source-code-path <path>` |
| `active_deployment.status.state` = `FAILED` | Source code has errors | Check `status.message` field in deployment, fix code, re-upload, re-deploy |
| Deployment `SUCCEEDED` but app not accessible | App may still be starting or has runtime errors | Wait 30-60s, then check logs for startup exceptions |
| `The maximum number of apps for your workspace` | Workspace has hit the 300-app limit | Delete unused apps before creating new ones |
| `Cannot delete app X as it is not terminal with state STARTING` | App is still provisioning | Wait until app reaches `ACTIVE` or `STOPPED` state before deleting |

### Debugging Workflow

1. **Check status**: `get_app(name="my-app")` — is `active_deployment.status.state` = `SUCCEEDED`?
2. **Read logs**: `get_app_logs(app_name="my-app")` or `databricks apps logs my-app`
3. **Look for patterns**:
   - `[SYSTEM]` log lines = deployment infrastructure issues
   - `[APP]` log lines = your application code errors
   - `ModuleNotFoundError` = missing package in `requirements.txt`
   - `Port already in use` = wrong port; use `DATABRICKS_APP_PORT` env var (default 8000)
   - `Permission denied` = service principal lacks access to a resource
4. **Fix and redeploy**: edit source → re-upload → `deploy_app` → verify

### App Status Meanings

| `compute_status.state` | Meaning | Action |
|-------------------------|---------|--------|
| `ACTIVE` | App compute is running | No action needed |
| `STARTING` | App compute is provisioning (can take 2-5 min after create) | Wait and poll `get_app` |
| `STOPPED` | App is idle (auto-stopped after inactivity) | Will auto-start on next request, or redeploy |
| `DELETING` | App is being deleted (takes ~30s) | Wait; `get_app` will eventually return "does not exist" |

| `app_status.state` | Meaning | Action |
|---------------------|---------|--------|
| `RUNNING` | App is serving traffic | No action needed |
| `UNAVAILABLE` | App status not available (stopped or not yet deployed) | Deploy or wait for compute to start |

| `active_deployment.status.state` | Meaning | Action |
|----------------------------------|---------|--------|
| `SUCCEEDED` | Deployment completed successfully | No action needed |
| `IN_PROGRESS` | Deployment is still running | Wait and poll `get_app` |
| `FAILED` | Deployment failed | Check `status.message`, fix code, redeploy |

> **Note:** A stopped app has no `active_deployment` field. An app that was created but never deployed also has no `active_deployment`.

---

## Related Skills

- **[databricks-app-python](../databricks-app-python/SKILL.md)** — building Python apps (Streamlit, Dash, FastAPI, etc.)
- **[databricks-app-apx](../databricks-app-apx/SKILL.md)** — building full-stack apps (FastAPI + React)
- **[databricks-asset-bundles](../databricks-asset-bundles/SKILL.md)** — deploying apps via DABs (alternative to MCP/CLI)

---

## Verified Against Live Workspace (Full E2E Test)

Complete lifecycle tested: create → upload → deploy → verify → logs → delete → confirm deletion.

| Tool | Input | Result | Status |
|------|-------|--------|--------|
| `list_apps` | `{limit: 5}` | Returned 5 apps with name, URL, status, active deployments | PASS |
| `create_app` | `{name: "skill-test-app"}` | **MCP bug**: SDK expects `App` object, not kwargs. App IS created server-side despite error. Use CLI fallback. | BUG |
| `get_app` | `{name: "skill-test-app"}` | Returned app details; `compute_status.state` = `ACTIVE`, no `active_deployment` (not yet deployed) | PASS |
| `upload_folder` | minimal app.yaml + main.py | Uploaded 2 files to workspace path | PASS |
| `deploy_app` | `{app_name: "skill-test-app", source_code_path: "..."}` | **MCP bug**: SDK expects `AppDeployment` object, not flat params. Use CLI fallback. | BUG |
| `get_app` (poll) | `{name: "skill-test-app"}` | `active_deployment.status.state` = `SUCCEEDED`, `compute_status.state` = `ACTIVE` | PASS |
| `get_app_logs` | `{app_name: "skill-test-app"}` | **MCP bug**: `cannot import name 'get_api_client'`. Use CLI: `databricks apps logs <name>` | BUG |
| `delete_app` | `{name: "skill-test-app"}` | Returns full app object with `compute_status.state` = `DELETING` | PASS |
| `get_app` (verify) | `{name: "skill-test-app"}` | First: `compute_status.state` = `DELETING`, then: `does not exist or is deleted` | PASS |

### Known MCP Tool Bugs (as of Mar 2026)

> **Note:** These bugs were originally verified against the `user-databricks` MCP server. If the MCP server has been updated, these bugs may be fixed. Test with MCP first; fall back to CLI if errors occur.

| Tool | Bug | Workaround |
|------|-----|------------|
| `create_app` | SDK v0.49.0 expects `app: App` object, not `name`/`description` kwargs | Use CLI: `databricks apps create <name> --description "..."` |
| `deploy_app` | SDK expects `app_deployment: AppDeployment` object, not flat `source_code_path` | Use CLI: `databricks apps deploy <name> --source-code-path <path>` |
| `get_app_logs` | `cannot import name 'get_api_client'` from `databricks_tools_core.client` | Use CLI: `databricks apps logs <name>` |

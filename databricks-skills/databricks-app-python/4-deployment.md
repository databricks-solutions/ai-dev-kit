# Deploying Databricks Apps

Three deployment options: Databricks CLI (simplest), Asset Bundles (multi-environment), or MCP tools (programmatic).

**Cookbook deployment guide**: https://apps-cookbook.dev/docs/deploy

---

## Option 1: Databricks CLI

**Best for**: quick deployments, single environment.

### Step 1: Create app.yaml

```yaml
command:
  - "python"        # Adjust per framework — see table below
  - "app.py"

env:
  - name: DATABRICKS_WAREHOUSE_ID
    valueFrom:
      resource: sql-warehouse
  - name: USE_MOCK_BACKEND
    value: "false"
```

### app.yaml Commands Per Framework

| Framework | Command |
|-----------|---------|
| Dash | `["python", "app.py"]` — bind to `DATABRICKS_APP_PORT` in code |
| Streamlit | `["streamlit", "run", "app.py"]` — port/address/headless auto-configured by runtime |
| Gradio | `["python", "app.py"]` — bind to `DATABRICKS_APP_PORT` in code |
| Flask | `["gunicorn", "app:app", "-w", "4", "-b", "0.0.0.0:8000"]` |
| FastAPI | `["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]` |
| Reflex | `["reflex", "run", "--env", "prod"]` |

**Port binding**: Apps must listen on `DATABRICKS_APP_PORT` (defaults to 8000). Streamlit is auto-configured. For Flask/FastAPI, 8000 in the command matches the default. For Dash/Gradio, read the env var in code: `int(os.environ.get("DATABRICKS_APP_PORT", 8000))`. **Never use 8080.**

### Step 2: Create and Deploy

```bash
# Create the app
databricks apps create <app-name>

# Upload source code
databricks workspace mkdirs /Workspace/Users/<user>/apps/<app-name>
databricks workspace import-dir . /Workspace/Users/<user>/apps/<app-name>

# Deploy
databricks apps deploy <app-name> \
  --source-code-path /Workspace/Users/<user>/apps/<app-name>

# Add resources via UI (SQL warehouse, Lakebase, etc.)

# Check status and URL
databricks apps get <app-name>
```

### Redeployment

**NEVER delete and recreate an app to fix deployment issues** — just redeploy. Deleting disrupts OAuth integration and doesn't fix underlying problems.

**Clean stale files** before redeploying — leftover files (e.g., old `main.py`) in the workspace source path can cause conflicts:

```bash
# Check for stale files
databricks workspace list /Workspace/Users/<user>/apps/<app-name>

# Remove stale files if needed
databricks workspace delete /Workspace/Users/<user>/apps/<app-name>/<stale-file>

# Sync and redeploy
databricks sync . /Workspace/Users/<user>/apps/<app-name> --full
databricks apps deploy <app-name> \
  --source-code-path /Workspace/Users/<user>/apps/<app-name>
```

---

## Option 2: Databricks Asset Bundles (DABs)

**Best for**: multi-environment deployments (dev/staging/prod), version-controlled infrastructure.

**Recommended workflow**: deploy via CLI first to validate, then generate bundle config.

### Generate Bundle from Existing App

```bash
databricks bundle generate app \
  --existing-app-name <app-name> \
  --key <resource_key>
```

This creates:
- `resources/<key>.app.yml` — app resource definition
- `src/app/` — app source files including `app.yaml`

### Deploy with Bundles

```bash
# Validate
databricks bundle validate -t dev

# Deploy
databricks bundle deploy -t dev

# Start the app (required after deployment)
databricks bundle run <resource_key> -t dev

# Production
databricks bundle deploy -t prod
databricks bundle run <resource_key> -t prod
```

**Key difference from other resources**: environment variables go in `src/app/app.yaml`, not `databricks.yml`.

For complete DABs guidance, use the **databricks-asset-bundles** skill.

---

## Option 3: MCP Tools

For programmatic app lifecycle management, see [6-mcp-approach.md](6-mcp-approach.md).

---

## Post-Deployment

### Attach Resources (CRITICAL)

Without resources attached, the gateway shows "App Not Available" even if the process is running. Attach resources via API PATCH **before** deploying:

```bash
databricks api patch /api/2.0/apps/<app-name> --json '{
  "resources": [
    {"name": "sql-warehouse", "sql_warehouse": {"id": "<warehouse-id>", "permission": "CAN_USE"}},
    {"name": "serving-endpoint", "serving_endpoint": {"name": "<endpoint-name>", "permission": "CAN_QUERY"}}
  ]
}' --profile <profile>
```

**Find the correct warehouse ID** for the target workspace:
```bash
databricks warehouses list --profile <profile>
```

### Configure Permissions

```bash
databricks api put /api/2.0/permissions/apps/<app-name> --json '{
  "access_control_list": [
    {"user_name": "<your-email>", "permission_level": "CAN_MANAGE"},
    {"group_name": "users", "permission_level": "CAN_USE"}
  ]
}' --profile <profile>
```

### Check Logs

```bash
databricks apps logs <app-name>
```

**Key patterns in logs**:
- `[SYSTEM]` — deployment status, file updates, dependency installation
- `[APP]` — application output, framework messages
- `Deployment successful` — app deployed correctly
- `App started successfully` — app is running
- `Error:` — check stack traces

### Verify

1. Access app URL (from `databricks apps get <app-name>`)
2. Check all pages load correctly
3. Verify data connectivity (look for backend initialization messages in logs)
4. Test user authorization flow if enabled

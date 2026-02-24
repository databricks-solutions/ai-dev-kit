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
    valueFrom: sql-warehouse
  - name: USE_MOCK_BACKEND
    value: "false"
```

### app.yaml Commands Per Framework

| Framework | Command |
|-----------|---------|
| Dash | `["python", "app.py"]` |
| Streamlit | `["streamlit", "run", "app.py"]` |
| Gradio | `["python", "app.py"]` |
| Flask | `["gunicorn", "app:app", "-w", "4", "-b", "0.0.0.0:8080"]` |
| FastAPI | `["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]` |
| Reflex | `["reflex", "run", "--env", "prod"]` |

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

```bash
databricks workspace delete /Workspace/Users/<user>/apps/<app-name> --recursive
databricks workspace import-dir . /Workspace/Users/<user>/apps/<app-name>
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

### Configure Permissions

- Set `CAN USE` for approved users/groups
- Set `CAN MANAGE` only for trusted developers
- Verify service principal has required resource permissions

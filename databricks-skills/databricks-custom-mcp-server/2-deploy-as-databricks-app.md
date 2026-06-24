# 2. Deploy as a Databricks App

The MCP server is a regular Databricks App with a specific `app.yaml` command. After deploy, grant the app's SP read access to whatever data its tools touch, then verify the server is reachable.

## `app.yaml` (3 lines)

```yaml
command: ["uvicorn", "server.app:http_app", "--host", "0.0.0.0", "--port", "8000"]

env:
  - name: "PORT"
    value: "8000"
  # Optional — if your tools talk to another deployed app:
  # - name: "ONTOS_APP_URL"
  #   value: "https://my-other-app.cloud.databricksapps.com"
```

The literal `server.app:http_app` matches the `http_app = mcp.streamable_http_app()` line at the bottom of `server/app.py`.

## `manifest.yaml`

```yaml
version: 1
name: "My Custom MCP Server"
description: "MCP server exposing <domain> tools to AI agents."
```

That's the entire manifest the Apps platform reads. Don't expect MCP-specific schema fields — there aren't any today.

## Deploy via the SDK (programmatic, idempotent)

```python
import datetime
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.apps import App, AppDeployment

w = WorkspaceClient(profile="<your-workspace-profile>")
APP_NAME = "my-custom-mcp"

# 1. Upload source to a workspace path
src_remote = f"/Workspace/Users/{w.current_user.me().user_name}/{APP_NAME}"
# (Use w.workspace.import_ or w.workspace.upload to push your local dir.)

# 2. Ensure the app exists
try:
    w.apps.get(name=APP_NAME)
    print(f"  ✓ app {APP_NAME} already exists; redeploying")
except Exception:
    w.apps.create(app=App(name=APP_NAME)).result(timeout=datetime.timedelta(minutes=10))
    print(f"  ✓ created app {APP_NAME}")

# 3. Trigger deployment
deployment = w.apps.deploy_and_wait(
    app_name=APP_NAME,
    app_deployment=AppDeployment(source_code_path=src_remote),
    timeout=datetime.timedelta(minutes=10),
)
print(f"  ✓ deployment {deployment.deployment_id} succeeded")
print(f"  url: {w.apps.get(name=APP_NAME).url}")
```

## Deploy via the CLI (fastest for iteration)

```bash
databricks apps deploy my-custom-mcp \
  --source-code-path /Workspace/Users/$USER/my-custom-mcp \
  -p <profile>
```

Watch logs while it boots:

```bash
databricks apps logs my-custom-mcp -p <profile>
```

Look for:
```
INFO:     Started server process [69]
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

If you see Python tracebacks instead, the most common culprits are missing `requirements.txt` entries or your imports breaking before lifespan startup.

## Grant the app SP access to its data

The Apps platform mints a fresh service principal per app at create-time. Find its client_id and grant whatever your tools read:

```python
app = w.apps.get(name=APP_NAME)
sp_client_id = app.service_principal_client_id
print(f"SP to grant: {sp_client_id}")

# UC reads (warehouses, catalogs, Metric Views, federated catalogs)
for sql in [
    f"GRANT USE CATALOG ON CATALOG my_catalog TO `{sp_client_id}`",
    f"GRANT USE SCHEMA, SELECT ON SCHEMA my_catalog.gold TO `{sp_client_id}`",
    f"GRANT SELECT ON VIEW my_catalog.gold.mv_sales TO `{sp_client_id}`",
]:
    w.statement_execution.execute_statement(
        warehouse_id="<warehouse>", statement=sql, wait_timeout="30s",
    )

# Warehouse CAN_USE
from databricks.sdk.service.iam import AccessControlRequest, PermissionLevel
w.warehouses.update_permissions(
    warehouse_id="<warehouse>",
    access_control_list=[
        AccessControlRequest(service_principal_name=sp_client_id,
                             permission_level=PermissionLevel.CAN_USE)
    ],
)

# Lakebase Postgres role + grants (if your tools read Lakebase)
from databricks.sdk.service.database import (
    DatabaseInstanceRole, DatabaseInstanceRoleIdentityType,
)
try:
    w.database.create_database_instance_role(
        instance_name="<lakebase-instance>",
        database_instance_role=DatabaseInstanceRole(
            name=sp_client_id,
            identity_type=DatabaseInstanceRoleIdentityType.SERVICE_PRINCIPAL,
        ),
    )
except Exception as e:
    if "already" not in str(e).lower(): raise
# Then run GRANT USAGE/SELECT inside Postgres for whichever schemas the tools read.
```

## Smoke-test the deployed server

```bash
TOKEN=$(databricks auth token --profile <p> | jq -r .access_token)
URL="https://my-custom-mcp-<workspace_id>.cloud.databricksapps.com"

# Health (FastAPI's auto-generated root)
curl -fsS -H "Authorization: Bearer $TOKEN" $URL/healthz
# If you don't have /healthz, hit / instead — should return a JSON or HTML status page.

# MCP discovery
curl -fsS -H "Authorization: Bearer $TOKEN" -H "Accept: application/json" $URL/mcp
# Should return 401 + WWW-Authenticate if no token (the Apps-SSO 401-on-JSON case),
# or 200 + a streaming session response if you've authenticated correctly.
```

Then exercise the protocol with the SDK:

```python
from databricks_mcp import DatabricksMCPClient
from databricks.sdk import WorkspaceClient
c = DatabricksMCPClient(server_url=f"{URL}/mcp",
                        workspace_client=WorkspaceClient(profile="<p>"))
tools = c.list_tools()
print([t.name for t in tools])
result = c.call_tool("query_lakebase_orders", {"customer_id": "CUST_001"})
print(result)
```

## Restart-as-recovery

A running MCP-server app can drift into a state where `/healthz` returns 200 but tool calls hang or fail silently — particularly after long idles, mid-deploy aborts, or downstream dependency reboots. **Stop + start cycles cure it**:

```python
import datetime
w.apps.stop_and_wait(name=APP_NAME, timeout=datetime.timedelta(minutes=3))
a = w.apps.start_and_wait(name=APP_NAME, timeout=datetime.timedelta(minutes=5))
print(f"state: {a.app_status.state.value}")  # expect RUNNING
```

Bake a `make restart-mcp` (or equivalent) into your project Makefile — you'll use it more often than you think.

## After deploy

Two next steps depending on how the server is going to be consumed:

- **Direct programmatic clients** (your own agent code, scripts): you're done. `DatabricksMCPClient(server_url=..., workspace_client=...)` is the contract; ship.
- **Agent Bricks / Supervisor Agents / Databricks Assistant**: go to [3-register-in-unity-catalog.md](3-register-in-unity-catalog.md) to register as a UC Connection, then [4-attach-to-supervisor-agent.md](4-attach-to-supervisor-agent.md).

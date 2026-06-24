# 4. Attach to a Supervisor Agent

Once the MCP server is deployed (and optionally registered as a UC Connection — see [3-register-in-unity-catalog.md](3-register-in-unity-catalog.md)), attach it as a Tool on a Supervisor Agent. The supervisor then exposes a single serving endpoint that downstream consumers call.

## Two registration variants

| `tool_type` | Auth model | When to use |
|---|---|---|
| `app` | Supervisor's own SP credentials → `CAN_USE` on the MCP app | Quick demo, no UC wiring needed |
| `uc_connection` | UC's per-user OAuth credential cache, governed | **Production** — real audit trail, per-user consent gating |

Pick **one**. Attaching both with the same MCP server enumerates duplicate tool names and the supervisor rejects everything with `Error: Duplicate tool name 'X' detected for agent 'main'`.

## Create the Supervisor Agent

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.supervisoragents import SupervisorAgent, Tool, App, UcConnection, GenieSpace

w = WorkspaceClient(profile="<p>")

# Idempotent: look up by display_name, else create
sa = None
for existing in w.supervisor_agents.list_supervisor_agents(page_size=100):
    if existing.display_name == "My Orchestrator":
        sa = existing
        break
if sa is None:
    sa = w.supervisor_agents.create_supervisor_agent(
        supervisor_agent=SupervisorAgent(
            display_name="My Orchestrator",
            description="Routes between domain MCP server and analytics surfaces.",
            instructions=(
                "For inventory / order questions, call the `my_mcp_conn` tool. "
                "For analytic aggregates (totals by category / region), route to "
                "the `my_genie_space` tool. Refuse ungrounded questions rather "
                "than substitute concepts."
            ),
        )
    )
print(f"supervisor_agent_id: {sa.supervisor_agent_id}")
print(f"endpoint_name      : {sa.endpoint_name}")
```

The `endpoint_name` is the serving endpoint to call later — typically `mas-<short-id>-endpoint`.

## Attach the MCP tool

### Variant A — `tool_type=app` (no UC wiring)

```python
w.supervisor_agents.create_tool(
    parent=f"supervisor-agents/{sa.supervisor_agent_id}",
    tool_id="my_mcp_app",
    tool=Tool(
        tool_type="app",
        app=App(name="my-custom-mcp"),    # exact Databricks App name (with dashes)
        description=(
            "MCP server exposing my-domain tools: query_lakebase_orders, "
            "query_metric_view, etc."
        ),
    ),
)
```

Auth model: every supervisor invocation runs as the supervisor's own SP, which calls the MCP app's `/mcp` endpoint with bearer auth. The supervisor SP needs **CAN_USE** on the MCP app:

```python
from databricks.sdk.service.apps import AppAccessControlRequest, AppPermissionLevel
mcp = w.apps.get(name="my-custom-mcp")
sup_endpoint_sp = w.serving_endpoints.get(name=sa.endpoint_name).creator  # check actual SP
# (or however your supervisor endpoint's SP is identified in your workspace)
w.apps.update_permissions(
    app_name="my-custom-mcp",
    access_control_list=[
        AppAccessControlRequest(service_principal_name=sup_endpoint_sp,
                                permission_level=AppPermissionLevel.CAN_USE),
    ],
)
```

### Variant B — `tool_type=uc_connection` (UC-governed)

Pre-req: UC Connection exists ([3-register-in-unity-catalog.md](3-register-in-unity-catalog.md)).

```python
w.supervisor_agents.create_tool(
    parent=f"supervisor-agents/{sa.supervisor_agent_id}",
    tool_id="my_mcp_uc",
    tool=Tool(
        tool_type="uc_connection",
        uc_connection=UcConnection(name="my_mcp_conn"),  # UC connection name (underscores)
        description=(
            "UC-governed MCP connection — per-user OAuth credentials, "
            "audit trail in system.access.audit, human-in-the-loop "
            "mcp_approval_request gate on every tool call."
        ),
    ),
)
```

Auth model: each calling user has a refresh token cached by UC. The supervisor mints a fresh access token via UC's token endpoint and uses it to call the MCP server. The MCP server's SSO accepts the token because it's a valid workspace user token with `CAN_USE` on the underlying app.

Required: the user has completed the one-time consent click (layer 4 of the UC registration recipe).

## Optional — attach other tools on the same supervisor

```python
# Genie Space (analytics surface)
w.supervisor_agents.create_tool(
    parent=f"supervisor-agents/{sa.supervisor_agent_id}",
    tool_id="my_genie",
    tool=Tool(
        tool_type="genie_space",
        genie_space=GenieSpace(id="<genie-space-id>"),
        description="Genie space over the canonical Metric View.",
    ),
)
```

The supervisor's instructions (set at `create_supervisor_agent` time) tell the LLM when to route to each tool. Keep instructions ≤ 5 sentences — the LLM gets confused by long routing rules.

## Call the supervisor endpoint

The serving endpoint is OpenAI-compatible with one quirk — the field is `input`, not `messages`:

```python
import httpx, time
host = w.config.host.rstrip("/")
TOKEN = w.config.authenticate()["Authorization"].removeprefix("Bearer ").strip()

t0 = time.perf_counter()
r = httpx.post(
    f"{host}/serving-endpoints/{sa.endpoint_name}/invocations",
    headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    json={"input": [{"role": "user", "content": "What's in order O123's status?"}]},
    timeout=120.0,
)
print(f"HTTP {r.status_code}  ·  {(time.perf_counter()-t0)*1000:.0f} ms")
body = r.json()
```

## Response shape

```json
{
  "id": "resp_<uuid>",
  "status": "completed",
  "output": [
    {
      "type": "message",
      "role": "assistant",
      "content": [{"type": "output_text",
                   "text": "I'll look that up via the MCP server."}]
    },
    {
      "type": "mcp_approval_request",
      "server_label": "my_mcp_conn",       ← matches the tool you attached
      "name": "query_lakebase_orders",
      "arguments": "{\"customer_id\": \"CUST_001\", \"limit\": 10}"
    }
  ]
}
```

The `mcp_approval_request` is **deliberate** — supervisor agents emit an approval request before *actually executing* the tool, so callers can run human-in-the-loop gating. To execute, your caller code needs to send the approval back as a follow-up turn. This is a feature, not a bug — the demo story for governance teams is exactly this.

## Errors you'll hit

| Error | Cause | Fix |
|---|---|---|
| `Duplicate tool name 'X' detected for agent 'main'` | Both `tool_type=app` and `tool_type=uc_connection` attached for the same MCP server | `delete_tool` on one of them |
| `oauth: Credential for user identity('<id>') is not found for the connection` | UC's per-user credential cache is empty for the caller | User opens the connection URL and clicks **Sign in** once |
| `serving endpoint not found` | `sa.endpoint_name` is still provisioning | Wait ~30-60s after `create_supervisor_agent`; re-fetch with `w.supervisor_agents.get_supervisor_agent` |
| Supervisor calls succeed but `mcp_approval_request` never appears | The LLM didn't think a tool call was warranted | Sharpen the tool description; the LLM routes on description quality |

## Detach / cleanup

```python
# Drop a single tool
w.supervisor_agents.delete_tool(
    name=f"supervisor-agents/{sa.supervisor_agent_id}/tools/my_mcp_app",
)

# Drop the supervisor itself (also drops its endpoint)
w.supervisor_agents.delete_supervisor_agent(supervisor_agent_id=sa.supervisor_agent_id)
```

`delete_tool` is the SDK method — `w.supervisor_agents.delete_tool(name="supervisor-agents/<id>/tools/<tool_id>")`. Several REST-API path guesses (e.g. `/api/2.0/agents/supervisor-agents/...`) return 404; the SDK method is the only one that works reliably.

---

When this all works:
- Catalog Explorer → Connections → your connection exists with `is_mcp_connection: true`
- The Supervisor's serving endpoint returns 200 with `mcp_approval_request` referencing your MCP server
- `server_label` matches the registration tool_type you intended (`uc_connection` name for UC-governed, app name for `tool_type=app`)

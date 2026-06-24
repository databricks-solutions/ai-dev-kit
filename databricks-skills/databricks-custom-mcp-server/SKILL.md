---
name: databricks-custom-mcp-server
description: "Build, deploy, and govern a custom Model Context Protocol (MCP) server on Databricks Apps end-to-end — FastMCP server skeleton, tool definitions over Lakebase / UC Metric Views / SQL warehouses, deployment via Databricks Apps, registration as a Unity Catalog Connection (with the no-DCR workaround when the workspace OAuth server lacks `registration_endpoint`), and attachment as a tool on a Supervisor Agent. Use when the user wants to build a custom MCP server, expose internal tools to agents, register an MCP server in Unity Catalog, wire MCP into Supervisor Agents / Agent Bricks, or hit any of the non-obvious gotchas around OAuth Dynamic Client Registration, account-level OAuth integrations, redirect URI allowlists, or duplicate-tool-name conflicts when both `tool_type=app` and `tool_type=uc_connection` route to the same MCP server."
---

# Custom MCP Server on Databricks

Build a custom MCP server that exposes Databricks-native data (Lakebase, Unity Catalog Metric Views, SQL warehouses, federated catalogs) as tools to AI agents — and govern it through Unity Catalog + Supervisor Agents.

This skill captures the **non-obvious cross-product wiring** that doesn't appear in any single doc page: how to make the OAuth handshake survive the Databricks Apps SSO proxy, how to register the server in UC when the workspace doesn't have DCR enabled yet, and how to swap supervisor tool registrations without hitting duplicate-tool-name conflicts.

---

## Critical Rules (always follow)

- **MUST** deploy the MCP server as a Databricks App (the only supported MCP hosting model today). Not a Job, not a model-serving endpoint.
- **MUST** use `FastMCP` from the `mcp` package + FastAPI — same as the official `mcp-server-hello-world` template. Don't roll your own MCP transport.
- **MUST** expose `/mcp` as the streamable-HTTP endpoint. Clients (including Supervisor Agents) hit `<app-url>/mcp`.
- **MUST** authenticate to downstream Databricks resources (Lakebase, warehouses) via `WorkspaceClient()` — *not* hardcoded tokens.
- **MUST** test the deployed server with the SDK's `DatabricksMCPClient` (`pip install databricks-mcp`) before claiming it works.
- **WHEN** registering in UC: if `register_mcp_server_via_dcr` fails with `Authorization Server does NOT support Dynamic Client Registration`, use the **manual four-layer recipe** in [3-register-in-unity-catalog.md](3-register-in-unity-catalog.md). Don't ship a half-registered connection.
- **WHEN** attaching to a Supervisor Agent: pick **one** of `tool_type=app` or `tool_type=uc_connection`, not both. Both routes enumerate the same MCP tool names; the supervisor rejects the duplicates.

---

## When to Use Each Surface

| Surface | When | Tradeoff |
|---|---|---|
| Direct MCP HTTP client (`DatabricksMCPClient`) | Programmatic testing, your own agent code | No governance layer; great for dev |
| Supervisor Agent with `tool_type=app` | Quick demo wiring, no UC registration needed | Uses app's SP credentials; bypasses UC OAuth |
| Supervisor Agent with `tool_type=uc_connection` | **Production** — every call goes through UC's per-user OAuth credential cache | Real audit trail, per-user consent gating, but needs the OAuth wiring in [3-register-in-unity-catalog.md](3-register-in-unity-catalog.md) |

---

## Lifecycle (the four steps that matter)

```
┌─ 1. Build ──────────────────────────────────────────┐
│   FastMCP server + @mcp.tool() decorated functions  │
│   tools wrap Lakebase / Metric View / warehouse SQL │
│   → see [1-build-fastmcp-server.md]                 │
└─────────────────────────────────────────────────────┘
                       ▼
┌─ 2. Deploy ─────────────────────────────────────────┐
│   Upload to /Workspace/Users/<me>/<src>             │
│   databricks apps create / deploy                   │
│   app.yaml: command=["uvicorn", "app:http_app", …]  │
│   → see [2-deploy-as-databricks-app.md]             │
└─────────────────────────────────────────────────────┘
                       ▼
┌─ 3. Register in UC ─────────────────────────────────┐
│   IDEAL  : register_mcp_server_via_dcr(name, url)   │
│   COMMON : Manual four-layer recipe when DCR is off │
│            (Account-admin custom OAuth integration  │
│             → UC HTTP connection + is_mcp_connection│
│             → user consent click)                   │
│   → see [3-register-in-unity-catalog.md]            │
└─────────────────────────────────────────────────────┘
                       ▼
┌─ 4. Attach to Supervisor Agent ─────────────────────┐
│   Tool(tool_type="uc_connection",                   │
│        uc_connection=UcConnection(name=<conn>))     │
│   Detach any duplicate tool_type="app" registration │
│   → see [4-attach-to-supervisor-agent.md]           │
└─────────────────────────────────────────────────────┘
```

---

## Quick Start

```bash
# 1. Scaffold + deploy a hello-world MCP server (~5 min)
databricks bundle init mlops-stacks --template-dir mcp-server-hello-world
cd my-mcp-server
databricks apps create my-mcp-server
databricks apps deploy my-mcp-server --source-code-path /Workspace/Users/<me>/my-mcp-server

# 2. Smoke-test via SDK (verifies streamable HTTP transport + auth)
python -c "
from databricks_mcp import DatabricksMCPClient
from databricks.sdk import WorkspaceClient
c = DatabricksMCPClient(
    server_url='https://my-mcp-server-<workspace_id>.cloud.databricksapps.com/mcp',
    workspace_client=WorkspaceClient(),
)
print(c.list_tools())
"

# 3. Try DCR registration first (works if workspace has it enabled)
python -c "
from databricks_mcp import register_mcp_server_via_dcr
from databricks.sdk import WorkspaceClient
url = register_mcp_server_via_dcr(
    connection_name='my_mcp_conn',
    mcp_url='https://my-mcp-server-<workspace_id>.cloud.databricksapps.com/mcp',
    workspace_client=WorkspaceClient(),
)
print(url)
"
# If DCR works: skip to step 4.
# If it fails with 'Authorization Server does NOT support Dynamic Client Registration':
#    follow the manual four-layer recipe in 3-register-in-unity-catalog.md

# 4. Attach to a Supervisor Agent (uc_connection variant)
# See 4-attach-to-supervisor-agent.md
```

---

## Reference Files

| File | When to read |
|---|---|
| [1-build-fastmcp-server.md](1-build-fastmcp-server.md) | Writing the MCP server itself — tool decorators, OAuth user-token passthrough, Lakebase/MetricView/warehouse helpers |
| [2-deploy-as-databricks-app.md](2-deploy-as-databricks-app.md) | `app.yaml`, `manifest.yaml`, deployment + grants flow, restart-as-recovery |
| [3-register-in-unity-catalog.md](3-register-in-unity-catalog.md) | **THE BIG ONE** — DCR-or-manual-recipe, Apps-SSO 401 quirk, per-user OAuth consent, four-layer permission stack |
| [4-attach-to-supervisor-agent.md](4-attach-to-supervisor-agent.md) | `Tool(tool_type="uc_connection")` shape, duplicate-tool-name conflict, `mcp_approval_request` human-in-the-loop |
| [scripts/register_mcp_in_uc.py](scripts/register_mcp_in_uc.py) | Production-ready idempotent four-layer registration script |

---

## Common Issues

| Issue | Cause | Fix |
|---|---|---|
| `register_mcp_server_via_dcr` fails: *"Expected HTTP 401 from MCP URL, got 200"* | Apps-SSO returns 302→200 HTML for plain GETs; the discovery code follows the redirect | Monkey-patch `requests.get` to send `Accept: application/json` and `allow_redirects=False` before importing `databricks_mcp.connector` |
| DCR fails: *"Authorization Server does NOT support Dynamic Client Registration (missing 'registration_endpoint')"* | Workspace OAuth server hasn't enabled DCR yet | Use the manual four-layer recipe — mint a custom OAuth integration via `AccountClient.custom_app_integration.create`, build a synthetic `dcr_result`, pass it to `databricks_mcp.connector.create_uc_connection` |
| `CREATE CONNECTION TYPE MCP` SQL fails: *"CONNECTION_TYPE_NOT_SUPPORTED"* | There's no first-class `MCP` connection type in UC yet | Use `TYPE HTTP` + `is_mcp_connection: "true"` in options — UC and Supervisor Agents recognise MCP via that flag |
| User-consent click fails: *"redirect_uri not registered for OAuth application"* | The app's auto-provisioned OAuth client doesn't allowlist UC's consent landing page (`/login/oauth/http.html`) | Account admin must create a **separate** custom OAuth integration with that redirect URI in `redirect_urls`. The Apps-platform-managed OAuth client is not patchable. |
| Supervisor: *"Duplicate tool name 'resolve_concept' detected for agent 'main'"* | Both `tool_type=app` and `tool_type=uc_connection` registrations enumerate the same MCP tool names | Detach one. Use `w.supervisor_agents.delete_tool(name=…)` before attaching the other |
| Supervisor: *"Credential for user identity('<id>') is not found for the connection"* | UC's per-user OAuth credential cache is empty for that user | User opens the connection URL once in a browser and clicks Sign in. Credential cached; subsequent calls succeed silently until refresh-token rotation |

---

## Validation Checklist

Before claiming "the MCP server is registered in Unity Catalog and the Supervisor calls through it":

```
- [ ] Deployed app's /mcp endpoint returns 401+JSON for unauth GET with Accept: application/json
- [ ] DatabricksMCPClient.list_tools() returns expected tool names with workspace OAuth bearer auth
- [ ] UC Connection visible in Catalog Explorer → Connections → <name>
- [ ] Connection options include is_mcp_connection: "true"
- [ ] At least one user has completed the per-user OAuth consent click
- [ ] Supervisor's list_tools shows tool_type=uc_connection registration
- [ ] No tool_type=app registration on the same supervisor (would duplicate tool names)
- [ ] Calling the supervisor endpoint returns mcp_approval_request with server=<UC connection name>, not <app name>
```

That last line is the verification that matters most — `server_label` in the supervisor response is `<connection_name>` (underscore-style) when the call routes through UC, vs `<app-name>` (dash-style) when it uses `tool_type=app`. One character of difference, all the governance story rides on it.

---

## Related Skills

- **[databricks-app-python](../databricks-app-python/SKILL.md)** — General Databricks Apps deployment (auth, app.yaml, frameworks). The MCP server is a specific kind of Databricks App; that skill covers the platform basics.
- **[databricks-python-sdk](../databricks-python-sdk/SKILL.md)** — WorkspaceClient + AccountClient setup, profiles.
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** — UC Connections, permissions, catalog discovery.
- **[databricks-lakebase-provisioned](../databricks-lakebase-provisioned/SKILL.md)** — Lakebase OAuth credential rotation; relevant for MCP tools that read Lakebase.
- **[databricks-metric-views](../databricks-metric-views/SKILL.md)** — `MEASURE()` semantics; relevant for MCP tools that wrap Metric Views.

## Upstream References

- **Stock template**: Databricks publishes `mcp-server-hello-world` as a Databricks Apps starter. Use as a skeleton; replace tools.
- **`databricks-mcp` package** (`pip install databricks-mcp`): contains `DatabricksMCPClient`, `register_mcp_server_via_dcr`, and the internal helpers (`discover_protected_resource_metadata`, `create_uc_connection`) we hijack in the manual recipe.
- **`mcp` package** (`pip install mcp`): the official MCP protocol library; `FastMCP` is your entry point.
- **MCP spec**: https://modelcontextprotocol.io/specification

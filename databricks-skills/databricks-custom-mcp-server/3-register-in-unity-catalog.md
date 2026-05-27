# 3. Register the MCP Server in Unity Catalog

There are two paths:

1. **`register_mcp_server_via_dcr()`** — the supported, one-call path. **Try this first.** Works only on workspaces where the OAuth Authorization Server has Dynamic Client Registration enabled.

2. **Manual four-layer recipe** — when DCR isn't enabled (more common than docs suggest as of 2026-05). Requires account-admin perms; ~5 minutes of scripted work + 1 user click.

Both paths end with a UC Connection visible in Catalog Explorer → Connections, with `is_mcp_connection: "true"` in its options — that's the flag UC and Supervisor Agents use to recognise an MCP server.

---

## Path 1 — DCR (try first)

```python
import requests
from databricks.sdk import WorkspaceClient
from databricks_mcp import register_mcp_server_via_dcr

# CRITICAL pre-step: patch requests.get so the discovery handshake works
# behind the Databricks Apps SSO proxy. Without this, an unauthenticated
# GET to /mcp returns 302→200 HTML (workspace login page) instead of the
# 401+JSON the discovery code expects.
_orig_get = requests.get
def _patched_get(url, **kw):
    headers = kw.pop("headers", {}) or {}
    headers.setdefault("Accept", "application/json")
    kw.setdefault("allow_redirects", False)
    return _orig_get(url, headers=headers, **kw)
requests.get = _patched_get

url = register_mcp_server_via_dcr(
    connection_name="my_mcp_conn",
    mcp_url="https://my-mcp-server-<workspace_id>.cloud.databricksapps.com/mcp",
    workspace_client=WorkspaceClient(profile="<p>"),
)
print(url)
```

If this returns a URL pointing at `/explore/connections/my_mcp_conn`, DCR worked. Skip to [4-attach-to-supervisor-agent.md](4-attach-to-supervisor-agent.md).

### Likely failure modes

| Error | Meaning | Path forward |
|---|---|---|
| `RuntimeError: Expected HTTP 401 from MCP URL, got 200` | You skipped the `requests.get` patch above | Apply the patch, retry |
| `Authorization Server does NOT support Dynamic Client Registration (missing 'registration_endpoint')` | Workspace OAuth doesn't expose DCR | **Switch to Path 2** below |
| `HTTPStatusError: '401 Unauthorized' on /mcp` | The caller's SP doesn't have `CAN_USE` on the MCP app | Run `w.apps.update_permissions(app_name=…, access_control_list=[…CAN_USE])` |

---

## Path 2 — Manual four-layer recipe (no-DCR workaround)

Use this when path 1 fails with the DCR error. The recipe is:

```
Layer 1: Account admin creates a custom OAuth integration with the right redirect URIs
Layer 2: Workspace user creates a UC HTTP connection embedding that integration's credentials
Layer 3: Workspace user detaches any duplicate tool_type=app on the supervisor (if applicable)
Layer 4: End user clicks the consent link once per identity
```

### Layer 1 — Custom OAuth integration (account admin)

Why the auto-provisioned client doesn't work: every Databricks App ships with a `oauth2_app_client_id` (`w.apps.get(name).oauth2_app_client_id`). That client's `redirect_urls` allowlist contains the **app's own** callback only — *not* UC's consent landing page (`<workspace>/login/oauth/http.html`). And: that client is **not patchable** by callers (`AccountClient.custom_app_integration.get(integration_id=<that_id>)` returns `Not Found` — it's platform-owned).

So mint a fresh integration:

```python
from databricks.sdk import AccountClient

# IMPORTANT: this must be an account-scoped profile, not workspace.
# Account profiles have `account_id` + `host = https://accounts.<cloud>.databricks.net`.
ac = AccountClient(profile="<account-admin-profile>")

new = ac.custom_app_integration.create(
    name="my-mcp-uc-client",
    confidential=True,
    redirect_urls=[
        # The UC connection consent landing page — note `/login/oauth/http.html`
        "https://<workspace-host>/login/oauth/http.html",
    ],
    scopes=["all-apis", "offline_access"],
)
print(f"client_id    : {new.client_id}")
print(f"client_secret: {new.client_secret}    ← only shown once!")
```

**Required perms**: account admin. A workspace admin or metastore admin will hit `Not Found` on `custom_app_integration.list/get/create`.

**Save the `client_secret` immediately** — Databricks doesn't show it again. For a non-demo deployment, store it in a Databricks Secret scope and reference it via `secret_ref` in the connection options.

### Layer 2 — UC HTTP Connection

There is **no `MCP` connection type** in UC (as of 2026-05). `CREATE CONNECTION TYPE MCP` returns `CONNECTION_TYPE_NOT_SUPPORTED`. Instead, use type `HTTP` with `is_mcp_connection: "true"`:

```python
from databricks.sdk.service import catalog
w = WorkspaceClient(profile="<workspace-profile>")

# Drop any prior connection with the same name (idempotency)
try: w.connections.delete("my_mcp_conn")
except Exception: pass

w.connections.create(
    name="my_mcp_conn",
    connection_type=catalog.ConnectionType.HTTP,
    options={
        "host":                              "https://my-mcp-server-<id>.cloud.databricksapps.com",
        "port":                              "443",
        "base_path":                         "/mcp",
        "oauth_credential_exchange_method":  "header_and_body",
        "client_id":                         new.client_id,
        "client_secret":                     new.client_secret,
        "authorization_endpoint":            f"<workspace-host>/oidc/v1/authorize",
        "token_endpoint":                    f"<workspace-host>/oidc/v1/token",
        "oauth_scope":                       "all-apis offline_access",
        "is_mcp_connection":                 "true",
    },
    comment="My custom MCP server, UC-registered.",
)
```

UC will accept the credentials and create the connection — but it will **not validate the redirect URI allowlist at create time**. Validation happens at consent (layer 4).

### Layer 3 — Detach duplicate supervisor registration (if applicable)

If you previously attached this MCP server as `tool_type=app` on a supervisor (e.g., during prototyping), **detach it now**:

```python
SUPERVISOR_ID = "<your-supervisor-id>"
try:
    w.supervisor_agents.delete_tool(
        name=f"supervisor-agents/{SUPERVISOR_ID}/tools/<old_app_tool_id>",
    )
    print("detached old tool_type=app registration")
except Exception:
    pass  # not attached, nothing to do
```

Why: both routes will enumerate the same MCP tool names. The supervisor's main agent rejects with:

> `Error: Duplicate tool name 'resolve_concept' detected for agent 'main'.`

This catches you ~5 minutes after first wiring up the UC route. Pre-empt it.

### Layer 4 — Per-user OAuth consent (one human click)

After layers 1-3, the first time a user calls through the supervisor, they'll see:

```
error: {
  code: "oauth",
  message: "Credential for user identity('<user_id>') is not found for the
            connection 'my_mcp_conn'. Please login first to the connection by
            visiting https://<workspace>/explore/connections/my_mcp_conn"
}
```

**This is OAuth working as designed** — UC stores credentials per `(user_id, connection_name)` for audit + governance. The user opens that URL, clicks **Sign in**, completes the consent screen, and lands back on the connection page. UC caches a refresh token; every subsequent supervisor call routes silently until the refresh token rotates out (typically months).

If the consent fails with `invalid_request: redirect_uri ... not registered for OAuth application`, the layer-1 integration's `redirect_urls` doesn't include the right URI. Re-mint with `--rotate-secret` and make sure `redirect_urls` contains exactly `https://<workspace>/login/oauth/http.html`.

---

## Verification — the one character that proves it works

After the consent click, call the supervisor's serving endpoint:

```bash
curl -sS \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"input":[{"role":"user","content":"<a question that should hit your MCP server>"}]}' \
  https://<workspace>/serving-endpoints/<supervisor-endpoint>/invocations
```

Find the `mcp_approval_request` event in the response:

```json
{
  "type": "mcp_approval_request",
  "server_label": "my_mcp_conn",            ← UC Connection name (underscore-style)
  "name": "query_lakebase_orders",
  "arguments": "{\"customer_id\": \"CUST_001\"}"
}
```

If `server_label` is the **UC Connection name** (`my_mcp_conn`, underscores), you're routing through UC. If it's the **app name** (`my-mcp-server`, dashes), you're still on the `tool_type=app` route — go back to layer 3 and detach it.

That one-character difference (`_` vs `-`) is the verification that matters.

---

## Production hardening

- **Secrets**: move `client_secret` from a literal option to a Databricks Secret reference. UC encrypts options at rest, but secrets are still better practice.
- **Scopes**: prune `oauth_scope` to the minimum your MCP server's tools need. `all-apis` works but is overscoped.
- **Per-user grants**: confirm every user who'll call the supervisor has been granted `USE CONNECTION` on the connection itself.
- **Rotation**: the custom OAuth integration's secret rotates manually via `--rotate-secret`. Set a calendar reminder.
- **Audit**: UC logs every connection invocation under `system.access.audit`. Wire that into your monitoring.

See [scripts/register_mcp_in_uc.py](scripts/register_mcp_in_uc.py) for an idempotent reference implementation of the full four-layer recipe.

When this all works → [4-attach-to-supervisor-agent.md](4-attach-to-supervisor-agent.md).

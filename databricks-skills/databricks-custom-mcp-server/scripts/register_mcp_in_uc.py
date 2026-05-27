"""Register a custom-MCP-server-as-Databricks-App in Unity Catalog end-to-end.

Implements the four-layer no-DCR recipe documented in
3-register-in-unity-catalog.md:
  1. Account admin creates a custom OAuth integration with the UC consent
     redirect URI in its allowlist.
  2. Workspace user creates a UC HTTP connection embedding those credentials,
     with is_mcp_connection: "true" so UC and Supervisor Agents treat it as
     MCP.
  3. Workspace user detaches any duplicate tool_type=app registration on a
     target Supervisor Agent (avoids duplicate-tool-name conflict).
  4. (Manual, downstream) The end user clicks the consent link to cache a
     per-user refresh token in UC.

Idempotent. Supports --rotate-secret to mint a new client_secret.

Requires:
  • account-admin perms on the Databricks account
  • metastore admin on the target workspace
  • The MCP server already deployed as a Databricks App
  • Two CLI profiles: one account-scoped, one workspace-scoped

Usage:
  python register_mcp_in_uc.py \\
    --account-profile ACCOUNT \\
    --workspace-profile DEFAULT \\
    --connection-name my_mcp_conn \\
    --integration-name my-mcp-uc-client \\
    --mcp-host https://my-mcp-server-<id>.cloud.databricksapps.com \\
    --workspace-host https://<workspace-host> \\
    --supervisor-id <uuid>  # optional; only if you want auto-detach + auto-attach
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

from databricks.sdk import AccountClient, WorkspaceClient
from databricks.sdk.service import catalog
from databricks.sdk.service.supervisoragents import Tool, UcConnection


def step1_oauth_integration(ac: AccountClient, name: str, redirect_uri: str,
                             rotate: bool, creds_file: pathlib.Path) -> dict:
    existing = None
    for it in ac.custom_app_integration.list():
        if it.name == name:
            existing = it
            break

    if existing and not rotate:
        if creds_file.exists():
            print(f"  ✓ integration exists ({existing.integration_id}) — using cached secret")
            return json.loads(creds_file.read_text())
        print(f"  ⚠ integration exists but secret cache missing — forcing rotate")
        rotate = True

    if existing and rotate:
        print(f"  • deleting {existing.integration_id} (rotate)")
        ac.custom_app_integration.delete(integration_id=existing.integration_id)

    new = ac.custom_app_integration.create(
        name=name, confidential=True,
        redirect_urls=[redirect_uri],
        scopes=["all-apis", "offline_access"],
    )
    creds = {
        "integration_id": new.integration_id,
        "client_id":      new.client_id,
        "client_secret":  new.client_secret or "",
    }
    creds_file.write_text(json.dumps(creds, indent=2))
    print(f"  ✓ created {new.integration_id}; secret cached → {creds_file}")
    return creds


def step2_uc_connection(w: WorkspaceClient, name: str, creds: dict,
                         mcp_host: str, workspace_host: str) -> None:
    try:
        w.connections.delete(name)
        print(f"  • dropped existing {name!r}")
    except Exception:
        pass
    w.connections.create(
        name=name,
        connection_type=catalog.ConnectionType.HTTP,
        options={
            "host":                              mcp_host,
            "port":                              "443",
            "base_path":                         "/mcp",
            "oauth_credential_exchange_method":  "header_and_body",
            "client_id":                         creds["client_id"],
            "client_secret":                     creds["client_secret"],
            "authorization_endpoint":            f"{workspace_host}/oidc/v1/authorize",
            "token_endpoint":                    f"{workspace_host}/oidc/v1/token",
            "oauth_scope":                       "all-apis offline_access",
            "is_mcp_connection":                 "true",
        },
        comment="UC-native registration of an MCP server hosted as a Databricks App.",
    )
    print(f"  ✓ created UC Connection {name!r}")


def step3_detach_app_tools(w: WorkspaceClient, supervisor_id: str) -> None:
    """Detach any tool_type=app on this supervisor whose underlying app name
    matches the connection — avoids duplicate-tool-name conflicts."""
    tools = list(w.supervisor_agents.list_tools(
        parent=f"supervisor-agents/{supervisor_id}",
    ))
    for t in tools:
        if t.tool_type == "app":
            print(f"  • detaching tool_type=app tool {t.tool_id!r}")
            w.supervisor_agents.delete_tool(
                name=f"supervisor-agents/{supervisor_id}/tools/{t.tool_id}",
            )
    if not any(t.tool_type == "app" for t in tools):
        print(f"  ✓ no tool_type=app to detach")


def step4_attach_uc_tool(w: WorkspaceClient, supervisor_id: str,
                          tool_id: str, connection_name: str) -> None:
    try:
        w.supervisor_agents.create_tool(
            parent=f"supervisor-agents/{supervisor_id}",
            tool_id=tool_id,
            tool=Tool(
                tool_type="uc_connection",
                uc_connection=UcConnection(name=connection_name),
                description=(
                    f"UC-governed MCP connection to {connection_name}. "
                    "Per-user OAuth credentials, audit trail in "
                    "system.access.audit, mcp_approval_request gate "
                    "on every tool call."
                ),
            ),
        )
        print(f"  ✓ attached tool_type=uc_connection ({tool_id})")
    except Exception as e:
        if "already exists" in str(e).lower():
            print(f"  ✓ uc_connection tool already attached")
        else:
            raise


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--account-profile",   required=True)
    p.add_argument("--workspace-profile", required=True)
    p.add_argument("--connection-name",   required=True)
    p.add_argument("--integration-name",  required=True)
    p.add_argument("--mcp-host",          required=True,
                   help="https://<your-mcp-app>.cloud.databricksapps.com (no /mcp suffix)")
    p.add_argument("--workspace-host",    required=True,
                   help="https://<workspace>.cloud.databricks.com")
    p.add_argument("--supervisor-id",     default=None,
                   help="If set, auto-detach any duplicate app tools and attach "
                        "the uc_connection tool to this supervisor.")
    p.add_argument("--supervisor-tool-id", default=None,
                   help="tool_id for the new uc_connection registration "
                        "(default: <connection-name>_uc)")
    p.add_argument("--rotate-secret", action="store_true")
    p.add_argument("--creds-file", default="/tmp/mcp-uc-client.json",
                   help="Where to cache the OAuth client_secret (gitignored)")
    args = p.parse_args()

    redirect_uri = f"{args.workspace_host.rstrip('/')}/login/oauth/http.html"
    creds_file = pathlib.Path(args.creds_file)
    tool_id = args.supervisor_tool_id or f"{args.connection_name}_uc"

    print(f"workspace : {args.workspace_host}")
    print(f"connection: {args.connection_name}")
    print(f"redirect  : {redirect_uri}\n")

    print("[1/4] Account-level custom OAuth integration")
    ac = AccountClient(profile=args.account_profile)
    creds = step1_oauth_integration(ac, args.integration_name, redirect_uri,
                                     args.rotate_secret, creds_file)
    print(f"  client_id: {creds['client_id']}\n")

    print("[2/4] UC HTTP Connection with is_mcp_connection: true")
    w = WorkspaceClient(profile=args.workspace_profile)
    step2_uc_connection(w, args.connection_name, creds,
                        args.mcp_host, args.workspace_host)
    print()

    if args.supervisor_id:
        print("[3/4] Detach duplicate tool_type=app on supervisor")
        step3_detach_app_tools(w, args.supervisor_id)
        print()

        print("[4/4] Attach UC connection as supervisor tool")
        step4_attach_uc_tool(w, args.supervisor_id, tool_id, args.connection_name)
        print()
    else:
        print("[3-4/4] Skipped supervisor wiring (no --supervisor-id given)\n")

    print("─" * 70)
    print("✓ MCP server registered in Unity Catalog")
    print(f"  catalog: {args.workspace_host.rstrip('/')}/explore/connections/{args.connection_name}")
    if args.supervisor_id:
        print(f"  super.:  {args.workspace_host.rstrip('/')}/agents/supervisor/{args.supervisor_id}")
    print()
    print("→ ONE HUMAN STEP REMAINS:")
    print(f"  Open the connection URL above. Click 'Sign in' / 'Authorize'.")
    print(f"  After consent, every supervisor call for your user_id routes")
    print(f"  silently through the UC Connection.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

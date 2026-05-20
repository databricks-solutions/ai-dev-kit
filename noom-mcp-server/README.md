# noom-mcp-server

A governance extension layer over the upstream
[databricks-mcp-server](../databricks-mcp-server/README.md).  It monkey-patches
three SQL governance controls at startup — PAT rejection, Service Principal SQL
execution, and per-user query tagging — **without modifying any upstream file**.
See [DESIGN.md](DESIGN.md) for the full viability analysis and design rationale.

## Architecture

```
run.py
  ├── apply_all_patches()          ← Noom governance, applied before server starts
  │     ├── check_upstream_version   version pin guard
  │     ├── patch_sql_executor       SP client + warehouse override, mcp_user tagging
  │     └── check_pat_rejected       live auth check: PAT rejected, OAuth required
  └── databricks_mcp_server.server.mcp.run()   ← upstream FastMCP server, unchanged
```

All SQL issued through the MCP server is:
- Executed by a fixed Service Principal (not the calling user's credentials)
- Routed to the designated production SQL warehouse
- Tagged with `mcp_user:<email>` in `system.query.history` for audit and cost attribution

Non-SQL tools (jobs, Unity Catalog, compute, etc.) continue to use the calling
user's own credentials and are not affected by the patches.

## Prerequisites

- Python ≥ 3.10
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Databricks OAuth access (PAT tokens are rejected at startup)
- READ permission on the `dbrix_mcp_secret` secret scope (provisioned by an admin)

## Environment variables

Copy `.env.example` and fill in the values:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|---|---|---|
| `DATABRICKS_HOST` | Yes | Your Databricks workspace URL (e.g. `https://noom-prod.cloud.databricks.com`). Used for OAuth identity resolution. |
| `DATABRICKS_MCP_SQL_HOST` | Yes | Workspace URL where SQL runs. Set to prod — keeps SQL pinned to prod even if `DATABRICKS_HOST` changes. |
| `DATABRICKS_WAREHOUSE_ID` | Yes | ID of the production SQL warehouse every query is routed to. |

The Service Principal credentials are fetched automatically from the
`dbrix_mcp_secret` Databricks secret scope at startup. You only need the
variables above in your `.env`.

### Dev / CI overrides

To skip the secret scope (e.g. in CI without Databricks Secrets access), set
the SP credentials directly as environment variables:

| Variable | Description |
|---|---|
| `DATABRICKS_MCP_SQL_CLIENT_ID` | SP client ID (bypasses secret scope lookup) |
| `DATABRICKS_MCP_SQL_CLIENT_SECRET` | SP client secret (required when `CLIENT_ID` is set) |

Do not use this in production — secrets are visible in process environment and
shell history.

## Admin setup

An admin must provision the secret scope once against the prod workspace:

```bash
databricks secrets create-scope dbrix_mcp_secret
databricks secrets put-secret dbrix_mcp_secret sql-sp-client-id     --string-value <sp-client-id>
databricks secrets put-secret dbrix_mcp_secret sql-sp-client-secret --string-value <sp-client-secret>
databricks secrets put-acl    dbrix_mcp_secret <group-or-user> READ
```

End users need READ access on the scope but never see the raw secret values.

## Running the server

```bash
cd noom-mcp-server
uv run python run.py
```

The server exits with code 2 on a version mismatch (`UpstreamChangedError`) and
code 1 on any other startup failure.

## Running the tests

**Unit tests** — no credentials needed:

```bash
cd noom-mcp-server
uv run pytest tests/ -v
```

**Integration tests** — requires a live Databricks connection and a populated `.env`:

```bash
cd noom-mcp-server
./run_integration_tests.sh
```

The integration test verifies that SQL runs as the Service Principal (not the
calling user) by comparing `SELECT current_user()` output.

## Upgrading the upstream

When a new upstream release lands (the repo `VERSION` file changes):

1. Check whether `SQLExecutor.__init__` or `.execute` signatures changed in
   [`databricks-tools-core/databricks_tools_core/sql/sql_utils/executor.py`](../databricks-tools-core/databricks_tools_core/sql/sql_utils/executor.py).
   Update the patch wrappers in `noom_mcp/sql_executor_patch.py` if needed.
2. Run the unit tests: `uv run pytest tests/ -v`
3. Bump `PATCHED_UPSTREAM_VERSION` in `noom_mcp/version_check.py` to the new version.
4. Run the integration tests to confirm SQL governance is still enforced.

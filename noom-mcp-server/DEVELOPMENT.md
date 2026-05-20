# Development Guide

## Admin setup: SQL Service Principal credentials

An admin must first provision the secret scope and store the SP credentials.
End users need READ access on the scope (see below) but never interact with the secret values directly.

Run this once against the prod workspace:

```bash
databricks secrets create-scope dbrix_mcp_secret
databricks secrets put-secret dbrix_mcp_secret sql-sp-client-id     --string-value <client-id>
databricks secrets put-secret dbrix_mcp_secret sql-sp-client-secret --string-value <client-secret>
databricks secrets put-acl    dbrix_mcp_secret <group-or-user> READ
```

Users need READ on the scope but never see the raw secret values.

---

## Workspace hosts

Both `DATABRICKS_HOST` (OAuth / identity) and `DATABRICKS_MCP_SQL_HOST` (SQL execution)
should always point to prod.  If you change `DATABRICKS_MCP_SQL_HOST` to a dev/staging
workspace for testing, change `DATABRICKS_HOST` to match — otherwise the `mcp_user:` tag
will reflect a prod identity running SQL on a dev warehouse, which is confusing.

---

## Dev / CI: credentials via env vars

When running locally without Databricks Secrets access (e.g. in CI), set the
SP credentials directly as environment variables. The secret scope lookup is
skipped when `DATABRICKS_MCP_SQL_CLIENT_ID` is set.

```bash
export DATABRICKS_MCP_SQL_CLIENT_ID=<service-principal-client-id>
export DATABRICKS_MCP_SQL_CLIENT_SECRET=<service-principal-client-secret>
export DATABRICKS_MCP_SQL_HOST=https://noom-prod.cloud.databricks.com
```

Do not use this approach in production — the secret is visible in the process
environment and shell history.

---

## Running the test suite

**Unit tests** (no credentials needed):

```bash
pytest tests/ -v
```

**Integration tests** (live Databricks required):

```bash
./run_integration_tests.sh
```

`DATABRICKS_WAREHOUSE_ID` is set in `.env` and injected by the server patch into every SQL execution — the AI client does not need to know or supply it.

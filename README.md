# Noom — Databricks AI Dev Kit

This is Noom's **governed fork** of [databricks-solutions/ai-dev-kit](https://github.com/databricks-solutions/ai-dev-kit).

## Getting started

**→ Follow [`noom-mcp-server/README.md`](noom-mcp-server/README.md)**

That's the only component Noom engineers need. It installs MCP client for Claude Desktop, Cursor, and Claude Code.

## Why a fork?

Noom wraps the upstream MCP server with three SQL governance controls:

- **PAT rejection** — Enforce OAuth; personal access tokens are blocked at startup
- **Service Principal execution** — all SQL runs as a governed SP, not your personal credentials
- **Per-user query tagging** — every query is tagged `mcp_user:<email>` in `system.query.history` for audit and cost attribution

## PII safety

The governed Service Principal does not have access to PII columns in Unity Catalog. SQL results returned through this MCP are PII-free by construction, making it safe to use with AI coding tools.

If your work genuinely requires querying PII data, reach out to the data platform team to discuss access options outside this MCP.

## What NOT to use

The scripts below install the **unpatched upstream server** without Noom's governance controls. Do not use them:

- `install.sh`
- `install.ps1`
- `databricks-mcp-server/setup.sh`

## Upstream components (read-only)

Everything outside `noom-mcp-server/` is upstream code. Do not modify it in this fork — changes belong in the [upstream repo](https://github.com/databricks-solutions/ai-dev-kit).

| Directory | Description |
|---|---|
| `databricks-mcp-server/` | Upstream MCP server (used as a dependency) |
| `databricks-tools-core/` | Upstream Python library |
| `databricks-skills/` | Upstream skill files |
| `databricks-builder-app/` | Upstream web app |

To pull in upstream bug fixes or new features, see the "Sync the upstream" section in [`noom-mcp-server/README.md`](noom-mcp-server/README.md).

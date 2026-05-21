# Noom — Databricks AI Dev Kit

This is Noom's **governed fork** of [databricks-solutions/ai-dev-kit](https://github.com/databricks-solutions/ai-dev-kit).

## Getting started

**→ Follow [`noom-mcp-server/README.md`](noom-mcp-server/README.md)**

That's the only component Noom engineers need. It installs in under 5 minutes and includes MCP client config snippets for Claude Desktop, Cursor, and Claude Code.

## Why a fork?

Noom wraps the upstream MCP server with three SQL governance controls:

- **PAT rejection** — OAuth only; personal access tokens are blocked at startup
- **Service Principal execution** — all SQL runs as a governed SP, not your personal credentials
- **Per-user query tagging** — every query is tagged `mcp_user:<email>` in `system.query.history` for audit and cost attribution

These controls live entirely in [`noom-mcp-server/`](noom-mcp-server/) and do not modify any upstream file.

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

# Noom MCP Server — Design & Viability Analysis

## Goal

Validate whether a **monkey-patch / thin extension** approach can apply Noom's SQL governance
controls to the upstream `databricks-mcp-server` without modifying any file inside
`databricks-mcp-server/` or `databricks-tools-core/`.

The alternative is **copy-and-modify**: copy the upstream files we need to change, edit those
copies, and accept the merge cost on every upstream update.

---

## What we implemented

```
noom-mcp-server/
├── pyproject.toml        # depends on both upstream packages via local path sources
├── run.py                # entry point: patches → import upstream server → mcp.run()
├── .env.example          # required env vars
├── DESIGN.md             # this file
└── noom_mcp/
    ├── __init__.py
    └── patches.py        # all three governance patches
```

`run.py` does three things in order:
1. Call `apply_all_patches()` — installs class-level patches on `SQLExecutor` and validates auth.
2. `from databricks_mcp_server.server import mcp` — creates the FastMCP instance and registers all tools.
3. `mcp.run()` — starts the server.

No files inside `databricks-mcp-server/` or `databricks-tools-core/` are touched.

---

## The three changes

### Change 1 — PAT rejection (`check_pat_rejected`)

**Mechanism:** After `apply_all_patches()` imports `get_workspace_client()` and calls
`current_user.me()`, the SDK resolves and caches `client.config.auth_type`.  We inspect
it and raise `RuntimeError` if it's `"pat"`.

**Fragility:** Low.  The Databricks Python SDK has used `config.auth_type` as a stable
public field across versions.  The only risk is if the SDK stops populating it before
an API call — unlikely.

**Where it lives in the POC branch:** `validate_oauth_auth()` was added to `auth.py`
(same logic); our `check_pat_rejected()` in `patches.py` is its equivalent called from
`run.py` at startup.

---

### Change 2 — SQL SP override (`patch_sql_executor` → `__init__` patch)

**Mechanism:** We replace `SQLExecutor.__init__` with a wrapper that always passes
`client=get_sql_sp_client()` to the original `__init__`, ignoring whatever client
the caller supplied.

**Why this covers `execute_sql_multi` too:**
`SQLParallelExecutor.__init__` (line 49) does:
```python
self.sql_executor = SQLExecutor(warehouse_id=warehouse_id, client=self.client)
```
Since we patched `SQLExecutor.__init__`, the `client` argument it receives (which would
be the user's client) is discarded and replaced with the SP client.

**Fragility:** Low–medium.  This depends on `SQLExecutor` remaining the single chokepoint
for all SQL execution (true today and structurally stable).  If upstream adds a new
executor class that bypasses `SQLExecutor`, the patch would miss it — but this would
require a significant refactor.

**Import-order safety:** The tool functions in `tools/sql.py` do not capture a reference
to `SQLExecutor` at import time; they look it up at call time via the module.  Patching
the class before the first tool invocation is sufficient regardless of import order.

---

### Change 3 — User identity tagging (`patch_sql_executor` → `execute` patch)

**Mechanism:** We replace `SQLExecutor.execute` with a wrapper that appends
`"mcp_user:<identity>"` to `query_tags` before forwarding to the original method.
`get_mcp_user_identity()` resolves the user's email (OAuth browser/CLI) or
`"sp:<client_id>"` (OAuth M2M) or `"unknown"`.

**Note on identity resolution timing:** `get_mcp_user_identity()` calls
`get_current_username()` from the upstream `auth.py`, which calls
`get_workspace_client()` using the *user's* credentials (not the SP).  This is correct:
we resolve identity while the user's auth context is still in effect, then the patched
`__init__` switches to the SP for actual execution.

**Fragility:** Low.  Depends only on `SQLExecutor.execute`'s signature remaining stable.
The signature has been stable since this class was introduced.

---

## Monkey-patch vs FastMCP tool registry patching

The prompt asked specifically whether FastMCP's tool registry could be patched instead
(removing and re-registering tools, or using middleware).

**Tool registry patching (`mcp.remove_tool` / `mcp.add_tool`):**
- FastMCP 3.x *does* expose a public API: `list_tools()`, `get_tool()`,
  `remove_tool()`, `add_tool()`.  (Verified at runtime — 44 tools registered,
  `_tool_manager` is internal but the public methods are stable.)
- We could call `mcp.remove_tool("execute_sql")` and re-register a new version.
- **Problem:** The tool wrapper functions in `tools/sql.py` hardcode
  `_execute_sql` and `_execute_sql_multi` as closed-over locals (captured at
  import time via `from databricks_tools_core.sql import execute_sql as _execute_sql`).
  Even if we swap the tool in the registry, the new wrapper would still need to
  re-implement the full tool body to call our governed executor.  That's more
  invasive than patching the class the tool already delegates to.

**Middleware approach:**
- `mcp.add_middleware(...)` intercepts tool calls at the JSON-RPC level.
- Middleware sees `context.message.name` and `context.message.arguments`.
- **Problem:** We need to inject a `WorkspaceClient` into the executor, not just
  modify the tool arguments.  Middleware cannot intercept Python-level object creation
  inside the tool's call stack.  It could mutate `arguments["query_tags"]`, but it
  cannot redirect which client `SQLExecutor` uses.

**Verdict:** Class-level patching of `SQLExecutor` is more stable, more correct, and
requires no FastMCP internals knowledge.  Middleware is not the right abstraction for
these changes.

---

## Minimal copy-and-modify alternative

If monkey-patching becomes untenable (e.g. upstream refactors `SQLExecutor` away), the
minimal copy-and-modify scope would be:

| File to copy | Change |
|---|---|
| `databricks-tools-core/databricks_tools_core/auth.py` | Add `get_sql_sp_client()`, `get_mcp_user_identity()`, `validate_oauth_auth()` |
| `databricks-mcp-server/databricks_mcp_server/tools/sql.py` | Use `get_sql_sp_client()` + inject user tag in `execute_sql` and `execute_sql_multi` |

That's exactly what the `bei/poc_custom_mcp` branch does.  Two files, ~100 lines of
additions.  The merge cost on upstream updates is bounded: `auth.py` changes rarely,
and `tools/sql.py` changes only when SQL tool signatures change.

---

## Verdict

**Monkey-patching is viable** for these three controls:

| Control | Mechanism | Fragility |
|---|---|---|
| PAT rejection | Startup `config.auth_type` check | Low |
| SQL SP override | `SQLExecutor.__init__` class patch | Low–medium |
| User identity tagging | `SQLExecutor.execute` class patch | Low |

The approach is stable because all three patch points are stable public/internal
interfaces that change rarely.  The class-level patch survives across FastMCP versions
because it doesn't touch FastMCP at all.

The main ongoing risk: if upstream introduces a second SQL executor class that bypasses
`SQLExecutor`, the SP override and tagging patches would silently not apply to it.
A lightweight integration test that verifies query_tags and client identity on actual
SQL calls would catch this regression.

---

## Open question: distribution (deferred)

Today `noom-mcp-server` requires `uv` because the upstream `databricks-mcp-server` requires
it.  For non-engineering users this is friction.

Options to revisit once governance is validated:

| Option | UX | Effort |
|---|---|---|
| Private PyPI + `uvx noom-mcp-server` | One-line MCP config, one-time `uv` install | Medium — CI publish pipeline |
| Docker image | Zero Python tooling required | Medium — Dockerfile + registry |
| Wrapper shell script | Hides `uv` behind `./start.sh` | Low |
| Bundled executable (PyInstaller) | True double-click install | High |

The monkey-patch approach in this POC is agnostic to all of these — `run.py` and
`patches.py` work identically however the user arrives at a Python environment.

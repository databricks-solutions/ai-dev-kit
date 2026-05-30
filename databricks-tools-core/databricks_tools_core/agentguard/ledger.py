"""
Audit ledger writer for AgentGuard.

Two-tier persistence strategy:
1. HOT PATH (per-action): Append each action to a local JSONL file as it happens.
   Cost: ~0.1ms per action. Survives crashes, forgotten stops, and closed connections.
2. COLD PATH (at session stop): Batch-flush the JSONL to a Delta table on Databricks.
   If Delta is unavailable, the JSONL file is kept for later recovery.

On next session start, any orphaned JSONL files (from crashed/abandoned sessions)
are detected and reported so they can be flushed to Delta.

This guarantees zero audit data loss regardless of how the session ends.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default catalog/schema for the audit ledger.
# Default: main.agentguard — "main" catalog exists on all workspaces.
# Override via env var if needed (e.g., AGENTGUARD_CATALOG=my_catalog).
_DEFAULT_CATALOG = os.environ.get("AGENTGUARD_CATALOG", "main")
_DEFAULT_SCHEMA = os.environ.get("AGENTGUARD_SCHEMA", "agentguard")
_ACTION_LOG_TABLE = "action_log"

# Local storage directory for JSONL session files
_SESSIONS_DIR = Path.home() / ".agentguard" / "sessions"

# Cache: once we confirm the Delta table exists, skip CREATE IF NOT EXISTS.
_table_exists_cache: set[str] = set()
_cache_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Hot path: per-action local JSONL append
# ---------------------------------------------------------------------------


def init_session_file(task_id: str) -> Path:
    """Create the JSONL file for a new session. Called at session start."""
    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    file_path = _SESSIONS_DIR / f"{task_id}.jsonl"
    # Write a header line with session metadata
    file_path.touch(exist_ok=True)
    return file_path


def append_action(task_id: str, action: Any, session: Any) -> None:
    """Append a single action to the session's JSONL file.

    Called from the middleware after every tool call. Must be fast (<1ms).
    Failures are logged but never block the agent.
    """
    file_path = _SESSIONS_DIR / f"{task_id}.jsonl"
    try:
        row = _action_to_row(action, session)
        line = json.dumps(row, default=str)
        with open(file_path, "a") as f:
            f.write(line + "\n")
    except Exception as e:
        # Never fail the agent because of audit logging
        logger.warning("Audit append failed for action %s: %s", action.action_id, e)


def _action_to_row(action: Any, session: Any) -> dict[str, Any]:
    """Convert a single action to a flat row dict."""
    cp = action.checkpoint_result
    return {
        "action_id": action.action_id,
        "task_id": action.task_id,
        "agent_id": action.agent_id,
        "action_sequence": action.action_sequence,
        "tool_name": action.tool_name,
        "action_category": action.action_category.value,
        "operation": action.operation,
        "target_resource_type": action.target_resource_type,
        "target_resource_id": action.target_resource_id,
        "target_environment": action.target_environment,
        "sql_statement": action.sql_statement,
        "sql_parsed_type": action.sql_parsed_type,
        "tables_read": json.dumps(action.tables_read),
        "tables_written": json.dumps(action.tables_written),
        "rows_affected": action.rows_affected,
        "cp1_policy_result": cp.policy_result if cp else None,
        "cp1_policy_rule_hit": cp.policy_rule_hit if cp else None,
        "cp2_scope_result": cp.scope_result if cp else None,
        "cp2_scope_violation": cp.scope_violation if cp else None,
        "cp3_risk_score": cp.risk_score if cp else 0.0,
        "cp3_risk_breakdown": json.dumps(cp.risk_breakdown) if cp else None,
        "cp3_risk_decision": cp.decision.value if cp else None,
        "cp4_approval_requested": cp.approval_requested if cp else False,
        "cp4_approval_outcome": cp.approval_outcome if cp else None,
        "cp4_approval_note": cp.approval_note if cp else None,
        "final_decision": action.final_decision,
        "execution_success": action.execution_success,
        "execution_error": action.execution_error,
        "execution_duration_ms": action.execution_duration_ms,
        "overhead_ms": action.overhead_ms,
        "received_at": action.received_at.isoformat() if action.received_at else None,
        "executed_at": action.executed_at.isoformat() if action.executed_at else None,
        "completed_at": action.completed_at.isoformat() if action.completed_at else None,
        "session_mode": session.mode.value,
        "session_description": session.description,
        "scope_template": session.scope_template,
        # Project identity — matches the tagging in identity.py so audit
        # records can be correlated with other AI Dev Kit resources
        "project_name": getattr(session, "project_name", "unknown"),
    }


# ---------------------------------------------------------------------------
# Cold path: flush JSONL to Delta at session stop
# ---------------------------------------------------------------------------


def flush_session_to_delta(
    session: Any,
    catalog: str = _DEFAULT_CATALOG,
    schema: str = _DEFAULT_SCHEMA,
    warehouse_id: Optional[str] = None,
) -> dict[str, Any]:
    """Flush a session's JSONL file to the Delta audit ledger.

    Reads all rows from the local JSONL, batch-inserts into Delta,
    and deletes the JSONL on success. If Delta write fails, the JSONL
    is kept for later recovery.

    Args:
        session: A completed AgentGuardSession.
        catalog: Unity Catalog catalog name.
        schema: Schema within the catalog.
        warehouse_id: SQL warehouse ID. If None, auto-selects.

    Returns:
        Dict with write status, row count, and destination.
    """
    jsonl_path = _SESSIONS_DIR / f"{session.task_id}.jsonl"

    # Read rows from JSONL
    rows = _read_jsonl(jsonl_path)
    if not rows:
        _cleanup_jsonl(jsonl_path)
        return {"status": "skipped", "reason": "no actions to flush", "rows": 0}

    try:
        result = _write_to_delta(rows, catalog, schema, warehouse_id)
        # Delta write succeeded — delete the local JSONL
        _cleanup_jsonl(jsonl_path)
        logger.info(
            "Audit ledger: %d actions written to %s for task %s",
            len(rows),
            result["destination"],
            session.task_id,
        )
        return result
    except Exception as e:
        logger.warning(
            "Audit ledger: Delta write failed for task %s (%s). JSONL preserved at %s for recovery.",
            session.task_id,
            e,
            jsonl_path,
        )
        return {
            "status": "pending",
            "destination": str(jsonl_path),
            "rows": len(rows),
            "method": "local_jsonl",
            "note": (
                f"Delta write failed. {len(rows)} actions preserved locally at {jsonl_path}. "
                f"They will be flushed on the next successful session stop, "
                f"or can be loaded manually."
            ),
        }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read all rows from a JSONL file."""
    if not path.exists():
        return []
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning("Skipping malformed JSONL line in %s", path)
    return rows


def _cleanup_jsonl(path: Path) -> None:
    """Delete a JSONL file after successful Delta flush."""
    try:
        if path.exists():
            path.unlink()
    except OSError as e:
        logger.warning("Could not delete JSONL %s: %s", path, e)


# ---------------------------------------------------------------------------
# Orphan recovery: detect abandoned sessions from previous runs
# ---------------------------------------------------------------------------


def find_orphaned_sessions() -> list[dict[str, Any]]:
    """Find JSONL files from sessions that were never flushed to Delta.

    These are sessions where the user closed Claude Code without running
    /agentguard stop, or where the Delta write failed.

    Returns:
        List of dicts with task_id, file path, and row count.
    """
    if not _SESSIONS_DIR.exists():
        return []

    orphans = []
    for jsonl_file in _SESSIONS_DIR.glob("*.jsonl"):
        # Skip empty files (created by init_session_file but never written to)
        if jsonl_file.stat().st_size == 0:
            _cleanup_jsonl(jsonl_file)
            continue
        rows = _read_jsonl(jsonl_file)
        if rows:
            task_id = jsonl_file.stem
            orphans.append(
                {
                    "task_id": task_id,
                    "file": str(jsonl_file),
                    "actions": len(rows),
                    "oldest_action": rows[0].get("received_at", "unknown"),
                }
            )
    return orphans


def flush_orphaned_sessions(
    catalog: str = _DEFAULT_CATALOG,
    schema: str = _DEFAULT_SCHEMA,
    warehouse_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Flush all orphaned JSONL files to Delta.

    Called on session start to recover data from abandoned sessions.

    Returns:
        List of results, one per orphaned session.
    """
    orphans = find_orphaned_sessions()
    if not orphans:
        return []

    results = []
    for orphan in orphans:
        jsonl_path = Path(orphan["file"])
        rows = _read_jsonl(jsonl_path)
        if not rows:
            _cleanup_jsonl(jsonl_path)
            continue

        try:
            result = _write_to_delta(rows, catalog, schema, warehouse_id)
            _cleanup_jsonl(jsonl_path)
            results.append(
                {
                    "task_id": orphan["task_id"],
                    "status": "recovered",
                    "rows": len(rows),
                    "destination": result["destination"],
                }
            )
            logger.info(
                "Recovered orphaned session %s: %d actions → Delta",
                orphan["task_id"],
                len(rows),
            )
        except Exception as e:
            results.append(
                {
                    "task_id": orphan["task_id"],
                    "status": "failed",
                    "rows": len(rows),
                    "error": str(e),
                }
            )
            logger.warning(
                "Failed to recover orphaned session %s: %s",
                orphan["task_id"],
                e,
            )

    return results


# ---------------------------------------------------------------------------
# Delta write internals
# ---------------------------------------------------------------------------


_TABLE_COLUMNS = """(
    action_id STRING, task_id STRING, agent_id STRING,
    action_sequence INT, tool_name STRING, action_category STRING,
    operation STRING, target_resource_type STRING,
    target_resource_id STRING, target_environment STRING,
    sql_statement STRING, sql_parsed_type STRING,
    tables_read STRING, tables_written STRING, rows_affected BIGINT,
    cp1_policy_result STRING, cp1_policy_rule_hit STRING,
    cp2_scope_result STRING, cp2_scope_violation STRING,
    cp3_risk_score DOUBLE, cp3_risk_breakdown STRING,
    cp3_risk_decision STRING, cp4_approval_requested BOOLEAN,
    cp4_approval_outcome STRING, cp4_approval_note STRING,
    final_decision STRING, execution_success BOOLEAN,
    execution_error STRING, execution_duration_ms DOUBLE,
    overhead_ms DOUBLE, received_at STRING, executed_at STRING,
    completed_at STRING, session_mode STRING,
    session_description STRING, scope_template STRING,
    project_name STRING
)"""


def _write_to_delta(
    rows: list[dict[str, Any]],
    catalog: str,
    schema: str,
    warehouse_id: Optional[str],
) -> dict[str, Any]:
    """Write rows to the Delta audit ledger via SQL INSERT VALUES.

    Simple, direct approach — one SQL call. No Volume, no COPY INTO,
    no extra permissions beyond table write access.

    If the INSERT fails (e.g., table was deleted externally), clears the
    cache and retries with table recreation.
    """
    from databricks_tools_core.sql.sql import execute_sql

    full_table = f"{catalog}.{schema}.{_ACTION_LOG_TABLE}"

    # Ensure table exists (cached after first call)
    with _cache_lock:
        needs_setup = full_table not in _table_exists_cache

    if needs_setup:
        _ensure_table_exists(catalog, schema, warehouse_id)
        with _cache_lock:
            _table_exists_cache.add(full_table)

    # Build batch INSERT
    value_rows = []
    for row in rows:
        values = []
        for col in _COLUMN_ORDER:
            val = row.get(col)
            if val is None:
                values.append("NULL")
            elif isinstance(val, bool):
                values.append("TRUE" if val else "FALSE")
            elif isinstance(val, (int, float)):
                values.append(str(val))
            else:
                escaped = str(val).replace("\\", "\\\\").replace("'", "''")
                values.append(f"'{escaped}'")
        value_rows.append(f"({', '.join(values)})")

    columns = ", ".join(_COLUMN_ORDER)
    values_sql = ",\n".join(value_rows)
    insert_sql = f"INSERT INTO {full_table} ({columns}) VALUES\n{values_sql}"

    try:
        execute_sql(insert_sql, warehouse_id=warehouse_id)
    except Exception:
        # Table may have been deleted externally. Clear cache, recreate, retry.
        logger.info("INSERT failed — recreating table and retrying")
        with _cache_lock:
            _table_exists_cache.discard(full_table)
        _ensure_table_exists(catalog, schema, warehouse_id)
        with _cache_lock:
            _table_exists_cache.add(full_table)
        execute_sql(insert_sql, warehouse_id=warehouse_id)

    return {
        "status": "success",
        "destination": full_table,
        "rows": len(rows),
        "method": "delta",
    }


def _ensure_table_exists(
    catalog: str,
    schema: str,
    warehouse_id: Optional[str],
) -> None:
    """Create schema and table if they don't exist.

    Runs once per process lifetime (cached). Skips catalog creation —
    most shared workspaces don't allow CREATE CATALOG. The catalog
    must exist already (or be set via AGENTGUARD_CATALOG env var to
    an existing catalog the user has access to).
    """
    from databricks_tools_core.sql.sql import execute_sql

    # Schema + table only. No CREATE CATALOG (requires admin).
    for stmt in [
        f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}",
        f"CREATE TABLE IF NOT EXISTS {catalog}.{schema}.{_ACTION_LOG_TABLE} {_TABLE_COLUMNS} USING DELTA TBLPROPERTIES ('delta.appendOnly' = 'true')",
    ]:
        try:
            execute_sql(stmt, warehouse_id=warehouse_id)
        except Exception as e:
            logger.warning("Setup statement failed (non-fatal): %s — %s", stmt[:60], e)


# Column order must match the INSERT and CREATE TABLE
_COLUMN_ORDER = [
    "action_id",
    "task_id",
    "agent_id",
    "action_sequence",
    "tool_name",
    "action_category",
    "operation",
    "target_resource_type",
    "target_resource_id",
    "target_environment",
    "sql_statement",
    "sql_parsed_type",
    "tables_read",
    "tables_written",
    "rows_affected",
    "cp1_policy_result",
    "cp1_policy_rule_hit",
    "cp2_scope_result",
    "cp2_scope_violation",
    "cp3_risk_score",
    "cp3_risk_breakdown",
    "cp3_risk_decision",
    "cp4_approval_requested",
    "cp4_approval_outcome",
    "cp4_approval_note",
    "final_decision",
    "execution_success",
    "execution_error",
    "execution_duration_ms",
    "overhead_ms",
    "received_at",
    "executed_at",
    "completed_at",
    "session_mode",
    "session_description",
    "scope_template",
    "project_name",
]

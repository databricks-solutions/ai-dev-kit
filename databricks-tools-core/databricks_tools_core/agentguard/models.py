"""
AgentGuard models

Pydantic models for checkpoint state, actions, and sessions.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, ClassVar, Optional

from pydantic import BaseModel, Field, PrivateAttr


class AgentGuardMode(str, Enum):
    """AgentGuard session mode."""

    MONITOR_ONLY = "monitor_only"
    ENFORCE = "enforce"


class ActionCategory(str, Enum):
    READ = "READ"
    WRITE = "WRITE"
    DDL = "DDL"
    DCL = "DCL"
    ADMIN = "ADMIN"
    EXTERNAL = "EXTERNAL"
    UNKNOWN = "UNKNOWN"


class CheckpointDecision(str, Enum):
    AUTO_APPROVE = "auto_approve"
    FLAG = "flag"
    HOLD_FOR_APPROVAL = "hold_for_approval"
    BLOCK = "block"
    WOULD_BLOCK = "would_block"


class SessionStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class TimingRecord(BaseModel):
    """One named timing sample (checkpoint phase)."""

    name: str
    duration_ms: float


class CheckpointResult(BaseModel):
    """Checkpoint pipeline outcome for one action."""

    decision: CheckpointDecision = CheckpointDecision.AUTO_APPROVE
    original_decision: Optional[CheckpointDecision] = None
    block_reason: Optional[str] = None
    blocking_checkpoint: Optional[str] = None
    risk_score: float = 0.0
    risk_breakdown: dict[str, float] = Field(default_factory=dict)

    policy_result: str = CheckpointDecision.AUTO_APPROVE.value
    policy_rule_hit: Optional[str] = None
    scope_result: str = CheckpointDecision.AUTO_APPROVE.value
    scope_violation: Optional[str] = None

    approval_requested: bool = False
    approval_outcome: Optional[str] = None
    approval_note: Optional[str] = None

    timings: list[TimingRecord] = Field(default_factory=list)

    @property
    def blocked(self) -> bool:
        """Hard block only; WOULD_BLOCK is monitor-only."""
        return self.decision == CheckpointDecision.BLOCK

    @property
    def total_overhead_ms(self) -> float:
        return sum(t.duration_ms for t in self.timings)


def _generate_action_id() -> str:
    return f"act_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


_SQL_CATEGORY_MAP: dict[str, tuple[ActionCategory, str]] = {
    "SELECT": (ActionCategory.READ, "SELECT"),
    "DESCRIBE": (ActionCategory.READ, "DESCRIBE"),
    "SHOW": (ActionCategory.READ, "SHOW"),
    "EXPLAIN": (ActionCategory.READ, "EXPLAIN"),
    "INSERT": (ActionCategory.WRITE, "INSERT"),
    "UPDATE": (ActionCategory.WRITE, "UPDATE"),
    "MERGE": (ActionCategory.WRITE, "MERGE"),
    "DELETE": (ActionCategory.WRITE, "DELETE"),
    "TRUNCATE": (ActionCategory.WRITE, "TRUNCATE"),
    "COPY": (ActionCategory.WRITE, "COPY_INTO"),
    "CREATE": (ActionCategory.DDL, "CREATE"),
    "ALTER": (ActionCategory.DDL, "ALTER"),
    "DROP": (ActionCategory.DDL, "DROP"),
    "GRANT": (ActionCategory.DCL, "GRANT"),
    "REVOKE": (ActionCategory.DCL, "REVOKE"),
}


def _strip_sql_noise(sql: str) -> str:
    """Normalize SQL for keyword classification.

    Strips leading comments (-- and /* */), CTEs (WITH ... AS), and
    whitespace so the first token is the actual operation keyword.

    Examples:
        "-- fix\\nDROP TABLE t"          → "DROP TABLE T"
        "/* cleanup */ DELETE FROM t"    → "DELETE FROM T"
        "WITH cte AS (SELECT 1) SELECT" → "SELECT"
    """
    import re

    text = sql.strip().upper()
    # Strip line comments
    text = re.sub(r"--[^\n]*", " ", text)
    # Strip block comments
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    text = text.strip()
    # Strip CTE prefix: WITH <name> AS (...) <actual statement>
    # Find the last top-level closing paren of the CTE, then take what follows
    if text.startswith("WITH "):
        # Simple heuristic: find the keyword after the last balanced ")"
        depth = 0
        for i, ch in enumerate(text):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    remainder = text[i + 1 :].strip()
                    if remainder:
                        text = remainder
                    break
    return text


class Action(BaseModel):
    """One intercepted agent tool call."""

    action_id: str = Field(default_factory=_generate_action_id)
    task_id: str = ""
    agent_id: str = ""

    tool_name: str
    tool_params: dict[str, Any] = Field(default_factory=dict)
    action_sequence: int = 0

    action_category: ActionCategory = ActionCategory.UNKNOWN
    operation: str = ""
    target_resource_type: str = ""
    target_resource_id: str = ""
    target_environment: str = ""

    sql_statement: Optional[str] = None
    sql_parsed_type: Optional[str] = None
    tables_read: list[str] = Field(default_factory=list)
    tables_written: list[str] = Field(default_factory=list)
    rows_affected: Optional[int] = None

    api_endpoint: Optional[str] = None
    api_method: Optional[str] = None

    checkpoint_result: Optional[CheckpointResult] = None

    final_decision: str = ""
    execution_success: Optional[bool] = None
    execution_error: Optional[str] = None
    execution_duration_ms: Optional[float] = None

    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    executed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    overhead_ms: Optional[float] = None

    @classmethod
    def from_tool_call(
        cls,
        tool_name: str,
        tool_params: dict[str, Any],
        task_id: str,
        agent_id: str,
        sequence: int,
    ) -> Action:
        """Build from an MCP tool call and enrich classification."""
        action = cls(
            tool_name=tool_name,
            tool_params=tool_params,
            task_id=task_id,
            agent_id=agent_id,
            action_sequence=sequence,
        )
        action._enrich_from_tool()
        return action

    _ACTION_BASED_TOOLS: ClassVar[dict[str, str]] = {
        "manage_jobs": "job",
        "manage_job_runs": "job_run",
        "manage_uc_objects": "unity_catalog",
        "manage_uc_grants": "uc_grant",
        "manage_uc_storage": "uc_storage",
        "manage_uc_connections": "uc_connection",
        "manage_uc_tags": "uc_tag",
        "manage_uc_security_policies": "uc_security",
        "manage_uc_monitors": "uc_monitor",
        "manage_uc_sharing": "uc_sharing",
        "manage_metric_views": "metric_view",
        "manage_ka": "knowledge_assistant",
        "manage_mas": "supervisor_agent",
        "manage_vs_data": "vector_search",
        "manage_workspace": "workspace",
        "create_or_update_app": "app",
        "create_or_update_pipeline": "pipeline",
        "create_or_update_dashboard": "dashboard",
        "create_or_update_genie": "genie_space",
        "create_or_update_vs_endpoint": "vs_endpoint",
        "create_or_update_vs_index": "vs_index",
        "create_or_update_lakebase_database": "lakebase_database",
        "create_or_update_lakebase_branch": "lakebase_branch",
        "create_or_update_lakebase_sync": "lakebase_sync",
    }

    _DELETE_TOOLS: ClassVar[dict[str, tuple[str, str]]] = {
        "delete_app": ("app", "name"),
        "delete_dashboard": ("dashboard", "dashboard_id"),
        "delete_pipeline": ("pipeline", "pipeline_id"),
        "delete_genie": ("genie_space", "space_id"),
        "delete_vs_endpoint": ("vs_endpoint", "name"),
        "delete_vs_index": ("vs_index", "index_name"),
        "delete_lakebase_database": ("lakebase_database", "name"),
        "delete_lakebase_branch": ("lakebase_branch", "name"),
        "delete_lakebase_sync": ("lakebase_sync", "table_name"),
        "delete_volume_file": ("file", "volume_path"),
        "delete_volume_directory": ("file", "volume_path"),
        "delete_tracked_resource": ("_dynamic", "resource_id"),
    }

    _READ_ONLY_TOOLS: ClassVar[frozenset] = frozenset(
        {
            "get_table_details",
            "get_volume_folder_details",
            "list_warehouses",
            "get_best_warehouse",
            "list_clusters",
            "get_best_cluster",
            "get_cluster_status",
            "get_pipeline",
            "get_update",
            "get_pipeline_events",
            "find_pipeline_by_name",
            "get_app",
            "get_dashboard",
            "get_genie",
            "ask_genie",
            "get_vs_endpoint",
            "get_vs_index",
            "query_vs_index",
            "get_serving_endpoint_status",
            "list_serving_endpoints",
            "get_lakebase_database",
            "list_volume_files",
            "get_volume_file_info",
            "download_from_volume",
            "list_tracked_resources",
            "get_current_user",
        }
    )

    _STANDALONE_WRITE_TOOLS: ClassVar[dict[str, tuple[str, str]]] = {
        "create_pipeline": ("pipeline", "CREATE"),
        "update_pipeline": ("pipeline", "UPDATE"),
        "start_update": ("pipeline", "START"),
        "stop_pipeline": ("pipeline", "STOP"),
        "start_cluster": ("cluster", "START_CLUSTER"),
        "upload_file": ("file", "UPLOAD"),
        "upload_folder": ("file", "UPLOAD"),
        "upload_to_volume": ("file", "UPLOAD"),
        "create_volume_directory": ("file", "CREATE_DIRECTORY"),
        "generate_and_upload_pdf": ("file", "GENERATE_PDF"),
        "generate_and_upload_pdfs": ("file", "GENERATE_PDF"),
        "publish_dashboard": ("dashboard", "PUBLISH"),
        "generate_lakebase_credential": ("lakebase_credential", "GENERATE_CREDENTIAL"),
        "migrate_genie": ("genie_space", "MIGRATE"),
        "query_serving_endpoint": ("serving_endpoint", "QUERY"),
    }

    _CODE_EXECUTION_TOOLS: ClassVar[frozenset] = frozenset(
        {
            "execute_databricks_command",
            "run_python_file_on_databricks",
        }
    )

    _DESTRUCTIVE_ACTIONS: ClassVar[frozenset] = frozenset(
        {
            "delete",
            "drop",
            "remove",
            "destroy",
            "terminate",
            "purge",
        }
    )

    _WRITE_ACTIONS: ClassVar[frozenset] = frozenset(
        {
            "create",
            "update",
            "run_now",
            "start",
            "restart",
            "reset",
            "run",
            "trigger",
            "deploy",
            "grant",
            "revoke",
        }
    )

    def _enrich_from_tool(self) -> None:
        """Set category, operation, and resource fields from tool_name and tool_params."""

        if self.tool_name == "execute_sql":
            self.target_resource_type = "sql"
            stmt = self.tool_params.get("sql_query") or self.tool_params.get("query", "")
            if stmt:
                self.sql_statement = stmt
                self._classify_sql(stmt)
            else:
                self.action_category = ActionCategory.READ
                self.operation = "SQL_EMPTY"
            return

        if self.tool_name == "execute_sql_multi":
            self.target_resource_type = "sql"
            sql_content = self.tool_params.get("sql_content", "")
            if sql_content and isinstance(sql_content, str):
                sqls = [s.strip() for s in sql_content.split(";") if s.strip()]
            else:
                sqls = self.tool_params.get("sqls", [])
            if sqls and isinstance(sqls, list) and len(sqls) > 0:
                self.sql_statement = "; ".join(sqls[:5])
                self._classify_sql_multi(sqls)
            else:
                self.action_category = ActionCategory.READ
                self.operation = "SQL_MULTI_EMPTY"
            return

        if self.tool_name in self._READ_ONLY_TOOLS:
            self.action_category = ActionCategory.READ
            self.operation = "READ"
            self.target_resource_id = self._extract_resource_id()
            return

        if self.tool_name in self._DELETE_TOOLS:
            resource_type, id_key = self._DELETE_TOOLS[self.tool_name]
            if resource_type == "_dynamic":
                resource_type = self.tool_params.get("type", "unknown")
            self.target_resource_type = resource_type
            self.action_category = ActionCategory.ADMIN
            self.target_resource_id = self.tool_params.get(id_key, "")
            self.operation = f"DELETE_{resource_type.upper()}"
            return

        if self.tool_name in self._ACTION_BASED_TOOLS:
            self.target_resource_type = self._ACTION_BASED_TOOLS[self.tool_name]
            action_param = self._extract_action_param()
            self.target_resource_id = self._extract_resource_id()

            action_lower = action_param.lower()
            if action_lower in self._DESTRUCTIVE_ACTIONS:
                self.action_category = ActionCategory.ADMIN
                self.operation = f"DELETE_{self.target_resource_type.upper()}"
            elif action_lower in ("grant", "revoke"):
                self.action_category = ActionCategory.DCL
                self.operation = action_param.upper()
            elif action_lower in self._WRITE_ACTIONS:
                self.action_category = ActionCategory.WRITE
                self.operation = action_param.upper()
            elif action_lower in ("get", "list", "find_by_name", "describe"):
                self.action_category = ActionCategory.READ
                self.operation = action_param.upper()
            else:
                self.action_category = ActionCategory.ADMIN
                self.operation = action_param.upper()
            return

        if self.tool_name in self._STANDALONE_WRITE_TOOLS:
            resource_type, operation = self._STANDALONE_WRITE_TOOLS[self.tool_name]
            self.target_resource_type = resource_type
            self.action_category = ActionCategory.WRITE
            self.operation = operation
            self.target_resource_id = self._extract_resource_id()
            return

        if self.tool_name in self._CODE_EXECUTION_TOOLS:
            self.target_resource_type = "code_execution"
            self.action_category = ActionCategory.ADMIN
            self.operation = "EXECUTE_CODE"
            self.target_resource_id = self.tool_params.get("cluster_id", "")
            return

        self.action_category = ActionCategory.UNKNOWN
        self.operation = self.tool_name.upper()

    def _extract_action_param(self) -> str:
        for key in ("action", "operation", "command"):
            val = self.tool_params.get(key, "")
            if val:
                return str(val)
        if "delete" in self.tool_name.lower():
            return "delete"
        if "create" in self.tool_name.lower():
            return "create"
        return "unknown"

    def _extract_resource_id(self) -> str:
        """First matching param wins; order avoids generic keys shadowing specific IDs.

        Note: "project_name" is intentionally excluded — it conflicts with the
        session-level project_name field from identity.py.
        """
        for key in (
            "app_name",
            "job_id",
            "pipeline_id",
            "endpoint_name",
            "dashboard_id",
            "resource_id",
            "space_id",
            "tile_id",
            "index_name",
            "cluster_id",
            "catalog_name",
            "schema_name",
            "table_name",
            "full_name",
            "instance_name",
            "volume_path",
            "workspace_path",
            "display_name",
            "name",
        ):
            val = self.tool_params.get(key, "")
            if val:
                return str(val)
        return ""

    def _classify_sql(self, stmt: str) -> None:
        normalized = _strip_sql_noise(stmt)
        tokens = normalized.split()
        first_keyword = tokens[0] if tokens else ""

        category, operation = _SQL_CATEGORY_MAP.get(first_keyword, (ActionCategory.UNKNOWN, first_keyword))
        self.action_category = category
        self.sql_parsed_type = operation
        self.operation = operation

    def _classify_sql_multi(self, sqls: list[str]) -> None:
        """Use highest-severity statement (DCL > DDL > WRITE > READ > UNKNOWN)."""
        priority = {
            ActionCategory.DCL: 5,
            ActionCategory.DDL: 4,
            ActionCategory.WRITE: 3,
            ActionCategory.READ: 2,
            ActionCategory.UNKNOWN: 1,
        }
        worst_category = ActionCategory.UNKNOWN
        worst_operation = "MULTI"

        for stmt in sqls:
            normalized = stmt.strip().upper()
            tokens = normalized.split()
            first_keyword = tokens[0] if tokens else ""
            cat, op = _SQL_CATEGORY_MAP.get(first_keyword, (ActionCategory.UNKNOWN, first_keyword))
            if priority.get(cat, 0) > priority.get(worst_category, 0):
                worst_category = cat
                worst_operation = op

        self.action_category = worst_category
        self.sql_parsed_type = worst_operation
        self.operation = f"MULTI({worst_operation})"


def _generate_task_id() -> str:
    return f"task_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


class AgentGuardSession(BaseModel):
    """One agent task. Not thread-safe; OK while MCP tools run single-threaded async."""

    task_id: str = Field(default_factory=_generate_task_id)
    agent_id: str = "unknown"
    user_id: str = "unknown"
    project_name: str = "unknown"
    mode: AgentGuardMode = AgentGuardMode.MONITOR_ONLY
    status: SessionStatus = SessionStatus.ACTIVE

    description: str = ""
    scope_template: Optional[str] = None
    scope_variables: Optional[dict[str, str]] = None
    scope: Optional[Any] = None  # Runtime type: Optional[ScopeManifest] (avoids circular import with scope.py)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

    _sequence_counter: int = PrivateAttr(default=0)
    _ledger_result: Optional[dict] = PrivateAttr(default=None)
    blocked_count: int = 0
    would_block_count: int = 0
    write_count: int = 0
    total_risk_score: float = 0.0
    max_risk_score: float = 0.0

    actions: list[Action] = Field(default_factory=list)

    def next_sequence(self) -> int:
        """Next sequence number (does not append an action)."""
        self._sequence_counter += 1
        return self._sequence_counter

    @property
    def action_count(self) -> int:
        return len(self.actions)

    def record_action(self, action: Action) -> None:
        self.actions.append(action)
        if action.action_category in (ActionCategory.WRITE, ActionCategory.DDL, ActionCategory.ADMIN):
            self.write_count += 1
        if action.checkpoint_result:
            score = action.checkpoint_result.risk_score
            self.total_risk_score += score
            if score > self.max_risk_score:
                self.max_risk_score = score
            if action.checkpoint_result.decision == CheckpointDecision.BLOCK:
                self.blocked_count += 1
            elif action.checkpoint_result.decision == CheckpointDecision.WOULD_BLOCK:
                self.would_block_count += 1

    @property
    def avg_risk_score(self) -> float:
        if self.action_count == 0:
            return 0.0
        return self.total_risk_score / self.action_count

    def complete(self) -> None:
        self.status = SessionStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc)

    def summary(self) -> str:
        mode_label = "monitor-only" if self.mode == AgentGuardMode.MONITOR_ONLY else "enforce"
        duration = ""
        if self.created_at:
            elapsed = datetime.now(timezone.utc) - self.created_at
            minutes = int(elapsed.total_seconds() // 60)
            seconds = int(elapsed.total_seconds() % 60)
            duration = f" | Duration: {minutes}m {seconds}s"

        block_label = "Would-block" if self.mode == AgentGuardMode.MONITOR_ONLY else "Blocked"
        block_count = self.would_block_count if self.mode == AgentGuardMode.MONITOR_ONLY else self.blocked_count

        return (
            f"Session: {self.status.value} ({mode_label}) | "
            f"Task: {self.task_id} | "
            f"Actions: {self.action_count} | "
            f"{block_label}: {block_count} | "
            f"Avg Risk: {self.avg_risk_score:.0f} | "
            f"Max Risk: {self.max_risk_score:.0f}"
            f"{duration}"
        )

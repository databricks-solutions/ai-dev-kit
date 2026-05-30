"""
AgentGuard scope (CP-2)

Optional manifest: allowed resources per type. Enforce blocks out-of-scope; monitor-only uses WOULD_BLOCK.
Without scope, CP-2 defers; risk still runs on the action alone.
"""

from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from databricks_tools_core.agentguard.models import (
    Action,
    ActionCategory,
    AgentGuardMode,
    CheckpointDecision,
)

_TEMPLATES_DIR = Path(__file__).parent / "templates"


class ResourceScope(BaseModel):
    """Per-resource-type allow lists (glob patterns)."""

    read: list[str] = Field(default_factory=list)
    write: list[str] = Field(default_factory=list)
    ddl: list[str] = Field(default_factory=list)
    delete: list[str] = Field(default_factory=list)


class ScopeManifest(BaseModel):
    """Task blast radius as globs per resource bucket."""

    tables: ResourceScope = Field(default_factory=ResourceScope)
    jobs: ResourceScope = Field(default_factory=ResourceScope)
    pipelines: ResourceScope = Field(default_factory=ResourceScope)
    apps: ResourceScope = Field(default_factory=ResourceScope)
    dashboards: ResourceScope = Field(default_factory=ResourceScope)
    clusters: ResourceScope = Field(default_factory=ResourceScope)
    serving_endpoints: ResourceScope = Field(default_factory=ResourceScope)
    genie_spaces: ResourceScope = Field(default_factory=ResourceScope)
    knowledge_assistants: ResourceScope = Field(default_factory=ResourceScope)
    supervisor_agents: ResourceScope = Field(default_factory=ResourceScope)
    unity_catalog: ResourceScope = Field(default_factory=ResourceScope)
    vector_search: ResourceScope = Field(default_factory=ResourceScope)
    lakebase: ResourceScope = Field(default_factory=ResourceScope)
    files: ResourceScope = Field(default_factory=ResourceScope)
    code_execution: ResourceScope = Field(default_factory=ResourceScope)

    default_deny: bool = False

    max_actions: Optional[int] = None
    max_write_actions: Optional[int] = None


def _resource_scope_has_patterns(rs: ResourceScope) -> bool:
    return bool(rs.read or rs.write or rs.ddl or rs.delete)


def _matches_any(value: str, patterns: list[str]) -> bool:
    value_lower = value.lower()
    for pattern in patterns:
        if fnmatch.fnmatch(value_lower, pattern.lower()):
            return True
    return False


_RESOURCE_TYPE_TO_SCOPE_FIELD = {
    "sql": "tables",
    "job": "jobs",
    "job_run": "jobs",
    "pipeline": "pipelines",
    "app": "apps",
    "dashboard": "dashboards",
    "cluster": "clusters",
    "serving_endpoint": "serving_endpoints",
    "genie_space": "genie_spaces",
    "knowledge_assistant": "knowledge_assistants",
    "supervisor_agent": "supervisor_agents",
    "unity_catalog": "unity_catalog",
    "uc_grant": "unity_catalog",
    "uc_storage": "unity_catalog",
    "uc_connection": "unity_catalog",
    "uc_tag": "unity_catalog",
    "uc_security": "unity_catalog",
    "uc_monitor": "unity_catalog",
    "uc_sharing": "unity_catalog",
    "metric_view": "unity_catalog",
    "vs_endpoint": "vector_search",
    "vs_index": "vector_search",
    "vector_search": "vector_search",
    "lakebase_database": "lakebase",
    "lakebase_branch": "lakebase",
    "lakebase_sync": "lakebase",
    "lakebase_credential": "lakebase",
    "file": "files",
    "code_execution": "code_execution",
    "workspace": "unity_catalog",
}

_CATEGORY_TO_SCOPE_OP = {
    ActionCategory.READ: "read",
    ActionCategory.WRITE: "write",
    ActionCategory.DDL: "ddl",
    ActionCategory.DCL: "write",
    ActionCategory.ADMIN: "delete",
}


def check_scope(
    action: Action,
    scope: ScopeManifest,
    mode: AgentGuardMode,
) -> tuple[CheckpointDecision, Optional[str]]:
    """Returns (decision, violation message or None)."""
    resource_id = action.target_resource_id
    if not resource_id:
        return CheckpointDecision.AUTO_APPROVE, None

    scope_field_name = _RESOURCE_TYPE_TO_SCOPE_FIELD.get(action.target_resource_type)
    if scope_field_name is None:
        return CheckpointDecision.AUTO_APPROVE, None

    resource_scope: ResourceScope = getattr(scope, scope_field_name)

    scope_op = _CATEGORY_TO_SCOPE_OP.get(action.action_category, "write")

    allowed_patterns: list[str] = getattr(resource_scope, scope_op, [])

    if not allowed_patterns:
        if scope.default_deny and _resource_scope_has_patterns(resource_scope):
            violation = (
                f"Operation '{scope_op}' on '{scope_field_name}' is not explicitly allowed (default_deny is enabled)"
            )
            if mode == AgentGuardMode.MONITOR_ONLY:
                return CheckpointDecision.WOULD_BLOCK, f"[monitor] {violation}"
            return CheckpointDecision.BLOCK, violation
        return CheckpointDecision.AUTO_APPROVE, None

    if _matches_any(resource_id, allowed_patterns):
        return CheckpointDecision.AUTO_APPROVE, None

    violation = (
        f"Resource '{resource_id}' ({scope_op}) is not in scope for "
        f"{scope_field_name}. Allowed patterns: {allowed_patterns}"
    )

    if mode == AgentGuardMode.MONITOR_ONLY:
        return CheckpointDecision.WOULD_BLOCK, f"[monitor] {violation}"

    return CheckpointDecision.BLOCK, violation


def check_scope_limits(
    action: Action,
    scope: ScopeManifest,
    session_action_count: int,
    session_write_count: int,
    mode: AgentGuardMode,
) -> tuple[CheckpointDecision, Optional[str]]:
    """Enforce max_actions / max_write_actions."""
    if scope.max_actions and session_action_count >= scope.max_actions:
        violation = f"Session exceeded max_actions limit ({scope.max_actions})"
        if mode == AgentGuardMode.MONITOR_ONLY:
            return CheckpointDecision.WOULD_BLOCK, f"[monitor] {violation}"
        return CheckpointDecision.BLOCK, violation

    if (
        scope.max_write_actions
        and action.action_category in (ActionCategory.WRITE, ActionCategory.DDL, ActionCategory.ADMIN)
        and session_write_count >= scope.max_write_actions
    ):
        violation = f"Session exceeded max_write_actions limit ({scope.max_write_actions})"
        if mode == AgentGuardMode.MONITOR_ONLY:
            return CheckpointDecision.WOULD_BLOCK, f"[monitor] {violation}"
        return CheckpointDecision.BLOCK, violation

    return CheckpointDecision.AUTO_APPROVE, None


def load_template(template_name: str, variables: Optional[dict[str, str]] = None) -> ScopeManifest:
    """Load `templates/{name}.json`; substitute `${key}` from variables."""
    template_path = _TEMPLATES_DIR / f"{template_name}.json"
    if not template_path.exists():
        available = [f.stem for f in _TEMPLATES_DIR.glob("*.json")]
        raise FileNotFoundError(f"Scope template '{template_name}' not found. Available templates: {available}")

    raw = template_path.read_text()

    if variables:
        for key, value in variables.items():
            raw = raw.replace(f"${{{key}}}", value)

    unresolved = re.findall(r"\$\{(\w+)\}", raw)
    if unresolved:
        raise ValueError(
            f"Scope template '{template_name}' has unresolved variables: {unresolved}. "
            f"Provide them via variables parameter."
        )

    data = json.loads(raw)
    return ScopeManifest.model_validate(data)


def list_templates() -> list[str]:
    if not _TEMPLATES_DIR.exists():
        return []
    return sorted(f.stem for f in _TEMPLATES_DIR.glob("*.json"))

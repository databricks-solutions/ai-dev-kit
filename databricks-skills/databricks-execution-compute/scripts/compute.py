#!/usr/bin/env python3
"""Compute CLI - Execute code and manage compute resources on Databricks.

Standalone script with no external dependencies beyond databricks-sdk.

Commands:
- execute-code: Run code on serverless or cluster compute
- list-compute: List clusters, node types, or spark versions
- manage-cluster: Create, start, terminate, or delete clusters

Requires: pip install databricks-sdk
"""

import argparse
import base64
import json
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, List, Optional

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound
from databricks.sdk.service.compute import (
    ClusterSource,
    CommandStatus,
    ContextStatus,
    Environment,
    Language,
    ListClustersFilterBy,
    ResultType,
    State,
)
from databricks.sdk.service.jobs import (
    JobEnvironment,
    NotebookTask,
    RunResultState,
    Source,
    SubmitTask,
)
from databricks.sdk.service.workspace import ImportFormat, Language as WsLang


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def get_workspace_client() -> WorkspaceClient:
    """Get authenticated WorkspaceClient using standard auth chain."""
    return WorkspaceClient()


def get_current_username() -> str:
    """Get the current user's username."""
    w = get_workspace_client()
    return w.current_user.me().user_name


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class NoRunningClusterError(Exception):
    """Raised when no running cluster is available."""

    def __init__(self, message: str, suggestions: List[str] = None, startable_clusters: List[Dict] = None):
        super().__init__(message)
        self.suggestions = suggestions or []
        self.startable_clusters = startable_clusters or []


# ---------------------------------------------------------------------------
# Result Classes
# ---------------------------------------------------------------------------

@dataclass
class ExecutionResult:
    """Result from cluster command execution."""
    success: bool
    output: str = ""
    error: str = ""
    cluster_id: str = ""
    context_id: str = ""
    status: str = ""
    result_type: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "cluster_id": self.cluster_id,
            "context_id": self.context_id,
            "status": self.status,
            "result_type": self.result_type,
        }


@dataclass
class ServerlessRunResult:
    """Result from serverless code execution."""
    success: bool
    output: str = ""
    error: str = ""
    run_id: int = 0
    run_page_url: str = ""
    state: str = ""
    execution_duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "run_id": self.run_id,
            "run_page_url": self.run_page_url,
            "state": self.state,
            "execution_duration_ms": self.execution_duration_ms,
        }


# ---------------------------------------------------------------------------
# Cluster Execution
# ---------------------------------------------------------------------------

def list_clusters() -> List[Dict[str, Any]]:
    """List interactive clusters created by humans (UI/API, not jobs)."""
    w = get_workspace_client()
    clusters = []
    # Filter to only UI and API created clusters (interactive, human-created)
    # Excludes JOB clusters (created by jobs) and other system clusters
    filter_by = ListClustersFilterBy(
        cluster_sources=[ClusterSource.UI, ClusterSource.API]
    )
    for c in w.clusters.list(filter_by=filter_by, page_size=100):
        clusters.append({
            "cluster_id": c.cluster_id,
            "cluster_name": c.cluster_name,
            "state": c.state.value if c.state else "UNKNOWN",
            "creator_user_name": c.creator_user_name,
            "spark_version": c.spark_version,
            "node_type_id": c.node_type_id,
            "num_workers": c.num_workers,
        })
    return clusters


def get_best_cluster() -> str:
    """Get the best running interactive cluster ID, or raise NoRunningClusterError."""
    w = get_workspace_client()
    running = []
    startable = []

    # Filter to only interactive clusters (UI/API created)
    filter_by = ListClustersFilterBy(
        cluster_sources=[ClusterSource.UI, ClusterSource.API]
    )
    for c in w.clusters.list(filter_by=filter_by, page_size=100):
        info = {
            "cluster_id": c.cluster_id,
            "cluster_name": c.cluster_name,
            "state": c.state.value if c.state else "UNKNOWN",
        }
        if c.state == State.RUNNING:
            running.append(info)
        elif c.state in (State.TERMINATED, State.PENDING):
            startable.append(info)

    if running:
        return running[0]["cluster_id"]

    raise NoRunningClusterError(
        "No running cluster available.",
        suggestions=[
            "Start an existing cluster with: python compute.py manage-cluster --action start --cluster-id <ID>",
            "Use serverless compute: python compute.py execute-code --compute-type serverless --code '...'",
        ],
        startable_clusters=startable,
    )


def start_cluster(cluster_id: str) -> Dict[str, Any]:
    """Start a cluster and wait for it to be running."""
    w = get_workspace_client()
    w.clusters.start(cluster_id=cluster_id)
    # Don't wait - just return immediately
    return {"success": True, "cluster_id": cluster_id, "message": "Cluster start initiated"}


def get_cluster_status(cluster_id: str) -> Dict[str, Any]:
    """Get the status of a specific cluster."""
    w = get_workspace_client()
    c = w.clusters.get(cluster_id=cluster_id)
    return {
        "success": True,
        "cluster_id": c.cluster_id,
        "cluster_name": c.cluster_name,
        "state": c.state.value if c.state else "UNKNOWN",
        "state_message": c.state_message,
        "creator_user_name": c.creator_user_name,
        "spark_version": c.spark_version,
        "node_type_id": c.node_type_id,
        "num_workers": c.num_workers,
    }


def _get_or_create_context(w: WorkspaceClient, cluster_id: str, context_id: Optional[str], language: str) -> str:
    """Get existing context or create a new one."""
    lang_map = {"python": Language.PYTHON, "scala": Language.SCALA, "sql": Language.SQL, "r": Language.R}
    lang = lang_map.get(language.lower(), Language.PYTHON)

    if context_id:
        # Verify context exists
        try:
            status = w.command_execution.context_status(cluster_id=cluster_id, context_id=context_id)
            if status.status == ContextStatus.RUNNING:
                return context_id
        except Exception:
            pass  # Context doesn't exist, create new one

    # Create new context
    ctx = w.command_execution.create(cluster_id=cluster_id, language=lang).result()
    return ctx.id


def execute_databricks_command(
    code: str,
    cluster_id: Optional[str] = None,
    context_id: Optional[str] = None,
    language: str = "python",
    timeout: int = 120,
    destroy_context_on_completion: bool = False,
) -> ExecutionResult:
    """Execute code on a Databricks cluster using Command Execution API."""
    w = get_workspace_client()

    # Get cluster ID if not provided
    if not cluster_id:
        cluster_id = get_best_cluster()

    # Get or create context
    ctx_id = _get_or_create_context(w, cluster_id, context_id, language)

    # Execute command
    lang_map = {"python": Language.PYTHON, "scala": Language.SCALA, "sql": Language.SQL, "r": Language.R}
    lang = lang_map.get(language.lower(), Language.PYTHON)

    try:
        cmd = w.command_execution.execute(
            cluster_id=cluster_id,
            context_id=ctx_id,
            language=lang,
            command=code,
        ).result(timeout=timedelta(seconds=timeout))

        # Parse results
        output = ""
        error = ""
        result_type = cmd.results.result_type.value if cmd.results and cmd.results.result_type else ""

        if cmd.results:
            if cmd.results.result_type == ResultType.TEXT:
                output = cmd.results.data or ""
            elif cmd.results.result_type == ResultType.TABLE:
                output = json.dumps(cmd.results.data) if cmd.results.data else ""
            elif cmd.results.result_type == ResultType.ERROR:
                error = cmd.results.cause or str(cmd.results.data) or "Unknown error"

        success = cmd.status == CommandStatus.FINISHED and cmd.results.result_type != ResultType.ERROR

        return ExecutionResult(
            success=success,
            output=output,
            error=error,
            cluster_id=cluster_id,
            context_id=ctx_id,
            status=cmd.status.value if cmd.status else "",
            result_type=result_type,
        )

    finally:
        if destroy_context_on_completion and ctx_id:
            try:
                w.command_execution.destroy(cluster_id=cluster_id, context_id=ctx_id)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Serverless Execution
# ---------------------------------------------------------------------------

def run_code_on_serverless(
    code: str,
    language: str = "python",
    timeout: int = 1800,
    environments: Optional[List[Any]] = None,
) -> ServerlessRunResult:
    """Run code on serverless compute using Jobs API runs/submit.

    Args:
        code: Source to execute.
        language: "python" or "sql".
        timeout: Max wait time in seconds.
        environments: Optional list of environments to install dependencies.
            Each entry may be a dict (documented shape) or a typed
            ``JobEnvironment``. Dict shape:
                {"environment_key": "my_env",
                 "spec": {"client": "4", "dependencies": ["pandas", "mlflow"]}}
            ``client`` must be ``"4"`` (or higher) for dependencies to install;
            ``"1"`` is the default but does NOT install ``dependencies``.
    """
    w = get_workspace_client()

    # Create temp notebook
    username = get_current_username()
    notebook_name = f"_tmp_serverless_{uuid.uuid4().hex[:8]}"
    notebook_path = f"/Workspace/Users/{username}/.tmp/{notebook_name}"

    # Ensure directory exists
    try:
        w.workspace.mkdirs(f"/Workspace/Users/{username}/.tmp")
    except Exception:
        pass

    # Upload notebook content
    if language.lower() == "sql":
        notebook_content = f"-- Databricks notebook source\n{code}"
    else:
        notebook_content = f"# Databricks notebook source\n{code}"

    content_b64 = base64.b64encode(notebook_content.encode()).decode()

    ws_lang_map = {"python": WsLang.PYTHON, "sql": WsLang.SQL}
    ws_lang = ws_lang_map.get(language.lower(), WsLang.PYTHON)

    w.workspace.import_(
        path=notebook_path,
        content=content_b64,
        format=ImportFormat.SOURCE,
        language=ws_lang,
        overwrite=True,
    )

    # Normalize environments (accept dicts or typed JobEnvironment).
    # The SDK serializes each list item via .as_dict(), so raw dicts fail there;
    # typed objects also lack .get(), so we need to canonicalize before reading
    # environment_key for the task binding.
    if environments:
        normalized = []
        for e in environments:
            if isinstance(e, JobEnvironment):
                normalized.append(e)
            elif isinstance(e, dict):
                spec = e.get("spec", {})
                if isinstance(spec, dict):
                    spec = Environment(**spec)
                elif not isinstance(spec, Environment):
                    raise TypeError(
                        f"environments[].spec must be a dict or Environment, got {type(spec).__name__}"
                    )
                normalized.append(
                    JobEnvironment(
                        environment_key=e.get("environment_key", "default"),
                        spec=spec,
                    )
                )
            else:
                raise TypeError(
                    f"environments[] entries must be dict or JobEnvironment, got {type(e).__name__}"
                )
        job_envs = normalized
        env_key = job_envs[0].environment_key or "default"
    else:
        job_envs = [JobEnvironment(environment_key="default", spec=Environment(client="1"))]
        env_key = "default"

    try:
        # Submit run
        run = w.jobs.submit(
            run_name=f"serverless-run-{uuid.uuid4().hex[:8]}",
            tasks=[
                SubmitTask(
                    task_key="main",
                    notebook_task=NotebookTask(
                        notebook_path=notebook_path,
                        source=Source.WORKSPACE,
                    ),
                    environment_key=env_key,
                )
            ],
            environments=job_envs,
        ).result(timeout=timedelta(seconds=timeout))

        # Get run output
        run_output = w.jobs.get_run_output(run_id=run.tasks[0].run_id)

        output = ""
        error = ""
        success = run.state.result_state == RunResultState.SUCCESS

        if run_output.notebook_output and run_output.notebook_output.result:
            output = run_output.notebook_output.result
        if run_output.error:
            error = run_output.error

        return ServerlessRunResult(
            success=success,
            output=output,
            error=error,
            run_id=run.run_id,
            run_page_url=run.run_page_url or "",
            state=run.state.result_state.value if run.state and run.state.result_state else "",
            execution_duration_ms=run.execution_duration or 0,
        )

    finally:
        # Cleanup temp notebook
        try:
            w.workspace.delete(notebook_path)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Cluster Management
# ---------------------------------------------------------------------------

def create_cluster(
    name: str,
    num_workers: int = 1,
    autotermination_minutes: int = 120,
    spark_version: Optional[str] = None,
    node_type_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new cluster."""
    w = get_workspace_client()

    # Get defaults if not provided
    if not spark_version:
        versions = list(w.clusters.spark_versions())
        # Pick latest LTS
        for v in versions:
            if "LTS" in v.name and "ML" not in v.name:
                spark_version = v.key
                break
        if not spark_version and versions:
            spark_version = versions[0].key

    if not node_type_id:
        node_types = list(w.clusters.list_node_types().node_types)
        # Pick smallest available
        for nt in sorted(node_types, key=lambda x: x.memory_mb or 0):
            if nt.is_deprecated is not True:
                node_type_id = nt.node_type_id
                break

    cluster = w.clusters.create(
        cluster_name=name,
        spark_version=spark_version,
        node_type_id=node_type_id,
        num_workers=num_workers,
        autotermination_minutes=autotermination_minutes,
    ).result()

    return {
        "success": True,
        "cluster_id": cluster.cluster_id,
        "cluster_name": name,
        "message": "Cluster created",
    }


def terminate_cluster(cluster_id: str) -> Dict[str, Any]:
    """Terminate a cluster (can be restarted)."""
    w = get_workspace_client()
    w.clusters.delete(cluster_id=cluster_id)
    return {"success": True, "cluster_id": cluster_id, "message": "Cluster terminated"}


def delete_cluster(cluster_id: str) -> Dict[str, Any]:
    """Permanently delete a cluster."""
    w = get_workspace_client()
    w.clusters.permanent_delete(cluster_id=cluster_id)
    return {"success": True, "cluster_id": cluster_id, "message": "Cluster permanently deleted"}


def list_node_types() -> List[Dict[str, Any]]:
    """List available node types."""
    w = get_workspace_client()
    result = []
    for nt in w.clusters.list_node_types().node_types:
        result.append({
            "node_type_id": nt.node_type_id,
            "memory_mb": nt.memory_mb,
            "num_cores": nt.num_cores,
            "description": nt.description,
            "is_deprecated": nt.is_deprecated,
        })
    return result


def list_spark_versions() -> List[Dict[str, Any]]:
    """List available Spark versions."""
    w = get_workspace_client()
    result = []
    response = w.clusters.spark_versions()
    for v in response.versions or []:
        result.append({
            "key": v.key,
            "name": v.name,
        })
    return result


# ---------------------------------------------------------------------------
# CLI Commands
# ---------------------------------------------------------------------------

def _none_if_empty(value):
    """Convert empty strings to None."""
    return None if value == "" else value


def _no_cluster_error_response(e: NoRunningClusterError) -> Dict[str, Any]:
    """Build a structured error response when no running cluster is available."""
    return {
        "success": False,
        "error": str(e),
        "suggestions": e.suggestions,
        "startable_clusters": e.startable_clusters,
    }


def cmd_execute_code(args):
    """Execute code on Databricks via serverless or cluster compute."""
    code = _none_if_empty(args.code)
    file_path = _none_if_empty(args.file)
    cluster_id = _none_if_empty(args.cluster_id)
    context_id = _none_if_empty(args.context_id)
    language = _none_if_empty(args.language) or "python"
    compute_type = args.compute_type
    timeout = args.timeout
    destroy_context = args.destroy_context

    # Parse --environments (JSON string or @path/to/file.json) for serverless
    environments = None
    env_arg = _none_if_empty(getattr(args, "environments", None))
    if env_arg:
        try:
            if env_arg.startswith("@"):
                with open(env_arg[1:], "r", encoding="utf-8") as fh:
                    environments = json.load(fh)
            else:
                environments = json.loads(env_arg)
        except (OSError, json.JSONDecodeError) as e:
            return {"success": False, "error": f"Invalid --environments: {e}"}
        if not isinstance(environments, list):
            return {"success": False,
                    "error": "--environments must be a JSON array of environment objects"}

    if not code and not file_path:
        return {"success": False, "error": "Either --code or --file must be provided."}

    # Read code from file if provided
    if file_path and not code:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()
        except FileNotFoundError:
            return {"success": False, "error": f"File not found: {file_path}"}

    # Resolve "auto" compute type
    if compute_type == "auto":
        if cluster_id or context_id:
            compute_type = "cluster"
        elif language.lower() in ("scala", "r"):
            compute_type = "cluster"
        else:
            compute_type = "serverless"

    # Serverless execution
    if compute_type == "serverless":
        default_timeout = timeout if timeout else 1800
        try:
            result = run_code_on_serverless(
                code=code,
                language=language,
                timeout=default_timeout,
                environments=environments,
            )
        except TypeError as e:
            return {"success": False, "error": str(e)}
        return result.to_dict()

    if environments:
        return {"success": False,
                "error": "--environments is only supported with --compute-type serverless"}

    # Cluster execution
    default_timeout = timeout if timeout else 120
    try:
        result = execute_databricks_command(
            code=code,
            cluster_id=cluster_id,
            context_id=context_id,
            language=language,
            timeout=default_timeout,
            destroy_context_on_completion=destroy_context,
        )
        return result.to_dict()
    except NoRunningClusterError as e:
        return _no_cluster_error_response(e)


def cmd_list_compute(args):
    """List compute resources: clusters, node types, or spark versions."""
    resource = args.resource.lower()
    cluster_id = _none_if_empty(args.cluster_id)
    auto_select = args.auto_select

    if resource == "clusters":
        if cluster_id:
            return get_cluster_status(cluster_id)
        if auto_select:
            try:
                best = get_best_cluster()
                return {"cluster_id": best}
            except NoRunningClusterError as e:
                return _no_cluster_error_response(e)
        return {"clusters": list_clusters()}

    elif resource == "node_types":
        return {"node_types": list_node_types()}

    elif resource == "spark_versions":
        return {"spark_versions": list_spark_versions()}

    else:
        return {"success": False, "error": f"Unknown resource: {resource}. Use: clusters, node_types, spark_versions"}


def cmd_manage_cluster(args):
    """Create, start, terminate, or delete a cluster."""
    action = args.action.lower()
    cluster_id = _none_if_empty(args.cluster_id)
    name = _none_if_empty(args.name)

    if action == "create":
        if not name:
            return {"success": False, "error": "name is required for create action."}
        return create_cluster(
            name=name,
            num_workers=args.num_workers or 1,
            autotermination_minutes=args.autotermination_minutes or 120,
        )

    elif action == "start":
        if not cluster_id:
            return {"success": False, "error": "cluster_id is required for start action."}
        return start_cluster(cluster_id)

    elif action == "terminate":
        if not cluster_id:
            return {"success": False, "error": "cluster_id is required for terminate action."}
        return terminate_cluster(cluster_id)

    elif action == "delete":
        if not cluster_id:
            return {"success": False, "error": "cluster_id is required for delete action."}
        return delete_cluster(cluster_id)

    elif action == "get":
        if not cluster_id:
            return {"success": False, "error": "cluster_id is required for get action."}
        try:
            return get_cluster_status(cluster_id)
        except NotFound:
            return {"success": False, "cluster_id": cluster_id, "state": "DELETED", "exists": False}
        except Exception as e:
            return {"success": False, "error": str(e)}

    else:
        return {"success": False, "error": f"Unknown action: {action}. Use: create, start, terminate, delete, get"}


# ---------------------------------------------------------------------------
# CLI Setup
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Execute code and manage compute on Databricks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # execute-code
    exec_parser = subparsers.add_parser("execute-code", help="Run code on Databricks")
    exec_parser.add_argument("--code", help="Code to execute")
    exec_parser.add_argument("--file", help="File to execute")
    exec_parser.add_argument("--compute-type", default="auto", choices=["auto", "serverless", "cluster"],
                            help="Compute type (default: auto)")
    exec_parser.add_argument("--cluster-id", help="Cluster ID (for cluster compute)")
    exec_parser.add_argument("--context-id", help="Context ID (reuse existing context)")
    exec_parser.add_argument("--language", default="python", choices=["python", "scala", "sql", "r"],
                            help="Language (default: python)")
    exec_parser.add_argument("--timeout", type=int, help="Timeout in seconds")
    exec_parser.add_argument("--destroy-context", action="store_true", help="Destroy context after execution")
    exec_parser.add_argument(
        "--environments",
        help=(
            "Serverless only. JSON array of environments (or @path/to/file.json). "
            'Example: \'[{"environment_key":"ml_env","spec":{"client":"4",'
            '"dependencies":["mlflow","scikit-learn"]}}]\'. '
            'IMPORTANT: "client":"4" installs dependencies; "1" does not.'
        ),
    )
    exec_parser.set_defaults(func=cmd_execute_code)

    # list-compute
    list_parser = subparsers.add_parser("list-compute", help="List compute resources")
    list_parser.add_argument("--resource", default="clusters", choices=["clusters", "node_types", "spark_versions"],
                            help="Resource to list (default: clusters)")
    list_parser.add_argument("--cluster-id", help="Get specific cluster status")
    list_parser.add_argument("--auto-select", action="store_true", help="Return best running cluster")
    list_parser.set_defaults(func=cmd_list_compute)

    # manage-cluster
    manage_parser = subparsers.add_parser("manage-cluster", help="Manage clusters")
    manage_parser.add_argument("--action", required=True, choices=["create", "start", "terminate", "delete", "get"],
                              help="Action to perform")
    manage_parser.add_argument("--cluster-id", help="Cluster ID")
    manage_parser.add_argument("--name", help="Cluster name (for create)")
    manage_parser.add_argument("--num-workers", type=int, help="Number of workers (for create)")
    manage_parser.add_argument("--autotermination-minutes", type=int, help="Auto-termination minutes (for create)")
    manage_parser.set_defaults(func=cmd_manage_cluster)

    args = parser.parse_args()
    result = args.func(args)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()

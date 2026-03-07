"""
Compute - Execution Context Operations

Functions for executing code on Databricks clusters using execution contexts.
Uses Databricks Command Execution API via SDK.
"""

import datetime
from typing import Optional, List, Dict, Any
from databricks.sdk.service.compute import (
    CommandStatus,
    ClusterSource,
    DataSecurityMode,
    Language,
    ListClustersFilterBy,
    State,
)

from ..auth import get_workspace_client, get_current_username

import logging

logger = logging.getLogger(__name__)


class ExecutionResult:
    """Result from code execution on a Databricks cluster.

    Attributes:
        success: Whether the execution completed successfully.
        output: The output from the execution (if successful).
        error: The error message (if failed).
        cluster_id: The cluster ID used for execution.
        context_id: The execution context ID. Can be reused for follow-up
                   commands to maintain state and speed up execution.
        context_destroyed: Whether the context was destroyed after execution.
                          If False, the context_id can be reused.
        message: A helpful message about reusing the context.
    """

    def __init__(
        self,
        success: bool,
        output: Optional[str] = None,
        error: Optional[str] = None,
        cluster_id: Optional[str] = None,
        context_id: Optional[str] = None,
        context_destroyed: bool = True,
    ):
        self.success = success
        self.output = output
        self.error = error
        self.cluster_id = cluster_id
        self.context_id = context_id
        self.context_destroyed = context_destroyed

        # Generate helpful message
        if success and context_id and not context_destroyed:
            self.message = (
                f"Execution successful. To speed up follow-up commands and maintain "
                f"state (variables, imports), reuse context_id='{context_id}' with "
                f"cluster_id='{cluster_id}'."
            )
        elif success and context_destroyed:
            self.message = "Execution successful. Context was destroyed."
        elif not success:
            self.message = None
        else:
            self.message = None

    def __repr__(self):
        if self.success:
            return (
                f"ExecutionResult(success=True, output={repr(self.output)}, "
                f"cluster_id={repr(self.cluster_id)}, context_id={repr(self.context_id)})"
            )
        return f"ExecutionResult(success=False, error={repr(self.error)})"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "cluster_id": self.cluster_id,
            "context_id": self.context_id,
            "context_destroyed": self.context_destroyed,
            "message": self.message,
        }


# Only list user-created clusters (UI or API), not job/pipeline clusters
_USER_CLUSTER_SOURCES = [ClusterSource.UI, ClusterSource.API]

# Language string to enum mapping
_LANGUAGE_MAP = {
    "python": Language.PYTHON,
    "scala": Language.SCALA,
    "sql": Language.SQL,
    "r": Language.R,
}


def list_clusters(
    include_terminated: bool = True,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    List user-created clusters in the workspace.

    Only returns clusters created by users (via UI or API), not job or pipeline clusters.
    Searches running clusters first, then terminated if include_terminated=True.

    Args:
        include_terminated: If True, includes terminated clusters in results.
                           If False, only returns running/pending clusters.
        limit: Maximum number of clusters to return. None means no limit.

    Returns:
        List of cluster info dicts with cluster_id, cluster_name, state, etc.
    """
    w = get_workspace_client()
    clusters = []

    def _add_cluster(cluster) -> bool:
        """Add cluster to list, return False if limit reached."""
        clusters.append(
            {
                "cluster_id": cluster.cluster_id,
                "cluster_name": cluster.cluster_name,
                "state": cluster.state.value if cluster.state else None,
                "creator_user_name": cluster.creator_user_name,
                "cluster_source": cluster.cluster_source.value if cluster.cluster_source else None,
            }
        )
        return limit is None or len(clusters) < limit

    # First, get running clusters (faster query)
    running_filter = ListClustersFilterBy(
        cluster_sources=_USER_CLUSTER_SOURCES,
        cluster_states=[State.RUNNING, State.PENDING, State.RESIZING, State.RESTARTING],
    )
    for cluster in w.clusters.list(filter_by=running_filter):
        if not _add_cluster(cluster):
            return clusters

    # If requested and not at limit, also get terminated clusters
    if include_terminated and (limit is None or len(clusters) < limit):
        terminated_filter = ListClustersFilterBy(
            cluster_sources=_USER_CLUSTER_SOURCES,
            cluster_states=[State.TERMINATED, State.TERMINATING, State.ERROR],
        )
        for cluster in w.clusters.list(filter_by=terminated_filter):
            if not _add_cluster(cluster):
                return clusters

    return clusters


def _is_cluster_accessible(cluster, current_user: Optional[str]) -> bool:
    """Check whether the current user can use this cluster.

    A cluster is inaccessible when its data_security_mode is SINGLE_USER
    and the single_user_name doesn't match the current user.

    Args:
        cluster: SDK ClusterDetails object.
        current_user: Current user's username/email, or None if unknown.

    Returns:
        True if the cluster is accessible (or we can't determine either way).
    """
    if current_user is None:
        # Can't determine access — assume accessible (graceful degradation)
        return True

    dsm = getattr(cluster, "data_security_mode", None)
    single_user = getattr(cluster, "single_user_name", None)

    # If it's a single-user cluster assigned to someone else, skip it
    if dsm == DataSecurityMode.SINGLE_USER and single_user:
        if single_user.lower() != current_user.lower():
            logger.debug(
                f"Skipping cluster '{cluster.cluster_name}' ({cluster.cluster_id}): "
                f"single-user cluster owned by {single_user}, current user is {current_user}"
            )
            return False

    return True


class ClusterSelectionResult:
    """Result from get_best_cluster with details about skipped clusters."""

    def __init__(
        self,
        cluster_id: Optional[str],
        skipped_clusters: Optional[List[Dict[str, str]]] = None,
    ):
        self.cluster_id = cluster_id
        self.skipped_clusters = skipped_clusters or []


def get_best_cluster() -> Optional[str]:
    """
    Get the ID of the best available cluster for code execution.

    Only considers user-created clusters (UI or API), not job or pipeline clusters.
    Filters out single-user clusters that belong to a different user.

    Selection logic:
    1. Only considers RUNNING clusters accessible to the current user
    2. Prefers clusters with "shared" in the name (case-insensitive)
    3. Then prefers clusters with "demo" in the name
    4. Otherwise returns the first running cluster

    Returns:
        Cluster ID string, or None if no running clusters available.
    """
    return _select_best_cluster().cluster_id


def _select_best_cluster() -> ClusterSelectionResult:
    """Internal cluster selection that also tracks skipped clusters.

    Returns:
        ClusterSelectionResult with the selected cluster_id and any skipped clusters.
    """
    w = get_workspace_client()
    current_user = get_current_username()

    # Only get running user-created clusters
    running_filter = ListClustersFilterBy(
        cluster_sources=_USER_CLUSTER_SOURCES,
        cluster_states=[State.RUNNING],
    )

    running_clusters = []
    skipped_clusters = []
    for cluster in w.clusters.list(filter_by=running_filter):
        if not _is_cluster_accessible(cluster, current_user):
            skipped_clusters.append(
                {
                    "cluster_id": cluster.cluster_id,
                    "cluster_name": cluster.cluster_name or "",
                    "single_user_name": getattr(cluster, "single_user_name", None) or "unknown",
                }
            )
            continue
        running_clusters.append(
            {
                "cluster_id": cluster.cluster_id,
                "cluster_name": cluster.cluster_name or "",
            }
        )

    if not running_clusters:
        return ClusterSelectionResult(cluster_id=None, skipped_clusters=skipped_clusters)

    # Priority 1: clusters with "shared" in name
    for c in running_clusters:
        if "shared" in c["cluster_name"].lower():
            return ClusterSelectionResult(cluster_id=c["cluster_id"], skipped_clusters=skipped_clusters)

    # Priority 2: clusters with "demo" in name
    for c in running_clusters:
        if "demo" in c["cluster_name"].lower():
            return ClusterSelectionResult(cluster_id=c["cluster_id"], skipped_clusters=skipped_clusters)

    # Fallback: first running cluster
    return ClusterSelectionResult(cluster_id=running_clusters[0]["cluster_id"], skipped_clusters=skipped_clusters)


class NoRunningClusterError(Exception):
    """Raised when no running cluster is available and none was specified.

    Provides structured data so agents can present actionable options to the user.

    Attributes:
        available_clusters: All clusters visible to the user (any state).
        skipped_clusters: Running clusters filtered out (e.g., single-user owned by others).
        startable_clusters: Terminated clusters the user can start.
        suggestions: List of actionable suggestion strings for the agent/user.
    """

    def __init__(
        self,
        available_clusters: List[Dict[str, str]],
        skipped_clusters: Optional[List[Dict[str, str]]] = None,
        startable_clusters: Optional[List[Dict[str, str]]] = None,
    ):
        self.available_clusters = available_clusters
        self.skipped_clusters = skipped_clusters or []
        self.startable_clusters = startable_clusters or []
        self.suggestions = self._build_suggestions()

        message = self._build_message()
        super().__init__(message)

    def _build_suggestions(self) -> List[str]:
        """Build a list of actionable suggestions based on available resources."""
        suggestions = []

        # Suggestion 1: offer to start a terminated cluster (agent should ask user first)
        if self.startable_clusters:
            best = self.startable_clusters[0]
            suggestions.append(
                f"ASK THE USER: \"I found your terminated cluster '{best['cluster_name']}'. "
                f'Would you like me to start it? (It typically takes 3-8 minutes to start.)". '
                f"If they approve, call start_cluster(cluster_id='{best['cluster_id']}'), "
                f"then poll with get_cluster_status() until it's RUNNING, then retry."
            )
            # Show additional options if there are more
            for c in self.startable_clusters[1:3]:
                suggestions.append(
                    f"Alternative cluster: '{c['cluster_name']}' (cluster_id='{c['cluster_id']}', state={c['state']})"
                )

        # Suggestion 2: use execute_sql for SQL workloads
        suggestions.append(
            "For SQL-only workloads, use execute_sql() instead — it routes through "
            "SQL warehouses and doesn't require a cluster."
        )

        # Suggestion 3: ask for shared access
        suggestions.append("Ask a workspace admin for access to a shared cluster.")

        return suggestions

    def _build_message(self) -> str:
        """Build a human-readable error message."""
        message = "No running cluster available for the current user."

        if self.startable_clusters:
            cluster_list = "\n".join(
                f"  - {c['cluster_name']} ({c['cluster_id']}) - {c['state']}" for c in self.startable_clusters[:10]
            )
            message += (
                f"\n\nYou have {len(self.startable_clusters)} terminated cluster(s) you could start:\n{cluster_list}"
            )

        if self.skipped_clusters:
            skipped_list = "\n".join(
                f"  - {c['cluster_name']} ({c['cluster_id']}) - owned by {c.get('single_user_name', 'unknown')}"
                for c in self.skipped_clusters
            )
            message += (
                f"\n\n{len(self.skipped_clusters)} running cluster(s) were skipped because they are "
                f"single-user clusters assigned to a different user:\n{skipped_list}"
            )

        message += "\n\nSuggestions:\n"
        for i, suggestion in enumerate(self.suggestions, 1):
            message += f"  {i}. {suggestion}\n"

        return message


def start_cluster(cluster_id: str) -> Dict[str, Any]:
    """
    Start a terminated Databricks cluster.

    This initiates the cluster start process and returns immediately — it does
    NOT wait for the cluster to reach RUNNING state (that typically takes 3-8
    minutes).  Use ``get_cluster_status()`` to poll until the cluster is ready.

    Args:
        cluster_id: ID of the cluster to start.

    Returns:
        Dictionary with cluster_id, cluster_name, state, and a message.

    Raises:
        Exception: If the cluster cannot be started (e.g., permissions, not found).
    """
    w = get_workspace_client()

    # Get cluster info first for a better response message
    cluster = w.clusters.get(cluster_id)
    cluster_name = cluster.cluster_name or cluster_id
    current_state = cluster.state.value if cluster.state else "UNKNOWN"

    if current_state == "RUNNING":
        return {
            "cluster_id": cluster_id,
            "cluster_name": cluster_name,
            "state": "RUNNING",
            "message": f"Cluster '{cluster_name}' is already running.",
        }

    if current_state not in ("TERMINATED", "ERROR"):
        return {
            "cluster_id": cluster_id,
            "cluster_name": cluster_name,
            "state": current_state,
            "message": (
                f"Cluster '{cluster_name}' is in state {current_state}. It may already be starting or resizing."
            ),
        }

    # Kick off start (non-blocking)
    w.clusters.start(cluster_id)

    return {
        "cluster_id": cluster_id,
        "cluster_name": cluster_name,
        "previous_state": current_state,
        "state": "PENDING",
        "message": (
            f"Cluster '{cluster_name}' is now starting. "
            f"This typically takes 3-8 minutes. "
            f"Use get_cluster_status(cluster_id='{cluster_id}') to check progress."
        ),
    }


def get_cluster_status(cluster_id: str) -> Dict[str, Any]:
    """
    Get the current status of a Databricks cluster.

    Useful for polling a cluster after calling ``start_cluster()`` to check
    whether it has reached RUNNING state.

    Args:
        cluster_id: ID of the cluster.

    Returns:
        Dictionary with cluster_id, cluster_name, state, and a message.
    """
    w = get_workspace_client()
    cluster = w.clusters.get(cluster_id)

    cluster_name = cluster.cluster_name or cluster_id
    state = cluster.state.value if cluster.state else "UNKNOWN"

    if state == "RUNNING":
        message = f"Cluster '{cluster_name}' is running and ready for use."
    elif state in ("PENDING", "RESTARTING", "RESIZING"):
        message = f"Cluster '{cluster_name}' is {state.lower()}. Please wait and check again in 30-60 seconds."
    elif state == "TERMINATED":
        message = f"Cluster '{cluster_name}' is terminated."
    elif state == "TERMINATING":
        message = f"Cluster '{cluster_name}' is shutting down."
    else:
        message = f"Cluster '{cluster_name}' is in state: {state}."

    return {
        "cluster_id": cluster_id,
        "cluster_name": cluster_name,
        "state": state,
        "message": message,
    }


def create_context(cluster_id: str, language: str = "python") -> str:
    """
    Create a new execution context on a Databricks cluster.

    Args:
        cluster_id: ID of the cluster to create context on
        language: Programming language ("python", "scala", "sql", "r")

    Returns:
        Context ID string

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()

    lang_enum = _LANGUAGE_MAP.get(language.lower(), Language.PYTHON)

    # SDK returns Wait object, need to wait for result
    result = w.command_execution.create(
        cluster_id=cluster_id, language=lang_enum
    ).result()  # Blocks until context is created

    return result.id


def destroy_context(cluster_id: str, context_id: str) -> None:
    """
    Destroy an execution context.

    Args:
        cluster_id: ID of the cluster
        context_id: ID of the context to destroy

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    w.command_execution.destroy(cluster_id=cluster_id, context_id=context_id)


def _execute_on_context(cluster_id: str, context_id: str, code: str, language: str, timeout: int) -> ExecutionResult:
    """
    Internal function to execute code on an existing context.

    Args:
        cluster_id: ID of the cluster
        context_id: ID of the execution context
        code: Code to execute
        language: Programming language
        timeout: Maximum time to wait for execution (seconds)

    Returns:
        ExecutionResult with output or error (context_id filled in but context_destroyed=False)
    """
    w = get_workspace_client()
    lang_enum = _LANGUAGE_MAP.get(language.lower(), Language.PYTHON)

    try:
        # Execute and wait for result with timeout
        result = w.command_execution.execute(
            cluster_id=cluster_id, context_id=context_id, language=lang_enum, command=code
        ).result(timeout=datetime.timedelta(seconds=timeout))

        # Check result status (compare with enum values)
        if result.status == CommandStatus.FINISHED:
            # Check if there was an error in the results
            if result.results and result.results.result_type and result.results.result_type.value == "error":
                error_msg = result.results.cause if result.results.cause else "Unknown error"
                return ExecutionResult(
                    success=False,
                    error=error_msg,
                    cluster_id=cluster_id,
                    context_id=context_id,
                    context_destroyed=False,
                )
            output = result.results.data if result.results and result.results.data else "Success (no output)"
            return ExecutionResult(
                success=True,
                output=str(output),
                cluster_id=cluster_id,
                context_id=context_id,
                context_destroyed=False,
            )
        elif result.status in [CommandStatus.ERROR, CommandStatus.CANCELLED]:
            error_msg = result.results.cause if result.results and result.results.cause else "Unknown error"
            return ExecutionResult(
                success=False,
                error=error_msg,
                cluster_id=cluster_id,
                context_id=context_id,
                context_destroyed=False,
            )
        else:
            return ExecutionResult(
                success=False,
                error=f"Unexpected status: {result.status}",
                cluster_id=cluster_id,
                context_id=context_id,
                context_destroyed=False,
            )

    except TimeoutError:
        return ExecutionResult(
            success=False,
            error="Command timed out",
            cluster_id=cluster_id,
            context_id=context_id,
            context_destroyed=False,
        )


def execute_databricks_command(
    code: str,
    cluster_id: Optional[str] = None,
    context_id: Optional[str] = None,
    language: str = "python",
    timeout: int = 120,
    destroy_context_on_completion: bool = False,
) -> ExecutionResult:
    """
    Execute code on a Databricks cluster.

    If context_id is provided, reuses the existing context (faster, maintains state).
    If not provided, creates a new context.

    By default, the context is kept alive for reuse. Set destroy_context_on_completion=True
    to destroy it after execution.

    Args:
        code: Code to execute
        cluster_id: ID of the cluster. If not provided, auto-selects a running cluster
                   (prefers clusters with "shared" or "demo" in name).
        context_id: Optional existing execution context ID. If provided, reuses it
                   for faster execution and state preservation (variables, imports).
        language: Programming language ("python", "scala", "sql", "r")
        timeout: Maximum time to wait for execution (seconds)
        destroy_context_on_completion: If True, destroys the context after execution.
                                       Default is False to allow reuse.

    Returns:
        ExecutionResult with output, error, and context info for reuse.

    Raises:
        NoRunningClusterError: If no cluster_id provided and no running cluster found
        DatabricksError: If API request fails
    """
    # Auto-select cluster if not provided
    if cluster_id is None:
        selection = _select_best_cluster()
        cluster_id = selection.cluster_id
        if cluster_id is None:
            # No accessible running cluster — build an actionable error
            available_clusters = list_clusters(limit=20)

            # Deduplicate clusters by cluster_id (API sometimes returns duplicates)
            seen_ids = set()
            deduped = []
            for c in available_clusters:
                if c["cluster_id"] not in seen_ids:
                    seen_ids.add(c["cluster_id"])
                    deduped.append(c)
            available_clusters = deduped

            # Find terminated clusters the user could start, preferring user-owned
            current_user = get_current_username()
            terminated = [c for c in available_clusters if c.get("state") in ("TERMINATED", "ERROR")]
            if current_user:
                user_lower = current_user.lower()
                user_owned = [c for c in terminated if (c.get("creator_user_name") or "").lower() == user_lower]
                others = [c for c in terminated if (c.get("creator_user_name") or "").lower() != user_lower]
                startable_clusters = user_owned + others
            else:
                startable_clusters = terminated

            raise NoRunningClusterError(
                available_clusters,
                skipped_clusters=selection.skipped_clusters,
                startable_clusters=startable_clusters,
            )

    # Create context if not provided
    context_created = False
    if context_id is None:
        context_id = create_context(cluster_id, language)
        context_created = True

    try:
        # Execute command
        result = _execute_on_context(
            cluster_id=cluster_id,
            context_id=context_id,
            code=code,
            language=language,
            timeout=timeout,
        )

        # Destroy context if requested
        if destroy_context_on_completion:
            try:
                destroy_context(cluster_id, context_id)
                result.context_destroyed = True
                result.message = "Execution successful. Context was destroyed."
            except Exception:
                pass  # Ignore cleanup errors

        return result

    except Exception:
        # If we created the context and there's an error, clean up
        if context_created and destroy_context_on_completion:
            try:
                destroy_context(cluster_id, context_id)
            except Exception:
                pass
        raise


def run_python_file_on_databricks(
    file_path: str,
    cluster_id: Optional[str] = None,
    context_id: Optional[str] = None,
    timeout: int = 600,
    destroy_context_on_completion: bool = False,
) -> ExecutionResult:
    """
    Read a local Python file and execute it on a Databricks cluster.

    This is useful for running data generation scripts or other Python code
    that has been written locally and needs to be executed on Databricks.

    If context_id is provided, reuses the existing context (faster, maintains state).
    If not provided, creates a new context.

    Args:
        file_path: Local path to the Python file to execute
        cluster_id: ID of the cluster to run the code on. If not provided,
                   auto-selects a running cluster (prefers "shared" or "demo").
        context_id: Optional existing execution context ID. If provided, reuses it
                   for faster execution and state preservation.
        timeout: Maximum time to wait for execution (seconds, default 600)
        destroy_context_on_completion: If True, destroys the context after execution.
                                       Default is False to allow reuse.

    Returns:
        ExecutionResult with output, error, and context info for reuse.

    Raises:
        FileNotFoundError: If the file doesn't exist
        NoRunningClusterError: If no cluster_id provided and no running cluster found
        DatabricksError: If API request fails

    Example:
        >>> # First execution - creates context
        >>> result = run_python_file_on_databricks(file_path="/path/to/script.py")
        >>> print(result.context_id)  # Save this for follow-up
        >>>
        >>> # Follow-up execution - reuses context (faster)
        >>> result2 = run_python_file_on_databricks(
        ...     file_path="/path/to/another_script.py",
        ...     cluster_id=result.cluster_id,
        ...     context_id=result.context_id
        ... )
    """
    # Read the file contents
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            code = f.read()
    except FileNotFoundError:
        return ExecutionResult(success=False, error=f"File not found: {file_path}")
    except Exception as e:
        return ExecutionResult(success=False, error=f"Failed to read file {file_path}: {str(e)}")

    if not code.strip():
        return ExecutionResult(success=False, error=f"File is empty: {file_path}")

    # Execute the code on Databricks
    return execute_databricks_command(
        code=code,
        cluster_id=cluster_id,
        context_id=context_id,
        language="python",
        timeout=timeout,
        destroy_context_on_completion=destroy_context_on_completion,
    )

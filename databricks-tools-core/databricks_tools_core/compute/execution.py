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
    Language,
    ListClustersFilterBy,
    State,
)

from ..auth import get_workspace_client


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
        output: str | None = None,
        error: str | None = None,
        cluster_id: str | None = None,
        context_id: str | None = None,
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
                f"ExecutionResult(success=True, output={self.output!r}, "
                f"cluster_id={self.cluster_id!r}, context_id={self.context_id!r})"
            )
        return f"ExecutionResult(success=False, error={self.error!r})"

    def to_dict(self) -> dict[str, Any]:
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
    limit: int | None = None,
) -> list[dict[str, Any]]:
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
        clusters.append({
            "cluster_id": cluster.cluster_id,
            "cluster_name": cluster.cluster_name,
            "state": cluster.state.value if cluster.state else None,
            "creator_user_name": cluster.creator_user_name,
            "cluster_source": cluster.cluster_source.value if cluster.cluster_source else None,
        })
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


def get_best_cluster() -> str | None:
    """
    Get the ID of the best available cluster for code execution.

    Only considers user-created clusters (UI or API), not job or pipeline clusters.

    Selection logic:
    1. Only considers RUNNING clusters
    2. Prefers clusters with "shared" in the name (case-insensitive)
    3. Then prefers clusters with "demo" in the name
    4. Otherwise returns the first running cluster

    Returns:
        Cluster ID string, or None if no running clusters available.
    """
    w = get_workspace_client()

    # Only get running user-created clusters
    running_filter = ListClustersFilterBy(
        cluster_sources=_USER_CLUSTER_SOURCES,
        cluster_states=[State.RUNNING],
    )

    running_clusters = []
    for cluster in w.clusters.list(filter_by=running_filter):
        running_clusters.append({
            "cluster_id": cluster.cluster_id,
            "cluster_name": cluster.cluster_name or "",
        })

    if not running_clusters:
        return None

    # Priority 1: clusters with "shared" in name
    for c in running_clusters:
        if "shared" in c["cluster_name"].lower():
            return c["cluster_id"]

    # Priority 2: clusters with "demo" in name
    for c in running_clusters:
        if "demo" in c["cluster_name"].lower():
            return c["cluster_id"]

    # Fallback: first running cluster
    return running_clusters[0]["cluster_id"]


class NoRunningClusterError(Exception):
    """Raised when no running cluster is available and none was specified."""

    def __init__(self, available_clusters: list[dict[str, str]]):
        self.available_clusters = available_clusters
        cluster_list = "\n".join(
            f"  - {c['cluster_name']} ({c['cluster_id']}) - {c['state']}"
            for c in available_clusters[:20]
        )
        message = (
            "No running cluster available. Please specify a cluster_id or start one of the following clusters:\n"
            f"{cluster_list}"
        )
        if len(available_clusters) > 20:
            message += f"\n  ... and {len(available_clusters) - 20} more"
        super().__init__(message)


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
        cluster_id=cluster_id,
        language=lang_enum
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
    w.command_execution.destroy(
        cluster_id=cluster_id,
        context_id=context_id
    )


def _execute_on_context(
    cluster_id: str,
    context_id: str,
    code: str,
    language: str,
    timeout: int
) -> ExecutionResult:
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
            cluster_id=cluster_id,
            context_id=context_id,
            language=lang_enum,
            command=code
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
            output = (
                result.results.data if result.results and result.results.data
                else "Success (no output)"
            )
            return ExecutionResult(
                success=True,
                output=str(output),
                cluster_id=cluster_id,
                context_id=context_id,
                context_destroyed=False,
            )
        elif result.status in [CommandStatus.ERROR, CommandStatus.CANCELLED]:
            error_msg = (
                result.results.cause if result.results and result.results.cause
                else "Unknown error"
            )
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
    cluster_id: str | None = None,
    context_id: str | None = None,
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
        cluster_id = get_best_cluster()
        if cluster_id is None:
            # No running cluster - raise error with available clusters list (limit to 20)
            available_clusters = list_clusters(limit=20)
            raise NoRunningClusterError(available_clusters)

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
            timeout=timeout
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
    cluster_id: str | None = None,
    context_id: str | None = None,
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
        with open(file_path, encoding='utf-8') as f:
            code = f.read()
    except FileNotFoundError:
        return ExecutionResult(
            success=False,
            error=f"File not found: {file_path}"
        )
    except Exception as e:
        return ExecutionResult(
            success=False,
            error=f"Failed to read file {file_path}: {e!s}"
        )

    if not code.strip():
        return ExecutionResult(
            success=False,
            error=f"File is empty: {file_path}"
        )

    # Execute the code on Databricks
    return execute_databricks_command(
        code=code,
        cluster_id=cluster_id,
        context_id=context_id,
        language="python",
        timeout=timeout,
        destroy_context_on_completion=destroy_context_on_completion,
    )

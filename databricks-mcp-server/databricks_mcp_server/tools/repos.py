"""Git repos tools - Manage Databricks Git repositories in the workspace.

Provides 5 tools:
- list_repos: list all repos, optionally filtered by path prefix
- get_repo: get repo details by ID
- create_or_update_repo: idempotent clone (returns existing if already cloned)
- update_repo: switch branch or tag
- delete_repo: remove a repo from the workspace
"""

from typing import Any, Dict, List, Optional

from databricks_tools_core.repos import (
    create_repo as _create_repo,
    delete_repo as _delete_repo,
    get_repo as _get_repo,
    list_repos as _list_repos,
    update_repo as _update_repo,
)

from ..manifest import register_deleter
from ..server import mcp


def _delete_repo_resource(resource_id: str) -> None:
    _delete_repo(repo_id=int(resource_id))


register_deleter("repo", _delete_repo_resource)


# ============================================================================
# Helpers
# ============================================================================


def _find_repo_by_url(url: str) -> Optional[Dict[str, Any]]:
    """Find an existing repo by its remote URL, returns None if not found."""
    try:
        result = _list_repos()
        for repo in result.get("repos", []):
            if repo.get("url") == url:
                return repo
        return None
    except Exception:
        return None


@mcp.tool(timeout=30)
def list_repos(path_prefix: Optional[str] = None) -> Dict[str, Any]:
    """
    List Git repos in the workspace.

    Returns all cloned repos, optionally filtered by workspace path prefix.

    Args:
        path_prefix: Filter repos whose workspace path starts with this prefix
            (e.g. "/Repos/user@example.com"). Omit to list all.

    Returns:
        Dictionary with:
        - repos: List of repo dicts with id, path, url, provider, branch, head_commit_id
        - count: Number of repos returned

    Example:
        >>> list_repos("/Repos/user@example.com")
        {"repos": [{"id": 123, "path": "...", "url": "...", "branch": "main"}], "count": 1}
    """
    return _list_repos(path_prefix=path_prefix)


@mcp.tool(timeout=30)
def get_repo(repo_id: int) -> Dict[str, Any]:
    """
    Get details for a specific Git repo by ID.

    Returns the repo's workspace path, remote URL, current branch, and head commit.

    Args:
        repo_id: Numeric ID of the repo

    Returns:
        Dictionary with:
        - id: Repo ID
        - path: Workspace path
        - url: Remote Git URL
        - provider: Git provider name
        - branch: Current branch
        - head_commit_id: Current commit SHA

    Example:
        >>> get_repo(12345)
        {"id": 12345, "path": "/Repos/user/my-repo", "branch": "main", ...}
    """
    return _get_repo(repo_id=repo_id)


@mcp.tool(timeout=120)
def create_or_update_repo(
    url: str,
    provider: str,
    path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Idempotent clone of a Git repository. Returns existing if already cloned.

    If a repo with the same URL already exists in the workspace, returns it
    with ``created: false``. Otherwise clones the repo and returns it with
    ``created: true``.

    Requires Git credentials to be configured for private repos.
    Supported providers: gitHub, gitLab, bitbucketCloud, azureDevOpsServices,
    gitHubEnterprise, bitbucketServer, gitLabEnterpriseEdition, awsCodeCommit.

    Args:
        url: Remote Git URL (e.g. "https://github.com/org/repo")
        provider: Git provider name (e.g. "gitHub", "gitLab")
        path: Optional workspace path (defaults to /Repos/<user>/<repo-name>)

    Returns:
        Dictionary with:
        - id: Repo ID
        - path: Workspace path
        - url: Remote URL
        - provider: Git provider
        - branch: Checked-out branch
        - head_commit_id: Current commit SHA
        - created: True if newly cloned, False if already existed

    Example:
        >>> create_or_update_repo("https://github.com/org/repo", "gitHub")
        {"id": 123, "path": "/Repos/user/repo", "branch": "main", "created": true, ...}
    """
    existing = _find_repo_by_url(url)
    if existing:
        return {**existing, "created": False}

    result = _create_repo(url=url, provider=provider, path=path)

    if "error" not in result:
        try:
            from ..manifest import track_resource

            track_resource(
                resource_type="repo",
                name=result.get("path", ""),
                resource_id=str(result["id"]),
                url=result.get("url"),
            )
        except Exception:
            pass
        return {**result, "created": True}

    return result


@mcp.tool(timeout=60)
def update_repo(
    repo_id: int,
    branch: Optional[str] = None,
    tag: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Switch a repo to a different branch or tag.

    Pulls the latest from the remote and checks out the specified ref.
    Exactly one of branch or tag must be provided.

    Args:
        repo_id: Numeric ID of the repo
        branch: Branch to check out (e.g. "main", "feature/xyz")
        tag: Tag to check out (e.g. "v1.0.0")

    Returns:
        Dictionary with:
        - id: Repo ID
        - path: Workspace path
        - branch: New checked-out branch
        - head_commit_id: New commit SHA

    Example:
        >>> update_repo(12345, branch="develop")
        {"id": 12345, "branch": "develop", "head_commit_id": "abc123", ...}
    """
    return _update_repo(repo_id=repo_id, branch=branch, tag=tag)


@mcp.tool(timeout=30)
def delete_repo(repo_id: int) -> Dict[str, Any]:
    """
    Delete a Git repo from the workspace.

    This removes the repo and all its contents from the workspace.
    The remote Git repository is not affected.

    Args:
        repo_id: Numeric ID of the repo to delete

    Returns:
        Dictionary with:
        - repo_id: The deleted repo ID
        - status: "deleted" or "not_found"

    Example:
        >>> delete_repo(12345)
        {"repo_id": 12345, "status": "deleted"}
    """
    result = _delete_repo(repo_id=repo_id)

    if result.get("status") == "deleted":
        try:
            from ..manifest import remove_resource

            remove_resource(resource_type="repo", resource_id=str(repo_id))
        except Exception:
            pass

    return result

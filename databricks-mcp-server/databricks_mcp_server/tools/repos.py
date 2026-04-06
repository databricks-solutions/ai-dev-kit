"""Git repos tools - Manage Databricks Git repositories in the workspace.

Consolidated into 1 tool:
- manage_repos: list, get, create, update, sync, delete
"""

from typing import Any, Dict, Optional

from databricks_tools_core.repos import (
    create_repo as _create_repo,
    delete_repo as _delete_repo,
    get_repo as _get_repo,
    list_repos as _list_repos,
    update_repo as _update_repo,
)

from ..manifest import register_deleter, track_resource, remove_resource
from ..server import mcp

_VALID_ACTIONS = ("list", "get", "create", "update", "sync", "delete")


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


# ============================================================================
# Consolidated tool
# ============================================================================


def _manage_repos_impl(
    action: str,
    repo_id: Optional[int] = None,
    url: Optional[str] = None,
    provider: Optional[str] = None,
    path: Optional[str] = None,
    branch: Optional[str] = None,
    tag: Optional[str] = None,
    path_prefix: Optional[str] = None,
) -> Dict[str, Any]:
    """Implementation for manage_repos dispatching to core library functions."""
    act = action.lower()

    if act == "list":
        return _list_repos(path_prefix=path_prefix)

    elif act == "get":
        if not repo_id:
            return {"error": "get requires: repo_id"}
        return _get_repo(repo_id=repo_id)

    elif act == "create":
        if not url or not provider:
            return {"error": "create requires: url, provider"}
        # Idempotent: return existing if same URL already cloned
        existing = _find_repo_by_url(url)
        if existing:
            return {**existing, "created": False}

        result = _create_repo(url=url, provider=provider, path=path)

        if "error" not in result:
            try:
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

    elif act == "update":
        if not repo_id:
            return {"error": "update requires: repo_id and branch or tag"}
        return _update_repo(repo_id=repo_id, branch=branch, tag=tag)

    elif act == "sync":
        # Sync is an alias for update — pulls latest and checks out the ref
        if not repo_id:
            return {"error": "sync requires: repo_id and branch or tag"}
        return _update_repo(repo_id=repo_id, branch=branch, tag=tag)

    elif act == "delete":
        if not repo_id:
            return {"error": "delete requires: repo_id"}
        result = _delete_repo(repo_id=repo_id)
        if result.get("status") == "deleted":
            try:
                remove_resource(resource_type="repo", resource_id=str(repo_id))
            except Exception:
                pass
        return result

    else:
        return {"error": f"Invalid action '{action}'. Valid: {', '.join(_VALID_ACTIONS)}"}


@mcp.tool(timeout=60)
def manage_repos(
    action: str,
    repo_id: Optional[int] = None,
    url: Optional[str] = None,
    provider: Optional[str] = None,
    path: Optional[str] = None,
    branch: Optional[str] = None,
    tag: Optional[str] = None,
    path_prefix: Optional[str] = None,
) -> Dict[str, Any]:
    """Manage Databricks Git repos (Repos API).

    Actions: list, get, create, update, sync, delete.

    - list: All cloned repos. Optional: path_prefix to filter.
    - get: Repo details. Requires: repo_id.
    - create: Idempotent clone (returns existing if same URL). Requires: url, provider. Optional: path.
    - update: Switch branch or tag. Requires: repo_id, branch or tag.
    - sync: Alias for update — pull latest and checkout ref. Requires: repo_id, branch or tag.
    - delete: Remove repo from workspace. Requires: repo_id.

    See databricks-repos skill for providers, credential setup, and patterns."""
    return _manage_repos_impl(
        action=action,
        repo_id=repo_id,
        url=url,
        provider=provider,
        path=path,
        branch=branch,
        tag=tag,
        path_prefix=path_prefix,
    )

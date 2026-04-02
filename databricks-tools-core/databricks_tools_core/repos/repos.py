"""
Git Repos Operations

Functions for managing Databricks Git repositories (Repos) in the workspace.
Supports cloning, listing, syncing branches/tags, and deleting repos.
"""

import logging
from typing import Any, Dict, List, Optional

from databricks.sdk.errors import NotFound, ResourceAlreadyExists, ResourceDoesNotExist

from ..auth import get_workspace_client

logger = logging.getLogger(__name__)

# Supported git providers (SDK accepts these strings)
VALID_PROVIDERS = {
    "gitHub",
    "bitbucketCloud",
    "gitLab",
    "azureDevOpsServices",
    "gitHubEnterprise",
    "bitbucketServer",
    "gitLabEnterpriseEdition",
    "awsCodeCommit",
}


def _serialize_repo(repo) -> Dict[str, Any]:
    """Convert a RepoInfo/CreateRepoResponse/GetRepoResponse to a serializable dict."""
    return {
        "id": repo.id,
        "path": repo.path,
        "url": repo.url,
        "provider": repo.provider,
        "branch": repo.branch,
        "head_commit_id": repo.head_commit_id,
    }


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------


def list_repos(path_prefix: Optional[str] = None) -> Dict[str, Any]:
    """List Git repos in the workspace.

    Args:
        path_prefix: Optional path prefix to filter repos
            (e.g. "/Repos/user@example.com").

    Returns:
        Dictionary with:
        - repos: List of repo dicts with id, path, url, provider, branch, head_commit_id
        - count: Number of repos returned
    """
    client = get_workspace_client()
    items = list(client.repos.list(path_prefix=path_prefix))
    repos = [_serialize_repo(r) for r in items]
    return {"repos": repos, "count": len(repos)}


def get_repo(repo_id: int) -> Dict[str, Any]:
    """Get details for a specific Git repo.

    Args:
        repo_id: Numeric ID of the repo.

    Returns:
        Dictionary with repo details: id, path, url, provider, branch, head_commit_id.
    """
    client = get_workspace_client()

    try:
        repo = client.repos.get(repo_id=repo_id)
    except (ResourceDoesNotExist, NotFound):
        return {"error": f"Repo not found: {repo_id}", "repo_id": repo_id}

    return _serialize_repo(repo)


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------


def create_repo(
    url: str,
    provider: str,
    path: Optional[str] = None,
) -> Dict[str, Any]:
    """Clone a Git repository into the workspace.

    Args:
        url: URL of the remote Git repository (e.g. "https://github.com/org/repo").
        provider: Git provider — gitHub, gitLab, bitbucketCloud, azureDevOpsServices,
            gitHubEnterprise, bitbucketServer, gitLabEnterpriseEdition, or awsCodeCommit.
        path: Optional workspace path where the repo should be created
            (e.g. "/Repos/user@example.com/my-repo"). If omitted, defaults to
            /Repos/<current-user>/<repo-name>.

    Returns:
        Dictionary with:
        - id: The new repo ID
        - path: Workspace path of the repo
        - url: Remote URL
        - provider: Git provider
        - branch: Checked-out branch
        - head_commit_id: Current commit SHA
    """
    if provider not in VALID_PROVIDERS:
        return {"error": f"Invalid provider '{provider}'. Valid: {sorted(VALID_PROVIDERS)}", "url": url}

    client = get_workspace_client()

    try:
        repo = client.repos.create(url=url, provider=provider, path=path)
    except ResourceAlreadyExists:
        return {"error": "Repo already exists at path. Use a different path or delete the existing repo.", "url": url}

    return _serialize_repo(repo)


def update_repo(
    repo_id: int,
    branch: Optional[str] = None,
    tag: Optional[str] = None,
) -> Dict[str, Any]:
    """Update a repo by switching to a different branch or tag.

    This pulls the latest from the remote and checks out the specified
    branch or tag. Exactly one of branch or tag must be provided.

    Args:
        repo_id: Numeric ID of the repo.
        branch: Branch name to check out (e.g. "main", "feature/xyz").
        tag: Tag name to check out (e.g. "v1.0.0").

    Returns:
        Dictionary with updated repo details: id, path, url, provider, branch, head_commit_id.
    """
    if not branch and not tag:
        return {"error": "Exactly one of 'branch' or 'tag' must be provided.", "repo_id": repo_id}
    if branch and tag:
        return {"error": "Cannot specify both 'branch' and 'tag'. Choose one.", "repo_id": repo_id}

    client = get_workspace_client()

    try:
        client.repos.update(repo_id=repo_id, branch=branch, tag=tag)
    except (ResourceDoesNotExist, NotFound):
        return {"error": f"Repo not found: {repo_id}", "repo_id": repo_id}

    # Fetch updated state since update returns void
    repo = client.repos.get(repo_id=repo_id)
    return _serialize_repo(repo)


def delete_repo(repo_id: int) -> Dict[str, Any]:
    """Delete a Git repo from the workspace.

    Args:
        repo_id: Numeric ID of the repo to delete.

    Returns:
        Dictionary with:
        - repo_id: The deleted repo ID
        - status: "deleted" or error details
    """
    client = get_workspace_client()

    try:
        client.repos.delete(repo_id=repo_id)
    except (ResourceDoesNotExist, NotFound):
        return {"error": f"Repo not found: {repo_id}", "repo_id": repo_id, "status": "not_found"}

    return {"repo_id": repo_id, "status": "deleted"}

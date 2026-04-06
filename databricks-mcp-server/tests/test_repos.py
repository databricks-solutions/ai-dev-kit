"""Tests for the manage_repos MCP tool."""

from unittest.mock import MagicMock, patch

import pytest

from databricks_mcp_server.tools.repos import _manage_repos_impl as manage_repos

# Patch targets (core library functions called by the MCP impl)
_LIST_REPOS = "databricks_mcp_server.tools.repos._list_repos"
_GET_REPO = "databricks_mcp_server.tools.repos._get_repo"
_CREATE_REPO = "databricks_mcp_server.tools.repos._create_repo"
_UPDATE_REPO = "databricks_mcp_server.tools.repos._update_repo"
_DELETE_REPO = "databricks_mcp_server.tools.repos._delete_repo"
_FIND_REPO_BY_URL = "databricks_mcp_server.tools.repos._find_repo_by_url"
_TRACK_RESOURCE = "databricks_mcp_server.tools.repos.track_resource"
_REMOVE_RESOURCE = "databricks_mcp_server.tools.repos.remove_resource"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _repo_dict(**overrides):
    """Build a typical repo dict."""
    base = {
        "id": 12345,
        "path": "/Repos/user@example.com/my-repo",
        "url": "https://github.com/org/my-repo",
        "provider": "gitHub",
        "branch": "main",
        "head_commit_id": "abc123def456",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


class TestListAction:
    def test_list_all(self):
        repos = [_repo_dict(id=1), _repo_dict(id=2)]
        with patch(_LIST_REPOS, return_value={"repos": repos, "count": 2}) as mock_list:
            result = manage_repos(action="list")

        assert result["count"] == 2
        assert len(result["repos"]) == 2
        mock_list.assert_called_once_with(path_prefix=None)

    def test_list_with_path_prefix(self):
        with patch(_LIST_REPOS, return_value={"repos": [], "count": 0}) as mock_list:
            result = manage_repos(action="list", path_prefix="/Repos/user@example.com")

        mock_list.assert_called_once_with(path_prefix="/Repos/user@example.com")
        assert result["count"] == 0

    def test_list_empty(self):
        with patch(_LIST_REPOS, return_value={"repos": [], "count": 0}):
            result = manage_repos(action="list")

        assert result["repos"] == []
        assert result["count"] == 0


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


class TestGetAction:
    def test_get_success(self):
        repo = _repo_dict()
        with patch(_GET_REPO, return_value=repo):
            result = manage_repos(action="get", repo_id=12345)

        assert result["id"] == 12345
        assert result["branch"] == "main"

    def test_get_missing_repo_id(self):
        result = manage_repos(action="get")
        assert "error" in result
        assert "repo_id" in result["error"]

    def test_get_not_found(self):
        with patch(_GET_REPO, return_value={"error": "Repo not found: 99999", "repo_id": 99999}):
            result = manage_repos(action="get", repo_id=99999)

        assert "error" in result


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


class TestCreateAction:
    def test_create_new_repo(self):
        repo = _repo_dict(id=100)
        with (
            patch(_FIND_REPO_BY_URL, return_value=None),
            patch(_CREATE_REPO, return_value=repo) as mock_create,
            patch(_TRACK_RESOURCE) as mock_track,
        ):
            result = manage_repos(action="create", url="https://github.com/org/repo", provider="gitHub")

        assert result["created"] is True
        assert result["id"] == 100
        mock_create.assert_called_once_with(url="https://github.com/org/repo", provider="gitHub", path=None)
        mock_track.assert_called_once()

    def test_create_idempotent_existing(self):
        existing = _repo_dict(id=50)
        with patch(_FIND_REPO_BY_URL, return_value=existing):
            result = manage_repos(action="create", url="https://github.com/org/repo", provider="gitHub")

        assert result["created"] is False
        assert result["id"] == 50

    def test_create_with_custom_path(self):
        repo = _repo_dict(path="/Repos/user/custom-path")
        with (
            patch(_FIND_REPO_BY_URL, return_value=None),
            patch(_CREATE_REPO, return_value=repo),
            patch(_TRACK_RESOURCE),
        ):
            result = manage_repos(
                action="create",
                url="https://github.com/org/repo",
                provider="gitHub",
                path="/Repos/user/custom-path",
            )

        assert result["path"] == "/Repos/user/custom-path"

    def test_create_missing_url(self):
        result = manage_repos(action="create", provider="gitHub")
        assert "error" in result
        assert "url" in result["error"]

    def test_create_missing_provider(self):
        result = manage_repos(action="create", url="https://github.com/org/repo")
        assert "error" in result
        assert "provider" in result["error"]

    def test_create_core_error_passthrough(self):
        with (
            patch(_FIND_REPO_BY_URL, return_value=None),
            patch(_CREATE_REPO, return_value={"error": "Invalid provider 'bad'", "url": "https://x.com/a"}),
        ):
            result = manage_repos(action="create", url="https://x.com/a", provider="bad")

        assert "error" in result

    def test_create_track_resource_failure_ignored(self):
        """Manifest tracking failure should not break create."""
        repo = _repo_dict()
        with (
            patch(_FIND_REPO_BY_URL, return_value=None),
            patch(_CREATE_REPO, return_value=repo),
            patch(_TRACK_RESOURCE, side_effect=Exception("manifest error")),
        ):
            result = manage_repos(action="create", url="https://github.com/org/repo", provider="gitHub")

        assert result["created"] is True


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


class TestUpdateAction:
    def test_update_branch(self):
        repo = _repo_dict(branch="develop", head_commit_id="new123")
        with patch(_UPDATE_REPO, return_value=repo):
            result = manage_repos(action="update", repo_id=12345, branch="develop")

        assert result["branch"] == "develop"

    def test_update_tag(self):
        repo = _repo_dict(branch=None, head_commit_id="tag123")
        with patch(_UPDATE_REPO, return_value=repo):
            result = manage_repos(action="update", repo_id=12345, tag="v1.0.0")

        assert result["branch"] is None

    def test_update_missing_repo_id(self):
        result = manage_repos(action="update", branch="main")
        assert "error" in result
        assert "repo_id" in result["error"]


# ---------------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------------


class TestSyncAction:
    def test_sync_delegates_to_update(self):
        repo = _repo_dict(branch="main", head_commit_id="latest")
        with patch(_UPDATE_REPO, return_value=repo) as mock_update:
            result = manage_repos(action="sync", repo_id=12345, branch="main")

        mock_update.assert_called_once_with(repo_id=12345, branch="main", tag=None)
        assert result["head_commit_id"] == "latest"

    def test_sync_missing_repo_id(self):
        result = manage_repos(action="sync", branch="main")
        assert "error" in result
        assert "repo_id" in result["error"]


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


class TestDeleteAction:
    def test_delete_success(self):
        with (
            patch(_DELETE_REPO, return_value={"repo_id": 12345, "status": "deleted"}),
            patch(_REMOVE_RESOURCE) as mock_remove,
        ):
            result = manage_repos(action="delete", repo_id=12345)

        assert result["status"] == "deleted"
        mock_remove.assert_called_once_with(resource_type="repo", resource_id="12345")

    def test_delete_not_found(self):
        not_found = {"error": "Repo not found: 99999", "repo_id": 99999, "status": "not_found"}
        with patch(_DELETE_REPO, return_value=not_found):
            result = manage_repos(action="delete", repo_id=99999)

        assert result["status"] == "not_found"

    def test_delete_missing_repo_id(self):
        result = manage_repos(action="delete")
        assert "error" in result
        assert "repo_id" in result["error"]

    def test_delete_remove_resource_failure_ignored(self):
        """Manifest removal failure should not break delete."""
        with (
            patch(_DELETE_REPO, return_value={"repo_id": 12345, "status": "deleted"}),
            patch(_REMOVE_RESOURCE, side_effect=Exception("manifest error")),
        ):
            result = manage_repos(action="delete", repo_id=12345)

        assert result["status"] == "deleted"


# ---------------------------------------------------------------------------
# invalid action
# ---------------------------------------------------------------------------


class TestInvalidAction:
    def test_invalid_action_returns_error(self):
        result = manage_repos(action="badaction")
        assert "error" in result
        assert "Invalid action" in result["error"]
        for valid in ("list", "get", "create", "update", "sync", "delete"):
            assert valid in result["error"]

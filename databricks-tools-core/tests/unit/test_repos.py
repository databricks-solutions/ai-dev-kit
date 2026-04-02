"""Unit tests for Git repos operations."""

from unittest import mock

import pytest
from databricks.sdk.errors import NotFound, ResourceAlreadyExists, ResourceDoesNotExist

from databricks_tools_core.repos import (
    create_repo,
    delete_repo,
    get_repo,
    list_repos,
    update_repo,
)

_GET_CLIENT = "databricks_tools_core.repos.repos.get_workspace_client"


def _make_repo_info(**kwargs):
    """Helper to build a mock repo object."""
    repo = mock.Mock()
    defaults = {
        "id": 12345,
        "path": "/Repos/user@example.com/my-repo",
        "url": "https://github.com/org/my-repo",
        "provider": "gitHub",
        "branch": "main",
        "head_commit_id": "abc123def456",
    }
    defaults.update(kwargs)
    for key, val in defaults.items():
        setattr(repo, key, val)
    return repo


class TestListRepos:
    """Tests for list_repos."""

    @mock.patch(_GET_CLIENT)
    def test_list_success(self, mock_get_client):
        mock_client = mock.Mock()
        mock_client.repos.list.return_value = [
            _make_repo_info(id=1, path="/Repos/user/repo1"),
            _make_repo_info(id=2, path="/Repos/user/repo2", branch="develop"),
        ]
        mock_get_client.return_value = mock_client

        result = list_repos()

        assert result["count"] == 2
        assert result["repos"][0]["id"] == 1
        assert result["repos"][1]["branch"] == "develop"
        mock_client.repos.list.assert_called_once_with(path_prefix=None)

    @mock.patch(_GET_CLIENT)
    def test_list_with_path_prefix(self, mock_get_client):
        mock_client = mock.Mock()
        mock_client.repos.list.return_value = [_make_repo_info()]
        mock_get_client.return_value = mock_client

        list_repos(path_prefix="/Repos/user@example.com")

        mock_client.repos.list.assert_called_once_with(path_prefix="/Repos/user@example.com")

    @mock.patch(_GET_CLIENT)
    def test_list_empty(self, mock_get_client):
        mock_client = mock.Mock()
        mock_client.repos.list.return_value = []
        mock_get_client.return_value = mock_client

        result = list_repos()

        assert result["count"] == 0
        assert result["repos"] == []


class TestGetRepo:
    """Tests for get_repo."""

    @mock.patch(_GET_CLIENT)
    def test_get_success(self, mock_get_client):
        mock_client = mock.Mock()
        mock_client.repos.get.return_value = _make_repo_info()
        mock_get_client.return_value = mock_client

        result = get_repo(repo_id=12345)

        assert result["id"] == 12345
        assert result["url"] == "https://github.com/org/my-repo"
        assert result["branch"] == "main"
        assert result["head_commit_id"] == "abc123def456"

    @mock.patch(_GET_CLIENT)
    def test_get_not_found(self, mock_get_client):
        mock_client = mock.Mock()
        mock_client.repos.get.side_effect = ResourceDoesNotExist("Repo not found")
        mock_get_client.return_value = mock_client

        result = get_repo(repo_id=99999)

        assert "error" in result
        assert result["repo_id"] == 99999

    @mock.patch(_GET_CLIENT)
    def test_get_not_found_404(self, mock_get_client):
        mock_client = mock.Mock()
        mock_client.repos.get.side_effect = NotFound("Not found")
        mock_get_client.return_value = mock_client

        result = get_repo(repo_id=99999)

        assert "error" in result


class TestCreateRepo:
    """Tests for create_repo."""

    @mock.patch(_GET_CLIENT)
    def test_create_success(self, mock_get_client):
        mock_client = mock.Mock()
        mock_client.repos.create.return_value = _make_repo_info(id=100)
        mock_get_client.return_value = mock_client

        result = create_repo(url="https://github.com/org/repo", provider="gitHub")

        assert result["id"] == 100
        assert result["provider"] == "gitHub"
        mock_client.repos.create.assert_called_once_with(url="https://github.com/org/repo", provider="gitHub", path=None)

    @mock.patch(_GET_CLIENT)
    def test_create_with_path(self, mock_get_client):
        mock_client = mock.Mock()
        mock_client.repos.create.return_value = _make_repo_info(path="/Repos/user/custom-path")
        mock_get_client.return_value = mock_client

        result = create_repo(
            url="https://github.com/org/repo",
            provider="gitHub",
            path="/Repos/user/custom-path",
        )

        assert result["path"] == "/Repos/user/custom-path"
        mock_client.repos.create.assert_called_once_with(
            url="https://github.com/org/repo", provider="gitHub", path="/Repos/user/custom-path"
        )

    def test_create_invalid_provider(self):
        result = create_repo(url="https://github.com/org/repo", provider="invalidProvider")

        assert "error" in result
        assert "Invalid provider" in result["error"]

    @mock.patch(_GET_CLIENT)
    def test_create_already_exists(self, mock_get_client):
        mock_client = mock.Mock()
        mock_client.repos.create.side_effect = ResourceAlreadyExists("Already exists")
        mock_get_client.return_value = mock_client

        result = create_repo(url="https://github.com/org/repo", provider="gitHub")

        assert "error" in result
        assert "already exists" in result["error"]

    @mock.patch(_GET_CLIENT)
    def test_create_gitlab(self, mock_get_client):
        mock_client = mock.Mock()
        mock_client.repos.create.return_value = _make_repo_info(provider="gitLab")
        mock_get_client.return_value = mock_client

        result = create_repo(url="https://gitlab.com/org/repo", provider="gitLab")

        assert result["provider"] == "gitLab"


class TestUpdateRepo:
    """Tests for update_repo."""

    @mock.patch(_GET_CLIENT)
    def test_update_branch(self, mock_get_client):
        mock_client = mock.Mock()
        mock_client.repos.get.return_value = _make_repo_info(branch="develop", head_commit_id="new123")
        mock_get_client.return_value = mock_client

        result = update_repo(repo_id=12345, branch="develop")

        assert result["branch"] == "develop"
        assert result["head_commit_id"] == "new123"
        mock_client.repos.update.assert_called_once_with(repo_id=12345, branch="develop", tag=None)

    @mock.patch(_GET_CLIENT)
    def test_update_tag(self, mock_get_client):
        mock_client = mock.Mock()
        mock_client.repos.get.return_value = _make_repo_info(branch=None, head_commit_id="tag123")
        mock_get_client.return_value = mock_client

        result = update_repo(repo_id=12345, tag="v1.0.0")

        mock_client.repos.update.assert_called_once_with(repo_id=12345, branch=None, tag="v1.0.0")

    def test_update_no_branch_or_tag(self):
        result = update_repo(repo_id=12345)

        assert "error" in result
        assert "Exactly one" in result["error"]

    def test_update_both_branch_and_tag(self):
        result = update_repo(repo_id=12345, branch="main", tag="v1.0")

        assert "error" in result
        assert "Cannot specify both" in result["error"]

    @mock.patch(_GET_CLIENT)
    def test_update_not_found(self, mock_get_client):
        mock_client = mock.Mock()
        mock_client.repos.update.side_effect = ResourceDoesNotExist("Not found")
        mock_get_client.return_value = mock_client

        result = update_repo(repo_id=99999, branch="main")

        assert "error" in result
        assert result["repo_id"] == 99999


class TestDeleteRepo:
    """Tests for delete_repo."""

    @mock.patch(_GET_CLIENT)
    def test_delete_success(self, mock_get_client):
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        result = delete_repo(repo_id=12345)

        assert result["status"] == "deleted"
        assert result["repo_id"] == 12345
        mock_client.repos.delete.assert_called_once_with(repo_id=12345)

    @mock.patch(_GET_CLIENT)
    def test_delete_not_found(self, mock_get_client):
        mock_client = mock.Mock()
        mock_client.repos.delete.side_effect = ResourceDoesNotExist("Not found")
        mock_get_client.return_value = mock_client

        result = delete_repo(repo_id=99999)

        assert "error" in result
        assert result["status"] == "not_found"

    @mock.patch(_GET_CLIENT)
    def test_delete_not_found_404(self, mock_get_client):
        mock_client = mock.Mock()
        mock_client.repos.delete.side_effect = NotFound("Not found")
        mock_get_client.return_value = mock_client

        result = delete_repo(repo_id=99999)

        assert "error" in result
        assert result["status"] == "not_found"

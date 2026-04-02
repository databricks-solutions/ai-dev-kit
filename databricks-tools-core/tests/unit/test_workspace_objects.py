"""Unit tests for workspace object operations."""

import base64
from unittest import mock

import pytest
from databricks.sdk.errors import NotFound, ResourceDoesNotExist
from databricks.sdk.service.workspace import ExportFormat, Language, ObjectInfo, ObjectType

from databricks_tools_core.file import (
    create_notebook,
    create_workspace_directory,
    get_workspace_object_status,
    list_workspace_directory,
    read_notebook,
)

_GET_CLIENT = "databricks_tools_core.file.workspace_objects.get_workspace_client"


def _make_object_info(**kwargs) -> ObjectInfo:
    """Helper to build ObjectInfo with sensible defaults."""
    defaults = {
        "path": "/Users/test@example.com/notebook1",
        "object_type": ObjectType.NOTEBOOK,
        "language": Language.PYTHON,
        "object_id": 12345,
        "size": 1024,
        "created_at": 1700000000000,
        "modified_at": 1700001000000,
    }
    defaults.update(kwargs)
    return ObjectInfo(**defaults)


class TestListWorkspaceDirectory:
    """Tests for list_workspace_directory."""

    @mock.patch(_GET_CLIENT)
    def test_list_success(self, mock_get_client):
        mock_client = mock.Mock()
        mock_client.workspace.list.return_value = [
            _make_object_info(path="/Users/test/nb1", object_type=ObjectType.NOTEBOOK),
            _make_object_info(path="/Users/test/dir1", object_type=ObjectType.DIRECTORY, language=None),
        ]
        mock_get_client.return_value = mock_client

        result = list_workspace_directory("/Users/test")

        assert result["path"] == "/Users/test"
        assert result["count"] == 2
        assert result["objects"][0]["path"] == "/Users/test/nb1"
        assert result["objects"][0]["object_type"] == "NOTEBOOK"
        assert result["objects"][1]["object_type"] == "DIRECTORY"
        assert result["objects"][1]["language"] is None

    @mock.patch(_GET_CLIENT)
    def test_list_empty_directory(self, mock_get_client):
        mock_client = mock.Mock()
        mock_client.workspace.list.return_value = []
        mock_get_client.return_value = mock_client

        result = list_workspace_directory("/Users/test/empty")

        assert result["count"] == 0
        assert result["objects"] == []

    @mock.patch(_GET_CLIENT)
    def test_list_not_found(self, mock_get_client):
        mock_client = mock.Mock()
        mock_client.workspace.list.side_effect = ResourceDoesNotExist("Path not found")
        mock_get_client.return_value = mock_client

        result = list_workspace_directory("/Users/nonexistent")

        assert "error" in result
        assert result["path"] == "/Users/nonexistent"

    @mock.patch(_GET_CLIENT)
    def test_list_not_found_404(self, mock_get_client):
        mock_client = mock.Mock()
        mock_client.workspace.list.side_effect = NotFound("Not found")
        mock_get_client.return_value = mock_client

        result = list_workspace_directory("/Users/nonexistent")

        assert "error" in result

    @mock.patch(_GET_CLIENT)
    def test_list_multiple_types(self, mock_get_client):
        mock_client = mock.Mock()
        mock_client.workspace.list.return_value = [
            _make_object_info(path="/ws/nb", object_type=ObjectType.NOTEBOOK, language=Language.SQL),
            _make_object_info(path="/ws/file", object_type=ObjectType.FILE, language=None, size=2048),
            _make_object_info(path="/ws/lib", object_type=ObjectType.LIBRARY, language=None),
            _make_object_info(path="/ws/repo", object_type=ObjectType.REPO, language=None),
        ]
        mock_get_client.return_value = mock_client

        result = list_workspace_directory("/ws")

        assert result["count"] == 4
        assert result["objects"][0]["language"] == "SQL"
        assert result["objects"][1]["object_type"] == "FILE"
        assert result["objects"][1]["size"] == 2048
        assert result["objects"][3]["object_type"] == "REPO"


class TestGetWorkspaceObjectStatus:
    """Tests for get_workspace_object_status."""

    @mock.patch(_GET_CLIENT)
    def test_status_notebook(self, mock_get_client):
        mock_client = mock.Mock()
        mock_client.workspace.get_status.return_value = _make_object_info()
        mock_get_client.return_value = mock_client

        result = get_workspace_object_status("/Users/test@example.com/notebook1")

        assert result["object_type"] == "NOTEBOOK"
        assert result["language"] == "PYTHON"
        assert result["object_id"] == 12345
        assert result["size"] == 1024

    @mock.patch(_GET_CLIENT)
    def test_status_directory(self, mock_get_client):
        mock_client = mock.Mock()
        mock_client.workspace.get_status.return_value = _make_object_info(
            path="/Users/test/mydir",
            object_type=ObjectType.DIRECTORY,
            language=None,
            size=None,
        )
        mock_get_client.return_value = mock_client

        result = get_workspace_object_status("/Users/test/mydir")

        assert result["object_type"] == "DIRECTORY"
        assert result["language"] is None

    @mock.patch(_GET_CLIENT)
    def test_status_not_found(self, mock_get_client):
        mock_client = mock.Mock()
        mock_client.workspace.get_status.side_effect = ResourceDoesNotExist("Not found")
        mock_get_client.return_value = mock_client

        result = get_workspace_object_status("/Users/test/missing")

        assert "error" in result
        assert result["path"] == "/Users/test/missing"


class TestReadNotebook:
    """Tests for read_notebook."""

    @mock.patch(_GET_CLIENT)
    def test_read_source_format(self, mock_get_client):
        mock_client = mock.Mock()
        source_code = "print('hello world')"
        encoded = base64.b64encode(source_code.encode("utf-8")).decode("utf-8")
        mock_response = mock.Mock()
        mock_response.content = encoded
        mock_client.workspace.export.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = read_notebook("/Users/test/nb")

        assert result["content"] == source_code
        assert result["format"] == "SOURCE"
        assert result["is_base64"] is False

    @mock.patch(_GET_CLIENT)
    def test_read_jupyter_format(self, mock_get_client):
        mock_client = mock.Mock()
        jupyter_b64 = base64.b64encode(b'{"cells": []}').decode("utf-8")
        mock_response = mock.Mock()
        mock_response.content = jupyter_b64
        mock_client.workspace.export.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = read_notebook("/Users/test/nb", format="JUPYTER")

        assert result["content"] == jupyter_b64
        assert result["format"] == "JUPYTER"
        assert result["is_base64"] is True

    @mock.patch(_GET_CLIENT)
    def test_read_raw_format_decoded(self, mock_get_client):
        mock_client = mock.Mock()
        raw_text = "# Raw file content"
        encoded = base64.b64encode(raw_text.encode("utf-8")).decode("utf-8")
        mock_response = mock.Mock()
        mock_response.content = encoded
        mock_client.workspace.export.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = read_notebook("/Users/test/file.py", format="RAW")

        assert result["content"] == raw_text
        assert result["is_base64"] is False

    @mock.patch(_GET_CLIENT)
    def test_read_html_format_base64(self, mock_get_client):
        mock_client = mock.Mock()
        html_b64 = base64.b64encode(b"<html></html>").decode("utf-8")
        mock_response = mock.Mock()
        mock_response.content = html_b64
        mock_client.workspace.export.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = read_notebook("/Users/test/nb", format="HTML")

        assert result["is_base64"] is True
        assert result["format"] == "HTML"

    def test_read_invalid_format(self):
        result = read_notebook("/Users/test/nb", format="INVALID")

        assert "error" in result
        assert "Invalid format" in result["error"]

    @mock.patch(_GET_CLIENT)
    def test_read_not_found(self, mock_get_client):
        mock_client = mock.Mock()
        mock_client.workspace.export.side_effect = ResourceDoesNotExist("Not found")
        mock_get_client.return_value = mock_client

        result = read_notebook("/Users/test/missing")

        assert "error" in result
        assert result["path"] == "/Users/test/missing"

    @mock.patch(_GET_CLIENT)
    def test_read_case_insensitive_format(self, mock_get_client):
        mock_client = mock.Mock()
        encoded = base64.b64encode(b"content").decode("utf-8")
        mock_response = mock.Mock()
        mock_response.content = encoded
        mock_client.workspace.export.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = read_notebook("/Users/test/nb", format="source")

        assert result["format"] == "SOURCE"
        assert result["is_base64"] is False


class TestCreateNotebook:
    """Tests for create_notebook."""

    @mock.patch(_GET_CLIENT)
    def test_create_default_params(self, mock_get_client):
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        result = create_notebook("/Users/test/new_nb", "print('hello')")

        assert result["success"] is True
        assert result["path"] == "/Users/test/new_nb"
        assert result["language"] == "PYTHON"
        assert result["format"] == "SOURCE"
        assert result["overwrite"] is False
        mock_client.workspace.import_.assert_called_once()

    @mock.patch(_GET_CLIENT)
    def test_create_with_overwrite(self, mock_get_client):
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        result = create_notebook("/Users/test/nb", "SELECT 1", language="SQL", overwrite=True)

        assert result["success"] is True
        assert result["language"] == "SQL"
        assert result["overwrite"] is True
        call_kwargs = mock_client.workspace.import_.call_args[1]
        assert call_kwargs["overwrite"] is True

    @mock.patch(_GET_CLIENT)
    def test_create_base64_encodes_content(self, mock_get_client):
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client
        source = "print('test')"

        create_notebook("/Users/test/nb", source)

        call_kwargs = mock_client.workspace.import_.call_args[1]
        decoded = base64.b64decode(call_kwargs["content"]).decode("utf-8")
        assert decoded == source

    def test_create_invalid_language(self):
        result = create_notebook("/Users/test/nb", "content", language="JAVA")

        assert "error" in result
        assert "Invalid language" in result["error"]

    def test_create_invalid_format(self):
        result = create_notebook("/Users/test/nb", "content", format="DOCX")

        assert "error" in result
        assert "Invalid format" in result["error"]

    @mock.patch(_GET_CLIENT)
    def test_create_scala_notebook(self, mock_get_client):
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        result = create_notebook("/Users/test/nb", "println(42)", language="SCALA")

        assert result["language"] == "SCALA"
        assert result["success"] is True

    @mock.patch(_GET_CLIENT)
    def test_create_case_insensitive_language(self, mock_get_client):
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        result = create_notebook("/Users/test/nb", "1+1", language="r")

        assert result["language"] == "R"
        assert result["success"] is True


class TestCreateWorkspaceDirectory:
    """Tests for create_workspace_directory."""

    @mock.patch(_GET_CLIENT)
    def test_create_directory_success(self, mock_get_client):
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        result = create_workspace_directory("/Users/test/new_dir")

        assert result["success"] is True
        assert result["path"] == "/Users/test/new_dir"
        mock_client.workspace.mkdirs.assert_called_once_with(path="/Users/test/new_dir")

    @mock.patch(_GET_CLIENT)
    def test_create_directory_nested(self, mock_get_client):
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        result = create_workspace_directory("/Users/test/a/b/c")

        assert result["success"] is True
        mock_client.workspace.mkdirs.assert_called_once_with(path="/Users/test/a/b/c")

    @mock.patch(_GET_CLIENT)
    def test_create_directory_api_error(self, mock_get_client):
        mock_client = mock.Mock()
        mock_client.workspace.mkdirs.side_effect = Exception("Permission denied")
        mock_get_client.return_value = mock_client

        with pytest.raises(Exception, match="Permission denied"):
            create_workspace_directory("/Shared/restricted")

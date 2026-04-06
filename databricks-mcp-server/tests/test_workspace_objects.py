"""Tests for the manage_workspace_objects consolidated MCP tool."""

from unittest.mock import MagicMock, patch

from databricks_mcp_server.tools.workspace_objects import _manage_workspace_objects_impl as manage_workspace_objects

# Patch targets — core library functions imported into the tool module
_LIST = "databricks_mcp_server.tools.workspace_objects._list_workspace_directory"
_GET_STATUS = "databricks_mcp_server.tools.workspace_objects._get_workspace_object_status"
_READ = "databricks_mcp_server.tools.workspace_objects._read_notebook"
_CREATE_NB = "databricks_mcp_server.tools.workspace_objects._create_notebook"
_CREATE_DIR = "databricks_mcp_server.tools.workspace_objects._create_workspace_directory"
_TRACK = "databricks_mcp_server.manifest.track_resource"


# ---------------------------------------------------------------------------
# invalid action
# ---------------------------------------------------------------------------


def test_invalid_action():
    """An unrecognised action returns an error listing valid actions."""
    result = manage_workspace_objects(action="destroy", path="/Users/test")
    assert "error" in result
    for valid in ("list", "get_status", "read", "create_notebook", "create_directory"):
        assert valid in result["error"]


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list_delegates_to_core():
    """action='list' calls _list_workspace_directory with the path."""
    expected = {"path": "/Users/test", "objects": [{"path": "/Users/test/nb1"}], "count": 1}
    with patch(_LIST, return_value=expected) as mock_list:
        result = manage_workspace_objects(action="list", path="/Users/test")

    mock_list.assert_called_once_with(path="/Users/test")
    assert result == expected


def test_list_returns_error_on_not_found():
    """action='list' propagates not-found error from core."""
    error_result = {"error": "Path not found: /bad", "path": "/bad"}
    with patch(_LIST, return_value=error_result):
        result = manage_workspace_objects(action="list", path="/bad")

    assert "error" in result


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------


def test_get_status_delegates_to_core():
    """action='get_status' calls _get_workspace_object_status with the path."""
    expected = {"path": "/Users/test/nb", "object_type": "NOTEBOOK", "language": "PYTHON"}
    with patch(_GET_STATUS, return_value=expected) as mock_status:
        result = manage_workspace_objects(action="get_status", path="/Users/test/nb")

    mock_status.assert_called_once_with(path="/Users/test/nb")
    assert result["object_type"] == "NOTEBOOK"


def test_get_status_not_found():
    """action='get_status' propagates not-found from core."""
    with patch(_GET_STATUS, return_value={"error": "Path not found", "path": "/missing"}):
        result = manage_workspace_objects(action="get_status", path="/missing")

    assert "error" in result


# ---------------------------------------------------------------------------
# read
# ---------------------------------------------------------------------------


def test_read_defaults_to_source():
    """action='read' defaults format to SOURCE when not specified."""
    expected = {"path": "/nb", "content": "print(1)", "format": "SOURCE", "is_base64": False}
    with patch(_READ, return_value=expected) as mock_read:
        result = manage_workspace_objects(action="read", path="/nb")

    mock_read.assert_called_once_with(path="/nb", format="SOURCE")
    assert result["content"] == "print(1)"


def test_read_with_explicit_format():
    """action='read' passes the explicit format to core."""
    expected = {"path": "/nb", "content": "abc", "format": "JUPYTER", "is_base64": True}
    with patch(_READ, return_value=expected) as mock_read:
        result = manage_workspace_objects(action="read", path="/nb", format="JUPYTER")

    mock_read.assert_called_once_with(path="/nb", format="JUPYTER")
    assert result["format"] == "JUPYTER"


def test_read_not_found():
    """action='read' propagates not-found from core."""
    with patch(_READ, return_value={"error": "Path not found", "path": "/missing"}):
        result = manage_workspace_objects(action="read", path="/missing")

    assert "error" in result


# ---------------------------------------------------------------------------
# create_notebook
# ---------------------------------------------------------------------------


def test_create_notebook_defaults():
    """action='create_notebook' uses default language/format when not specified."""
    expected = {"path": "/Users/test/nb", "language": "PYTHON", "format": "SOURCE", "overwrite": False, "success": True}
    with patch(_CREATE_NB, return_value=expected) as mock_create:
        result = manage_workspace_objects(action="create_notebook", path="/Users/test/nb", content="print(1)")

    mock_create.assert_called_once_with(
        path="/Users/test/nb", content="print(1)", language="PYTHON", format="SOURCE", overwrite=False
    )
    assert result["success"] is True


def test_create_notebook_with_options():
    """action='create_notebook' passes all explicit parameters to core."""
    expected = {"path": "/nb", "language": "SQL", "format": "SOURCE", "overwrite": True, "success": True}
    with patch(_CREATE_NB, return_value=expected) as mock_create:
        result = manage_workspace_objects(
            action="create_notebook", path="/nb", content="SELECT 1", language="SQL", overwrite=True
        )

    mock_create.assert_called_once_with(path="/nb", content="SELECT 1", language="SQL", format="SOURCE", overwrite=True)
    assert result["language"] == "SQL"


def test_create_notebook_missing_content():
    """action='create_notebook' returns error when content is not provided."""
    result = manage_workspace_objects(action="create_notebook", path="/nb")
    assert "error" in result
    assert "content" in result["error"]


def test_create_notebook_tracks_resource():
    """action='create_notebook' calls track_resource on success."""
    expected = {"path": "/Users/test/nb", "language": "PYTHON", "format": "SOURCE", "overwrite": False, "success": True}
    with patch(_CREATE_NB, return_value=expected), patch(_TRACK) as mock_track:
        manage_workspace_objects(action="create_notebook", path="/Users/test/nb", content="x=1")

    mock_track.assert_called_once_with(
        resource_type="workspace_object",
        name="nb",
        resource_id="/Users/test/nb",
    )


def test_create_notebook_tracking_failure_does_not_raise():
    """track_resource failure is swallowed (best-effort)."""
    expected = {"path": "/nb", "success": True, "language": "PYTHON", "format": "SOURCE", "overwrite": False}
    with patch(_CREATE_NB, return_value=expected), patch(_TRACK, side_effect=Exception("tracking error")):
        result = manage_workspace_objects(action="create_notebook", path="/nb", content="x=1")

    assert result["success"] is True


def test_create_notebook_no_tracking_on_failure():
    """track_resource is not called when create fails."""
    expected = {"error": "Invalid language 'JAVA'", "path": "/nb"}
    with patch(_CREATE_NB, return_value=expected), patch(_TRACK) as mock_track:
        manage_workspace_objects(action="create_notebook", path="/nb", content="x=1")

    mock_track.assert_not_called()


# ---------------------------------------------------------------------------
# create_directory
# ---------------------------------------------------------------------------


def test_create_directory_delegates_to_core():
    """action='create_directory' calls _create_workspace_directory with the path."""
    expected = {"path": "/Users/test/dir", "success": True}
    with patch(_CREATE_DIR, return_value=expected) as mock_mkdir:
        result = manage_workspace_objects(action="create_directory", path="/Users/test/dir")

    mock_mkdir.assert_called_once_with(path="/Users/test/dir")
    assert result["success"] is True

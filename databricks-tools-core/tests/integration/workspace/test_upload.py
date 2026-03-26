"""Integration tests for workspace upload functions.

These tests actually upload files to Databricks workspace and verify they exist.
Requires a valid Databricks connection.
"""

import logging
import os
import tempfile
import uuid
from pathlib import Path

import pytest
from databricks.sdk import WorkspaceClient

from databricks_tools_core.file.workspace import upload_to_workspace

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def workspace_path(workspace_client: WorkspaceClient) -> str:
    """Create a unique workspace path for testing and clean up after."""
    # Get current user's home folder
    user = workspace_client.current_user.me()
    test_id = str(uuid.uuid4())[:8]
    path = f"/Workspace/Users/{user.user_name}/test_upload_{test_id}"

    logger.info(f"Using test workspace path: {path}")

    yield path

    # Cleanup: delete the test folder
    try:
        workspace_client.workspace.delete(path, recursive=True)
        logger.info(f"Cleaned up test folder: {path}")
    except Exception as e:
        logger.warning(f"Failed to clean up test folder {path}: {e}")


@pytest.mark.integration
class TestUploadToWorkspaceIntegration:
    """Integration tests for upload_to_workspace."""

    def test_upload_single_file(self, workspace_client: WorkspaceClient, workspace_path: str):
        """Test uploading a single file to workspace."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("# Test file\nprint('hello world')\n")
            local_path = f.name

        try:
            remote_path = f"{workspace_path}/single_file.py"

            result = upload_to_workspace(
                local_path=local_path,
                workspace_path=remote_path,
            )

            assert result.success, f"Upload failed: {result.results}"
            assert result.total_files == 1
            assert result.successful == 1
            assert result.failed == 0

            # Verify file exists in workspace
            status = workspace_client.workspace.get_status(remote_path)
            assert status is not None
            logger.info(f"Successfully uploaded single file to {remote_path}")

        finally:
            os.unlink(local_path)

    def test_upload_folder(self, workspace_client: WorkspaceClient, workspace_path: str):
        """Test uploading a folder with multiple files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            (Path(tmpdir) / "file1.py").write_text("# File 1\nprint(1)")
            (Path(tmpdir) / "file2.py").write_text("# File 2\nprint(2)")
            (Path(tmpdir) / "subdir").mkdir()
            (Path(tmpdir) / "subdir" / "nested.py").write_text("# Nested\nprint('nested')")

            remote_path = f"{workspace_path}/folder_test"

            result = upload_to_workspace(
                local_path=tmpdir,
                workspace_path=remote_path,
            )

            assert result.success, f"Upload failed: {result.results}"
            assert result.total_files == 3
            assert result.successful == 3

            # Verify files exist
            status1 = workspace_client.workspace.get_status(f"{remote_path}/file1.py")
            assert status1 is not None

            status2 = workspace_client.workspace.get_status(f"{remote_path}/subdir/nested.py")
            assert status2 is not None

            logger.info(f"Successfully uploaded folder with {result.total_files} files")

    def test_upload_glob_pattern(self, workspace_client: WorkspaceClient, workspace_path: str):
        """Test uploading files matching a glob pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            (Path(tmpdir) / "script1.py").write_text("# Script 1")
            (Path(tmpdir) / "script2.py").write_text("# Script 2")
            (Path(tmpdir) / "data.json").write_text('{"key": "value"}')
            (Path(tmpdir) / "readme.md").write_text("# README")

            remote_path = f"{workspace_path}/glob_test"

            # Upload only .py files
            result = upload_to_workspace(
                local_path=f"{tmpdir}/*.py",
                workspace_path=remote_path,
            )

            assert result.success, f"Upload failed: {result.results}"
            assert result.total_files == 2  # Only .py files
            assert result.successful == 2

            # Verify .py files exist
            status = workspace_client.workspace.get_status(f"{remote_path}/script1.py")
            assert status is not None

            # Verify .json was NOT uploaded
            with pytest.raises(Exception):
                workspace_client.workspace.get_status(f"{remote_path}/data.json")

            logger.info("Successfully uploaded files matching glob pattern")

    def test_upload_star_glob(self, workspace_client: WorkspaceClient, workspace_path: str):
        """Test uploading all contents with /* pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test structure
            (Path(tmpdir) / "main.py").write_text("# Main")
            (Path(tmpdir) / "utils").mkdir()
            (Path(tmpdir) / "utils" / "helper.py").write_text("# Helper")

            remote_path = f"{workspace_path}/star_test"

            # Upload all contents
            result = upload_to_workspace(
                local_path=f"{tmpdir}/*",
                workspace_path=remote_path,
            )

            assert result.success, f"Upload failed: {result.results}"
            assert result.total_files == 2  # main.py + utils/helper.py

            # Verify nested file exists
            status = workspace_client.workspace.get_status(f"{remote_path}/utils/helper.py")
            assert status is not None

            logger.info("Successfully uploaded with /* glob pattern")

    def test_upload_overwrites_existing(self, workspace_client: WorkspaceClient, workspace_path: str):
        """Test that overwrite=True replaces existing files."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("# Version 1\n")
            local_path = f.name

        try:
            remote_path = f"{workspace_path}/overwrite_test.py"

            # First upload
            result1 = upload_to_workspace(local_path=local_path, workspace_path=remote_path)
            assert result1.success

            # Modify file
            with open(local_path, "w") as f:
                f.write("# Version 2\n")

            # Second upload with overwrite
            result2 = upload_to_workspace(
                local_path=local_path,
                workspace_path=remote_path,
                overwrite=True,
            )
            assert result2.success

            logger.info("Successfully tested overwrite functionality")

        finally:
            os.unlink(local_path)

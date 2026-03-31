"""
Integration tests for volume files MCP tool.

Tests:
- manage_volume_files: upload, download, list, delete
"""

import logging
import tempfile
from pathlib import Path

import pytest

from databricks_mcp_server.tools.volume_files import manage_volume_files
from tests.test_config import TEST_CATALOG, SCHEMAS, TEST_RESOURCE_PREFIX

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def test_volume(
    workspace_client,
    test_catalog: str,
    volume_files_schema: str,
) -> str:
    """Create a test volume for file operations."""
    from databricks.sdk.service.catalog import VolumeType

    volume_name = f"{TEST_RESOURCE_PREFIX}volume"
    full_volume_name = f"{test_catalog}.{volume_files_schema}.{volume_name}"

    # Delete if exists
    try:
        workspace_client.volumes.delete(full_volume_name)
    except Exception:
        pass

    # Create volume
    workspace_client.volumes.create(
        catalog_name=test_catalog,
        schema_name=volume_files_schema,
        name=volume_name,
        volume_type=VolumeType.MANAGED,
    )

    logger.info(f"Created test volume: {full_volume_name}")

    yield full_volume_name

    # Cleanup
    try:
        workspace_client.volumes.delete(full_volume_name)
        logger.info(f"Cleaned up volume: {full_volume_name}")
    except Exception as e:
        logger.warning(f"Failed to cleanup volume: {e}")


@pytest.fixture
def test_local_file():
    """Create a temporary local file for upload tests."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("Hello from MCP integration test!\n")
        f.write("Line 2 of test file.\n")
        temp_path = f.name

    yield temp_path

    # Cleanup
    try:
        Path(temp_path).unlink()
    except Exception:
        pass


@pytest.fixture
def test_local_dir():
    """Create a temporary local directory with files for upload tests."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create some test files
        (Path(temp_dir) / "file1.txt").write_text("File 1 content")
        (Path(temp_dir) / "file2.txt").write_text("File 2 content")
        (Path(temp_dir) / "subdir").mkdir()
        (Path(temp_dir) / "subdir" / "file3.txt").write_text("File 3 in subdir")

        yield temp_dir


@pytest.mark.integration
class TestManageVolumeFiles:
    """Tests for manage_volume_files tool."""

    def test_upload_single_file(
        self,
        test_volume: str,
        test_local_file: str,
        test_catalog: str,
        volume_files_schema: str,
    ):
        """Should upload a single file to volume and verify it exists."""
        file_name = Path(test_local_file).name
        # For single file upload, volume_path must include the destination filename
        volume_path = f"/Volumes/{test_catalog}/{volume_files_schema}/{TEST_RESOURCE_PREFIX}volume/{file_name}"

        result = manage_volume_files(
            action="upload",
            volume_path=volume_path,
            local_path=test_local_file,
            overwrite=True,
        )

        logger.info(f"Upload result: {result}")

        assert not result.get("error"), f"Upload failed: {result}"
        assert result.get("success", False) or result.get("status") == "success"

        # Verify file exists by listing the parent directory
        volume_dir = f"/Volumes/{test_catalog}/{volume_files_schema}/{TEST_RESOURCE_PREFIX}volume"
        list_result = manage_volume_files(action="list", volume_path=volume_dir)
        assert not list_result.get("error"), f"List failed: {list_result}"

        # Check file appears in listing
        files = list_result.get("files", []) or list_result.get("contents", [])
        file_names = [f.get("name") or f.get("path", "").split("/")[-1] for f in files]
        assert file_name in file_names, f"Uploaded file {file_name} not found in {file_names}"

    def test_upload_directory(
        self,
        test_volume: str,
        test_local_dir: str,
        test_catalog: str,
        volume_files_schema: str,
    ):
        """Should upload a directory to volume."""
        volume_path = f"/Volumes/{test_catalog}/{volume_files_schema}/{TEST_RESOURCE_PREFIX}volume/test_dir"

        result = manage_volume_files(
            action="upload",
            local_path=test_local_dir,
            volume_path=volume_path,
            overwrite=True,
        )

        logger.info(f"Upload directory result: {result}")

        assert "error" not in result, f"Upload failed: {result}"

    def test_list_files(
        self,
        test_volume: str,
        test_catalog: str,
        volume_files_schema: str,
    ):
        """Should list files in volume."""
        volume_path = f"/Volumes/{test_catalog}/{volume_files_schema}/{TEST_RESOURCE_PREFIX}volume"

        result = manage_volume_files(
            action="list",
            volume_path=volume_path,
        )

        logger.info(f"List result: {result}")

        assert "error" not in result, f"List failed: {result}"

    def test_download_file(
        self,
        test_volume: str,
        test_local_file: str,
        test_catalog: str,
        volume_files_schema: str,
    ):
        """Should download a file from volume and verify content matches."""
        volume_dir = f"/Volumes/{test_catalog}/{volume_files_schema}/{TEST_RESOURCE_PREFIX}volume"
        file_name = Path(test_local_file).name
        # For single file upload, volume_path must include the destination filename
        volume_file_path = f"{volume_dir}/{file_name}"

        # Read original content
        original_content = Path(test_local_file).read_text()

        # First upload a file
        manage_volume_files(
            action="upload",
            volume_path=volume_file_path,
            local_path=test_local_file,
            overwrite=True,
        )

        # Download to temp location
        with tempfile.TemporaryDirectory() as temp_dir:
            # local_destination must be the full file path, not just directory
            local_file_path = str(Path(temp_dir) / file_name)
            result = manage_volume_files(
                action="download",
                volume_path=volume_file_path,
                local_destination=local_file_path,
            )

            logger.info(f"Download result: {result}")

            assert not result.get("error"), f"Download failed: {result}"

            # Verify downloaded content matches original
            downloaded_file = Path(local_file_path)
            assert downloaded_file.exists(), f"Downloaded file not found at {downloaded_file}"

            downloaded_content = downloaded_file.read_text()
            assert downloaded_content == original_content, \
                f"Content mismatch: expected {original_content!r}, got {downloaded_content!r}"

    def test_delete_file(
        self,
        test_volume: str,
        test_local_file: str,
        test_catalog: str,
        volume_files_schema: str,
    ):
        """Should delete a file from volume and verify it's gone."""
        volume_dir = f"/Volumes/{test_catalog}/{volume_files_schema}/{TEST_RESOURCE_PREFIX}volume"
        # Use a unique file name for this test to avoid conflicts
        delete_test_file = Path(test_local_file).parent / f"delete_test_{Path(test_local_file).name}"
        delete_test_file.write_text("File to be deleted")
        file_name = delete_test_file.name
        # For single file upload, volume_path must include the destination filename
        volume_file_path = f"{volume_dir}/{file_name}"

        try:
            # First upload a file
            manage_volume_files(
                action="upload",
                volume_path=volume_file_path,
                local_path=str(delete_test_file),
                overwrite=True,
            )

            # Verify file exists before delete
            list_before = manage_volume_files(action="list", volume_path=volume_dir)
            files_before = list_before.get("files", []) or list_before.get("contents", [])
            file_names_before = [f.get("name") or f.get("path", "").split("/")[-1] for f in files_before]
            assert file_name in file_names_before, f"File {file_name} should exist before delete"

            # Delete it
            result = manage_volume_files(
                action="delete",
                volume_path=volume_file_path,
            )

            logger.info(f"Delete result: {result}")

            assert not result.get("error"), f"Delete failed: {result}"

            # Verify file is gone
            list_after = manage_volume_files(action="list", volume_path=volume_dir)
            files_after = list_after.get("files", []) or list_after.get("contents", [])
            file_names_after = [f.get("name") or f.get("path", "").split("/")[-1] for f in files_after]
            assert file_name not in file_names_after, f"File {file_name} should be deleted but still exists"
        finally:
            # Cleanup local temp file
            delete_test_file.unlink(missing_ok=True)

    def test_invalid_action(self):
        """Should return error for invalid action."""
        result = manage_volume_files(action="invalid_action", volume_path="/Volumes/dummy/path")

        assert "error" in result

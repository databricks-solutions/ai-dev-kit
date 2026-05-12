"""Integration tests for volume upload functions.

These tests actually upload files to a Databricks Unity Catalog volume and verify they exist.
Requires a valid Databricks connection and an existing volume at /Volumes/main/demo/raw_data.
"""

import logging
import os
import tempfile
import uuid
from pathlib import Path

import pytest
from databricks.sdk import WorkspaceClient

from databricks_tools_core.unity_catalog import upload_to_volume, list_volume_files

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def volume_path(workspace_client: WorkspaceClient) -> str:
    """Create a unique folder path in an existing volume for testing and clean up after."""
    test_id = str(uuid.uuid4())[:8]
    # Use an existing volume - main.demo.raw_data is commonly available
    path = f"/Volumes/main/demo/raw_data/test_upload_{test_id}"

    logger.info(f"Using test volume path: {path}")

    yield path

    # Cleanup: recursively delete test folder contents
    def delete_recursive(folder_path: str):
        try:
            items = list_volume_files(folder_path)
            # Delete files first
            for item in items:
                if not item.is_directory:
                    try:
                        workspace_client.files.delete(item.path)
                    except Exception:
                        pass
            # Then delete subdirectories
            for item in items:
                if item.is_directory:
                    delete_recursive(item.path)
                    try:
                        workspace_client.files.delete_directory(item.path)
                    except Exception:
                        pass
        except Exception:
            pass

    try:
        delete_recursive(path)
        workspace_client.files.delete_directory(path)
        logger.info(f"Cleaned up test folder: {path}")
    except Exception as e:
        logger.warning(f"Failed to clean up test folder {path}: {e}")


@pytest.mark.integration
class TestUploadToVolumeIntegration:
    """Integration tests for upload_to_volume."""

    def test_upload_single_file(self, workspace_client: WorkspaceClient, volume_path: str):
        """Test uploading a single file to volume."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("col1,col2\n1,2\n3,4\n")
            local_path = f.name

        try:
            remote_path = f"{volume_path}/single_file.csv"

            result = upload_to_volume(
                local_path=local_path,
                volume_path=remote_path,
            )

            assert result.success, f"Upload failed: {result.results}"
            assert result.total_files == 1
            assert result.successful == 1
            assert result.failed == 0

            # Verify file exists in volume
            metadata = workspace_client.files.get_metadata(remote_path)
            assert metadata is not None
            logger.info(f"Successfully uploaded single file to {remote_path}")

        finally:
            os.unlink(local_path)

    def test_upload_folder(self, workspace_client: WorkspaceClient, volume_path: str):
        """Test uploading a folder with multiple files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            (Path(tmpdir) / "file1.csv").write_text("col1,col2\n1,2")
            (Path(tmpdir) / "file2.json").write_text('{"key": "value"}')
            (Path(tmpdir) / "subdir").mkdir()
            (Path(tmpdir) / "subdir" / "nested.txt").write_text("nested content")

            remote_path = f"{volume_path}/folder_test"

            result = upload_to_volume(
                local_path=tmpdir,
                volume_path=remote_path,
            )

            assert result.success, f"Upload failed: {result.results}"
            assert result.total_files == 3
            assert result.successful == 3

            # Verify files exist
            metadata1 = workspace_client.files.get_metadata(f"{remote_path}/file1.csv")
            assert metadata1 is not None

            metadata2 = workspace_client.files.get_metadata(f"{remote_path}/subdir/nested.txt")
            assert metadata2 is not None

            logger.info(f"Successfully uploaded folder with {result.total_files} files")

    def test_upload_glob_pattern(self, workspace_client: WorkspaceClient, volume_path: str):
        """Test uploading files matching a glob pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            (Path(tmpdir) / "data1.csv").write_text("col1\n1")
            (Path(tmpdir) / "data2.csv").write_text("col1\n2")
            (Path(tmpdir) / "config.json").write_text('{"setting": true}')
            (Path(tmpdir) / "readme.md").write_text("# README")

            remote_path = f"{volume_path}/glob_test"

            # Upload only .csv files
            result = upload_to_volume(
                local_path=f"{tmpdir}/*.csv",
                volume_path=remote_path,
            )

            assert result.success, f"Upload failed: {result.results}"
            assert result.total_files == 2  # Only .csv files
            assert result.successful == 2

            # Verify .csv files exist
            metadata = workspace_client.files.get_metadata(f"{remote_path}/data1.csv")
            assert metadata is not None

            # Verify .json was NOT uploaded
            with pytest.raises(Exception):
                workspace_client.files.get_metadata(f"{remote_path}/config.json")

            logger.info("Successfully uploaded files matching glob pattern")

    def test_upload_star_glob(self, workspace_client: WorkspaceClient, volume_path: str):
        """Test uploading all contents with /* pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test structure
            (Path(tmpdir) / "main.csv").write_text("col1\nmain")
            (Path(tmpdir) / "utils").mkdir()
            (Path(tmpdir) / "utils" / "helper.txt").write_text("helper content")

            remote_path = f"{volume_path}/star_test"

            # Upload all contents
            result = upload_to_volume(
                local_path=f"{tmpdir}/*",
                volume_path=remote_path,
            )

            assert result.success, f"Upload failed: {result.results}"
            assert result.total_files == 2  # main.csv + utils/helper.txt

            # Verify nested file exists
            metadata = workspace_client.files.get_metadata(f"{remote_path}/utils/helper.txt")
            assert metadata is not None

            logger.info("Successfully uploaded with /* glob pattern")

    def test_upload_overwrites_existing(self, workspace_client: WorkspaceClient, volume_path: str):
        """Test that overwrite=True replaces existing files."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("version,1\n")
            local_path = f.name

        try:
            remote_path = f"{volume_path}/overwrite_test.csv"

            # First upload
            result1 = upload_to_volume(local_path=local_path, volume_path=remote_path)
            assert result1.success

            # Modify file
            with open(local_path, "w") as f:
                f.write("version,2\n")

            # Second upload with overwrite
            result2 = upload_to_volume(
                local_path=local_path,
                volume_path=remote_path,
                overwrite=True,
            )
            assert result2.success

            logger.info("Successfully tested overwrite functionality")

        finally:
            os.unlink(local_path)

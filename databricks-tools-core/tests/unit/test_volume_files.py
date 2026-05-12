"""Unit tests for volume file upload functions."""

import os
from pathlib import Path
from unittest import mock

import pytest

from databricks_tools_core.unity_catalog.volume_files import (
    upload_to_volume,
    delete_from_volume,
    _collect_local_files,
    _collect_local_directories,
    VolumeUploadResult,
    VolumeFolderUploadResult,
    VolumeDeleteResult,
)


class TestCollectLocalFiles:
    """Tests for _collect_local_files helper function."""

    def test_collects_files_recursively(self, tmp_path):
        """Should collect all files in nested directories."""
        (tmp_path / "file1.csv").write_text("content1")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "file2.csv").write_text("content2")
        (tmp_path / "subdir" / "nested").mkdir()
        (tmp_path / "subdir" / "nested" / "file3.csv").write_text("content3")

        files = _collect_local_files(str(tmp_path))

        assert len(files) == 3
        rel_paths = {f[1] for f in files}
        assert "file1.csv" in rel_paths
        assert os.path.join("subdir", "file2.csv") in rel_paths
        assert os.path.join("subdir", "nested", "file3.csv") in rel_paths

    def test_skips_hidden_files(self, tmp_path):
        """Should skip files starting with dot."""
        (tmp_path / "visible.csv").write_text("content")
        (tmp_path / ".hidden").write_text("hidden")

        files = _collect_local_files(str(tmp_path))

        assert len(files) == 1
        assert files[0][1] == "visible.csv"

    def test_skips_pycache(self, tmp_path):
        """Should skip __pycache__ directories."""
        (tmp_path / "file.csv").write_text("content")
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "cached.pyc").write_text("cached")

        files = _collect_local_files(str(tmp_path))

        assert len(files) == 1
        assert files[0][1] == "file.csv"


class TestCollectLocalDirectories:
    """Tests for _collect_local_directories helper function."""

    def test_collects_directories_recursively(self, tmp_path):
        """Should collect all directories."""
        (tmp_path / "dir1").mkdir()
        (tmp_path / "dir1" / "subdir").mkdir()
        (tmp_path / "dir2").mkdir()

        dirs = _collect_local_directories(str(tmp_path))

        assert "dir1" in dirs
        assert "dir2" in dirs
        assert os.path.join("dir1", "subdir") in dirs

    def test_skips_hidden_directories(self, tmp_path):
        """Should skip directories starting with dot."""
        (tmp_path / "visible").mkdir()
        (tmp_path / ".hidden").mkdir()

        dirs = _collect_local_directories(str(tmp_path))

        assert "visible" in dirs
        assert ".hidden" not in dirs


class TestUploadToVolume:
    """Tests for upload_to_volume function."""

    @mock.patch("databricks_tools_core.unity_catalog.volume_files.get_workspace_client")
    def test_single_file_upload(self, mock_get_client, tmp_path):
        """Should upload a single file correctly."""
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        test_file = tmp_path / "test.csv"
        test_file.write_text("col1,col2\n1,2")

        result = upload_to_volume(
            local_path=str(test_file),
            volume_path="/Volumes/catalog/schema/volume/test.csv",
        )

        assert result.success
        assert result.total_files == 1
        assert result.successful == 1
        assert result.failed == 0
        mock_client.files.upload_from.assert_called_once()

    @mock.patch("databricks_tools_core.unity_catalog.volume_files.get_workspace_client")
    def test_folder_upload(self, mock_get_client, tmp_path):
        """Should upload a folder with all files."""
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        (tmp_path / "file1.csv").write_text("content1")
        (tmp_path / "file2.json").write_text("{}")

        result = upload_to_volume(
            local_path=str(tmp_path),
            volume_path="/Volumes/catalog/schema/volume/data",
        )

        assert result.success
        assert result.total_files == 2
        assert result.successful == 2
        assert result.failed == 0
        assert mock_client.files.upload_from.call_count == 2
        mock_client.files.create_directory.assert_called()

    @mock.patch("databricks_tools_core.unity_catalog.volume_files.get_workspace_client")
    def test_glob_pattern_files(self, mock_get_client, tmp_path):
        """Should upload files matching glob pattern."""
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        (tmp_path / "file1.csv").write_text("content1")
        (tmp_path / "file2.csv").write_text("content2")
        (tmp_path / "data.json").write_text("{}")

        result = upload_to_volume(
            local_path=str(tmp_path / "*.csv"),
            volume_path="/Volumes/catalog/schema/volume/data",
        )

        assert result.success
        assert result.total_files == 2  # Only .csv files
        assert result.successful == 2

    @mock.patch("databricks_tools_core.unity_catalog.volume_files.get_workspace_client")
    def test_glob_pattern_star(self, mock_get_client, tmp_path):
        """Should upload all contents with /* pattern."""
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        (tmp_path / "file.csv").write_text("content")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "nested.json").write_text("{}")

        result = upload_to_volume(
            local_path=str(tmp_path / "*"),
            volume_path="/Volumes/catalog/schema/volume/data",
        )

        assert result.success
        # file.csv + subdir/nested.json
        assert result.total_files == 2

    @mock.patch("databricks_tools_core.unity_catalog.volume_files.get_workspace_client")
    def test_nonexistent_path_returns_error(self, mock_get_client):
        """Should return error result for nonexistent path."""
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        result = upload_to_volume(
            local_path="/nonexistent/path/file.csv",
            volume_path="/Volumes/catalog/schema/volume/file.csv",
        )

        assert not result.success
        assert result.failed == 1
        assert "not found" in result.results[0].error.lower()

    @mock.patch("databricks_tools_core.unity_catalog.volume_files.get_workspace_client")
    def test_empty_glob_returns_error(self, mock_get_client, tmp_path):
        """Should return error when glob matches nothing."""
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        result = upload_to_volume(
            local_path=str(tmp_path / "*.nonexistent"),
            volume_path="/Volumes/catalog/schema/volume/data",
        )

        assert not result.success
        assert "no files match" in result.results[0].error.lower()

    @mock.patch("databricks_tools_core.unity_catalog.volume_files.get_workspace_client")
    def test_creates_parent_directories(self, mock_get_client, tmp_path):
        """Should create parent directories for single file upload."""
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        test_file = tmp_path / "test.csv"
        test_file.write_text("content")

        upload_to_volume(
            local_path=str(test_file),
            volume_path="/Volumes/catalog/schema/volume/deep/nested/test.csv",
        )

        # Should call create_directory for parent
        mock_client.files.create_directory.assert_called()

    @mock.patch("databricks_tools_core.unity_catalog.volume_files.get_workspace_client")
    def test_handles_upload_failure(self, mock_get_client, tmp_path):
        """Should handle upload failures gracefully."""
        mock_client = mock.Mock()
        mock_client.files.upload_from.side_effect = Exception("Upload failed")
        mock_get_client.return_value = mock_client

        test_file = tmp_path / "test.csv"
        test_file.write_text("content")

        result = upload_to_volume(
            local_path=str(test_file),
            volume_path="/Volumes/catalog/schema/volume/test.csv",
        )

        assert not result.success
        assert result.failed == 1
        assert "Upload failed" in result.results[0].error

    @mock.patch("databricks_tools_core.unity_catalog.volume_files.get_workspace_client")
    def test_expands_tilde_in_path(self, mock_get_client, tmp_path):
        """Should expand ~ in local path."""
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        # Create a file in a known location we can reference with ~
        home = Path.home()
        test_dir = home / ".test_upload_volume"
        test_dir.mkdir(exist_ok=True)
        test_file = test_dir / "test.csv"
        test_file.write_text("content")

        try:
            result = upload_to_volume(
                local_path="~/.test_upload_volume/test.csv",
                volume_path="/Volumes/catalog/schema/volume/test.csv",
            )

            assert result.total_files == 1
            mock_client.files.upload_from.assert_called_once()
        finally:
            test_file.unlink()
            test_dir.rmdir()

    @mock.patch("databricks_tools_core.unity_catalog.volume_files.get_workspace_client")
    def test_max_workers_parameter(self, mock_get_client, tmp_path):
        """Should respect max_workers parameter."""
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        # Create multiple files
        for i in range(10):
            (tmp_path / f"file{i}.csv").write_text(f"content{i}")

        result = upload_to_volume(
            local_path=str(tmp_path),
            volume_path="/Volumes/catalog/schema/volume/data",
            max_workers=2,
        )

        assert result.success
        assert result.total_files == 10
        assert mock_client.files.upload_from.call_count == 10


class TestDeleteFromVolume:
    """Tests for delete_from_volume function."""

    @mock.patch("databricks_tools_core.unity_catalog.volume_files.get_workspace_client")
    def test_delete_file_succeeds(self, mock_get_client):
        """Should delete a file successfully."""
        mock_client = mock.Mock()
        # get_metadata succeeds means it's a file
        mock_client.files.get_metadata.return_value = mock.Mock(content_length=100)
        mock_get_client.return_value = mock_client

        result = delete_from_volume("/Volumes/catalog/schema/volume/file.csv")

        assert result.success
        assert result.files_deleted == 1
        assert result.directories_deleted == 0
        mock_client.files.delete.assert_called_once_with("/Volumes/catalog/schema/volume/file.csv")

    @mock.patch("databricks_tools_core.unity_catalog.volume_files.get_workspace_client")
    def test_delete_empty_directory_without_recursive(self, mock_get_client):
        """Should delete an empty directory without recursive flag."""
        mock_client = mock.Mock()
        # get_metadata fails for directories
        mock_client.files.get_metadata.side_effect = Exception("Not a file")
        # list_directory_contents returns empty
        mock_client.files.list_directory_contents.return_value = iter([])
        mock_get_client.return_value = mock_client

        result = delete_from_volume("/Volumes/catalog/schema/volume/empty_dir")

        assert result.success
        assert result.directories_deleted == 1
        mock_client.files.delete_directory.assert_called_once()

    @mock.patch("databricks_tools_core.unity_catalog.volume_files.get_workspace_client")
    def test_delete_nonempty_directory_without_recursive_fails(self, mock_get_client):
        """Should fail when deleting non-empty directory without recursive."""
        mock_client = mock.Mock()
        mock_client.files.get_metadata.side_effect = Exception("Not a file")
        # list succeeds with content
        mock_client.files.list_directory_contents.return_value = iter([
            mock.Mock(name="file.csv", path="/Volumes/.../file.csv", is_directory=False)
        ])
        # delete_directory fails because not empty
        mock_client.files.delete_directory.side_effect = Exception("Directory not empty")
        mock_get_client.return_value = mock_client

        result = delete_from_volume("/Volumes/catalog/schema/volume/nonempty_dir")

        assert not result.success
        assert "recursive=True" in result.error

    @mock.patch("databricks_tools_core.unity_catalog.volume_files.get_workspace_client")
    def test_delete_directory_recursive(self, mock_get_client):
        """Should delete directory and contents with recursive=True."""
        mock_client = mock.Mock()
        mock_client.files.get_metadata.side_effect = Exception("Not a file")

        # Simulate directory with nested content
        # The function calls list_directory_contents multiple times:
        # 1. Initial check to determine it's a directory
        # 2. _collect_volume_contents for root dir
        # 3. _collect_volume_contents for subdir
        mock_client.files.list_directory_contents.side_effect = [
            # Initial check (called with trailing /)
            iter([
                mock.Mock(name="file1.csv", path="/Volumes/c/s/v/dir/file1.csv", is_directory=False),
            ]),
            # _collect_volume_contents: root dir
            iter([
                mock.Mock(name="file1.csv", path="/Volumes/c/s/v/dir/file1.csv", is_directory=False),
                mock.Mock(name="subdir", path="/Volumes/c/s/v/dir/subdir", is_directory=True),
            ]),
            # _collect_volume_contents: subdir
            iter([
                mock.Mock(name="file2.csv", path="/Volumes/c/s/v/dir/subdir/file2.csv", is_directory=False),
            ]),
        ]
        mock_get_client.return_value = mock_client

        result = delete_from_volume("/Volumes/c/s/v/dir", recursive=True)

        assert result.success
        assert result.files_deleted == 2
        assert result.directories_deleted == 2  # subdir + root dir

    @mock.patch("databricks_tools_core.unity_catalog.volume_files.get_workspace_client")
    def test_delete_nonexistent_path_fails(self, mock_get_client):
        """Should fail for nonexistent path."""
        mock_client = mock.Mock()
        mock_client.files.get_metadata.side_effect = Exception("Not found")
        mock_client.files.list_directory_contents.side_effect = Exception("Not found")
        mock_get_client.return_value = mock_client

        result = delete_from_volume("/Volumes/catalog/schema/volume/nonexistent")

        assert not result.success
        assert "not found" in result.error.lower()

    @mock.patch("databricks_tools_core.unity_catalog.volume_files.get_workspace_client")
    def test_delete_file_handles_api_error(self, mock_get_client):
        """Should handle API errors gracefully."""
        mock_client = mock.Mock()
        mock_client.files.get_metadata.return_value = mock.Mock()
        mock_client.files.delete.side_effect = Exception("Permission denied")
        mock_get_client.return_value = mock_client

        result = delete_from_volume("/Volumes/catalog/schema/volume/file.csv")

        assert not result.success
        assert "Permission denied" in result.error

    @mock.patch("databricks_tools_core.unity_catalog.volume_files.get_workspace_client")
    def test_delete_strips_trailing_slash(self, mock_get_client):
        """Should strip trailing slash from path."""
        mock_client = mock.Mock()
        mock_client.files.get_metadata.return_value = mock.Mock()
        mock_get_client.return_value = mock_client

        result = delete_from_volume("/Volumes/catalog/schema/volume/file.csv/")

        assert result.volume_path == "/Volumes/catalog/schema/volume/file.csv"

"""
Integration tests for workspace files MCP tool.

Tests:
- manage_workspace_files: upload, delete
- File type preservation (Python files should remain FILE, not NOTEBOOK)
"""

import logging
import tempfile
from pathlib import Path

import pytest
from databricks.sdk import WorkspaceClient

from databricks_mcp_server.tools.file import manage_workspace_files
from tests.test_config import TEST_RESOURCE_PREFIX

logger = logging.getLogger(__name__)


@pytest.fixture
def test_local_file():
    """Create a temporary local file for upload tests."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("# Test Python file\n")
        f.write("print('Hello from MCP test')\n")
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
        (Path(temp_dir) / "script1.py").write_text("# Script 1\nprint('one')")
        (Path(temp_dir) / "script2.py").write_text("# Script 2\nprint('two')")
        (Path(temp_dir) / "subdir").mkdir()
        (Path(temp_dir) / "subdir" / "script3.py").write_text("# Script 3\nprint('three')")

        yield temp_dir


@pytest.mark.integration
class TestManageWorkspaceFiles:
    """Tests for manage_workspace_files tool."""

    def test_upload_single_file(
        self,
        workspace_client: WorkspaceClient,
        workspace_test_path: str,
        test_local_file: str,
    ):
        """Should upload a single file to workspace and verify it exists as FILE type (not NOTEBOOK)."""
        upload_path = f"{workspace_test_path}/single_file_test"
        file_name = Path(test_local_file).name

        result = manage_workspace_files(
            action="upload",
            local_path=test_local_file,
            workspace_path=upload_path,
            overwrite=True,
        )

        logger.info(f"Upload result: {result}")

        assert "error" not in result or result.get("error") is None, f"Upload failed: {result}"
        assert result.get("success", False), f"Upload not successful: {result}"

        # List the parent directory to see what was created
        parent_objects = list(workspace_client.workspace.list(workspace_test_path))
        logger.info(f"Objects in parent {workspace_test_path}: {[(obj.path, obj.object_type) for obj in parent_objects]}")

        # Find what was created at our upload_path
        created_obj = next((obj for obj in parent_objects if "single_file_test" in obj.path), None)
        assert created_obj is not None, f"Upload path not found in {[obj.path for obj in parent_objects]}"

        logger.info(f"Created object: path={created_obj.path}, type={created_obj.object_type}")

        # If it's a directory, list its contents to find the .py file
        if created_obj.object_type and created_obj.object_type.value == "DIRECTORY":
            inner_objects = list(workspace_client.workspace.list(upload_path))
            logger.info(f"Contents of {upload_path}: {[(obj.path, obj.object_type) for obj in inner_objects]}")

            # Find the .py file
            uploaded_file = next((obj for obj in inner_objects if obj.path.endswith(".py")), None)
            assert uploaded_file is not None, f"Could not find .py file in {[obj.path for obj in inner_objects]}"

            object_type = uploaded_file.object_type.value if uploaded_file.object_type else None
        else:
            # The upload might have created a file directly (rare case)
            object_type = created_obj.object_type.value if created_obj.object_type else None
            uploaded_file = created_obj

        logger.info(f"Uploaded file object_type: {object_type}")

        # Python files should be stored as FILE, not NOTEBOOK
        assert object_type == "FILE", \
            f"Python file should be uploaded as FILE type, not {object_type}. " \
            f"This indicates a bug where .py files are converted to notebooks during import."

    def test_upload_directory(
        self,
        workspace_test_path: str,
        test_local_dir: str,
    ):
        """Should upload a directory to workspace."""
        result = manage_workspace_files(
            action="upload",
            local_path=test_local_dir,
            workspace_path=f"{workspace_test_path}/test_dir",
            overwrite=True,
        )

        logger.info(f"Upload directory result: {result}")

        assert "error" not in result or result.get("error") is None, f"Upload failed: {result}"
        assert result.get("success", False), f"Upload not successful: {result}"

    def test_list_files_via_sdk(
        self,
        workspace_client: WorkspaceClient,
        workspace_test_path: str,
        test_local_dir: str,
    ):
        """Should upload files and verify listing via SDK."""
        # First upload some files
        upload_path = f"{workspace_test_path}/list_test"
        manage_workspace_files(
            action="upload",
            local_path=test_local_dir,
            workspace_path=upload_path,
            overwrite=True,
        )

        # List files using SDK
        objects = list(workspace_client.workspace.list(upload_path))
        logger.info(f"Listed objects: {[obj.path for obj in objects]}")

        assert len(objects) > 0, "Should have uploaded files"

    def test_delete_path(
        self,
        workspace_client: WorkspaceClient,
        workspace_test_path: str,
        test_local_file: str,
    ):
        """Should delete a file/directory from workspace and verify it's gone."""
        # First upload a file
        upload_path = f"{workspace_test_path}/delete_test"
        manage_workspace_files(
            action="upload",
            local_path=test_local_file,
            workspace_path=upload_path,
            overwrite=True,
        )

        # Verify it exists before delete using SDK
        objects_before = list(workspace_client.workspace.list(workspace_test_path))
        paths_before = [obj.path for obj in objects_before]
        assert any("delete_test" in p for p in paths_before), f"Path should exist before delete: {paths_before}"

        # Delete it
        result = manage_workspace_files(
            action="delete",
            workspace_path=upload_path,
            recursive=True,
        )

        logger.info(f"Delete result: {result}")

        assert result.get("success", False), f"Delete failed: {result}"

        # Verify it's gone using SDK
        objects_after = list(workspace_client.workspace.list(workspace_test_path))
        paths_after = [obj.path for obj in objects_after]
        assert not any("delete_test" in p for p in paths_after), f"Path should be deleted: {paths_after}"

    def test_invalid_action(self, workspace_test_path: str):
        """Should return error for invalid action."""
        result = manage_workspace_files(
            action="invalid_action",
            workspace_path=workspace_test_path,
        )

        assert "error" in result

    def test_file_type_preservation(
        self,
        workspace_client: WorkspaceClient,
        workspace_test_path: str,
    ):
        """Should preserve file types during upload - .py files should remain FILE, not NOTEBOOK.

        This test specifically catches bugs where Python files are incorrectly
        converted to Databricks notebooks during workspace import.
        """
        # Create various file types
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create files with different extensions
            test_files = {
                "script.py": ("# Python script\nprint('hello')", "FILE"),
                "data.json": ('{"key": "value"}', "FILE"),
                "config.yaml": ("key: value", "FILE"),
                "readme.txt": ("Plain text file", "FILE"),
            }

            for filename, (content, expected_type) in test_files.items():
                (temp_path / filename).write_text(content)

            # Upload all files
            upload_path = f"{workspace_test_path}/type_preservation_test"
            result = manage_workspace_files(
                action="upload",
                local_path=str(temp_path),
                workspace_path=upload_path,
                overwrite=True,
            )

            assert result.get("success", False), f"Upload failed: {result}"

            # List contents of the upload directory
            # When uploading a temp directory, it creates a subdirectory with the temp dir name
            objects = list(workspace_client.workspace.list(upload_path))
            logger.info(f"Listed objects in {upload_path}: {[(obj.path, obj.object_type) for obj in objects]}")

            # If there's a subdirectory (from temp dir), look inside it
            if objects and objects[0].object_type and objects[0].object_type.value == "DIRECTORY":
                inner_dir = objects[0].path
                objects = list(workspace_client.workspace.list(inner_dir))
                logger.info(f"Listed objects in nested dir {inner_dir}: {[(obj.path, obj.object_type) for obj in objects]}")

            for filename, (_, expected_type) in test_files.items():
                # Find this file in the listing
                file_obj = next(
                    (obj for obj in objects if filename in obj.path),
                    None
                )

                assert file_obj is not None, f"File {filename} not found in workspace listing: {[obj.path for obj in objects]}"

                actual_type = file_obj.object_type.value if file_obj.object_type else None

                assert actual_type == expected_type, \
                    f"File {filename} should be {expected_type}, but got {actual_type}. " \
                    f"This indicates a bug in file type handling during workspace import."

            logger.info("All file types preserved correctly")


@pytest.mark.integration
class TestNotebookUpload:
    """Tests for notebook vs file type handling during upload.

    Databricks notebooks have special markers (e.g., '# Databricks notebook source')
    that distinguish them from regular files. Files with these markers should be
    imported as NOTEBOOK objects, while regular files should remain as FILE objects.
    """

    def test_upload_python_notebook(
        self,
        workspace_client: WorkspaceClient,
        workspace_test_path: str,
    ):
        """Python files with notebook marker should be uploaded as NOTEBOOK type."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            # Write Databricks notebook marker + content
            f.write("# Databricks notebook source\n")
            f.write("print('Hello from Python notebook')\n")
            temp_path = f.name

        try:
            upload_path = f"{workspace_test_path}/python_notebook_test"

            result = manage_workspace_files(
                action="upload",
                local_path=temp_path,
                workspace_path=upload_path,
                overwrite=True,
            )

            logger.info(f"Upload Python notebook result: {result}")
            assert result.get("success", False), f"Upload failed: {result}"

            # Verify the uploaded object type
            info = workspace_client.workspace.get_status(upload_path)
            logger.info(f"Python notebook status: type={info.object_type}, language={info.language}")

            assert info.object_type.value == "NOTEBOOK", \
                f"Python notebook should be NOTEBOOK type, got {info.object_type}"
            assert info.language.value == "PYTHON", \
                f"Python notebook should have PYTHON language, got {info.language}"

        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_upload_sql_notebook(
        self,
        workspace_client: WorkspaceClient,
        workspace_test_path: str,
    ):
        """SQL files with notebook marker should be uploaded as NOTEBOOK type."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
            # Write Databricks notebook marker + content
            f.write("-- Databricks notebook source\n")
            f.write("SELECT 1 AS test_value\n")
            temp_path = f.name

        try:
            upload_path = f"{workspace_test_path}/sql_notebook_test"

            result = manage_workspace_files(
                action="upload",
                local_path=temp_path,
                workspace_path=upload_path,
                overwrite=True,
            )

            logger.info(f"Upload SQL notebook result: {result}")
            assert result.get("success", False), f"Upload failed: {result}"

            # Verify the uploaded object type
            info = workspace_client.workspace.get_status(upload_path)
            logger.info(f"SQL notebook status: type={info.object_type}, language={info.language}")

            assert info.object_type.value == "NOTEBOOK", \
                f"SQL notebook should be NOTEBOOK type, got {info.object_type}"
            assert info.language.value == "SQL", \
                f"SQL notebook should have SQL language, got {info.language}"

        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_upload_scala_notebook(
        self,
        workspace_client: WorkspaceClient,
        workspace_test_path: str,
    ):
        """Scala files with notebook marker should be uploaded as NOTEBOOK type."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".scala", delete=False) as f:
            # Write Databricks notebook marker + content
            f.write("// Databricks notebook source\n")
            f.write("println(\"Hello from Scala notebook\")\n")
            temp_path = f.name

        try:
            upload_path = f"{workspace_test_path}/scala_notebook_test"

            result = manage_workspace_files(
                action="upload",
                local_path=temp_path,
                workspace_path=upload_path,
                overwrite=True,
            )

            logger.info(f"Upload Scala notebook result: {result}")
            assert result.get("success", False), f"Upload failed: {result}"

            # Verify the uploaded object type
            info = workspace_client.workspace.get_status(upload_path)
            logger.info(f"Scala notebook status: type={info.object_type}, language={info.language}")

            assert info.object_type.value == "NOTEBOOK", \
                f"Scala notebook should be NOTEBOOK type, got {info.object_type}"
            assert info.language.value == "SCALA", \
                f"Scala notebook should have SCALA language, got {info.language}"

        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_upload_regular_python_file(
        self,
        workspace_client: WorkspaceClient,
        workspace_test_path: str,
    ):
        """Python files WITHOUT notebook marker should remain as FILE type."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            # Regular Python file (no notebook marker)
            f.write("# Regular Python script\n")
            f.write("def hello():\n")
            f.write("    print('Hello from regular Python file')\n")
            temp_path = f.name

        try:
            upload_path = f"{workspace_test_path}/regular_python_test.py"

            result = manage_workspace_files(
                action="upload",
                local_path=temp_path,
                workspace_path=upload_path,
                overwrite=True,
            )

            logger.info(f"Upload regular Python file result: {result}")
            assert result.get("success", False), f"Upload failed: {result}"

            # Verify the uploaded object type
            info = workspace_client.workspace.get_status(upload_path)
            logger.info(f"Regular Python file status: type={info.object_type}")

            assert info.object_type.value == "FILE", \
                f"Regular Python file should be FILE type, got {info.object_type}. " \
                f"Files without notebook markers should NOT be converted to notebooks."

        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_upload_regular_sql_file(
        self,
        workspace_client: WorkspaceClient,
        workspace_test_path: str,
    ):
        """SQL files WITHOUT notebook marker should remain as FILE type."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
            # Regular SQL file (no notebook marker)
            f.write("-- Regular SQL script\n")
            f.write("SELECT * FROM some_table WHERE id = 1;\n")
            temp_path = f.name

        try:
            upload_path = f"{workspace_test_path}/regular_sql_test.sql"

            result = manage_workspace_files(
                action="upload",
                local_path=temp_path,
                workspace_path=upload_path,
                overwrite=True,
            )

            logger.info(f"Upload regular SQL file result: {result}")
            assert result.get("success", False), f"Upload failed: {result}"

            # Verify the uploaded object type
            info = workspace_client.workspace.get_status(upload_path)
            logger.info(f"Regular SQL file status: type={info.object_type}")

            assert info.object_type.value == "FILE", \
                f"Regular SQL file should be FILE type, got {info.object_type}. " \
                f"Files without notebook markers should NOT be converted to notebooks."

        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_upload_mixed_directory(
        self,
        workspace_client: WorkspaceClient,
        workspace_test_path: str,
    ):
        """Uploading a directory with both notebooks and regular files should preserve types."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create various file types
            test_files = {
                # Notebooks (with marker)
                "notebook_python.py": (
                    "# Databricks notebook source\nprint('Python notebook')",
                    "NOTEBOOK",
                    "PYTHON"
                ),
                "notebook_sql.sql": (
                    "-- Databricks notebook source\nSELECT 1",
                    "NOTEBOOK",
                    "SQL"
                ),
                # Regular files (no marker)
                "script.py": (
                    "# Regular script\nprint('hello')",
                    "FILE",
                    None
                ),
                "query.sql": (
                    "-- Regular query\nSELECT * FROM table",
                    "FILE",
                    None
                ),
                "data.json": (
                    '{"key": "value"}',
                    "FILE",
                    None
                ),
            }

            for filename, (content, _, _) in test_files.items():
                (temp_path / filename).write_text(content)

            # Upload directory contents (trailing slash = copy contents, like cp -r src/ dest/)
            upload_path = f"{workspace_test_path}/mixed_directory_test"
            result = manage_workspace_files(
                action="upload",
                local_path=str(temp_path) + "/",  # Trailing slash = copy contents directly
                workspace_path=upload_path,
                overwrite=True,
            )

            logger.info(f"Upload mixed directory result: {result}")
            assert result.get("success", False), f"Upload failed: {result}"

            # List and verify each file's type
            objects = list(workspace_client.workspace.list(upload_path))
            logger.info(f"Listed objects: {[(obj.path, obj.object_type) for obj in objects]}")

            for filename, (_, expected_type, expected_lang) in test_files.items():
                # Find the file - notebooks don't have extensions in path
                if expected_type == "NOTEBOOK":
                    # Notebooks are stored without extension
                    name_without_ext = filename.rsplit(".", 1)[0]
                    file_obj = next(
                        (obj for obj in objects if name_without_ext in obj.path and expected_type == obj.object_type.value),
                        None
                    )
                else:
                    # Regular files keep their extension
                    file_obj = next(
                        (obj for obj in objects if filename in obj.path),
                        None
                    )

                assert file_obj is not None, \
                    f"File {filename} not found in workspace: {[obj.path for obj in objects]}"

                actual_type = file_obj.object_type.value if file_obj.object_type else None
                assert actual_type == expected_type, \
                    f"File {filename} should be {expected_type}, got {actual_type}"

                if expected_lang:
                    actual_lang = file_obj.language.value if file_obj.language else None
                    assert actual_lang == expected_lang, \
                        f"Notebook {filename} should have language {expected_lang}, got {actual_lang}"

            logger.info("All files in mixed directory have correct types")

    def test_upload_notebook_to_directory(
        self,
        workspace_client: WorkspaceClient,
        workspace_test_path: str,
    ):
        """Uploading a notebook to a directory path should work correctly."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("# Databricks notebook source\n")
            f.write("print('Notebook in directory')\n")
            temp_path = f.name

        try:
            # Create target directory first
            dir_path = f"{workspace_test_path}/notebook_in_dir"
            workspace_client.workspace.mkdirs(dir_path)

            # Upload to the directory (not to a specific file path)
            result = manage_workspace_files(
                action="upload",
                local_path=temp_path,
                workspace_path=dir_path,
                overwrite=True,
            )

            logger.info(f"Upload notebook to directory result: {result}")
            assert result.get("success", False), f"Upload failed: {result}"

            # List directory contents
            objects = list(workspace_client.workspace.list(dir_path))
            logger.info(f"Directory contents: {[(obj.path, obj.object_type, obj.language) for obj in objects]}")

            assert len(objects) > 0, f"Directory should contain the uploaded notebook"

            # Find the notebook
            notebook = next(
                (obj for obj in objects if obj.object_type.value == "NOTEBOOK"),
                None
            )
            assert notebook is not None, \
                f"Should find a NOTEBOOK in directory, got: {[(obj.path, obj.object_type) for obj in objects]}"
            assert notebook.language.value == "PYTHON", \
                f"Notebook should be PYTHON, got {notebook.language}"

        finally:
            Path(temp_path).unlink(missing_ok=True)

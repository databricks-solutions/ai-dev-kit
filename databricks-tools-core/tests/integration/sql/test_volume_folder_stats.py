"""
Integration tests for volume folder statistics functions.

Tests:
- get_volume_folder_details
- format="parquet" - read parquet data and compute stats
- format="file" - list files only
- TableStatLevel variants
"""

import pytest
from databricks_tools_core.sql import (
    get_volume_folder_details,
    TableStatLevel,
    TableSchemaResult,
    DataSourceInfo,
    VolumeFileInfo,
)


@pytest.mark.integration
class TestGetVolumeFolderDetailsParquet:
    """Tests for get_volume_folder_details with parquet format."""

    def test_parquet_basic_info(self, warehouse_id, test_catalog, test_schema, test_volume):
        """Should read parquet files and return basic info."""
        volume_path = f"{test_catalog}/{test_schema}/{test_volume}/parquet_data"

        result = get_volume_folder_details(
            volume_path=volume_path,
            format="parquet",
            table_stat_level=TableStatLevel.SIMPLE,
            warehouse_id=warehouse_id,
        )

        assert isinstance(result, TableSchemaResult)
        assert len(result.tables) == 1
        info = result.tables[0]
        assert isinstance(info, DataSourceInfo)
        assert info.error is None, f"Unexpected error: {info.error}"
        assert info.format == "parquet"
        assert info.total_files >= 1
        assert info.total_rows == 5  # We have 5 rows in test data

    def test_parquet_column_details(self, warehouse_id, test_catalog, test_schema, test_volume):
        """Should return column statistics for parquet data."""
        volume_path = f"{test_catalog}/{test_schema}/{test_volume}/parquet_data"

        result = get_volume_folder_details(
            volume_path=volume_path,
            format="parquet",
            table_stat_level=TableStatLevel.SIMPLE,
            warehouse_id=warehouse_id,
        )

        info = result.tables[0]
        assert info.error is None
        assert info.column_details is not None
        assert len(info.column_details) == 5  # id, name, age, salary, department

        # Check specific columns
        assert "id" in info.column_details
        assert "name" in info.column_details
        assert "age" in info.column_details
        assert "salary" in info.column_details
        assert "department" in info.column_details

        # Check age column has numeric stats
        age_col = info.column_details["age"]
        assert age_col.name == "age"
        assert age_col.total_count == 5

    def test_parquet_numeric_stats(self, warehouse_id, test_catalog, test_schema, test_volume):
        """Should compute min/max/avg for numeric columns."""
        volume_path = f"{test_catalog}/{test_schema}/{test_volume}/parquet_data"

        result = get_volume_folder_details(
            volume_path=volume_path,
            format="parquet",
            table_stat_level=TableStatLevel.SIMPLE,
            warehouse_id=warehouse_id,
        )

        info = result.tables[0]
        assert info.error is None

        # Check salary column stats - may be inferred as numeric or string
        # depending on how read_files returns the data
        salary_col = info.column_details["salary"]
        assert salary_col.total_count == 5
        assert salary_col.unique_count == 5  # All unique salaries

        # If recognized as numeric, should have min/max/avg
        # If recognized as string, should have samples
        if salary_col.min is not None:
            # Verify values (50000, 60000, 75000, 55000, 80000)
            assert salary_col.min == 50000.0
            assert salary_col.max == 80000.0
        else:
            # String type - should have samples
            assert salary_col.samples is not None
            assert len(salary_col.samples) > 0

    def test_parquet_detailed_has_samples(self, warehouse_id, test_catalog, test_schema, test_volume):
        """DETAILED level should include sample data."""
        volume_path = f"{test_catalog}/{test_schema}/{test_volume}/parquet_data"

        result = get_volume_folder_details(
            volume_path=volume_path,
            format="parquet",
            table_stat_level=TableStatLevel.DETAILED,
            warehouse_id=warehouse_id,
        )

        info = result.tables[0]
        assert info.error is None
        assert info.sample_data is not None
        assert len(info.sample_data) > 0
        assert len(info.sample_data) <= 5

        # Check sample data has expected columns
        first_row = info.sample_data[0]
        assert "id" in first_row
        assert "name" in first_row

    def test_parquet_stat_level_none(self, warehouse_id, test_catalog, test_schema, test_volume):
        """NONE level should return schema without stats."""
        volume_path = f"{test_catalog}/{test_schema}/{test_volume}/parquet_data"

        result = get_volume_folder_details(
            volume_path=volume_path,
            format="parquet",
            table_stat_level=TableStatLevel.NONE,
            warehouse_id=warehouse_id,
        )

        info = result.tables[0]
        assert info.error is None
        assert info.total_rows == 5  # Row count still present
        # Column details should have schema but minimal stats
        assert info.column_details is not None


@pytest.mark.integration
class TestGetVolumeFolderDetailsFile:
    """Tests for get_volume_folder_details with format='file' (listing only)."""

    def test_file_listing(self, test_catalog, test_schema, test_volume):
        """format='file' should list files without reading data."""
        volume_path = f"{test_catalog}/{test_schema}/{test_volume}/txt_files"

        result = get_volume_folder_details(
            volume_path=volume_path,
            format="file",
        )

        assert isinstance(result, TableSchemaResult)
        info = result.tables[0]
        assert info.error is None, f"Unexpected error: {info.error}"
        assert info.format == "file"
        assert info.total_files == 3  # readme.txt, data.txt, notes.txt

        # Should have file list
        assert info.files is not None
        assert len(info.files) == 3

        # Check file info structure
        file_names = [f.name for f in info.files]
        assert "readme.txt" in file_names
        assert "data.txt" in file_names
        assert "notes.txt" in file_names

    def test_file_listing_has_size(self, test_catalog, test_schema, test_volume):
        """File listing should include file sizes."""
        volume_path = f"{test_catalog}/{test_schema}/{test_volume}/txt_files"

        result = get_volume_folder_details(
            volume_path=volume_path,
            format="file",
        )

        info = result.tables[0]
        assert info.error is None
        assert info.files is not None

        # All files should have size
        for file_info in info.files:
            assert isinstance(file_info, VolumeFileInfo)
            assert file_info.size_bytes is not None or file_info.is_directory

    def test_file_listing_no_data_reading(self, test_catalog, test_schema, test_volume):
        """format='file' should not read data (no column_details, no rows)."""
        volume_path = f"{test_catalog}/{test_schema}/{test_volume}/txt_files"

        result = get_volume_folder_details(
            volume_path=volume_path,
            format="file",
        )

        info = result.tables[0]
        assert info.error is None
        # Should not have data-related fields
        assert info.column_details is None
        assert info.total_rows is None
        assert info.sample_data is None


@pytest.mark.integration
class TestVolumeFolderPathFormats:
    """Tests for different volume path formats."""

    def test_short_path_format(self, warehouse_id, test_catalog, test_schema, test_volume):
        """Should accept catalog/schema/volume/path format."""
        volume_path = f"{test_catalog}/{test_schema}/{test_volume}/parquet_data"

        result = get_volume_folder_details(
            volume_path=volume_path,
            format="parquet",
            warehouse_id=warehouse_id,
        )

        info = result.tables[0]
        assert info.error is None
        assert "/Volumes/" in info.name

    def test_full_volumes_path_format(self, warehouse_id, test_catalog, test_schema, test_volume):
        """Should accept /Volumes/catalog/schema/volume/path format."""
        volume_path = f"/Volumes/{test_catalog}/{test_schema}/{test_volume}/parquet_data"

        result = get_volume_folder_details(
            volume_path=volume_path,
            format="parquet",
            warehouse_id=warehouse_id,
        )

        info = result.tables[0]
        assert info.error is None
        assert info.name == volume_path


@pytest.mark.integration
class TestVolumeFolderErrors:
    """Tests for error handling."""

    def test_nonexistent_path(self, test_catalog, test_schema, test_volume):
        """Should return error for non-existent path."""
        volume_path = f"{test_catalog}/{test_schema}/{test_volume}/nonexistent_folder"

        result = get_volume_folder_details(
            volume_path=volume_path,
            format="file",
        )

        info = result.tables[0]
        assert info.error is not None
        assert "not found" in info.error.lower() or "empty" in info.error.lower()

    def test_empty_folder(self, workspace_client, test_catalog, test_schema, test_volume):
        """Should handle empty folders gracefully."""
        # Create an empty folder by uploading and deleting a file
        volume_path = f"/Volumes/{test_catalog}/{test_schema}/{test_volume}/empty_folder"

        # Upload a temp file to create the folder
        from io import BytesIO

        temp_path = f"{volume_path}/temp.txt"
        workspace_client.files.upload(temp_path, BytesIO(b"temp"), overwrite=True)
        workspace_client.files.delete(temp_path)

        result = get_volume_folder_details(
            volume_path=f"{test_catalog}/{test_schema}/{test_volume}/empty_folder",
            format="file",
        )

        info = result.tables[0]
        # Should handle empty gracefully (either error or empty list)
        if info.error is None:
            assert info.total_files == 0
        else:
            assert "empty" in info.error.lower()


@pytest.mark.integration
class TestVolumeFolderResultMethods:
    """Tests for TableSchemaResult methods with volume folder data."""

    def test_keep_basic_stats(self, warehouse_id, test_catalog, test_schema, test_volume):
        """keep_basic_stats() should remove heavy stats."""
        volume_path = f"{test_catalog}/{test_schema}/{test_volume}/parquet_data"

        result = get_volume_folder_details(
            volume_path=volume_path,
            format="parquet",
            table_stat_level=TableStatLevel.DETAILED,
            warehouse_id=warehouse_id,
        )

        basic_result = result.keep_basic_stats()

        info = basic_result.tables[0]
        assert info.error is None
        assert info.column_details is not None

        # Should still have basic column info
        salary_col = info.column_details["salary"]
        assert salary_col.total_count == 5

        # Sample data should be removed
        assert info.sample_data is None

"""
Integration tests for Unity Catalog - Security Policy operations.

Tests:
- create_security_function
- set_row_filter
- drop_row_filter
- set_column_mask
- drop_column_mask
"""

import logging
import pytest

from databricks_tools_core.unity_catalog import (
    create_security_function,
    set_row_filter,
    drop_row_filter,
    set_column_mask,
    drop_column_mask,
)

logger = logging.getLogger(__name__)

UC_TEST_PREFIX = "uc_test"


@pytest.mark.integration
class TestCreateSecurityFunction:
    """Tests for creating security functions."""

    def test_create_row_filter_function(
        self,
        test_catalog: str,
        uc_test_schema: str,
        unique_name: str,
        warehouse_id: str,
        cleanup_functions,
    ):
        """Should create a row filter function."""
        fn_name = (
            f"{test_catalog}.{uc_test_schema}.{UC_TEST_PREFIX}_row_filter_{unique_name}"
        )
        cleanup_functions(fn_name)

        result = create_security_function(
            function_name=fn_name,
            parameter_name="dept",
            parameter_type="STRING",
            return_type="BOOLEAN",
            function_body="RETURN dept = 'Engineering'",
            comment="Test row filter function",
            warehouse_id=warehouse_id,
        )

        assert result["status"] == "created"
        assert result["function_name"] == fn_name
        logger.info(f"Row filter function created: {fn_name}")

    def test_create_column_mask_function(
        self,
        test_catalog: str,
        uc_test_schema: str,
        unique_name: str,
        warehouse_id: str,
        cleanup_functions,
    ):
        """Should create a column mask function."""
        fn_name = (
            f"{test_catalog}.{uc_test_schema}.{UC_TEST_PREFIX}_col_mask_{unique_name}"
        )
        cleanup_functions(fn_name)

        result = create_security_function(
            function_name=fn_name,
            parameter_name="val",
            parameter_type="STRING",
            return_type="STRING",
            function_body="RETURN CASE WHEN is_account_group_member('admins') THEN val ELSE '***' END",
            warehouse_id=warehouse_id,
        )

        assert result["status"] == "created"
        logger.info(f"Column mask function created: {fn_name}")


@pytest.mark.integration
class TestRowFilter:
    """Tests for row filter operations."""

    def test_set_and_drop_row_filter(
        self,
        test_catalog: str,
        uc_test_schema: str,
        uc_test_table: str,
        unique_name: str,
        warehouse_id: str,
        cleanup_functions,
    ):
        """Should set and then drop a row filter on a table."""
        fn_name = f"{test_catalog}.{uc_test_schema}.{UC_TEST_PREFIX}_rf_{unique_name}"
        cleanup_functions(fn_name)

        # Create filter function
        create_security_function(
            function_name=fn_name,
            parameter_name="dept",
            parameter_type="STRING",
            return_type="BOOLEAN",
            function_body="RETURN dept = 'Engineering'",
            warehouse_id=warehouse_id,
        )

        # Set row filter
        logger.info(f"Setting row filter on {uc_test_table}")
        set_result = set_row_filter(
            table_name=uc_test_table,
            filter_function=fn_name,
            filter_columns=["department"],
            warehouse_id=warehouse_id,
        )

        assert set_result["status"] == "row_filter_set"
        assert set_result["function"] == fn_name
        logger.info(f"Row filter set: {set_result['sql']}")

        # Drop row filter
        logger.info(f"Dropping row filter from {uc_test_table}")
        drop_result = drop_row_filter(
            table_name=uc_test_table,
            warehouse_id=warehouse_id,
        )

        assert drop_result["status"] == "row_filter_dropped"
        logger.info(f"Row filter dropped: {drop_result['sql']}")


@pytest.mark.integration
class TestColumnMask:
    """Tests for column mask operations."""

    def test_set_and_drop_column_mask(
        self,
        test_catalog: str,
        uc_test_schema: str,
        uc_test_table: str,
        unique_name: str,
        warehouse_id: str,
        cleanup_functions,
    ):
        """Should set and then drop a column mask."""
        fn_name = f"{test_catalog}.{uc_test_schema}.{UC_TEST_PREFIX}_cm_{unique_name}"
        cleanup_functions(fn_name)

        # Create mask function
        create_security_function(
            function_name=fn_name,
            parameter_name="val",
            parameter_type="STRING",
            return_type="STRING",
            function_body="RETURN CASE WHEN is_account_group_member('admins') THEN val ELSE '***@***.com' END",
            warehouse_id=warehouse_id,
        )

        # Set column mask
        logger.info(f"Setting column mask on {uc_test_table}.email")
        set_result = set_column_mask(
            table_name=uc_test_table,
            column_name="email",
            mask_function=fn_name,
            warehouse_id=warehouse_id,
        )

        assert set_result["status"] == "column_mask_set"
        assert set_result["column"] == "email"
        logger.info(f"Column mask set: {set_result['sql']}")

        # Drop column mask
        logger.info(f"Dropping column mask from {uc_test_table}.email")
        drop_result = drop_column_mask(
            table_name=uc_test_table,
            column_name="email",
            warehouse_id=warehouse_id,
        )

        assert drop_result["status"] == "column_mask_dropped"
        logger.info(f"Column mask dropped: {drop_result['sql']}")


@pytest.mark.integration
class TestSecurityPolicyValidation:
    """Tests for input validation in security policy functions."""

    def test_invalid_identifier_raises(self):
        """Should raise ValueError for invalid SQL identifiers."""
        with pytest.raises(ValueError) as exc_info:
            set_row_filter(
                table_name="DROP TABLE; --",
                filter_function="fn",
                filter_columns=["col"],
            )

        assert "invalid sql identifier" in str(exc_info.value).lower()

    def test_invalid_column_identifier_raises(self):
        """Should raise ValueError for invalid column in filter."""
        with pytest.raises(ValueError) as exc_info:
            set_row_filter(
                table_name="catalog.schema.table",
                filter_function="catalog.schema.fn",
                filter_columns=["col; DROP TABLE--"],
            )

        assert "invalid sql identifier" in str(exc_info.value).lower()

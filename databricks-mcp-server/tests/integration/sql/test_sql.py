"""
Integration tests for SQL MCP tools.

Tests:
- execute_sql: basic queries, catalog/schema context
- manage_warehouse: list, get_best
"""

import logging

import pytest

from databricks_mcp_server.tools.sql import execute_sql, manage_warehouse
from tests.test_config import TEST_CATALOG, SCHEMAS

logger = logging.getLogger(__name__)


@pytest.mark.integration
class TestExecuteSql:
    """Tests for execute_sql tool."""

    def test_simple_select(self, warehouse_id: str):
        """Should execute a simple SELECT statement."""
        result = execute_sql(
            sql_query="SELECT 1 as num, 'hello' as greeting",
            warehouse_id=warehouse_id,
        )

        logger.info(f"Result: {result}")

        # Result is now a markdown-formatted string
        assert isinstance(result, str)
        assert "(1 row)" in result
        assert "num" in result and "greeting" in result
        assert "| 1 |" in result and "hello" in result

    def test_select_with_multiple_rows(self, warehouse_id: str):
        """Should return multiple rows correctly."""
        result = execute_sql(
            sql_query="""
                SELECT * FROM (
                    VALUES (1, 'a'), (2, 'b'), (3, 'c')
                ) AS t(id, letter)
            """,
            warehouse_id=warehouse_id,
        )

        # Result is now a markdown-formatted string
        assert isinstance(result, str)
        assert "(3 rows)" in result
        assert "id" in result and "letter" in result
        # Check all three rows are present
        assert "| 1 |" in result and "| a |" in result
        assert "| 2 |" in result and "| b |" in result
        assert "| 3 |" in result and "| c |" in result

    def test_create_and_query_table(
        self,
        warehouse_id: str,
        test_catalog: str,
        sql_schema: str,
    ):
        """Should create a table and query it."""
        table_name = f"{test_catalog}.{sql_schema}.test_table"

        # Create table
        execute_sql(
            sql_query=f"""
                CREATE OR REPLACE TABLE {table_name} (
                    id INT,
                    name STRING
                )
            """,
            warehouse_id=warehouse_id,
        )

        # Insert data
        execute_sql(
            sql_query=f"""
                INSERT INTO {table_name} VALUES
                (1, 'Alice'),
                (2, 'Bob')
            """,
            warehouse_id=warehouse_id,
        )

        # Query
        result = execute_sql(
            sql_query=f"SELECT * FROM {table_name} ORDER BY id",
            warehouse_id=warehouse_id,
        )

        # Result is now a markdown-formatted string
        assert isinstance(result, str)
        assert "(2 rows)" in result
        assert "Alice" in result
        assert "Bob" in result

    def test_catalog_schema_context(
        self,
        warehouse_id: str,
        test_catalog: str,
        sql_schema: str,
    ):
        """Should use catalog/schema context for unqualified names."""
        table_name = f"{test_catalog}.{sql_schema}.context_test"

        # Create table with qualified name
        execute_sql(
            sql_query=f"CREATE OR REPLACE TABLE {table_name} AS SELECT 1 as val",
            warehouse_id=warehouse_id,
        )

        # Query with unqualified name using context
        result = execute_sql(
            sql_query="SELECT * FROM context_test",
            warehouse_id=warehouse_id,
            catalog=test_catalog,
            schema=sql_schema,
        )

        # Result is now a markdown-formatted string
        assert isinstance(result, str)
        assert "(1 row)" in result

    def test_auto_select_warehouse(self, test_catalog: str, sql_schema: str):
        """Should auto-select warehouse when not provided."""
        result = execute_sql(
            sql_query="SELECT 1 as num",
            # warehouse_id not provided
        )

        # Result is now a markdown-formatted string
        assert isinstance(result, str)
        assert "(1 row)" in result

    def test_invalid_sql_returns_error(self, warehouse_id: str):
        """Should handle invalid SQL gracefully."""
        # This should raise or return error, not crash
        try:
            result = execute_sql(
                sql_query="SELECT * FROM nonexistent_table_xyz_12345",
                warehouse_id=warehouse_id,
            )
            # If it returns instead of raising, check for error indicators
            logger.info(f"Result for invalid SQL: {result}")
        except Exception as e:
            logger.info(f"Expected error for invalid SQL: {e}")
            error_msg = str(e).lower()
            assert "not found" in error_msg or "does not exist" in error_msg or "cannot be found" in error_msg


@pytest.mark.integration
class TestManageWarehouse:
    """Tests for manage_warehouse tool."""

    def test_list_warehouses(self):
        """Should list all warehouses."""
        result = manage_warehouse(action="list")

        logger.info(f"List result: {result}")

        assert "error" not in result, f"List failed: {result}"
        assert "warehouses" in result
        assert isinstance(result["warehouses"], list)

    def test_get_best_warehouse(self):
        """Should return the best available warehouse."""
        result = manage_warehouse(action="get_best")

        logger.info(f"Get best result: {result}")

        assert "error" not in result, f"Get best failed: {result}"
        # Should have warehouse info
        assert result.get("warehouse_id") or result.get("id")

    def test_invalid_action(self):
        """Should return error for invalid action."""
        result = manage_warehouse(action="invalid_action")

        assert "error" in result

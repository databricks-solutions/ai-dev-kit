"""
Integration tests for SQL execution functions.

Tests:
- execute_sql
- execute_sql_multi
"""

import pytest
from databricks_tools_core.sql import execute_sql, execute_sql_multi, SQLExecutionError


@pytest.mark.integration
class TestExecuteSQL:
    """Tests for execute_sql function."""

    def test_simple_select(self, warehouse_id):
        """Should execute a simple SELECT statement."""
        result = execute_sql(
            sql_query="SELECT 1 as num, 'hello' as greeting",
            warehouse_id=warehouse_id,
        )

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["num"] == "1" or result[0]["num"] == 1
        assert result[0]["greeting"] == "hello"

    def test_select_with_multiple_rows(self, warehouse_id):
        """Should return multiple rows correctly."""
        result = execute_sql(
            sql_query="""
                SELECT * FROM (
                    VALUES (1, 'a'), (2, 'b'), (3, 'c')
                ) AS t(id, letter)
            """,
            warehouse_id=warehouse_id,
        )

        assert len(result) == 3
        assert all("id" in row and "letter" in row for row in result)

    def test_select_from_test_table(self, warehouse_id, test_catalog, test_schema, test_tables):
        """Should query data from test tables."""
        result = execute_sql(
            sql_query=f"SELECT * FROM {test_tables['customers']} ORDER BY customer_id",
            warehouse_id=warehouse_id,
            catalog=test_catalog,
            schema=test_schema,
        )

        assert len(result) == 5
        assert result[0]["name"] == "Alice Smith"
        assert result[4]["name"] == "Eve Wilson"

    def test_select_with_catalog_schema_context(self, warehouse_id, test_catalog, test_schema, test_tables):
        """Should use catalog/schema context for unqualified table names."""
        result = execute_sql(
            sql_query="SELECT COUNT(*) as cnt FROM customers",
            warehouse_id=warehouse_id,
            catalog=test_catalog,
            schema=test_schema,
        )

        assert len(result) == 1
        count = int(result[0]["cnt"])
        assert count == 5

    def test_aggregate_query(self, warehouse_id, test_catalog, test_schema, test_tables):
        """Should handle aggregate functions."""
        result = execute_sql(
            sql_query=f"""
                SELECT
                    status,
                    COUNT(*) as order_count,
                    SUM(amount) as total_amount
                FROM {test_tables["orders"]}
                GROUP BY status
                ORDER BY status
            """,
            warehouse_id=warehouse_id,
        )

        assert len(result) == 3  # cancelled, completed, pending
        statuses = [row["status"] for row in result]
        assert "completed" in statuses
        assert "pending" in statuses

    def test_join_query(self, warehouse_id, test_catalog, test_schema, test_tables):
        """Should handle JOIN operations."""
        result = execute_sql(
            sql_query=f"""
                SELECT
                    c.name,
                    COUNT(o.order_id) as order_count
                FROM {test_tables["customers"]} c
                LEFT JOIN {test_tables["orders"]} o ON c.customer_id = o.customer_id
                GROUP BY c.name
                ORDER BY order_count DESC
            """,
            warehouse_id=warehouse_id,
        )

        assert len(result) == 5
        # Alice has the most orders (3)
        assert result[0]["name"] == "Alice Smith"

    def test_auto_selects_warehouse(self, test_catalog, test_schema, test_tables):
        """Should auto-select warehouse if not provided."""
        result = execute_sql(
            sql_query=f"SELECT COUNT(*) as cnt FROM {test_tables['customers']}",
            # warehouse_id not provided
        )

        assert len(result) == 1
        assert int(result[0]["cnt"]) == 5

    def test_invalid_sql_raises_error(self, warehouse_id):
        """Should raise SQLExecutionError for invalid SQL."""
        with pytest.raises(SQLExecutionError) as exc_info:
            execute_sql(
                sql_query="SELECT * FROM nonexistent_table_xyz",
                warehouse_id=warehouse_id,
            )

        assert "TABLE_OR_VIEW_NOT_FOUND" in str(exc_info.value).upper() or "NOT FOUND" in str(exc_info.value).upper()

    def test_syntax_error_raises_error(self, warehouse_id):
        """Should raise SQLExecutionError for syntax errors."""
        with pytest.raises(SQLExecutionError) as exc_info:
            execute_sql(
                sql_query="SELEC * FORM table",  # typos
                warehouse_id=warehouse_id,
            )

        error_msg = str(exc_info.value).upper()
        assert "SYNTAX" in error_msg or "PARSE" in error_msg or "ERROR" in error_msg


@pytest.mark.integration
class TestExecuteSQLMulti:
    """Tests for execute_sql_multi function."""

    def test_multiple_independent_statements(self, warehouse_id, test_catalog, test_schema):
        """Should execute multiple independent statements."""
        result = execute_sql_multi(
            sql_content=f"""
                CREATE OR REPLACE TABLE {test_catalog}.{test_schema}.multi_test_1
                    AS SELECT 1 as id;
                CREATE OR REPLACE TABLE {test_catalog}.{test_schema}.multi_test_2
                    AS SELECT 2 as id;
                SELECT * FROM {test_catalog}.{test_schema}.multi_test_1;
                SELECT * FROM {test_catalog}.{test_schema}.multi_test_2;
            """,
            warehouse_id=warehouse_id,
            catalog=test_catalog,
            schema=test_schema,
        )

        assert "results" in result
        assert "execution_summary" in result

        # All 4 statements should succeed
        results = result["results"]
        assert len(results) == 4
        assert all(r["status"] == "success" for r in results.values())

    def test_dependency_analysis(self, warehouse_id, test_catalog, test_schema):
        """Should analyze dependencies and execute in correct order."""
        result = execute_sql_multi(
            sql_content=f"""
                CREATE OR REPLACE TABLE {test_catalog}.{test_schema}.dep_base
                    AS SELECT 1 as id, 'a' as val;
                CREATE OR REPLACE TABLE {test_catalog}.{test_schema}.dep_derived
                    AS SELECT * FROM {test_catalog}.{test_schema}.dep_base WHERE id = 1;
                SELECT COUNT(*) FROM {test_catalog}.{test_schema}.dep_derived;
            """,
            warehouse_id=warehouse_id,
        )

        summary = result["execution_summary"]

        # Should have multiple groups due to dependencies
        assert summary["total_groups"] >= 2

        # All should succeed
        assert all(r["status"] == "success" for r in result["results"].values())

    def test_parallel_execution_info(self, warehouse_id, test_catalog, test_schema):
        """Should indicate which queries ran in parallel."""
        result = execute_sql_multi(
            sql_content=f"""
                CREATE OR REPLACE TABLE {test_catalog}.{test_schema}.para_1 AS SELECT 1 as id;
                CREATE OR REPLACE TABLE {test_catalog}.{test_schema}.para_2 AS SELECT 2 as id;
                CREATE OR REPLACE TABLE {test_catalog}.{test_schema}.para_3 AS SELECT 3 as id;
            """,
            warehouse_id=warehouse_id,
        )

        summary = result["execution_summary"]

        # These are independent, should be in same group (parallel)
        groups = summary["groups"]
        assert len(groups) >= 1

        # First group should have all 3 (parallel)
        first_group = groups[0]
        assert first_group["group_size"] == 3
        assert first_group["is_parallel"] is True

    def test_stops_on_error(self, warehouse_id, test_catalog, test_schema):
        """Should stop execution when a query fails."""
        result = execute_sql_multi(
            sql_content=f"""
                CREATE OR REPLACE TABLE {test_catalog}.{test_schema}.stop_test AS SELECT 1 as id;
                SELECT * FROM nonexistent_table_xyz_123;
                CREATE OR REPLACE TABLE {test_catalog}.{test_schema}.should_not_run AS SELECT 2 as id;
            """,
            warehouse_id=warehouse_id,
        )

        summary = result["execution_summary"]

        # Should have stopped after error
        assert summary["stopped_after_group"] is not None

        # Check that we have at least one error
        has_error = any(r["status"] == "error" for r in result["results"].values())
        assert has_error

    def test_execution_summary_structure(self, warehouse_id, test_catalog, test_schema):
        """Should return proper execution summary."""
        result = execute_sql_multi(
            sql_content="""
                SELECT 1 as a;
                SELECT 2 as b;
            """,
            warehouse_id=warehouse_id,
        )

        summary = result["execution_summary"]

        assert "total_queries" in summary
        assert "total_groups" in summary
        assert "total_time" in summary
        assert "groups" in summary

        assert summary["total_queries"] == 2
        assert isinstance(summary["total_time"], float)

    def test_result_contains_query_details(self, warehouse_id, test_catalog, test_schema):
        """Each result should contain query details."""
        result = execute_sql_multi(
            sql_content="SELECT 1 as num; SELECT 2 as num;",
            warehouse_id=warehouse_id,
        )

        for idx, query_result in result["results"].items():
            assert "query_index" in query_result
            assert "status" in query_result
            assert "execution_time" in query_result
            assert "query_preview" in query_result
            assert "group_number" in query_result

    def test_handles_comments(self, warehouse_id):
        """Should handle SQL comments correctly."""
        result = execute_sql_multi(
            sql_content="""
                -- This is a comment
                SELECT 1 as first;
                /* Multi-line
                   comment */
                SELECT 2 as second;
            """,
            warehouse_id=warehouse_id,
        )

        assert len(result["results"]) == 2
        assert all(r["status"] == "success" for r in result["results"].values())

    def test_auto_selects_warehouse(self, test_catalog, test_schema):
        """Should auto-select warehouse if not provided."""
        result = execute_sql_multi(
            sql_content="SELECT 1 as num;",
            # warehouse_id not provided
        )

        assert len(result["results"]) == 1
        assert result["results"][0]["status"] == "success"

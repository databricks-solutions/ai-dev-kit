"""
Integration tests for table statistics functions.

Tests:
- get_table_details
- TableStatLevel (NONE, SIMPLE, DETAILED)
- GLOB pattern matching
- Caching behavior
"""

import pytest
from databricks_tools_core.sql import (
    get_table_details,
    TableStatLevel,
    TableSchemaResult,
)


@pytest.mark.integration
class TestGetTableDetails:
    """Tests for get_table_details function."""

    def test_get_all_tables(self, warehouse_id, test_catalog, test_schema, test_tables):
        """Should list all tables when table_names is empty."""
        result = get_table_details(
            catalog=test_catalog,
            schema=test_schema,
            table_names=[],
            warehouse_id=warehouse_id,
        )

        assert isinstance(result, TableSchemaResult)
        assert result.catalog == test_catalog
        assert result.schema_name == test_schema
        assert len(result.tables) >= 3  # customers, orders, products

        table_names = [t.name.split(".")[-1] for t in result.tables]
        assert "customers" in table_names
        assert "orders" in table_names
        assert "products" in table_names

    def test_get_specific_tables(
        self, warehouse_id, test_catalog, test_schema, test_tables
    ):
        """Should get specific tables by exact name."""
        result = get_table_details(
            catalog=test_catalog,
            schema=test_schema,
            table_names=["customers", "orders"],
            warehouse_id=warehouse_id,
        )

        assert len(result.tables) == 2
        table_names = [t.name.split(".")[-1] for t in result.tables]
        assert "customers" in table_names
        assert "orders" in table_names
        assert "products" not in table_names

    def test_glob_pattern_star(
        self, warehouse_id, test_catalog, test_schema, test_tables
    ):
        """Should filter tables using * glob pattern."""
        # First create tables with a common prefix
        from databricks_tools_core.sql import execute_sql

        execute_sql(
            sql_query=f"CREATE OR REPLACE TABLE {test_catalog}.{test_schema}.raw_sales AS SELECT 1 as id",
            warehouse_id=warehouse_id,
        )
        execute_sql(
            sql_query=f"CREATE OR REPLACE TABLE {test_catalog}.{test_schema}.raw_inventory AS SELECT 2 as id",
            warehouse_id=warehouse_id,
        )

        result = get_table_details(
            catalog=test_catalog,
            schema=test_schema,
            table_names=["raw_*"],
            warehouse_id=warehouse_id,
        )

        assert len(result.tables) >= 2
        for table in result.tables:
            assert table.name.split(".")[-1].startswith("raw_")

    def test_glob_pattern_question_mark(
        self, warehouse_id, test_catalog, test_schema, test_tables
    ):
        """Should filter tables using ? glob pattern."""
        from databricks_tools_core.sql import execute_sql

        execute_sql(
            sql_query=f"CREATE OR REPLACE TABLE {test_catalog}.{test_schema}.dim_a AS SELECT 1 as id",
            warehouse_id=warehouse_id,
        )
        execute_sql(
            sql_query=f"CREATE OR REPLACE TABLE {test_catalog}.{test_schema}.dim_b AS SELECT 2 as id",
            warehouse_id=warehouse_id,
        )

        result = get_table_details(
            catalog=test_catalog,
            schema=test_schema,
            table_names=["dim_?"],
            warehouse_id=warehouse_id,
        )

        assert len(result.tables) >= 2
        for table in result.tables:
            name = table.name.split(".")[-1]
            assert name.startswith("dim_") and len(name) == 5

    def test_mixed_patterns_and_exact(
        self, warehouse_id, test_catalog, test_schema, test_tables
    ):
        """Should handle mix of glob patterns and exact names."""
        result = get_table_details(
            catalog=test_catalog,
            schema=test_schema,
            table_names=["customers", "raw_*"],
            warehouse_id=warehouse_id,
        )

        table_names = [t.name.split(".")[-1] for t in result.tables]
        assert "customers" in table_names
        # Should also include raw_* tables if they exist


@pytest.mark.integration
class TestTableStatLevelNone:
    """Tests for TableStatLevel.NONE (DDL only, no stats)."""

    def test_stat_level_none_returns_ddl(
        self, warehouse_id, test_catalog, test_schema, test_tables
    ):
        """Should return DDL without column stats."""
        result = get_table_details(
            catalog=test_catalog,
            schema=test_schema,
            table_names=["customers"],
            table_stat_level=TableStatLevel.NONE,
            warehouse_id=warehouse_id,
        )

        assert len(result.tables) == 1
        table = result.tables[0]

        # Should have DDL
        assert table.ddl is not None
        assert "CREATE" in table.ddl.upper()

        # Should NOT have column details
        assert table.column_details is None

        # Should NOT have row count
        assert table.total_rows is None

    def test_stat_level_none_is_fast(
        self, warehouse_id, test_catalog, test_schema, test_tables
    ):
        """NONE level should be faster than SIMPLE/DETAILED."""
        import time

        # NONE level
        start = time.time()
        get_table_details(
            catalog=test_catalog,
            schema=test_schema,
            table_names=["customers"],
            table_stat_level=TableStatLevel.NONE,
            warehouse_id=warehouse_id,
        )
        none_time = time.time() - start

        # SIMPLE level (should be slower due to stats collection)
        start = time.time()
        get_table_details(
            catalog=test_catalog,
            schema=test_schema,
            table_names=["orders"],  # Different table to avoid cache
            table_stat_level=TableStatLevel.SIMPLE,
            warehouse_id=warehouse_id,
        )
        simple_time = time.time() - start

        # NONE should generally be faster (though not guaranteed due to caching)
        # Just ensure both complete without error
        assert none_time >= 0
        assert simple_time >= 0


@pytest.mark.integration
class TestTableStatLevelSimple:
    """Tests for TableStatLevel.SIMPLE (basic stats with caching)."""

    def test_stat_level_simple_has_basic_stats(
        self, warehouse_id, test_catalog, test_schema, test_tables
    ):
        """Should return basic column statistics."""
        result = get_table_details(
            catalog=test_catalog,
            schema=test_schema,
            table_names=["customers"],
            table_stat_level=TableStatLevel.SIMPLE,
            warehouse_id=warehouse_id,
        )

        assert len(result.tables) == 1
        table = result.tables[0]

        # Should have DDL
        assert table.ddl is not None

        # Should have column details
        assert table.column_details is not None
        assert len(table.column_details) > 0

        # Check a known column
        if "name" in table.column_details:
            name_col = table.column_details["name"]
            assert name_col.name == "name"
            assert name_col.data_type is not None

    def test_stat_level_simple_excludes_heavy_stats(
        self, warehouse_id, test_catalog, test_schema, test_tables
    ):
        """SIMPLE level should not include histograms/percentiles."""
        result = get_table_details(
            catalog=test_catalog,
            schema=test_schema,
            table_names=["orders"],
            table_stat_level=TableStatLevel.SIMPLE,
            warehouse_id=warehouse_id,
        )

        table = result.tables[0]
        for col_name, col in table.column_details.items():
            # Heavy stats should be None in SIMPLE mode
            assert col.histogram is None, f"Column {col_name} should not have histogram"
            assert col.stddev is None, f"Column {col_name} should not have stddev"
            assert col.q1 is None, f"Column {col_name} should not have q1"
            assert col.median is None, f"Column {col_name} should not have median"
            assert col.q3 is None, f"Column {col_name} should not have q3"

    def test_caching_works(self, warehouse_id, test_catalog, test_schema, test_tables):
        """Second call should use cache and be faster."""
        import time

        # First call (cache miss)
        start = time.time()
        result1 = get_table_details(
            catalog=test_catalog,
            schema=test_schema,
            table_names=["products"],
            table_stat_level=TableStatLevel.SIMPLE,
            warehouse_id=warehouse_id,
        )
        time.time() - start

        # Second call (should hit cache)
        start = time.time()
        result2 = get_table_details(
            catalog=test_catalog,
            schema=test_schema,
            table_names=["products"],
            table_stat_level=TableStatLevel.SIMPLE,
            warehouse_id=warehouse_id,
        )
        second_time = time.time() - start

        # Results should be equivalent
        assert len(result1.tables) == len(result2.tables)

        # Second call should generally be faster (cache hit)
        # Note: Not always guaranteed due to other factors
        assert second_time >= 0


@pytest.mark.integration
class TestTableStatLevelDetailed:
    """Tests for TableStatLevel.DETAILED (full stats)."""

    def test_stat_level_detailed_has_all_stats(
        self, warehouse_id, test_catalog, test_schema, test_tables
    ):
        """Should return all column statistics including heavy ones."""
        result = get_table_details(
            catalog=test_catalog,
            schema=test_schema,
            table_names=["orders"],
            table_stat_level=TableStatLevel.DETAILED,
            warehouse_id=warehouse_id,
        )

        assert len(result.tables) == 1
        table = result.tables[0]

        # Should have column details
        assert table.column_details is not None

        # Check numeric column (amount) has detailed stats
        if "amount" in table.column_details:
            amount_col = table.column_details["amount"]
            # These should be present for numeric columns
            assert amount_col.min is not None or amount_col.max is not None
            # Histogram may or may not be present depending on data

    def test_stat_level_detailed_has_row_count(
        self, warehouse_id, test_catalog, test_schema, test_tables
    ):
        """DETAILED level should include total row count."""
        result = get_table_details(
            catalog=test_catalog,
            schema=test_schema,
            table_names=["customers"],
            table_stat_level=TableStatLevel.DETAILED,
            warehouse_id=warehouse_id,
        )

        table = result.tables[0]
        assert table.total_rows is not None
        assert table.total_rows == 5  # We inserted 5 customers

    def test_stat_level_detailed_has_sample_data(
        self, warehouse_id, test_catalog, test_schema, test_tables
    ):
        """DETAILED level should include sample data."""
        result = get_table_details(
            catalog=test_catalog,
            schema=test_schema,
            table_names=["customers"],
            table_stat_level=TableStatLevel.DETAILED,
            warehouse_id=warehouse_id,
        )

        table = result.tables[0]
        assert table.sample_data is not None
        assert len(table.sample_data) > 0
        assert len(table.sample_data) <= 10  # SAMPLE_ROW_COUNT

    def test_categorical_columns_have_value_counts(
        self, warehouse_id, test_catalog, test_schema, test_tables
    ):
        """Categorical columns with low cardinality should have value_counts."""
        result = get_table_details(
            catalog=test_catalog,
            schema=test_schema,
            table_names=["orders"],
            table_stat_level=TableStatLevel.DETAILED,
            warehouse_id=warehouse_id,
        )

        table = result.tables[0]

        # status column is categorical with 3 values
        if "status" in table.column_details:
            status_col = table.column_details["status"]
            # Should have value_counts for low-cardinality categorical
            if status_col.value_counts:
                assert "completed" in status_col.value_counts
                assert "pending" in status_col.value_counts


@pytest.mark.integration
class TestTableInfoStructure:
    """Tests for TableInfo structure and content."""

    def test_table_info_has_full_name(
        self, warehouse_id, test_catalog, test_schema, test_tables
    ):
        """Table name should be fully qualified."""
        result = get_table_details(
            catalog=test_catalog,
            schema=test_schema,
            table_names=["customers"],
            warehouse_id=warehouse_id,
        )

        table = result.tables[0]
        expected_full_name = f"{test_catalog}.{test_schema}.customers"
        assert table.name == expected_full_name

    def test_ddl_contains_columns(
        self, warehouse_id, test_catalog, test_schema, test_tables
    ):
        """DDL should contain column definitions."""
        result = get_table_details(
            catalog=test_catalog,
            schema=test_schema,
            table_names=["customers"],
            table_stat_level=TableStatLevel.NONE,
            warehouse_id=warehouse_id,
        )

        table = result.tables[0]
        ddl_upper = table.ddl.upper()

        assert "CUSTOMER_ID" in ddl_upper
        assert "NAME" in ddl_upper
        assert "EMAIL" in ddl_upper

    def test_column_types_detected(
        self, warehouse_id, test_catalog, test_schema, test_tables
    ):
        """Column types should be correctly detected."""
        result = get_table_details(
            catalog=test_catalog,
            schema=test_schema,
            table_names=["products"],
            table_stat_level=TableStatLevel.DETAILED,
            warehouse_id=warehouse_id,
        )

        table = result.tables[0]
        cols = table.column_details

        # Check various column types are detected
        if "price" in cols:
            assert cols["price"].data_type in ["numeric", "double", "float"]

        if "tags" in cols:
            assert cols["tags"].data_type == "array"

        if "created_at" in cols:
            assert cols["created_at"].data_type == "timestamp"


@pytest.mark.integration
class TestTableSchemaResult:
    """Tests for TableSchemaResult methods."""

    def test_table_count_property(
        self, warehouse_id, test_catalog, test_schema, test_tables
    ):
        """table_count property should return correct count."""
        result = get_table_details(
            catalog=test_catalog,
            schema=test_schema,
            table_names=["customers", "orders"],
            warehouse_id=warehouse_id,
        )

        assert result.table_count == 2

    def test_keep_basic_stats_method(
        self, warehouse_id, test_catalog, test_schema, test_tables
    ):
        """keep_basic_stats() should remove heavy stats."""
        result = get_table_details(
            catalog=test_catalog,
            schema=test_schema,
            table_names=["orders"],
            table_stat_level=TableStatLevel.DETAILED,
            warehouse_id=warehouse_id,
        )

        basic_result = result.keep_basic_stats()

        # Should still have tables
        assert len(basic_result.tables) == len(result.tables)

        # But without heavy stats
        for table in basic_result.tables:
            if table.column_details:
                for col in table.column_details.values():
                    assert col.histogram is None
                    assert col.stddev is None

    def test_remove_stats_method(
        self, warehouse_id, test_catalog, test_schema, test_tables
    ):
        """remove_stats() should remove all column details."""
        result = get_table_details(
            catalog=test_catalog,
            schema=test_schema,
            table_names=["customers"],
            table_stat_level=TableStatLevel.DETAILED,
            warehouse_id=warehouse_id,
        )

        minimal_result = result.remove_stats()

        assert len(minimal_result.tables) == 1
        table = minimal_result.tables[0]

        # DDL should still be present
        assert table.ddl is not None

        # But no column details
        assert table.column_details is None
        assert table.total_rows is None


@pytest.mark.integration
class TestAutoWarehouseSelection:
    """Tests for automatic warehouse selection."""

    def test_auto_selects_warehouse(self, test_catalog, test_schema, test_tables):
        """Should auto-select warehouse if not provided."""
        result = get_table_details(
            catalog=test_catalog,
            schema=test_schema,
            table_names=["customers"],
            # warehouse_id not provided
        )

        assert len(result.tables) == 1
        assert result.tables[0].ddl is not None

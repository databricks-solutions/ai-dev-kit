"""
Integration tests for the MCP tag-based table filter.

Two test categories:
  - "offline" tests: validate filtering logic without Databricks connection
  - "online" tests: connect to real Databricks workspace (stg-bi) to verify
    the full flow against actual tagged tables

Run offline tests only (no auth needed):
    PYTHONPATH=... python -m pytest tests/integration/ -v -k "not online"

Run all tests (requires valid stg-bi auth):
    databricks auth login --profile stg-bi
    PYTHONPATH=... python -m pytest tests/integration/ -v
"""

import os
import sys
import time

import pytest

MCP_SERVER_ROOT = os.path.expanduser("~/.ai-dev-kit/repo/databricks-mcp-server")
TOOLS_CORE_ROOT = os.path.expanduser("~/.ai-dev-kit/repo/databricks-tools-core")
sys.path.insert(0, MCP_SERVER_ROOT)
sys.path.insert(0, TOOLS_CORE_ROOT)

os.environ.setdefault("DATABRICKS_CONFIG_PROFILE", "stg-bi")
os.environ["MCP_TABLE_FILTER_TAG_NAME"] = "mcp-ready"
os.environ["MCP_TABLE_FILTER_TAG_VALUE"] = "yes"
os.environ["MCP_TABLE_FILTER_CACHE_TTL"] = "60"

from databricks_mcp_server.table_filter import TableTagFilter  # noqa: E402

KNOWN_TAGGED_CATALOG = "main"
KNOWN_TAGGED_SCHEMA = "eod"
KNOWN_TAGGED_TABLE = "delta_bronze_analystratings"


# ── Helpers ───────────────────────────────────────────────────────────────

def _make_filter_with_fake_cache(tables):
    """Return a TableTagFilter pre-loaded with a fake allowlist (no Databricks call)."""
    f = TableTagFilter()
    f._cache = {(c.lower(), s.lower(), t.lower()) for c, s, t in tables}
    f._cache_ts = time.time()
    return f


# ── Offline tests (no Databricks connection needed) ───────────────────────

class TestFilterLogicOffline:
    """Pure-logic tests using a fake allowlist."""

    @pytest.fixture()
    def f(self):
        return _make_filter_with_fake_cache([
            ("main", "eod", "delta_bronze_analystratings"),
            ("main", "eod", "delta_bronze_price"),
            ("prod", "finance", "transactions"),
        ])

    def test_is_enabled(self, f: TableTagFilter):
        assert f.is_enabled

    def test_allowed_table_passes(self, f: TableTagFilter):
        assert f.is_table_allowed("main", "eod", "delta_bronze_analystratings")

    def test_blocked_table_rejected(self, f: TableTagFilter):
        assert not f.is_table_allowed("main", "eod", "some_random_table")

    def test_case_insensitive(self, f: TableTagFilter):
        assert f.is_table_allowed("MAIN", "EOD", "Delta_Bronze_AnalystRatings")

    def test_system_tables_always_allowed(self, f: TableTagFilter):
        assert f.is_table_allowed("system", "information_schema", "table_tags")
        assert f.is_table_allowed("system", "information_schema", "columns")
        assert f.is_table_allowed("system", "access", "audit")

    def test_filter_table_list(self, f: TableTagFilter):
        tables = [
            {"name": "delta_bronze_analystratings", "updated_at": None, "comment": None},
            {"name": "delta_bronze_price", "updated_at": None, "comment": None},
            {"name": "some_other_table", "updated_at": None, "comment": None},
        ]
        result = f.filter_table_list(tables, "main", "eod")
        names = [t["name"] for t in result]
        assert "delta_bronze_analystratings" in names
        assert "delta_bronze_price" in names
        assert "some_other_table" not in names

    def test_filter_empty_list(self, f: TableTagFilter):
        assert f.filter_table_list([], "main", "eod") == []


class TestSQLValidationOffline:
    """SQL parsing/validation tests using a fake allowlist."""

    @pytest.fixture()
    def f(self):
        return _make_filter_with_fake_cache([
            ("main", "eod", "delta_bronze_analystratings"),
            ("main", "eod", "delta_bronze_price"),
        ])

    def test_fqn_allowed_table_passes(self, f: TableTagFilter):
        f.validate_sql("SELECT * FROM main.eod.delta_bronze_analystratings")

    def test_fqn_blocked_table_raises(self, f: TableTagFilter):
        with pytest.raises(PermissionError, match="Access denied"):
            f.validate_sql("SELECT * FROM main.eod.unknown_table")

    def test_system_table_always_passes(self, f: TableTagFilter):
        f.validate_sql("SELECT * FROM system.information_schema.table_tags")

    def test_cte_not_blocked(self, f: TableTagFilter):
        sql = (
            "WITH temp AS (SELECT * FROM main.eod.delta_bronze_analystratings) "
            "SELECT * FROM temp"
        )
        f.validate_sql(sql)

    def test_unqualified_with_context_allowed(self, f: TableTagFilter):
        f.validate_sql(
            "SELECT * FROM delta_bronze_analystratings",
            catalog_context="main",
            schema_context="eod",
        )

    def test_unqualified_with_context_blocked(self, f: TableTagFilter):
        with pytest.raises(PermissionError, match="Access denied"):
            f.validate_sql(
                "SELECT * FROM unknown_table",
                catalog_context="main",
                schema_context="eod",
            )

    def test_join_one_blocked(self, f: TableTagFilter):
        with pytest.raises(PermissionError, match="Access denied"):
            f.validate_sql(
                "SELECT a.* FROM main.eod.delta_bronze_analystratings a "
                "JOIN main.eod.nonexistent b ON a.id = b.id"
            )

    def test_join_both_allowed(self, f: TableTagFilter):
        f.validate_sql(
            "SELECT a.* FROM main.eod.delta_bronze_analystratings a "
            "JOIN main.eod.delta_bronze_price b ON a.ticker = b.ticker"
        )

    def test_insert_blocked_table(self, f: TableTagFilter):
        with pytest.raises(PermissionError, match="Access denied"):
            f.validate_sql("INSERT INTO main.eod.secret_table SELECT 1")

    def test_show_tables_no_refs_passes(self, f: TableTagFilter):
        f.validate_sql("SHOW TABLES IN main.eod")

    def test_use_catalog_passes(self, f: TableTagFilter):
        f.validate_sql("USE CATALOG main")

    def test_multi_statement_one_blocked(self, f: TableTagFilter):
        sql = (
            "SELECT * FROM main.eod.delta_bronze_analystratings; "
            "SELECT * FROM main.eod.blocked_table"
        )
        with pytest.raises(PermissionError, match="Access denied"):
            f.validate_sql(sql)


class TestShowTablesFilteringOffline:
    """Test that SHOW TABLES output is filtered to only allowed tables."""

    @pytest.fixture()
    def f(self):
        return _make_filter_with_fake_cache([
            ("main", "eod", "delta_bronze_analystratings"),
            ("main", "eod", "delta_bronze_price"),
        ])

    def test_show_tables_filters_output(self, f: TableTagFilter):
        rows = [
            {"tableName": "delta_bronze_analystratings", "isTemporary": False},
            {"tableName": "delta_bronze_price", "isTemporary": False},
            {"tableName": "delta_bronze_dividends", "isTemporary": False},
            {"tableName": "delta_bronze_earnings", "isTemporary": False},
        ]
        filtered = f.filter_show_results("SHOW TABLES IN main.eod", rows)
        names = [r["tableName"] for r in filtered]
        assert names == ["delta_bronze_analystratings", "delta_bronze_price"]

    def test_show_tables_case_insensitive(self, f: TableTagFilter):
        rows = [
            {"tableName": "Delta_Bronze_AnalystRatings", "isTemporary": False},
        ]
        filtered = f.filter_show_results("SHOW TABLES IN main.eod", rows)
        assert len(filtered) == 1

    def test_non_show_query_not_filtered(self, f: TableTagFilter):
        rows = [{"col1": "value1"}, {"col1": "value2"}]
        filtered = f.filter_show_results("SELECT * FROM main.eod.some_table", rows)
        assert filtered == rows

    def test_show_tables_from_syntax(self, f: TableTagFilter):
        rows = [
            {"tableName": "delta_bronze_analystratings", "isTemporary": False},
            {"tableName": "secret_table", "isTemporary": False},
        ]
        filtered = f.filter_show_results("SHOW TABLES FROM main.eod", rows)
        names = [r["tableName"] for r in filtered]
        assert names == ["delta_bronze_analystratings"]

    def test_show_views_also_filtered(self, f: TableTagFilter):
        rows = [
            {"viewName": "delta_bronze_analystratings", "isTemporary": False},
            {"viewName": "secret_view", "isTemporary": False},
        ]
        filtered = f.filter_show_results("SHOW VIEWS IN main.eod", rows)
        assert len(filtered) == 1


class TestCacheBehaviorOffline:
    """Cache logic tests without Databricks connection."""

    def test_cache_hit(self):
        f = _make_filter_with_fake_cache([("main", "eod", "t1")])
        result1 = f.get_allowed_tables()
        result2 = f.get_allowed_tables()
        assert result1 is result2

    def test_cache_expiry(self):
        f = _make_filter_with_fake_cache([("main", "eod", "t1")])
        f.cache_ttl = 0  # expire immediately
        f._cache_ts = time.time() - 1
        assert not f._is_cache_valid()


class TestFilterDisabled:
    """Verify behavior when filtering env vars are not set."""

    def test_disabled_filter_allows_everything(self):
        saved = os.environ.pop("MCP_TABLE_FILTER_TAG_NAME", None)
        try:
            disabled_filter = TableTagFilter()
            assert not disabled_filter.is_enabled
            assert disabled_filter.is_table_allowed("any", "catalog", "table")
            disabled_filter.validate_sql("SELECT * FROM anything.goes.here")
            assert disabled_filter.filter_table_list(
                [{"name": "foo"}], "c", "s"
            ) == [{"name": "foo"}]
        finally:
            if saved:
                os.environ["MCP_TABLE_FILTER_TAG_NAME"] = saved


# ── Online tests (require valid Databricks auth) ─────────────────────────

@pytest.fixture(scope="module")
def online_filter() -> TableTagFilter:
    """Create a filter that queries real Databricks."""
    return TableTagFilter()


@pytest.fixture(scope="module")
def online_allowed_tables(online_filter: TableTagFilter):
    return online_filter.get_allowed_tables()


@pytest.mark.online
class TestGetAllowedTablesOnline:

    def test_returns_nonempty_set(self, online_allowed_tables):
        assert len(online_allowed_tables) > 0

    def test_known_table_is_allowed(self, online_allowed_tables):
        key = (
            KNOWN_TAGGED_CATALOG.lower(),
            KNOWN_TAGGED_SCHEMA.lower(),
            KNOWN_TAGGED_TABLE.lower(),
        )
        assert key in online_allowed_tables, (
            f"Expected {KNOWN_TAGGED_TABLE} in allowed tables. Got: {online_allowed_tables}"
        )

    def test_tuples_are_lowercase(self, online_allowed_tables):
        for cat, sch, tbl in online_allowed_tables:
            assert cat == cat.lower()
            assert sch == sch.lower()
            assert tbl == tbl.lower()


@pytest.mark.online
class TestFilterOnline:

    def test_filter_real_tables(self, online_filter: TableTagFilter):
        fake_tables = [
            {"name": KNOWN_TAGGED_TABLE, "updated_at": None, "comment": None},
            {"name": "this_table_should_not_exist_xyz", "updated_at": None, "comment": None},
        ]
        filtered = online_filter.filter_table_list(
            fake_tables, KNOWN_TAGGED_CATALOG, KNOWN_TAGGED_SCHEMA
        )
        names = [t["name"] for t in filtered]
        assert KNOWN_TAGGED_TABLE in names
        assert "this_table_should_not_exist_xyz" not in names

    def test_validate_allowed_sql(self, online_filter: TableTagFilter):
        fqn = f"{KNOWN_TAGGED_CATALOG}.{KNOWN_TAGGED_SCHEMA}.{KNOWN_TAGGED_TABLE}"
        online_filter.validate_sql(f"SELECT * FROM {fqn}")

    def test_validate_blocked_sql(self, online_filter: TableTagFilter):
        with pytest.raises(PermissionError, match="Access denied"):
            online_filter.validate_sql(
                "SELECT * FROM main.eod.this_table_should_not_exist_xyz"
            )


@pytest.mark.online
class TestCacheOnline:

    def test_second_call_uses_cache(self, online_filter: TableTagFilter):
        online_filter.refresh_cache()

        start = time.time()
        online_filter.get_allowed_tables()
        first_duration = time.time() - start

        start = time.time()
        online_filter.get_allowed_tables()
        second_duration = time.time() - start

        assert second_duration < first_duration or second_duration < 0.01

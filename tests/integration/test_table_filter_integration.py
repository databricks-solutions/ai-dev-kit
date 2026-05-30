"""
Integration tests for the MCP tag-based table filter.

Two test categories:
  * **offline** — pure logic, uses an in-memory fake repository (no SDK calls).
  * **online**  — connects to a real Databricks workspace; marked with
    ``@pytest.mark.online`` so it can be skipped via ``-m "not online"``.

Run offline only::

    uv run pytest tests/integration/ -m "not online"

Run everything (requires valid Databricks auth)::

    uv run pytest tests/integration/
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterable

import pytest

from mcp_databricks_filtering.config import FilterConfig
from mcp_databricks_filtering.repository import TableKey
from mcp_databricks_filtering.table_filter import TableTagFilter

# ── Test config ───────────────────────────────────────────────────────────

KNOWN_TAGGED_CATALOG = os.environ.get("TEST_TAGGED_CATALOG", "main")
KNOWN_TAGGED_SCHEMA = os.environ.get("TEST_TAGGED_SCHEMA", "eod")
KNOWN_TAGGED_TABLE = os.environ.get("TEST_TAGGED_TABLE", "delta_bronze_analystratings")

DEFAULT_CONFIG = FilterConfig(
    tag_name="mcp-ready",
    tag_value="yes",
    cache_ttl_seconds=60,
)


# ── Test helpers ──────────────────────────────────────────────────────────


class FakeRepository:
    """In-memory repository for offline tests."""

    def __init__(self, tables: Iterable[TableKey]):
        self._tables = frozenset((c.lower(), s.lower(), t.lower()) for c, s, t in tables)
        self.fetch_count = 0

    def fetch_allowed(self, tag_name: str, tag_value: str) -> frozenset[TableKey]:
        self.fetch_count += 1
        return self._tables


def _make_filter(tables: Iterable[TableKey], **config_overrides) -> TableTagFilter:
    config = FilterConfig(
        tag_name=config_overrides.pop("tag_name", "mcp-ready"),
        tag_value=config_overrides.pop("tag_value", "yes"),
        cache_ttl_seconds=config_overrides.pop("cache_ttl_seconds", 60),
        **config_overrides,
    )
    return TableTagFilter(config=config, repository=FakeRepository(tables))


# ── Offline tests ─────────────────────────────────────────────────────────


class TestFilterLogicOffline:
    """Pure-logic tests using the fake repository."""

    @pytest.fixture()
    def f(self):
        return _make_filter([
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
            {"name": "delta_bronze_analystratings"},
            {"name": "delta_bronze_price"},
            {"name": "some_other_table"},
        ]
        result = f.filter_table_list(tables, "main", "eod")
        names = [t["name"] for t in result]
        assert names == ["delta_bronze_analystratings", "delta_bronze_price"]

    def test_filter_empty_list(self, f: TableTagFilter):
        assert f.filter_table_list([], "main", "eod") == []

    def test_get_allowed_tables_returns_frozenset(self, f: TableTagFilter):
        result = f.get_allowed_tables()
        assert isinstance(result, frozenset)
        with pytest.raises(AttributeError):
            result.add(("a", "b", "c"))  # type: ignore[attr-defined]


class TestSQLValidationOffline:
    """SQL parsing/validation tests."""

    @pytest.fixture()
    def f(self):
        return _make_filter([
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

    def test_unparseable_sql_fails_closed_by_default(self, f: TableTagFilter):
        with pytest.raises(PermissionError, match="could not be parsed"):
            f.validate_sql("THIS IS NOT VALID SQL @@@@ ;;;;")

    def test_unparseable_sql_passes_when_fail_open(self):
        f = _make_filter(
            [("main", "eod", "x")],
            fail_closed=False,
        )
        f.validate_sql("THIS IS NOT VALID SQL @@@@ ;;;;")


class TestShowTablesFilteringOffline:
    """Test that SHOW TABLES output is filtered to only allowed tables."""

    @pytest.fixture()
    def f(self):
        return _make_filter([
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
        rows = [{"tableName": "Delta_Bronze_AnalystRatings", "isTemporary": False}]
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
    """Cache logic tests using the fake repository's call counter."""

    def test_cache_hit_avoids_repository_call(self):
        repo = FakeRepository([("main", "eod", "t1")])
        f = TableTagFilter(config=DEFAULT_CONFIG, repository=repo)
        f.get_allowed_tables()
        f.get_allowed_tables()
        f.get_allowed_tables()
        assert repo.fetch_count == 1

    def test_refresh_cache_re_fetches(self):
        repo = FakeRepository([("main", "eod", "t1")])
        f = TableTagFilter(config=DEFAULT_CONFIG, repository=repo)
        f.get_allowed_tables()
        f.refresh_cache()
        assert repo.fetch_count == 2

    def test_cache_expiry_triggers_refetch(self):
        repo = FakeRepository([("main", "eod", "t1")])
        f = TableTagFilter(
            config=FilterConfig(tag_name="mcp-ready", cache_ttl_seconds=0),
            repository=repo,
        )
        f.get_allowed_tables()
        time.sleep(0.01)
        f.get_allowed_tables()
        assert repo.fetch_count == 2


class TestFilterDisabled:
    """Behavior when no tag is configured."""

    def test_disabled_filter_allows_everything(self):
        f = TableTagFilter(config=FilterConfig())
        assert not f.is_enabled
        assert f.is_table_allowed("any", "catalog", "table")
        f.validate_sql("SELECT * FROM anything.goes.here")
        assert f.filter_table_list([{"name": "foo"}], "c", "s") == [{"name": "foo"}]


class TestConfigValidation:
    """FilterConfig should reject obviously bad input."""

    def test_invalid_tag_name_rejected(self):
        with pytest.raises(ValueError, match="Invalid tag_name"):
            FilterConfig(tag_name="bad name with spaces; DROP TABLE x;")

    def test_negative_ttl_rejected(self):
        with pytest.raises(ValueError, match="cache_ttl_seconds"):
            FilterConfig(tag_name="mcp-ready", cache_ttl_seconds=-1)

    def test_invalid_ttl_env_rejected(self):
        with pytest.raises(ValueError, match="must be an integer"):
            FilterConfig.from_env({"MCP_TABLE_FILTER_CACHE_TTL": "not-a-number"})

    def test_from_env_defaults(self):
        config = FilterConfig.from_env({})
        assert config.tag_name == ""
        assert config.cache_ttl_seconds == 300
        assert config.fail_closed is True

    def test_from_env_fail_closed_can_be_disabled(self):
        config = FilterConfig.from_env({"MCP_TABLE_FILTER_FAIL_CLOSED": "false"})
        assert config.fail_closed is False


# ── Online tests ──────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def online_filter() -> TableTagFilter:
    config = FilterConfig.from_env()
    if not config.is_enabled:
        config = FilterConfig(tag_name="mcp-ready", tag_value="yes", cache_ttl_seconds=60)
    return TableTagFilter(config=config)


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
            {"name": KNOWN_TAGGED_TABLE},
            {"name": "this_table_should_not_exist_xyz"},
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
                f"SELECT * FROM {KNOWN_TAGGED_CATALOG}.{KNOWN_TAGGED_SCHEMA}"
                ".this_table_should_not_exist_xyz"
            )

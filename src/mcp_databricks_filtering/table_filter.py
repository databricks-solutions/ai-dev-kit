"""
Tag-based table filtering for the Databricks MCP server.

Restricts table discovery and SQL execution to only tables that have a
specific Unity Catalog tag (e.g. ``mcp-ready=yes``). Driven by environment
variables, but the underlying primitives are also usable directly via
:class:`FilterConfig` and :class:`AllowlistRepository` injection.

Design notes
------------
- ``TableTagFilter`` is the orchestrator: cache + parse + decide.
- The actual SDK call lives in :mod:`.repository` so unit tests can mock it.
- SQL parsing lives in :mod:`.sql_parser` and uses sqlglot **scope** traversal
  to correctly distinguish real tables from CTEs.
- Defaults are *fail-closed*: unparseable SQL is rejected, not silently allowed.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from mcp_databricks_filtering.config import FilterConfig
from mcp_databricks_filtering.repository import (
    AllowlistRepository,
    TableKey,
    UnityCatalogTagsRepository,
)
from mcp_databricks_filtering.sql_parser import (
    SQLParseFailure,
    extract_real_tables,
    is_show_query,
    parse_show_target,
)

logger = logging.getLogger(__name__)

SYSTEM_CATALOGS = frozenset({"system"})
SYSTEM_SCHEMAS = frozenset({"information_schema"})

__all__ = ["TableTagFilter", "get_table_filter", "reset_singleton"]


class TableTagFilter:
    """Filters MCP table access based on Unity Catalog tags.

    The class is safe to share across threads. Construction is cheap; the
    expensive call (fetching the allowlist) is lazy and cached for
    ``config.cache_ttl_seconds``.

    Args:
        config: configuration; if ``None``, built from env vars via
            :meth:`FilterConfig.from_env`.
        repository: implementation that returns the allowlist; if ``None``,
            uses :class:`UnityCatalogTagsRepository` against the workspace
            referenced by the ambient Databricks SDK config.
    """

    def __init__(
        self,
        config: FilterConfig | None = None,
        repository: AllowlistRepository | None = None,
    ):
        self._config = config or FilterConfig.from_env()
        self._repository = repository or UnityCatalogTagsRepository(
            warehouse_id=self._config.warehouse_id
        )

        self._cache: frozenset[TableKey] | None = None
        self._cache_ts: float = 0.0
        self._cache_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def config(self) -> FilterConfig:
        return self._config

    @property
    def is_enabled(self) -> bool:
        return self._config.is_enabled

    @property
    def tag_name(self) -> str:
        return self._config.tag_name

    @property
    def tag_value(self) -> str:
        return self._config.tag_value

    @property
    def cache_ttl(self) -> int:
        return self._config.cache_ttl_seconds

    def get_allowed_tables(self) -> frozenset[TableKey]:
        """Return the set of allowed (catalog, schema, table) triples.

        The result is a *frozen* set, so callers cannot accidentally mutate
        the cache. Cached for ``config.cache_ttl_seconds``.
        """
        if not self.is_enabled:
            return frozenset()

        # Single critical section: avoids the thundering-herd problem where
        # many threads simultaneously trigger a slow Databricks query when
        # the cache expires. The trade-off is briefly serializing cache
        # misses, which is acceptable for an admin-tier query.
        with self._cache_lock:
            if self._is_cache_valid_locked():
                return self._cache  # type: ignore[return-value]

            allowed = self._repository.fetch_allowed(
                tag_name=self._config.tag_name,
                tag_value=self._config.tag_value,
            )
            self._cache = allowed
            self._cache_ts = time.time()
            return allowed

    def refresh_cache(self) -> frozenset[TableKey]:
        """Drop the cache and re-fetch the allowlist."""
        with self._cache_lock:
            self._cache = None
            self._cache_ts = 0.0
        return self.get_allowed_tables()

    def is_table_allowed(
        self,
        catalog: str | None,
        schema: str | None,
        table: str,
    ) -> bool:
        if not self.is_enabled:
            return True
        if _is_system_ref(catalog, schema, table):
            return True
        return _match_table(catalog, schema, table, self.get_allowed_tables())

    def filter_table_list(
        self,
        tables: list[dict[str, Any]],
        catalog: str,
        schema: str,
    ) -> list[dict[str, Any]]:
        """Filter table-info dicts to only those in the allowlist."""
        if not self.is_enabled:
            return tables

        allowed = self.get_allowed_tables()
        cat_lower = catalog.lower()
        sch_lower = schema.lower()
        return [
            t for t in tables
            if (cat_lower, sch_lower, str(t.get("name", "")).lower()) in allowed
        ]

    def validate_sql(
        self,
        sql_query: str,
        catalog_context: str | None = None,
        schema_context: str | None = None,
    ) -> None:
        """Raise ``PermissionError`` if ``sql_query`` references blocked tables.

        With ``fail_closed=True`` (default), unparseable SQL is rejected.
        With ``fail_closed=False``, it is allowed (use only in trusted contexts).
        """
        if not self.is_enabled:
            return

        try:
            refs = extract_real_tables(sql_query)
        except SQLParseFailure as exc:
            if self._config.fail_closed:
                raise PermissionError(
                    "Access denied: SQL could not be parsed for safety validation. "
                    f"Reason: {exc}"
                ) from exc
            return

        if not refs:
            return

        allowed = self.get_allowed_tables()
        blocked: list[str] = []

        for ref in refs:
            resolved_cat = ref.catalog or catalog_context
            resolved_sch = ref.schema or schema_context

            if _is_system_ref(resolved_cat, resolved_sch, ref.table):
                continue
            if _match_table(resolved_cat, resolved_sch, ref.table, allowed):
                continue

            fqn = ".".join(filter(None, [resolved_cat, resolved_sch, ref.table]))
            blocked.append(fqn)

        if blocked:
            tag_repr = (
                f"{self._config.tag_name}={self._config.tag_value}"
                if self._config.tag_value
                else self._config.tag_name
            )
            raise PermissionError(
                f"Access denied. The following tables are not tagged with "
                f"'{tag_repr}': {', '.join(blocked)}. "
                "Only tables with this tag are accessible via this MCP server."
            )

    def filter_show_results(
        self,
        sql_query: str,
        rows: list[dict[str, Any]],
        catalog_context: str | None = None,
        schema_context: str | None = None,
    ) -> list[dict[str, Any]]:
        """Filter the output of SHOW TABLES / SHOW VIEWS to allowed tables only."""
        if not self.is_enabled or not rows or not is_show_query(sql_query):
            return rows

        allowed = self.get_allowed_tables()
        show_cat, show_sch = parse_show_target(sql_query)
        cat = (show_cat or catalog_context or "").lower()
        sch = (show_sch or schema_context or "").lower()

        filtered: list[dict[str, Any]] = []
        for row in rows:
            table_name = (
                row.get("tableName")
                or row.get("table_name")
                or row.get("viewName")
                or row.get("view_name")
                or ""
            ).lower()
            if not table_name:
                filtered.append(row)
                continue
            if (cat, sch, table_name) in allowed:
                filtered.append(row)
        return filtered

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _is_cache_valid_locked(self) -> bool:
        return (
            self._cache is not None
            and (time.time() - self._cache_ts) < self._config.cache_ttl_seconds
        )


# ----------------------------------------------------------------------
# Module-level helpers
# ----------------------------------------------------------------------


def _is_system_ref(
    catalog: str | None, schema: str | None, table: str
) -> bool:
    if catalog and catalog.lower() in SYSTEM_CATALOGS:
        return True
    if schema and schema.lower() in SYSTEM_SCHEMAS:
        return True
    return table.lower().startswith("information_schema")


def _match_table(
    catalog: str | None,
    schema: str | None,
    table: str,
    allowed: frozenset[TableKey],
) -> bool:
    tbl_lower = table.lower()
    if catalog and schema:
        return (catalog.lower(), schema.lower(), tbl_lower) in allowed

    for a_cat, a_sch, a_tbl in allowed:
        if a_tbl != tbl_lower:
            continue
        if schema and a_sch != schema.lower():
            continue
        if catalog and a_cat != catalog.lower():
            continue
        return True
    return False


# ----------------------------------------------------------------------
# Singleton (module-level, lazy, thread-safe via double-checked locking)
# ----------------------------------------------------------------------

_singleton: TableTagFilter | None = None
_singleton_lock = threading.Lock()


def get_table_filter() -> TableTagFilter:
    """Return the process-wide :class:`TableTagFilter` singleton.

    The singleton is created lazily from environment variables. Tests that
    need a different config should call :func:`reset_singleton` first.
    """
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = TableTagFilter()
    return _singleton


def reset_singleton() -> None:
    """Drop the cached singleton — primarily for tests."""
    global _singleton
    with _singleton_lock:
        _singleton = None

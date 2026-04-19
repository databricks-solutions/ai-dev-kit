"""
Tag-based table filtering for the Databricks MCP server.

Restricts table discovery and SQL execution to only tables that have
a specific UC tag (e.g., mcp-ready=yes). Configured via environment variables:

  MCP_TABLE_FILTER_TAG_NAME   - tag key to filter on (e.g. "mcp-ready")
  MCP_TABLE_FILTER_TAG_VALUE  - required tag value (e.g. "yes")
  MCP_TABLE_FILTER_CACHE_TTL  - cache lifetime in seconds (default 300)

When MCP_TABLE_FILTER_TAG_NAME is not set, filtering is disabled.
"""

import logging
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple

import sqlglot
from sqlglot import exp

logger = logging.getLogger(__name__)

SYSTEM_CATALOGS = {"system"}
SYSTEM_SCHEMAS = {"information_schema"}


class TableTagFilter:
    """Filters MCP table access based on Unity Catalog tags."""

    def __init__(self):
        self.tag_name = os.environ.get("MCP_TABLE_FILTER_TAG_NAME", "").strip()
        self.tag_value = os.environ.get("MCP_TABLE_FILTER_TAG_VALUE", "").strip()
        self.cache_ttl = int(os.environ.get("MCP_TABLE_FILTER_CACHE_TTL", "300"))

        self._cache: Optional[Set[Tuple[str, str, str]]] = None
        self._cache_ts: float = 0.0
        self._cache_lock = threading.Lock()

    @property
    def is_enabled(self) -> bool:
        return bool(self.tag_name)

    def _is_cache_valid(self) -> bool:
        return self._cache is not None and (time.time() - self._cache_ts) < self.cache_ttl

    def get_allowed_tables(self, warehouse_id: Optional[str] = None) -> Set[Tuple[str, str, str]]:
        """Return the set of (catalog, schema, table) tuples that pass the tag filter.

        Results are cached for ``cache_ttl`` seconds.
        """
        if not self.is_enabled:
            return set()

        with self._cache_lock:
            if self._is_cache_valid():
                return self._cache  # type: ignore[return-value]

        allowed = self._query_allowed_tables(warehouse_id)

        with self._cache_lock:
            self._cache = allowed
            self._cache_ts = time.time()

        return allowed

    def _query_allowed_tables(self, warehouse_id: Optional[str] = None) -> Set[Tuple[str, str, str]]:
        from databricks.sdk import WorkspaceClient

        w = WorkspaceClient()

        conditions = [f"tag_name = '{self.tag_name}'"]
        if self.tag_value:
            conditions.append(f"tag_value = '{self.tag_value}'")
        where = " AND ".join(conditions)

        sql = (
            "SELECT catalog_name, schema_name, table_name "
            f"FROM system.information_schema.table_tags WHERE {where}"
        )
        logger.info("Querying allowed tables: %s", sql)

        result: Set[Tuple[str, str, str]] = set()
        with w.statement_execution.execute_and_wait(
            warehouse_id=warehouse_id or self._get_warehouse_id(w),
            statement=sql,
        ) as response:
            if response.result and response.result.data_array:
                for row in response.result.data_array:
                    cat = (row[0] or "").lower()
                    sch = (row[1] or "").lower()
                    tbl = (row[2] or "").lower()
                    if cat and sch and tbl:
                        result.add((cat, sch, tbl))

        logger.info("Allowed tables (%d): %s", len(result), result)
        return result

    @staticmethod
    def _get_warehouse_id(w) -> str:
        """Find the first available SQL warehouse."""
        warehouses = list(w.warehouses.list())
        if not warehouses:
            raise RuntimeError("No SQL warehouses available")
        running = [wh for wh in warehouses if wh.state and wh.state.value == "RUNNING"]
        chosen = running[0] if running else warehouses[0]
        return chosen.id

    def refresh_cache(self, warehouse_id: Optional[str] = None) -> Set[Tuple[str, str, str]]:
        """Force-refresh the cache and return the new allowlist."""
        with self._cache_lock:
            self._cache = None
            self._cache_ts = 0.0
        return self.get_allowed_tables(warehouse_id)

    def is_table_allowed(
        self,
        catalog: Optional[str],
        schema: Optional[str],
        table: str,
        warehouse_id: Optional[str] = None,
    ) -> bool:
        if not self.is_enabled:
            return True

        if self._is_system_ref(catalog, schema, table):
            return True

        allowed = self.get_allowed_tables(warehouse_id)
        return self._match_table(catalog, schema, table, allowed)

    def filter_table_list(
        self,
        tables: List[Dict[str, Any]],
        catalog: str,
        schema: str,
        warehouse_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Filter a list of table-info dicts to only those in the allowlist."""
        if not self.is_enabled:
            return tables

        allowed = self.get_allowed_tables(warehouse_id)
        cat_lower = catalog.lower()
        sch_lower = schema.lower()
        return [
            t for t in tables
            if (cat_lower, sch_lower, t["name"].lower()) in allowed
        ]

    def validate_sql(
        self,
        sql_query: str,
        catalog_context: Optional[str] = None,
        schema_context: Optional[str] = None,
        warehouse_id: Optional[str] = None,
    ) -> None:
        """Raise ``PermissionError`` if the SQL references any non-allowed table."""
        if not self.is_enabled:
            return

        table_refs = self._extract_table_refs(sql_query)
        if not table_refs:
            return

        allowed = self.get_allowed_tables(warehouse_id)
        cte_names = self._extract_cte_names(sql_query)
        blocked: List[str] = []

        for cat, sch, tbl in table_refs:
            if tbl.lower() in cte_names:
                continue

            resolved_cat = cat or catalog_context
            resolved_sch = sch or schema_context

            if self._is_system_ref(resolved_cat, resolved_sch, tbl):
                continue

            if not self._match_table(resolved_cat, resolved_sch, tbl, allowed):
                fqn = ".".join(filter(None, [resolved_cat, resolved_sch, tbl]))
                blocked.append(fqn)

        if blocked:
            raise PermissionError(
                f"Access denied. The following tables are not tagged with "
                f"'{self.tag_name}={self.tag_value}': {', '.join(blocked)}. "
                f"Only tables with this tag are accessible via this MCP server."
            )

    def filter_show_results(
        self,
        sql_query: str,
        rows: List[Dict[str, Any]],
        catalog_context: Optional[str] = None,
        schema_context: Optional[str] = None,
        warehouse_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Filter the output of SHOW TABLES / SHOW VIEWS to only allowed tables."""
        if not self.is_enabled or not rows:
            return rows

        if not self._is_show_tables_query(sql_query):
            return rows

        allowed = self.get_allowed_tables(warehouse_id)

        show_cat, show_sch = self._parse_show_target(sql_query)
        cat = (show_cat or catalog_context or "").lower()
        sch = (show_sch or schema_context or "").lower()

        filtered = []
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
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_show_tables_query(sql_query: str) -> bool:
        normalized = sql_query.strip().upper()
        return any(
            normalized.startswith(prefix)
            for prefix in ("SHOW TABLES", "SHOW VIEWS", "SHOW TBLPROPERTIES")
        )

    @staticmethod
    def _parse_show_target(sql_query: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract catalog and schema from 'SHOW TABLES IN catalog.schema'."""
        match = re.search(r"(?:IN|FROM)\s+(\S+)", sql_query, re.IGNORECASE)
        if not match:
            return None, None
        target = match.group(1).strip("`\"'")
        parts = target.split(".")
        if len(parts) >= 2:
            return parts[0], parts[1]
        return None, parts[0]

    @staticmethod
    def _is_system_ref(
        catalog: Optional[str], schema: Optional[str], table: str
    ) -> bool:
        if catalog and catalog.lower() in SYSTEM_CATALOGS:
            return True
        if schema and schema.lower() in SYSTEM_SCHEMAS:
            return True
        if table.lower().startswith("information_schema"):
            return True
        return False

    @staticmethod
    def _match_table(
        catalog: Optional[str],
        schema: Optional[str],
        table: str,
        allowed: Set[Tuple[str, str, str]],
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

    @staticmethod
    def _is_data_statement(stmt) -> bool:
        """Return True if the statement is a DML/query that references real tables."""
        _SKIP_TYPES = (exp.Use, exp.Set, exp.Command, exp.Show)
        return not isinstance(stmt, _SKIP_TYPES)

    @staticmethod
    def _extract_table_refs(sql_query: str) -> List[Tuple[Optional[str], Optional[str], str]]:
        refs: List[Tuple[Optional[str], Optional[str], str]] = []
        try:
            for stmt in sqlglot.parse(sql_query, dialect="databricks"):
                if stmt is None:
                    continue
                if not TableTagFilter._is_data_statement(stmt):
                    continue
                for tbl in stmt.find_all(exp.Table):
                    name = tbl.name
                    if not name:
                        continue
                    catalog = tbl.catalog or None
                    schema = tbl.db or None
                    refs.append((catalog, schema, name))
        except sqlglot.errors.ParseError:
            logger.warning("Failed to parse SQL for table refs: %s", sql_query[:200])
        return refs

    @staticmethod
    def _extract_cte_names(sql_query: str) -> Set[str]:
        cte_names: Set[str] = set()
        try:
            for stmt in sqlglot.parse(sql_query, dialect="databricks"):
                if stmt is None:
                    continue
                for cte in stmt.find_all(exp.CTE):
                    alias = cte.alias
                    if alias:
                        cte_names.add(alias.lower())
        except sqlglot.errors.ParseError:
            pass
        return cte_names


_filter: Optional[TableTagFilter] = None
_filter_lock = threading.Lock()


def get_table_filter() -> TableTagFilter:
    """Return the global TableTagFilter singleton."""
    global _filter
    if _filter is None:
        with _filter_lock:
            if _filter is None:
                _filter = TableTagFilter()
    return _filter

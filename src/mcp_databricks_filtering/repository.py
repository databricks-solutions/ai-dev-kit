"""Repository for fetching the table allowlist from Unity Catalog.

This module isolates all Databricks SDK calls behind a small protocol so
the filter logic can be unit-tested without a live workspace.
"""

from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)

TableKey = tuple[str, str, str]


class AllowlistRepository(Protocol):
    """Returns the set of (catalog, schema, table) triples that are allowed."""

    def fetch_allowed(self, tag_name: str, tag_value: str) -> frozenset[TableKey]: ...


class UnityCatalogTagsRepository:
    """Reads the allowlist from ``system.information_schema.table_tags``.

    Uses parameterized SQL via the Databricks Statement Execution API to
    prevent any SQL-injection risk from environment-supplied tag values.
    """

    def __init__(self, warehouse_id: str | None = None, wait_timeout: str = "30s"):
        self._warehouse_id = warehouse_id
        self._wait_timeout = wait_timeout

    def fetch_allowed(self, tag_name: str, tag_value: str) -> frozenset[TableKey]:
        from databricks.sdk import WorkspaceClient
        from databricks.sdk.service.sql import (
            StatementParameterListItem,
            StatementState,
        )

        w = WorkspaceClient()
        warehouse_id = self._warehouse_id or self._first_running_warehouse_id(w)

        statement = (
            "SELECT catalog_name, schema_name, table_name "
            "FROM system.information_schema.table_tags "
            "WHERE tag_name = :tag_name"
        )
        params = [StatementParameterListItem(name="tag_name", value=tag_name)]
        if tag_value:
            statement += " AND tag_value = :tag_value"
            params.append(StatementParameterListItem(name="tag_value", value=tag_value))

        logger.info("Fetching allowlist (tag=%s, value=%s)", tag_name, tag_value or "*")

        response = w.statement_execution.execute_statement(
            warehouse_id=warehouse_id,
            statement=statement,
            parameters=params,
            wait_timeout=self._wait_timeout,
        )

        if not response.status or response.status.state != StatementState.SUCCEEDED:
            error_msg = (
                response.status.error.message
                if response.status and response.status.error
                else "unknown error"
            )
            raise RuntimeError(f"Allowlist query failed: {error_msg}")

        result: set[TableKey] = set()
        if response.result and response.result.data_array:
            for row in response.result.data_array:
                if len(row) < 3:
                    continue
                cat = (row[0] or "").lower()
                sch = (row[1] or "").lower()
                tbl = (row[2] or "").lower()
                if cat and sch and tbl:
                    result.add((cat, sch, tbl))

        logger.info("Allowlist contains %d tables", len(result))
        return frozenset(result)

    @staticmethod
    def _first_running_warehouse_id(w) -> str:
        """Pick a warehouse: prefer RUNNING, otherwise the first available."""
        warehouses = list(w.warehouses.list())
        if not warehouses:
            raise RuntimeError(
                "No SQL warehouses available. Set MCP_TABLE_FILTER_WAREHOUSE_ID "
                "or create a warehouse."
            )
        for wh in warehouses:
            if wh.state and getattr(wh.state, "value", str(wh.state)) == "RUNNING":
                return wh.id
        return warehouses[0].id

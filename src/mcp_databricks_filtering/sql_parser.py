"""SQL parsing helpers built on top of sqlglot.

Uses sqlglot's *scope* module so we correctly distinguish real tables from
CTE references. See https://github.com/tobymao/sqlglot/blob/main/posts/ast_primer.md
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError
from sqlglot.optimizer.scope import build_scope

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TableRef:
    catalog: str | None
    schema: str | None
    table: str


class SQLParseFailure(Exception):
    """Raised when SQL cannot be parsed (callers decide whether to fail-open or closed)."""


_SHOW_PREFIXES = ("SHOW TABLES", "SHOW VIEWS", "SHOW TBLPROPERTIES")
_SHOW_TARGET_RE = re.compile(r"(?:IN|FROM)\s+(\S+)", re.IGNORECASE)
_SKIP_STMT_TYPES: tuple[type, ...] = (exp.Use, exp.Set, exp.Command, exp.Show)


def is_show_query(sql: str) -> bool:
    """True if the SQL is a SHOW TABLES / SHOW VIEWS / SHOW TBLPROPERTIES."""
    normalized = sql.strip().upper()
    return any(normalized.startswith(prefix) for prefix in _SHOW_PREFIXES)


def parse_show_target(sql: str) -> tuple[str | None, str | None]:
    """Extract (catalog, schema) from `SHOW TABLES IN catalog.schema`."""
    match = _SHOW_TARGET_RE.search(sql)
    if not match:
        return None, None
    target = match.group(1).strip("`\"'").rstrip(";")
    parts = target.split(".")
    if len(parts) >= 2:
        return parts[0], parts[1]
    return None, parts[0]


def extract_real_tables(sql: str, dialect: str = "databricks") -> list[TableRef]:
    """Return real database tables referenced by ``sql``, excluding CTEs.

    Strategy:
      - For each top-level statement, gather *all* CTE names so we can
        exclude them as references.
      - Use scope traversal where applicable (SELECT-shaped queries) to
        find real tables.
      - Always also include DML targets (INSERT / UPDATE / DELETE / MERGE)
        since those live outside the query scope.

    Raises:
        SQLParseFailure: if ``sql`` cannot be parsed by sqlglot.
    """
    try:
        statements = sqlglot.parse(sql, dialect=dialect)
    except ParseError as exc:
        logger.warning("Failed to parse SQL: %.200s — %s", sql, exc)
        raise SQLParseFailure(str(exc)) from exc

    refs: list[TableRef] = []
    for stmt in statements:
        if stmt is None or isinstance(stmt, _SKIP_STMT_TYPES):
            continue

        cte_names = {
            cte.alias.lower()
            for cte in stmt.find_all(exp.CTE)
            if cte.alias
        }

        seen: set[tuple[str | None, str | None, str]] = set()

        root = build_scope(stmt)
        if root is not None:
            for scope in root.traverse():
                for _alias, (_node, source) in scope.selected_sources.items():
                    if isinstance(source, exp.Table):
                        ref = _to_ref(source)
                        key = (ref.catalog, ref.schema, ref.table.lower())
                        if ref.table.lower() not in cte_names and key not in seen:
                            refs.append(ref)
                            seen.add(key)

        for tbl in stmt.find_all(exp.Table):
            if tbl.name.lower() in cte_names:
                continue
            ref = _to_ref(tbl)
            key = (ref.catalog, ref.schema, ref.table.lower())
            if key not in seen:
                refs.append(ref)
                seen.add(key)

    return refs


def _to_ref(tbl: exp.Table) -> TableRef:
    return TableRef(
        catalog=tbl.catalog or None,
        schema=tbl.db or None,
        table=tbl.name,
    )

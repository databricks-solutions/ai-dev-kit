"""
Unity Catalog - Metric View Operations

Functions for creating, altering, describing, dropping, and querying
Unity Catalog metric views via SQL DDL.

Metric views are defined in YAML and executed through the Statement Execution API
since there is no dedicated REST API or Python SDK support for metric views.
"""

import logging
import textwrap
from typing import Any, Dict, List, Optional

from ..sql.sql import execute_sql

logger = logging.getLogger(__name__)


def _build_yaml_block(
    source: str,
    dimensions: List[Dict[str, str]],
    measures: List[Dict[str, str]],
    version: str = "1.1",
    comment: Optional[str] = None,
    filter_expr: Optional[str] = None,
    joins: Optional[List[Dict[str, Any]]] = None,
    materialization: Optional[Dict[str, Any]] = None,
) -> str:
    """Build the YAML definition block for a metric view.

    Args:
        source: Source table, view, or SQL query (three-level namespace).
        dimensions: List of dimension dicts with keys: name, expr, comment (optional).
        measures: List of measure dicts with keys: name, expr, comment (optional).
        version: YAML spec version (default "1.1" for DBR 17.2+).
        comment: Optional description of the metric view.
        filter_expr: Optional SQL boolean filter expression applied to all queries.
        joins: Optional list of join dicts with keys: name, source, on/using, joins (nested).
        materialization: Optional materialization config dict.

    Returns:
        The YAML string to embed in the SQL $$ block.
    """
    lines = [f"version: {version}"]

    if comment:
        lines.append(f'comment: "{comment}"')

    lines.append(f"source: {source}")

    if filter_expr:
        lines.append(f"filter: {filter_expr}")

    # Joins
    if joins:
        lines.append("joins:")
        _render_joins(lines, joins, indent=2)

    # Dimensions
    lines.append("dimensions:")
    for dim in dimensions:
        lines.append(f"  - name: {dim['name']}")
        lines.append(f"    expr: {dim['expr']}")
        if dim.get("comment"):
            lines.append(f'    comment: "{dim["comment"]}"')

    # Measures
    lines.append("measures:")
    for measure in measures:
        lines.append(f"  - name: {measure['name']}")
        lines.append(f"    expr: {measure['expr']}")
        if measure.get("comment"):
            lines.append(f'    comment: "{measure["comment"]}"')

    # Materialization
    if materialization:
        lines.append("materialization:")
        if materialization.get("schedule"):
            lines.append(f"  schedule: {materialization['schedule']}")
        if materialization.get("mode"):
            lines.append(f"  mode: {materialization['mode']}")
        if materialization.get("materialized_views"):
            lines.append("  materialized_views:")
            for mv in materialization["materialized_views"]:
                lines.append(f"    - name: {mv['name']}")
                lines.append(f"      type: {mv['type']}")
                if mv.get("dimensions"):
                    lines.append("      dimensions:")
                    for d in mv["dimensions"]:
                        lines.append(f"        - {d}")
                if mv.get("measures"):
                    lines.append("      measures:")
                    for m in mv["measures"]:
                        lines.append(f"        - {m}")

    return "\n".join(lines)


def _render_joins(lines: List[str], joins: List[Dict[str, Any]], indent: int) -> None:
    """Recursively render join definitions into YAML lines."""
    prefix = " " * indent
    for join in joins:
        lines.append(f"{prefix}- name: {join['name']}")
        lines.append(f"{prefix}  source: {join['source']}")
        if join.get("on"):
            lines.append(f"{prefix}  on: {join['on']}")
        if join.get("using"):
            lines.append(f"{prefix}  using:")
            for col in join["using"]:
                lines.append(f"{prefix}    - {col}")
        # Nested joins (snowflake schema)
        if join.get("joins"):
            lines.append(f"{prefix}  joins:")
            _render_joins(lines, join["joins"], indent + 4)


def create_metric_view(
    full_name: str,
    source: str,
    dimensions: List[Dict[str, str]],
    measures: List[Dict[str, str]],
    version: str = "1.1",
    comment: Optional[str] = None,
    filter_expr: Optional[str] = None,
    joins: Optional[List[Dict[str, Any]]] = None,
    materialization: Optional[Dict[str, Any]] = None,
    or_replace: bool = False,
    warehouse_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a metric view in Unity Catalog.

    Metric views define reusable, governed business metrics in YAML. They
    separate measure definitions from dimension groupings so metrics can
    be queried flexibly across any dimension at runtime.

    Requires Databricks Runtime 17.2+ and a SQL warehouse.

    Args:
        full_name: Three-level name (catalog.schema.metric_view_name).
        source: Source table, view, or SQL query.
        dimensions: List of dimension dicts. Each must have:
            - name: Display name for the dimension.
            - expr: SQL expression (column reference or transformation).
            - comment: (optional) Description of the dimension.
        measures: List of measure dicts. Each must have:
            - name: Display name for the measure.
            - expr: Aggregate SQL expression (e.g. "SUM(amount)").
            - comment: (optional) Description of the measure.
        version: YAML spec version ("1.1" for DBR 17.2+, "0.1" for DBR 16.4-17.1).
        comment: Optional description of the metric view.
        filter_expr: Optional SQL boolean filter applied to all queries.
        joins: Optional list of join definitions for star/snowflake schemas.
            Each dict: name, source, on (or using), joins (nested, optional).
        materialization: Optional materialization config dict with keys:
            - schedule: e.g. "every 6 hours"
            - mode: "relaxed" (only supported value)
            - materialized_views: list of {name, type, dimensions, measures}
        or_replace: If True, uses CREATE OR REPLACE (default: False).
        warehouse_id: Optional SQL warehouse ID.

    Returns:
        Dict with status, full_name, and the generated SQL.

    Raises:
        ValueError: If dimensions or measures are empty.
        SQLExecutionError: If query execution fails.
    """
    if not dimensions:
        raise ValueError("At least one dimension is required")
    if not measures:
        raise ValueError("At least one measure is required")

    yaml_block = _build_yaml_block(
        source=source,
        dimensions=dimensions,
        measures=measures,
        version=version,
        comment=comment,
        filter_expr=filter_expr,
        joins=joins,
        materialization=materialization,
    )

    create_keyword = "CREATE OR REPLACE" if or_replace else "CREATE"
    sql = textwrap.dedent(f"""\
        {create_keyword} VIEW {full_name}
        WITH METRICS
        LANGUAGE YAML
        AS $$
        {textwrap.indent(yaml_block, "  ")}
        $$""")

    execute_sql(sql_query=sql, warehouse_id=warehouse_id)

    return {
        "status": "created",
        "full_name": full_name,
        "sql": sql,
    }


def alter_metric_view(
    full_name: str,
    source: str,
    dimensions: List[Dict[str, str]],
    measures: List[Dict[str, str]],
    version: str = "1.1",
    comment: Optional[str] = None,
    filter_expr: Optional[str] = None,
    joins: Optional[List[Dict[str, Any]]] = None,
    materialization: Optional[Dict[str, Any]] = None,
    warehouse_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Alter an existing metric view with a new YAML definition.
    Args:
        full_name: Three-level name (catalog.schema.metric_view_name).
        source: Source table, view, or SQL query.
        dimensions: List of dimension dicts (name, expr, comment).
        measures: List of measure dicts (name, expr, comment).
        version: YAML spec version.
        comment: Optional description.
        filter_expr: Optional SQL boolean filter.
        joins: Optional join definitions.
        materialization: Optional materialization config.
        warehouse_id: Optional SQL warehouse ID.

    Returns:
        Dict with status, full_name, and the generated SQL.
    """
    yaml_block = _build_yaml_block(
        source=source,
        dimensions=dimensions,
        measures=measures,
        version=version,
        comment=comment,
        filter_expr=filter_expr,
        joins=joins,
        materialization=materialization,
    )

    sql = textwrap.dedent(f"""\
        ALTER VIEW {full_name}
        AS $$
        {textwrap.indent(yaml_block, "  ")}
        $$""")

    execute_sql(sql_query=sql, warehouse_id=warehouse_id)

    return {
        "status": "altered",
        "full_name": full_name,
        "sql": sql,
    }


def drop_metric_view(
    full_name: str,
    if_exists: bool = True,
    warehouse_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Drop a metric view.

    Args:
        full_name: Three-level name (catalog.schema.metric_view_name).
        if_exists: If True, does not error if the view doesn't exist.
        warehouse_id: Optional SQL warehouse ID.

    Returns:
        Dict with status and full_name.
    """
    exists_clause = " IF EXISTS" if if_exists else ""
    sql = f"DROP VIEW{exists_clause} {full_name}"

    execute_sql(sql_query=sql, warehouse_id=warehouse_id)

    return {
        "status": "dropped",
        "full_name": full_name,
        "sql": sql,
    }


def describe_metric_view(
    full_name: str,
    warehouse_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get the definition and metadata of a metric view.

    Uses DESCRIBE TABLE EXTENDED ... AS JSON to retrieve the full
    YAML definition, dimensions, measures, and other metadata.

    Args:
        full_name: Three-level name (catalog.schema.metric_view_name).
        warehouse_id: Optional SQL warehouse ID.

    Returns:
        Dict with the metric view definition and metadata.
    """
    sql = f"DESCRIBE TABLE EXTENDED {full_name} AS JSON"
    result = execute_sql(sql_query=sql, warehouse_id=warehouse_id)
    return {"full_name": full_name, "definition": result}


def query_metric_view(
    full_name: str,
    measures: List[str],
    dimensions: Optional[List[str]] = None,
    where: Optional[str] = None,
    order_by: Optional[str] = None,
    limit: Optional[int] = None,
    warehouse_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Query a metric view by selecting dimensions and measures.

    Measures must be wrapped in MEASURE() aggregate function.
    Dimensions are used in GROUP BY.

    Args:
        full_name: Three-level name (catalog.schema.metric_view_name).
        measures: List of measure names to query (wrapped in MEASURE() automatically).
        dimensions: Optional list of dimension names/expressions to group by.
        where: Optional WHERE clause filter (without the WHERE keyword).
        order_by: Optional ORDER BY clause (without the ORDER BY keyword).
            Use "ALL" for ORDER BY ALL.
        limit: Optional row limit.
        warehouse_id: Optional SQL warehouse ID.

    Returns:
        List of row dicts with query results.

    Example:
        query_metric_view(
            full_name="catalog.schema.orders_metrics",
            measures=["Total Revenue", "Order Count"],
            dimensions=["Order Month", "Order Status"],
            where="extract(year FROM `Order Month`) = 2024",
            order_by="ALL",
            limit=100,
        )
    """
    select_parts = []

    if dimensions:
        for dim in dimensions:
            # Backtick-quote dimension names that contain spaces
            if " " in dim and not dim.startswith("`"):
                select_parts.append(f"`{dim}`")
            else:
                select_parts.append(dim)

    for measure in measures:
        # Backtick-quote measure names that contain spaces
        if " " in measure and not measure.startswith("`"):
            select_parts.append(f"MEASURE(`{measure}`)")
        else:
            select_parts.append(f"MEASURE({measure})")

    select_clause = ",\n  ".join(select_parts)
    sql = f"SELECT\n  {select_clause}\nFROM {full_name}"

    if where:
        sql += f"\nWHERE {where}"

    if dimensions:
        sql += "\nGROUP BY ALL"

    if order_by:
        sql += f"\nORDER BY {order_by}"

    if limit:
        sql += f"\nLIMIT {limit}"

    return execute_sql(sql_query=sql, warehouse_id=warehouse_id)


def grant_metric_view(
    full_name: str,
    principal: str,
    privileges: Optional[List[str]] = None,
    warehouse_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Grant privileges on a metric view.

    Args:
        full_name: Three-level name (catalog.schema.metric_view_name).
        principal: User, group, or service principal to grant to.
        privileges: List of privileges (default: ["SELECT"]).
        warehouse_id: Optional SQL warehouse ID.

    Returns:
        Dict with status and executed SQL.
    """
    privs = privileges or ["SELECT"]
    priv_str = ", ".join(privs)
    sql = f"GRANT {priv_str} ON {full_name} TO `{principal}`"

    execute_sql(sql_query=sql, warehouse_id=warehouse_id)

    return {
        "status": "granted",
        "full_name": full_name,
        "principal": principal,
        "privileges": privs,
        "sql": sql,
    }

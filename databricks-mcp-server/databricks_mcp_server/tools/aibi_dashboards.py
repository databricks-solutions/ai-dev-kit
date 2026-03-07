"""AI/BI Dashboard tools - Create and manage AI/BI dashboards.

Note: AI/BI dashboards were previously known as Lakeview dashboards.
The SDK/API still uses the 'lakeview' name internally.

Provides 4 workflow-oriented tools following the Lakebase pattern:
- create_or_update_dashboard: idempotent create/update with auto-publish
- get_dashboard: get details by ID, or list all
- delete_dashboard: move to trash (renamed from trash_dashboard for consistency)
- publish_dashboard: publish or unpublish via boolean toggle
"""

import json
from typing import Any, Dict, Union

from databricks_tools_core.aibi_dashboards import (
    create_or_update_dashboard as _create_or_update_dashboard,
    get_dashboard as _get_dashboard,
    list_dashboards as _list_dashboards,
    publish_dashboard as _publish_dashboard,
    trash_dashboard as _trash_dashboard,
    unpublish_dashboard as _unpublish_dashboard,
)

from ..manifest import register_deleter
from ..server import mcp


def _delete_dashboard_resource(resource_id: str) -> None:
    _trash_dashboard(dashboard_id=resource_id)


register_deleter("dashboard", _delete_dashboard_resource)


# ============================================================================
# Tool 1: create_or_update_dashboard
# ============================================================================


@mcp.tool
def create_or_update_dashboard(
    display_name: str,
    parent_path: str,
    serialized_dashboard: Union[str, dict],
    warehouse_id: str,
    publish: bool = True,
) -> Dict[str, Any]:
    """Create or update an AI/BI dashboard from JSON content.

    CRITICAL PRE-REQUISITES (DO NOT SKIP):
    Before calling this tool, you MUST:
    1. Call get_table_details() to get table schemas
    2. Call execute_sql() to TEST EVERY dataset query - if any fail, fix them first!
    3. Verify query results have expected columns and data types

    If you skip validation, widgets WILL show "Invalid widget definition" errors!

    DASHBOARD JSON REQUIREMENTS:

    Dataset Architecture:
    - One dataset per domain (orders, customers, products)
    - Exactly ONE SQL query per dataset (no semicolon-separated queries)
    - Use fully-qualified table names: catalog.schema.table_name
    - All widget fieldNames must match dataset column names exactly

    CRITICAL VERSION REQUIREMENTS:
    - counter: version 2
    - table: version 2
    - filter-multi-select, filter-single-select, filter-date-range-picker: version 2
    - bar, line, pie: version 3
    - text: NO spec block (use multilineTextboxSpec directly on widget)

    CRITICAL FIELD NAME MATCHING:
    The "name" in query.fields MUST exactly match "fieldName" in encodings!
    - CORRECT: fields=[{"name": "sum(spend)", "expression": "SUM(`spend`)"}]
               encodings={"value": {"fieldName": "sum(spend)", ...}}
    - WRONG:   fields=[{"name": "spend", "expression": "SUM(`spend`)"}]
               encodings={"value": {"fieldName": "sum(spend)", ...}}  # ERROR!

    Widget Field Expressions (ONLY these are allowed):
    - Aggregates: SUM(`col`), AVG(`col`), COUNT(`col`), COUNT(DISTINCT `col`), MIN(`col`), MAX(`col`)
    - Date truncation: DATE_TRUNC("DAY", `date`), DATE_TRUNC("WEEK", `date`), DATE_TRUNC("MONTH", `date`)
    - Simple reference: `column_name`
    - NO CAST, no complex SQL - put logic in dataset query instead

    Layout (6-column grid, NO GAPS):
    - Each row must total width=6 exactly
    - Counter/KPI: width=2, height=3-4 (NEVER height=2)
    - Charts: width=3, height=5-6
    - Tables: width=6, height=5-8
    - Text headers: width=6, height=1 (use SEPARATE widgets for title and subtitle)

    Widget Naming:
    - widget.name: alphanumeric + hyphens + underscores ONLY (no spaces/parentheses/colons)
    - frame.title: human-readable name (any characters)
    - widget.queries[0].name: always "main_query"

    Text Widgets:
    - Do NOT use a spec block - use multilineTextboxSpec directly on widget
    - Multiple items in lines[] are CONCATENATED, not separate lines
    - Use separate text widgets for title and subtitle at different y positions

    Counter Widgets (version 2):
    Pattern 1 - Pre-aggregated (1 row, no filters):
    - Dataset returns exactly 1 row
    - Use "disaggregated": true and simple field reference
    Pattern 2 - Aggregating (multi-row, supports filters):
    - Dataset returns multiple rows (grouped by filter dimension)
    - Use "disaggregated": false and aggregation expression
    - Field name must match: {"name": "sum(spend)", "expression": "SUM(`spend`)"}
    - Percent values must be 0-1 (not 0-100)

    Table Widgets (version 2):
    - Column objects only need fieldName and displayName - no other properties!
    - Use "disaggregated": true for raw rows

    Charts - line/bar/pie (version 3):
    - Use "disaggregated": true with pre-aggregated data
    - scale.type: "temporal" (dates), "quantitative" (numbers), "categorical" (strings)
    - Limit color/grouping dimensions to 3-8 distinct values

    SQL Patterns (Spark SQL):
    - Date math: date_sub(current_date(), N), add_months(current_date(), -N)
    - AVOID INTERVAL syntax - use functions instead

    Filters (CRITICAL - Global vs Page-Level):
    - Valid filter widgetTypes: "filter-multi-select", "filter-single-select", "filter-date-range-picker"
    - Filter widgets use spec.version: 2 (NOT 3 like charts)
    - Filter encodings require "queryName" to bind to dataset queries
    - Use "disaggregated": false for filter queries
    - DO NOT use widgetType: "filter" - this is INVALID and will cause errors
    - DO NOT use associative_filter_predicate_group - causes SQL errors
    - ALWAYS include "frame": {"showTitle": true, "title": "..."} for filter widgets

    Global Filters vs Page-Level Filters:
    - GLOBAL: Place on page with "pageType": "PAGE_TYPE_GLOBAL_FILTERS" - affects ALL pages
    - PAGE-LEVEL: Place on regular "PAGE_TYPE_CANVAS" page - affects ONLY that page
    - A filter only affects datasets containing the filter field column

    Args:
        display_name: Dashboard display name
        parent_path: Workspace folder path (e.g., "/Workspace/Users/me/dashboards")
        serialized_dashboard: Dashboard JSON content as string (MUST be tested first!)
        warehouse_id: SQL warehouse ID for query execution
        publish: Whether to publish after creation (default: True)

    Returns:
        Dictionary with:
        - success: Whether operation succeeded
        - status: 'created' or 'updated'
        - dashboard_id: Dashboard ID
        - path: Full workspace path
        - url: Dashboard URL
        - published: Whether dashboard was published
        - error: Error message if failed
    """
    # MCP deserializes JSON params, so serialized_dashboard may arrive as a dict
    if isinstance(serialized_dashboard, dict):
        serialized_dashboard = json.dumps(serialized_dashboard)

    result = _create_or_update_dashboard(
        display_name=display_name,
        parent_path=parent_path,
        serialized_dashboard=serialized_dashboard,
        warehouse_id=warehouse_id,
        publish=publish,
    )

    # Track resource on successful create/update
    try:
        if result.get("success") and result.get("dashboard_id"):
            from ..manifest import track_resource

            track_resource(
                resource_type="dashboard",
                name=display_name,
                resource_id=result["dashboard_id"],
                url=result.get("url"),
            )
    except Exception:
        pass  # best-effort tracking

    return result


# ============================================================================
# Tool 2: get_dashboard
# ============================================================================


@mcp.tool
def get_dashboard(
    dashboard_id: str = None,
    page_size: int = 25,
) -> Dict[str, Any]:
    """Get AI/BI dashboard details by ID, or list all dashboards.

    Pass a dashboard_id to get one dashboard's details.
    Omit dashboard_id to list all dashboards.

    Args:
        dashboard_id: The dashboard ID. If omitted, lists all dashboards.
        page_size: Number of dashboards to return when listing (default: 25)

    Returns:
        Single dashboard dict (if dashboard_id provided) or
        {"dashboards": [...]} when listing.

    Example:
        >>> get_dashboard("abc123")
        {"dashboard_id": "abc123", "display_name": "Sales Dashboard", ...}
        >>> get_dashboard()
        {"dashboards": [{"dashboard_id": "abc", "display_name": "Sales", ...}]}
    """
    if dashboard_id:
        return _get_dashboard(dashboard_id=dashboard_id)

    return _list_dashboards(page_size=page_size)


# ============================================================================
# Tool 3: delete_dashboard
# ============================================================================


@mcp.tool
def delete_dashboard(dashboard_id: str) -> Dict[str, str]:
    """Soft-delete an AI/BI dashboard by moving it to trash.

    Args:
        dashboard_id: Dashboard ID to delete

    Returns:
        Dictionary with status message

    Example:
        >>> delete_dashboard("abc123")
        {"status": "success", "message": "Dashboard abc123 moved to trash", ...}
    """
    result = _trash_dashboard(dashboard_id=dashboard_id)
    try:
        from ..manifest import remove_resource

        remove_resource(resource_type="dashboard", resource_id=dashboard_id)
    except Exception:
        pass
    return result


# ============================================================================
# Tool 4: publish_dashboard
# ============================================================================


@mcp.tool
def publish_dashboard(
    dashboard_id: str,
    warehouse_id: str = None,
    publish: bool = True,
    embed_credentials: bool = True,
) -> Dict[str, Any]:
    """Publish or unpublish an AI/BI dashboard.

    Set publish=True (default) to publish, or publish=False to unpublish.

    Publishing with embed_credentials=True allows users without direct
    data access to view the dashboard (queries execute using the
    service principal's permissions).

    Args:
        dashboard_id: Dashboard ID
        warehouse_id: SQL warehouse ID for query execution (required for publish)
        publish: True to publish (default), False to unpublish
        embed_credentials: Whether to embed credentials (default: True)

    Returns:
        Dictionary with publish/unpublish status

    Example:
        >>> publish_dashboard("abc123", "warehouse456")
        {"status": "published", "dashboard_id": "abc123", ...}
        >>> publish_dashboard("abc123", publish=False)
        {"status": "unpublished", "dashboard_id": "abc123", ...}
    """
    if not publish:
        return _unpublish_dashboard(dashboard_id=dashboard_id)

    if not warehouse_id:
        return {"error": "warehouse_id is required for publishing."}

    return _publish_dashboard(
        dashboard_id=dashboard_id,
        warehouse_id=warehouse_id,
        embed_credentials=embed_credentials,
    )

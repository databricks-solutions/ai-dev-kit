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


@mcp.tool(timeout=120)
def create_or_update_dashboard(
    display_name: str,
    parent_path: str,
    serialized_dashboard: Union[str, dict],
    warehouse_id: str,
    publish: bool = True,
) -> Dict[str, Any]:
    """Create or update an AI/BI dashboard from JSON content.

    CRITICAL: Before calling this tool, you MUST:
    1. Call get_table_stats_and_schema() to get table schemas
    2. Call execute_sql() to TEST EVERY dataset query
    If you skip validation, widgets WILL show errors!

    WIDGET STRUCTURE (CRITICAL - follow this exactly):
    Each widget in a page layout has `queries` as a TOP-LEVEL SIBLING of `spec`.
    Do NOT put queries inside spec. Do NOT use `named_queries`.

    Correct counter widget:
    {
      "widget": {
        "name": "total-trips",
        "queries": [
          {
            "name": "main_query",
            "query": {
              "datasetName": "summary",
              "fields": [{"name": "sum(trips)", "expression": "SUM(`trips`)"}],
              "disaggregated": false
            }
          }
        ],
        "spec": {
          "version": 2,
          "widgetType": "counter",
          "encodings": {
            "value": {"fieldName": "sum(trips)", "displayName": "Total Trips"}
          },
          "frame": {"showTitle": true, "title": "Total Trips"}
        }
      },
      "position": {"x": 0, "y": 0, "width": 2, "height": 3}
    }

    Correct bar chart widget:
    {
      "widget": {
        "name": "trips-by-zip",
        "queries": [
          {
            "name": "main_query",
            "query": {
              "datasetName": "by_zip",
              "fields": [
                {"name": "pickup_zip", "expression": "`pickup_zip`"},
                {"name": "trip_count", "expression": "`trip_count`"}
              ],
              "disaggregated": true
            }
          }
        ],
        "spec": {
          "version": 3,
          "widgetType": "bar",
          "encodings": {
            "x": {"fieldName": "pickup_zip", "scale": {"type": "categorical"}, "displayName": "ZIP"},
            "y": {"fieldName": "trip_count", "scale": {"type": "quantitative"}, "displayName": "Trips"}
          },
          "frame": {"showTitle": true, "title": "Trips by ZIP"}
        }
      },
      "position": {"x": 0, "y": 3, "width": 6, "height": 5}
    }

    Correct filter widget:
    {
      "widget": {
        "name": "filter-region",
        "queries": [
          {
            "name": "main_query",
            "query": {
              "datasetName": "sales",
              "fields": [{"name": "region", "expression": "`region`"}],
              "disaggregated": false
            }
          }
        ],
        "spec": {
          "version": 2,
          "widgetType": "filter-multi-select",
          "encodings": {
            "fields": [{"fieldName": "region", "queryName": "main_query", "displayName": "Region"}]
          },
          "frame": {"showTitle": true, "title": "Region"}
        }
      },
      "position": {"x": 0, "y": 0, "width": 2, "height": 2}
    }

    Text widget (NO spec block):
    {
      "widget": {
        "name": "title",
        "textbox_spec": "## Dashboard Title"
      },
      "position": {"x": 0, "y": 0, "width": 6, "height": 1}
    }

    KEY RULES:
    - queries[].query.datasetName (camelCase, not dataSetName)
    - queries[].query.fields[].name MUST exactly match encodings fieldName
    - Versions: counter=2, table=2, filters=2, bar/line/pie=3
    - Layout: 6-column grid, each row must sum to width=6
    - Filter widgetType must be "filter-multi-select", "filter-single-select",
      or "filter-date-range-picker" (NOT "filter")
    - Global filters: page with "pageType": "PAGE_TYPE_GLOBAL_FILTERS"
    - Page-level filters: on regular "PAGE_TYPE_CANVAS" page

    See the databricks-aibi-dashboards skill for full reference.

    Args:
        display_name: Dashboard display name
        parent_path: Workspace folder path (e.g., "/Workspace/Users/me/dashboards")
        serialized_dashboard: Dashboard JSON content as string (MUST be tested first!)
        warehouse_id: SQL warehouse ID for query execution
        publish: Whether to publish after creation (default: True)

    Returns:
        Dictionary with success, status, dashboard_id, path, url, published, error.
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


@mcp.tool(timeout=30)
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


@mcp.tool(timeout=30)
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


@mcp.tool(timeout=60)
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

"""AI/BI Dashboard tools - Create and manage AI/BI dashboards.

Note: AI/BI dashboards were previously known as Lakeview dashboards.
The SDK/API still uses the 'lakeview' name internally.

Consolidated into 1 tool:
- manage_dashboard: create_or_update, get, list, delete, publish, unpublish
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

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


@mcp.tool(timeout=120)
def manage_dashboard(
    action: str,
    # For create_or_update:
    display_name: Optional[str] = None,
    parent_path: Optional[str] = None,
    dashboard_file_path: Optional[str] = None,
    warehouse_id: Optional[str] = None,
    # For create_or_update publish option:
    publish: bool = True,
    genie_space_id: Optional[str] = None,
    catalog: Optional[str] = None,
    schema: Optional[str] = None,
    # For get/delete/publish/unpublish:
    dashboard_id: Optional[str] = None,
    # For publish:
    embed_credentials: bool = True,
) -> Dict[str, Any]:
    """Manage AI/BI dashboards: create, update, get, list, delete, publish.

    CRITICAL: Before calling this tool to create or edit a dashboard, you MUST:
    0. Review the databricks-aibi-dashboards skill to understand widget definitions.
       You must EXACTLY follow the JSON structure detailed in the skill.
    1. Call get_table_stats_and_schema() to get table schemas for your queries.
    2. Call execute_sql() to TEST EVERY dataset query before using in dashboard.
    If you skip validation, widgets WILL show errors!

    Actions:
    - create_or_update: Create/update dashboard from local JSON file.
      Requires display_name, parent_path, dashboard_file_path, warehouse_id.
      Optional: genie_space_id (link Genie), catalog/schema (defaults for unqualified tables).
      publish=True (default) auto-publishes after create.
      Returns: {success, dashboard_id, path, url, published, error}.
    - get: Get dashboard details. Requires dashboard_id.
      Returns: dashboard config and metadata.
    - list: List all dashboards.
      Returns: {dashboards: [...]}.
    - delete: Soft-delete (moves to trash). Requires dashboard_id.
      Returns: {status, message}.
    - publish: Publish dashboard. Requires dashboard_id, warehouse_id.
      embed_credentials=True allows users without data access to view.
      Returns: {status, dashboard_id}.
    - unpublish: Unpublish dashboard. Requires dashboard_id.
      Returns: {status, dashboard_id}.

Workflow for create_or_update:
    1. Write dashboard JSON to a local file (e.g., ./my_dashboard.json)
    2. Test all SQL queries via execute_sql()
    3. Call manage_dashboard(action="create_or_update", dashboard_file_path="./my_dashboard.json", ...)
    4. To update: edit the local file, then call manage_dashboard again

    See databricks-aibi-dashboards skill for full widget structure reference."""
    act = action.lower()

    if act == "create_or_update":
        if not all([display_name, parent_path, dashboard_file_path, warehouse_id]):
            return {"error": "create_or_update requires: display_name, parent_path, dashboard_file_path, warehouse_id"}

        # Read dashboard JSON from local file
        file_path = Path(dashboard_file_path)
        if not file_path.exists():
            return {"error": f"Dashboard file not found: {dashboard_file_path}"}

        try:
            dashboard_content = file_path.read_text(encoding="utf-8")
            # Validate it's valid JSON
            json.loads(dashboard_content)
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON in dashboard file: {e}"}
        except Exception as e:
            return {"error": f"Failed to read dashboard file: {e}"}

        result = _create_or_update_dashboard(
            display_name=display_name,
            parent_path=parent_path,
            serialized_dashboard=dashboard_content,
            warehouse_id=warehouse_id,
            publish=publish,
            genie_space_id=genie_space_id,
            catalog=catalog,
            schema=schema,
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
            pass

        return result

    elif act == "get":
        if not dashboard_id:
            return {"error": "get requires: dashboard_id"}
        return _get_dashboard(dashboard_id=dashboard_id)

    elif act == "list":
        return _list_dashboards(page_size=200)

    elif act == "delete":
        if not dashboard_id:
            return {"error": "delete requires: dashboard_id"}
        result = _trash_dashboard(dashboard_id=dashboard_id)
        try:
            from ..manifest import remove_resource
            remove_resource(resource_type="dashboard", resource_id=dashboard_id)
        except Exception:
            pass
        return result

    elif act == "publish":
        if not dashboard_id:
            return {"error": "publish requires: dashboard_id"}
        if not warehouse_id:
            return {"error": "publish requires: warehouse_id"}
        return _publish_dashboard(
            dashboard_id=dashboard_id,
            warehouse_id=warehouse_id,
            embed_credentials=embed_credentials,
        )

    elif act == "unpublish":
        if not dashboard_id:
            return {"error": "unpublish requires: dashboard_id"}
        return _unpublish_dashboard(dashboard_id=dashboard_id)

    else:
        return {
            "error": f"Invalid action '{action}'. Valid actions: create_or_update, get, list, delete, publish, unpublish"
        }

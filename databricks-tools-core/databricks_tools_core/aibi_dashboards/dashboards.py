"""AI/BI Dashboard CRUD Operations.

Functions for managing AI/BI dashboards using the Databricks Lakeview API.
Note: AI/BI dashboards were previously known as Lakeview dashboards.
The SDK/API still uses the 'lakeview' name internally.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from databricks.sdk.service.dashboards import Dashboard

from ..auth import get_workspace_client
from .models import DashboardDeploymentResult

logger = logging.getLogger(__name__)


def get_dashboard(dashboard_id: str) -> Dict[str, Any]:
    """Get dashboard details by ID.

    Args:
        dashboard_id: The dashboard ID

    Returns:
        Dictionary with dashboard details including:
        - dashboard_id: The dashboard ID
        - display_name: Dashboard display name
        - warehouse_id: Associated SQL warehouse
        - parent_path: Workspace path
        - serialized_dashboard: Dashboard JSON content (if available)
    """
    w = get_workspace_client()
    dashboard = w.lakeview.get(dashboard_id=dashboard_id)

    return {
        "dashboard_id": dashboard.dashboard_id,
        "display_name": dashboard.display_name,
        "warehouse_id": dashboard.warehouse_id,
        "parent_path": dashboard.parent_path,
        "path": dashboard.path,
        "create_time": dashboard.create_time,
        "update_time": dashboard.update_time,
        "lifecycle_state": dashboard.lifecycle_state.value
        if dashboard.lifecycle_state
        else None,
        "serialized_dashboard": dashboard.serialized_dashboard,
    }


def list_dashboards(
    page_size: int = 25,
    page_token: Optional[str] = None,
) -> Dict[str, Any]:
    """List AI/BI dashboards in the workspace.

    Args:
        page_size: Number of dashboards per page (default: 25)
        page_token: Token for pagination

    Returns:
        Dictionary with:
        - dashboards: List of dashboard summaries
        - next_page_token: Token for next page (if available)
    """
    w = get_workspace_client()

    dashboards = []
    for dashboard in w.lakeview.list(page_size=page_size, page_token=page_token):
        dashboards.append(
            {
                "dashboard_id": dashboard.dashboard_id,
                "display_name": dashboard.display_name,
                "warehouse_id": dashboard.warehouse_id,
                "parent_path": dashboard.parent_path,
                "path": dashboard.path,
                "lifecycle_state": dashboard.lifecycle_state.value
                if dashboard.lifecycle_state
                else None,
            }
        )

    return {"dashboards": dashboards}


def find_dashboard_by_path(dashboard_path: str) -> Optional[str]:
    """Find a dashboard by its workspace path and return its ID.

    Args:
        dashboard_path: Full workspace path (e.g., /Workspace/Users/.../MyDash.lvdash.json)

    Returns:
        Dashboard ID if found, None otherwise
    """
    w = get_workspace_client()

    try:
        from databricks.sdk.errors.platform import ResourceDoesNotExist

        existing = w.workspace.get_status(path=dashboard_path)
        return existing.resource_id
    except ResourceDoesNotExist:
        return None
    except Exception as e:
        logger.warning(f"Error checking dashboard path {dashboard_path}: {e}")
        return None


def create_dashboard(
    display_name: str,
    parent_path: str,
    serialized_dashboard: str,
    warehouse_id: str,
) -> Dict[str, Any]:
    """Create a new AI/BI dashboard.

    Args:
        display_name: Dashboard display name
        parent_path: Workspace folder path (e.g., /Workspace/Users/me/dashboards)
        serialized_dashboard: Dashboard JSON content as string
        warehouse_id: SQL warehouse ID

    Returns:
        Dictionary with:
        - dashboard_id: Created dashboard ID
        - display_name: Dashboard name
        - path: Full workspace path
        - url: Dashboard URL
    """
    w = get_workspace_client()

    dashboard = Dashboard(
        display_name=display_name,
        warehouse_id=warehouse_id,
        parent_path=parent_path,
        serialized_dashboard=serialized_dashboard,
    )

    created = w.lakeview.create(dashboard=dashboard)
    dashboard_url = f"{w.config.host}/sql/dashboardsv3/{created.dashboard_id}"

    return {
        "dashboard_id": created.dashboard_id,
        "display_name": created.display_name,
        "path": created.path,
        "url": dashboard_url,
    }


def update_dashboard(
    dashboard_id: str,
    display_name: Optional[str] = None,
    serialized_dashboard: Optional[str] = None,
    warehouse_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Update an existing AI/BI dashboard.

    Args:
        dashboard_id: Dashboard ID to update
        display_name: New display name (optional)
        serialized_dashboard: New dashboard JSON content (optional)
        warehouse_id: New warehouse ID (optional)

    Returns:
        Dictionary with updated dashboard details
    """
    w = get_workspace_client()

    # Get current dashboard to preserve existing values
    current = w.lakeview.get(dashboard_id=dashboard_id)

    dashboard = Dashboard(
        display_name=display_name or current.display_name,
        warehouse_id=warehouse_id or current.warehouse_id,
        parent_path=current.parent_path,
        serialized_dashboard=serialized_dashboard or current.serialized_dashboard,
    )

    updated = w.lakeview.update(dashboard_id=dashboard_id, dashboard=dashboard)
    dashboard_url = f"{w.config.host}/sql/dashboardsv3/{updated.dashboard_id}"

    return {
        "dashboard_id": updated.dashboard_id,
        "display_name": updated.display_name,
        "path": updated.path,
        "url": dashboard_url,
    }


def trash_dashboard(dashboard_id: str) -> Dict[str, str]:
    """Move a dashboard to trash.

    Args:
        dashboard_id: Dashboard ID to trash

    Returns:
        Dictionary with status message
    """
    w = get_workspace_client()
    w.lakeview.trash(dashboard_id=dashboard_id)

    return {
        "status": "success",
        "message": f"Dashboard {dashboard_id} moved to trash",
        "dashboard_id": dashboard_id,
    }


def publish_dashboard(
    dashboard_id: str,
    warehouse_id: str,
    embed_credentials: bool = True,
) -> Dict[str, Any]:
    """Publish a dashboard to make it accessible to viewers.

    Publishing with embed_credentials=True allows users without direct
    data access to view the dashboard (queries execute using the
    service principal's permissions).

    Args:
        dashboard_id: Dashboard ID to publish
        warehouse_id: SQL warehouse ID for query execution
        embed_credentials: Whether to embed credentials (default: True)

    Returns:
        Dictionary with publish status
    """
    w = get_workspace_client()

    w.lakeview.publish(
        dashboard_id=dashboard_id,
        warehouse_id=warehouse_id,
        embed_credentials=embed_credentials,
    )

    dashboard_url = f"{w.config.host}/sql/dashboardsv3/{dashboard_id}"

    return {
        "status": "published",
        "dashboard_id": dashboard_id,
        "url": dashboard_url,
        "embed_credentials": embed_credentials,
    }


def unpublish_dashboard(dashboard_id: str) -> Dict[str, str]:
    """Unpublish a dashboard.

    Args:
        dashboard_id: Dashboard ID to unpublish

    Returns:
        Dictionary with status message
    """
    w = get_workspace_client()
    w.lakeview.unpublish(dashboard_id=dashboard_id)

    return {
        "status": "unpublished",
        "message": f"Dashboard {dashboard_id} unpublished",
        "dashboard_id": dashboard_id,
    }


async def deploy_dashboard(
    dashboard_content: str,
    install_path: str,
    dashboard_name: str,
    warehouse_id: str,
) -> DashboardDeploymentResult:
    """Deploy a dashboard to Databricks workspace using Lakeview API.

    This is a high-level function that handles create-or-update logic:
    - Checks if a dashboard exists at the path
    - Creates new or updates existing dashboard
    - Publishes the dashboard

    Args:
        dashboard_content: Dashboard JSON content as string
        install_path: Workspace folder path (e.g., /Workspace/Users/me/dashboards)
        dashboard_name: Display name for the dashboard
        warehouse_id: SQL warehouse ID

    Returns:
        DashboardDeploymentResult with deployment status and details
    """
    from databricks.sdk.errors.platform import ResourceDoesNotExist

    w = get_workspace_client()
    dashboard_path = f"{install_path}/{dashboard_name}.lvdash.json"

    try:
        # Ensure the parent directory exists
        try:
            await asyncio.to_thread(w.workspace.mkdirs, install_path)
        except Exception as e:
            logger.debug(f"Directory creation check: {install_path} - {e}")

        # Check if dashboard already exists at path
        existing_dashboard_id = None
        try:
            existing = await asyncio.to_thread(
                w.workspace.get_status, path=dashboard_path
            )
            existing_dashboard_id = existing.resource_id
        except ResourceDoesNotExist:
            pass

        dashboard = Dashboard(
            display_name=dashboard_name,
            warehouse_id=warehouse_id,
            parent_path=install_path,
            serialized_dashboard=dashboard_content,
        )

        # Update or create
        if existing_dashboard_id:
            try:
                logger.info(f"Updating existing dashboard: {dashboard_name}")
                updated = w.lakeview.update(
                    dashboard_id=existing_dashboard_id, dashboard=dashboard
                )
                dashboard_id = updated.dashboard_id
                status = "updated"
            except Exception as e:
                logger.warning(
                    f"Failed to update dashboard {existing_dashboard_id}: {e}. Creating new."
                )
                created = w.lakeview.create(dashboard=dashboard)
                dashboard_id = created.dashboard_id
                status = "created"
        else:
            logger.info(f"Creating new dashboard: {dashboard_name}")
            created = w.lakeview.create(dashboard=dashboard)
            dashboard_id = created.dashboard_id
            status = "created"

        dashboard_url = f"{w.config.host}/sql/dashboardsv3/{dashboard_id}"

        # Publish (best-effort)
        try:
            w.lakeview.publish(
                dashboard_id=dashboard_id,
                warehouse_id=warehouse_id,
                embed_credentials=True,
            )
            logger.info(f"Dashboard {dashboard_id} published successfully")
        except Exception as e:
            logger.warning(f"Failed to publish dashboard {dashboard_id}: {e}")

        return DashboardDeploymentResult(
            success=True,
            status=status,
            dashboard_id=dashboard_id,
            path=dashboard_path,
            url=dashboard_url,
        )

    except Exception as e:
        logger.error(f"Dashboard deployment failed: {e}", exc_info=True)
        return DashboardDeploymentResult(
            success=False,
            error=str(e),
            path=dashboard_path,
        )


def deploy_dashboard_sync(
    dashboard_content: str,
    install_path: str,
    dashboard_name: str,
    warehouse_id: str,
) -> DashboardDeploymentResult:
    """Deploy a dashboard to Databricks workspace (synchronous version).

    This is a high-level function that handles create-or-update logic:
    - Checks if a dashboard exists at the path
    - Creates new or updates existing dashboard
    - Publishes the dashboard

    Args:
        dashboard_content: Dashboard JSON content as string
        install_path: Workspace folder path (e.g., /Workspace/Users/me/dashboards)
        dashboard_name: Display name for the dashboard
        warehouse_id: SQL warehouse ID

    Returns:
        DashboardDeploymentResult with deployment status and details
    """
    from databricks.sdk.errors.platform import ResourceDoesNotExist

    w = get_workspace_client()
    dashboard_path = f"{install_path}/{dashboard_name}.lvdash.json"

    try:
        # Ensure the parent directory exists
        try:
            w.workspace.mkdirs(install_path)
        except Exception as e:
            logger.debug(f"Directory creation check: {install_path} - {e}")

        # Check if dashboard already exists at path
        existing_dashboard_id = None
        try:
            existing = w.workspace.get_status(path=dashboard_path)
            existing_dashboard_id = existing.resource_id
        except ResourceDoesNotExist:
            pass

        dashboard = Dashboard(
            display_name=dashboard_name,
            warehouse_id=warehouse_id,
            parent_path=install_path,
            serialized_dashboard=dashboard_content,
        )

        # Update or create
        if existing_dashboard_id:
            try:
                logger.info(f"Updating existing dashboard: {dashboard_name}")
                updated = w.lakeview.update(
                    dashboard_id=existing_dashboard_id, dashboard=dashboard
                )
                dashboard_id = updated.dashboard_id
                status = "updated"
            except Exception as e:
                logger.warning(
                    f"Failed to update dashboard {existing_dashboard_id}: {e}. Creating new."
                )
                created = w.lakeview.create(dashboard=dashboard)
                dashboard_id = created.dashboard_id
                status = "created"
        else:
            logger.info(f"Creating new dashboard: {dashboard_name}")
            created = w.lakeview.create(dashboard=dashboard)
            dashboard_id = created.dashboard_id
            status = "created"

        dashboard_url = f"{w.config.host}/sql/dashboardsv3/{dashboard_id}"

        # Publish (best-effort)
        try:
            w.lakeview.publish(
                dashboard_id=dashboard_id,
                warehouse_id=warehouse_id,
                embed_credentials=True,
            )
            logger.info(f"Dashboard {dashboard_id} published successfully")
        except Exception as e:
            logger.warning(f"Failed to publish dashboard {dashboard_id}: {e}")

        return DashboardDeploymentResult(
            success=True,
            status=status,
            dashboard_id=dashboard_id,
            path=dashboard_path,
            url=dashboard_url,
        )

    except Exception as e:
        logger.error(f"Dashboard deployment failed: {e}", exc_info=True)
        return DashboardDeploymentResult(
            success=False,
            error=str(e),
            path=dashboard_path,
        )


def create_or_update_dashboard(
    display_name: str,
    parent_path: str,
    serialized_dashboard: str,
    warehouse_id: str,
    publish: bool = True,
) -> Dict[str, Any]:
    """Create or update a dashboard (synchronous version).

    This is a convenience function that:
    1. Checks if a dashboard exists at the path
    2. Creates new or updates existing
    3. Optionally publishes

    Args:
        display_name: Dashboard display name
        parent_path: Workspace folder path
        serialized_dashboard: Dashboard JSON content
        warehouse_id: SQL warehouse ID
        publish: Whether to publish after create/update (default: True)

    Returns:
        Dictionary with:
        - success: Whether operation succeeded
        - status: 'created' or 'updated'
        - dashboard_id: Dashboard ID
        - url: Dashboard URL
        - published: Whether dashboard was published
    """
    result = deploy_dashboard_sync(
        dashboard_content=serialized_dashboard,
        install_path=parent_path,
        dashboard_name=display_name,
        warehouse_id=warehouse_id,
    )

    return {
        "success": result.success,
        "status": result.status,
        "dashboard_id": result.dashboard_id,
        "path": result.path,
        "url": result.url,
        "published": result.success and publish,
        "error": result.error,
    }

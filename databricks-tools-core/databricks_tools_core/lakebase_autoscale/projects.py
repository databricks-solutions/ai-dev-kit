"""
Lakebase Autoscaling Project Operations

Functions for creating, managing, and deleting Lakebase Autoscaling projects.
Projects are the top-level container for branches, computes, databases, and roles.
"""

import logging
from typing import Any, Dict, List, Optional

from ..auth import get_workspace_client

logger = logging.getLogger(__name__)


def _normalize_project_name(name: str) -> str:
    """Ensure project name has the 'projects/' prefix."""
    if not name.startswith("projects/"):
        return f"projects/{name}"
    return name


def create_project(
    project_id: str,
    display_name: Optional[str] = None,
    pg_version: str = "17",
) -> Dict[str, Any]:
    """
    Create a Lakebase Autoscaling project.

    Args:
        project_id: Project identifier (1-63 chars, lowercase letters, digits, hyphens).
        display_name: Human-readable display name. Defaults to project_id.
        pg_version: Postgres version ("16" or "17"). Default: "17".

    Returns:
        Dictionary with:
        - name: Project resource name (projects/{project_id})
        - display_name: Display name
        - pg_version: Postgres version
        - status: Creation status

    Raises:
        Exception: If creation fails
    """
    client = get_workspace_client()

    try:
        from databricks.sdk.service.postgres import Project, ProjectSpec

        spec = ProjectSpec(
            display_name=display_name or project_id,
            pg_version=int(pg_version),
        )

        operation = client.postgres.create_project(
            project=Project(spec=spec),
            project_id=project_id,
        )
        result_project = operation.wait()

        result: Dict[str, Any] = {
            "name": result_project.name,
            "display_name": display_name or project_id,
            "pg_version": pg_version,
            "status": "CREATED",
        }

        if result_project.status:
            try:
                if result_project.status.display_name:
                    result["display_name"] = result_project.status.display_name
            except (KeyError, AttributeError):
                pass
            try:
                if result_project.status.pg_version:
                    result["pg_version"] = str(result_project.status.pg_version)
            except (KeyError, AttributeError):
                pass
            try:
                if result_project.status.state:
                    result["state"] = str(result_project.status.state)
            except (KeyError, AttributeError):
                pass

        return result
    except Exception as e:
        error_msg = str(e)
        if "ALREADY_EXISTS" in error_msg or "already exists" in error_msg.lower():
            return {
                "name": f"projects/{project_id}",
                "status": "ALREADY_EXISTS",
                "error": f"Project '{project_id}' already exists",
            }
        raise Exception(f"Failed to create Lakebase Autoscaling project '{project_id}': {error_msg}")


def get_project(name: str) -> Dict[str, Any]:
    """
    Get Lakebase Autoscaling project details.

    Args:
        name: Project resource name (e.g., "projects/my-app" or "my-app")

    Returns:
        Dictionary with:
        - name: Project resource name
        - display_name: Display name
        - pg_version: Postgres version
        - state: Current state (READY, CREATING, etc.)

    Raises:
        Exception: If API request fails
    """
    client = get_workspace_client()
    full_name = _normalize_project_name(name)

    try:
        project = client.postgres.get_project(name=full_name)
    except Exception as e:
        error_msg = str(e)
        if "not found" in error_msg.lower() or "does not exist" in error_msg.lower() or "404" in error_msg:
            return {
                "name": full_name,
                "state": "NOT_FOUND",
                "error": f"Project '{full_name}' not found",
            }
        raise Exception(f"Failed to get Lakebase Autoscaling project '{full_name}': {error_msg}")

    result: Dict[str, Any] = {"name": project.name}

    if project.status:
        for attr, key, transform in [
            ("display_name", "display_name", None),
            ("pg_version", "pg_version", str),
            ("owner", "owner", None),
        ]:
            try:
                val = getattr(project.status, attr)
                if val is not None:
                    result[key] = transform(val) if transform else val
            except (KeyError, AttributeError):
                pass

    return result


def list_projects() -> List[Dict[str, Any]]:
    """
    List all Lakebase Autoscaling projects in the workspace.

    Returns:
        List of project dictionaries with name, display_name, pg_version, state.

    Raises:
        Exception: If API request fails
    """
    client = get_workspace_client()

    try:
        response = client.postgres.list_projects()
    except Exception as e:
        raise Exception(f"Failed to list Lakebase Autoscaling projects: {str(e)}")

    result = []
    projects = list(response) if response else []
    for proj in projects:
        entry: Dict[str, Any] = {"name": proj.name}

        if proj.status:
            for attr, key, transform in [
                ("display_name", "display_name", None),
                ("pg_version", "pg_version", str),
                ("owner", "owner", None),
            ]:
                try:
                    val = getattr(proj.status, attr)
                    if val is not None:
                        entry[key] = transform(val) if transform else val
                except (KeyError, AttributeError):
                    pass

        result.append(entry)

    return result


def update_project(
    name: str,
    display_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Update a Lakebase Autoscaling project.

    Args:
        name: Project resource name (e.g., "projects/my-app" or "my-app")
        display_name: New display name for the project

    Returns:
        Dictionary with updated project details

    Raises:
        Exception: If update fails
    """
    client = get_workspace_client()
    full_name = _normalize_project_name(name)

    try:
        from databricks.sdk.service.postgres import Project, ProjectSpec, FieldMask

        update_fields = []
        spec_kwargs: Dict[str, Any] = {}

        if display_name is not None:
            spec_kwargs["display_name"] = display_name
            update_fields.append("spec.display_name")

        if not update_fields:
            return {
                "name": full_name,
                "status": "NO_CHANGES",
                "error": "No fields specified for update",
            }

        operation = client.postgres.update_project(
            name=full_name,
            project=Project(
                name=full_name,
                spec=ProjectSpec(**spec_kwargs),
            ),
            update_mask=FieldMask(field_mask=update_fields),
        )
        result_project = operation.wait()

        result: Dict[str, Any] = {
            "name": full_name,
            "status": "UPDATED",
        }

        if display_name is not None:
            result["display_name"] = display_name

        if result_project and result_project.status:
            try:
                if result_project.status.state:
                    result["state"] = str(result_project.status.state)
            except (KeyError, AttributeError):
                pass

        return result
    except Exception as e:
        raise Exception(f"Failed to update Lakebase Autoscaling project '{full_name}': {str(e)}")


def delete_project(name: str) -> Dict[str, Any]:
    """
    Delete a Lakebase Autoscaling project and all its resources.

    WARNING: This permanently deletes all branches, computes, databases,
    roles, and data in the project.

    Args:
        name: Project resource name (e.g., "projects/my-app" or "my-app")

    Returns:
        Dictionary with:
        - name: Project resource name
        - status: "deleted" or error info

    Raises:
        Exception: If deletion fails
    """
    client = get_workspace_client()
    full_name = _normalize_project_name(name)

    try:
        operation = client.postgres.delete_project(name=full_name)
        operation.wait()
        return {
            "name": full_name,
            "status": "deleted",
        }
    except Exception as e:
        error_msg = str(e)
        if "not found" in error_msg.lower() or "does not exist" in error_msg.lower() or "404" in error_msg:
            return {
                "name": full_name,
                "status": "NOT_FOUND",
                "error": f"Project '{full_name}' not found",
            }
        raise Exception(f"Failed to delete Lakebase Autoscaling project '{full_name}': {error_msg}")

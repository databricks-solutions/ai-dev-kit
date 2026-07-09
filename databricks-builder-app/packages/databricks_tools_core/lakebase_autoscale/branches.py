"""
Lakebase Autoscaling Branch Operations

Functions for creating, managing, and deleting branches within
Lakebase Autoscaling projects.
"""

import logging
from typing import Any, Dict, List, Optional

from ..auth import get_workspace_client

logger = logging.getLogger(__name__)


def create_branch(
    project_name: str,
    branch_id: str,
    source_branch: Optional[str] = None,
    ttl_seconds: Optional[int] = None,
    no_expiry: bool = False,
) -> Dict[str, Any]:
    """
    Create a branch in a Lakebase Autoscaling project.

    Args:
        project_name: Project resource name (e.g., "projects/my-app")
        branch_id: Branch identifier (1-63 chars, lowercase letters, digits, hyphens)
        source_branch: Source branch to fork from. If not specified,
            automatically uses the project's default branch.
        ttl_seconds: Time-to-live in seconds (max 30 days = 2592000s).
            Set to create an expiring branch.
        no_expiry: If True, branch never expires. One of ttl_seconds
            or no_expiry must be specified.

    Returns:
        Dictionary with:
        - name: Branch resource name
        - status: Creation status
        - expire_time: Expiration time (if TTL set)

    Raises:
        Exception: If creation fails
    """
    client = get_workspace_client()

    if not project_name.startswith("projects/"):
        project_name = f"projects/{project_name}"

    # Resolve the source branch: use the provided one, or find the default branch
    if source_branch is None:
        branches = list_branches(project_name)
        default_branches = [b for b in branches if b.get("is_default") is True]
        if default_branches:
            source_branch = default_branches[0]["name"]
        elif branches:
            source_branch = branches[0]["name"]
        else:
            raise Exception(f"No branches found in project '{project_name}' to fork from")

    try:
        from databricks.sdk.service.postgres import Branch, BranchSpec, Duration

        spec_kwargs: Dict[str, Any] = {
            "source_branch": source_branch,
        }

        if ttl_seconds is not None:
            spec_kwargs["ttl"] = Duration(seconds=ttl_seconds)
        elif no_expiry:
            spec_kwargs["no_expiry"] = True
        else:
            # Default to no expiry if neither is specified
            spec_kwargs["no_expiry"] = True

        operation = client.postgres.create_branch(
            parent=project_name,
            branch=Branch(spec=BranchSpec(**spec_kwargs)),
            branch_id=branch_id,
        )
        result_branch = operation.wait()

        result: Dict[str, Any] = {
            "name": result_branch.name,
            "status": "CREATED",
        }

        if result_branch.status:
            for attr, key, transform in [
                ("current_state", "state", str),
                ("default", "is_default", None),
                ("is_protected", "is_protected", None),
                ("expire_time", "expire_time", str),
                ("logical_size_bytes", "logical_size_bytes", None),
            ]:
                try:
                    val = getattr(result_branch.status, attr)
                    if val is not None:
                        result[key] = transform(val) if transform else val
                except (KeyError, AttributeError):
                    pass

        return result
    except Exception as e:
        error_msg = str(e)
        if "ALREADY_EXISTS" in error_msg or "already exists" in error_msg.lower():
            return {
                "name": f"{project_name}/branches/{branch_id}",
                "status": "ALREADY_EXISTS",
                "error": f"Branch '{branch_id}' already exists",
            }
        raise Exception(f"Failed to create branch '{branch_id}': {error_msg}")


def get_branch(name: str) -> Dict[str, Any]:
    """
    Get Lakebase Autoscaling branch details.

    Args:
        name: Branch resource name
            (e.g., "projects/my-app/branches/production")

    Returns:
        Dictionary with:
        - name: Branch resource name
        - state: Current state
        - is_default: Whether this is the default branch
        - is_protected: Whether the branch is protected
        - expire_time: Expiration time (if set)
        - logical_size_bytes: Logical data size

    Raises:
        Exception: If API request fails
    """
    client = get_workspace_client()

    try:
        branch = client.postgres.get_branch(name=name)
    except Exception as e:
        error_msg = str(e)
        if "not found" in error_msg.lower() or "does not exist" in error_msg.lower() or "404" in error_msg:
            return {
                "name": name,
                "state": "NOT_FOUND",
                "error": f"Branch '{name}' not found",
            }
        raise Exception(f"Failed to get branch '{name}': {error_msg}")

    result: Dict[str, Any] = {"name": branch.name}

    if branch.status:
        for attr, key, transform in [
            ("current_state", "state", str),
            ("default", "is_default", None),
            ("is_protected", "is_protected", None),
            ("expire_time", "expire_time", str),
            ("logical_size_bytes", "logical_size_bytes", None),
            ("parent_name", "parent_name", None),
        ]:
            try:
                val = getattr(branch.status, attr)
                if val is not None:
                    result[key] = transform(val) if transform else val
            except (KeyError, AttributeError):
                pass

    return result


def list_branches(project_name: str) -> List[Dict[str, Any]]:
    """
    List all branches in a Lakebase Autoscaling project.

    Args:
        project_name: Project resource name (e.g., "projects/my-app")

    Returns:
        List of branch dictionaries with name, state, is_default, is_protected.

    Raises:
        Exception: If API request fails
    """
    client = get_workspace_client()

    if not project_name.startswith("projects/"):
        project_name = f"projects/{project_name}"

    try:
        response = client.postgres.list_branches(parent=project_name)
    except Exception as e:
        raise Exception(f"Failed to list branches for '{project_name}': {str(e)}")

    result = []
    branches = list(response) if response else []
    for br in branches:
        entry: Dict[str, Any] = {"name": br.name}

        if br.status:
            for attr, key, transform in [
                ("current_state", "state", str),
                ("default", "is_default", None),
                ("is_protected", "is_protected", None),
                ("expire_time", "expire_time", str),
            ]:
                try:
                    val = getattr(br.status, attr)
                    if val is not None:
                        entry[key] = transform(val) if transform else val
                except (KeyError, AttributeError):
                    pass

        result.append(entry)

    return result


def update_branch(
    name: str,
    is_protected: Optional[bool] = None,
    ttl_seconds: Optional[int] = None,
    no_expiry: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Update a Lakebase Autoscaling branch (protect or set expiration).

    Args:
        name: Branch resource name
            (e.g., "projects/my-app/branches/production")
        is_protected: Set branch protection status
        ttl_seconds: New TTL in seconds (max 30 days)
        no_expiry: If True, remove expiration

    Returns:
        Dictionary with updated branch details

    Raises:
        Exception: If update fails
    """
    client = get_workspace_client()

    try:
        from databricks.sdk.service.postgres import Branch, BranchSpec, Duration, FieldMask

        spec_kwargs: Dict[str, Any] = {}
        update_fields: list[str] = []

        if is_protected is not None:
            spec_kwargs["is_protected"] = is_protected
            update_fields.append("spec.is_protected")

        if ttl_seconds is not None:
            spec_kwargs["ttl"] = Duration(seconds=ttl_seconds)
            update_fields.append("spec.expiration")
        elif no_expiry is True:
            spec_kwargs["no_expiry"] = True
            update_fields.append("spec.expiration")

        if not update_fields:
            return {
                "name": name,
                "status": "NO_CHANGES",
                "error": "No fields specified for update",
            }

        operation = client.postgres.update_branch(
            name=name,
            branch=Branch(
                name=name,
                spec=BranchSpec(**spec_kwargs),
            ),
            update_mask=FieldMask(field_mask=update_fields),
        )
        result_branch = operation.wait()

        result: Dict[str, Any] = {
            "name": name,
            "status": "UPDATED",
        }

        if is_protected is not None:
            result["is_protected"] = is_protected

        if result_branch and result_branch.status:
            try:
                if result_branch.status.expire_time:
                    result["expire_time"] = str(result_branch.status.expire_time)
            except (KeyError, AttributeError):
                pass

        return result
    except Exception as e:
        raise Exception(f"Failed to update branch '{name}': {str(e)}")


def delete_branch(name: str) -> Dict[str, Any]:
    """
    Delete a Lakebase Autoscaling branch.

    This permanently deletes all databases, roles, computes, and data
    specific to this branch.

    Args:
        name: Branch resource name
            (e.g., "projects/my-app/branches/development")

    Returns:
        Dictionary with:
        - name: Branch resource name
        - status: "deleted" or error info

    Raises:
        Exception: If deletion fails
    """
    client = get_workspace_client()

    try:
        operation = client.postgres.delete_branch(name=name)
        operation.wait()
        return {
            "name": name,
            "status": "deleted",
        }
    except Exception as e:
        error_msg = str(e)
        if "not found" in error_msg.lower() or "does not exist" in error_msg.lower() or "404" in error_msg:
            return {
                "name": name,
                "status": "NOT_FOUND",
                "error": f"Branch '{name}' not found",
            }
        raise Exception(f"Failed to delete branch '{name}': {error_msg}")


# NOTE: reset_branch is not yet available in the Databricks SDK.
# It may be added in a future SDK release.

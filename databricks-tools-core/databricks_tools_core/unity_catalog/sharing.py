"""
Unity Catalog - Delta Sharing Operations

Functions for managing shares, recipients, and providers.
"""

from typing import Any, Dict, List, Optional

from ..auth import get_workspace_client


# --- Shares ---


def list_shares() -> List[Dict[str, Any]]:
    """
    List all shares.

    Returns:
        List of share info dicts

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    shares = list(w.shares.list_shares())
    return [s.as_dict() if hasattr(s, "as_dict") else vars(s) for s in shares]


def get_share(name: str, include_shared_data: bool = True) -> Dict[str, Any]:
    """
    Get details of a share including its shared objects.

    Args:
        name: Name of the share
        include_shared_data: Whether to include shared data objects (default: True)

    Returns:
        Dict with share details and objects

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    result = w.shares.get(name=name, include_shared_data=include_shared_data)
    return result.as_dict() if hasattr(result, "as_dict") else vars(result)


def create_share(
    name: str,
    comment: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a new share.

    Args:
        name: Name for the share
        comment: Optional description

    Returns:
        Dict with created share details

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    kwargs: Dict[str, Any] = {"name": name}
    if comment is not None:
        kwargs["comment"] = comment
    result = w.shares.create(**kwargs)
    return result.as_dict() if hasattr(result, "as_dict") else vars(result)


def add_table_to_share(
    share_name: str,
    table_name: str,
    shared_as: Optional[str] = None,
    partition_spec: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Add a table to a share.

    Args:
        share_name: Name of the share
        table_name: Full table name (catalog.schema.table)
        shared_as: Alias for the shared table (hides internal naming)
        partition_spec: Partition filter (e.g., "(date = '2024-01-01')")

    Returns:
        Dict with updated share details

    Raises:
        DatabricksError: If API request fails
    """
    from databricks.sdk.service.sharing import (
        SharedDataObject,
        SharedDataObjectDataObjectType,
        SharedDataObjectUpdate,
        SharedDataObjectUpdateAction,
    )

    w = get_workspace_client()
    data_object = SharedDataObject(
        name=table_name,
        data_object_type=SharedDataObjectDataObjectType.TABLE,
        shared_as=shared_as,
    )
    if partition_spec:
        from databricks.sdk.service.sharing import Partition, PartitionValue

        data_object.partitions = [
            Partition(
                values=[
                    PartitionValue(name="partition", op="EQUAL", value=partition_spec)
                ]
            )
        ]

    result = w.shares.update(
        name=share_name,
        updates=[
            SharedDataObjectUpdate(
                action=SharedDataObjectUpdateAction.ADD,
                data_object=data_object,
            )
        ],
    )
    return result.as_dict() if hasattr(result, "as_dict") else vars(result)


def remove_table_from_share(
    share_name: str,
    table_name: str,
) -> Dict[str, Any]:
    """
    Remove a table from a share.

    Args:
        share_name: Name of the share
        table_name: Full table name (catalog.schema.table)

    Returns:
        Dict with updated share details

    Raises:
        DatabricksError: If API request fails
    """
    from databricks.sdk.service.sharing import (
        SharedDataObject,
        SharedDataObjectDataObjectType,
        SharedDataObjectUpdate,
        SharedDataObjectUpdateAction,
    )

    w = get_workspace_client()
    result = w.shares.update(
        name=share_name,
        updates=[
            SharedDataObjectUpdate(
                action=SharedDataObjectUpdateAction.REMOVE,
                data_object=SharedDataObject(
                    name=table_name,
                    data_object_type=SharedDataObjectDataObjectType.TABLE,
                ),
            )
        ],
    )
    return result.as_dict() if hasattr(result, "as_dict") else vars(result)


def delete_share(name: str) -> None:
    """
    Delete a share.

    Args:
        name: Name of the share to delete

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    w.shares.delete(name=name)


def grant_share_to_recipient(
    share_name: str,
    recipient_name: str,
) -> Dict[str, Any]:
    """
    Grant SELECT permission on a share to a recipient.

    Args:
        share_name: Name of the share
        recipient_name: Name of the recipient

    Returns:
        Dict with permission update result

    Raises:
        DatabricksError: If API request fails
    """
    from databricks.sdk.service.catalog import Privilege, PermissionsChange

    w = get_workspace_client()
    w.shares.update_permissions(
        name=share_name,
        changes=[
            PermissionsChange(
                principal=recipient_name,
                add=[Privilege.SELECT],
            )
        ],
    )
    return {"status": "granted", "share": share_name, "recipient": recipient_name}


def revoke_share_from_recipient(
    share_name: str,
    recipient_name: str,
) -> Dict[str, Any]:
    """
    Revoke SELECT permission on a share from a recipient.

    Args:
        share_name: Name of the share
        recipient_name: Name of the recipient

    Returns:
        Dict with permission update result

    Raises:
        DatabricksError: If API request fails
    """
    from databricks.sdk.service.catalog import Privilege, PermissionsChange

    w = get_workspace_client()
    w.shares.update_permissions(
        name=share_name,
        changes=[
            PermissionsChange(
                principal=recipient_name,
                remove=[Privilege.SELECT],
            )
        ],
    )
    return {"status": "revoked", "share": share_name, "recipient": recipient_name}


# --- Recipients ---


def list_recipients() -> List[Dict[str, Any]]:
    """
    List all sharing recipients.

    Returns:
        List of recipient info dicts

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    recipients = list(w.recipients.list())
    return [r.as_dict() if hasattr(r, "as_dict") else vars(r) for r in recipients]


def get_recipient(name: str) -> Dict[str, Any]:
    """
    Get a specific recipient.

    Args:
        name: Name of the recipient

    Returns:
        Dict with recipient details

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    result = w.recipients.get(name=name)
    return result.as_dict() if hasattr(result, "as_dict") else vars(result)


def create_recipient(
    name: str,
    authentication_type: str = "TOKEN",
    sharing_id: Optional[str] = None,
    comment: Optional[str] = None,
    ip_access_list: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Create a sharing recipient.

    Args:
        name: Name for the recipient
        authentication_type: "TOKEN" (external) or "DATABRICKS" (D2D sharing)
        sharing_id: Required for DATABRICKS authentication (recipient's sharing identifier)
        comment: Optional description
        ip_access_list: Optional list of allowed IP addresses/CIDR ranges

    Returns:
        Dict with recipient details (includes activation_url for TOKEN type)

    Raises:
        DatabricksError: If API request fails
    """
    from databricks.sdk.service.sharing import AuthenticationType

    w = get_workspace_client()
    kwargs: Dict[str, Any] = {
        "name": name,
        "authentication_type": AuthenticationType(authentication_type.upper()),
    }
    if sharing_id is not None:
        kwargs["sharing_code"] = sharing_id
    if comment is not None:
        kwargs["comment"] = comment
    if ip_access_list is not None:
        from databricks.sdk.service.sharing import IpAccessList

        kwargs["ip_access_list"] = IpAccessList(allowed_ip_addresses=ip_access_list)

    result = w.recipients.create(**kwargs)
    return result.as_dict() if hasattr(result, "as_dict") else vars(result)


def rotate_recipient_token(name: str) -> Dict[str, Any]:
    """
    Rotate the authentication token for a recipient.

    Args:
        name: Name of the recipient

    Returns:
        Dict with new token details

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    result = w.recipients.rotate_token(name=name, existing_token_expire_in_seconds=0)
    return result.as_dict() if hasattr(result, "as_dict") else vars(result)


def delete_recipient(name: str) -> None:
    """
    Delete a sharing recipient.

    Args:
        name: Name of the recipient to delete

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    w.recipients.delete(name=name)


# --- Providers ---


def list_providers() -> List[Dict[str, Any]]:
    """
    List all sharing providers.

    Returns:
        List of provider info dicts

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    providers = list(w.providers.list())
    return [p.as_dict() if hasattr(p, "as_dict") else vars(p) for p in providers]


def get_provider(name: str) -> Dict[str, Any]:
    """
    Get a specific provider.

    Args:
        name: Name of the provider

    Returns:
        Dict with provider details

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    result = w.providers.get(name=name)
    return result.as_dict() if hasattr(result, "as_dict") else vars(result)


def list_provider_shares(name: str) -> List[Dict[str, Any]]:
    """
    List shares available from a provider.

    Args:
        name: Name of the provider

    Returns:
        List of share info dicts

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    shares = list(w.providers.list_shares(name=name))
    return [s.as_dict() if hasattr(s, "as_dict") else vars(s) for s in shares]

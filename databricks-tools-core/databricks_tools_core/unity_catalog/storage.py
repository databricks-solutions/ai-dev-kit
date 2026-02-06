"""
Unity Catalog - Storage Operations

Functions for managing storage credentials and external locations.
"""

from typing import Any, Dict, List, Optional
from databricks.sdk.service.catalog import (
    StorageCredentialInfo,
    ExternalLocationInfo,
    AwsIamRoleRequest,
    AzureManagedIdentityRequest,
)

from ..auth import get_workspace_client


# --- Storage Credentials ---


def list_storage_credentials() -> list[StorageCredentialInfo]:
    """
    List all storage credentials.

    Returns:
        List of StorageCredentialInfo objects

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    return list(w.storage_credentials.list())


def get_storage_credential(name: str) -> StorageCredentialInfo:
    """
    Get a specific storage credential.

    Args:
        name: Name of the storage credential

    Returns:
        StorageCredentialInfo with credential details

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    return w.storage_credentials.get(name=name)


def create_storage_credential(
    name: str,
    comment: str | None = None,
    aws_iam_role_arn: str | None = None,
    azure_access_connector_id: str | None = None,
    read_only: bool = False,
) -> StorageCredentialInfo:
    """
    Create a storage credential for accessing cloud storage.

    Provide exactly one of aws_iam_role_arn or azure_access_connector_id
    based on your cloud provider.

    Args:
        name: Name for the credential
        comment: Optional description
        aws_iam_role_arn: AWS IAM role ARN (for AWS)
        azure_access_connector_id: Azure Access Connector resource ID (for Azure)
        read_only: Whether the credential is read-only

    Returns:
        StorageCredentialInfo with created credential details

    Raises:
        ValueError: If no cloud credential is provided
        DatabricksError: If API request fails
    """
    if not aws_iam_role_arn and not azure_access_connector_id:
        raise ValueError("Provide aws_iam_role_arn (AWS) or azure_access_connector_id (Azure)")

    w = get_workspace_client()
    kwargs: dict[str, Any] = {"name": name, "read_only": read_only}
    if comment is not None:
        kwargs["comment"] = comment
    if aws_iam_role_arn:
        kwargs["aws_iam_role"] = AwsIamRoleRequest(role_arn=aws_iam_role_arn)
    if azure_access_connector_id:
        kwargs["azure_managed_identity"] = AzureManagedIdentityRequest(access_connector_id=azure_access_connector_id)
    return w.storage_credentials.create(**kwargs)


def update_storage_credential(
    name: str,
    new_name: str | None = None,
    comment: str | None = None,
    owner: str | None = None,
    aws_iam_role_arn: str | None = None,
    azure_access_connector_id: str | None = None,
) -> StorageCredentialInfo:
    """
    Update a storage credential.

    Args:
        name: Current name of the credential
        new_name: New name for the credential
        comment: New comment
        owner: New owner
        aws_iam_role_arn: New AWS IAM role ARN
        azure_access_connector_id: New Azure Access Connector ID

    Returns:
        StorageCredentialInfo with updated details

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    kwargs: dict[str, Any] = {"name": name}
    if new_name is not None:
        kwargs["new_name"] = new_name
    if comment is not None:
        kwargs["comment"] = comment
    if owner is not None:
        kwargs["owner"] = owner
    if aws_iam_role_arn:
        kwargs["aws_iam_role"] = AwsIamRoleRequest(role_arn=aws_iam_role_arn)
    if azure_access_connector_id:
        kwargs["azure_managed_identity"] = AzureManagedIdentityRequest(access_connector_id=azure_access_connector_id)
    return w.storage_credentials.update(**kwargs)


def delete_storage_credential(name: str, force: bool = False) -> None:
    """
    Delete a storage credential.

    Args:
        name: Name of the credential to delete
        force: If True, force deletion

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    w.storage_credentials.delete(name=name, force=force)


def validate_storage_credential(
    name: str,
    url: str | None = None,
) -> dict[str, Any]:
    """
    Validate a storage credential against a cloud storage URL.

    Args:
        name: Name of the credential to validate
        url: Cloud storage URL to validate against

    Returns:
        Dict with validation results

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    kwargs: dict[str, Any] = {"storage_credential_name": name}
    if url is not None:
        kwargs["url"] = url
    result = w.storage_credentials.validate(**kwargs)
    return {
        "is_valid": result.is_dir if hasattr(result, "is_dir") else None,
        "results": [
            {
                "operation": r.operation.value if r.operation else None,
                "result": r.result.value if r.result else None,
                "message": r.message,
            }
            for r in (result.results or [])
        ]
        if hasattr(result, "results") and result.results
        else [],
    }


# --- External Locations ---


def list_external_locations() -> list[ExternalLocationInfo]:
    """
    List all external locations.

    Returns:
        List of ExternalLocationInfo objects

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    return list(w.external_locations.list())


def get_external_location(name: str) -> ExternalLocationInfo:
    """
    Get a specific external location.

    Args:
        name: Name of the external location

    Returns:
        ExternalLocationInfo with location details

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    return w.external_locations.get(name=name)


def create_external_location(
    name: str,
    url: str,
    credential_name: str,
    comment: str | None = None,
    read_only: bool = False,
) -> ExternalLocationInfo:
    """
    Create an external location pointing to cloud storage.

    Args:
        name: Name for the external location
        url: Cloud storage URL (s3://, abfss://, gs://)
        credential_name: Name of the storage credential to use
        comment: Optional description
        read_only: Whether location is read-only

    Returns:
        ExternalLocationInfo with created location details

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    kwargs: dict[str, Any] = {
        "name": name,
        "url": url,
        "credential_name": credential_name,
        "read_only": read_only,
    }
    if comment is not None:
        kwargs["comment"] = comment
    return w.external_locations.create(**kwargs)


def update_external_location(
    name: str,
    new_name: str | None = None,
    url: str | None = None,
    credential_name: str | None = None,
    comment: str | None = None,
    owner: str | None = None,
    read_only: bool | None = None,
) -> ExternalLocationInfo:
    """
    Update an external location.

    Args:
        name: Current name of the external location
        new_name: New name
        url: New cloud storage URL
        credential_name: New storage credential name
        comment: New comment
        owner: New owner
        read_only: New read-only setting

    Returns:
        ExternalLocationInfo with updated details

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    kwargs: dict[str, Any] = {"name": name}
    if new_name is not None:
        kwargs["new_name"] = new_name
    if url is not None:
        kwargs["url"] = url
    if credential_name is not None:
        kwargs["credential_name"] = credential_name
    if comment is not None:
        kwargs["comment"] = comment
    if owner is not None:
        kwargs["owner"] = owner
    if read_only is not None:
        kwargs["read_only"] = read_only
    return w.external_locations.update(**kwargs)


def delete_external_location(name: str, force: bool = False) -> None:
    """
    Delete an external location.

    Args:
        name: Name of the external location to delete
        force: If True, force deletion

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    w.external_locations.delete(name=name, force=force)

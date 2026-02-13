"""Unity Catalog provisioning utilities using the Databricks Python SDK.

REFERENCE IMPLEMENTATION — This file is not an importable module. Claude reads it
for patterns and adapts the code inline for user notebooks and scripts.

Catalog creation requires metastore admin privileges and workspace-specific storage
configuration that varies across environments. This module validates that a catalog
exists rather than attempting to create one. Schemas and volumes are created as needed
within the validated catalog.
"""

import logging

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import BadRequest, NotFound, ResourceConflict
from databricks.sdk.service.catalog import VolumeType

logger = logging.getLogger(__name__)


def _get_client(client: WorkspaceClient | None) -> WorkspaceClient:
    """Return the given client or create one from the DEFAULT profile."""
    if client is not None:
        return client
    return WorkspaceClient()


def validate_catalog(
    catalog_name: str,
    *,
    client: WorkspaceClient | None = None,
) -> None:
    """Validate that a Unity Catalog catalog exists.

    Raises ValueError if the catalog does not exist. Catalog creation requires
    metastore admin privileges and workspace-specific storage configuration,
    so it must be done beforehand via the Databricks UI or by an admin.

    Args:
        catalog_name: Name of the catalog to validate.
        client: WorkspaceClient instance. Created from DEFAULT profile if not provided.

    Raises:
        ValueError: If the catalog does not exist.
    """
    ws = _get_client(client)
    try:
        ws.catalogs.get(catalog_name)
        logger.info("Validated catalog exists: %s", catalog_name)
    except NotFound:
        raise ValueError(
            f"Catalog '{catalog_name}' does not exist. "
            f"Create it in the Databricks UI (Catalog > Create Catalog) before running generation."
        )


def ensure_schema(
    catalog_name: str,
    schema_name: str,
    *,
    comment: str | None = None,
    client: WorkspaceClient | None = None,
) -> None:
    """Create a Unity Catalog schema if it doesn't already exist.

    Args:
        catalog_name: Parent catalog name.
        schema_name: Name of the schema to create.
        comment: Optional description for the schema.
        client: WorkspaceClient instance. Created from DEFAULT profile if not provided.
    """
    ws = _get_client(client)
    try:
        ws.schemas.create(name=schema_name, catalog_name=catalog_name, comment=comment)
        logger.info("Created schema: %s.%s", catalog_name, schema_name)
    except (ResourceConflict, BadRequest) as e:
        if "already exists" in str(e).lower():
            logger.debug("Schema already exists: %s.%s", catalog_name, schema_name)
        else:
            raise


def ensure_volume(
    catalog_name: str,
    schema_name: str,
    volume_name: str,
    *,
    volume_type: VolumeType = VolumeType.MANAGED,
    comment: str | None = None,
    client: WorkspaceClient | None = None,
) -> None:
    """Create a Unity Catalog volume if it doesn't already exist.

    Args:
        catalog_name: Parent catalog name.
        schema_name: Parent schema name.
        volume_name: Name of the volume to create.
        volume_type: MANAGED (default) or EXTERNAL.
        comment: Optional description for the volume.
        client: WorkspaceClient instance. Created from DEFAULT profile if not provided.
    """
    ws = _get_client(client)
    try:
        ws.volumes.create(
            catalog_name=catalog_name,
            schema_name=schema_name,
            name=volume_name,
            volume_type=volume_type,
            comment=comment,
        )
        logger.info(
            "Created volume: %s.%s.%s", catalog_name, schema_name, volume_name
        )
    except (ResourceConflict, BadRequest) as e:
        if "already exists" in str(e).lower():
            logger.debug(
                "Volume already exists: %s.%s.%s",
                catalog_name,
                schema_name,
                volume_name,
            )
        else:
            raise


def ensure_uc_path(
    catalog: str,
    schema: str,
    volume: str | None = None,
    *,
    client: WorkspaceClient | None = None,
) -> None:
    """Provision a Unity Catalog path (validate catalog + create schema + optional volume).

    Validates the catalog exists (raises ValueError if not), then creates the schema
    and optional volume as needed.

    Args:
        catalog: Catalog name (must already exist).
        schema: Schema name (created if missing).
        volume: Volume name (created if missing). Skipped if None.
        client: WorkspaceClient instance. Created from DEFAULT profile if not provided.

    Raises:
        ValueError: If the catalog does not exist.
    """
    ws = _get_client(client)
    validate_catalog(catalog, client=ws)
    ensure_schema(catalog, schema, client=ws)
    if volume is not None:
        ensure_volume(catalog, schema, volume, client=ws)

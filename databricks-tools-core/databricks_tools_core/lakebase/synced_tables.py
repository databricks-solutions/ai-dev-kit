"""
Lakebase Synced Table Operations

Functions for creating and managing reverse ETL synced tables that
sync data from Unity Catalog Delta tables to Lakebase PostgreSQL.
"""

import logging
from typing import Any, Dict, List, Optional

from ..auth import get_workspace_client

logger = logging.getLogger(__name__)


def create_synced_table(
    instance_name: str,
    source_table_name: str,
    target_table_name: str,
    primary_key_columns: Optional[List[str]] = None,
    scheduling_policy: str = "TRIGGERED",
) -> Dict[str, Any]:
    """
    Create a synced table to replicate data from a Delta table to Lakebase.

    This enables reverse ETL: syncing processed data from Unity Catalog
    into a PostgreSQL table for low-latency OLTP access.

    Args:
        instance_name: Lakebase instance name
        source_table_name: Fully qualified source Delta table
            (catalog.schema.table_name)
        target_table_name: Fully qualified target Lakebase catalog table
            (catalog.schema.table_name)
        primary_key_columns: List of primary key column names from the source
            table. If not provided, the source table's primary key is used.
        scheduling_policy: Sync mode: "TRIGGERED" (manual sync), "SNAPSHOT"
            (full refresh), or "CONTINUOUS" (real-time). Default: "TRIGGERED"

    Returns:
        Dictionary with:
        - instance_name: Lakebase instance
        - source_table_name: Source Delta table
        - target_table_name: Target PostgreSQL table
        - status: Creation result

    Raises:
        Exception: If creation fails
    """
    client = get_workspace_client()

    try:
        from databricks.sdk.service.database import (
            SyncedDatabaseTable,
            SyncedTableSpec,
            SyncedTableSchedulingPolicy,
        )

        spec_kwargs: Dict[str, Any] = {
            "source_table_full_name": source_table_name,
            "scheduling_policy": SyncedTableSchedulingPolicy(scheduling_policy),
        }

        if primary_key_columns:
            spec_kwargs["primary_key_columns"] = primary_key_columns

        synced_table = SyncedDatabaseTable(
            name=target_table_name,
            database_instance_name=instance_name,
            spec=SyncedTableSpec(**spec_kwargs),
        )

        client.database.create_synced_database_table(synced_table)

        return {
            "instance_name": instance_name,
            "source_table_name": source_table_name,
            "target_table_name": target_table_name,
            "scheduling_policy": scheduling_policy,
            "status": "CREATING",
            "message": (
                f"Synced table creation initiated. Source: '{source_table_name}' -> Target: '{target_table_name}'."
            ),
        }
    except Exception as e:
        error_msg = str(e)
        if "ALREADY_EXISTS" in error_msg or "already exists" in error_msg.lower():
            return {
                "target_table_name": target_table_name,
                "status": "ALREADY_EXISTS",
                "error": f"Synced table '{target_table_name}' already exists",
            }
        raise Exception(f"Failed to create synced table '{target_table_name}': {error_msg}")


def get_synced_table(
    table_name: str,
) -> Dict[str, Any]:
    """
    Get status and details of a synced table.

    Args:
        table_name: Fully qualified synced table name
            (catalog.schema.table_name)

    Returns:
        Dictionary with synced table details including sync status

    Raises:
        Exception: If API request fails
    """
    client = get_workspace_client()

    try:
        table = client.database.get_synced_database_table(name=table_name)
    except Exception as e:
        error_msg = str(e)
        if "not found" in error_msg.lower() or "does not exist" in error_msg.lower() or "404" in error_msg:
            return {
                "table_name": table_name,
                "status": "NOT_FOUND",
                "error": f"Synced table '{table_name}' not found",
            }
        raise Exception(f"Failed to get synced table '{table_name}': {error_msg}")

    result: Dict[str, Any] = {"table_name": table_name}

    if hasattr(table, "database_instance_name") and table.database_instance_name:
        result["instance_name"] = table.database_instance_name

    if hasattr(table, "spec") and table.spec:
        if hasattr(table.spec, "source_table_full_name") and table.spec.source_table_full_name:
            result["source_table_name"] = table.spec.source_table_full_name
        if hasattr(table.spec, "scheduling_policy") and table.spec.scheduling_policy:
            result["scheduling_policy"] = str(table.spec.scheduling_policy.value)
        if hasattr(table.spec, "primary_key_columns") and table.spec.primary_key_columns:
            result["primary_key_columns"] = table.spec.primary_key_columns

    if hasattr(table, "status") and table.status:
        result["status"] = str(table.status)

    return result


def delete_synced_table(
    table_name: str,
) -> Dict[str, Any]:
    """
    Delete a synced table.

    This stops syncing and removes the target table from Lakebase.
    The source Delta table is not affected.

    Args:
        table_name: Fully qualified synced table name
            (catalog.schema.table_name)

    Returns:
        Dictionary with:
        - table_name: Synced table name
        - status: "deleted" or error info

    Raises:
        Exception: If deletion fails
    """
    client = get_workspace_client()

    try:
        client.database.delete_synced_database_table(name=table_name)
        return {
            "table_name": table_name,
            "status": "deleted",
        }
    except Exception as e:
        error_msg = str(e)
        if "not found" in error_msg.lower() or "does not exist" in error_msg.lower() or "404" in error_msg:
            return {
                "table_name": table_name,
                "status": "NOT_FOUND",
                "error": f"Synced table '{table_name}' not found",
            }
        raise Exception(f"Failed to delete synced table '{table_name}': {error_msg}")

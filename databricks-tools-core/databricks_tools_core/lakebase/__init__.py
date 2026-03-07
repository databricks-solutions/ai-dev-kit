"""
Lakebase Provisioned Operations

Functions for managing Databricks Lakebase Provisioned (managed PostgreSQL)
instances, Unity Catalog registration, and reverse ETL synced tables.
"""

from .instances import (
    create_lakebase_instance,
    get_lakebase_instance,
    list_lakebase_instances,
    update_lakebase_instance,
    delete_lakebase_instance,
    generate_lakebase_credential,
)
from .catalogs import (
    create_lakebase_catalog,
    get_lakebase_catalog,
    delete_lakebase_catalog,
)
from .synced_tables import (
    create_synced_table,
    get_synced_table,
    delete_synced_table,
)

__all__ = [
    # Instances
    "create_lakebase_instance",
    "get_lakebase_instance",
    "list_lakebase_instances",
    "update_lakebase_instance",
    "delete_lakebase_instance",
    "generate_lakebase_credential",
    # Catalogs
    "create_lakebase_catalog",
    "get_lakebase_catalog",
    "delete_lakebase_catalog",
    # Synced Tables
    "create_synced_table",
    "get_synced_table",
    "delete_synced_table",
]

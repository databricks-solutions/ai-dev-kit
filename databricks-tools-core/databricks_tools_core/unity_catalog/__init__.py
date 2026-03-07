"""
Unity Catalog Operations

Functions for managing Unity Catalog objects, permissions, storage,
governance metadata, monitors, and data sharing.
"""

# Catalogs
from .catalogs import (
    list_catalogs,
    get_catalog,
    create_catalog,
    update_catalog,
    delete_catalog,
)

# Schemas
from .schemas import (
    list_schemas,
    get_schema,
    create_schema,
    update_schema,
    delete_schema,
)

# Tables
from .tables import (
    list_tables,
    get_table,
    create_table,
    delete_table,
)

# Volumes
from .volumes import (
    list_volumes,
    get_volume,
    create_volume,
    update_volume,
    delete_volume,
)

# Volume Files
from .volume_files import (
    VolumeFileInfo,
    VolumeUploadResult,
    VolumeDownloadResult,
    list_volume_files,
    upload_to_volume,
    download_from_volume,
    delete_volume_file,
    delete_volume_directory,
    create_volume_directory,
    get_volume_file_metadata,
)

# Functions
from .functions_uc import (
    list_functions,
    get_function,
    delete_function,
)

# Grants
from .grants import (
    grant_privileges,
    revoke_privileges,
    get_grants,
    get_effective_grants,
)

# Storage credentials and external locations
from .storage import (
    list_storage_credentials,
    get_storage_credential,
    create_storage_credential,
    update_storage_credential,
    delete_storage_credential,
    validate_storage_credential,
    list_external_locations,
    get_external_location,
    create_external_location,
    update_external_location,
    delete_external_location,
)

# Connections (Lakehouse Federation)
from .connections import (
    list_connections,
    get_connection,
    create_connection,
    update_connection,
    delete_connection,
    create_foreign_catalog,
)

# Tags and comments
from .tags import (
    set_tags,
    unset_tags,
    set_comment,
    query_table_tags,
    query_column_tags,
)

# Security policies (RLS, column masking)
from .security_policies import (
    create_security_function,
    set_row_filter,
    drop_row_filter,
    set_column_mask,
    drop_column_mask,
)

# Quality monitors
from .monitors import (
    create_monitor,
    get_monitor,
    run_monitor_refresh,
    list_monitor_refreshes,
    delete_monitor,
)

# Metric Views
from .metric_views import (
    create_metric_view,
    alter_metric_view,
    drop_metric_view,
    describe_metric_view,
    query_metric_view,
    grant_metric_view,
)

# Delta Sharing
from .sharing import (
    list_shares,
    get_share,
    create_share,
    add_table_to_share,
    remove_table_from_share,
    delete_share,
    grant_share_to_recipient,
    revoke_share_from_recipient,
    list_recipients,
    get_recipient,
    create_recipient,
    rotate_recipient_token,
    delete_recipient,
    list_providers,
    get_provider,
    list_provider_shares,
)

__all__ = [
    # Catalogs
    "list_catalogs",
    "get_catalog",
    "create_catalog",
    "update_catalog",
    "delete_catalog",
    # Schemas
    "list_schemas",
    "get_schema",
    "create_schema",
    "update_schema",
    "delete_schema",
    # Tables
    "list_tables",
    "get_table",
    "create_table",
    "delete_table",
    # Volumes
    "list_volumes",
    "get_volume",
    "create_volume",
    "update_volume",
    "delete_volume",
    # Volume Files
    "VolumeFileInfo",
    "VolumeUploadResult",
    "VolumeDownloadResult",
    "list_volume_files",
    "upload_to_volume",
    "download_from_volume",
    "delete_volume_file",
    "delete_volume_directory",
    "create_volume_directory",
    "get_volume_file_metadata",
    # Functions
    "list_functions",
    "get_function",
    "delete_function",
    # Grants
    "grant_privileges",
    "revoke_privileges",
    "get_grants",
    "get_effective_grants",
    # Storage
    "list_storage_credentials",
    "get_storage_credential",
    "create_storage_credential",
    "update_storage_credential",
    "delete_storage_credential",
    "validate_storage_credential",
    "list_external_locations",
    "get_external_location",
    "create_external_location",
    "update_external_location",
    "delete_external_location",
    # Connections
    "list_connections",
    "get_connection",
    "create_connection",
    "update_connection",
    "delete_connection",
    "create_foreign_catalog",
    # Tags and comments
    "set_tags",
    "unset_tags",
    "set_comment",
    "query_table_tags",
    "query_column_tags",
    # Security policies
    "create_security_function",
    "set_row_filter",
    "drop_row_filter",
    "set_column_mask",
    "drop_column_mask",
    # Quality monitors
    "create_monitor",
    "get_monitor",
    "run_monitor_refresh",
    "list_monitor_refreshes",
    "delete_monitor",
    # Metric Views
    "create_metric_view",
    "alter_metric_view",
    "drop_metric_view",
    "describe_metric_view",
    "query_metric_view",
    "grant_metric_view",
    # Sharing
    "list_shares",
    "get_share",
    "create_share",
    "add_table_to_share",
    "remove_table_from_share",
    "delete_share",
    "grant_share_to_recipient",
    "revoke_share_from_recipient",
    "list_recipients",
    "get_recipient",
    "create_recipient",
    "rotate_recipient_token",
    "delete_recipient",
    "list_providers",
    "get_provider",
    "list_provider_shares",
]

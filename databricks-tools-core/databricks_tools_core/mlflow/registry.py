"""
MLflow Model Registry (Unity Catalog)

Functions for managing registered models and model versions
via the Unity Catalog model registry APIs.
"""

import logging
from typing import Any, Dict, List, Optional

from databricks.sdk.errors import NotFound, ResourceDoesNotExist

from ..auth import get_workspace_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _model_to_dict(model) -> Dict[str, Any]:
    """Convert a RegisteredModelInfo SDK object to a user-friendly dict."""
    aliases = []
    for a in model.aliases or []:
        aliases.append({"alias_name": a.alias_name, "version_number": a.version_number})

    return {
        "full_name": model.full_name,
        "name": model.name,
        "catalog_name": model.catalog_name,
        "schema_name": model.schema_name,
        "comment": model.comment,
        "owner": model.owner,
        "created_at": model.created_at,
        "created_by": model.created_by,
        "updated_at": model.updated_at,
        "updated_by": model.updated_by,
        "storage_location": model.storage_location,
        "aliases": aliases,
    }


def _version_to_dict(version) -> Dict[str, Any]:
    """Convert a ModelVersionInfo SDK object to a user-friendly dict."""
    status = version.status
    if status is not None and hasattr(status, "value"):
        status = status.value

    aliases = []
    for a in version.aliases or []:
        aliases.append({"alias_name": a.alias_name, "version_number": a.version_number})

    # Build full_name from components (SDK doesn't provide it directly)
    full_name = f"{version.catalog_name}.{version.schema_name}.{version.model_name}"

    return {
        "full_name": full_name,
        "version": version.version,
        "model_name": version.model_name,
        "catalog_name": version.catalog_name,
        "schema_name": version.schema_name,
        "source": version.source,
        "run_id": version.run_id,
        "status": status,
        "comment": version.comment,
        "created_at": version.created_at,
        "created_by": version.created_by,
        "updated_at": version.updated_at,
        "updated_by": version.updated_by,
        "storage_location": version.storage_location,
        "aliases": aliases,
    }


# ---------------------------------------------------------------------------
# Registered Models
# ---------------------------------------------------------------------------


def get_registered_model(
    full_name: str,
    include_aliases: bool = True,
) -> Dict[str, Any]:
    """
    Get a registered model from Unity Catalog.

    Args:
        full_name: Three-level name (catalog.schema.model)
        include_aliases: Whether to include alias information (default: True)

    Returns:
        Dictionary with model details:
        - full_name: Three-level name
        - name: Model name (without catalog/schema)
        - catalog_name: Catalog
        - schema_name: Schema
        - comment: Model description
        - owner: Owner principal
        - aliases: List of alias dicts with alias_name and version_number
        - created_at/updated_at: Timestamps (ms)
    """
    client = get_workspace_client()

    try:
        model = client.registered_models.get(
            full_name=full_name,
            include_aliases=include_aliases,
        )
    except (ResourceDoesNotExist, NotFound):
        return {"error": f"Model '{full_name}' not found", "status": "NOT_FOUND"}
    except Exception as e:
        raise Exception(f"Failed to get model '{full_name}': {e}")

    return _model_to_dict(model)


def list_registered_models(
    catalog_name: Optional[str] = None,
    schema_name: Optional[str] = None,
    max_results: int = 50,
) -> Dict[str, Any]:
    """
    List registered models in Unity Catalog.

    Args:
        catalog_name: Filter by catalog (optional)
        schema_name: Filter by schema (requires catalog_name)
        max_results: Maximum models to return (default: 50)

    Returns:
        Dictionary with:
        - models: List of model dicts
        - count: Number of models returned
    """
    client = get_workspace_client()

    try:
        kwargs: Dict[str, Any] = {"max_results": max_results}
        if catalog_name:
            kwargs["catalog_name"] = catalog_name
        if schema_name:
            kwargs["schema_name"] = schema_name

        models_iter = client.registered_models.list(**kwargs)
        models = []
        for model in models_iter:
            models.append(_model_to_dict(model))
            if len(models) >= max_results:
                break
    except Exception as e:
        raise Exception(f"Failed to list registered models: {e}")

    return {"models": models, "count": len(models)}


def search_registered_models(
    filter_string: Optional[str] = None,
    max_results: int = 50,
    order_by: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Search registered models in the legacy workspace registry.

    Note: Unity Catalog models use list with catalog/schema filters.
    This function searches the legacy workspace model registry.

    Args:
        filter_string: Filter expression (e.g. "name LIKE '%churn%'")
        max_results: Maximum models to return (default: 50)
        order_by: Sort order (e.g. ["name ASC", "last_updated_timestamp DESC"])

    Returns:
        Dictionary with:
        - models: List of model dicts with name, description, tags, versions
        - count: Number of models returned
    """
    client = get_workspace_client()

    try:
        models_iter = client.model_registry.search_models(
            filter=filter_string,
            max_results=max_results,
            order_by=order_by,
        )
        models = []
        for model in models_iter:
            latest_versions = []
            for v in model.latest_versions or []:
                stage = v.current_stage
                if stage and hasattr(stage, "value"):
                    stage = stage.value
                latest_versions.append(
                    {
                        "version": v.version,
                        "current_stage": stage,
                        "status": v.status.value if v.status and hasattr(v.status, "value") else v.status,
                        "run_id": v.run_id,
                        "source": v.source,
                        "creation_timestamp": v.creation_timestamp,
                    }
                )

            tags = {}
            for t in model.tags or []:
                tags[t.key] = t.value

            models.append(
                {
                    "name": model.name,
                    "description": model.description,
                    "creation_timestamp": model.creation_timestamp,
                    "last_updated_timestamp": model.last_updated_timestamp,
                    "user_id": model.user_id,
                    "tags": tags,
                    "latest_versions": latest_versions,
                }
            )
            if len(models) >= max_results:
                break
    except Exception as e:
        raise Exception(f"Failed to search models: {e}")

    return {"models": models, "count": len(models)}


# ---------------------------------------------------------------------------
# Model Versions
# ---------------------------------------------------------------------------


def get_model_version(
    full_name: str,
    version: int,
    include_aliases: bool = True,
) -> Dict[str, Any]:
    """
    Get a specific model version from Unity Catalog.

    Args:
        full_name: Three-level model name (catalog.schema.model)
        version: Version number
        include_aliases: Whether to include alias information (default: True)

    Returns:
        Dictionary with version details:
        - full_name: Three-level model name
        - version: Version number
        - source: Source artifact location
        - run_id: MLflow run that produced this version
        - status: PENDING_REGISTRATION, READY, FAILED_REGISTRATION, etc.
        - comment: Version description
        - aliases: List of alias dicts
        - created_at/updated_at: Timestamps (ms)
    """
    client = get_workspace_client()

    try:
        version_info = client.model_versions.get(
            full_name=full_name,
            version=version,
            include_aliases=include_aliases,
        )
    except (ResourceDoesNotExist, NotFound):
        return {"error": f"Model version '{full_name}' v{version} not found", "status": "NOT_FOUND"}
    except Exception as e:
        raise Exception(f"Failed to get model version: {e}")

    return _version_to_dict(version_info)


def list_model_versions(
    full_name: str,
    max_results: int = 50,
) -> Dict[str, Any]:
    """
    List all versions of a registered model in Unity Catalog.

    Args:
        full_name: Three-level model name (catalog.schema.model)
        max_results: Maximum versions to return (default: 50)

    Returns:
        Dictionary with:
        - full_name: The model name
        - versions: List of version dicts
        - count: Number of versions returned
    """
    client = get_workspace_client()

    try:
        versions_iter = client.model_versions.list(
            full_name=full_name,
            max_results=max_results,
        )
        versions = []
        for v in versions_iter:
            versions.append(_version_to_dict(v))
            if len(versions) >= max_results:
                break
    except (ResourceDoesNotExist, NotFound):
        return {"error": f"Model '{full_name}' not found", "status": "NOT_FOUND"}
    except Exception as e:
        raise Exception(f"Failed to list model versions: {e}")

    return {"full_name": full_name, "versions": versions, "count": len(versions)}


def get_model_version_by_alias(
    full_name: str,
    alias: str,
) -> Dict[str, Any]:
    """
    Get a model version by its alias (e.g. "champion", "challenger").

    Args:
        full_name: Three-level model name (catalog.schema.model)
        alias: Alias name (e.g. "champion", "production")

    Returns:
        Dictionary with version details (same as get_model_version)
    """
    client = get_workspace_client()

    try:
        version_info = client.model_versions.get_by_alias(
            full_name=full_name,
            alias=alias,
        )
    except (ResourceDoesNotExist, NotFound):
        return {"error": f"Alias '{alias}' not found for model '{full_name}'", "status": "NOT_FOUND"}
    except Exception as e:
        raise Exception(f"Failed to get model version by alias: {e}")

    return _version_to_dict(version_info)


def set_model_alias(
    full_name: str,
    alias: str,
    version_num: int,
) -> Dict[str, Any]:
    """
    Set an alias on a model version (e.g. "champion", "challenger").

    Aliases provide a mutable reference to a specific version.
    If the alias already exists, it is reassigned to the new version.

    Args:
        full_name: Three-level model name (catalog.schema.model)
        alias: Alias name to set
        version_num: Version number to point the alias to

    Returns:
        Dictionary with:
        - full_name: Model name
        - alias: Alias name
        - version_num: Version number
        - status: "set"
    """
    client = get_workspace_client()

    try:
        client.registered_models.set_alias(
            full_name=full_name,
            alias=alias,
            version_num=version_num,
        )
    except (ResourceDoesNotExist, NotFound):
        return {"error": f"Model '{full_name}' or version {version_num} not found", "status": "NOT_FOUND"}
    except Exception as e:
        raise Exception(f"Failed to set alias: {e}")

    return {
        "full_name": full_name,
        "alias": alias,
        "version_num": version_num,
        "status": "set",
    }


def delete_model_alias(
    full_name: str,
    alias: str,
) -> Dict[str, Any]:
    """
    Remove an alias from a registered model.

    Args:
        full_name: Three-level model name (catalog.schema.model)
        alias: Alias name to remove

    Returns:
        Dictionary with:
        - full_name: Model name
        - alias: Alias removed
        - status: "deleted" or "not_found"
    """
    client = get_workspace_client()

    try:
        client.registered_models.delete_alias(
            full_name=full_name,
            alias=alias,
        )
    except (ResourceDoesNotExist, NotFound):
        return {"error": f"Alias '{alias}' not found for model '{full_name}'", "status": "NOT_FOUND"}
    except Exception as e:
        raise Exception(f"Failed to delete alias: {e}")

    return {
        "full_name": full_name,
        "alias": alias,
        "status": "deleted",
    }

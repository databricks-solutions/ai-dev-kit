"""
Compute - Manage Compute Resources

Functions for creating, modifying, and deleting Databricks clusters and SQL warehouses.
Uses Databricks SDK for all operations.
"""

import logging
from typing import Optional, List, Dict, Any

from databricks.sdk.service.compute import (
    AutoScale,
    DataSecurityMode,
)

from ..auth import get_workspace_client

logger = logging.getLogger(__name__)


# --- Clusters ---


def _get_latest_lts_spark_version(w) -> str:
    """Pick the latest LTS Databricks Runtime version.

    Falls back to the latest non-ML, non-GPU, non-Photon LTS version,
    or the first available version if no LTS is found.
    """
    versions = w.clusters.spark_versions()
    lts_versions = []
    for v in versions.versions:
        key = v.key or ""
        name = (v.name or "").lower()
        # Skip ML, GPU, Photon, and aarch64 runtimes
        if any(tag in key for tag in ("-ml-", "-gpu-", "-photon-", "-aarch64-")):
            continue
        if "lts" in name:
            lts_versions.append(v)

    if lts_versions:
        # Sort by key descending to get latest
        lts_versions.sort(key=lambda v: v.key, reverse=True)
        return lts_versions[0].key

    # Fallback: first available version
    if versions.versions:
        return versions.versions[0].key

    raise RuntimeError("No Spark versions available in this workspace")


def _get_default_node_type(w) -> str:
    """Pick a reasonable default node type for the current cloud.

    Prefers memory-optimized, mid-size instances. Falls back to the
    smallest available node type.
    """
    node_types = w.clusters.list_node_types()

    # Common sensible defaults by cloud
    preferred = [
        "i3.xlarge",          # AWS
        "Standard_DS3_v2",    # Azure
        "n1-highmem-4",       # GCP
        "Standard_D4ds_v5",   # Azure newer
        "m5d.xlarge",         # AWS newer
    ]

    available_ids = {nt.node_type_id for nt in node_types.node_types}

    for pref in preferred:
        if pref in available_ids:
            return pref

    # Fallback: pick smallest available node type by memory
    if node_types.node_types:
        sorted_types = sorted(
            node_types.node_types,
            key=lambda nt: getattr(nt, "memory_mb", 0) or 0,
        )
        # Skip types with 0 memory (metadata-only entries)
        for nt in sorted_types:
            if (getattr(nt, "memory_mb", 0) or 0) > 0:
                return nt.node_type_id
        return sorted_types[0].node_type_id

    raise RuntimeError("No node types available in this workspace")


def create_cluster(
    name: str,
    num_workers: int = 1,
    spark_version: Optional[str] = None,
    node_type_id: Optional[str] = None,
    driver_node_type_id: Optional[str] = None,
    autotermination_minutes: int = 120,
    data_security_mode: Optional[str] = None,
    single_user_name: Optional[str] = None,
    spark_conf: Optional[Dict[str, str]] = None,
    autoscale_min_workers: Optional[int] = None,
    autoscale_max_workers: Optional[int] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Create a new Databricks cluster with sensible defaults.

    Provides opinionated defaults so ``create_cluster(name="my-cluster", num_workers=1)``
    just works — auto-picks the latest LTS DBR, a reasonable node type, single-user
    security mode, and 120-minute auto-termination.

    Power users can override any parameter or pass additional SDK parameters via kwargs.

    Args:
        name: Human-readable cluster name.
        num_workers: Fixed number of workers (ignored if autoscale is set). Default 1.
        spark_version: DBR version key (e.g. "15.4.x-scala2.12"). Auto-picks latest LTS if omitted.
        node_type_id: Worker node type (e.g. "i3.xlarge"). Auto-picked if omitted.
        driver_node_type_id: Driver node type. Defaults to same as worker.
        autotermination_minutes: Minutes of inactivity before auto-termination. Default 120.
        data_security_mode: Security mode string ("SINGLE_USER", "USER_ISOLATION", etc.).
            Defaults to SINGLE_USER.
        single_user_name: User for SINGLE_USER mode. Auto-detected if omitted.
        spark_conf: Spark configuration overrides.
        autoscale_min_workers: If set (with autoscale_max_workers), enables autoscaling
            instead of fixed num_workers.
        autoscale_max_workers: Maximum workers for autoscaling.
        **kwargs: Additional parameters passed directly to the SDK clusters.create() call.

    Returns:
        Dict with cluster_id, cluster_name, state, and message.
    """
    w = get_workspace_client()

    # Auto-pick defaults
    if spark_version is None:
        spark_version = _get_latest_lts_spark_version(w)
    if node_type_id is None:
        node_type_id = _get_default_node_type(w)
    if driver_node_type_id is None:
        driver_node_type_id = node_type_id

    # Security mode defaults
    if data_security_mode is None:
        dsm = DataSecurityMode.SINGLE_USER
    else:
        dsm = DataSecurityMode(data_security_mode)

    if dsm == DataSecurityMode.SINGLE_USER and single_user_name is None:
        from ..auth import get_current_username
        single_user_name = get_current_username()

    # Build create kwargs
    create_kwargs = {
        "cluster_name": name,
        "spark_version": spark_version,
        "node_type_id": node_type_id,
        "driver_node_type_id": driver_node_type_id,
        "autotermination_minutes": autotermination_minutes,
        "data_security_mode": dsm,
    }

    if single_user_name:
        create_kwargs["single_user_name"] = single_user_name
    if spark_conf:
        create_kwargs["spark_conf"] = spark_conf

    # Autoscale vs fixed workers
    if autoscale_min_workers is not None and autoscale_max_workers is not None:
        create_kwargs["autoscale"] = AutoScale(
            min_workers=autoscale_min_workers,
            max_workers=autoscale_max_workers,
        )
    else:
        create_kwargs["num_workers"] = num_workers

    # Merge any extra SDK parameters
    create_kwargs.update(kwargs)

    # Create the cluster (non-blocking — returns immediately)
    wait = w.clusters.create(**create_kwargs)
    cluster_id = wait.cluster_id

    return {
        "cluster_id": cluster_id,
        "cluster_name": name,
        "state": "PENDING",
        "spark_version": spark_version,
        "node_type_id": node_type_id,
        "message": (
            f"Cluster '{name}' is being created (cluster_id='{cluster_id}'). "
            f"It typically takes 3-8 minutes to start. "
            f"Use get_cluster_status(cluster_id='{cluster_id}') to check progress."
        ),
    }


def modify_cluster(
    cluster_id: str,
    name: Optional[str] = None,
    num_workers: Optional[int] = None,
    spark_version: Optional[str] = None,
    node_type_id: Optional[str] = None,
    driver_node_type_id: Optional[str] = None,
    autotermination_minutes: Optional[int] = None,
    spark_conf: Optional[Dict[str, str]] = None,
    autoscale_min_workers: Optional[int] = None,
    autoscale_max_workers: Optional[int] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Modify an existing Databricks cluster configuration.

    Fetches the current config, applies the requested changes, and calls the
    edit API. The cluster will restart if it is running.

    Args:
        cluster_id: ID of the cluster to modify.
        name: New cluster name (optional).
        num_workers: New fixed worker count (optional).
        spark_version: New DBR version (optional).
        node_type_id: New worker node type (optional).
        driver_node_type_id: New driver node type (optional).
        autotermination_minutes: New auto-termination timeout (optional).
        spark_conf: Spark configuration overrides (optional).
        autoscale_min_workers: Set to enable/modify autoscaling (optional).
        autoscale_max_workers: Set to enable/modify autoscaling (optional).
        **kwargs: Additional SDK parameters.

    Returns:
        Dict with cluster_id, cluster_name, state, and message.
    """
    w = get_workspace_client()

    # Get current cluster config
    cluster = w.clusters.get(cluster_id)

    # Build edit kwargs from current config
    edit_kwargs = {
        "cluster_id": cluster_id,
        "cluster_name": name or cluster.cluster_name,
        "spark_version": spark_version or cluster.spark_version,
        "node_type_id": node_type_id or cluster.node_type_id,
        "driver_node_type_id": driver_node_type_id or cluster.driver_node_type_id or cluster.node_type_id,
    }

    if autotermination_minutes is not None:
        edit_kwargs["autotermination_minutes"] = autotermination_minutes
    elif cluster.autotermination_minutes:
        edit_kwargs["autotermination_minutes"] = cluster.autotermination_minutes

    if spark_conf is not None:
        edit_kwargs["spark_conf"] = spark_conf
    elif cluster.spark_conf:
        edit_kwargs["spark_conf"] = cluster.spark_conf

    # Handle data_security_mode and single_user_name from existing config
    if cluster.data_security_mode:
        edit_kwargs["data_security_mode"] = cluster.data_security_mode
    if cluster.single_user_name:
        edit_kwargs["single_user_name"] = cluster.single_user_name

    # Autoscale vs fixed workers
    if autoscale_min_workers is not None and autoscale_max_workers is not None:
        edit_kwargs["autoscale"] = AutoScale(
            min_workers=autoscale_min_workers,
            max_workers=autoscale_max_workers,
        )
    elif num_workers is not None:
        edit_kwargs["num_workers"] = num_workers
    elif cluster.autoscale:
        edit_kwargs["autoscale"] = cluster.autoscale
    else:
        edit_kwargs["num_workers"] = cluster.num_workers or 0

    # Merge extra SDK params
    edit_kwargs.update(kwargs)

    w.clusters.edit(**edit_kwargs)

    current_state = cluster.state.value if cluster.state else "UNKNOWN"
    cluster_name = edit_kwargs["cluster_name"]

    return {
        "cluster_id": cluster_id,
        "cluster_name": cluster_name,
        "state": current_state,
        "message": (
            f"Cluster '{cluster_name}' configuration updated. "
            + (
                "The cluster will restart to apply changes."
                if current_state == "RUNNING"
                else "Changes will take effect when the cluster starts."
            )
        ),
    }


def terminate_cluster(cluster_id: str) -> Dict[str, Any]:
    """Stop a running Databricks cluster (reversible).

    The cluster is terminated but not deleted. It can be restarted later
    with start_cluster(). This is a safe, reversible operation.

    Args:
        cluster_id: ID of the cluster to terminate.

    Returns:
        Dict with cluster_id, cluster_name, state, and message.
    """
    w = get_workspace_client()
    cluster = w.clusters.get(cluster_id)
    cluster_name = cluster.cluster_name or cluster_id
    current_state = cluster.state.value if cluster.state else "UNKNOWN"

    if current_state == "TERMINATED":
        return {
            "cluster_id": cluster_id,
            "cluster_name": cluster_name,
            "state": "TERMINATED",
            "message": f"Cluster '{cluster_name}' is already terminated.",
        }

    w.clusters.delete(cluster_id)  # SDK's delete = terminate (confusing but correct)

    return {
        "cluster_id": cluster_id,
        "cluster_name": cluster_name,
        "previous_state": current_state,
        "state": "TERMINATING",
        "message": f"Cluster '{cluster_name}' is being terminated. This is reversible — use start_cluster() to restart.",
    }


def delete_cluster(cluster_id: str) -> Dict[str, Any]:
    """Permanently delete a Databricks cluster.

    WARNING: This action is PERMANENT and cannot be undone. The cluster
    and its configuration will be permanently removed.

    Args:
        cluster_id: ID of the cluster to permanently delete.

    Returns:
        Dict with cluster_id, cluster_name, and warning message.
    """
    w = get_workspace_client()
    cluster = w.clusters.get(cluster_id)
    cluster_name = cluster.cluster_name or cluster_id

    w.clusters.permanent_delete(cluster_id)

    return {
        "cluster_id": cluster_id,
        "cluster_name": cluster_name,
        "state": "DELETED",
        "message": (
            f"WARNING: Cluster '{cluster_name}' has been PERMANENTLY deleted. "
            f"This action cannot be undone. The cluster configuration is gone."
        ),
    }


def list_node_types() -> List[Dict[str, Any]]:
    """List available VM/node types for cluster creation.

    Returns a summary of each node type including ID, memory, cores,
    and GPU info. Useful for choosing node_type_id when creating clusters.

    Returns:
        List of node type info dicts.
    """
    w = get_workspace_client()
    result = w.clusters.list_node_types()

    node_types = []
    for nt in result.node_types:
        node_types.append({
            "node_type_id": nt.node_type_id,
            "memory_mb": nt.memory_mb,
            "num_cores": getattr(nt, "num_cores", None),
            "num_gpus": getattr(nt, "num_gpus", None) or 0,
            "description": getattr(nt, "description", None) or nt.node_type_id,
            "is_deprecated": getattr(nt, "is_deprecated", False),
        })
    return node_types


def list_spark_versions() -> List[Dict[str, Any]]:
    """List available Databricks Runtime (Spark) versions.

    Returns version key and name. Filter for "LTS" in the name to find
    long-term support versions.

    Returns:
        List of dicts with key and name for each version.
    """
    w = get_workspace_client()
    result = w.clusters.spark_versions()

    versions = []
    for v in result.versions:
        versions.append({
            "key": v.key,
            "name": v.name,
        })
    return versions


# --- SQL Warehouses ---


def create_sql_warehouse(
    name: str,
    size: str = "Small",
    min_num_clusters: int = 1,
    max_num_clusters: int = 1,
    auto_stop_mins: int = 120,
    warehouse_type: str = "PRO",
    enable_serverless: bool = True,
    **kwargs,
) -> Dict[str, Any]:
    """Create a new SQL warehouse with sensible defaults.

    By default creates a serverless Pro warehouse with auto-stop at 120 minutes.

    Args:
        name: Human-readable warehouse name.
        size: T-shirt size ("2X-Small", "X-Small", "Small", "Medium", "Large",
            "X-Large", "2X-Large", "3X-Large", "4X-Large"). Default "Small".
        min_num_clusters: Minimum number of clusters. Default 1.
        max_num_clusters: Maximum number of clusters for scaling. Default 1.
        auto_stop_mins: Minutes of inactivity before auto-stop. Default 120.
        warehouse_type: "PRO", "CLASSIC", or "TYPE_UNSPECIFIED". Default "PRO".
        enable_serverless: Enable serverless compute. Default True.
        **kwargs: Additional SDK parameters.

    Returns:
        Dict with warehouse_id, name, state, and message.
    """
    w = get_workspace_client()

    from databricks.sdk.service.sql import (
        CreateWarehouseRequestWarehouseType,
    )

    # Map warehouse type string to enum
    type_map = {
        "PRO": CreateWarehouseRequestWarehouseType.PRO,
        "CLASSIC": CreateWarehouseRequestWarehouseType.CLASSIC,
        "TYPE_UNSPECIFIED": CreateWarehouseRequestWarehouseType.TYPE_UNSPECIFIED,
    }
    wh_type = type_map.get(warehouse_type.upper(), CreateWarehouseRequestWarehouseType.PRO)

    create_kwargs = {
        "name": name,
        "cluster_size": size,
        "min_num_clusters": min_num_clusters,
        "max_num_clusters": max_num_clusters,
        "auto_stop_mins": auto_stop_mins,
        "warehouse_type": wh_type,
        "enable_serverless_compute": enable_serverless,
    }
    create_kwargs.update(kwargs)

    wait = w.warehouses.create(**create_kwargs)
    warehouse_id = wait.id

    return {
        "warehouse_id": warehouse_id,
        "name": name,
        "size": size,
        "state": "STARTING",
        "message": (
            f"SQL warehouse '{name}' is being created (warehouse_id='{warehouse_id}'). "
            f"It typically takes 1-3 minutes to start."
        ),
    }


def modify_sql_warehouse(
    warehouse_id: str,
    name: Optional[str] = None,
    size: Optional[str] = None,
    min_num_clusters: Optional[int] = None,
    max_num_clusters: Optional[int] = None,
    auto_stop_mins: Optional[int] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Modify an existing SQL warehouse configuration.

    Only the specified parameters are changed; others remain as-is.

    Args:
        warehouse_id: ID of the warehouse to modify.
        name: New warehouse name (optional).
        size: New T-shirt size (optional).
        min_num_clusters: New minimum clusters (optional).
        max_num_clusters: New maximum clusters (optional).
        auto_stop_mins: New auto-stop timeout in minutes (optional).
        **kwargs: Additional SDK parameters.

    Returns:
        Dict with warehouse_id, name, state, and message.
    """
    w = get_workspace_client()

    # Get current config
    wh = w.warehouses.get(warehouse_id)

    edit_kwargs = {
        "id": warehouse_id,
        "name": name or wh.name,
        "cluster_size": size or wh.cluster_size,
        "min_num_clusters": min_num_clusters if min_num_clusters is not None else wh.min_num_clusters,
        "max_num_clusters": max_num_clusters if max_num_clusters is not None else wh.max_num_clusters,
        "auto_stop_mins": auto_stop_mins if auto_stop_mins is not None else wh.auto_stop_mins,
    }
    edit_kwargs.update(kwargs)

    w.warehouses.edit(**edit_kwargs)

    current_state = wh.state.value if wh.state else "UNKNOWN"
    wh_name = edit_kwargs["name"]

    return {
        "warehouse_id": warehouse_id,
        "name": wh_name,
        "state": current_state,
        "message": f"SQL warehouse '{wh_name}' configuration updated.",
    }


def delete_sql_warehouse(warehouse_id: str) -> Dict[str, Any]:
    """Permanently delete a SQL warehouse.

    WARNING: This action is PERMANENT and cannot be undone. The warehouse
    and its configuration will be permanently removed.

    Args:
        warehouse_id: ID of the warehouse to permanently delete.

    Returns:
        Dict with warehouse_id, name, and warning message.
    """
    w = get_workspace_client()

    # Get warehouse info before deleting
    wh = w.warehouses.get(warehouse_id)
    wh_name = wh.name or warehouse_id

    w.warehouses.delete(warehouse_id)

    return {
        "warehouse_id": warehouse_id,
        "name": wh_name,
        "state": "DELETED",
        "message": (
            f"WARNING: SQL warehouse '{wh_name}' has been PERMANENTLY deleted. "
            f"This action cannot be undone."
        ),
    }

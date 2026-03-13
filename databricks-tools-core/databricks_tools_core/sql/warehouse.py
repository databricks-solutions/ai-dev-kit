"""
SQL Warehouse Operations

Functions for listing and selecting SQL warehouses.
"""

import logging
from typing import Any, Dict, List, Optional

from databricks.sdk.service.sql import State

from ..auth import get_workspace_client, get_current_username

logger = logging.getLogger(__name__)


def list_warehouses(limit: int = 20) -> List[Dict[str, Any]]:
    """
    List SQL warehouses, with online (RUNNING) warehouses first.

    Args:
        limit: Maximum number of warehouses to return (default: 20)

    Returns:
        List of warehouse dictionaries with keys:
        - id: Warehouse ID
        - name: Warehouse name
        - state: Current state (RUNNING, STOPPED, STARTING, etc.)
        - cluster_size: Size of the warehouse
        - auto_stop_mins: Auto-stop timeout in minutes
        - creator_name: Who created the warehouse
        - warehouse_type: Type of warehouse (PRO, CLASSIC)
        - enable_serverless_compute: Whether serverless compute is enabled

    Raises:
        Exception: If API request fails
    """
    client = get_workspace_client()

    try:
        warehouses = list(client.warehouses.list())
    except Exception as e:
        raise Exception(f"Failed to list SQL warehouses: {str(e)}. Check that you have permission to view warehouses.")

    # Sort: RUNNING first, then by name
    def sort_key(w):
        # RUNNING = 0 (first), others = 1
        state_priority = 0 if w.state == State.RUNNING else 1
        return (state_priority, w.name.lower() if w.name else "")

    warehouses.sort(key=sort_key)

    # Convert to dicts and limit
    result = []
    for w in warehouses[:limit]:
        result.append(
            {
                "id": w.id,
                "name": w.name,
                "state": w.state.value if w.state else None,
                "cluster_size": w.cluster_size,
                "auto_stop_mins": w.auto_stop_mins,
                "creator_name": w.creator_name,
                "warehouse_type": getattr(w, "warehouse_type", None),
                "enable_serverless_compute": getattr(w, "enable_serverless_compute", None),
            }
        )

    return result


def _sort_within_tier(warehouses: list, current_user: Optional[str]) -> list:
    """Sort warehouses within a tier: serverless first, then user-owned.

    This is a *soft* preference — no warehouses are removed. Within the same
    priority bucket, serverless warehouses are tried first, then user-owned.

    Args:
        warehouses: List of SDK warehouse objects.
        current_user: Current user's username/email, or None.

    Returns:
        Reordered list (serverless first, then user-owned, then the rest).
    """
    if not warehouses:
        return warehouses

    def sort_key(w):
        is_serverless = 0 if getattr(w, "enable_serverless_compute", False) else 1
        user_lower = (current_user or "").lower()
        is_owned = 0 if user_lower and (w.creator_name or "").lower() == user_lower else 1
        return (is_serverless, is_owned)

    return sorted(warehouses, key=sort_key)


def get_best_warehouse() -> Optional[str]:
    """
    Select the best available SQL warehouse based on priority rules.

    Within each priority tier, serverless warehouses are preferred first
    (instant start, auto-scale, no idle costs), then warehouses created
    by the current user. No warehouses are excluded.

    Priority:
    1. Running warehouse named "Shared endpoint" or "dbdemos-shared-endpoint"
    2. Any running warehouse with 'shared' in name
    3. Any running warehouse
    4. Stopped warehouse with 'shared' in name
    5. Any stopped warehouse

    Returns:
        Warehouse ID string, or None if no warehouses available

    Raises:
        Exception: If API request fails
    """
    client = get_workspace_client()
    current_user = get_current_username()

    try:
        warehouses = list(client.warehouses.list())
    except Exception as e:
        raise Exception(f"Failed to list SQL warehouses: {str(e)}. Check that you have permission to view warehouses.")

    if not warehouses:
        logger.warning("No SQL warehouses found in workspace")
        return None

    # Categorize warehouses
    standard_shared = []  # Specific shared endpoint names
    online_shared = []  # Running + 'shared' in name
    online_other = []  # Running, no 'shared'
    offline_shared = []  # Stopped + 'shared' in name
    offline_other = []  # Stopped, no 'shared'

    for warehouse in warehouses:
        is_running = warehouse.state == State.RUNNING
        name_lower = warehouse.name.lower() if warehouse.name else ""
        is_shared = "shared" in name_lower

        # Check for standard shared endpoint names
        if is_running and warehouse.name in ("Shared endpoint", "dbdemos-shared-endpoint"):
            standard_shared.append(warehouse)
        elif is_running and is_shared:
            online_shared.append(warehouse)
        elif is_running:
            online_other.append(warehouse)
        elif is_shared:
            offline_shared.append(warehouse)
        else:
            offline_other.append(warehouse)

    # Within each tier, prefer warehouses owned by the current user
    standard_shared = _sort_within_tier(standard_shared, current_user)
    online_shared = _sort_within_tier(online_shared, current_user)
    online_other = _sort_within_tier(online_other, current_user)
    offline_shared = _sort_within_tier(offline_shared, current_user)
    offline_other = _sort_within_tier(offline_other, current_user)

    # Select based on priority
    if standard_shared:
        selected = standard_shared[0]
    elif online_shared:
        selected = online_shared[0]
    elif online_other:
        selected = online_other[0]
    elif offline_shared:
        selected = offline_shared[0]
    elif offline_other:
        selected = offline_other[0]
    else:
        return None

    logger.debug(f"Selected warehouse: {selected.name} (state: {selected.state})")
    return selected.id

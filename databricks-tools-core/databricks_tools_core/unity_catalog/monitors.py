"""
Unity Catalog - Quality Monitor Operations

Functions for managing Lakehouse Monitors (data quality monitors).
"""

from typing import Any, Dict, List, Optional

from ..auth import get_workspace_client


def create_monitor(
    table_name: str,
    output_schema_name: str,
    monitor_type: str = "snapshot",
    assets_dir: str | None = None,
    time_series_timestamp_col: str | None = None,
    time_series_granularities: list[str] | None = None,
    schedule_cron: str | None = None,
    schedule_timezone: str = "UTC",
) -> dict[str, Any]:
    """
    Create a quality monitor on a table.

    Args:
        table_name: Full table name to monitor (catalog.schema.table)
        output_schema_name: Schema for monitor output tables (catalog.schema)
        monitor_type: Type of monitor: "snapshot" (default), "time_series", or "inference"
        assets_dir: Workspace path for monitor assets. If not provided,
            auto-generated under /Workspace/Users/{user}/databricks_lakehouse_monitoring/
        time_series_timestamp_col: Timestamp column (required for time_series type)
        time_series_granularities: Granularities list (e.g., ["1 day"]) for time_series
        schedule_cron: Quartz cron expression for schedule (e.g., "0 0 * * * ?")
        schedule_timezone: Timezone for schedule (default: "UTC")

    Returns:
        Dict with monitor details

    Raises:
        ValueError: If monitor_type is invalid or required params missing
        DatabricksError: If API request fails
    """
    w = get_workspace_client()

    # assets_dir is required by the SDK; generate a default if not provided
    if assets_dir is None:
        user = w.current_user.me()
        safe_table = table_name.replace(".", "_")
        assets_dir = f"/Workspace/Users/{user.user_name}/databricks_lakehouse_monitoring/{safe_table}"

    kwargs: dict[str, Any] = {
        "table_name": table_name,
        "output_schema_name": output_schema_name,
        "assets_dir": assets_dir,
    }

    # Configure monitor type (exactly one is required by the API)
    if monitor_type == "snapshot":
        from databricks.sdk.service.catalog import MonitorSnapshot

        kwargs["snapshot"] = MonitorSnapshot()
    elif monitor_type == "time_series":
        if not time_series_timestamp_col:
            raise ValueError("time_series_timestamp_col is required for time_series monitors")
        from databricks.sdk.service.catalog import MonitorTimeSeries

        kwargs["time_series"] = MonitorTimeSeries(
            timestamp_col=time_series_timestamp_col,
            granularities=time_series_granularities or ["1 day"],
        )
    elif monitor_type == "inference":
        from databricks.sdk.service.catalog import MonitorInferenceLog

        kwargs["inference_log"] = MonitorInferenceLog()
    else:
        raise ValueError(f"Invalid monitor_type: '{monitor_type}'. Valid types: snapshot, time_series, inference")

    if schedule_cron is not None:
        from databricks.sdk.service.catalog import MonitorCronSchedule

        kwargs["schedule"] = MonitorCronSchedule(
            quartz_cron_expression=schedule_cron,
            timezone_id=schedule_timezone,
        )

    result = w.quality_monitors.create(**kwargs)
    return result.as_dict() if hasattr(result, "as_dict") else vars(result)


def get_monitor(table_name: str) -> dict[str, Any]:
    """
    Get the quality monitor on a table.

    Args:
        table_name: Full table name (catalog.schema.table)

    Returns:
        Dict with monitor details

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    result = w.quality_monitors.get(table_name=table_name)
    return result.as_dict() if hasattr(result, "as_dict") else vars(result)


def run_monitor_refresh(table_name: str) -> dict[str, Any]:
    """
    Trigger a refresh of a quality monitor.

    Args:
        table_name: Full table name (catalog.schema.table)

    Returns:
        Dict with refresh details including refresh_id

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    result = w.quality_monitors.run_refresh(table_name=table_name)
    return result.as_dict() if hasattr(result, "as_dict") else vars(result)


def list_monitor_refreshes(table_name: str) -> list[dict[str, Any]]:
    """
    List refresh history for a quality monitor.

    Args:
        table_name: Full table name (catalog.schema.table)

    Returns:
        List of dicts with refresh history

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    result = w.quality_monitors.list_refreshes(table_name=table_name)
    return [r.as_dict() if hasattr(r, "as_dict") else vars(r) for r in (result.refreshes or [])]


def delete_monitor(table_name: str) -> None:
    """
    Delete the quality monitor on a table.

    Args:
        table_name: Full table name (catalog.schema.table)

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    w.quality_monitors.delete(table_name=table_name)

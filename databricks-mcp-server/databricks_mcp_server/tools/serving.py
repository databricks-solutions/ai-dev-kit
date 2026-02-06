"""Model Serving tools - Query and manage serving endpoints."""

from typing import Any, Dict, List, Optional

from databricks_tools_core.serving import (
    get_serving_endpoint_status as _get_serving_endpoint_status,
    query_serving_endpoint as _query_serving_endpoint,
    list_serving_endpoints as _list_serving_endpoints,
)

from ..server import mcp


@mcp.tool
def get_serving_endpoint_status(name: str) -> dict[str, Any]:
    """
    Get the status of a Model Serving endpoint.

    Use this to check if an endpoint is ready after deployment, or to
    debug issues with a serving endpoint.

    Args:
        name: The name of the serving endpoint

    Returns:
        Dictionary with endpoint status:
        - name: Endpoint name
        - state: Current state (READY, NOT_READY, NOT_FOUND)
        - config_update: Config update state if updating (IN_PROGRESS, etc.)
        - served_entities: List of served models with their deployment states
        - error: Error message if endpoint is in error state

    Example:
        >>> get_serving_endpoint_status("my-agent-endpoint")
        {
            "name": "my-agent-endpoint",
            "state": "READY",
            "config_update": null,
            "served_entities": [
                {"name": "my-agent-1", "entity_name": "main.agents.my_agent", ...}
            ]
        }
    """
    return _get_serving_endpoint_status(name=name)


@mcp.tool
def query_serving_endpoint(
    name: str,
    messages: list[dict[str, str]] | None = None,
    inputs: dict[str, Any] | None = None,
    dataframe_records: list[dict[str, Any]] | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> dict[str, Any]:
    """
    Query a Model Serving endpoint.

    Supports multiple input formats depending on endpoint type:
    - messages: For chat/agent endpoints (OpenAI-compatible format)
    - inputs: For custom pyfunc models
    - dataframe_records: For traditional ML models (pandas DataFrame format)

    Args:
        name: The name of the serving endpoint
        messages: List of chat messages for chat/agent endpoints.
            Format: [{"role": "user", "content": "Hello"}]
        inputs: Dictionary of inputs for custom pyfunc models.
            Format depends on model signature.
        dataframe_records: List of records for ML models.
            Format: [{"feature1": 1.0, "feature2": 2.0}, ...]
        max_tokens: Maximum tokens for chat/completion endpoints
        temperature: Temperature for chat/completion endpoints (0.0-2.0)

    Returns:
        Dictionary with query response:
        - For chat endpoints: Contains 'choices' with assistant response
        - For ML endpoints: Contains 'predictions'

    Example (chat/agent endpoint):
        >>> query_serving_endpoint(
        ...     name="my-agent-endpoint",
        ...     messages=[{"role": "user", "content": "What is Databricks?"}]
        ... )
        {
            "choices": [
                {"message": {"role": "assistant", "content": "Databricks is..."}}
            ]
        }

    Example (ML model):
        >>> query_serving_endpoint(
        ...     name="sklearn-model",
        ...     dataframe_records=[{"age": 25, "income": 50000}]
        ... )
        {"predictions": [0.85]}
    """
    return _query_serving_endpoint(
        name=name,
        messages=messages,
        inputs=inputs,
        dataframe_records=dataframe_records,
        max_tokens=max_tokens,
        temperature=temperature,
    )


@mcp.tool
def list_serving_endpoints(limit: int = 50) -> list[dict[str, Any]]:
    """
    List Model Serving endpoints in the workspace.

    Args:
        limit: Maximum number of endpoints to return (default: 50)

    Returns:
        List of endpoint dictionaries with:
        - name: Endpoint name
        - state: Current state (READY, NOT_READY)
        - creation_timestamp: When created
        - creator: Who created it
        - served_entities_count: Number of served models

    Example:
        >>> list_serving_endpoints(limit=10)
        [
            {"name": "my-agent", "state": "READY", ...},
            {"name": "ml-model", "state": "READY", ...}
        ]
    """
    return _list_serving_endpoints(limit=limit)

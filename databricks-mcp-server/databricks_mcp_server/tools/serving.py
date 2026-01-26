"""Model Serving tools - Manage serving endpoints for ML models and agents."""

from typing import Any, Dict, List, Optional

from databricks_tools_core.serving import ServingManager

from ..server import mcp

# Singleton manager instance
_manager: Optional[ServingManager] = None


def _get_manager() -> ServingManager:
    """Get or create the singleton ServingManager instance."""
    global _manager
    if _manager is None:
        _manager = ServingManager()
    return _manager


# ============================================================================
# Serving Endpoint Tools
# ============================================================================


@mcp.tool
def list_serving_endpoints() -> List[Dict[str, Any]]:
    """
    List all model serving endpoints in the workspace.

    Returns a summary of each endpoint including name, state, and served entities.
    Use this to discover available endpoints before querying or managing them.

    Returns:
        List of endpoint summaries, each containing:
        - name: The endpoint name
        - state: Current state (READY, NOT_READY, PENDING, etc.)
        - served_entities: List of deployed models/agents

    Example:
        >>> list_serving_endpoints()
        [
            {
                "name": "my-agent-endpoint",
                "state": "READY",
                "served_entities": [
                    {"name": "agent-v1", "entity_name": "catalog.schema.my_agent"}
                ]
            },
            ...
        ]
    """
    manager = _get_manager()
    return manager.list_endpoints()


@mcp.tool
def get_serving_endpoint(name: str) -> Dict[str, Any]:
    """
    Get details for a specific serving endpoint.

    Use this to check endpoint status, configuration, and served model details.
    Especially useful after creating an endpoint to check when it becomes READY.

    Args:
        name: The endpoint name

    Returns:
        Dictionary with endpoint details:
        - name: The endpoint name
        - state: Current state (READY, NOT_READY, PENDING)
        - config_update: Config update state if updating
        - served_entities: List of served models/agents with their config

    Example:
        >>> get_serving_endpoint("my-agent-endpoint")
        {
            "name": "my-agent-endpoint",
            "state": "READY",
            "served_entities": [
                {
                    "name": "agent-v1",
                    "entity_name": "catalog.schema.my_agent",
                    "entity_version": "1",
                    "workload_size": "Small",
                    "scale_to_zero_enabled": true
                }
            ]
        }
    """
    manager = _get_manager()
    try:
        return manager.get_endpoint(name)
    except Exception as e:
        return {"error": f"Endpoint '{name}' not found: {str(e)}"}


@mcp.tool
def create_serving_endpoint(
    name: str,
    model_name: str,
    model_version: Optional[str] = None,
    workload_size: str = "Small",
    workload_type: Optional[str] = None,
    scale_to_zero: bool = True,
    environment_vars: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Create a serving endpoint from a Unity Catalog registered model.

    This creates the endpoint asynchronously and returns immediately.
    Use get_serving_endpoint() to check when the endpoint becomes READY.
    Endpoint creation typically takes 2-5 minutes.

    IMPORTANT: The model must be registered in Unity Catalog first.
    Use mlflow.register_model() or log with registered_model_name parameter.

    Args:
        name: Endpoint name (alphanumeric, dashes, underscores allowed)
        model_name: Unity Catalog model path (e.g., "catalog.schema.my_model")
        model_version: Model version number (default: uses latest version)
        workload_size: Compute size - "Small", "Medium", or "Large" (default: Small)
        workload_type: GPU type - "GPU_SMALL", "GPU_MEDIUM", "GPU_LARGE" (default: CPU)
        scale_to_zero: Enable scale to zero when idle (default: True)
        environment_vars: Environment variables for the endpoint, use for secrets:
            {"OPENAI_API_KEY": "{{secrets/scope/key}}"}

    Returns:
        Dictionary with:
        - name: Endpoint name
        - status: "CREATING" if successful, "FAILED" if error
        - model_name: The UC model path
        - message: Next steps

    Example:
        >>> create_serving_endpoint(
        ...     name="my-agent-endpoint",
        ...     model_name="catalog.schema.my_agent",
        ...     model_version="1",
        ...     environment_vars={"OPENAI_API_KEY": "{{secrets/llm-keys/openai}}"}
        ... )
        {
            "name": "my-agent-endpoint",
            "status": "CREATING",
            "model_name": "catalog.schema.my_agent",
            "model_version": "1",
            "message": "Endpoint creation initiated. Use get_serving_endpoint to check status."
        }
    """
    manager = _get_manager()
    return manager.create_endpoint(
        name=name,
        model_name=model_name,
        model_version=model_version,
        workload_size=workload_size,
        workload_type=workload_type,
        scale_to_zero=scale_to_zero,
        environment_vars=environment_vars,
    )


@mcp.tool
def delete_serving_endpoint(name: str) -> Dict[str, Any]:
    """
    Delete a serving endpoint.

    This immediately initiates deletion. The endpoint will be removed
    and any running instances will be terminated.

    Args:
        name: The endpoint name to delete

    Returns:
        Dictionary with:
        - success: True if deletion initiated
        - name: The endpoint name
        - message: Confirmation message

    Example:
        >>> delete_serving_endpoint("my-agent-endpoint")
        {"success": True, "name": "my-agent-endpoint", "message": "Endpoint deleted"}
    """
    manager = _get_manager()
    return manager.delete_endpoint(name)


@mcp.tool
def query_serving_endpoint(
    name: str,
    message: str,
    max_tokens: int = 500,
    temperature: float = 0.7,
) -> Dict[str, Any]:
    """
    Query a serving endpoint with a chat message.

    Use this to test deployed models and agents. Works with:
    - LangChain/LangGraph agents
    - Custom PyFunc agents with chat interface
    - External model endpoints (OpenAI, etc.)
    - Foundation model endpoints

    Args:
        name: The endpoint name to query
        message: The user message to send
        max_tokens: Maximum tokens in response (default: 500)
        temperature: Sampling temperature 0.0-2.0 (default: 0.7)

    Returns:
        Dictionary with:
        - success: True if query succeeded
        - response: The model/agent response text
        - usage: Token usage info (if available)

    Example:
        >>> query_serving_endpoint("my-agent-endpoint", "What is 2+2?")
        {
            "success": True,
            "name": "my-agent-endpoint",
            "response": "2 + 2 equals 4.",
            "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18}
        }
    """
    manager = _get_manager()
    return manager.query_endpoint(
        name=name,
        message=message,
        max_tokens=max_tokens,
        temperature=temperature,
    )


@mcp.tool
def get_serving_endpoint_logs(
    name: str,
    served_model_name: str,
    log_type: str = "runtime",
) -> Dict[str, Any]:
    """
    Get logs for a served model in an endpoint.

    Use this to debug issues with deployed models/agents.

    Args:
        name: The endpoint name
        served_model_name: The served model/entity name
            (usually the model name or version, see get_serving_endpoint for entity names)
        log_type: "build" for build logs, "runtime" for runtime logs (default: runtime)

    Returns:
        Dictionary with:
        - success: True if logs retrieved
        - logs: The log content
        - error: Error message if failed

    Example:
        >>> get_serving_endpoint_logs("my-agent-endpoint", "agent-v1", "build")
        {
            "success": True,
            "name": "my-agent-endpoint",
            "served_model_name": "agent-v1",
            "logs": "Installing dependencies...\\nStarting model server..."
        }
    """
    manager = _get_manager()

    if log_type == "build":
        return manager.get_build_logs(name, served_model_name)
    else:
        return manager.get_logs(name, served_model_name)

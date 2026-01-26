"""
Serving Manager - Manage Model Serving Endpoints.

Wrapper for Databricks Model Serving endpoints with operations for:
- Listing, getting, creating, deleting endpoints
- Querying endpoints (inference)
- Getting build and runtime logs
"""

import logging
from typing import Any, Dict, List, Optional

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    ChatMessage,
    ChatMessageRole,
    EndpointCoreConfigInput,
    ServedEntityInput,
)

from ..auth import get_workspace_client

logger = logging.getLogger(__name__)


class ServingManager:
    """Manager for Databricks Model Serving endpoints.

    Key operations:
        - list_endpoints(): List all serving endpoints
        - get_endpoint(): Get endpoint by name
        - create_endpoint(): Create endpoint from UC model (async)
        - delete_endpoint(): Delete endpoint
        - query_endpoint(): Query endpoint with message
        - get_build_logs(): Get build logs for debugging
        - get_logs(): Get runtime logs
    """

    def __init__(self, client: Optional[WorkspaceClient] = None):
        """
        Initialize the Serving Manager.

        Args:
            client: Optional WorkspaceClient (creates new one if not provided)
        """
        self.w: WorkspaceClient = client or get_workspace_client()

    def list_endpoints(self) -> List[Dict[str, Any]]:
        """
        List all serving endpoints.

        Returns:
            List of endpoint summaries with name, state, and entity info.
        """
        endpoints = []
        for ep in self.w.serving_endpoints.list():
            endpoint_info = {
                "name": ep.name,
                "state": ep.state.ready.value if ep.state and ep.state.ready else "UNKNOWN",
                "creator": getattr(ep, "creator", None),
                "creation_timestamp": getattr(ep, "creation_timestamp", None),
            }

            # Get served entities info
            if ep.config and ep.config.served_entities:
                endpoint_info["served_entities"] = [
                    {
                        "name": entity.name,
                        "entity_name": getattr(entity, "entity_name", None),
                        "entity_version": getattr(entity, "entity_version", None),
                    }
                    for entity in ep.config.served_entities
                ]

            endpoints.append(endpoint_info)

        return endpoints

    def get_endpoint(self, name: str) -> Dict[str, Any]:
        """
        Get a serving endpoint by name.

        Args:
            name: The endpoint name

        Returns:
            Endpoint details including state, config, and served entities.
        """
        ep = self.w.serving_endpoints.get(name=name)

        result = {
            "name": ep.name,
            "state": ep.state.ready.value if ep.state and ep.state.ready else "UNKNOWN",
            "config_update": ep.state.config_update.value if ep.state and ep.state.config_update else None,
            "creator": getattr(ep, "creator", None),
            "creation_timestamp": getattr(ep, "creation_timestamp", None),
        }

        # Get served entities details
        if ep.config and ep.config.served_entities:
            result["served_entities"] = []
            for entity in ep.config.served_entities:
                entity_info = {
                    "name": entity.name,
                    "entity_name": getattr(entity, "entity_name", None),
                    "entity_version": getattr(entity, "entity_version", None),
                    "workload_size": getattr(entity, "workload_size", None),
                    "workload_type": getattr(entity, "workload_type", None),
                    "scale_to_zero_enabled": getattr(entity, "scale_to_zero_enabled", None),
                }
                # Check for external model
                if hasattr(entity, "external_model") and entity.external_model:
                    entity_info["external_model"] = {
                        "name": entity.external_model.name,
                        "provider": entity.external_model.provider.value if entity.external_model.provider else None,
                    }
                result["served_entities"].append(entity_info)

        # Pending config (if updating)
        if ep.pending_config and ep.pending_config.served_entities:
            result["pending_config"] = True

        return result

    def create_endpoint(
        self,
        name: str,
        model_name: str,
        model_version: Optional[str] = None,
        workload_size: str = "Small",
        workload_type: Optional[str] = None,
        scale_to_zero: bool = True,
        environment_vars: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Create a serving endpoint from a Unity Catalog model.

        This method returns immediately without waiting for the endpoint
        to be ready. Use get_endpoint() to check status.

        Args:
            name: Endpoint name (alphanumeric, dashes, underscores)
            model_name: UC model path (catalog.schema.model)
            model_version: Model version (default: latest)
            workload_size: Small, Medium, Large (default: Small)
            workload_type: CPU, GPU_SMALL, GPU_MEDIUM, GPU_LARGE (default: CPU)
            scale_to_zero: Enable scale to zero (default: True)
            environment_vars: Environment variables for the endpoint

        Returns:
            Dictionary with endpoint name and initial status.
        """
        # Build served entity config
        # ServedEntityInput requires a name - use model name's last part + version
        model_short_name = model_name.split(".")[-1] if "." in model_name else model_name
        entity_display_name = f"{model_short_name}-{model_version or '1'}"

        entity_config = {
            "name": entity_display_name,  # Required: name for the served entity
            "entity_name": model_name,
            "workload_size": workload_size,
            "scale_to_zero_enabled": scale_to_zero,
        }

        if model_version:
            entity_config["entity_version"] = model_version

        if workload_type:
            entity_config["workload_type"] = workload_type

        if environment_vars:
            entity_config["environment_vars"] = environment_vars

        # Create endpoint using REST API directly (non-blocking)
        try:
            # Build the request payload
            payload = {
                "name": name,
                "config": {
                    "name": name,
                    "served_entities": [
                        {
                            "name": entity_display_name,
                            "entity_name": model_name,
                            "workload_size": workload_size,
                            "scale_to_zero_enabled": scale_to_zero,
                        }
                    ],
                },
            }

            # Add optional fields
            if model_version:
                payload["config"]["served_entities"][0]["entity_version"] = model_version
            if workload_type:
                payload["config"]["served_entities"][0]["workload_type"] = workload_type
            if environment_vars:
                payload["config"]["served_entities"][0]["environment_vars"] = environment_vars

            # Use the API client directly - this returns immediately
            self.w.api_client.do(
                "POST",
                "/api/2.0/serving-endpoints",
                body=payload,
            )

            return {
                "name": name,
                "status": "CREATING",
                "model_name": model_name,
                "model_version": model_version or "latest",
                "message": "Endpoint creation initiated. Use get_serving_endpoint to check status.",
            }

        except Exception as e:
            error_msg = str(e)
            return {
                "name": name,
                "status": "FAILED",
                "error": error_msg,
            }

    def delete_endpoint(self, name: str) -> Dict[str, Any]:
        """
        Delete a serving endpoint.

        Args:
            name: The endpoint name to delete

        Returns:
            Dictionary with success status.
        """
        try:
            self.w.serving_endpoints.delete(name=name)
            return {"success": True, "name": name, "message": "Endpoint deleted"}
        except Exception as e:
            return {"success": False, "name": name, "error": str(e)}

    def query_endpoint(
        self,
        name: str,
        message: str,
        max_tokens: int = 500,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        """
        Query a serving endpoint with a chat message.

        Args:
            name: The endpoint name
            message: The user message to send
            max_tokens: Maximum tokens in response (default: 500)
            temperature: Sampling temperature (default: 0.7)

        Returns:
            Dictionary with the response content and usage info.
        """
        try:
            response = self.w.serving_endpoints.query(
                name=name,
                messages=[
                    ChatMessage(role=ChatMessageRole.USER, content=message)
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )

            result = {"success": True, "name": name}

            # Extract response content
            if hasattr(response, "choices") and response.choices:
                result["response"] = response.choices[0].message.content
            else:
                # For non-chat models, try other response formats
                result["response"] = str(response)

            # Extract usage info if available
            if hasattr(response, "usage") and response.usage:
                result["usage"] = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }

            return result

        except Exception as e:
            return {
                "success": False,
                "name": name,
                "error": str(e),
            }

    def get_build_logs(self, name: str, served_model_name: str) -> Dict[str, Any]:
        """
        Get build logs for a served model.

        Args:
            name: The endpoint name
            served_model_name: The served model/entity name

        Returns:
            Dictionary with logs content.
        """
        try:
            response = self.w.serving_endpoints.build_logs(
                name=name,
                served_model_name=served_model_name,
            )
            return {
                "success": True,
                "name": name,
                "served_model_name": served_model_name,
                "logs": response.logs if hasattr(response, "logs") else str(response),
            }
        except Exception as e:
            return {
                "success": False,
                "name": name,
                "served_model_name": served_model_name,
                "error": str(e),
            }

    def get_logs(self, name: str, served_model_name: str) -> Dict[str, Any]:
        """
        Get runtime logs for a served model.

        Args:
            name: The endpoint name
            served_model_name: The served model/entity name

        Returns:
            Dictionary with logs content.
        """
        try:
            response = self.w.serving_endpoints.logs(
                name=name,
                served_model_name=served_model_name,
            )
            return {
                "success": True,
                "name": name,
                "served_model_name": served_model_name,
                "logs": response.logs if hasattr(response, "logs") else str(response),
            }
        except Exception as e:
            return {
                "success": False,
                "name": name,
                "served_model_name": served_model_name,
                "error": str(e),
            }

"""LLM calls for PDF generation using Databricks model serving.

Uses the same query_serving_endpoint as all other tools.
"""

import json
import logging
import os
import re
from functools import lru_cache
from typing import Any, Optional, Union

from pydantic import BaseModel

from ..serving.endpoints import list_serving_endpoints, query_serving_endpoint

logger = logging.getLogger(__name__)


class LLMConfigurationError(Exception):
    """Raised when LLM is not properly configured."""


@lru_cache(maxsize=1)
def _discover_databricks_gpt_endpoints() -> tuple[Optional[str], Optional[str]]:
    """Discover the latest databricks-gpt endpoints.

    Looks for endpoints starting with 'databricks-gpt' and returns:
    - The latest non-nano model (highest version)
    - The latest nano model (highest version with 'nano' in name)

    Returns:
        Tuple of (main_model, nano_model). Either can be None if not found.
    """
    try:
        # Get all endpoints - SDK fetches all, we filter client-side for databricks-gpt-*
        endpoints = list_serving_endpoints(limit=None)
    except Exception as e:
        logger.warning(f"Could not list endpoints for auto-discovery: {e}")
        return None, None

    # Filter to databricks-gpt endpoints that are READY
    gpt_endpoints = [
        ep["name"] for ep in endpoints if ep["name"].startswith("databricks-gpt") and ep.get("state") == "READY"
    ]

    if not gpt_endpoints:
        logger.warning("No databricks-gpt endpoints found")
        return None, None

    # Parse version from endpoint names like "databricks-gpt-5-4" or "databricks-gpt-5-4-nano"
    def parse_version(name: str) -> tuple[int, ...]:
        """Extract version numbers from endpoint name."""
        # Match patterns like "5-4" or "5-4-nano"
        match = re.search(r"databricks-gpt-(\d+(?:-\d+)*)", name)
        if match:
            version_str = match.group(1)
            # Remove 'nano' suffix if present for version parsing
            version_str = version_str.replace("-nano", "")
            return tuple(int(x) for x in version_str.split("-"))
        return (0,)

    # Separate nano and non-nano endpoints
    nano_endpoints = [ep for ep in gpt_endpoints if "nano" in ep.lower()]
    main_endpoints = [ep for ep in gpt_endpoints if "nano" not in ep.lower()]

    # Sort by version (highest first)
    main_endpoints.sort(key=parse_version, reverse=True)
    nano_endpoints.sort(key=parse_version, reverse=True)

    main_model = main_endpoints[0] if main_endpoints else None
    nano_model = nano_endpoints[0] if nano_endpoints else main_model  # Fall back to main if no nano

    logger.info(f"Discovered databricks-gpt endpoints: main={main_model}, nano={nano_model}")
    return main_model, nano_model


def _get_model_name(mini: bool = False, model_name: Optional[str] = None) -> str:
    """Get the model endpoint name.

    Priority:
    1. Explicit model_name parameter
    2. Environment variable (DATABRICKS_MODEL or DATABRICKS_MODEL_NANO)
    3. Auto-discovered databricks-gpt endpoint

    Args:
        mini: Use smaller/faster model (nano variant)
        model_name: Override model name

    Returns:
        Model endpoint name

    Raises:
        LLMConfigurationError: If no model can be found
    """
    if model_name:
        return model_name

    # Check environment variables
    if mini:
        env_model = os.getenv("DATABRICKS_MODEL_NANO")
        if env_model:
            return env_model
    else:
        env_model = os.getenv("DATABRICKS_MODEL")
        if env_model:
            return env_model

    # Auto-discover from available endpoints
    main_model, nano_model = _discover_databricks_gpt_endpoints()

    if mini and nano_model:
        return nano_model
    if main_model:
        return main_model

    raise LLMConfigurationError(
        "No LLM model configured. Set DATABRICKS_MODEL environment variable "
        "or ensure a databricks-gpt-* endpoint is available in your workspace."
    )


def call_llm(
    prompt: str,
    system_prompt: Optional[str] = None,
    mini: bool = False,
    max_tokens: int = 4000,
    temperature: float = 1.0,
    response_format: Optional[Union[str, dict[str, Any], type[BaseModel]]] = None,
    model_name: Optional[str] = None,
) -> str:
    """Call Databricks model serving endpoint.

    Uses the same query_serving_endpoint as all other tools (SDK auth chain).

    Args:
        prompt: User prompt
        system_prompt: Optional system prompt
        mini: Use smaller/faster model (nano variant if available)
        max_tokens: Maximum tokens in response
        temperature: Model temperature (default: 1.0)
        response_format: Response format - 'json_object' (note: passed via system prompt hint)
        model_name: Override model name (auto-discovered if not set)

    Returns:
        Generated content string
    """
    endpoint_name = _get_model_name(mini=mini, model_name=model_name)

    # Build messages
    messages: list[dict[str, str]] = []

    # Add JSON hint to system prompt if json response requested
    effective_system_prompt = system_prompt or ""
    if response_format == "json_object":
        if effective_system_prompt:
            effective_system_prompt += "\n\nYou must respond with valid JSON only."
        else:
            effective_system_prompt = "You must respond with valid JSON only."

    if effective_system_prompt:
        messages.append({"role": "system", "content": effective_system_prompt})
    messages.append({"role": "user", "content": prompt})

    logger.info(f"Calling Databricks endpoint: {endpoint_name}")

    try:
        response = query_serving_endpoint(
            name=endpoint_name,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature if temperature != 1.0 else None,
        )
    except Exception as e:
        logger.error(f"Error calling {endpoint_name}: {type(e).__name__}: {e}")
        raise

    # Extract content from response
    if not response.get("choices") or not response["choices"][0].get("message", {}).get("content"):
        finish_reason = response.get("choices", [{}])[0].get("finish_reason", "unknown")
        raise Exception(f"Empty response from model. finish_reason={finish_reason}")

    content = response["choices"][0]["message"]["content"]

    # Validate Pydantic response
    if isinstance(response_format, type) and issubclass(response_format, BaseModel):
        try:
            response_format.model_validate(json.loads(content))
        except Exception as e:
            logger.warning(f"Response validation failed: {e}")

    return content

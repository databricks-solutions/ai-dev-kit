"""Resolve configured or available Databricks GPT serving endpoints."""

import logging
import os
import re
from typing import Optional

from ..serving import list_serving_endpoints

logger = logging.getLogger(__name__)


class LLMConfigurationError(ValueError):
    """No model was configured or discovered in the workspace."""


def _discover_databricks_gpt_endpoints() -> tuple[Optional[str], Optional[str]]:
    """Find the latest ready main and nano GPT endpoints by numeric version.

    If no nano endpoint exists, use the main endpoint for both model sizes.
    An unavailable endpoint listing is treated as unsuccessful discovery.
    """
    try:
        endpoints = list_serving_endpoints(limit=None)
    except Exception as exc:
        logger.warning("Unable to discover Databricks GPT endpoints: %s", exc)
        return None, None

    main_models: list[tuple[tuple[int, ...], str]] = []
    nano_models: list[tuple[tuple[int, ...], str]] = []
    for endpoint in endpoints:
        if endpoint.get("state") != "READY":
            continue
        name = endpoint.get("name") or ""
        match = re.fullmatch(r"databricks-gpt-(\d+(?:-\d+)*)(-nano)?", name)
        if not match:
            continue
        version = tuple(int(part) for part in match.group(1).split("-"))
        models = nano_models if match.group(2) else main_models
        models.append((version, name))

    main_model = max(main_models)[1] if main_models else None
    nano_model = max(nano_models)[1] if nano_models else main_model
    return main_model, nano_model


def _get_model_name(mini: bool = False, model_name: Optional[str] = None) -> str:
    """Resolve an explicit name, environment setting, or discovered endpoint."""
    if model_name:
        return model_name

    configured = os.environ.get("DATABRICKS_MODEL_NANO") if mini else None
    configured = configured or os.environ.get("DATABRICKS_MODEL")
    if configured:
        return configured

    main_model, nano_model = _discover_databricks_gpt_endpoints()
    discovered = nano_model if mini else main_model
    if discovered:
        return discovered

    raise LLMConfigurationError(
        "No LLM model configured. Provide model_name, set DATABRICKS_MODEL "
        "(or DATABRICKS_MODEL_NANO), or make a Databricks GPT endpoint available."
    )

"""Product identity, project detection, and resource tagging.

Every Databricks API call made through the SDK includes a User-Agent header.
This module sets a custom product name and auto-detects the project name from
a config file or git, so all calls are attributable in the
``system.access.audit`` system table.

Resources created by the MCP server are also tagged with project metadata
and any freeform tags defined in ``.databricks-ai-dev-kit.yaml``.

Example user-agent string::

    databricks-ai-dev-kit/0.1.0 databricks-sdk-py/0.73.0 python/3.11.13 os/darwin auth/pat project/my-repo

Example config file (``.databricks-ai-dev-kit.yaml`` at repo root)::

    project: my-sales-dashboard
    tags:
      team: data-eng
      env: dev
"""

import logging
import os
import re
import subprocess
from typing import Any, Dict, Optional

import yaml
from databricks.sdk import WorkspaceClient

logger = logging.getLogger(__name__)

PRODUCT_NAME = "databricks-ai-dev-kit"
PRODUCT_VERSION = "0.1.0"

_CONFIG_FILENAME = ".databricks-ai-dev-kit.yaml"

_cached_project: Optional[str] = None
_cached_config: Optional[Dict[str, Any]] = None


def _sanitize_project_name(name: str) -> str:
    """Sanitize a project name for use in a user-agent string.

    Keeps only alphanumeric characters, hyphens, underscores, and dots.
    """
    sanitized = re.sub(r"[^a-zA-Z0-9._-]", "-", name)
    # Collapse multiple hyphens and strip leading/trailing hyphens
    sanitized = re.sub(r"-+", "-", sanitized).strip("-")
    return sanitized or "unknown"


def _git_toplevel() -> Optional[str]:
    """Return the git repo root directory, or None."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _load_config() -> Dict[str, Any]:
    """Load ``.databricks-ai-dev-kit.yaml`` from the git repo root or cwd.

    The result is cached for the lifetime of the process.

    Returns:
        Parsed config dict, or empty dict if the file doesn't exist.
    """
    global _cached_config
    if _cached_config is not None:
        return _cached_config

    search_dirs = [_git_toplevel(), os.getcwd()]
    for directory in search_dirs:
        if directory:
            config_path = os.path.join(directory, _CONFIG_FILENAME)
            if os.path.isfile(config_path):
                try:
                    with open(config_path) as f:
                        _cached_config = yaml.safe_load(f) or {}
                    logger.debug("Loaded config from %s", config_path)
                    return _cached_config
                except Exception:
                    logger.warning("Failed to parse %s", config_path, exc_info=True)

    _cached_config = {}
    return _cached_config


def detect_project_name() -> str:
    """Detect the project name. Cached after first call.

    Detection priority:
        1. ``project`` field in ``.databricks-ai-dev-kit.yaml``
        2. Git remote origin URL → extract repository name
        3. Git repo root directory → use basename
        4. Current working directory → use basename

    Returns:
        A sanitized project name string.
    """
    global _cached_project
    if _cached_project is not None:
        return _cached_project

    name: Optional[str] = None

    # Priority 1: config file
    config = _load_config()
    config_project = config.get("project")
    if config_project and isinstance(config_project, str):
        name = config_project

    # Priority 2: git remote origin URL
    if not name:
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                url = result.stdout.strip()
                # Handle both HTTPS and SSH URLs
                # https://github.com/org/repo.git -> repo
                # git@github.com:org/repo.git -> repo
                name = url.rstrip("/").split("/")[-1].removesuffix(".git")
        except Exception:
            pass

    # Priority 3: git repo root directory name
    if not name:
        toplevel = _git_toplevel()
        if toplevel:
            name = os.path.basename(toplevel)

    # Priority 4: current working directory name
    if not name:
        name = os.path.basename(os.getcwd())

    _cached_project = _sanitize_project_name(name or "unknown")
    logger.debug("Detected project name: %s", _cached_project)
    return _cached_project


def get_default_tags() -> Dict[str, str]:
    """Get tags to apply to all created resources.

    Merges:
        1. ``created_by: databricks-ai-dev-kit`` (always)
        2. ``project: <detected or configured>`` (always)
        3. Freeform tags from ``.databricks-ai-dev-kit.yaml`` ``tags:`` section

    Config file tags do not override ``created_by`` or ``project``.
    User-provided tags at resource creation time take precedence over
    all default tags (handled by callers).

    Returns:
        Dictionary of tag key-value pairs.
    """
    tags: Dict[str, str] = {
        "created_by": PRODUCT_NAME,
        "aidevkit_project": detect_project_name(),
    }
    # Merge freeform tags from config file
    config = _load_config()
    config_tags = config.get("tags", {})
    if isinstance(config_tags, dict):
        for k, v in config_tags.items():
            # Config tags don't override the hardcoded created_by / project
            tags.setdefault(str(k), str(v))
    return tags


def tag_client(client: WorkspaceClient) -> WorkspaceClient:
    """Add project identifier to a WorkspaceClient's user-agent.

    Call this after creating a ``WorkspaceClient`` to append the
    ``project/<name>`` tag to the user-agent header.

    Args:
        client: A ``WorkspaceClient`` instance (already created with
            ``product=PRODUCT_NAME, product_version=PRODUCT_VERSION``).

    Returns:
        The same client, for chaining.
    """
    client.config.with_user_agent_extra("project", detect_project_name())
    return client

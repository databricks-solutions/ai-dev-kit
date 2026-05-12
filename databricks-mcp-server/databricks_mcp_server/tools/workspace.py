"""Workspace management tool - switch between Databricks workspaces at runtime."""

import configparser
import os
import subprocess
from typing import Any, Dict, List, Optional

from databricks_tools_core.auth import (
    get_active_workspace,
    get_workspace_client,
    set_active_workspace,
)

from ..server import mcp

_DATABRICKS_CFG_PATH = os.path.expanduser("~/.databrickscfg")
_VALID_ACTIONS = ("status", "list", "switch", "login")

_TOKEN_EXPIRED_PATTERNS = (
    "refresh token is invalid",
    "token is expired",
    "access token could not be retrieved",
    "invalid_grant",
    "token has expired",
    "unauthenticated",
    "invalid access token",
)


def _read_profiles() -> List[Dict[str, str]]:
    """Parse ~/.databrickscfg and return a list of profile dicts.

    configparser treats [DEFAULT] as a special section that does not appear
    in cfg.sections(), so we handle it explicitly via cfg.defaults().
    """
    cfg = configparser.ConfigParser()
    try:
        cfg.read(_DATABRICKS_CFG_PATH)
    except Exception:
        return []
    profiles = []
    # Include DEFAULT section if it has any keys
    if cfg.defaults():
        host = cfg.defaults().get("host", None)
        profiles.append({"profile": "DEFAULT", "host": host or "(no host configured)"})
    for section in cfg.sections():
        host = cfg.get(section, "host", fallback=None)
        profiles.append({"profile": section, "host": host or "(no host configured)"})
    return profiles


def _derive_profile_name(host: str) -> str:
    """Derive a profile name from a workspace URL.

    E.g. https://adb-1234567890.7.azuredatabricks.net -> adb-1234567890
    """
    # Strip scheme and trailing slash
    name = host.rstrip("/")
    if "://" in name:
        name = name.split("://", 1)[1]
    # Take the first hostname segment (before the first dot)
    name = name.split(".")[0]
    return name or "workspace"


def _validate_and_switch(profile: Optional[str] = None, host: Optional[str] = None) -> Dict[str, Any]:
    """Set active workspace state and validate by calling current_user.me().

    Rolls back if validation fails.

    Returns a success dict on success, raises on failure.
    """
    previous = get_active_workspace()
    set_active_workspace(profile=profile, host=host)
    try:
        client = get_workspace_client()
        me = client.current_user.me()
        return {
            "host": client.config.host,
            "profile": profile or host,
            "username": me.user_name,
        }
    except Exception as exc:
        # Roll back to previous state
        set_active_workspace(
            profile=previous["profile"],
            host=previous["host"],
        )
        raise exc


def _manage_workspace_impl(
    action: str,
    profile: Optional[str] = None,
    host: Optional[str] = None,
) -> Dict[str, Any]:
    """Business logic for manage_workspace. Separated from the MCP decorator
    so it can be imported and tested directly without FastMCP wrapping."""

    if action not in _VALID_ACTIONS:
        return {"error": f"Invalid action '{action}'. Valid actions: {', '.join(_VALID_ACTIONS)}"}

    # -------------------------------------------------------------------------
    # status: return info about the currently connected workspace
    # -------------------------------------------------------------------------
    if action == "status":
        try:
            client = get_workspace_client()
            me = client.current_user.me()
            active = get_active_workspace()
            env_profile = os.environ.get("DATABRICKS_CONFIG_PROFILE")
            return {
                "host": client.config.host,
                "profile": active["profile"] or env_profile or "(default)",
                "username": me.user_name,
            }
        except Exception as exc:
            return {"error": f"Failed to get workspace status: {exc}"}

    # -------------------------------------------------------------------------
    # list: show all profiles from ~/.databrickscfg
    # -------------------------------------------------------------------------
    if action == "list":
        profiles = _read_profiles()
        if not profiles:
            return {
                "profiles": [],
                "message": f"No profiles found in {_DATABRICKS_CFG_PATH}. "
                "Run manage_workspace(action='login', host='...') to add one.",
            }
        active = get_active_workspace()
        env_profile = os.environ.get("DATABRICKS_CONFIG_PROFILE")
        current_profile = active["profile"] or env_profile

        for p in profiles:
            p["active"] = p["profile"] == current_profile

        return {"profiles": profiles}

    # -------------------------------------------------------------------------
    # switch: change to an existing profile or host
    # -------------------------------------------------------------------------
    if action == "switch":
        if not profile and not host:
            return {"error": "Provide either 'profile' (name from ~/.databrickscfg) or 'host' (workspace URL)."}

        if profile:
            # Verify profile exists in config
            known = {p["profile"] for p in _read_profiles()}
            if profile not in known:
                suggestions = ", ".join(sorted(known)) if known else "none configured"
                return {
                    "error": f"Profile '{profile}' not found in {_DATABRICKS_CFG_PATH}. "
                    f"Available profiles: {suggestions}. "
                    "Use action='login' to authenticate a new workspace."
                }

        try:
            result = _validate_and_switch(profile=profile, host=host)
            result["message"] = f"Switched to workspace: {result['host']}"
            return result
        except Exception as exc:
            err_str = str(exc).lower()
            is_expired = any(p in err_str for p in _TOKEN_EXPIRED_PATTERNS)
            if is_expired:
                # Look up the host for this profile so the LLM can call login directly
                profile_host = host
                if not profile_host and profile:
                    for p in _read_profiles():
                        if p["profile"] == profile:
                            profile_host = p["host"]
                            break
                return {
                    "error": "Token expired or invalid for this workspace.",
                    "token_expired": True,
                    "profile": profile,
                    "host": profile_host,
                    "action_required": f"Run manage_workspace(action='login', host='{profile_host}') "
                    "to re-authenticate via browser OAuth.",
                }
            return {
                "error": f"Failed to connect to workspace: {exc}",
                "hint": "Check your credentials or use action='login' to re-authenticate.",
            }

    # -------------------------------------------------------------------------
    # login: run OAuth via the Databricks CLI then switch
    # -------------------------------------------------------------------------
    if action == "login":
        if not host:
            return {"error": "Provide 'host' (workspace URL) for the login action."}

        derived_profile = _derive_profile_name(host)

        try:
            proc = subprocess.run(
                ["databricks", "auth", "login", "--host", host, "--profile", derived_profile],
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            return {
                "error": "OAuth login timed out after 120 seconds. "
                "Please complete the browser authorization flow promptly, "
                "or run 'databricks auth login --host <url>' manually in a terminal."
            }
        except FileNotFoundError:
            return {
                "error": "Databricks CLI not found. Install it with: pip install databricks-cli "
                "or brew install databricks/tap/databricks"
            }

        if proc.returncode != 0:
            stderr = proc.stderr.strip() or proc.stdout.strip()
            return {"error": f"databricks auth login failed (exit {proc.returncode}): {stderr}"}

        try:
            conn = _validate_and_switch(profile=derived_profile, host=host)
            conn["message"] = f"Logged in and switched to workspace: {conn['host']}"
            return conn
        except Exception as exc:
            return {
                "error": f"Login succeeded but validation failed: {exc}",
                "hint": f"Try manage_workspace(action='switch', profile='{derived_profile}') manually.",
            }


@mcp.tool(timeout=60)
def manage_workspace(
    action: str,
    profile: Optional[str] = None,
    host: Optional[str] = None,
) -> Dict[str, Any]:
    """Manage active Databricks workspace connection (session-scoped).

    Actions: status (current workspace), list (profiles from ~/.databrickscfg), switch (profile or host), login (OAuth via CLI).
    Returns: {host, profile, username} or {profiles: [...]}."""
    return _manage_workspace_impl(action=action, profile=profile, host=host)

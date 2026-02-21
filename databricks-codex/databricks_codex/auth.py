"""Authentication utilities for Codex CLI integration.

Provides utilities to check Codex authentication status, manage login/logout,
and bridge Databricks credentials into Codex environment.
"""

import logging
import os
import subprocess
from dataclasses import dataclass
from typing import Optional, Tuple

from databricks_codex.models import CodexAuthMethod

logger = logging.getLogger(__name__)


@dataclass
class CodexAuthStatus:
    """Current Codex authentication status."""

    method: CodexAuthMethod
    is_authenticated: bool
    username: Optional[str] = None
    error: Optional[str] = None


def check_codex_auth() -> CodexAuthStatus:
    """Check current Codex CLI authentication status.

    Returns:
        CodexAuthStatus with current authentication state.

    Example:
        >>> status = check_codex_auth()
        >>> if status.is_authenticated:
        ...     print(f"Logged in as {status.username}")
    """
    try:
        # Check if codex CLI exists and is functional
        result = subprocess.run(
            ["codex", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return CodexAuthStatus(
                method=CodexAuthMethod.NONE,
                is_authenticated=False,
                error=f"Codex CLI error: {result.stderr.strip()}",
            )

        # Try a simple operation to verify auth
        # Note: This is a heuristic since Codex doesn't have a status command
        # We assume if --version works, the CLI is installed
        # Full auth check would require attempting an actual operation

        return CodexAuthStatus(
            method=CodexAuthMethod.CHATGPT_OAUTH,  # Assume OAuth if working
            is_authenticated=True,
        )

    except FileNotFoundError:
        return CodexAuthStatus(
            method=CodexAuthMethod.NONE,
            is_authenticated=False,
            error="Codex CLI not found. Install from: npm i -g @openai/codex",
        )
    except subprocess.TimeoutExpired:
        return CodexAuthStatus(
            method=CodexAuthMethod.NONE,
            is_authenticated=False,
            error="Codex CLI timed out",
        )
    except Exception as e:
        return CodexAuthStatus(
            method=CodexAuthMethod.NONE,
            is_authenticated=False,
            error=str(e),
        )


def login_codex(
    method: CodexAuthMethod = CodexAuthMethod.CHATGPT_OAUTH,
    api_key: Optional[str] = None,
) -> CodexAuthStatus:
    """Authenticate with Codex CLI.

    Args:
        method: Authentication method to use
        api_key: API key if using API_KEY method

    Returns:
        Updated authentication status

    Example:
        >>> status = login_codex(method=CodexAuthMethod.DEVICE_CODE)
        >>> print(f"Auth status: {status.is_authenticated}")
    """
    cmd = ["codex", "login"]

    if method == CodexAuthMethod.DEVICE_CODE:
        cmd.append("--device-auth")

    try:
        if method == CodexAuthMethod.API_KEY:
            if not api_key:
                return CodexAuthStatus(
                    method=CodexAuthMethod.NONE,
                    is_authenticated=False,
                    error="API key required for API_KEY auth method",
                )
            # Pipe API key to stdin
            result = subprocess.run(
                cmd + ["--with-api-key"],
                input=api_key,
                capture_output=True,
                text=True,
                timeout=60,
            )
        else:
            # Interactive auth (opens browser for OAuth)
            logger.info(f"Starting Codex login with method: {method.value}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180,  # Longer timeout for OAuth flow
            )

        if result.returncode == 0:
            logger.info("Codex login successful")
            return check_codex_auth()
        else:
            error_msg = result.stderr.strip() or result.stdout.strip() or "Login failed"
            logger.error(f"Codex login failed: {error_msg}")
            return CodexAuthStatus(
                method=CodexAuthMethod.NONE,
                is_authenticated=False,
                error=error_msg,
            )

    except subprocess.TimeoutExpired:
        return CodexAuthStatus(
            method=CodexAuthMethod.NONE,
            is_authenticated=False,
            error="Login timed out - user may need to complete browser auth",
        )
    except FileNotFoundError:
        return CodexAuthStatus(
            method=CodexAuthMethod.NONE,
            is_authenticated=False,
            error="Codex CLI not found",
        )
    except Exception as e:
        logger.exception("Codex login error")
        return CodexAuthStatus(
            method=CodexAuthMethod.NONE,
            is_authenticated=False,
            error=str(e),
        )


def logout_codex() -> bool:
    """Log out from Codex CLI.

    Returns:
        True if logout succeeded

    Example:
        >>> if logout_codex():
        ...     print("Logged out successfully")
    """
    try:
        result = subprocess.run(
            ["codex", "logout"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            logger.info("Codex logout successful")
            return True
        else:
            logger.warning(f"Codex logout returned: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"Codex logout error: {e}")
        return False


def get_combined_auth_context() -> Tuple[Optional[str], Optional[str]]:
    """Get Databricks auth from environment or profile.

    Used to pass Databricks credentials to Codex exec sessions.

    Priority:
    1. DATABRICKS_HOST + DATABRICKS_TOKEN environment variables
    2. databricks-tools-core get_workspace_client()
    3. (None, None) if not configured

    Returns:
        Tuple of (host, token) or (None, None) if not configured

    Example:
        >>> host, token = get_combined_auth_context()
        >>> if host:
        ...     print(f"Connected to {host}")
    """
    # First try environment variables
    host = os.environ.get("DATABRICKS_HOST")
    token = os.environ.get("DATABRICKS_TOKEN")

    if host and token:
        return (host, token)

    # Try to get from databricks-tools-core
    try:
        from databricks_tools_core.auth import get_workspace_client

        client = get_workspace_client()
        return (client.config.host, client.config.token)
    except ImportError:
        logger.debug("databricks-tools-core not available")
    except Exception as e:
        logger.debug(f"Could not get Databricks credentials: {e}")

    # Try databricks-sdk directly
    try:
        from databricks.sdk import WorkspaceClient

        client = WorkspaceClient()
        return (client.config.host, client.config.token)
    except ImportError:
        logger.debug("databricks-sdk not available")
    except Exception as e:
        logger.debug(f"Could not get Databricks credentials from SDK: {e}")

    return (None, None)


def get_databricks_env(profile: str = "DEFAULT") -> dict:
    """Get environment variables for Databricks integration.

    Args:
        profile: Databricks config profile to use

    Returns:
        Dictionary of environment variables to inject

    Example:
        >>> env = get_databricks_env(profile="PROD")
        >>> subprocess.run(["codex", "exec", "..."], env={**os.environ, **env})
    """
    env: dict = {}

    host, token = get_combined_auth_context()
    if host:
        env["DATABRICKS_HOST"] = host
    if token:
        env["DATABRICKS_TOKEN"] = token

    if profile != "DEFAULT":
        env["DATABRICKS_CONFIG_PROFILE"] = profile

    return env

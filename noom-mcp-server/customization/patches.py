"""Apply all Noom MCP governance patches.

This module is the single entry point imported by run.py.  It delegates to
three focused sub-modules and calls them in the required order.

Sub-modules
-----------
version_check         Upstream version pin — abort if the upstream has changed.
auth_guard_patch      OAuth enforcement — opens browser if no cached token exists.
sql_executor_patch    SP client override + user identity tagging on SQLExecutor.
"""

import logging

from customization.auth_guard_patch import (
    ensure_oauth_authenticated as ensure_oauth_authenticated,
)  # re-export
from customization.sql_executor_patch import patch_sql_executor as patch_sql_executor  # re-export
from customization.version_check import (  # re-export
    UpstreamChangedError as UpstreamChangedError,
    check_upstream_version as check_upstream_version,
)

logger = logging.getLogger(__name__)


def apply_all_patches() -> None:
    """Apply all Noom MCP governance patches in the correct order.

    Must be called BEFORE the first MCP tool invocation so that patches are
    in place before any SQL execution can happen.  (Importing the server
    module is safe before calling this function.)

    Execution order:
    1. check_upstream_version — version pin guard; raises UpstreamChangedError
       if the installed upstream doesn't match the validated version.
    2. patch_sql_executor — installs class-level patches on SQLExecutor for
       SP client override and user identity tagging.
    3. ensure_oauth_authenticated — validates the calling user's identity via
       OAuth; opens a browser if no cached token exists; fails on headless
       systems with instructions to run 'databricks auth login'.
    """
    check_upstream_version()
    patch_sql_executor()
    ensure_oauth_authenticated()
    logger.info("All Noom MCP governance patches applied successfully")

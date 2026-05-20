"""Apply all Noom MCP governance patches.

This module is the single entry point imported by run.py.  It delegates to
three focused sub-modules and calls them in the required order.

Sub-modules
-----------
version_check         Upstream version pin — abort if the upstream has changed.
auth_guard_patch      PAT rejection — abort if the user authenticated with a PAT.
sql_executor_patch    SP client override + user identity tagging on SQLExecutor.
"""

import logging

from noom_mcp.auth_guard_patch import check_pat_rejected as check_pat_rejected  # re-export
from noom_mcp.sql_executor_patch import patch_sql_executor as patch_sql_executor  # re-export
from noom_mcp.version_check import (  # re-export
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
    3. check_pat_rejected — validates startup credentials via a live API call;
       fails immediately if auth is PAT.
    """
    check_upstream_version()
    patch_sql_executor()
    check_pat_rejected()
    logger.info("All Noom MCP governance patches applied successfully")

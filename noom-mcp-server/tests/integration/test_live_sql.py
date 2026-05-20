"""Live SQL integration test.

Verifies that the SP client override is actually in effect by running
SELECT current_user() and asserting the result is the SP's identity,
not the calling user's identity.

Run with:
    pytest tests/integration/ --integration -v

Required environment variables
-------------------------------
DATABRICKS_HOST             Calling user's workspace (for OAuth + PAT check)
DATABRICKS_WAREHOUSE_ID     SQL warehouse to run queries against

Calling user auth (OAuth — PAT is rejected by the patch):
    Browser: run 'databricks auth login' beforehand, no env vars needed
    M2M:     set DATABRICKS_CLIENT_ID + DATABRICKS_CLIENT_SECRET

SQL SP credentials (one of):
    DATABRICKS_MCP_SECRET_SCOPE              Databricks secret scope with SP creds
    DATABRICKS_MCP_SQL_CLIENT_ID +           Direct env vars (dev/CI fallback)
      DATABRICKS_MCP_SQL_CLIENT_SECRET

    DATABRICKS_MCP_SQL_HOST                  Workspace for SQL execution
"""

import pytest


@pytest.mark.integration
def test_sql_runs_as_sp_not_calling_user(patches_applied) -> None:
    """SELECT current_user() must return the SP identity, not the calling user.

    This is the core assertion for the SP client override patch:
    if patching is in effect, all SQL runs as the pre-configured Service
    Principal regardless of who the MCP client is authenticated as.

    The warehouse ID is injected by the patch (from DATABRICKS_WAREHOUSE_ID)
    so no warehouse_id fixture is needed here.
    """
    from databricks_tools_core.auth import get_current_username
    from databricks_tools_core.sql.sql_utils.executor import SQLExecutor

    # get_current_username() uses the end user's OAuth client (DATABRICKS_HOST),
    # which the patch does NOT replace — it only overrides the client inside
    # SQLExecutor.  So this returns the human user's identity (e.g. bei@noom.com).
    calling_user = get_current_username()

    # SQLExecutor.__init__ is patched to use the SP client and the configured
    # warehouse — whatever arguments we pass here are overridden at runtime.
    executor = SQLExecutor(warehouse_id="any")

    # current_user() in SQL reflects who executed the query on Databricks.
    # If the SP override is in effect, this returns the SP's identity, not
    # the calling user's — which is what the assertion below verifies.
    rows = executor.execute("SELECT current_user() AS running_as")

    assert rows, "Query returned no rows"
    running_as = rows[0]["running_as"]
    assert running_as, "current_user() returned an empty value"

    assert running_as != calling_user, (
        f"SQL executed as the calling user ({calling_user!r}) instead of the SP.\n"
        f"  current_user() = {running_as!r}\n"
        "The SP client override patch does not appear to be in effect."
    )

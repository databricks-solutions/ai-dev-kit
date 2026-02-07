"""
Databricks SDK Authentication Examples

Documentation: https://databricks-sdk-py.readthedocs.io/en/latest/authentication.html
"""

from databricks.sdk import WorkspaceClient, AccountClient

# =============================================================================
# Pattern 1: Environment Variables (Recommended)
# =============================================================================
# Set these environment variables:
#   DATABRICKS_HOST=https://your-workspace.cloud.databricks.com
#   DATABRICKS_TOKEN=dapi...
#
# Then simply:
w = WorkspaceClient()

# Verify connection
me = w.current_user.me()
print(f"Authenticated as: {me.user_name}")


# =============================================================================
# Pattern 2: Explicit Token Authentication
# =============================================================================
w = WorkspaceClient(
    host="https://your-workspace.cloud.databricks.com",
    token="dapi..."
)


# =============================================================================
# Pattern 3: Named Profile from ~/.databrickscfg
# =============================================================================
# ~/.databrickscfg contents:
# [MY_PROFILE]
# host = https://your-workspace.cloud.databricks.com
# token = dapi...
#
w = WorkspaceClient(profile="MY_PROFILE")


# =============================================================================
# Pattern 4: Azure Service Principal
# =============================================================================
# Documentation: https://databricks-sdk-py.readthedocs.io/en/latest/authentication.html
w = WorkspaceClient(
    host="https://adb-123456789.azuredatabricks.net",
    azure_workspace_resource_id="/subscriptions/xxx/resourceGroups/xxx/providers/Microsoft.Databricks/workspaces/xxx",
    azure_tenant_id="your-tenant-id",
    azure_client_id="your-client-id",
    azure_client_secret="your-client-secret"
)


# =============================================================================
# Pattern 5: Account-Level Client
# =============================================================================
# For account-level operations (users, workspaces, billing)
# Documentation: https://databricks-sdk-py.readthedocs.io/en/latest/account/index.html
a = AccountClient(
    host="https://accounts.cloud.databricks.com",
    account_id="your-account-id",
    token="dapi..."  # Or use environment variables
)

# List workspaces in account
for workspace in a.workspaces.list():
    print(f"Workspace: {workspace.workspace_name}")


# =============================================================================
# Pattern 6: Within a Databricks Notebook
# =============================================================================
# In notebooks, credentials are auto-detected:
# from databricks.sdk import WorkspaceClient
# w = WorkspaceClient()
# # Works automatically with notebook context

---
name: databricks-config
description: "Manage Databricks workspace connections: check current workspace, switch profiles, list available workspaces, or authenticate to a new workspace. Use when the user mentions \"switch workspace\", \"which workspace\", \"current profile\", \"databrickscfg\", \"connect to workspace\", or \"databricks auth\"."
---

Use the Databricks CLI for all workspace operations.

## CLI Commands

### Check Current Workspace

```bash
# Show current configuration status
databricks auth describe

# Show current workspace URL
databricks config get --key host

# Show current profile
databricks config get --key profile
```

### List Available Profiles

```bash
# List all configured profiles from ~/.databrickscfg
cat ~/.databrickscfg | grep '^\[' | tr -d '[]'
```

### Switch Workspace/Profile

```bash
# Use a different profile for subsequent commands
databricks --profile <profile_name> auth describe

# Or set environment variable for the session
export DATABRICKS_CONFIG_PROFILE=<profile_name>
```

### Authenticate to New Workspace

```bash
# OAuth login (opens browser)
databricks auth login --host https://your-workspace.cloud.databricks.com

# OAuth login with profile name
databricks auth login --host https://your-workspace.cloud.databricks.com --profile my-profile

# Configure with PAT
databricks configure --profile my-profile
```

### Verify Authentication

```bash
# Check auth status
databricks auth describe

# Test by listing clusters
databricks clusters list
```

## ~/.databrickscfg Format

```ini
[DEFAULT]
host = https://your-workspace.cloud.databricks.com
cluster_id = 0123-456789-abc123
# or
serverless_compute_id = auto

[production]
host = https://prod-workspace.cloud.databricks.com
token = dapi...

[development]
host = https://dev-workspace.cloud.databricks.com
```

## Python SDK

```python
from databricks.sdk import WorkspaceClient

# Use default profile
w = WorkspaceClient()

# Use specific profile
w = WorkspaceClient(profile="production")

# Use specific host
w = WorkspaceClient(host="https://your-workspace.cloud.databricks.com")

# Check current user
print(w.current_user.me().user_name)
```

> **Note:** Profile changes via environment variables or CLI flags are session-scoped. For permanent profile setup, use `databricks auth login -p <profile>` and update `~/.databrickscfg` with `cluster_id` or `serverless_compute_id = auto`.

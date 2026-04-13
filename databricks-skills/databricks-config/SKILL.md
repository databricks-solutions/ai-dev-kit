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

## CLI Syntax Patterns

**IMPORTANT**: Use `--json` for creating Unity Catalog objects. This is the most reliable syntax.

```bash
# ✅ CORRECT - use --json for create operations
databricks catalogs create --json '{"name": "my_catalog"}'
databricks schemas create --json '{"name": "my_schema", "catalog_name": "my_catalog"}'
databricks volumes create --json '{"name": "my_volume", "catalog_name": "my_catalog", "schema_name": "my_schema", "volume_type": "MANAGED"}'
```

### Common CLI Patterns

```bash
# Get help for any command
databricks <command> --help
databricks schemas create --help

# List operations
databricks catalogs list
databricks schemas list CATALOG_NAME
databricks volumes list CATALOG_NAME.SCHEMA_NAME
databricks clusters list
databricks warehouses list

# Create operations (use --json)
databricks catalogs create --json '{"name": "my_catalog"}'
databricks schemas create --json '{"name": "my_schema", "catalog_name": "my_catalog"}'
databricks volumes create --json '{"name": "my_volume", "catalog_name": "my_catalog", "schema_name": "my_schema", "volume_type": "MANAGED"}'

# Delete operations (use full name)
databricks catalogs delete CATALOG_NAME
databricks schemas delete CATALOG_NAME.SCHEMA_NAME
databricks volumes delete CATALOG_NAME.SCHEMA_NAME.VOLUME_NAME
```

### SQL Execution via CLI

```bash
# Run SQL query
databricks sql execute --warehouse-id WAREHOUSE_ID --query "SELECT * FROM catalog.schema.table LIMIT 10"

# Create objects via SQL (alternative approach)
databricks sql execute --warehouse-id WAREHOUSE_ID --query "CREATE CATALOG my_catalog"
databricks sql execute --warehouse-id WAREHOUSE_ID --query "CREATE SCHEMA my_catalog.my_schema"
databricks sql execute --warehouse-id WAREHOUSE_ID --query "CREATE VOLUME my_catalog.my_schema.my_volume"
```

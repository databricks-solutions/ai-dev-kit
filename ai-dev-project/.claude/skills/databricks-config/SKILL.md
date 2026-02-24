---
name: databricks-config
description: Configure Databricks profile and authenticate for Databricks Connect, Databricks CLI, and Databricks SDK.
---

Configure the Databricks profile in ~/.databrickscfg for use with Databricks Connect.

**Usage:** `/databricks-config [profile_name|workspace_host]`

Examples:
- `/databricks-config` - Configure DEFAULT profile (interactive)
- `/databricks-config DEFAULT` - Configure DEFAULT profile
- `/databricks-config my-workspace` - Configure profile named "my-workspace"
- `/databricks-config https://adb-1234567890123456.7.azuredatabricks.net/` - Configure using workspace host URL

## Task

1. Determine the profile and host:
   - If a parameter is provided and it starts with `https://`, treat it as a workspace host:
     - Extract profile name from the host (e.g., `adb-1234567890123456.7.azuredatabricks.net` → `adb-1234567890123456`, `my-company-dev.cloud.databricks.com` → `my-company-dev`)
     - Use this as the profile name and configure it with the provided host
   - If a parameter is provided and it doesn't start with `https://`, treat it as a profile name
   - If no parameter is provided, ask the user which profile they want to configure (default: DEFAULT)

2. Run `databricks auth login -p <profile>` with the determined profile name
   - If a workspace host was provided, add `--host <workspace_host>` to the command
   - This ensures authentication is completed and the profile works
3. Check if the profile exists in ~/.databrickscfg
4. Ask the user to choose ONE of the following compute options:
   - **Cluster ID**: Provide a specific cluster ID for an interactive/all-purpose cluster
   - **Serverless**: Use serverless compute (sets `serverless_compute_id = auto`)
5. Update the profile in ~/.databrickscfg with the selected configuration
6. Verify the configuration by displaying the updated profile section

## Important Notes

- Use the AskUserQuestion tool to present the compute options as a choice
- Only add ONE of: `cluster_id` OR `serverless_compute_id` (never both)
- For serverless, set `serverless_compute_id = auto` (not just `serverless = true`)
- Preserve all existing settings in the profile (host, auth_type, etc.)
- Format the configuration file consistently with proper spacing
- The `databricks auth login` command will open a browser for OAuth authentication
- **SECURITY: NEVER print token values in plain text**
  - When displaying configuration, redact any `token` field values (e.g., `token = [REDACTED]`)
  - Inform the user they can view the full configuration at `~/.databrickscfg`
  - This applies to any output showing the profile configuration

## Example Configurations

**With Cluster ID:**
```
[DEFAULT]
host       = https://adb-123456789.11.azuredatabricks.net/
cluster_id = 1217-064531-c9c3ngyn
auth_type  = databricks-cli
```

**With Serverless:**
```
[DEFAULT]
host                  = https://adb-123456789.11.azuredatabricks.net/
serverless_compute_id = auto
auth_type             = databricks-cli
```

**With Token (display as redacted):**
```
[DEFAULT]
host       = https://adb-123456789.11.azuredatabricks.net/
token      = [REDACTED]
cluster_id = 1217-064531-c9c3ngyn

View full configuration at: ~/.databrickscfg
```

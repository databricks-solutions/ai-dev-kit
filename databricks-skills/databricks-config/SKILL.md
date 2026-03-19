---
name: databricks-config
description: "Set up Databricks CLI authentication and profiles. Use when you need to authenticate to a Databricks workspace, manage named profiles, or verify your current connection."
---

# Databricks CLI Auth & Profile Setup

Use this skill when you need to authenticate to a Databricks workspace or configure named profiles for multi-workspace workflows. For a full dev environment setup (IDE, SDK, project structure), see [dev-best-practices §2](../dev-best-practices/1-foundations-and-setup.md).

## Authenticate to a workspace

For initial CLI setup and install instructions, see [dev-best-practices §2.5](../dev-best-practices/1-foundations-and-setup.md).

```bash
# Store under a named profile (for multi-workspace workflows)
databricks auth login --host https://<your-workspace>.azuredatabricks.net --profile my-profile
```

## Multiple workspaces with named profiles

```bash
# Set up separate profiles per environment
databricks auth login --host https://dev.databricks.com  --profile dev
databricks auth login --host https://prod.databricks.com --profile prod

# Use a profile for CLI commands
databricks jobs list --profile prod
```

## Verify your connection

```bash
# Check current user and workspace
databricks current-user me

# Check a specific profile
databricks current-user me --profile dev
```

## View and edit profiles

```bash
# Show all configured profiles
databricks auth profiles

# Config file location
cat ~/.databrickscfg
```

## Set a default profile

Add `DATABRICKS_CONFIG_PROFILE=<profile>` to your shell profile (`.zshrc`, `.bashrc`) or export it in your session:

```bash
export DATABRICKS_CONFIG_PROFILE=dev
```

## Troubleshooting

- **Token expired:** Re-run `databricks auth login` for the relevant profile.
- **Wrong workspace:** Check `databricks current-user me` — confirm the host matches.
- **SDK not picking up profile:** Set `DATABRICKS_CONFIG_PROFILE` or pass `profile` explicitly in code.

```python
from databricks.sdk import WorkspaceClient
w = WorkspaceClient(profile="dev")
```

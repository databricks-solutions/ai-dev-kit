# Databricks Config

Configure Databricks profile and authenticate for Databricks Connect, Databricks CLI, and Databricks SDK.

## Overview

This skill walks through configuring a Databricks profile in `~/.databrickscfg` and authenticating via `databricks auth login`. It activates when users need to set up or update their local Databricks connection profile, choose between cluster-based or serverless compute, and verify their configuration. The skill ensures proper security practices including token redaction in output.

## What's Included

```
databricks-config/
└── SKILL.md    # Profile configuration workflow, compute options, and example configurations
```

## Key Topics

- Profile configuration in `~/.databrickscfg`
- OAuth authentication via `databricks auth login`
- Workspace host URL parsing and profile name extraction
- Compute option selection (Cluster ID vs Serverless)
- Serverless compute configuration (`serverless_compute_id = auto`)
- Token security and redaction practices

## When to Use

- Setting up a new Databricks profile for the first time
- Switching between workspace environments or compute targets
- Configuring authentication for Databricks Connect, CLI, or SDK
- Troubleshooting connection or authentication issues
- User invokes `/databricks-config` with an optional profile name or workspace URL

## Related Skills

- [Databricks Python SDK](../databricks-python-sdk/) -- uses profiles configured by this skill
- [Asset Bundles](../asset-bundles/) -- references workspace profiles for deployment targets
- [Databricks Apps (APX)](../databricks-app-apx/) -- apps that connect via configured profiles
- [Databricks Apps (Python)](../databricks-app-python/) -- Python apps using configured profiles

## Resources

- [Databricks CLI Authentication](https://docs.databricks.com/dev-tools/cli/authentication.html)
- [Databricks Configuration Profiles](https://docs.databricks.com/dev-tools/auth/index.html#configuration-profiles)
- [Databricks Connect Setup](https://docs.databricks.com/dev-tools/databricks-connect.html)

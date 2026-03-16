---
name: databricks-lakebridge
description: "Databricks Labs Lakebridge: analyze source code complexity, transpile SQL/ETL to Databricks, and reconcile data between source and target systems."
---

Lakebridge is a Databricks Labs tool for data migration. It provides three core capabilities: **Analyze** (assess source code complexity), **Transpile** (convert SQL/ETL to Databricks), and **Reconcile** (verify data consistency post-migration).

Documentation: https://databrickslabs.github.io/lakebridge/
Repository: https://github.com/databrickslabs/lakebridge

## When to Use

Use this skill when the user mentions: "lakebridge", "transpile", "reconcile", "analyze" (in a migration context), "SQL migration", "code conversion", "data reconciliation", "Switch", "BladeBridge", "Morpheus", "remorph", or migrating from other databases/ETL tools to Databricks.

## Overview

| Capability | Description | CLI Command | Reference |
|------------|-------------|-------------|-----------|
| **Analyze** | Assess source code complexity and generate migration inventory | `databricks labs lakebridge analyze` | analyze.md |
| **Transpile** | Convert SQL/ETL code to Databricks-compatible formats | `databricks labs lakebridge transpile` | transpile.md |
| **Reconcile** | Verify data consistency between source and target systems | `databricks labs lakebridge reconcile` | reconcile.md |

## Prerequisites

1. **Databricks CLI** installed and authenticated:
   ```bash
   databricks auth login --host <workspace-url> --profile <profile-name>
   ```

2. **Install Lakebridge**:
   ```bash
   databricks labs install lakebridge --profile <profile-name>
   ```

3. **Install transpilers** (for Transpile capability):
   ```bash
   databricks labs lakebridge install-transpile --profile <profile-name>
   ```
   To include the LLM-powered Switch transpiler:
   ```bash
   databricks labs lakebridge install-transpile --include-llm-transpiler true --profile <profile-name>
   ```

## Quick Start

### Analyze: Assess Source Code Complexity

```bash
databricks labs lakebridge analyze \
  --source-directory /path/to/source/code \
  --report-file /path/to/report.json \
  --source-tech <source_technology>
```

See analyze.md for supported source technologies and configuration details.

### Transpile: Convert SQL to Databricks

```bash
# Pattern-based transpilation (BladeBridge/Morpheus)
databricks labs lakebridge transpile \
  --transpiler-config-path /path/to/config.json \
  --input-source /path/to/input \
  --source-dialect <dialect> \
  --output-folder /path/to/output

# LLM-powered transpilation (Switch)
databricks labs lakebridge llm-transpile \
  --input-source /path/to/input \
  --output-ws-folder /Workspace/Users/<user>/output \
  --source-dialect <dialect> \
  --profile <profile-name>
```

See transpile.md for transpiler comparison and configuration.

### Reconcile: Verify Data Consistency

```bash
# Interactive configuration
databricks labs lakebridge configure-reconcile

# Run reconciliation
databricks labs lakebridge reconcile
```

See reconcile.md for report types and configuration reference.

## CLI Quick Reference

| Command | Description |
|---------|-------------|
| `analyze` | Analyze source code complexity and generate reports |
| `install-transpile` | Install transpiler components on workspace |
| `describe-transpile` | Show installed transpiler configuration |
| `transpile` | Run pattern-based transpilation (BladeBridge/Morpheus) |
| `llm-transpile` | Run LLM-powered transpilation (Switch) |
| `configure-reconcile` | Interactive reconcile configuration |
| `reconcile` | Run data reconciliation |
| `aggregates-reconcile` | Run aggregate-level reconciliation |

All commands support `--profile <profile-name>` to specify the Databricks CLI profile.

## Common Issues

- **Environment variables override profiles**: `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, and `DATABRICKS_AUTH_TYPE` take precedence over `--profile`. Unset them if you need to use a profile:
  ```bash
  (unset DATABRICKS_HOST DATABRICKS_TOKEN DATABRICKS_AUTH_TYPE; databricks labs lakebridge <command> --profile <profile-name>)
  ```
- **Transpiler not found**: Run `databricks labs lakebridge install-transpile` before using `transpile` or `llm-transpile`.
- **Supported sources change frequently**: Always check the [official documentation](https://databrickslabs.github.io/lakebridge/) for the latest supported source systems and dialects.

## Reference Files

- **analyze.md** - Source code analysis and complexity assessment
- **transpile.md** - SQL/ETL transpilation with BladeBridge, Morpheus, and Switch
- **reconcile.md** - Data reconciliation between source and target

## Related Skills

- `databricks-config` - Manage workspace connections and authentication
- `databricks-dbsql` - Databricks SQL features (useful for understanding target dialect)
- `databricks-unity-catalog` - Unity Catalog and volumes (used by reconcile for output)

---
name: databricks-workspace
description: "Browse, read, and create Databricks workspace notebooks and directories. Use when listing workspace contents, reading notebook source code, creating notebooks, or managing workspace directories."
---

# Databricks Workspace

Browse, read, and create notebooks and directories in the Databricks workspace filesystem.

## Overview

The Databricks workspace is a file-based hierarchy that stores notebooks, files, directories, and repos. This skill covers browsing workspace paths, reading notebook source code, creating notebooks from inline content, and managing directories.

## When to Use This Skill

Use this skill when:
- Browsing workspace paths to discover notebooks and files
- Reading notebook source code or exporting in other formats
- Creating new notebooks from inline Python, SQL, Scala, or R code
- Creating directories to organize workspace content
- Checking metadata (type, language, size) for workspace objects

## MCP Tools

| Tool | Actions | Purpose |
|------|---------|---------|
| `manage_workspace_objects` | `list`, `get_status`, `read`, `create_notebook`, `create_directory` | Browse, read, and create workspace notebooks and directories |

## Quick Start

### 1. Browse the Workspace

```python
manage_workspace_objects(action="list", path="/Users/user@example.com")
# {"path": "/Users/user@example.com", "objects": [...], "count": 5}
```

### 2. Read a Notebook

```python
manage_workspace_objects(action="read", path="/Users/user@example.com/my_notebook")
# {"path": "...", "content": "# Databricks notebook source\nprint('hello')", "format": "SOURCE"}
```

### 3. Create a Notebook

```python
manage_workspace_objects(
    action="create_notebook",
    path="/Users/user@example.com/new_notebook",
    content="# My analysis\nimport pandas as pd\ndf = pd.read_csv('data.csv')\ndf.describe()",
    language="PYTHON"
)
# {"path": "...", "language": "PYTHON", "success": true}
```

### 4. Create a Directory

```python
manage_workspace_objects(action="create_directory", path="/Users/user@example.com/my_project")
# {"path": "...", "success": true}
```

## Common Patterns

### Explore a User's Workspace

```python
# List top-level contents
manage_workspace_objects(action="list", path="/Users/user@example.com")

# Drill into a subdirectory
manage_workspace_objects(action="list", path="/Users/user@example.com/projects")

# Check details of a specific object
manage_workspace_objects(action="get_status", path="/Users/user@example.com/projects/analysis")
```

### Export a Notebook as Jupyter

```python
manage_workspace_objects(
    action="read",
    path="/Users/user@example.com/my_notebook",
    format="JUPYTER"
)
# {"content": "{...}", "format": "JUPYTER", "is_base64": false}
```

### Create a SQL Notebook

```python
manage_workspace_objects(
    action="create_notebook",
    path="/Shared/team/monthly_report",
    content="SELECT date, SUM(revenue) FROM catalog.schema.sales GROUP BY date",
    language="SQL"
)
```

### Scaffold a Project Structure

```python
# Create directories
manage_workspace_objects(action="create_directory", path="/Users/user@example.com/my_project")
manage_workspace_objects(action="create_directory", path="/Users/user@example.com/my_project/notebooks")
manage_workspace_objects(action="create_directory", path="/Users/user@example.com/my_project/utils")

# Create notebooks
manage_workspace_objects(
    action="create_notebook",
    path="/Users/user@example.com/my_project/notebooks/01_ingest",
    content="# Ingestion notebook\n...",
    language="PYTHON"
)
manage_workspace_objects(
    action="create_notebook",
    path="/Users/user@example.com/my_project/notebooks/02_transform",
    content="# Transform notebook\n...",
    language="PYTHON"
)
```

### Overwrite an Existing Notebook

```python
manage_workspace_objects(
    action="create_notebook",
    path="/Users/user@example.com/existing_notebook",
    content="# Updated content\nprint('v2')",
    language="PYTHON",
    overwrite=True
)
```

## Reference Files

| Topic | File | Description |
|-------|------|-------------|
| Workspace Objects | [workspace-objects.md](workspace-objects.md) | Object types, export formats, path conventions, and workspace hierarchy |

## Common Issues

| Issue | Solution |
|-------|----------|
| **Path not found** | Workspace paths are case-sensitive. Use `list_workspace_directory` to verify the path |
| **Cannot create notebook** | Parent directory must exist. Create it first with `create_workspace_directory` |
| **Notebook already exists** | Set `overwrite=True` to replace, or choose a different path |
| **Binary content in export** | HTML, DBC formats return base64. Use SOURCE for readable text |
| **Permission denied** | Check workspace ACLs. Users can only access their own `/Users/` path and `/Shared` |

## Related Skills

- **[databricks-repos](../databricks-repos/SKILL.md)** - Manage Git repos synced into the workspace
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** - Volume file operations for data files (not notebooks)
- **[databricks-jobs](../databricks-jobs/SKILL.md)** - Run notebooks as job tasks

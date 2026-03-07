# Lakebase Autoscaling Projects

## Overview

A project is the top-level container for Lakebase Autoscaling resources, including branches, computes, databases, and roles. Each project is isolated and contains its own Postgres version, compute defaults, and restore window settings.

## Project Structure

```
Project
  └── Branches (production, development, staging, etc.)
        ├── Computes (R/W compute, read replicas)
        ├── Roles (Postgres roles)
        └── Databases (Postgres databases)
```

When a project is created, it includes by default:
- A `production` branch (the default branch)
- A primary read-write compute (8-32 CU, autoscaling enabled, scale-to-zero disabled)
- A `databricks_postgres` database
- A Postgres role for the creating user's Databricks identity

## Resource Naming

Projects follow a hierarchical naming convention:
```
projects/{project_id}
```

**Resource ID requirements:**
- 1-63 characters long
- Lowercase letters, digits, and hyphens only
- Cannot start or end with a hyphen
- Cannot be changed after creation

## Creating a Project

### Python SDK

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.postgres import Project, ProjectSpec

w = WorkspaceClient()

# Create a project (long-running operation)
operation = w.postgres.create_project(
    project=Project(
        spec=ProjectSpec(
            display_name="My Application",
            pg_version="17"
        )
    ),
    project_id="my-app"
)

# Wait for completion
result = operation.wait()
print(f"Created project: {result.name}")
print(f"Display name: {result.status.display_name}")
print(f"Postgres version: {result.status.pg_version}")
```

### CLI

```bash
databricks postgres create-project \
    --project-id my-app \
    --json '{
        "spec": {
            "display_name": "My Application",
            "pg_version": "17"
        }
    }'
```

## Getting Project Details

### Python SDK

```python
project = w.postgres.get_project(name="projects/my-app")

print(f"Project: {project.name}")
print(f"Display name: {project.status.display_name}")
print(f"Postgres version: {project.status.pg_version}")
```

### CLI

```bash
databricks postgres get-project projects/my-app
```

**Note:** The `spec` field is not populated for GET operations. All properties are returned in the `status` field.

## Listing Projects

```python
projects = w.postgres.list_projects()

for project in projects:
    print(f"Project: {project.name}")
    print(f"  Display name: {project.status.display_name}")
    print(f"  Postgres version: {project.status.pg_version}")
```

## Updating a Project

Updates require an `update_mask` specifying which fields to modify:

```python
from databricks.sdk.service.postgres import Project, ProjectSpec, FieldMask

# Update display name
operation = w.postgres.update_project(
    name="projects/my-app",
    project=Project(
        name="projects/my-app",
        spec=ProjectSpec(
            display_name="My Updated Application"
        )
    ),
    update_mask=FieldMask(field_mask=["spec.display_name"])
)
result = operation.wait()
```

### CLI

```bash
databricks postgres update-project projects/my-app spec.display_name \
    --json '{
        "spec": {
            "display_name": "My Updated Application"
        }
    }'
```

## Deleting a Project

**WARNING:** Deleting a project is permanent and also deletes all branches, computes, databases, roles, and data.

Delete all Unity Catalog catalogs and synced tables before deleting the project.

```python
operation = w.postgres.delete_project(name="projects/my-app")
# This is a long-running operation
```

### CLI

```bash
databricks postgres delete-project projects/my-app
```

## Project Settings

### Compute Defaults

Default settings for new primary computes:
- Compute size range (0.5-112 CU)
- Scale-to-zero timeout (default: 5 minutes)

### Instant Restore

Configure the restore window length (2-35 days). Longer windows increase storage costs.

### Postgres Version

Supports Postgres 16 and Postgres 17.

## Project Limits

| Resource | Limit |
|----------|-------|
| Concurrently active computes | 20 |
| Branches per project | 500 |
| Postgres roles per branch | 500 |
| Postgres databases per branch | 500 |
| Logical data size per branch | 8 TB |
| Projects per workspace | 1000 |
| Protected branches | 1 |
| Root branches | 3 |
| Unarchived branches | 10 |
| Snapshots | 10 |
| Maximum history retention | 35 days |
| Minimum scale-to-zero time | 60 seconds |

## Long-Running Operations

All create, update, and delete operations return a long-running operation (LRO). Use `.wait()` in the SDK to block until completion:

```python
# Start operation
operation = w.postgres.create_project(...)

# Wait for completion
result = operation.wait()

# Or check status manually
op_status = w.postgres.get_operation(name=operation.name)
print(f"Done: {op_status.done}")
```

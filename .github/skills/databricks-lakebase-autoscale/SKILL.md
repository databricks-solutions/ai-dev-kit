---
name: databricks-lakebase-autoscale
description: "Patterns and best practices for using Lakebase Autoscaling (next-gen managed PostgreSQL) with autoscaling, branching, scale-to-zero, and instant restore."
---

# Lakebase Autoscaling

Patterns and best practices for using Lakebase Autoscaling, the next-generation managed PostgreSQL on Databricks with autoscaling compute, branching, scale-to-zero, and instant restore.

## When to Use

Use this skill when:
- Building applications that need a PostgreSQL database with autoscaling compute
- Working with database branching for dev/test/staging workflows
- Adding persistent state to applications with scale-to-zero cost savings
- Implementing reverse ETL from Delta Lake to an operational database via synced tables
- Managing Lakebase Autoscaling projects, branches, computes, or credentials

## Overview

Lakebase Autoscaling is Databricks' next-generation managed PostgreSQL service for OLTP workloads. It provides autoscaling compute, Git-like branching, scale-to-zero, and instant point-in-time restore.

| Feature | Description |
|---------|-------------|
| **Autoscaling Compute** | 0.5-112 CU with 2 GB RAM per CU; scales dynamically based on load |
| **Scale-to-Zero** | Compute suspends after configurable inactivity timeout |
| **Branching** | Create isolated database environments (like Git branches) for dev/test |
| **Instant Restore** | Point-in-time restore from any moment within the configured window (up to 35 days) |
| **OAuth Authentication** | Token-based auth via Databricks SDK (1-hour expiry) |
| **Reverse ETL** | Sync data from Delta tables to PostgreSQL via synced tables |

**Available Regions (AWS):** us-east-1, us-east-2, eu-central-1, eu-west-1, eu-west-2, ap-south-1, ap-southeast-1, ap-southeast-2

**Available Regions (Azure Beta):** eastus2, westeurope, westus

## Project Hierarchy

Understanding the hierarchy is essential for working with Lakebase Autoscaling:

```
Project (top-level container)
  └── Branch(es) (isolated database environments)
        ├── Compute (primary R/W endpoint)
        ├── Read Replica(s) (optional, read-only)
        ├── Role(s) (Postgres roles)
        └── Database(s) (Postgres databases)
              └── Schema(s)
```

| Object | Description |
|--------|-------------|
| **Project** | Top-level container. Created via `w.postgres.create_project()`. |
| **Branch** | Isolated database environment with copy-on-write storage. Default branch is `production`. |
| **Compute** | Postgres server powering a branch. Configurable CU sizing and autoscaling. |
| **Database** | Standard Postgres database within a branch. Default is `databricks_postgres`. |

## Quick Start

Create a project and connect:

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
result = operation.wait()
print(f"Created project: {result.name}")
```

## Common Patterns

### Generate OAuth Token

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Generate database credential for connecting (optionally scoped to an endpoint)
cred = w.postgres.generate_database_credential(
    endpoint="projects/my-app/branches/production/endpoints/ep-primary"
)
token = cred.token  # Use as password in connection string
# Token expires after 1 hour
```

### Connect from Notebook

```python
import psycopg
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Get endpoint details
endpoint = w.postgres.get_endpoint(
    name="projects/my-app/branches/production/endpoints/ep-primary"
)
host = endpoint.status.hosts.host

# Generate token (scoped to endpoint)
cred = w.postgres.generate_database_credential(
    endpoint="projects/my-app/branches/production/endpoints/ep-primary"
)

# Connect using psycopg3
conn_string = (
    f"host={host} "
    f"dbname=databricks_postgres "
    f"user={w.current_user.me().user_name} "
    f"password={cred.token} "
    f"sslmode=require"
)
with psycopg.connect(conn_string) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT version()")
        print(cur.fetchone())
```

### Create a Branch for Development

```python
from databricks.sdk.service.postgres import Branch, BranchSpec, Duration

# Create a dev branch with 7-day expiration
branch = w.postgres.create_branch(
    parent="projects/my-app",
    branch=Branch(
        spec=BranchSpec(
            source_branch="projects/my-app/branches/production",
            ttl=Duration(seconds=604800)  # 7 days
        )
    ),
    branch_id="development"
).wait()
print(f"Branch created: {branch.name}")
```

### Resize Compute (Autoscaling)

```python
from databricks.sdk.service.postgres import Endpoint, EndpointSpec, FieldMask

# Update compute to autoscale between 2-8 CU
w.postgres.update_endpoint(
    name="projects/my-app/branches/production/endpoints/ep-primary",
    endpoint=Endpoint(
        name="projects/my-app/branches/production/endpoints/ep-primary",
        spec=EndpointSpec(
            autoscaling_limit_min_cu=2.0,
            autoscaling_limit_max_cu=8.0
        )
    ),
    update_mask=FieldMask(field_mask=[
        "spec.autoscaling_limit_min_cu",
        "spec.autoscaling_limit_max_cu"
    ])
).wait()
```

## MCP Tools

The following MCP tools are available for managing Lakebase infrastructure. Use `type="autoscale"` for Lakebase Autoscaling.

### Database (Project) Management

| Tool | Description |
|------|-------------|
| `create_or_update_lakebase_database` | Create or update a database. Finds by name, creates if new, updates if existing. Use `type="autoscale"`, `display_name`, `pg_version` params. A new project auto-creates a production branch, default compute, and databricks_postgres database. |
| `get_lakebase_database` | Get database details (including branches and endpoints) or list all. Pass `name` to get one, omit to list all. Use `type="autoscale"` to filter. |
| `delete_lakebase_database` | Delete a project and all its branches, computes, and data. Use `type="autoscale"`. |

### Branch Management

| Tool | Description |
|------|-------------|
| `create_or_update_lakebase_branch` | Create or update a branch with its compute endpoint. Params: `project_name`, `branch_id`, `source_branch`, `ttl_seconds`, `is_protected`, plus compute params (`autoscaling_limit_min_cu`, `autoscaling_limit_max_cu`, `scale_to_zero_seconds`). |
| `delete_lakebase_branch` | Delete a branch and its compute endpoints. |

### Credentials

| Tool | Description |
|------|-------------|
| `generate_lakebase_credential` | Generate OAuth token for PostgreSQL connections (1-hour expiry). Pass `endpoint` resource name for autoscale. |

## Reference Files

- [projects.md](projects.md) - Project management patterns and settings
- [branches.md](branches.md) - Branching workflows, protection, and expiration
- [computes.md](computes.md) - Compute sizing, autoscaling, and scale-to-zero
- [connection-patterns.md](connection-patterns.md) - Connection patterns for different use cases
- [reverse-etl.md](reverse-etl.md) - Synced tables from Delta Lake to Lakebase

## CLI Quick Reference

```bash
# Create a project
databricks postgres create-project \
    --project-id my-app \
    --json '{"spec": {"display_name": "My App", "pg_version": "17"}}'

# List projects
databricks postgres list-projects

# Get project details
databricks postgres get-project projects/my-app

# Create a branch
databricks postgres create-branch projects/my-app development \
    --json '{"spec": {"source_branch": "projects/my-app/branches/production", "no_expiry": true}}'

# List branches
databricks postgres list-branches projects/my-app

# Get endpoint details
databricks postgres get-endpoint projects/my-app/branches/production/endpoints/ep-primary

# Delete a project
databricks postgres delete-project projects/my-app
```

## Key Differences from Lakebase Provisioned

| Aspect | Provisioned | Autoscaling |
|--------|-------------|-------------|
| SDK module | `w.database` | `w.postgres` |
| Top-level resource | Instance | Project |
| Capacity | CU_1, CU_2, CU_4, CU_8 (16 GB/CU) | 0.5-112 CU (2 GB/CU) |
| Branching | Not supported | Full branching support |
| Scale-to-zero | Not supported | Configurable timeout |
| Operations | Synchronous | Long-running operations (LRO) |
| Read replicas | Readable secondaries | Dedicated read-only endpoints |

## Common Issues

| Issue | Solution |
|-------|----------|
| **Token expired during long query** | Implement token refresh loop; tokens expire after 1 hour |
| **Connection refused after scale-to-zero** | Compute wakes automatically on connection; reactivation takes a few hundred ms; implement retry logic |
| **DNS resolution fails on macOS** | Use `dig` command to resolve hostname, pass `hostaddr` to psycopg |
| **Branch deletion blocked** | Delete child branches first; cannot delete branches with children |
| **Autoscaling range too wide** | Max - min cannot exceed 8 CU (e.g., 8-16 CU is valid, 0.5-32 CU is not) |
| **SSL required error** | Always use `sslmode=require` in connection string |
| **Update mask required** | All update operations require an `update_mask` specifying fields to modify |
| **Connection closed after 24h idle** | All connections have a 24-hour idle timeout and 3-day max lifetime; implement retry logic |

## Current Limitations

These features are NOT yet supported in Lakebase Autoscaling:
- High availability with readable secondaries (use read replicas instead)
- Databricks Apps UI integration (Apps can connect manually via credentials)
- Feature Store integration
- Stateful AI agents (LangChain memory)
- Postgres-to-Delta sync (only Delta-to-Postgres reverse ETL)
- Custom billing tags and serverless budget policies
- Direct migration from Lakebase Provisioned (use pg_dump/pg_restore or reverse ETL)

## SDK Version Requirements

- **Databricks SDK for Python**: >= 0.81.0 (for `w.postgres` module)
- **psycopg**: 3.x (supports `hostaddr` parameter for DNS workaround)
- **SQLAlchemy**: 2.x with `postgresql+psycopg` driver

```python
%pip install -U "databricks-sdk>=0.81.0" "psycopg[binary]>=3.0" sqlalchemy
```

## Notes

- **Compute Units** in Autoscaling provide ~2 GB RAM each (vs 16 GB in Provisioned).
- **Resource naming** follows hierarchical paths: `projects/{id}/branches/{id}/endpoints/{id}`.
- All create/update/delete operations are **long-running** -- use `.wait()` in the SDK.
- Tokens are short-lived (1 hour) -- production apps MUST implement token refresh.
- **Postgres versions** 16 and 17 are supported.

## Related Skills

- **[databricks-lakebase-provisioned](../databricks-lakebase-provisioned/SKILL.md)** - fixed-capacity managed PostgreSQL (predecessor)
- **[databricks-app-apx](../databricks-app-apx/SKILL.md)** - full-stack apps that can use Lakebase for persistence
- **[databricks-app-python](../databricks-app-python/SKILL.md)** - Python apps with Lakebase backend
- **[databricks-python-sdk](../databricks-python-sdk/SKILL.md)** - SDK used for project management and token generation
- **[databricks-asset-bundles](../databricks-asset-bundles/SKILL.md)** - deploying apps with Lakebase resources
- **[databricks-jobs](../databricks-jobs/SKILL.md)** - scheduling reverse ETL sync jobs

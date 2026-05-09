# Lakebase Autoscaling operations

Use `WorkspaceClient().postgres` for Autoscaling projects, branches, endpoints, roles, and credentials. Most create/update/delete methods return long-running operations; call `.wait()`.

```python
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()
```

## Resource names

```text
Project:  projects/{project_id}
Branch:   projects/{project_id}/branches/{branch_id}
Endpoint: projects/{project_id}/branches/{branch_id}/endpoints/{endpoint_id}
```

Project ID rules:
- 1–63 chars
- lowercase letters, digits, hyphens
- cannot start/end with hyphen
- immutable after creation

Default database: `databricks_postgres`.

## Projects

Create:

```python
from databricks.sdk.service.postgres import Project, ProjectSpec

project = w.postgres.create_project(
    project=Project(spec=ProjectSpec(display_name="My App", pg_version="17")),
    project_id="my-app",
).wait()
```

Project defaults:
- `production` branch
- primary read-write endpoint
- `databricks_postgres` database
- role for creator’s Databricks identity
- production scale-to-zero disabled by default

GET gotcha: effective properties are typically in `project.status`, not `project.spec`.

Update requires `FieldMask`:

```python
from databricks.sdk.service.postgres import FieldMask

w.postgres.update_project(
    name="projects/my-app",
    project=Project(
        name="projects/my-app",
        spec=ProjectSpec(display_name="New Name"),
    ),
    update_mask=FieldMask(field_mask=["spec.display_name"]),
).wait()
```

Delete is destructive and permanent; delete dependent Unity Catalog catalogs/synced tables first where applicable:

```python
w.postgres.delete_project(name="projects/my-app").wait()
```

## Branches

Branches are copy-on-write isolated database environments. Use them for dev/test/staging, schema-change validation, point-in-time recovery workflows, and ephemeral CI.

Create branch from current parent:

```python
from databricks.sdk.service.postgres import Branch, BranchSpec, Duration

branch = w.postgres.create_branch(
    parent="projects/my-app",
    branch=Branch(spec=BranchSpec(
        source_branch="projects/my-app/branches/production",
        ttl=Duration(seconds=604800),   # or no_expiry=True
    )),
    branch_id="development",
).wait()
```

Keep:
- `ttl=Duration(seconds=...)` for ephemeral branches.
- `no_expiry=True` for permanent branches.
- Max expiration period: 30 days from current time.
- Only 10 unarchived branches per project.
- Protected branches cannot be deleted, reset, archived, or expired.
- Default branch cannot be deleted or expired.
- Branches with children cannot be deleted, reset, or expired; delete children first.
- Reset replaces branch data/schema with latest parent and interrupts connections.

Protect production:

```python
w.postgres.update_branch(
    name="projects/my-app/branches/production",
    branch=Branch(
        name="projects/my-app/branches/production",
        spec=BranchSpec(is_protected=True),
    ),
    update_mask=FieldMask(field_mask=["spec.is_protected"]),
).wait()
```

Reset/delete:

```python
w.postgres.reset_branch(name="projects/my-app/branches/development").wait()
w.postgres.delete_branch(name="projects/my-app/branches/development").wait()
```

Branch status fields worth inspecting:
- `status.default`
- `status.is_protected`
- `status.current_state`
- `status.logical_size_bytes`
- `status.expire_time`

## Endpoints / computes

A compute endpoint runs Postgres for a branch. Each branch has at most one primary read-write endpoint and may have read-only replica endpoints.

Create endpoint:

```python
from databricks.sdk.service.postgres import Endpoint, EndpointSpec, EndpointType

ep = w.postgres.create_endpoint(
    parent="projects/my-app/branches/production",
    endpoint=Endpoint(spec=EndpointSpec(
        endpoint_type=EndpointType.ENDPOINT_TYPE_READ_WRITE,
        autoscaling_limit_min_cu=0.5,
        autoscaling_limit_max_cu=4.0,
    )),
    endpoint_id="ep-primary",
).wait()
```

Get host:

```python
host = w.postgres.get_endpoint(
    name="projects/my-app/branches/production/endpoints/ep-primary"
).status.hosts.host
```

Resize with update mask:

```python
w.postgres.update_endpoint(
    name="projects/my-app/branches/production/endpoints/ep-primary",
    endpoint=Endpoint(
        name="projects/my-app/branches/production/endpoints/ep-primary",
        spec=EndpointSpec(
            autoscaling_limit_min_cu=2.0,
            autoscaling_limit_max_cu=8.0,
        ),
    ),
    update_mask=FieldMask(field_mask=[
        "spec.autoscaling_limit_min_cu",
        "spec.autoscaling_limit_max_cu",
    ]),
).wait()
```

Delete:

```python
w.postgres.delete_endpoint(
    name="projects/my-app/branches/production/endpoints/ep-primary"
).wait()
```

## Compute sizing

Autoscaling uses ~2 GB RAM per CU.

| CU | Approx RAM | Max connections |
|---:|---:|---:|
| 0.5 | ~1 GB | 104 |
| 1 | ~2 GB | 209 |
| 4 | ~8 GB | 839 |
| 8 | ~16 GB | 1,678 |
| 16 | ~32 GB | 3,357 |
| 32 | ~64 GB | 4,000 |
| 64 | ~128 GB | 4,000 |
| 112 | ~224 GB | 4,000 |

Rules:
- Autoscale range: 0.5–32 CU.
- `autoscaling_limit_max_cu - autoscaling_limit_min_cu <= 8`.
- Valid: 4–8, 8–16, 16–24.
- Invalid: 0.5–32.
- Large fixed-size computes: 36–112 CU; no autoscaling.
- Connection limit is based on max CU.
- Set min CU high enough for working-set cache and latency needs.

## Scale-to-zero

Defaults:
- `production`: disabled by default.
- Other branches: configurable.
- Default inactivity timeout: 5 minutes.
- Minimum inactivity timeout: 60 seconds.

Wake-up:
- First connection wakes compute automatically.
- Apps should use retry/backoff for the brief reactivation period.
- Reactivated compute starts at minimum autoscaling size.

Session reset after suspension:
- temp tables gone
- prepared statements gone
- in-memory stats/cache cleared
- session settings reset
- active transactions/connections terminated

Disable scale-to-zero for latency-critical apps or apps relying on persistent session state.

## Project limits

| Resource | Limit |
|---|---:|
| Projects per workspace | 1000 |
| Branches per project | 500 |
| Unarchived branches | 10 |
| Root branches | 3 |
| Protected branches | 1 |
| Concurrently active computes | 20 |
| Postgres roles per branch | 500 |
| Postgres databases per branch | 500 |
| Logical data size per branch | 8 TB |
| Snapshots | 10 |
| Maximum history retention | 35 days |
| Minimum scale-to-zero time | 60 sec |

## CLI names

CLI mirrors the SDK under `databricks postgres`, for example:
- `create-project`, `get-project`, `list-projects`, `update-project`, `delete-project`
- `create-branch`, `list-branches`, `reset-branch`, `delete-branch`
- `create-endpoint`, `get-endpoint`, `list-endpoints`, `update-endpoint`, `delete-endpoint`

## MCP tools

Use `type="autoscale"` for Lakebase Autoscaling.

### `manage_lakebase_database`

Actions:
- `create_or_update`: requires `name`; useful params include `display_name`, `pg_version`
- `get`: requires `name`
- `list`: optional type filter
- `delete`: requires `name`

Example intent:

```python
manage_lakebase_database(
    action="create_or_update",
    name="my-app",
    type="autoscale",
    display_name="My Application",
    pg_version="17",
)
```

### `manage_lakebase_branch`

Actions:
- `create_or_update`: requires `project_name`, `branch_id`
- `delete`: requires full branch `name`

Useful params:
- `source_branch`
- `ttl_seconds`
- `autoscaling_limit_min_cu`
- `autoscaling_limit_max_cu`
- `scale_to_zero_seconds`

### `generate_lakebase_credential`

Generate a Lakebase-scoped database credential:

```python
generate_lakebase_credential(
    endpoint="projects/my-app/branches/production/endpoints/ep-primary"
)
```

Use returned token as the Postgres password with `sslmode=require`.

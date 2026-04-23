# Lakebase Autoscaling — Projects (deep dive)

Deep dive for the Projects concept. Basic CLI is in [SKILL.md](SKILL.md).

## What a Project Is

A project is the top-level isolation boundary: its own Postgres major version, compute defaults, restore window, and hierarchical namespace for branches/endpoints/databases/roles. Projects do not share storage or compute with each other.

A freshly created project contains:
- Default branch `production` (cannot be deleted; default scale-to-zero **off**)
- Primary R/W endpoint named `primary` (1 CU min/max by default, autoscaling on)
- Database `databricks_postgres`
- A Postgres role mapped to the creator's Databricks identity

## Naming Rules

Path: `projects/{project_id}`. The `project_id` must be 1-63 chars, `[a-z0-9-]`, no leading/trailing hyphen, and is immutable.

## Defaults & Settings

| Setting | Default | Configurable range |
|---------|---------|--------------------|
| Postgres version | 17 | 16 or 17 |
| Scale-to-zero (production) | off | off always; cannot be enabled on default branch |
| Scale-to-zero (other branches) | 5 min | ≥ 60 s |
| Primary endpoint CU range | 1-1 (creator can override) | 0.5-32 (autoscale) or 36-112 (fixed) |
| Restore window | 1 day | 2-35 days |

Longer restore windows increase storage cost.

## Limits

| Resource | Limit |
|----------|-------|
| Projects per workspace | 1,000 |
| Concurrently active computes per project | 20 |
| Branches per project | 500 |
| Unarchived branches | 10 |
| Root branches | 3 |
| Protected branches | 1 |
| Roles / databases per branch | 500 / 500 |
| Logical data size per branch | 8 TB |
| Snapshots | 10 |
| Max history retention | 35 days |
| Min scale-to-zero time | 60 s |

## Long-Running Operations

Every create/update/delete returns an LRO. The CLI blocks until `done=true` by default; programmatic callers can poll:

```bash
# Start async and get an operation name back (advanced; the default CLI behaviour is blocking)
databricks postgres list-operations projects/my-app
databricks postgres get-operation projects/my-app/operations/op-<id>
```

## Advanced CLI

Full update with multiple fields (durations are ISO8601-style strings like `"2592000s"`):

```bash
databricks postgres update-project projects/my-app \
    "spec.display_name,spec.history_retention_duration" \
    --json '{"spec": {"display_name": "My App (prod)",
                      "history_retention_duration": "2592000s"}}'  # 30 days
```

Deleting a project with active synced tables fails — drop the UC synced tables and catalogs first, then delete.

## Field Reference

Returned fields on `get-project` live under `status`, **not** `spec`:

```
status.display_name
status.pg_version
status.history_retention_duration        # e.g. "86400s"
status.enable_pg_native_login
status.owner
status.default_endpoint_settings.autoscaling_limit_min_cu
status.default_endpoint_settings.autoscaling_limit_max_cu
status.default_endpoint_settings.suspend_timeout_duration   # scale-to-zero; "0s" = off
create_time
update_time
uid
```

## SDK Equivalents

Use these only inside Python automation where shelling out to the CLI is awkward. Requires `databricks-sdk>=0.81.0`.

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.postgres import Project, ProjectSpec, FieldMask

w = WorkspaceClient()

# Create
w.postgres.create_project(
    project=Project(spec=ProjectSpec(display_name="My App", pg_version="17")),
    project_id="my-app",
).wait()

# Get / list
w.postgres.get_project(name="projects/my-app")
list(w.postgres.list_projects())

# Update
w.postgres.update_project(
    name="projects/my-app",
    project=Project(name="projects/my-app",
                    spec=ProjectSpec(display_name="Renamed App")),
    update_mask=FieldMask(field_mask=["spec.display_name"]),
).wait()

# Delete
w.postgres.delete_project(name="projects/my-app").wait()

# Poll an LRO manually instead of .wait()
op = w.postgres.create_project(...)
w.postgres.get_operation(name=op.name).done
```

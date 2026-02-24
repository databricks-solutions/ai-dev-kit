# Lakebase Autoscaling Branches

## Overview

Branches in Lakebase Autoscaling are isolated database environments that share storage with their parent through copy-on-write. They enable Git-like workflows for databases: create isolated dev/test environments, test schema changes safely, and recover from mistakes.

## Branch Types

| Option | Description | Use Case |
|--------|-------------|----------|
| **Current data** | Branch from latest state of parent | Development, testing with current data |
| **Past data** | Branch from a specific point in time | Point-in-time recovery, historical analysis |

## Creating a Branch

### With Expiration (TTL)

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.postgres import Branch, BranchSpec, Duration

w = WorkspaceClient()

# Create branch with 7-day expiration
result = w.postgres.create_branch(
    parent="projects/my-app",
    branch=Branch(
        spec=BranchSpec(
            source_branch="projects/my-app/branches/production",
            ttl=Duration(seconds=604800)  # 7 days
        )
    ),
    branch_id="development"
).wait()

print(f"Branch created: {result.name}")
print(f"Expires: {result.status.expire_time}")
```

### Permanent Branch (No Expiration)

```python
result = w.postgres.create_branch(
    parent="projects/my-app",
    branch=Branch(
        spec=BranchSpec(
            source_branch="projects/my-app/branches/production",
            no_expiry=True
        )
    ),
    branch_id="staging"
).wait()
```

### CLI

```bash
# With TTL
databricks postgres create-branch projects/my-app development \
    --json '{
        "spec": {
            "source_branch": "projects/my-app/branches/production",
            "ttl": "604800s"
        }
    }'

# Permanent
databricks postgres create-branch projects/my-app staging \
    --json '{
        "spec": {
            "source_branch": "projects/my-app/branches/production",
            "no_expiry": true
        }
    }'
```

## Getting Branch Details

```python
branch = w.postgres.get_branch(
    name="projects/my-app/branches/development"
)

print(f"Branch: {branch.name}")
print(f"Protected: {branch.status.is_protected}")
print(f"Default: {branch.status.default}")
print(f"State: {branch.status.current_state}")
print(f"Size: {branch.status.logical_size_bytes} bytes")
```

## Listing Branches

```python
branches = list(w.postgres.list_branches(
    parent="projects/my-app"
))

for branch in branches:
    print(f"Branch: {branch.name}")
    print(f"  Default: {branch.status.default}")
    print(f"  Protected: {branch.status.is_protected}")
```

## Protecting a Branch

Protected branches cannot be deleted, reset, or archived.

```python
from databricks.sdk.service.postgres import Branch, BranchSpec, FieldMask

w.postgres.update_branch(
    name="projects/my-app/branches/production",
    branch=Branch(
        name="projects/my-app/branches/production",
        spec=BranchSpec(is_protected=True)
    ),
    update_mask=FieldMask(field_mask=["spec.is_protected"])
).wait()
```

To remove protection:

```python
w.postgres.update_branch(
    name="projects/my-app/branches/production",
    branch=Branch(
        name="projects/my-app/branches/production",
        spec=BranchSpec(is_protected=False)
    ),
    update_mask=FieldMask(field_mask=["spec.is_protected"])
).wait()
```

## Updating Branch Expiration

```python
# Extend to 14 days
w.postgres.update_branch(
    name="projects/my-app/branches/development",
    branch=Branch(
        name="projects/my-app/branches/development",
        spec=BranchSpec(
            is_protected=False,
            ttl=Duration(seconds=1209600)  # 14 days
        )
    ),
    update_mask=FieldMask(field_mask=["spec.is_protected", "spec.expiration"])
).wait()

# Remove expiration
w.postgres.update_branch(
    name="projects/my-app/branches/development",
    branch=Branch(
        name="projects/my-app/branches/development",
        spec=BranchSpec(no_expiry=True)
    ),
    update_mask=FieldMask(field_mask=["spec.expiration"])
).wait()
```

## Resetting a Branch from Parent

Reset completely replaces a branch's data and schema with the latest from its parent. Local changes are lost.

```python
w.postgres.reset_branch(
    name="projects/my-app/branches/development"
).wait()
```

**Constraints:**
- Root branches (like `production`) cannot be reset (no parent)
- Branches with children cannot be reset (delete children first)
- Connections are temporarily interrupted during reset

## Deleting a Branch

```python
w.postgres.delete_branch(
    name="projects/my-app/branches/development"
).wait()
```

**Constraints:**
- Cannot delete branches with child branches (delete children first)
- Cannot delete protected branches (remove protection first)
- Cannot delete the default branch

## Branch Expiration

Branch expiration sets an automatic deletion timestamp. Useful for:
- **CI/CD environments**: 2-4 hours
- **Demos**: 24-48 hours
- **Feature development**: 1-7 days
- **Long-term testing**: up to 30 days

**Maximum expiration period:** 30 days from current time.

### Expiration Restrictions

- Cannot expire protected branches
- Cannot expire default branches
- Cannot expire branches that have children
- When a branch expires, all compute resources are also deleted

## Best Practices

1. **Use TTL for ephemeral branches**: Set expiration for dev/test branches to avoid accumulation
2. **Protect production branches**: Prevent accidental deletion or reset
3. **Reset instead of recreate**: Use reset from parent when you need fresh data without new branch overhead
4. **Schema diff before merge**: Compare schemas between branches before applying changes to production
5. **Monitor unarchived limit**: Only 10 unarchived branches are allowed per project

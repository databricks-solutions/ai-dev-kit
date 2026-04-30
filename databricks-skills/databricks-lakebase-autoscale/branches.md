# Lakebase Autoscaling — Branches (deep dive)

Deep dive for the Branches concept. Basic CLI is in [SKILL.md](SKILL.md).

## How Branching Works

A branch is a logical Postgres instance whose storage is a **copy-on-write** fork of its parent at a specific LSN (point in the parent's WAL history). Reads hit the shared base until a page is modified; writes create branch-local copies. This is why branches are cheap to create and diverge gradually.

Consequences:
- Creating a branch is nearly instant regardless of parent size.
- Storage grows with write volume on the branch, not with the parent's size.
- Resetting a branch drops its CoW layer and re-points at the parent's current state.

## Branch Sources

When creating a branch you pick a source LSN implicitly:

| Option | `spec` field | Use case |
|--------|--------------|----------|
| Current data | `source_branch` only | Dev/test with up-to-date data |
| Past data | `source_branch` + `source_lsn` or `source_time` | Point-in-time recovery, reproduce a bug |

Past-data branching is bounded by the project's `history_retention_seconds` (default 7 days, max 35).

## TTL & Permanence

Branches are either ephemeral (TTL) or permanent (`no_expiry: true`). Max TTL is 30 days from creation. You **cannot** set TTL on:
- Protected branches
- The default branch (`production`)
- Branches that have children

When a TTL branch expires, its endpoints and data are deleted.

## Protection

A protected branch cannot be deleted, reset, or archived. Only 1 branch per project can be protected. Typically this is `production`. Protection is stored on the branch spec and toggled with `update-branch`.

## Reset

`reset-branch` replaces a branch's CoW layer with a fresh fork from its parent's current head. Effect:
- All local schema and data changes are discarded
- Active connections are interrupted briefly
- Cannot run on: root branches (no parent), protected branches, parents-of-others

Use reset when your dev branch has drifted and you want fresh data without recreating the branch (preserves the branch name and any downstream config).

## Constraints Cheat-Sheet

| Action | Blocked when |
|--------|-------------|
| Delete | Has children; is protected; is default |
| Reset | Is root; has children; is protected |
| TTL/expire | Is protected; is default; has children |
| Archive | Is protected |

## Advanced CLI

Past-data branch from LSN:

```bash
databricks postgres create-branch projects/my-app debug-bug-1234 \
    --json '{"spec": {"source_branch": "projects/my-app/branches/production",
                      "source_lsn": "0/1A2B3C4D",
                      "no_expiry": true}}'
```

Past-data branch from timestamp:

```bash
databricks postgres create-branch projects/my-app pre-incident \
    --json '{"spec": {"source_branch": "projects/my-app/branches/production",
                      "source_time": "2026-04-20T14:30:00Z",
                      "ttl": "86400s"}}'
```

Extend or drop a TTL:

```bash
# Extend to 14 days
databricks postgres update-branch projects/my-app/branches/development \
    spec.expiration --json '{"spec": {"ttl": "1209600s"}}'

# Convert to permanent
databricks postgres update-branch projects/my-app/branches/development \
    spec.expiration --json '{"spec": {"no_expiry": true}}'
```

## Best Practices

- TTL everything ephemeral — dev/CI branches accumulate fast against the 10-unarchived limit.
- Protect `production` at project creation time, not "eventually".
- Prefer reset over recreate when you just need fresh data — it preserves the branch name and downstream references.
- Compare schemas between branches (`pg_dump --schema-only`) before merging changes back upstream.

## Typical TTL Envelopes

| Workload | TTL |
|----------|-----|
| CI run | 2-4 h |
| Demo | 24-48 h |
| Feature branch | 1-7 days |
| Long-lived test env | up to 30 days |

## SDK Equivalents

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.postgres import Branch, BranchSpec, Duration, FieldMask

w = WorkspaceClient()

# Create (TTL or permanent)
w.postgres.create_branch(
    parent="projects/my-app",
    branch=Branch(spec=BranchSpec(
        source_branch="projects/my-app/branches/production",
        ttl=Duration(seconds=604800),      # or: no_expiry=True
    )),
    branch_id="development",
).wait()

# Protect
w.postgres.update_branch(
    name="projects/my-app/branches/production",
    branch=Branch(name="projects/my-app/branches/production",
                  spec=BranchSpec(is_protected=True)),
    update_mask=FieldMask(field_mask=["spec.is_protected"]),
).wait()

# Reset / delete
w.postgres.reset_branch(name="projects/my-app/branches/development").wait()
w.postgres.delete_branch(name="projects/my-app/branches/development").wait()
```

---
name: databricks-lakebase-autoscale
description: "Manage Lakebase Postgres Autoscaling projects, branches, and endpoints via Databricks CLI. Use when asked to create, configure, or manage Lakebase Postgres databases, projects, branches, computes, or endpoints."
compatibility: Requires databricks CLI (>= v0.294.0)
metadata:
  version: "0.2.0"
---

# Lakebase Postgres Autoscaling

Lakebase is Databricks' serverless Postgres-compatible database, available on both AWS and Azure (GA). It provides fully managed OLTP storage with autoscaling, branching, and scale-to-zero.

> **Autoscaling by Default (March 2026):** All new Lakebase instances are Autoscaling projects. The `/database/` APIs now create autoscaling instances behind the scenes. Existing provisioned instances are unchanged.

**Compliance:** Supports HIPAA, C5, TISAX, or None.

| Feature | Status |
|---------|--------|
| Autoscaling Compute | 0.5--32 CU dynamic, 36--112 CU fixed (~2 GB RAM/CU) |
| Scale-to-Zero | Default 5 min timeout, minimum 60s |
| Branching | Copy-on-write isolated environments |
| Point-in-Time Branching | Create branches from past state |
| OAuth Authentication | 1-hour token expiry, refresh before expiry |
| High Availability | 1 primary + 1--3 secondaries, automatic failover |
| Data API | PostgREST-compatible HTTP CRUD (Autoscaling only) |
| Reverse ETL | Sync Delta tables to Postgres via synced tables |
| Cloud Support | AWS and Azure (GA) |

**Reference docs:**
- [computes-and-scaling.md](references/computes-and-scaling.md) — Sizing, endpoint management, scale-to-zero, HA
- [connectivity.md](references/connectivity.md) — Connection patterns, token refresh, Data API
- [reverse-etl.md](references/reverse-etl.md) — Synced tables, data type mapping, capacity planning

## Resource Hierarchy

```
Project (top-level container)
  └── Branch (isolated database environment, copy-on-write)
        ├── Endpoint (read-write or read-only)
        ├── Database (standard Postgres DB)
        └── Role (Postgres role)
```

- **Project**: Top-level container. Creating one auto-provisions a `production` branch and a `primary` read-write endpoint.
- **Branch**: Isolated database environment sharing storage with parent (copy-on-write). States: `READY`, `ARCHIVED`.
- **Endpoint** (called **Compute** in UI): Compute resource powering a branch. Types: `ENDPOINT_TYPE_READ_WRITE`, `ENDPOINT_TYPE_READ_ONLY`.
- **Database**: Standard Postgres database within a branch. Default: `databricks_postgres`.
- **Role**: Postgres role within a branch.

### Resource Name Formats

| Resource | Format |
|----------|--------|
| Project | `projects/{project_id}` |
| Branch | `projects/{project_id}/branches/{branch_id}` |
| Endpoint | `projects/{project_id}/branches/{branch_id}/endpoints/{endpoint_id}` |
| Database | `projects/{project_id}/branches/{branch_id}/databases/{database_id}` |

All IDs: 1-63 characters, start with lowercase letter, lowercase letters/numbers/hyphens only (RFC 1123).

## CLI Discovery -- ALWAYS Do This First

> **Note:** "Lakebase" is the product name; the CLI command group is `postgres`. All commands use `databricks postgres ...`.

**Do NOT guess command syntax.** Discover available commands dynamically:

```bash
databricks postgres -h                    # List all subcommands
databricks postgres <subcommand> -h       # Flags, args, JSON fields
```

## Create a Project

> **Do NOT list projects before creating.**

```bash
databricks postgres create-project <PROJECT_ID> \
  --json '{"spec": {"display_name": "<DISPLAY_NAME>", "pg_version": "17"}}' \
  --profile <PROFILE>
```

Auto-creates: `production` branch + `primary` read-write endpoint (1 CU min/max, scale-to-zero). Long-running operation; CLI waits by default. Use `--no-wait` to return immediately.

After creation, verify:

```bash
databricks postgres list-branches projects/<PROJECT_ID> --profile <PROFILE>
databricks postgres list-endpoints projects/<PROJECT_ID>/branches/<BRANCH_ID> --profile <PROFILE>
```

### Updating a Project

```bash
databricks postgres update-project projects/<PROJECT_ID> spec.display_name \
  --json '{"spec": {"display_name": "My Updated Application"}}' \
  --profile <PROFILE>
```

### Deleting a Project

**WARNING:** Permanent -- deletes all branches, computes, databases, roles, and data. **Do not delete without explicit user permission.**

```bash
databricks postgres delete-project projects/<PROJECT_ID> --profile <PROFILE>
```

## Autoscaling

Endpoints use **compute units (CU)** (~2 GB RAM per CU). Configure min/max CU on endpoints.

- **Autoscale range:** 0.5--32 CU (dynamic). **Fixed-size:** 36--112 CU.
- **Constraint:** Max - Min cannot exceed 16 CU.
- **Scale-to-zero:** Enabled by default (5 min timeout).

See [computes-and-scaling.md](references/computes-and-scaling.md) for sizing tables, endpoint CRUD, and scale-to-zero details.

```bash
# Resize an endpoint
databricks postgres update-endpoint \
  projects/<PROJECT_ID>/branches/<BRANCH_ID>/endpoints/<ENDPOINT_ID> \
  "spec.autoscaling_limit_min_cu,spec.autoscaling_limit_max_cu" \
  --json '{"spec": {"autoscaling_limit_min_cu": 2.0, "autoscaling_limit_max_cu": 8.0}}' \
  --profile <PROFILE>
```

## Branches

Branches are copy-on-write snapshots. Use for testing schema migrations, trying queries, or previewing data changes without affecting production.

```bash
databricks postgres create-branch projects/<PROJECT_ID> <BRANCH_ID> \
  --json '{"spec": {"source_branch": "projects/<PROJECT_ID>/branches/<SOURCE>", "no_expiry": true}}' \
  --profile <PROFILE>
```

Branches require an expiration policy: `"no_expiry": true` for permanent, or `"ttl": "<seconds>s"` (max 30 days).

**Limits:** 10 unarchived branches per project. 8 TB logical data per branch. 1,000 projects per workspace.

| Use Case | TTL |
|----------|-----|
| CI/CD environments | 2--4 hours (`"ttl": "14400s"`) |
| Demos | 24--48 hours (`"ttl": "172800s"`) |
| Feature development | 1--7 days (`"ttl": "604800s"`) |
| Long-term testing | Up to 30 days (`"ttl": "2592000s"`) |

**Point-in-time branching:** Create from a past state (within restore window) for recovery. Run `databricks postgres create-branch -h` for time specification fields.

**Reset:** Replaces branch data with latest from parent. Local changes are lost. Root branches and branches with children cannot be reset. Reset is currently available via the SDK (`w.postgres.reset_branch(...)`) or REST API — not yet exposed as a `databricks postgres reset-branch` CLI subcommand in CLI v0.298.0.

**Delete:** Protected branches must be unprotected first (`update-branch` to set `spec.is_protected` to `false`). Cannot delete branches with children. **Never delete the `production` branch.**

```bash
# Unprotect, then delete
databricks postgres update-branch projects/<PROJECT_ID>/branches/<BRANCH_ID> spec.is_protected \
  --json '{"spec": {"is_protected": false}}' --profile <PROFILE>
databricks postgres delete-branch projects/<PROJECT_ID>/branches/<BRANCH_ID> --profile <PROFILE>
```

## Key Differences from Lakebase Provisioned

> All new instances default to Autoscaling as of March 2026. Automatic migration of Provisioned instances begins June 2026.

| Aspect | Provisioned | Autoscaling |
|--------|-------------|-------------|
| CLI group | `databricks database` | `databricks postgres` |
| SDK module | `w.database` | `w.postgres` |
| Top-level resource | Instance | Project |
| Capacity | Named sizes: CU_1, CU_2, CU_4, CU_8 (~16 GB RAM each) | 0.5--112 CU (~2 GB RAM/CU) |
| Branching | Not supported | Full support |
| Scale-to-zero | Not supported | Configurable |
| HA | Readable secondaries | 1--3 secondaries + read replicas |
| Data API | Not available | PostgREST HTTP API |
| Operations | Synchronous | Long-running operations (LRO) |
| Cloud | AWS only | AWS and Azure |

**Migration:** Manual via `pg_dump`/`pg_restore` (requires pausing writes). Automatic seamless upgrades (seconds of downtime) begin June 2026 -- no customer action required.

## What's Next

### Build a Databricks App

After creating a project, scaffold a connected Databricks App:

```bash
# 1. Get branch name
databricks postgres list-branches projects/<PROJECT_ID> --profile <PROFILE>

# 2. Get database name
databricks postgres list-databases projects/<PROJECT_ID>/branches/<BRANCH_ID> --profile <PROFILE>

# 3. Scaffold with lakebase feature
databricks apps init --name <APP_NAME> --features lakebase \
  --set "lakebase.postgres.branch=<BRANCH_NAME>" \
  --set "lakebase.postgres.database=<DATABASE_NAME>" \
  --run none --profile <PROFILE>
```

For the full app workflow, use the **`databricks-app-python`** skill.

### Other Workflows

```bash
# Connect a Postgres client -- get connection string
databricks postgres get-endpoint projects/<PROJECT_ID>/branches/<BRANCH_ID>/endpoints/<ENDPOINT_ID> --profile <PROFILE>

# Generate a 1-hour OAuth token for a specific endpoint
databricks postgres generate-database-credential \
  projects/<PROJECT_ID>/branches/<BRANCH_ID>/endpoints/<ENDPOINT_ID> --profile <PROFILE>

# Manage roles
databricks postgres create-role -h

# Add a read replica
databricks postgres create-endpoint projects/<PROJECT_ID>/branches/<BRANCH_ID> <ENDPOINT_ID> \
  --json '{"spec": {"endpoint_type": "ENDPOINT_TYPE_READ_ONLY"}}' --profile <PROFILE>
```

**Data API:** PostgREST-compatible HTTP CRUD on Postgres tables. See [connectivity.md](references/connectivity.md).
**Reverse ETL:** Sync Delta tables into Lakebase. See [reverse-etl.md](references/reverse-etl.md).

## Troubleshooting

| Error | Solution |
|-------|----------|
| `cannot configure default credentials` | Use `--profile` flag or authenticate first |
| `PERMISSION_DENIED` | Check workspace permissions |
| `permission denied for schema` | Schema owned by another role. Deploy app first so SP creates/owns it |
| Protected branch won't delete | `update-branch` to set `spec.is_protected` to `false` first |
| Long-running operation timeout | Use `--no-wait` and poll with `get-operation` |
| Token expired during long query | Tokens expire after 1 hour; implement refresh (see [connectivity.md](references/connectivity.md)) |
| Connection refused after scale-to-zero | Compute wakes in ~100ms; implement retry logic |
| Branch deletion blocked | Delete child branches first |
| Autoscaling range too wide | Max - Min cannot exceed 16 CU |
| SSL required error | Always use `sslmode=require` |
| Update mask required | All `update-*` operations require specifying fields (see `-h`) |
| Connection closed after idle | 24h idle timeout; max lifetime beyond 24h not guaranteed. Implement retry. |
| DNS resolution fails (macOS) | Python `socket.getaddrinfo()` fails with long hostnames. Use `dig` to resolve IP, pass via `hostaddr` param alongside `host` (for TLS SNI). See [connectivity.md](references/connectivity.md). |

## SDK and Version Requirements

| Component | Minimum Version |
|-----------|----------------|
| Databricks CLI | >= v0.294.0 |
| Databricks SDK for Python | >= 0.81.0 (for `w.postgres` module) |
| psycopg | 2.x or 3.x (3.x recommended for async/pooling) |
| Postgres | 16 or 17 (default: PG 17) |

```python
%pip install -U "databricks-sdk>=0.81.0" "psycopg[binary]>=3.0" sqlalchemy
```

## Related Skills

- **[databricks-lakebase-provisioned](../databricks-lakebase-provisioned/SKILL.md)** - fixed-capacity managed PostgreSQL (predecessor)
- **[databricks-app-python](../databricks-app-python/SKILL.md)** - Python apps with Lakebase backend
- **[databricks-bundles](../databricks-bundles/SKILL.md)** - deploying apps with Lakebase resources

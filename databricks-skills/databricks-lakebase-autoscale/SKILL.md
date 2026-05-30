---
name: databricks-lakebase-autoscale
description: "Patterns and best practices for Lakebase Autoscaling (next-gen managed PostgreSQL). Use when creating or managing Lakebase Autoscaling projects, configuring autoscaling compute or scale-to-zero, working with database branching for dev/test workflows, implementing reverse ETL via synced tables, connecting applications to Lakebase with OAuth credentials, or migrating an existing Lakebase Provisioned database to Autoscaling via pg_dump/pg_restore."
---

# Lakebase Autoscaling

Lakebase Autoscaling is Databricks' next-generation managed PostgreSQL service for OLTP workloads: autoscaling compute, database branching, scale-to-zero, instant restore, and Delta-to-Postgres synced tables.

Use this skill when creating/managing Lakebase Autoscaling projects, branches, endpoints/computes, credentials, reverse ETL synced tables, or app connections.

## Core framing

> **There is no separate Python “Lakebase SDK.”** Use `databricks-sdk` for management and for minting short-lived database credentials with `WorkspaceClient().postgres.generate_database_credential(...)`; use standard Postgres drivers (`psycopg`, SQLAlchemy, JDBC, `pgx`, etc.) for SQL.

| Language | Credential / management SDK | DB driver / wrapper |
|---|---|---|
| **Python** | `databricks-sdk` `WorkspaceClient().postgres` | `psycopg[binary,pool]` canonical; SQLAlchemy supported |
| **Node/TS** | `@databricks/lakebase` convenience wrapper, Autoscaling only | Wrapper manages `pg` pool |
| **Java/Go** | Databricks SDK for Java/Go | Standard JDBC / `pgx` |

## Lead connection pattern

For production Python apps, start with:

1. `psycopg_pool.ConnectionPool`
2. `connection_class=OAuthConnection`, where `OAuthConnection(psycopg.Connection).connect()` calls `w.postgres.generate_database_credential(endpoint=...)`
3. `max_lifetime=2700`

This is the canonical pattern from the official Databricks Apps + Lakebase Autoscaling tutorial lineage and `databricks-ai-bridge`: no background token thread; physical connections get fresh credentials when opened/recycled.

Prefer `max_lifetime=2700` as a defensive 45-minute recycle before 1-hour token expiry. The official tutorial does not set `max_lifetime`; `databricks-ai-bridge` uses `2700`.

See `connections.md`.

## Critical auth warning

Do **not** use `WorkspaceClient().config.token`, `w.config.oauth_token().access_token`, or any workspace-scoped OAuth token as the Postgres password. It will fail at Postgres login.

Use:

```python
cred = WorkspaceClient().postgres.generate_database_credential(endpoint=endpoint_name)
password = cred.token
```

That token is Lakebase-scoped and is used as the Postgres password with `sslmode=require`.

## Resource model

```text
Project
  └── Branches
        ├── Endpoint/Compute: primary read-write endpoint
        ├── Read replicas: optional read-only endpoints
        ├── Roles
        └── Databases
              └── Schemas/Tables
```

Canonical names:

```text
projects/{project_id}
projects/{project_id}/branches/{branch_id}
projects/{project_id}/branches/{branch_id}/endpoints/{endpoint_id}
```

Defaults on project creation:
- default branch: `production`
- default database: `databricks_postgres`
- primary read-write endpoint/compute
- Postgres role for the creator’s Databricks identity

Key SDK namespace: `WorkspaceClient().postgres`.

Most create/update/delete calls return long-running operations; call `.wait()`.

## Lakebase Autoscaling vs Provisioned

| Aspect | Provisioned | Autoscaling |
|---|---|---|
| SDK module | `w.database` | `w.postgres` |
| Top-level resource | Instance | Project |
| Capacity | fixed CU tiers, ~16 GB/CU | 0.5–112 CU, ~2 GB/CU |
| Branching | no | yes |
| Scale-to-zero | no | yes |
| Operations | mostly synchronous | LROs; use `.wait()` |
| Reverse ETL | synced tables | synced tables |
| Read replicas | readable secondaries | dedicated read-only endpoints |

## Non-obvious facts to preserve

- Postgres versions: **16 and 17**.
- AWS regions: `us-east-1`, `us-east-2`, `eu-central-1`, `eu-west-1`, `eu-west-2`, `ap-south-1`, `ap-southeast-1`, `ap-southeast-2`.
- Azure beta regions: `eastus2`, `westeurope`, `westus`.
- Autoscaling computes: 0.5–32 CU with `max - min <= 16`.
- Fixed-size always-on computes: 40–112 CU.
- Autoscaling CU ≈ 2 GB RAM.
- `sslmode=require` on all driver connections.
- Endpoint host comes from `w.postgres.get_endpoint(...).status.hosts.host`.
- GET responses often return effective properties under `status`; create/update payloads use `spec`.
- All update calls need a `FieldMask`.
- Scale-to-zero wake-up is automatic but apps should retry.
- Connections can be closed by platform timeouts: 24-hour idle timeout and 3-day max connection lifetime.
- macOS DNS can fail on long Lakebase hostnames; if so, resolve to IP and pass both `host` and `hostaddr` to psycopg.
- Triggered/Continuous synced tables require Delta Change Data Feed.
- Reverse ETL is Delta-to-Postgres only; not Postgres-to-Delta.

## Task files

- `connections.md` — app/notebook connection patterns and credential rotation.
- `operations.md` — project, branch, endpoint/compute, scale-to-zero, limits, MCP mapping.
- `reverse-etl.md` — synced tables from Delta Lake to Lakebase.
- `references/migration.md` — migrating an existing Lakebase Provisioned database to Autoscaling via `pg_dump`/`pg_restore` (the five field-discovered gotchas + step-by-step runbook).

## SDK / package versions

```bash
pip install -U "databricks-sdk>=0.81.0" "psycopg[binary,pool]>=3.1" "sqlalchemy>=2"
```

Use SQLAlchemy URL prefix `postgresql+psycopg://...` for psycopg3.

## Current limitations

Not yet supported or not equivalent to Provisioned:
- High availability with readable secondaries; use read replicas instead.
- Databricks Apps UI integration may lag; Apps can connect manually via credentials/resource env vars.
- Feature Store integration.
- Stateful AI-agent memory integrations.
- Postgres-to-Delta sync.
- Custom billing tags / serverless budget policies.
- Direct in-place migration from Lakebase Provisioned. The snapshot path via `pg_dump`/`pg_restore` is documented in [`references/migration.md`](references/migration.md).

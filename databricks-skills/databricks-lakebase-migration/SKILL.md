---
name: databricks-lakebase-migration
description: "Migrate data and apps from Lakebase Provisioned to Lakebase Autoscaling. Use when planning or executing a Provisioned → Autoscaling cutover, dumping/restoring a Lakebase database via pg_dump, registering Service Principal roles on a new instance, re-pointing a Databricks App's database resource binding, or working around the gotchas in raw SQL bootstrap of a destination database."
---

# Lakebase Migration (Provisioned → Autoscaling)

Mechanics and gotchas for migrating an existing Lakebase Provisioned database
to a new Lakebase Autoscaling project via `pg_dump` / `pg_restore`. Direct
in-place migration is **not currently supported** by Databricks; this is the
sanctioned manual path until one-click migration ships.

## When to Use

Use this skill when:

- A Lakebase Provisioned instance backs a Databricks App and you want to move
  to Autoscaling for scale-to-zero, branching, or instant-restore.
- You hit `password authentication failed` after pointing an app at a freshly
  bootstrapped Autoscaling database.
- You need to restore a `pg_dump` snapshot into a fresh Lakebase database and
  have it work for app-SP OAuth connections.
- You're updating a Databricks App's `database` resource to point at a new
  instance and the bundle deploy fails on the update mask.

Also use the related skills:
- [databricks-lakebase-provisioned](../databricks-lakebase-provisioned/SKILL.md) — source-side mechanics
- [databricks-lakebase-autoscale](../databricks-lakebase-autoscale/SKILL.md) — destination-side mechanics

## Overview

| Aspect | Details |
|--------|---------|
| **In-place upgrade** | Not supported as of 2026-05. A one-click migration is on the roadmap; timing TBD. |
| **Recommended path** | Snapshot via `pg_dump` (custom format) → restore into a new Autoscaling project. |
| **Downtime** | Roughly 5-15 minutes for a sub-100 MB database; dominated by app-redeploy time. |
| **Reversibility** | High — keep the source database until you've soaked the destination. Rollback = revert one bundle var + one apps update + restart app. |
| **Synced tables** | UC sync pipelines do **not** auto-follow; copied data is a frozen snapshot. Re-wiring is a separate workstream. |

## Pre-flight checklist

- [ ] Local `pg_dump --version` and `pg_restore --version` ≥ 16 (matches Lakebase PG_VERSION_16)
- [ ] You have **Database superuser** on the new Autoscaling instance (workspace UI: **Compute → Database Instances → … → Permissions**)
- [ ] You know the target app's **service_principal_client_id** (`databricks apps get <name>` → `service_principal_client_id`)
- [ ] No active writes against the source DB during cutover (or accept a small window of orphaned writes)

## The five gotchas you will hit

These are not in the public docs as of 2026-05. They are the difference
between a 30-minute migration and a 3-hour one.

### 1. Don't `CREATE DATABASE` with raw SQL — use the Databricks Database API

Creating a database via `psql -c "CREATE DATABASE foo;"` skips Lakebase's
managed-creation flow and leaves the database **without the
`databricks_auth` and `neon` extensions**. The first symptom you'll see is
the app failing to authenticate with `password authentication failed for
user '<sp-uuid>'` — even though the role exists.

**Fix (preferred):** create the database via the Databricks Database CLI/API,
which provisions extensions automatically:

```bash
databricks database create-database-catalog <catalog_name> \
  <instance_name> <database_name> \
  --create-database-if-not-exists \
  -p <profile>
```

**Fix (recovery, if you already raw-`CREATE DATABASE`'d):**

```sql
CREATE EXTENSION IF NOT EXISTS databricks_auth;
CREATE EXTENSION IF NOT EXISTS neon;
```

You must run these as a superuser. Without `databricks_auth`, OAuth tokens
from app SPs cannot be resolved to Postgres roles.

### 2. App SP roles need `databricks_create_role()`, not `CREATE ROLE`

Vanilla `CREATE ROLE "0ad623cd-..." LOGIN INHERIT` produces a role that
*looks* right but lacks the OAuth-token-resolution wiring inside
`databricks_auth`. The fix is to use the Lakebase-provided function:

```sql
SELECT databricks_create_role(
  '0ad623cd-2827-40d9-917e-1b9f824e4c57',  -- service_principal_client_id
  'SERVICE_PRINCIPAL'                       -- identity_type
);
```

Verify the registration:

```sql
SELECT * FROM databricks_list_roles
 WHERE role_name='0ad623cd-2827-40d9-917e-1b9f824e4c57';
-- expect: identity_type='service_principal'
```

If you've already created a vanilla role with the same name, you must
unwind it first:

```sql
-- 1. Park ownership on a real user
REASSIGN OWNED BY "<sp-uuid>" TO "<your-email>";

-- 2. Drop privileges that block role drop
REVOKE ALL ON DATABASE <db_name>     FROM "<sp-uuid>";
REVOKE ALL ON SCHEMA <schema>        FROM "<sp-uuid>";
REVOKE ALL ON ALL TABLES IN SCHEMA <schema> FROM "<sp-uuid>";

-- 3. Grant role membership so DROP OWNED works
GRANT "<sp-uuid>" TO "<your-email>";

-- 4. Drop
DROP OWNED  BY "<sp-uuid>";
DROP ROLE      "<sp-uuid>";

-- 5. Now register properly
SELECT databricks_create_role('<sp-uuid>', 'SERVICE_PRINCIPAL');
```

### 3. `pg_restore` ownership trap

If you restore as your IdP user (e.g. `david.okeeffe@databricks.com`), every
table ends up owned by you, and the app SP cannot run DDL on its own
tables later (e.g. when the app's startup migrations try `ALTER TABLE …
ADD COLUMN`). The fix is the `--role` flag:

```bash
pg_restore -v \
  --no-owner --no-acl \
  --role="0ad623cd-2827-40d9-917e-1b9f824e4c57" \
  -h <ep-host>.database.us-west-2.cloud.databricks.com \
  -U "<your-email>" \
  -d <database_name> \
  /path/to/dump.bak
```

`--role` causes every restored DDL to run via `SET ROLE` to the SP, so
tables end up SP-owned. This requires:

1. The SP role to exist (registered via `databricks_create_role`, gotcha #2).
2. The connecting user to have `GRANT <sp-uuid> TO <user>` membership.

### 4. Bundle deploy can't change `database.instance_name` on an existing app

The Databricks Apps API doesn't accept `resources[*].database.instance_name`
in the update mask. The bundle deploy emits a deep update path and fails:

```
Invalid update mask. Only description, ..., resources, ... are allowed.
Supplied update mask: resources[0].database.instance_name
```

**Fix:** call `apps update` directly with the full `resources` array, which
*is* an allowed top-level update mask:

```bash
databricks apps update <app_name> -p <profile> --json '{
  "name": "<app_name>",
  "description": "<existing description>",
  "resources": [
    {
      "name": "database",
      "description": "Lakebase database for ...",
      "database": {
        "database_name": "<db_name>",
        "instance_name": "<new_instance_name>",
        "permission": "CAN_CONNECT_AND_CREATE"
      }
    }
  ]
}'
```

After the resource is updated, re-run `databricks bundle deploy` (or
`make ship`) — it will be a no-op on the resource and successfully sync
new code.

### 5. Synced tables (`sync_*`) are a frozen snapshot after migration

UC sync pipelines write to a *specific* Lakebase instance. They do not
auto-follow when you re-point an app's database resource. After the
cutover, your `sync_pricing_vm_costs`, `sync_ref_*`, `sync_salesforce_*`
tables exist on the new instance with the data they had at dump time, but
no further updates flow in.

**Two options:**
- **Path A (snapshot):** accept frozen data, refresh manually when needed.
  Suitable for SE/demo apps where freshness is best-effort.
- **Path B (re-wire):** open a ticket with the team owning the UC sync
  pipeline to re-point it at the new instance. Required for any
  customer-facing tool.

Path B is the same work either way — direct migration would still need
re-wiring — so path A is a no-regret default for v1 migrations.

## End-to-end migration runbook

This is the full sequence proven on a 99 MB lakemeter database. Adapt the
identifiers (instance name, app name, SP UUID, schema) to your project.

### Step 1: Create the destination Autoscaling project

Use the CLI (auto-provisions `databricks_auth` and `neon` extensions):

```bash
databricks database create-database-instance <new_instance_name> \
  --capacity CU_1 \
  --enable-pg-native-login \
  -p <profile>
```

Note the returned `read_write_dns` (looks like `ep-...database.<region>.cloud.databricks.com`).

### Step 2: Create the destination database

The cleanest path is to use the Databricks Database CLI to create the
database AND register it under a UC catalog at the same time:

```bash
databricks database create-database-catalog <catalog_name> \
  <new_instance_name> <database_name> \
  --create-database-if-not-exists \
  -p <profile>
```

If you've already created the database via raw SQL, recover with the
extension installs in gotcha #1.

### Step 3: pg_dump from the source

```bash
mkdir -p /tmp/lakebase_migration && cd /tmp/lakebase_migration

PGPASSWORD="$(databricks auth token -p <profile> | python3 -c \
  'import sys,json; print(json.load(sys.stdin)["access_token"])')" \
pg_dump -Fc -v \
  -n <schema_name> \
  --no-owner --no-acl \
  -h <source_instance_dns> \
  -U "<your-email>" \
  -d <database_name> \
  -p 5432 \
  -f migration.bak
```

**Why these flags:**
- `-Fc` — custom-format archive for parallelisable restore
- `-n <schema>` — only the app schema, not system tables
- `--no-owner --no-acl` — destination's startup privilege block re-grants

### Step 4: Bootstrap the destination schema and SP role

```sql
-- Connected as superuser to <database_name> on the new instance

-- (Only if Step 2 used raw CREATE DATABASE)
CREATE EXTENSION IF NOT EXISTS databricks_auth;
CREATE EXTENSION IF NOT EXISTS neon;

-- Register the app SP for OAuth resolution
SELECT databricks_create_role(
  '<sp_client_id>',
  'SERVICE_PRINCIPAL'
);

-- Grant yourself membership so --role on pg_restore works
GRANT "<sp_client_id>" TO "<your-email>";

-- Create the schema owned by the SP
CREATE SCHEMA IF NOT EXISTS <schema_name>
  AUTHORIZATION "<sp_client_id>";
```

### Step 5: pg_restore with `--role`

```bash
PGPASSWORD="$(databricks auth token -p <profile> | python3 -c \
  'import sys,json; print(json.load(sys.stdin)["access_token"])')" \
pg_restore -v \
  --no-owner --no-acl \
  --role="<sp_client_id>" \
  -h <new_instance_dns> \
  -U "<your-email>" \
  -d <database_name> \
  /tmp/lakebase_migration/migration.bak
```

A handful of cosmetic warnings are normal:
- `unrecognized configuration parameter "transaction_timeout"` — Neon doesn't honor it
- `permission denied for database <name>` — `COMMENT ON DATABASE`; ignore
- `Databricks SyncedTable` — synced-table metadata didn't transfer (gotcha #5)

### Step 6: Verify row counts match

```sql
SELECT 'users'      AS t, COUNT(*) FROM <schema>.users
UNION ALL
SELECT 'estimates'      , COUNT(*) FROM <schema>.estimates
UNION ALL
SELECT 'sync_pricing_*' , COUNT(*) FROM <schema>.sync_pricing_<...>;
```

**STOP if counts diverge.** Don't proceed to cutover.

### Step 7: Patch the bundle config

In `databricks.yml`, change the v2 (or whichever) target:

```diff
   v2:
     variables:
       app_name: "<app_name>"
-      lakebase_instance_name: "<old_instance>"
+      lakebase_instance_name: "<new_instance>"
       lakebase_database_name: "<database_name>"
```

### Step 8: Update the app's database resource (workaround for gotcha #4)

```bash
databricks apps update <app_name> -p <profile> --json '{
  "name": "<app_name>",
  "description": "<existing description>",
  "resources": [
    {
      "name": "database",
      "description": "<existing resource description>",
      "database": {
        "database_name": "<database_name>",
        "instance_name": "<new_instance_name>",
        "permission": "CAN_CONNECT_AND_CREATE"
      }
    }
  ]
}'
```

### Step 9: Stop, deploy, start

```bash
databricks apps stop <app_name> -p <profile>
make ship TARGET=<target> PROFILE=<profile>          # or `databricks bundle deploy -t <target>`
databricks apps start <app_name> -p <profile>
```

### Step 10: Verify the app boots and authenticates

Tail logs and look for the `[TokenManager]` line plus a clean Uvicorn
startup with **no** `password authentication failed` errors:

```bash
databricks apps logs <app_name> -p <profile> | tail -50 | \
  grep -iE "error|password|connect|started|uvicorn"
```

Then hit the app URL in a browser. If the app's startup migrations need
to add new columns / GRANT privileges, those should now succeed because
the SP owns the schema.

### Step 11: Soak before decommissioning the source

Keep the old database for at least 7 days. Rollback is fast:

```bash
# Revert the one-line bundle config change
git checkout databricks.yml

# Re-point app via direct apps update (gotcha #4)
databricks apps update <app_name> -p <profile> --json '{ ... old instance ... }'

# Restart
databricks apps stop  <app_name> -p <profile>
databricks apps start <app_name> -p <profile>
```

When you're confident, drop the source database:

```sql
-- Connected as superuser to databricks_postgres on the OLD instance
DROP DATABASE <database_name>;
```

## Common Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| `password authentication failed for user '<sp-uuid>'` | `databricks_auth` extension missing OR SP role not registered via `databricks_create_role` | Gotchas #1, #2 |
| `must be able to SET ROLE "<sp-uuid>"` on `ALTER OWNER` | Your IdP user lacks role membership | `GRANT "<sp-uuid>" TO "<your-email>"` |
| `permission denied for schema <name>` during restore | Schema owner mismatch or missing GRANT | Re-create the schema with `AUTHORIZATION "<sp-uuid>"` before restore |
| `permission denied to drop objects` | You revoked role membership before dropping owned objects | Re-grant role to yourself, then `DROP OWNED BY` first, then `DROP ROLE` |
| `role "<sp-uuid>" cannot be dropped because some objects depend on it` (after `REASSIGN OWNED`) | DB-level privileges weren't revoked | `REVOKE ALL ON DATABASE <name> FROM "<sp-uuid>"` |
| Bundle deploy fails with `Invalid update mask: resources[0].database.instance_name` | Apps API doesn't allow deep paths | Gotcha #4 — direct `apps update --json` |
| Cosmetic `Could not create schema (may already exist)` warning at app boot | App's `_init_schemas()` calls `CREATE SCHEMA IF NOT EXISTS` but SP doesn't own the database | Harmless; same warning appears on the source instance |
| `Databricks SyncedTable` warning during restore | Synced-table metadata doesn't transfer | Gotcha #5 — re-wire UC sync pipelines after cutover |
| Cost calc / lookups against `sync_*` tables stale after migration | UC sync wasn't re-pointed at new instance | Gotcha #5 |

## What this migration does NOT cover

- **Live replication.** This is a snapshot migration. For zero-downtime,
  consider [logical replication](https://www.postgresql.org/docs/current/logical-replication.html)
  via a dedicated replication slot — Lakebase Autoscaling supports it, but
  that's a separate workstream.
- **UC catalog re-binding.** The existing UC catalog (e.g.
  `<app>_catalog`) was bound to the old instance. Either create a new
  catalog on the new instance (via `databricks database
  create-database-catalog`) or live with the old binding until you
  decommission. Don't delete-and-recreate the existing catalog if
  another target's database lives on the same instance.
- **Onboarding new SPs after migration.** If a new app SP needs to access
  the migrated database later, register it the same way:
  `SELECT databricks_create_role('<new-sp-uuid>', 'SERVICE_PRINCIPAL');`
- **Provisioned-side cleanup.** Decommission only after a soak window. The
  source data is unchanged by the migration, so rollback is non-destructive.

## Mapping reference

When sizing the destination, use the [official mapping table](https://docs.databricks.com/aws/en/oltp/upgrade-to-autoscaling)
between Provisioned capacity units and Autoscaling CU ranges:

| Provisioned (1 CU = 16 GB) | Autoscaling min CU | Autoscaling max CU |
|---|---|---|
| CU_1 (16 GB) | 4 (8 GB) | 8 (16 GB) |
| CU_2 (32 GB) | 8 (16 GB) | 16 (32 GB) |
| CU_4 (64 GB) | 16 (32 GB) | 32 (64 GB) |
| CU_8 (128 GB) | 64 (128 GB) | 64 (128 GB, fixed) |

Note: 1 Provisioned CU = 16 GB RAM, 1 Autoscaling CU = 2 GB RAM. The unit
was redefined; raw CU counts don't compare directly across versions.

## Related Skills

- **[databricks-lakebase-provisioned](../databricks-lakebase-provisioned/SKILL.md)** — source-side patterns for the legacy fixed-capacity model
- **[databricks-lakebase-autoscale](../databricks-lakebase-autoscale/SKILL.md)** — destination-side patterns including projects, branches, computes
- **[databricks-app-python](../databricks-app-python/SKILL.md)** — apps that connect to Lakebase via OAuth tokens
- **[databricks-bundles](../databricks-bundles/SKILL.md)** — Asset Bundle config for the app's `database` resource
- **[databricks-python-sdk](../databricks-python-sdk/SKILL.md)** — `w.database` (Provisioned) vs `w.postgres` (Autoscaling) clients

## Notes

- **Postgres extensions installed by Lakebase managed flow:** `databricks_auth` (OAuth bridge), `neon` (engine), `plpgsql` (PL/pgSQL). Raw `CREATE DATABASE` only installs `plpgsql`.
- **`databricks_list_roles`** is a view installed by `databricks_auth` — use it to see *registered* roles. `pg_roles` may show roles that aren't OAuth-resolvable.
- **The cosmetic restore warnings** (`transaction_timeout`, `permission denied for database`, `SyncedTable`) are not fatal but always appear on this path. Don't treat them as failures.
- **Idempotent retries:** all SQL in Step 4 is safe to re-run (uses `IF NOT EXISTS` / catches duplicates). The `pg_restore` itself is not idempotent — running it twice produces "already exists" errors that are recoverable but noisy.

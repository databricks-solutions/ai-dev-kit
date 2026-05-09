# Lakebase Provisioned → Autoscaling Migration

Use when migrating an existing Lakebase Provisioned database to Autoscaling. Direct in-place migration is not supported as of 2026-05; this is the sanctioned snapshot path via pg_dump / pg_restore.

## Quick facts

| Aspect | Reference |
|---|---|
| Migration path | Snapshot via `pg_dump -Fc` → restore into a new Autoscaling database with `pg_restore` |
| Downtime | Usually app redeploy + verification time; source remains intact for rollback |
| App cutover | Update Databricks App `database` resource to new instance using `databricks apps update --json` |
| Role model | App service principals must be registered with `databricks_create_role`, not raw `CREATE ROLE` |
| Synced tables | `sync_*` data copies as a frozen snapshot; UC sync pipelines do **not** auto-follow |

## Pre-flight checklist

- `pg_dump --version` and `pg_restore --version` are ≥ 16.
- You have **Database superuser** on the destination Autoscaling instance.
- You know the app `service_principal_client_id` from `databricks apps get <app_name>`.
- Writes are stopped during cutover, or you accept orphaned writes after the dump.

## Capacity mapping: Provisioned ↔ Autoscaling

Use the official mapping when sizing the destination:

| Provisioned (1 CU = 16 GB) | Autoscaling min CU | Autoscaling max CU |
|---|---:|---:|
| CU_1 (16 GB) | 4 (8 GB) | 8 (16 GB) |
| CU_2 (32 GB) | 8 (16 GB) | 16 (32 GB) |
| CU_4 (64 GB) | 16 (32 GB) | 32 (64 GB) |
| CU_8 (128 GB) | 64 (128 GB) | 64 (128 GB, fixed) |

Note: 1 Provisioned CU = 16 GB RAM, 1 Autoscaling CU = 2 GB RAM. The unit was redefined; raw CU counts do not compare directly across versions.

## The five gotchas

These are the non-obvious failure modes that usually turn a short migration into a long one.

### 1. Do not `CREATE DATABASE` with raw SQL — use the Databricks Database API

Creating a database via `psql -c "CREATE DATABASE foo;"` skips Lakebase's managed-creation flow and leaves the database **without the `databricks_auth` and `neon` extensions**.

**Symptom:** app authentication fails with:

```text
password authentication failed for user '<sp-uuid>'
```

**Why it fails:** raw `CREATE DATABASE` only installs `plpgsql`; without `databricks_auth`, OAuth tokens from app SPs cannot be resolved to Postgres roles.

**Fix, preferred:**

```bash
databricks database create-database-catalog <catalog_name> \
  <instance_name> <database_name> \
  --create-database-if-not-exists \
  -p <profile>
```

This auto-installs the Lakebase-managed extensions.

**Fix, recovery if you already raw-`CREATE DATABASE`'d:**

```sql
CREATE EXTENSION IF NOT EXISTS databricks_auth;
CREATE EXTENSION IF NOT EXISTS neon;
```

Run as superuser.

Extensions installed by Lakebase managed flow: `databricks_auth`, `neon`, `plpgsql`. Raw `CREATE DATABASE` only installs `plpgsql`.

### 2. App SP roles need `databricks_create_role()`, not `CREATE ROLE`

Vanilla `CREATE ROLE "0ad623cd-..." LOGIN INHERIT` produces a role that looks right but lacks OAuth-token-resolution wiring inside `databricks_auth`.

**Symptom:** app authentication fails with:

```text
password authentication failed for user '<sp-uuid>'
```

even though `pg_roles` shows the role exists.

**Why it fails:** `pg_roles` can contain roles that are not registered in the Lakebase OAuth identity bridge.

**Fix:**

```sql
SELECT databricks_create_role('<sp-uuid>', 'SERVICE_PRINCIPAL');
```

Verify registration:

```sql
SELECT * FROM databricks_list_roles WHERE role_name='<sp-uuid>';
-- expect identity_type='service_principal'
```

If you already created a vanilla role with the same name, unwind it first:

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

If you restore as your IdP user, every table ends up owned by you, and the app SP cannot run later DDL such as startup migrations that do `ALTER TABLE … ADD COLUMN`.

**Symptom:** app boot or migrations fail with schema/table DDL permission errors after restore.

**Why it fails:** without `--role`, restored DDL runs as the connecting user, so object ownership is wrong for the app.

**Fix:** restore with the SP role:

```bash
pg_restore --role=<sp-uuid> --no-owner --no-acl \
  -h <new_instance_dns> \
  -U "<your-email>" \
  -d <database_name> \
  migration.bak
```

Requirements:

```sql
SELECT databricks_create_role('<sp-uuid>', 'SERVICE_PRINCIPAL');
GRANT "<sp-uuid>" TO "<your-email>";
CREATE SCHEMA IF NOT EXISTS <schema> AUTHORIZATION "<sp-uuid>";
```

`--role=<sp-uuid>` causes restored DDL to run through `SET ROLE`, so tables end up SP-owned.

### 4. Bundle deploy cannot change `database.instance_name` on an existing app

The Databricks Apps API does not accept `resources[*].database.instance_name` in the update mask.

**Symptom:**

```text
Invalid update mask. Only description, ..., resources, ... are allowed.
Supplied update mask: resources[0].database.instance_name
```

**Why it fails:** bundle deploy emits a deep update path; the Apps API only allows updating the top-level `resources` array.

**Fix:** use `databricks apps update --json` with the full `resources` array, NOT `bundle deploy`, for the resource rebinding:

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

After this succeeds, re-run `databricks bundle deploy` or your normal ship command to sync code.

### 5. Synced tables (`sync_*`) are a frozen snapshot after migration

UC sync pipelines write to a specific Lakebase instance. They do not auto-follow when you re-point an app's database resource.

**Symptom:** customer-facing tools show stale cost/lookup/reference data in `sync_pricing_vm_costs`, `sync_ref_*`, `sync_salesforce_*`, etc. after migration.

**Why it fails:** `pg_dump` copies table data, not the external UC sync pipeline binding.

**Fix options:**

- Snapshot mode: accept frozen `sync_*` data and refresh manually when needed.
- Re-wire mode: open a ticket with the UC sync pipeline owner to point the pipeline at the new instance.

This is the surprise that breaks customer-facing tools. Re-wiring is required for any production/customer-facing use where `sync_*` freshness matters.

## Tight runbook

1. **Create destination Autoscaling instance** with native PG login enabled:

   ```bash
   databricks database create-database-instance <new_instance_name> \
     --capacity CU_1 \
     --enable-pg-native-login \
     -p <profile>
   ```

2. **Create destination database/catalog** through the managed API so extensions are installed:

   ```bash
   databricks database create-database-catalog <catalog_name> \
     <new_instance_name> <database_name> \
     --create-database-if-not-exists \
     -p <profile>
   ```

3. **Dump source schema** using `pg_dump`; load-bearing flags are `-Fc`, `-n <schema>`, `--no-owner`, `--no-acl`:

   ```bash
   pg_dump -Fc -n <schema> --no-owner --no-acl \
     -h <source_instance_dns> -U "<your-email>" -d <database_name> \
     -f migration.bak
   ```

4. **Bootstrap destination SQL** as superuser:

   ```sql
   -- only needed if the DB was created with raw CREATE DATABASE
   CREATE EXTENSION IF NOT EXISTS databricks_auth;
   CREATE EXTENSION IF NOT EXISTS neon;

   SELECT databricks_create_role('<sp-uuid>', 'SERVICE_PRINCIPAL');
   GRANT "<sp-uuid>" TO "<your-email>";
   CREATE SCHEMA IF NOT EXISTS <schema> AUTHORIZATION "<sp-uuid>";
   SELECT * FROM databricks_list_roles WHERE role_name='<sp-uuid>';
   ```

5. **Restore with SP ownership**; load-bearing flag is `pg_restore --role=<sp-uuid> --no-owner --no-acl`:

   ```bash
   pg_restore --role=<sp-uuid> --no-owner --no-acl \
     -h <new_instance_dns> -U "<your-email>" -d <database_name> \
     migration.bak
   ```

6. **Ignore expected cosmetic restore warnings** only if limited to this list:

   - `transaction_timeout`
   - `permission denied for database`
   - `Databricks SyncedTable`

7. **Verify counts** for key application tables and `sync_*` tables. Stop if counts diverge.

8. **Patch bundle variables/config** so `lakebase_instance_name` or equivalent points at `<new_instance_name>`.

9. **Rebind app resource** using `databricks apps update --json` with the full `resources` array from gotcha #4.

10. **Stop, deploy, start** the app:

    ```bash
    databricks apps stop <app_name> -p <profile>
    databricks bundle deploy -t <target> -p <profile>
    databricks apps start <app_name> -p <profile>
    ```

11. **Verify logs**: look for clean startup and no `password authentication failed` errors.

12. **Soak before decommissioning**. Keep source at least 7 days. Rollback = re-point app resource to old instance, revert config, restart app.

## Common Issues

| Symptom | Cause | Fix |
|---|---|---|
| `password authentication failed for user '<sp-uuid>'` | `databricks_auth` extension missing OR SP role not registered via `databricks_create_role` | Gotchas #1, #2 |
| `must be able to SET ROLE "<sp-uuid>"` on `ALTER OWNER` | Your IdP user lacks role membership | `GRANT "<sp-uuid>" TO "<your-email>"` |
| `permission denied for schema <name>` during restore | Schema owner mismatch or missing GRANT | Re-create the schema with `AUTHORIZATION "<sp-uuid>"` before restore |
| `permission denied to drop objects` | You revoked role membership before dropping owned objects | Re-grant role to yourself, then `DROP OWNED BY` first, then `DROP ROLE` |
| `role "<sp-uuid>" cannot be dropped because some objects depend on it` after `REASSIGN OWNED` | DB-level privileges were not revoked | `REVOKE ALL ON DATABASE <name> FROM "<sp-uuid>"` |
| Bundle deploy fails with `Invalid update mask: resources[0].database.instance_name` | Apps API does not allow deep paths | Gotcha #4 — direct `databricks apps update --json` with full `resources` array |
| Cosmetic `Could not create schema (may already exist)` warning at app boot | App `_init_schemas()` calls `CREATE SCHEMA IF NOT EXISTS` but SP does not own the database | Harmless if app otherwise starts; same warning can appear on source |
| `Databricks SyncedTable` warning during restore | Synced-table metadata does not transfer | Gotcha #5 — re-wire UC sync pipelines after cutover |
| Cost calc / lookups against `sync_*` tables stale after migration | UC sync was not re-pointed at new instance | Gotcha #5 |

## Restore warning policy

These warnings during `pg_restore` are expected, not failures:

- `transaction_timeout` — source/destination Postgres variants differ on this setting.
- `permission denied for database` — usually from `COMMENT ON DATABASE`; ignore.
- `Databricks SyncedTable` — synced-table metadata did not transfer; data is only a snapshot.

Anything outside this list deserves inspection before cutover.

## Notes for Claude Code

- Prefer the managed create path: `databricks database create-database-catalog` auto-installs `databricks_auth`, `neon`, and `plpgsql`.
- Always create the Autoscaling instance with `databricks database create-database-instance ... --enable-pg-native-login`.
- Always register app SPs with `SELECT databricks_create_role('<sp-uuid>', 'SERVICE_PRINCIPAL')`.
- Use `SELECT * FROM databricks_list_roles WHERE role_name=...` to confirm OAuth-resolvable roles; `pg_roles` alone is insufficient.
- Always restore with `pg_restore --role=<sp-uuid> --no-owner --no-acl`.
- Do not rely on `bundle deploy` to change an existing app's database instance; use `databricks apps update --json` with the full `resources` array.
- This is a snapshot migration, not live replication. For zero-downtime migration, logical replication is a separate workstream.
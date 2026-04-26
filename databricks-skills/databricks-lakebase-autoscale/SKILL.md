---
name: databricks-lakebase-autoscale
description: "Patterns and best practices for Lakebase Autoscaling (next-gen managed PostgreSQL). Use when creating or managing Lakebase Autoscaling projects, configuring autoscaling compute or scale-to-zero, working with database branching for dev/test workflows, implementing reverse ETL via synced tables, or connecting applications to Lakebase with OAuth credentials."
---

# Lakebase Autoscaling

Next-generation managed PostgreSQL on Databricks — autoscaling compute (0.5-112 CU, ~2 GB/CU), Git-like branching, scale-to-zero, and point-in-time restore (up to 35 days).

**Interface: Databricks CLI (`databricks postgres ...`).** Every admin command below uses the CLI. The only place SDK is preferred is inside an application that needs to refresh 1-hour OAuth tokens — see [connection-patterns.md](references/connection-patterns.md).

## Hierarchy

```
Project → Branch(es) → Endpoint(s) (compute) + Database(s) (Postgres DBs)
```

A new project includes by default: a `production` branch, a primary R/W endpoint named `primary` (1 CU min/max, autoscaling on, scale-to-zero off), a `databricks_postgres` database, and a Postgres role for the creating user.

Resource names are hierarchical paths: `projects/{id}/branches/{id}/endpoints/{id}`. IDs are 1-63 chars, lowercase/digits/hyphens, no leading or trailing hyphen, immutable after creation.

**Regions (AWS):** us-east-1, us-east-2, eu-central-1, eu-west-1, eu-west-2, ap-south-1, ap-southeast-1, ap-southeast-2. **Azure (Beta):** eastus2, westeurope, westus.

All CLI create/update/delete operations are long-running — the CLI blocks until the LRO completes and returns the final resource.

---

## Projects

Top-level container. One per application or environment grouping.

```bash
# Create — variants: pg_version 16 | 17. PROJECT_ID is positional.
databricks postgres create-project my-app \
    --json '{"spec": {"display_name": "My App", "pg_version": "17"}}'

# Get / list
databricks postgres get-project projects/my-app
databricks postgres list-projects

# Update — positional arg is the field mask
databricks postgres update-project projects/my-app spec.display_name \
    --json '{"spec": {"display_name": "Renamed App"}}'

# Delete (irreversible — wipes all branches/data; drop UC catalogs/synced tables first)
databricks postgres delete-project projects/my-app
```

→ Defaults, limits table, LRO mechanics, SDK equivalents: [projects.md](references/projects.md).

---

## Branches

Isolated DB environments sharing storage with their parent via copy-on-write. The default branch is `production` (cannot be deleted). Branches can be TTL-expiring or permanent.

```bash
# Create — variants: "ttl": "604800s" (TTL in seconds) | "no_expiry": true (permanent)
databricks postgres create-branch projects/my-app development \
    --json '{"spec": {"source_branch": "projects/my-app/branches/production", "ttl": "604800s"}}'

# Get / list
databricks postgres get-branch projects/my-app/branches/development
databricks postgres list-branches projects/my-app

# Protect (protected branches can't be deleted/reset/archived)
databricks postgres update-branch projects/my-app/branches/production \
    spec.is_protected --json '{"spec": {"is_protected": true}}'

# Reset to parent's latest state (destroys local changes; not for root/protected/parent branches)
databricks postgres reset-branch projects/my-app/branches/development

# Delete (children must be deleted first; protection must be removed first)
databricks postgres delete-branch projects/my-app/branches/development
```

→ Copy-on-write internals, TTL rules (max 30 days), reset constraints, SDK equivalents: [branches.md](references/branches.md).

---

## Endpoints (Compute)

A compute runs Postgres for one branch. One R/W endpoint per branch (plus optional read replicas). Autoscale range: 0.5-32 CU with max-min ≤ 16 CU. Large fixed sizes: 36-112 CU.

```bash
# Create an R/W endpoint — replace RW with ENDPOINT_TYPE_READ_ONLY for read replicas
databricks postgres create-endpoint \
    projects/my-app/branches/production my-compute \
    --json '{"spec": {"endpoint_type": "ENDPOINT_TYPE_READ_WRITE",
                      "autoscaling_limit_min_cu": 0.5,
                      "autoscaling_limit_max_cu": 4.0}}'

# Get host, state, CU range
databricks postgres get-endpoint projects/my-app/branches/production/endpoints/primary

# List all endpoints on a branch
databricks postgres list-endpoints projects/my-app/branches/production

# Resize — mask is a comma-separated positional; JSON holds new values
databricks postgres update-endpoint \
    projects/my-app/branches/production/endpoints/primary \
    "spec.autoscaling_limit_min_cu,spec.autoscaling_limit_max_cu" \
    --json '{"spec": {"autoscaling_limit_min_cu": 2.0, "autoscaling_limit_max_cu": 8.0}}'

# Delete
databricks postgres delete-endpoint projects/my-app/branches/production/endpoints/my-compute
```

**Scale-to-zero:** off on `production` by default, configurable elsewhere (min 60s, default 5min). Reactivation takes ~100ms; session context (temp tables, prepared statements, in-memory cache) is **reset** on wake.

→ CU sizing table, autoscaling math, scale-to-zero internals, SDK equivalents: [computes.md](references/computes.md).

---

## Credentials & Connecting

OAuth tokens are 1-hour TTL and used as the Postgres password with `sslmode=require`.

```bash
# Generate a scoped OAuth token (use as PGPASSWORD). ENDPOINT is positional.
databricks postgres generate-database-credential \
    projects/my-app/branches/production/endpoints/primary
```

Full connection-string recipe (use with `psql`, psycopg, or any Postgres client):

```bash
ENDPOINT="projects/my-app/branches/production/endpoints/primary"
HOST=$(databricks postgres get-endpoint "$ENDPOINT" | jq -r '.status.hosts.host')
USER=$(databricks current-user me | jq -r '.userName')
TOKEN=$(databricks postgres generate-database-credential "$ENDPOINT" | jq -r '.token')

# psycopg keyword form:
echo "host=$HOST dbname=databricks_postgres user=$USER password=$TOKEN sslmode=require"

# Postgres URI form (the user is an email, so URL-encode @ as %40):
echo "postgresql://${USER/@/%40}:$TOKEN@$HOST:5432/databricks_postgres?sslmode=require"

# Connect with psql:
PGPASSWORD="$TOKEN" psql "host=$HOST dbname=databricks_postgres user=$USER sslmode=require"
```

Token TTL is ~1 hour. For app deployment, store **only the endpoint path** as config and generate the token at startup (and every 45 min thereafter) — never bake the token into env files.

Application code is the one place to use the SDK — tokens expire hourly and must be refreshed in-process.

→ Runtime connection patterns (minimal SDK snippet, SQLAlchemy pooling, async refresh loop, macOS DNS workaround, static-URL local dev): [connection-patterns.md](references/connection-patterns.md).

---

## Reverse ETL (Synced Tables)

Syncs Unity Catalog Delta tables into Lakebase as Postgres tables via managed Lakeflow pipelines. Modes: `SNAPSHOT` (one-shot) | `TRIGGERED` (scheduled, needs CDF) | `CONTINUOUS` (~15s latency, needs CDF).

```bash
# Create a synced table — swap scheduling_policy to SNAPSHOT | TRIGGERED | CONTINUOUS
databricks postgres create-synced-table lakebase_catalog.schema.synced_table \
    --json '{"spec": {"source_table_full_name": "analytics.gold.user_profiles",
                      "primary_key_columns": ["user_id"],
                      "scheduling_policy": "TRIGGERED",
                      "new_pipeline_spec": {"storage_catalog": "lakebase_catalog",
                                            "storage_schema": "staging"}}}'

# Status (detailed_state shows sync progress)
databricks postgres get-synced-table synced_tables/lakebase_catalog.schema.synced_table

# Delete (also drop the Postgres-side table separately)
databricks postgres delete-synced-table synced_tables/lakebase_catalog.schema.synced_table
```

Enable CDF on the source for TRIGGERED/CONTINUOUS: `ALTER TABLE ... SET TBLPROPERTIES (delta.enableChangeDataFeed = true)`. Each synced table uses up to 16 connections and counts against per-branch limits.

→ Mode comparison, type mapping (UC → Postgres), capacity planning, schema evolution rules, SDK equivalents: [reverse-etl.md](references/reverse-etl.md).

---

## Common Issues

| Issue | Solution |
|-------|----------|
| Token expired during long query | Refresh tokens every 45 min (1h TTL) |
| Connection refused after scale-to-zero | Compute wakes on connect (~100ms); add retry logic |
| DNS resolution fails on macOS | Pass `hostaddr` (resolved via `dig`) alongside `host` to psycopg |
| Branch delete blocked | Delete child branches first; remove protection first |
| Autoscaling range rejected | max-min must be ≤ 16 CU (e.g., 4-20 valid; 0.5-32 invalid) |
| SSL required error | Always `sslmode=require` |
| Update mask required | CLI `update-*` commands take the mask as a positional arg |
| Connection closed after 24h idle | 24h idle timeout, 3-day max lifetime — add retry |

## Databricks Apps Integration

Scaffold an app connected to Lakebase at creation time:

```bash
databricks apps init --name my-app \
    --features lakebase \
    --set "lakebase.postgres.branch=production" \
    --set "lakebase.postgres.database=databricks_postgres"
```

## High Availability

HA adds 1–3 read secondaries across availability zones with automatic failover. Secondaries are accessible via a `-ro` suffix on the host and independently autoscale (but won't drop below the primary's current CU). HA is incompatible with scale-to-zero. See [computes.md](references/computes.md) for sizing constraints.

## Lakehouse Sync (Beta — AWS only)

Reverse direction: continuously streams Postgres changes from Lakebase into Unity Catalog Delta tables via CDC. Azure support TBD. Enable via the project UI.

## Not Yet Supported

Custom billing tags / serverless budget policies.

## Related Skills

- [databricks-app-apx](../databricks-app-apx/SKILL.md), [databricks-app-python](../databricks-app-python/SKILL.md) — apps using Lakebase
- [databricks-bundles](../databricks-bundles/SKILL.md) — bundle deploys with Lakebase resources
- [databricks-jobs](../databricks-jobs/SKILL.md) — scheduling reverse ETL pipelines

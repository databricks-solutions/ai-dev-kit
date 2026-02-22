# Lakebase — Managed Postgres on Databricks

## Overview

**Lakebase** is Databricks' managed PostgreSQL service. There are **two distinct models** with different resource APIs:

| Model | Resources | Scaling | Branching | Best For |
|-------|-----------|---------|-----------|----------|
| **Classic** | `databricks_database_instance` | Fixed tiers (CU_1–CU_8) | Child instances via `parent_instance_ref` | Simple managed Postgres, HA with replicas |
| **Autoscaling** | `databricks_postgres_project` + `databricks_postgres_branch` + `databricks_postgres_endpoint` | True autoscaling (min/max CU, auto-suspend) | Copy-on-write branching (instant, storage-efficient) | Multi-env development, ephemeral branches, cost-optimized serverless Postgres |

Choose **Autoscaling** for new deployments — it provides true autoscaling, instant copy-on-write branches for dev/staging/PITR, and suspend-on-idle behavior.

---

## Provider Requirements

```hcl
terraform {
  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.67.0"  # postgres_project/branch/endpoint available from ~1.65+
    }
  }
}

# Workspace-level provider (all Lakebase resources are workspace-scoped)
provider "databricks" {
  host  = var.databricks_host
  token = var.databricks_token
}
```

> **Important**: All Lakebase resources are workspace-level — no account-level provider alias is needed.

---

---

# Part 1: Lakebase Classic (`databricks_database_instance`)

## Resource: `databricks_database_instance`

### Arguments

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `name` | string | Yes | Unique name for the database instance within the workspace |
| `capacity` | string | No | Compute capacity: `CU_1`, `CU_2`, `CU_4`, `CU_8` (default: `CU_1`) |
| `node_count` | number | No | Number of nodes. Set `> 1` for high availability |
| `enable_readable_secondaries` | bool | No | Allow read queries on secondary nodes (requires `node_count > 1`) |
| `enable_pg_native_login` | bool | No | Enable native Postgres username/password authentication |
| `retention_window_in_days` | number | No | PITR retention: 2–35 days (default: 7) |
| `stopped` | bool | No | Stop the instance without deleting it (for cost savings) |
| `usage_policy_id` | string | No | ID of the usage policy to apply |
| `custom_tags` | list(object) | No | List of `{ key = string, value = string }` tag pairs |
| `parent_instance_ref` | block | No | Reference to parent instance for PITR child instances |

### `parent_instance_ref` Block

```hcl
parent_instance_ref {
  name = databricks_database_instance.production.name
}
```

### Exported Attributes

| Attribute | Description |
|-----------|-------------|
| `id` | The instance name (same as `name`) |
| `creation_time` | RFC3339 timestamp of when the instance was created |
| `creator` | Email/identity of the creator |
| `child_instance_refs` | List of child (PITR) instances referencing this instance |
| `effective_capacity` | Resolved capacity after defaults are applied |
| `effective_enable_pg_native_login` | Resolved value for native login setting |
| `effective_enable_readable_secondaries` | Resolved value for readable secondaries |
| `effective_stopped` | Current stopped state |
| `effective_custom_tags` | Merged tag list including system-applied tags |

---

## Classic Pattern 1: Development / Test Instance

```hcl
resource "databricks_database_instance" "dev" {
  name     = "${var.prefix}-dev-db"
  capacity = "CU_1"

  custom_tags = [
    { key = "environment", value = "dev" },
    { key = "team",        value = var.team_name },
  ]
}

output "dev_db_name" {
  value = databricks_database_instance.dev.name
}
```

---

## Classic Pattern 2: Production High-Availability Instance

Multi-node instance with readable secondaries, increased retention, and native Postgres login.

```hcl
resource "databricks_database_instance" "production" {
  name                        = "${var.prefix}-prod-db"
  capacity                    = "CU_8"
  node_count                  = 2
  enable_readable_secondaries = true
  enable_pg_native_login      = true
  retention_window_in_days    = 35

  custom_tags = [
    { key = "environment", value = "production" },
    { key = "team",        value = var.team_name },
    { key = "cost-center", value = var.cost_center },
  ]

  lifecycle {
    prevent_destroy = true
  }
}

output "prod_db_name" {
  value       = databricks_database_instance.production.name
  description = "Lakebase production database instance name"
}
```

---

## Classic Pattern 3: PITR Child Instance

```hcl
# Parent with PITR retention enabled
resource "databricks_database_instance" "production" {
  name                     = "${var.prefix}-prod-db"
  capacity                 = "CU_4"
  retention_window_in_days = 14
}

# Child — cloned from parent; restore timestamp configured via UI or REST API after apply
resource "databricks_database_instance" "restore" {
  name     = "${var.prefix}-prod-db-restore"
  capacity = "CU_4"

  parent_instance_ref {
    name = databricks_database_instance.production.name
  }

  custom_tags = [
    { key = "type",   value = "pitr-restore" },
    { key = "parent", value = databricks_database_instance.production.name },
  ]
}
```

> **Note**: Terraform creates the child instance shell; the specific restore point is set in the Databricks UI or via the REST API after `terraform apply`.

---

## Classic Pattern 4: Stop/Start Lifecycle (Cost Management)

```hcl
variable "instance_stopped" {
  type    = bool
  default = false
}

resource "databricks_database_instance" "staging" {
  name     = "${var.prefix}-staging-db"
  capacity = "CU_2"
  stopped  = var.instance_stopped
}
```

```bash
terraform apply -var="instance_stopped=true"   # stop
terraform apply -var="instance_stopped=false"  # resume
```

---

## Classic Capacity Sizing Guide

| Tier | `capacity` | `node_count` | Readable Secondaries | Use Case |
|------|-----------|-------------|---------------------|----------|
| **Dev/Test** | `CU_1` | 1 | No | Local development, quick testing |
| **Small Prod** | `CU_2` | 1 | No | Low-traffic apps, batch workloads |
| **Medium Prod** | `CU_4` | 1 | No | Moderate traffic, typical OLTP |
| **HA Medium** | `CU_4` | 2 | Yes | Moderate traffic + read scaling |
| **Large Prod** | `CU_8` | 2 | Yes | High traffic, analytics read replicas |

---

---

# Part 2: Lakebase Autoscaling

Three resources form a strict hierarchy:

```
databricks_postgres_project          (root container — one per app/team/env)
└── databricks_postgres_branch       (independent DB environment, copy-on-write)
    └── databricks_postgres_endpoint (virtualized Postgres connection endpoint)
```

**Key behavioral notes:**
- **No drift detection**: Changes made outside Terraform (via UI/API) are not detected. Always use `terraform plan` before applying in shared environments.
- **`spec` vs `status`**: `spec` is your intended configuration; `status` reflects what the system has actually applied. Removing a field from `spec` removes your intent, but server-side defaults persist.
- **Shared state required**: For multi-user/CI environments, use remote state (S3/Azure Blob/GCS) to prevent conflicts.
- A branch can have **only one** `ENDPOINT_TYPE_READ_WRITE` endpoint. Multiple `ENDPOINT_TYPE_READ_ONLY` endpoints are allowed.

---

## Resource: `databricks_postgres_project`

Top-level container that groups branches, endpoints, databases, and roles.

### Arguments

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `project_id` | string | Yes | 1–63 chars, lowercase letters/numbers/hyphens, must start with a letter. Becomes `projects/{project_id}` |
| `spec` | object | No | Project configuration (see below) |
| `provider_config` | object | No | `{ workspace_id = string }` — for account-level management |

#### `spec` Fields

| Field | Type | Description |
|-------|------|-------------|
| `pg_version` | number | PostgreSQL major version: `16` or `17` |
| `display_name` | string | Human-readable name (1–256 chars) |
| `history_retention_duration` | string | PITR window in seconds, e.g. `"1209600s"` (14 days). Max `"2592000s"` (30 days) |
| `budget_policy_id` | string | Associated budget policy ID |
| `custom_tags` | list | List of `{ key = string, value = string }` |
| `default_endpoint_settings` | object | Default autoscaling/suspension settings for endpoints (see below) |

#### `default_endpoint_settings` Fields

| Field | Type | Description |
|-------|------|-------------|
| `autoscaling_limit_min_cu` | number | Minimum compute units (≥ 0.5) |
| `autoscaling_limit_max_cu` | number | Maximum compute units (≥ 0.5) |
| `suspend_timeout_duration` | string | Inactivity before suspension, `"60s"`–`"604800s"` |
| `no_suspension` | bool | `true` disables auto-suspension entirely |
| `pg_settings` | object | Raw Postgres configuration key-value pairs |

### Exported Attributes

| Attribute | Description |
|-----------|-------------|
| `name` | Full resource path: `projects/{project_id}` |
| `uid` | System-generated unique identifier |
| `create_time` / `update_time` | RFC3339 timestamps |
| `status` | Current system state (mirrors spec fields with effective values) |
| `status.owner` | Project owner email |
| `status.synthetic_storage_size_bytes` | Current storage consumption |

---

## Resource: `databricks_postgres_branch`

Independent database environment within a project. Branches share underlying storage with their source via **copy-on-write** — creating a branch is instant regardless of database size.

### Arguments

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `branch_id` | string | Yes | 1–63 chars, lowercase letters/numbers/hyphens, starts with a letter. Becomes `projects/{project_id}/branches/{branch_id}` |
| `parent` | string | Yes | Project path — use `databricks_postgres_project.this.name` |
| `spec` | object | No | Branch configuration (see below) |
| `provider_config` | object | No | `{ workspace_id = string }` |

#### `spec` Fields

| Field | Type | Description |
|-------|------|-------------|
| `is_protected` | bool | Prevents deletion and reset; also blocks parent project deletion |
| `no_expiry` | bool | Explicitly disables expiration (for permanent branches) |
| `ttl` | string | Relative TTL from creation, e.g. `"604800s"` (7 days) |
| `expire_time` | string | Absolute expiration RFC3339 timestamp |
| `source_branch` | string | Branch path to copy from for PITR: `projects/{p}/branches/{b}` |
| `source_branch_lsn` | string | Log Sequence Number on source for PITR |
| `source_branch_time` | string | RFC3339 timestamp on source branch for PITR |

### Exported Attributes

| Attribute | Description |
|-----------|-------------|
| `name` | Full path: `projects/{project_id}/branches/{branch_id}` |
| `uid` | System-generated unique identifier |
| `create_time` / `update_time` | RFC3339 timestamps |
| `status.current_state` | `INIT`, `READY`, `ARCHIVED`, `IMPORTING`, `RESETTING` |
| `status.default` | `true` if this is the project's default branch |
| `status.is_protected` | Effective protection status |
| `status.logical_size_bytes` | Branch logical storage size |
| `status.source_branch` | Lineage parent branch path |

---

## Resource: `databricks_postgres_endpoint`

A virtualized Postgres service that fronts a branch. Clients connect to the endpoint's hostname to read/write data.

### Arguments

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `endpoint_id` | string | Yes | 1–63 chars, lowercase letters/numbers/hyphens, starts with a letter |
| `parent` | string | Yes | Branch path — use `databricks_postgres_branch.this.name` |
| `spec` | object | No | Endpoint configuration (see below) |
| `provider_config` | object | No | `{ workspace_id = string }` |

#### `spec` Fields

| Field | Type | Description |
|-------|------|-------------|
| `endpoint_type` | string | **Required**: `ENDPOINT_TYPE_READ_WRITE` or `ENDPOINT_TYPE_READ_ONLY`. One branch = one READ_WRITE max. |
| `autoscaling_limit_min_cu` | number | Minimum compute units (≥ 0.5) |
| `autoscaling_limit_max_cu` | number | Maximum compute units (≥ 0.5) |
| `suspend_timeout_duration` | string | Inactivity before auto-suspend: `"60s"`–`"604800s"` |
| `no_suspension` | bool | `true` disables auto-suspension |
| `disabled` | bool | `true` restricts all connections and schedules suspension |
| `settings` | object | `{ pg_settings = { key = value, ... } }` — raw Postgres settings |

### Exported Attributes

| Attribute | Description |
|-----------|-------------|
| `name` | Full path: `projects/{p}/branches/{b}/endpoints/{endpoint_id}` |
| `uid` | System-generated unique identifier |
| `create_time` / `update_time` | RFC3339 timestamps |
| `status.current_state` | `ACTIVE`, `IDLE`, `INIT` |
| `status.hosts.host` | **Connection hostname** — use this to connect clients |
| `status.pending_state` | Transitional state during operations |

---

## Autoscaling Pattern 1: Single Project with Main Branch

Minimal setup — one project, one permanent branch, one read-write endpoint.

```hcl
# Project — top-level container
resource "databricks_postgres_project" "app" {
  project_id = "${var.prefix}-app"

  spec = {
    pg_version   = 17
    display_name = "Application Database"
    history_retention_duration = "604800s"  # 7-day PITR

    default_endpoint_settings = {
      autoscaling_limit_min_cu = 0.5
      autoscaling_limit_max_cu = 4.0
      suspend_timeout_duration = "300s"  # suspend after 5 min idle
    }

    custom_tags = [
      { key = "team",        value = var.team_name },
      { key = "managed-by",  value = "terraform" },
    ]
  }
}

# Main branch — permanent, protected
resource "databricks_postgres_branch" "main" {
  branch_id = "main"
  parent    = databricks_postgres_project.app.name

  spec = {
    is_protected = true
    no_expiry    = true
  }
}

# Primary read-write endpoint
resource "databricks_postgres_endpoint" "primary" {
  endpoint_id = "primary"
  parent      = databricks_postgres_branch.main.name

  spec = {
    endpoint_type            = "ENDPOINT_TYPE_READ_WRITE"
    autoscaling_limit_min_cu = 0.5
    autoscaling_limit_max_cu = 4.0
    suspend_timeout_duration = "300s"
  }
}

output "connection_host" {
  value       = databricks_postgres_endpoint.primary.status.hosts.host
  description = "Postgres connection hostname for the primary endpoint"
}
```

---

## Autoscaling Pattern 2: Multi-Environment Branches

One project, separate branches per environment — dev/staging branches share storage with main via copy-on-write.

```hcl
resource "databricks_postgres_project" "platform" {
  project_id = "${var.prefix}-platform"

  spec = {
    pg_version   = 17
    display_name = "Platform Database"
    history_retention_duration = "1209600s"  # 14-day PITR

    default_endpoint_settings = {
      autoscaling_limit_min_cu = 0.5
      autoscaling_limit_max_cu = 8.0
    }
  }
}

# Production branch — protected, no expiry
resource "databricks_postgres_branch" "production" {
  branch_id = "production"
  parent    = databricks_postgres_project.platform.name

  spec = {
    is_protected = true
    no_expiry    = true
  }
}

# Staging branch — derived from production, no expiry
resource "databricks_postgres_branch" "staging" {
  branch_id = "staging"
  parent    = databricks_postgres_project.platform.name

  spec = {
    no_expiry     = true
    source_branch = databricks_postgres_branch.production.name
  }
}

# Dev branch — derived from staging, 30-day TTL
resource "databricks_postgres_branch" "dev" {
  branch_id = "dev"
  parent    = databricks_postgres_project.platform.name

  spec = {
    ttl           = "2592000s"  # 30 days
    source_branch = databricks_postgres_branch.staging.name
  }
}

# Endpoints — one per branch
resource "databricks_postgres_endpoint" "prod_primary" {
  endpoint_id = "primary"
  parent      = databricks_postgres_branch.production.name

  spec = {
    endpoint_type            = "ENDPOINT_TYPE_READ_WRITE"
    autoscaling_limit_min_cu = 2.0
    autoscaling_limit_max_cu = 8.0
    no_suspension            = true  # production never suspends
  }
}

resource "databricks_postgres_endpoint" "staging_primary" {
  endpoint_id = "primary"
  parent      = databricks_postgres_branch.staging.name

  spec = {
    endpoint_type            = "ENDPOINT_TYPE_READ_WRITE"
    autoscaling_limit_min_cu = 0.5
    autoscaling_limit_max_cu = 4.0
    suspend_timeout_duration = "600s"
  }
}

resource "databricks_postgres_endpoint" "dev_primary" {
  endpoint_id = "primary"
  parent      = databricks_postgres_branch.dev.name

  spec = {
    endpoint_type            = "ENDPOINT_TYPE_READ_WRITE"
    autoscaling_limit_min_cu = 0.5
    autoscaling_limit_max_cu = 2.0
    suspend_timeout_duration = "120s"  # suspend after 2 min idle in dev
  }
}

output "endpoints" {
  value = {
    production = databricks_postgres_endpoint.prod_primary.status.hosts.host
    staging    = databricks_postgres_endpoint.staging_primary.status.hosts.host
    dev        = databricks_postgres_endpoint.dev_primary.status.hosts.host
  }
}
```

---

## Autoscaling Pattern 3: Ephemeral Feature Branch (TTL)

Spin up a short-lived branch for a feature/PR, auto-expires after the TTL.

```hcl
variable "feature_name" {
  type        = string
  description = "Feature branch identifier, e.g. 'feature-user-auth'"
}

resource "databricks_postgres_branch" "feature" {
  branch_id = var.feature_name
  parent    = databricks_postgres_project.platform.name

  spec = {
    ttl           = "604800s"  # 7-day TTL — auto-deleted
    source_branch = databricks_postgres_branch.dev.name
  }
}

resource "databricks_postgres_endpoint" "feature_primary" {
  endpoint_id = "primary"
  parent      = databricks_postgres_branch.feature.name

  spec = {
    endpoint_type            = "ENDPOINT_TYPE_READ_WRITE"
    autoscaling_limit_min_cu = 0.5
    autoscaling_limit_max_cu = 1.0
    suspend_timeout_duration = "60s"  # aggressive suspension for cost
  }
}

output "feature_host" {
  value = databricks_postgres_endpoint.feature_primary.status.hosts.host
}
```

Clean up manually before TTL if needed:

```bash
terraform destroy -target=databricks_postgres_endpoint.feature_primary
terraform destroy -target=databricks_postgres_branch.feature
```

---

## Autoscaling Pattern 4: Point-in-Time Recovery Branch

Restore from a specific timestamp on the production branch.

```hcl
variable "restore_time" {
  type        = string
  description = "RFC3339 timestamp to restore from, e.g. '2025-01-15T10:30:00Z'"
}

resource "databricks_postgres_branch" "pitr_restore" {
  branch_id = "pitr-restore-${formatdate("YYYYMMDD", var.restore_time)}"
  parent    = databricks_postgres_project.platform.name

  spec = {
    source_branch      = databricks_postgres_branch.production.name
    source_branch_time = var.restore_time  # RFC3339 timestamp
    no_expiry          = true  # keep until explicitly deleted
  }
}

resource "databricks_postgres_endpoint" "pitr_endpoint" {
  endpoint_id = "restore-primary"
  parent      = databricks_postgres_branch.pitr_restore.name

  spec = {
    endpoint_type            = "ENDPOINT_TYPE_READ_WRITE"
    autoscaling_limit_min_cu = 0.5
    autoscaling_limit_max_cu = 4.0
    suspend_timeout_duration = "300s"
  }
}

output "pitr_host" {
  value       = databricks_postgres_endpoint.pitr_endpoint.status.hosts.host
  description = "Connect to this endpoint to inspect the restored database"
}
```

---

## Autoscaling Pattern 5: Read Scaling with Read-Only Endpoint

Add a read-only endpoint on the same branch to horizontally scale read traffic (analytics, reporting).

```hcl
# Primary read-write endpoint (already exists from Pattern 1)
resource "databricks_postgres_endpoint" "primary" {
  endpoint_id = "primary"
  parent      = databricks_postgres_branch.main.name

  spec = {
    endpoint_type            = "ENDPOINT_TYPE_READ_WRITE"
    autoscaling_limit_min_cu = 1.0
    autoscaling_limit_max_cu = 8.0
    no_suspension            = true
  }
}

# Read-only endpoint for analytics workloads
resource "databricks_postgres_endpoint" "analytics" {
  endpoint_id = "analytics"
  parent      = databricks_postgres_branch.main.name  # same branch, different endpoint

  spec = {
    endpoint_type            = "ENDPOINT_TYPE_READ_ONLY"
    autoscaling_limit_min_cu = 0.5
    autoscaling_limit_max_cu = 4.0
    suspend_timeout_duration = "600s"
  }
}

output "read_write_host" {
  value = databricks_postgres_endpoint.primary.status.hosts.host
}

output "read_only_host" {
  value       = databricks_postgres_endpoint.analytics.status.hosts.host
  description = "Use this for reporting and analytics queries"
}
```

---

## Autoscaling Pattern 6: Disabled Endpoint (Maintenance Mode)

Temporarily block all connections without destroying the endpoint.

```hcl
variable "maintenance_mode" {
  type    = bool
  default = false
}

resource "databricks_postgres_endpoint" "primary" {
  endpoint_id = "primary"
  parent      = databricks_postgres_branch.main.name

  spec = {
    endpoint_type            = "ENDPOINT_TYPE_READ_WRITE"
    autoscaling_limit_min_cu = 1.0
    autoscaling_limit_max_cu = 8.0
    disabled                 = var.maintenance_mode
  }
}
```

```bash
terraform apply -var="maintenance_mode=true"   # block connections
terraform apply -var="maintenance_mode=false"  # restore access
```

---

## Full Autoscaling Production Example

```hcl
terraform {
  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.67.0"
    }
  }
}

provider "databricks" {
  host  = var.databricks_host
  token = var.databricks_token
}

# ── Project ──────────────────────────────────────────────────────────────────

resource "databricks_postgres_project" "production" {
  project_id = "${var.prefix}-prod"

  spec = {
    pg_version   = 17
    display_name = "Production Application Database"
    history_retention_duration = "1209600s"  # 14-day PITR

    default_endpoint_settings = {
      autoscaling_limit_min_cu = 1.0
      autoscaling_limit_max_cu = 16.0
    }

    custom_tags = [
      { key = "environment", value = "production" },
      { key = "team",        value = var.team_name },
      { key = "managed-by",  value = "terraform" },
    ]
  }
}

# ── Branches ─────────────────────────────────────────────────────────────────

# Production branch — protected, permanent
resource "databricks_postgres_branch" "main" {
  branch_id = "main"
  parent    = databricks_postgres_project.production.name

  spec = {
    is_protected = true
    no_expiry    = true
  }
}

# Staging branch — copy of main, permanent
resource "databricks_postgres_branch" "staging" {
  branch_id = "staging"
  parent    = databricks_postgres_project.production.name

  spec = {
    no_expiry     = true
    source_branch = databricks_postgres_branch.main.name
  }
}

# ── Endpoints ────────────────────────────────────────────────────────────────

# Production primary (read-write, never suspends)
resource "databricks_postgres_endpoint" "prod_primary" {
  endpoint_id = "primary"
  parent      = databricks_postgres_branch.main.name

  spec = {
    endpoint_type            = "ENDPOINT_TYPE_READ_WRITE"
    autoscaling_limit_min_cu = 2.0
    autoscaling_limit_max_cu = 16.0
    no_suspension            = true
  }
}

# Production analytics (read-only, auto-suspends)
resource "databricks_postgres_endpoint" "prod_analytics" {
  endpoint_id = "analytics"
  parent      = databricks_postgres_branch.main.name

  spec = {
    endpoint_type            = "ENDPOINT_TYPE_READ_ONLY"
    autoscaling_limit_min_cu = 0.5
    autoscaling_limit_max_cu = 8.0
    suspend_timeout_duration = "600s"
  }
}

# Staging primary (read-write, aggressive suspension)
resource "databricks_postgres_endpoint" "staging_primary" {
  endpoint_id = "primary"
  parent      = databricks_postgres_branch.staging.name

  spec = {
    endpoint_type            = "ENDPOINT_TYPE_READ_WRITE"
    autoscaling_limit_min_cu = 0.5
    autoscaling_limit_max_cu = 4.0
    suspend_timeout_duration = "300s"
  }
}

# ── Outputs ──────────────────────────────────────────────────────────────────

output "prod_rw_host" {
  value       = databricks_postgres_endpoint.prod_primary.status.hosts.host
  description = "Production read-write connection hostname"
}

output "prod_ro_host" {
  value       = databricks_postgres_endpoint.prod_analytics.status.hosts.host
  description = "Production read-only analytics hostname"
}

output "staging_host" {
  value       = databricks_postgres_endpoint.staging_primary.status.hosts.host
  description = "Staging read-write connection hostname"
}
```

---

## Import (Autoscaling Resources)

Import uses the full resource `name` path:

```hcl
# Terraform 1.5+ block syntax
import {
  id = "projects/my-app"
  to = databricks_postgres_project.app
}

import {
  id = "projects/my-app/branches/main"
  to = databricks_postgres_branch.main
}

import {
  id = "projects/my-app/branches/main/endpoints/primary"
  to = databricks_postgres_endpoint.primary
}
```

```bash
# Legacy CLI import
terraform import databricks_postgres_project.app "projects/my-app"
terraform import databricks_postgres_branch.main "projects/my-app/branches/main"
terraform import databricks_postgres_endpoint.primary "projects/my-app/branches/main/endpoints/primary"
```

---

## Common Issues

### Classic (`databricks_database_instance`)

| Issue | Solution |
|-------|----------|
| **`databricks_database_instance` not found** | Upgrade provider to `~> 1.60.0` or later |
| **`node_count > 1` requires higher capacity** | Multi-node HA requires at least `CU_2` |
| **`enable_readable_secondaries` has no effect** | Requires `node_count >= 2` |
| **PITR child requires retention on parent** | Parent must have `retention_window_in_days > 0` (default: 7) |
| **`stopped = true` doesn't free capacity immediately** | Shutdown takes minutes; check `effective_stopped` |
| **Destroy fails on instance with child instances** | Delete child instances first, then parent |

### Autoscaling (`databricks_postgres_project/branch/endpoint`)

| Issue | Solution |
|-------|----------|
| **Resources not found in provider** | Upgrade to `~> 1.65.0` or later |
| **Drift not detected after manual changes** | These resources have no drift detection — run `terraform refresh` before `plan` |
| **`ENDPOINT_TYPE_READ_WRITE` conflict** | Each branch supports only one read-write endpoint; add `ENDPOINT_TYPE_READ_ONLY` for additional endpoints |
| **Branch stuck in `INIT` state** | Wait for branch to reach `READY` before creating endpoints; use `depends_on` |
| **`source_branch_time` out of retention window** | PITR time must be within `history_retention_duration` of the source branch |
| **Protected branch cannot be deleted** | Set `is_protected = false` and apply before `terraform destroy` |
| **`autoscaling_limit_min_cu` must be ≥ 0.5** | Minimum value is 0.5 CU — do not set to 0 |
| **`suspend_timeout_duration` out of range** | Must be between `"60s"` (1 min) and `"604800s"` (7 days) |
| **Endpoint `IDLE` when expecting `ACTIVE`** | Endpoint auto-suspended — the first connection wakes it; set `no_suspension = true` for always-on |

---

## Unity Catalog Integration

Expose any Lakebase instance or autoscaling endpoint as a UC Connection for querying from notebooks, SQL warehouses, and Genie.

```hcl
# Works for both Classic (database_instance.name) and Autoscaling (endpoint hostname)
resource "databricks_connection" "lakebase" {
  name            = "${var.prefix}-lakebase-connection"
  connection_type = "POSTGRESQL"
  comment         = "Lakebase production connection"

  options = {
    # For Classic: use databricks_database_instance.production.name
    # For Autoscaling: use databricks_postgres_endpoint.prod_primary.status.hosts.host
    host     = databricks_postgres_endpoint.prod_primary.status.hosts.host
    port     = "5432"
    database = "postgres"
  }
}

resource "databricks_grants" "lakebase_connection" {
  connection = databricks_connection.lakebase.name

  grant {
    principal  = "data_engineers"
    privileges = ["ALL_PRIVILEGES"]
  }

  grant {
    principal  = "data_analysts"
    privileges = ["USE_CONNECTION"]
  }
}
```

---

## Variables Reference

```hcl
variable "prefix" {
  type        = string
  description = "Naming prefix for all Lakebase resources"
}

variable "team_name" {
  type        = string
  description = "Team name for tagging"
}

variable "cost_center" {
  type        = string
  description = "Cost center for billing tags"
  default     = ""
}

variable "databricks_host" {
  type        = string
  description = "Databricks workspace URL"
}

variable "databricks_token" {
  type      = string
  sensitive = true
}

variable "dev_instance_stopped" {
  type    = bool
  default = false
}
```

---

## Related Resources

- [databricks_database_instance — Terraform Provider Docs](https://registry.terraform.io/providers/databricks/databricks/latest/docs/resources/database_instance)
- [databricks_postgres_project — Terraform Provider Docs](https://registry.terraform.io/providers/databricks/databricks/latest/docs/resources/postgres_project)
- [databricks_postgres_branch — Terraform Provider Docs](https://registry.terraform.io/providers/databricks/databricks/latest/docs/resources/postgres_branch)
- [databricks_postgres_endpoint — Terraform Provider Docs](https://registry.terraform.io/providers/databricks/databricks/latest/docs/resources/postgres_endpoint)
- [Databricks Connection — Terraform Provider Docs](https://registry.terraform.io/providers/databricks/databricks/latest/docs/resources/connection)
- [Lakebase Overview — Databricks Docs](https://docs.databricks.com/en/database-instances/index.html)

# IAM & Permissions Management

## Overview

Databricks has two permission layers:
1. **Unity Catalog permissions** (`databricks_grants`) — data-level access (catalogs, schemas, tables, volumes)
2. **Workspace permissions** (`databricks_permissions`) — compute-level access (clusters, jobs, notebooks, SQL warehouses)

And two identity levels:
- **Account-level** — users, groups, and service principals managed at the Databricks account (via account-level provider)
- **Workspace-level** — the same identities added to specific workspaces

---

## Users

### Create Account-Level Users

```hcl
# Create multiple users (account-level provider required)
resource "databricks_user" "users" {
  provider   = databricks.mws
  for_each   = toset(var.user_emails)
  user_name  = each.key
  force      = true  # Don't fail if user already exists
}

# Single user
resource "databricks_user" "admin_user" {
  provider     = databricks.mws
  user_name    = "admin@company.com"
  display_name = "Admin User"
  force        = true
}

# Assign account admin role
resource "databricks_user_role" "admin" {
  provider = databricks.mws
  user_id  = databricks_user.admin_user.id
  role     = "account_admin"
}
```

### Add User to Workspace

```hcl
# Add user to workspace (workspace-level provider)
resource "databricks_user" "workspace_user" {
  provider     = databricks.workspace
  user_name    = "analyst@company.com"
  display_name = "Data Analyst"
}
```

---

## Groups

### Create Groups

```hcl
# Account-level group (for UC grants)
resource "databricks_group" "data_engineers" {
  provider     = databricks.mws
  display_name = "data_engineers"
}

resource "databricks_group" "data_analysts" {
  provider     = databricks.mws
  display_name = "data_analysts"
}

resource "databricks_group" "ml_team" {
  provider     = databricks.mws
  display_name = "ml_team"
}

resource "databricks_group" "pii_access" {
  provider     = databricks.mws
  display_name = "pii_access_group"
}
```

### Add Members to Groups

```hcl
# Add individual users to group
resource "databricks_group_member" "engineers" {
  provider  = databricks.mws
  for_each  = toset(var.engineer_emails)
  group_id  = databricks_group.data_engineers.id
  member_id = databricks_user.users[each.value].id
}

# Nested groups (group within a group)
resource "databricks_group" "all_data_teams" {
  provider     = databricks.mws
  display_name = "all_data_teams"
}

resource "databricks_group_member" "engineers_in_all" {
  provider  = databricks.mws
  group_id  = databricks_group.all_data_teams.id
  member_id = databricks_group.data_engineers.id
}

resource "databricks_group_member" "analysts_in_all" {
  provider  = databricks.mws
  group_id  = databricks_group.all_data_teams.id
  member_id = databricks_group.data_analysts.id
}
```

### Sync Groups from Cloud Identity Providers

For large organizations, use group sync rather than Terraform for individual membership. Terraform manages group creation and workspace assignment; Azure AD/Okta/etc. syncs members.

```hcl
# Create the group in Databricks (members synced from IdP via SCIM)
resource "databricks_group" "synced_group" {
  provider         = databricks.mws
  display_name     = "data-team"
  allow_instance_pool_create  = false
  allow_cluster_create        = false
}

# Look up externally-synced group (read-only)
data "databricks_group" "existing" {
  provider     = databricks.workspace
  display_name = "data-team"
}
```

---

## Service Principals

### Create Service Principal

```hcl
# Account-level service principal (for CI/CD, automation)
resource "databricks_service_principal" "ci_cd" {
  provider         = databricks.mws
  display_name     = "CI/CD Pipeline SP"
  allow_cluster_create = false  # Restrict to only what's needed
}

# Workspace-level service principal
resource "databricks_service_principal" "workspace_sp" {
  provider         = databricks.workspace
  application_id   = var.sp_application_id  # Azure AD app ID or AWS IAM
  display_name     = "Workspace Automation SP"
}

# Grant account admin to SP (for UC admin operations)
resource "databricks_service_principal_role" "sp_admin" {
  provider             = databricks.mws
  service_principal_id = databricks_service_principal.ci_cd.id
  role                 = "account_admin"
}
```

### Service Principal OAuth Secrets

```hcl
# Create OAuth secret for SP (account-level)
resource "databricks_service_principal_secret" "ci_cd" {
  provider             = databricks.mws
  service_principal_id = databricks_service_principal.ci_cd.id
}

output "sp_client_id" {
  value = databricks_service_principal.ci_cd.application_id
}

output "sp_client_secret" {
  value     = databricks_service_principal_secret.ci_cd.secret
  sensitive = true
}
```

---

## Workspace Assignment

```hcl
# Add group to workspace with specific entitlements
resource "databricks_mws_workspace_assignment" "engineers" {
  provider     = databricks.mws
  workspace_id = var.workspace_id
  principal_id = databricks_group.data_engineers.id

  permissions = ["USER"]  # "USER" or "ADMIN"
}

resource "databricks_mws_workspace_assignment" "sp_admin" {
  provider     = databricks.mws
  workspace_id = var.workspace_id
  principal_id = databricks_service_principal.ci_cd.id

  permissions = ["ADMIN"]
}
```

---

## Entitlements

```hcl
# Allow a group to create clusters
resource "databricks_entitlements" "cluster_create" {
  provider              = databricks.workspace
  group_id              = databricks_group.data_engineers.id
  allow_cluster_create  = true
  allow_instance_pool_create = true
}

# Allow SP to create clusters and instance pools
resource "databricks_entitlements" "sp_entitlements" {
  provider              = databricks.workspace
  service_principal_id  = databricks_service_principal.ci_cd.id
  allow_cluster_create  = true
  databricks_sql_access = true
  workspace_access      = true
}

# Analyst — SQL-only access
resource "databricks_entitlements" "analyst_entitlements" {
  provider              = databricks.workspace
  group_id              = databricks_group.data_analysts.id
  allow_cluster_create  = false
  databricks_sql_access = true  # Access to DBSQL
  workspace_access      = true
}
```

---

## Workspace-Level Permissions Matrix

### Permission Levels by Resource

| Resource | Levels | Notes |
|----------|--------|-------|
| **Cluster** | `CAN_ATTACH_TO`, `CAN_RESTART`, `CAN_MANAGE` | Workspace admins can manage all clusters |
| **Job** | `CAN_VIEW`, `CAN_MANAGE_RUN`, `IS_OWNER`, `CAN_MANAGE` | Job owner auto-gets `IS_OWNER` |
| **Notebook** | `CAN_READ`, `CAN_RUN`, `CAN_EDIT`, `CAN_MANAGE` | |
| **Directory** | `CAN_READ`, `CAN_RUN`, `CAN_EDIT`, `CAN_MANAGE` | Applies to all objects within |
| **SQL Warehouse** | `CAN_USE`, `CAN_MANAGE` | |
| **Cluster Policy** | `CAN_USE` | Allows creating clusters under the policy |
| **Secret Scope** | `READ`, `WRITE`, `MANAGE` | |
| **Instance Pool** | `CAN_ATTACH_TO`, `CAN_MANAGE` | |
| **Dashboard** | `CAN_VIEW`, `CAN_RUN`, `CAN_EDIT`, `CAN_MANAGE` | |
| **Alert** | `CAN_VIEW`, `CAN_RUN`, `CAN_EDIT`, `CAN_MANAGE` | |

### Complete Permissions Example

```hcl
# Data Engineering workspace permissions setup
locals {
  workspace_permissions = {
    cluster = {
      resource_type = "cluster_id"
      resource_id   = databricks_cluster.shared_autoscaling.id
      groups = {
        "data_engineers" = "CAN_RESTART"
        "data_analysts"  = "CAN_ATTACH_TO"
        "ml_team"        = "CAN_RESTART"
      }
    }
  }
}

resource "databricks_permissions" "cluster_permissions" {
  provider   = databricks.workspace
  cluster_id = databricks_cluster.shared_autoscaling.id

  dynamic "access_control" {
    for_each = {
      "data_engineers" = "CAN_RESTART"
      "data_analysts"  = "CAN_ATTACH_TO"
      "ml_team"        = "CAN_RESTART"
    }
    content {
      group_name       = access_control.key
      permission_level = access_control.value
    }
  }
}
```

---

## Unity Catalog Grants (Data Permissions)

> See [5-unity-catalog.md](5-unity-catalog.md) for full UC grants reference.

### Quick Reference: Grant All Standard Roles

```hcl
# Metastore: Admin group gets full control
resource "databricks_grants" "metastore_grants" {
  provider  = databricks.workspace
  metastore = databricks_metastore.this.id

  grant {
    principal  = "data_engineers"
    privileges = ["CREATE_CATALOG", "CREATE_EXTERNAL_LOCATION", "CREATE_STORAGE_CREDENTIAL"]
  }
}

# Production catalog: layered access
resource "databricks_grants" "prod_catalog" {
  provider = databricks.workspace
  catalog  = "prod"

  grant {
    principal  = "data_engineers"
    privileges = ["USE_CATALOG", "CREATE_SCHEMA"]
  }
  grant {
    principal  = "data_analysts"
    privileges = ["USE_CATALOG"]
  }
  grant {
    principal  = "ml_team"
    privileges = ["USE_CATALOG"]
  }
}

# Silver schema: transform layer
resource "databricks_grants" "silver" {
  provider = databricks.workspace
  schema   = "prod.silver"

  grant {
    principal  = "data_engineers"
    privileges = ["USE_SCHEMA", "CREATE_TABLE", "SELECT", "MODIFY"]
  }
  grant {
    principal  = "ml_team"
    privileges = ["USE_SCHEMA", "SELECT"]
  }
}

# Gold schema: business layer (analysts read-only)
resource "databricks_grants" "gold" {
  provider = databricks.workspace
  schema   = "prod.gold"

  grant {
    principal  = "data_engineers"
    privileges = ["USE_SCHEMA", "CREATE_TABLE", "SELECT", "MODIFY"]
  }
  grant {
    principal  = "data_analysts"
    privileges = ["USE_SCHEMA", "SELECT"]
  }
  grant {
    principal  = "ml_team"
    privileges = ["USE_SCHEMA", "SELECT"]
  }
}
```

---

## SCIM Integration (Enterprise IdP Sync)

For large organizations, use SCIM to sync users/groups from Azure AD, Okta, or other IdPs instead of managing individuals in Terraform.

```hcl
# Terraform manages SCIM configuration; IdP manages user/group membership

# Azure AD — enable SCIM provisioning endpoint
# (This is configured in Azure AD Enterprise App, not in Terraform)
# Terraform only creates the groups that IdP will sync members into:

resource "databricks_group" "scim_groups" {
  provider     = databricks.mws
  for_each     = toset([
    "data_engineers",
    "data_analysts",
    "ml_team",
    "workspace_admins"
  ])
  display_name = each.key
}
```

---

## Row-Level & Column-Level Security

Databricks UC supports row filters and column masks — set via SQL, not Terraform directly, but the underlying permissions are managed through grants.

```hcl
# Grant SELECT but row filters/column masks are applied via SQL functions
resource "databricks_grants" "customer_table" {
  provider = databricks.workspace
  table    = "prod.gold.customer_transactions"

  grant {
    principal  = "data_analysts"
    privileges = ["SELECT"]
    # Row filter applied via: ALTER TABLE ... SET ROW FILTER ...
    # Column mask via: ALTER TABLE ... ALTER COLUMN ... SET MASK ...
  }
}

# The SQL row filter function must also be granted EXECUTE
resource "databricks_grants" "row_filter_fn" {
  provider = databricks.workspace
  function = "prod.security.customer_row_filter"

  grant {
    principal  = "data_analysts"
    privileges = ["EXECUTE"]
  }
}
```

---

## Token Policies

```hcl
# Restrict token lifetime for all users
resource "databricks_workspace_conf" "token_policy" {
  provider = databricks.workspace
  custom_config = {
    "maxTokenLifetimeDays" = "90"
    "enableTokensConfig"   = "true"
  }
}

# Manage which service principals can generate tokens
resource "databricks_obo_token" "sp_token" {
  provider             = databricks.workspace
  application_id       = databricks_service_principal.ci_cd.application_id
  comment              = "Token for CI/CD pipeline"
  lifetime_seconds     = 86400  # 1 day
}

output "sp_obo_token" {
  value     = databricks_obo_token.sp_token.token_value
  sensitive = true
}
```

---

## Best Practices

### 1. Use Groups, Not Individual Users

```hcl
# GOOD — grant to groups
resource "databricks_grants" "gold_schema" {
  schema = "prod.gold"
  grant {
    principal  = "data_analysts"  # group
    privileges = ["USE_SCHEMA", "SELECT"]
  }
}

# AVOID — granting to individual users creates maintenance burden
resource "databricks_grants" "gold_schema_bad" {
  schema = "prod.gold"
  grant {
    principal  = "alice@company.com"  # user — hard to maintain
    privileges = ["USE_SCHEMA", "SELECT"]
  }
}
```

### 2. Principle of Least Privilege

```hcl
# Only grant what's needed
resource "databricks_entitlements" "analyst" {
  group_id              = databricks_group.data_analysts.id
  allow_cluster_create  = false  # Analysts use shared warehouses
  databricks_sql_access = true
  workspace_access      = true
}
```

### 3. Separate Account vs Workspace Groups

```hcl
# Account-level (for UC grants) — use databricks.mws
resource "databricks_group" "uc_group" {
  provider     = databricks.mws
  display_name = "data_engineers"
}

# Workspace-level entitlements — use databricks.workspace
resource "databricks_entitlements" "ws_entitlements" {
  provider              = databricks.workspace
  group_id              = databricks_group.uc_group.id
  allow_cluster_create  = true
}
```

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **`User already exists` when creating** | Set `force = true` on `databricks_user` to allow creation even if user exists |
| **Group not visible in workspace** | Account-level groups must be assigned to workspace via `databricks_mws_workspace_assignment` |
| **`grants` removes metastore admin privileges** | `databricks_grants` is authoritative — always include metastore admin group in every grants resource on that securable |
| **Service principal can't authenticate** | Ensure SP has been assigned to workspace and has `workspace_access = true` entitlement |
| **SCIM-synced users cannot be modified via Terraform** | SCIM-managed users are read-only in Terraform; manage via IdP |
| **`CAN_MANAGE` on job fails** | Job owner (`IS_OWNER`) is set at creation; transfer ownership via UI or API if needed |
| **Entitlements conflict** | `databricks_entitlements` is an update to existing entitlements; importing existing resources is recommended before managing |
| **OBO token requires workspace admin** | Only workspace admins can create OBO tokens for service principals |

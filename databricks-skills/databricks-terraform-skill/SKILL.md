---
name: databricks-terraform-skill
description: "Terraform automation for Databricks: workspace deployment on AWS/Azure/GCP (with or without PrivateLink), Unity Catalog setup, Databricks resource management (clusters, jobs, warehouses, grants), and Lakebase managed Postgres (Classic database_instance and Autoscaling postgres_project/branch/endpoint). Use when writing or reviewing Terraform for Databricks infrastructure."
---

# Databricks Terraform Skill

End-to-end Terraform automation for Databricks infrastructure — from workspace provisioning to Unity Catalog and resource management across all three major clouds.

## When to Use This Skill

Use this skill when:
- **Deploying Databricks workspaces** on AWS, Azure, or GCP (basic or PrivateLink)
- **Setting up Unity Catalog** (metastore, storage credentials, external locations, catalogs, schemas, grants)
- **Managing Databricks resources** via Terraform (clusters, jobs, SQL warehouses, notebooks, secrets, policies, Databricks Apps, Mosaic AI Vector Search)
- **Configuring IAM/access control** (users, groups, service principals, permissions)
- **Provisioning Lakebase Classic** (`databricks_database_instance`) — fixed-tier HA managed Postgres
- **Provisioning Lakebase Autoscaling** (`databricks_postgres_project` / `databricks_postgres_branch` / `databricks_postgres_endpoint`) — true autoscaling, copy-on-write branching, suspend-on-idle
- **Reviewing or troubleshooting** existing Databricks Terraform configurations
- **Migrating** manual Databricks setups to Infrastructure-as-Code

## Reference Files

| Topic | File | Description |
|-------|------|-------------|
| Provider & Auth | [1-provider-authentication.md](1-provider-authentication.md) | Provider setup, authentication for all clouds, multi-provider patterns |
| AWS Deployment | [2-aws-workspace-deployment.md](2-aws-workspace-deployment.md) | AWS basic workspace and PrivateLink deployment |
| Azure Deployment | [3-azure-workspace-deployment.md](3-azure-workspace-deployment.md) | Azure basic workspace and Private Link standard deployment |
| GCP Deployment | [4-gcp-workspace-deployment.md](4-gcp-workspace-deployment.md) | GCP managed VPC and BYOVPC workspace deployment |
| Unity Catalog | [5-unity-catalog.md](5-unity-catalog.md) | Metastore, storage credentials, external locations, catalogs, schemas, grants |
| Databricks Resources | [6-databricks-resources.md](6-databricks-resources.md) | Clusters, jobs, SQL warehouses, notebooks, secrets, cluster policies, Databricks Apps, Mosaic AI Vector Search |
| IAM & Permissions | [7-iam-permissions.md](7-iam-permissions.md) | Users, groups, service principals, workspace permissions, grants |
| Lakebase (Postgres) | [8-lakebase.md](8-lakebase.md) | Classic (`database_instance`) and Autoscaling (`postgres_project/branch/endpoint`): HA, PITR, copy-on-write branching, autoscaling, suspend-on-idle |

## Quick Start

### 1. Configure the Provider

```hcl
terraform {
  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.38.0"
    }
  }
}

# Workspace-level provider (uses PAT or OAuth)
provider "databricks" {
  host  = var.databricks_host
  token = var.databricks_token
}
```

### 2. Deploy a Workspace (AWS Quick Start)

Follow the inline resource pattern in [2-aws-workspace-deployment.md](2-aws-workspace-deployment.md) — the examples use direct resources rather than published registry modules.

```hcl
# See 2-aws-workspace-deployment.md for the full VPC → IAM → MWS workspace pattern
resource "databricks_mws_workspaces" "this" {
  provider       = databricks.mws
  account_id     = var.databricks_account_id
  workspace_name = var.workspace_name
  aws_region     = var.region
  # ... see 2-aws-workspace-deployment.md for complete configuration
}
```

### 3. Set Up Unity Catalog (Quick Start)

```hcl
resource "databricks_metastore" "this" {
  name          = "my-metastore"
  storage_root  = "s3://my-uc-bucket/metastore"
  region        = "us-east-1"
  force_destroy = true
}

resource "databricks_metastore_assignment" "this" {
  metastore_id = databricks_metastore.this.id
  workspace_id = var.workspace_id
}
```

### 4. Provision Lakebase (Quick Start)

**Classic** (fixed capacity, HA replicas):

```hcl
# See 8-lakebase.md for HA, PITR, stop/start, and UC integration patterns
resource "databricks_database_instance" "production" {
  name                        = "prod-lakebase"
  capacity                    = "CU_4"
  node_count                  = 2
  enable_readable_secondaries = true
  enable_pg_native_login      = true
  retention_window_in_days    = 14
}
```

**Autoscaling** (copy-on-write branches, suspend-on-idle — recommended for new deployments):

```hcl
# See 8-lakebase.md for multi-env branching, PITR branch, read-only endpoint patterns
resource "databricks_postgres_project" "app" {
  project_id = "my-app"
  spec = {
    pg_version   = 17
    display_name = "Application Database"
    history_retention_duration = "604800s"
  }
}

resource "databricks_postgres_branch" "main" {
  branch_id = "main"
  parent    = databricks_postgres_project.app.name
  spec      = { is_protected = true, no_expiry = true }
}

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
```

### 5. Run Terraform

```bash
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

## Key Design Patterns

### Multi-Provider Pattern (Account + Workspace)

Most Unity Catalog operations require **two providers**: one for account-level operations and one per workspace.

```hcl
# Account-level (for UC, users, groups)
provider "databricks" {
  alias      = "mws"
  host       = "https://accounts.cloud.databricks.com"
  account_id = var.databricks_account_id
  client_id  = var.client_id
  client_secret = var.client_secret
}

# Workspace-level (for clusters, jobs, etc.)
provider "databricks" {
  alias = "workspace"
  host  = var.workspace_url
  client_id  = var.client_id
  client_secret = var.client_secret
}
```

### Modular Structure (Recommended)

```
project/
├── main.tf              # Root module — calls sub-modules
├── variables.tf         # Input variables
├── outputs.tf           # Output values
├── providers.tf         # Provider declarations
├── terraform.tfvars     # Variable values (gitignored)
├── modules/
│   ├── networking/      # VPC, subnets, security groups
│   ├── workspace/       # Databricks workspace
│   └── unity-catalog/   # UC metastore, catalogs, grants
└── backend.tf           # Remote state (S3/Azure Blob/GCS)
```

### Remote State (Required for Production)

```hcl
# backend.tf — AWS S3 example
terraform {
  backend "s3" {
    bucket         = "my-terraform-state"
    key            = "databricks/workspace/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-state-lock"
  }
}
```

## Common Issues

| Issue | Solution |
|-------|----------|
| **`account_id` required for UC** | Use account-level provider with `host = "https://accounts.cloud.databricks.com"` |
| **Provider version mismatch** | Pin to `~> 1.38.0` and run `terraform init -upgrade` |
| **`grants` overwrites existing permissions** | `databricks_grants` is authoritative — include ALL grants for a securable |
| **Workspace not ready for UC** | Use `depends_on` to ensure workspace is created before metastore assignment |
| **Cross-account AWS role trust issues** | Verify that the Databricks account ID is in the trust policy of the IAM role |
| **Azure SP permissions** | SP needs `Contributor` on resource group + `User Access Administrator` for ADLS |
| **State drift on manual changes** | Run `terraform refresh` to sync state, then `terraform plan` before applying |
| **Sensitive values in state** | Use `sensitive = true` for variables; consider Vault or cloud KMS for secrets |

## Cloud Decision Matrix

| Requirement | AWS | Azure | GCP |
|-------------|-----|-------|-----|
| **PrivateLink/PSC** | `aws-databricks-modular-privatelink` | `adb-with-private-link-standard` | `gcp-with-psc-exfiltration-protection` |
| **Custom VPC/VNet** | `aws_vpc` with SG + subnet module | `azurerm_virtual_network` | `gcp-byovpc` |
| **Customer-managed keys** | AWS KMS + `databricks_mws_customer_managed_keys` | Azure Key Vault | Cloud KMS |
| **Identity** | IAM role/instance profile | Azure AD / Entra ID | GCP Service Account |
| **UC storage** | S3 + IAM role | ADLS Gen2 + managed identity | GCS + service account |

## Related Skills

- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** — query UC system tables and manage volumes at the SQL level
- **[databricks-asset-bundles](../databricks-asset-bundles/SKILL.md)** — deploy Databricks resources via DABs (YAML-based CI/CD)
- **[databricks-jobs](../databricks-jobs/SKILL.md)** — job patterns and examples for resources managed via Terraform
- **[databricks-config](../databricks-config/SKILL.md)** — CLI authentication and profile configuration

## Resources

- [Databricks Terraform Provider Docs](https://registry.terraform.io/providers/databricks/databricks/latest/docs)
- [terraform-databricks-examples GitHub](https://github.com/databricks/terraform-databricks-examples)
- [Databricks Terraform Provider GitHub](https://github.com/databricks/terraform-provider-databricks)
- [AWS Deployment Examples](https://github.com/databricks/terraform-databricks-examples/tree/main/examples)
- [Azure Deployment Examples](https://github.com/databricks/terraform-databricks-examples/tree/main/examples)
- [GCP Deployment Examples](https://github.com/databricks/terraform-databricks-examples/tree/main/examples)

# Provider Configuration & Authentication

## Overview

The Databricks Terraform provider supports multiple authentication methods. For production, always use a **service principal** with client credentials. Never hardcode tokens in `.tf` files.

## Provider Version Declaration

```hcl
# versions.tf
terraform {
  required_version = ">= 1.3.0"
  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.38.0"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}
```

---

## Authentication Methods

### Method 1: Personal Access Token (PAT) — Dev/Test Only

```hcl
provider "databricks" {
  host  = "https://adb-<workspace-id>.azuredatabricks.net"
  token = var.databricks_token   # Never hardcode!
}
```

Set via environment variable (preferred):
```bash
export DATABRICKS_HOST="https://adb-<workspace-id>.azuredatabricks.net"
export DATABRICKS_TOKEN="dapiXXXXXXXXXXXXXXXXXX"
```

### Method 2: Service Principal — OAuth M2M (Recommended for Production)

Works for **all clouds**. Service principal must be added as Databricks account admin for account-level operations.

```hcl
provider "databricks" {
  host          = var.databricks_host
  client_id     = var.client_id      # SP application ID
  client_secret = var.client_secret  # SP client secret
}

# Account-level operations (Unity Catalog, workspace creation)
provider "databricks" {
  alias         = "mws"
  host          = "https://accounts.cloud.databricks.com"  # AWS/GCP
  # Azure: "https://accounts.azuredatabricks.net"
  account_id    = var.databricks_account_id
  client_id     = var.client_id
  client_secret = var.client_secret
}
```

Set via environment variables:
```bash
export DATABRICKS_CLIENT_ID="<sp-application-id>"
export DATABRICKS_CLIENT_SECRET="<sp-client-secret>"
export DATABRICKS_ACCOUNT_ID="<databricks-account-id>"
```

### Method 3: Azure CLI Authentication (Azure-Specific)

```hcl
provider "databricks" {
  host = "https://adb-<workspace-id>.azuredatabricks.net"
  # Uses `az login` credentials automatically
}

provider "azurerm" {
  features {}
  # Uses `az login` credentials automatically
}
```

### Method 4: Azure Service Principal with Client Secret (Azure Production)

```hcl
provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
  client_id       = var.azure_client_id
  client_secret   = var.azure_client_secret
  tenant_id       = var.azure_tenant_id
}

provider "databricks" {
  azure_workspace_resource_id = azurerm_databricks_workspace.this.id
  azure_client_id             = var.azure_client_id
  azure_client_secret         = var.azure_client_secret
  azure_tenant_id             = var.azure_tenant_id
}
```

### Method 5: GCP Service Account (GCP)

```hcl
provider "google" {
  project = var.google_project
  region  = var.google_region
  # Uses GOOGLE_APPLICATION_CREDENTIALS env var or ADC
}

provider "databricks" {
  host                     = module.databricks_workspace.databricks_host
  google_service_account   = var.databricks_google_service_account
  # Or use: token from module output
  token                    = module.databricks_workspace.databricks_token
}
```

---

## Multi-Provider Patterns

### Pattern 1: Account + Workspace (Unity Catalog)

Required when managing both account-level (UC) and workspace-level resources.

```hcl
# providers.tf

# AWS account-level provider
provider "databricks" {
  alias         = "mws"
  host          = "https://accounts.cloud.databricks.com"
  account_id    = var.databricks_account_id
  client_id     = var.client_id
  client_secret = var.client_secret
}

# Workspace-level provider (created after workspace exists)
provider "databricks" {
  alias         = "workspace"
  host          = databricks_mws_workspaces.this.workspace_url
  client_id     = var.client_id
  client_secret = var.client_secret
}
```

Usage in resources:
```hcl
# Account-level resource
resource "databricks_user" "admin" {
  provider  = databricks.mws
  user_name = "admin@company.com"
}

# Workspace-level resource
resource "databricks_cluster" "shared" {
  provider       = databricks.workspace
  cluster_name   = "shared-cluster"
  spark_version  = data.databricks_spark_version.latest.id
  node_type_id   = data.databricks_node_type.smallest.id
  num_workers    = 2
}
```

### Pattern 2: Multiple Workspaces

```hcl
provider "databricks" {
  alias  = "ws_prod"
  host   = var.workspace_prod_url
  client_id     = var.client_id
  client_secret = var.client_secret
}

provider "databricks" {
  alias  = "ws_dev"
  host   = var.workspace_dev_url
  client_id     = var.client_id
  client_secret = var.client_secret
}

resource "databricks_cluster" "prod_cluster" {
  provider      = databricks.ws_prod
  cluster_name  = "prod-shared"
  spark_version = "15.4.x-scala2.12"
  node_type_id  = "i3.xlarge"
  num_workers   = 4
}
```

### Pattern 3: Workspace Referenced Before Created (Dynamic Provider)

When the workspace URL isn't known until apply time, use a data source or output:

```hcl
# Create workspace first
resource "databricks_mws_workspaces" "this" {
  provider       = databricks.mws
  account_id     = var.databricks_account_id
  workspace_name = var.workspace_name
  # ... other config
}

# Use workspace URL in provider (requires two-step apply)
provider "databricks" {
  alias  = "workspace"
  host   = databricks_mws_workspaces.this.workspace_url
  client_id     = var.client_id
  client_secret = var.client_secret
}
```

> **Note**: This requires `terraform apply -target=databricks_mws_workspaces.this` first, then a full apply.

---

## Variables Best Practices

```hcl
# variables.tf
variable "databricks_account_id" {
  type        = string
  description = "Databricks Account ID (found in Account Console)"
  sensitive   = false
}

variable "client_id" {
  type        = string
  description = "Service principal application (client) ID"
  sensitive   = false
}

variable "client_secret" {
  type        = string
  description = "Service principal client secret"
  sensitive   = true
}

variable "databricks_host" {
  type        = string
  description = "Databricks workspace URL (e.g., https://adb-123.azuredatabricks.net)"
}
```

Pass sensitive values via environment variables — **never commit** `terraform.tfvars` with secrets:

```bash
# Set for Terraform variables
export TF_VAR_client_id="<sp-client-id>"
export TF_VAR_client_secret="<sp-client-secret>"
export TF_VAR_databricks_account_id="<account-id>"
```

---

## Data Sources for Dynamic Lookups

```hcl
# Look up latest LTS Spark version
data "databricks_spark_version" "lts" {
  long_term_support = true
}

# Look up smallest node type for the cloud
data "databricks_node_type" "smallest" {
  local_disk = true
}

# Look up existing cluster
data "databricks_cluster" "existing" {
  cluster_name = "Shared Autoscaling"
}

# Look up current user
data "databricks_current_user" "me" {}

# Look up existing metastore
data "databricks_metastore" "this" {
  provider = databricks.mws
  name     = "my-metastore"
}
```

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **`Error: default auth: cannot configure default credentials`** | Set `DATABRICKS_HOST` + either `DATABRICKS_TOKEN` or `DATABRICKS_CLIENT_ID`+`DATABRICKS_CLIENT_SECRET` |
| **`account_id` missing for UC operations** | Add `account_id` to the account-level provider alias |
| **Azure SP can't create workspace** | SP needs `Contributor` role on the resource group and `User Access Administrator` |
| **`cannot use pat auth: host is an account-level host`** | Account-level operations require OAuth M2M (SP), not PAT |
| **Provider initialization order** | Use `depends_on` or two-pass applies when workspace URL is needed by provider |
| **GCP ADC not found** | Run `gcloud auth application-default login` or set `GOOGLE_APPLICATION_CREDENTIALS` |

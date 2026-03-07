# Provider Configuration & Authentication

## Provider Block

```hcl
terraform {
  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.110"
    }
  }
}
```

Always pin the provider version to avoid unexpected breaking changes.

---

## Authentication Patterns

### Personal Access Token (Simplest)

```hcl
provider "databricks" {
  host  = var.databricks_host
  token = var.databricks_token
}
```

```hcl
variable "databricks_host" {
  description = "Databricks workspace URL (e.g., https://adb-1234567890.1.azuredatabricks.net)"
  type        = string
}

variable "databricks_token" {
  description = "Databricks personal access token"
  type        = string
  sensitive   = true
}
```

### Environment Variables

```bash
export DATABRICKS_HOST="https://my-workspace.cloud.databricks.com"
export DATABRICKS_TOKEN="dapi..."
```

```hcl
provider "databricks" {}
```

### Databricks CLI Profile

```hcl
provider "databricks" {
  profile = "my-profile"
}
```

Uses `~/.databrickscfg` profile configuration.

---

## AWS Authentication

### Service Principal (OAuth M2M) — Recommended for CI/CD

```hcl
provider "databricks" {
  host          = var.databricks_host
  client_id     = var.client_id
  client_secret = var.client_secret
}
```

### AWS IAM Role (Account-Level)

```hcl
provider "databricks" {
  host       = "https://accounts.cloud.databricks.com"
  account_id = var.databricks_account_id
}
```

---

## Azure Authentication

### Service Principal with Client Secret

```hcl
provider "databricks" {
  host                        = var.databricks_host
  azure_tenant_id             = var.azure_tenant_id
  azure_client_id             = var.azure_client_id
  azure_client_secret         = var.azure_client_secret
}
```

### Azure CLI

```hcl
provider "databricks" {
  host = var.databricks_host
}
```

Requires `az login` before running Terraform.

### Managed Identity (for Azure VMs / Azure DevOps)

```hcl
provider "databricks" {
  host                    = var.databricks_host
  azure_use_msi           = true
  azure_client_id         = var.msi_client_id  # Optional for user-assigned MI
}
```

---

## GCP Authentication

### Service Account

```hcl
provider "databricks" {
  host                  = var.databricks_host
  google_service_account = var.google_service_account
}
```

### Google Default Credentials

```hcl
provider "databricks" {
  host = var.databricks_host
}
```

Requires `gcloud auth application-default login`.

---

## Multi-Provider Configuration

Use aliases when managing resources across workspaces or account + workspace levels.

### Account + Workspace

```hcl
provider "databricks" {
  alias      = "account"
  host       = "https://accounts.cloud.databricks.com"
  account_id = var.databricks_account_id
  client_id     = var.client_id
  client_secret = var.client_secret
}

provider "databricks" {
  alias         = "workspace"
  host          = var.workspace_host
  client_id     = var.client_id
  client_secret = var.client_secret
}

resource "databricks_group" "admins" {
  provider     = databricks.account
  display_name = "workspace-admins"
}

resource "databricks_cluster" "shared" {
  provider     = databricks.workspace
  cluster_name = "shared"
  # ...
}
```

### Multiple Workspaces

```hcl
provider "databricks" {
  alias = "dev"
  host  = var.dev_workspace_host
  token = var.dev_token
}

provider "databricks" {
  alias = "prod"
  host  = var.prod_workspace_host
  token = var.prod_token
}
```

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **"Unauthorized"** | Verify `host` URL includes `https://` and has no trailing slash |
| **Token expired** | Regenerate PAT; for CI/CD prefer service principal with OAuth |
| **Azure auth fails** | Ensure service principal has "Contributor" role on the workspace resource |
| **Account vs workspace confusion** | Account-level resources (groups, metastores) need account-level auth; workspace resources need workspace-level auth |

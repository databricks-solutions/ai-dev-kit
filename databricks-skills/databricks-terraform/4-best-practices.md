# Best Practices

Project structure, modules, state management, and CI/CD patterns for Databricks Terraform.

## Project Structure

### Single Workspace

```
databricks-infra/
├── main.tf              # Provider config, data sources
├── variables.tf         # Input variables
├── outputs.tf           # Output values
├── terraform.tfvars     # Variable values (gitignored)
├── clusters.tf          # Cluster resources
├── jobs.tf              # Job resources
├── unity-catalog.tf     # UC hierarchy and grants
├── warehouses.tf        # SQL warehouses
└── backend.tf           # Remote state config
```

### Multi-Environment

```
databricks-infra/
├── modules/
│   ├── catalog/         # Reusable UC catalog module
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── cluster/         # Reusable cluster module
│   └── job/             # Reusable job module
├── environments/
│   ├── dev/
│   │   ├── main.tf      # Module calls with dev values
│   │   ├── variables.tf
│   │   ├── terraform.tfvars
│   │   └── backend.tf
│   ├── staging/
│   └── prod/
└── README.md
```

---

## Reusable Modules

### Catalog Module

```hcl
# modules/catalog/variables.tf
variable "catalog_name" { type = string }
variable "layers" {
  type    = list(string)
  default = ["bronze", "silver", "gold"]
}
variable "teams" {
  type = map(object({
    catalog_privileges = list(string)
    schema_privileges  = list(string)
  }))
}

# modules/catalog/main.tf
resource "databricks_catalog" "this" {
  name    = var.catalog_name
  comment = "Managed by Terraform"
}

resource "databricks_schema" "layers" {
  for_each     = toset(var.layers)
  catalog_name = databricks_catalog.this.name
  name         = each.value
}

resource "databricks_grants" "catalog" {
  catalog = databricks_catalog.this.name

  dynamic "grant" {
    for_each = var.teams
    content {
      principal  = grant.key
      privileges = grant.value.catalog_privileges
    }
  }
}

# modules/catalog/outputs.tf
output "catalog_name" { value = databricks_catalog.this.name }
output "schema_names" { value = { for k, v in databricks_schema.layers : k => v.name } }
```

### Usage

```hcl
module "analytics" {
  source       = "../../modules/catalog"
  catalog_name = "analytics"

  teams = {
    "data-engineering" = {
      catalog_privileges = ["USE_CATALOG", "CREATE_SCHEMA"]
      schema_privileges  = ["USE_SCHEMA", "SELECT", "MODIFY", "CREATE_TABLE"]
    }
    "data-analysts" = {
      catalog_privileges = ["USE_CATALOG"]
      schema_privileges  = ["USE_SCHEMA", "SELECT"]
    }
  }
}
```

---

## Remote State

### AWS S3

```hcl
terraform {
  backend "s3" {
    bucket         = "my-terraform-state"
    key            = "databricks/prod/terraform.tfstate"
    region         = "us-west-2"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}
```

### Azure Blob Storage

```hcl
terraform {
  backend "azurerm" {
    resource_group_name  = "terraform-state-rg"
    storage_account_name = "tfstateaccount"
    container_name       = "tfstate"
    key                  = "databricks/prod/terraform.tfstate"
  }
}
```

### GCS

```hcl
terraform {
  backend "gcs" {
    bucket = "my-terraform-state"
    prefix = "databricks/prod"
  }
}
```

---

## Variable Management

### Separate Sensitive Variables

```hcl
# variables.tf
variable "databricks_host" { type = string }
variable "databricks_token" {
  type      = string
  sensitive = true
}
variable "environment" {
  type    = string
  default = "dev"
}
```

```hcl
# terraform.tfvars (gitignored)
databricks_host  = "https://my-workspace.cloud.databricks.com"
databricks_token = "dapi..."
environment      = "production"
```

### Use Locals for Derived Values

```hcl
locals {
  name_prefix = "${var.project}-${var.environment}"
  common_tags = {
    "Project"     = var.project
    "Environment" = var.environment
    "ManagedBy"   = "terraform"
  }
}

resource "databricks_cluster" "shared" {
  cluster_name = "${local.name_prefix}-shared"
  custom_tags  = local.common_tags
  # ...
}
```

---

## CI/CD Integration

### GitHub Actions

```yaml
name: Terraform Databricks
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  terraform:
    runs-on: ubuntu-latest
    env:
      DATABRICKS_HOST: ${{ secrets.DATABRICKS_HOST }}
      DATABRICKS_TOKEN: ${{ secrets.DATABRICKS_TOKEN }}

    steps:
      - uses: actions/checkout@v4

      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "1.9"

      - name: Terraform Init
        run: terraform init

      - name: Terraform Plan
        run: terraform plan -out=tfplan
        if: github.event_name == 'pull_request'

      - name: Terraform Apply
        run: terraform apply -auto-approve tfplan
        if: github.ref == 'refs/heads/main'
```

### Azure DevOps

```yaml
trigger:
  branches:
    include: [main]

pool:
  vmImage: "ubuntu-latest"

steps:
  - task: TerraformInstaller@0
    inputs:
      terraformVersion: "1.9"

  - script: |
      terraform init
      terraform plan -out=tfplan
    env:
      DATABRICKS_HOST: $(DATABRICKS_HOST)
      DATABRICKS_TOKEN: $(DATABRICKS_TOKEN)

  - script: terraform apply -auto-approve tfplan
    condition: eq(variables['Build.SourceBranch'], 'refs/heads/main')
    env:
      DATABRICKS_HOST: $(DATABRICKS_HOST)
      DATABRICKS_TOKEN: $(DATABRICKS_TOKEN)
```

---

## Lifecycle Management

### Prevent Accidental Destruction

```hcl
resource "databricks_catalog" "production" {
  name = "production"

  lifecycle {
    prevent_destroy = true
  }
}
```

### Ignore External Changes

```hcl
resource "databricks_cluster" "shared" {
  cluster_name = "shared"
  # ...

  lifecycle {
    ignore_changes = [
      spark_conf,
      custom_tags,
    ]
  }
}
```

### Import Existing Resources

```bash
# Import existing catalog
terraform import databricks_catalog.analytics "analytics"

# Import existing cluster
terraform import databricks_cluster.shared "<cluster-id>"

# Import existing job
terraform import databricks_job.etl "<job-id>"

# Import grants
terraform import 'databricks_grants.catalog' "catalog/analytics"
```

---

## Common Patterns

### Environment-Specific Sizing

```hcl
variable "environment" { type = string }

locals {
  cluster_config = {
    dev  = { min_workers = 1, max_workers = 2, node_type = "i3.xlarge" }
    prod = { min_workers = 2, max_workers = 10, node_type = "i3.2xlarge" }
  }
  config = local.cluster_config[var.environment]
}

resource "databricks_cluster" "main" {
  node_type_id = local.config.node_type
  autoscale {
    min_workers = local.config.min_workers
    max_workers = local.config.max_workers
  }
}
```

### Conditional Resources

```hcl
variable "enable_monitoring" {
  type    = bool
  default = false
}

resource "databricks_sql_endpoint" "monitoring" {
  count        = var.enable_monitoring ? 1 : 0
  name         = "monitoring-warehouse"
  cluster_size = "Small"
}
```

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **State lock stuck** | Force unlock: `terraform force-unlock <lock-id>` |
| **Drift after manual changes** | Run `terraform plan` to detect; `terraform import` to reconcile |
| **Circular dependencies** | Use `depends_on` explicitly or restructure resource references |
| **Slow plan with many resources** | Use `-target` for focused operations; split into smaller state files |
| **Secrets in state file** | Always use encrypted remote state; never commit `.tfstate` to git |
| **Provider version conflicts** | Pin version with `version = "~> 1.110"` and run `terraform init -upgrade` |

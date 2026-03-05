---
name: databricks-terraform
description: "Generate, validate, and manage Databricks infrastructure using the Databricks Terraform Provider. Use when provisioning workspaces, Unity Catalog objects, clusters, jobs, pipelines, model serving, SQL warehouses, or any Databricks resource via Terraform."
---

# Databricks Terraform

Infrastructure-as-code for Databricks using the [Databricks Terraform Provider](https://registry.terraform.io/providers/databricks/databricks/latest/docs).

## When to Use This Skill

Use this skill when:
- Generating `.tf` files for Databricks resources (clusters, jobs, UC objects, pipelines, etc.)
- Setting up **provider authentication** (PAT, service principal, Azure/AWS/GCP)
- Scaffolding a **Unity Catalog hierarchy** (metastore → catalog → schema → tables/volumes)
- Creating reusable **Terraform modules** for Databricks
- Debugging `terraform plan` or `terraform apply` errors
- Configuring **remote state** backends (S3, Azure Blob, GCS)

## Reference Files

| Topic | File | Description |
|-------|------|-------------|
| Provider & Auth | [1-provider-and-auth.md](1-provider-and-auth.md) | Provider configuration, authentication patterns for AWS/Azure/GCP |
| Core Resources | [2-core-resources.md](2-core-resources.md) | Clusters, jobs, SQL warehouses, notebooks, secrets |
| Unity Catalog | [3-unity-catalog.md](3-unity-catalog.md) | Catalogs, schemas, volumes, grants, external locations |
| Best Practices | [4-best-practices.md](4-best-practices.md) | Project structure, modules, state management, CI/CD |

## Quick Start

### Minimal Provider Setup (AWS)

```hcl
terraform {
  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.110"
    }
  }
}

provider "databricks" {
  host  = var.databricks_host
  token = var.databricks_token
}
```

### Create a Cluster

```hcl
data "databricks_spark_version" "latest_lts" {
  long_term_support = true
}

data "databricks_node_type" "smallest" {
  local_disk = true
}

resource "databricks_cluster" "shared" {
  cluster_name            = "shared-analytics"
  spark_version           = data.databricks_spark_version.latest_lts.id
  node_type_id            = data.databricks_node_type.smallest.id
  autotermination_minutes = 30
  num_workers             = 2

  spark_conf = {
    "spark.databricks.cluster.profile" = "serverless"
  }
}
```

### Create a Unity Catalog Hierarchy

```hcl
resource "databricks_catalog" "analytics" {
  name    = "analytics"
  comment = "Production analytics catalog"
}

resource "databricks_schema" "gold" {
  catalog_name = databricks_catalog.analytics.name
  name         = "gold"
  comment      = "Gold-layer aggregated tables"
}

resource "databricks_volume" "raw_files" {
  catalog_name     = databricks_catalog.analytics.name
  schema_name      = databricks_schema.gold.name
  name             = "raw_files"
  volume_type      = "MANAGED"
  comment          = "Raw ingestion files"
}

resource "databricks_grants" "catalog_grants" {
  catalog = databricks_catalog.analytics.name

  grant {
    principal  = "data-analysts"
    privileges = ["USE_CATALOG"]
  }
}

resource "databricks_grants" "schema_grants" {
  schema = "${databricks_catalog.analytics.name}.${databricks_schema.gold.name}"

  grant {
    principal  = "data-analysts"
    privileges = ["USE_SCHEMA", "SELECT"]
  }
}
```

### Create a Job

```hcl
resource "databricks_job" "etl_pipeline" {
  name = "daily-etl-pipeline"

  task {
    task_key = "ingest"

    notebook_task {
      notebook_path = "/Repos/team/etl/ingest"
    }

    new_cluster {
      spark_version = data.databricks_spark_version.latest_lts.id
      node_type_id  = data.databricks_node_type.smallest.id
      num_workers   = 4
    }
  }

  task {
    task_key = "transform"
    depends_on {
      task_key = "ingest"
    }

    notebook_task {
      notebook_path = "/Repos/team/etl/transform"
    }

    new_cluster {
      spark_version = data.databricks_spark_version.latest_lts.id
      node_type_id  = data.databricks_node_type.smallest.id
      num_workers   = 8
    }
  }

  schedule {
    quartz_cron_expression = "0 0 6 * * ?"
    timezone_id            = "UTC"
  }
}
```

## Common Resources

| Resource | Purpose |
|----------|---------|
| `databricks_cluster` | All-purpose and job clusters |
| `databricks_job` | Scheduled and triggered jobs |
| `databricks_sql_endpoint` | SQL warehouses |
| `databricks_notebook` | Workspace notebooks |
| `databricks_catalog` | Unity Catalog catalogs |
| `databricks_schema` | Unity Catalog schemas |
| `databricks_volume` | Unity Catalog volumes |
| `databricks_grants` | Permissions on UC objects |
| `databricks_external_location` | External storage locations |
| `databricks_storage_credential` | Cloud storage credentials |
| `databricks_model_serving` | Model serving endpoints |
| `databricks_pipeline` | DLT/SDP pipelines |
| `databricks_secret_scope` | Secret scopes |
| `databricks_secret` | Secrets within scopes |
| `databricks_cluster_policy` | Cluster policies |
| `databricks_instance_pool` | Instance pools |
| `databricks_token` | Personal access tokens |
| `databricks_group` | Account/workspace groups |
| `databricks_service_principal` | Service principals |

## Common Data Sources

| Data Source | Purpose |
|-------------|---------|
| `databricks_spark_version` | Look up Spark/DBR versions |
| `databricks_node_type` | Find instance types by criteria |
| `databricks_current_user` | Current authenticated user |
| `databricks_catalogs` | List existing catalogs |
| `databricks_schemas` | List schemas in a catalog |
| `databricks_tables` | List tables in a schema |

## Common Issues

| Issue | Solution |
|-------|----------|
| **"Provider produced inconsistent result"** | Pin provider version with `version = "~> 1.110"` to avoid breaking changes |
| **"Unauthorized" on plan/apply** | Check `host` and `token` variables; ensure token has workspace admin access |
| **Cluster creation fails** | Use `databricks_node_type` data source instead of hardcoding instance types |
| **Grants fail with "not found"** | Ensure parent resources (catalog, schema) are created first with `depends_on` or implicit references |
| **State drift after manual changes** | Run `terraform import` to reconcile, or use `lifecycle { ignore_changes }` |
| **Slow plan with many resources** | Use `-target` for focused applies; split into modules |

## Related Skills

- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** — UC concepts that Terraform resources map to
- **[databricks-jobs](../databricks-jobs/SKILL.md)** — job configurations that `databricks_job` implements
- **[databricks-asset-bundles](../databricks-asset-bundles/SKILL.md)** — alternative IaC approach using Databricks-native bundles
- **[databricks-config](../databricks-config/SKILL.md)** — authentication setup used by the Terraform provider

## Resources

- [Terraform Registry — Databricks Provider](https://registry.terraform.io/providers/databricks/databricks/latest/docs)
- [Databricks Terraform Docs](https://docs.databricks.com/en/dev-tools/terraform/index.html)
- [Automate Unity Catalog with Terraform](https://docs.databricks.com/en/dev-tools/terraform/automate-uc.html)
- [GitHub — terraform-provider-databricks](https://github.com/databricks/terraform-provider-databricks)

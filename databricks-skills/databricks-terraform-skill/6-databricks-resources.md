# Databricks Resource Management

## Overview

Core Databricks resources manageable via Terraform:
- **Clusters** — interactive and job compute
- **Jobs** — scheduled/triggered workloads
- **SQL Warehouses** — serverless SQL compute
- **Notebooks** — workspace code artifacts
- **Secrets** — secure credential storage
- **Cluster Policies** — governance for cluster creation
- **Databricks Apps** — serverless web apps running inside Databricks
- **Mosaic AI Vector Search** — serverless similarity search engine

All resources use a **workspace-level provider**.

---

## Clusters

### All-Purpose Cluster (Interactive)

```hcl
data "databricks_spark_version" "lts" {
  provider          = databricks.workspace
  long_term_support = true
}

data "databricks_node_type" "standard" {
  provider   = databricks.workspace
  local_disk = false
  min_cores  = 4
  gb_per_core = 8
}

resource "databricks_cluster" "shared_autoscaling" {
  provider              = databricks.workspace
  cluster_name          = "Shared Autoscaling Cluster"
  spark_version         = data.databricks_spark_version.lts.id
  node_type_id          = data.databricks_node_type.standard.id
  autotermination_minutes = 30
  is_pinned             = true

  autoscale {
    min_workers = 1
    max_workers = 8
  }

  spark_conf = {
    "spark.databricks.cluster.profile" = "serverless"
    "spark.databricks.repl.allowedLanguages" = "python,sql,scala"
  }

  spark_env_vars = {
    "PYSPARK_PYTHON" = "/databricks/python3/bin/python3"
  }

  custom_tags = {
    "Team"        = "data-engineering"
    "Environment" = "production"
  }
}
```

### Single-Node Cluster (ML Development)

```hcl
resource "databricks_cluster" "ml_single_node" {
  provider              = databricks.workspace
  cluster_name          = "ML Dev Single Node"
  spark_version         = "15.4.x-cpu-ml-scala2.12"  # ML runtime
  node_type_id          = "i3.2xlarge"
  num_workers           = 0   # Single-node
  autotermination_minutes = 60

  spark_conf = {
    "spark.databricks.cluster.profile" = "singleNode"
    "spark.master"                     = "local[*]"
  }

  custom_tags = {
    "ResourceClass" = "SingleNode"
  }
}
```

### AWS Cluster with Instance Profile

```hcl
resource "databricks_instance_profile" "s3_access" {
  provider             = databricks.workspace
  instance_profile_arn = "arn:aws:iam::123456789012:instance-profile/my-s3-profile"
}

resource "databricks_cluster" "aws_cluster" {
  provider              = databricks.workspace
  cluster_name          = "AWS S3 Access Cluster"
  spark_version         = data.databricks_spark_version.lts.id
  node_type_id          = "i3.xlarge"
  autotermination_minutes = 30

  autoscale {
    min_workers = 2
    max_workers = 10
  }

  aws_attributes {
    availability        = "SPOT_WITH_FALLBACK"
    zone_id             = "us-east-1a"
    first_on_demand     = 2
    spot_bid_price_percent = 100
    instance_profile_arn   = databricks_instance_profile.s3_access.id

    ebs_volume_type   = "GENERAL_PURPOSE_SSD"
    ebs_volume_count  = 1
    ebs_volume_size   = 100
  }
}
```

### Azure Cluster

```hcl
resource "databricks_cluster" "azure_cluster" {
  provider              = databricks.workspace
  cluster_name          = "Azure Spot Cluster"
  spark_version         = data.databricks_spark_version.lts.id
  node_type_id          = "Standard_DS3_v2"
  autotermination_minutes = 20

  autoscale {
    min_workers = 2
    max_workers = 8
  }

  azure_attributes {
    availability       = "SPOT_WITH_FALLBACK_AZURE"
    first_on_demand    = 1
    spot_bid_max_price = 100  # % of on-demand price
  }

  library {
    pypi { package = "pandas==2.0.0" }
  }
  library {
    pypi { package = "scikit-learn" }
  }
}
```

### GCP Cluster

```hcl
resource "databricks_cluster" "gcp_cluster" {
  provider              = databricks.workspace
  cluster_name          = "GCP Preemptible Cluster"
  spark_version         = data.databricks_spark_version.lts.id
  node_type_id          = "n1-standard-4"
  autotermination_minutes = 30

  autoscale {
    min_workers = 2
    max_workers = 10
  }

  gcp_attributes {
    availability            = "PREEMPTIBLE_WITH_FALLBACK_GCP"
    google_service_account  = var.cluster_service_account
    local_ssd_count         = 1
  }
}
```

### Cluster with Init Script & Logging

```hcl
resource "databricks_cluster" "with_init" {
  provider              = databricks.workspace
  cluster_name          = "Cluster with Init Script"
  spark_version         = data.databricks_spark_version.lts.id
  node_type_id          = data.databricks_node_type.standard.id
  autotermination_minutes = 30
  num_workers           = 4

  cluster_log_conf {
    s3 {
      destination      = "s3://my-logs-bucket/cluster-logs"
      region           = "us-east-1"
      enable_encryption = true
    }
  }

  init_scripts {
    s3 {
      destination = "s3://my-scripts-bucket/init.sh"
    }
  }

  # Alternative: workspace init script
  init_scripts {
    workspace {
      destination = "/Shared/init-scripts/setup.sh"
    }
  }
}
```

---

## Jobs

### Simple Notebook Job

```hcl
resource "databricks_job" "etl_notebook" {
  provider = databricks.workspace
  name     = "Daily ETL Notebook Job"

  task {
    task_key = "extract_load"

    notebook_task {
      notebook_path = "/Shared/ETL/extract_load"
      source        = "WORKSPACE"
      base_parameters = {
        "date"        = "{{ds}}"
        "environment" = "production"
      }
    }

    new_cluster {
      spark_version           = data.databricks_spark_version.lts.id
      node_type_id            = "i3.xlarge"
      num_workers             = 4
      autotermination_minutes = 30
    }
  }

  schedule {
    quartz_cron_expression = "0 0 6 * * ?"   # Daily at 6 AM UTC
    timezone_id            = "America/New_York"
    pause_status           = "UNPAUSED"
  }

  email_notifications {
    on_failure = ["data-engineering-alerts@company.com"]
    on_success = []
    on_start   = []
  }

  max_concurrent_runs = 1
}
```

### Multi-Task Job with Dependencies

```hcl
resource "databricks_job" "pipeline" {
  provider = databricks.workspace
  name     = "Multi-Stage Pipeline"

  # Shared cluster across tasks
  job_cluster {
    job_cluster_key = "shared_cluster"
    new_cluster {
      spark_version = data.databricks_spark_version.lts.id
      node_type_id  = "i3.xlarge"
      num_workers   = 4
    }
  }

  task {
    task_key        = "ingest"
    job_cluster_key = "shared_cluster"

    python_wheel_task {
      package_name = "my_pipeline"
      entry_point  = "ingest"
      named_parameters = {
        "source" = "s3://source-bucket/data"
      }
    }

    library {
      whl = "s3://my-artifacts/my_pipeline-1.0.0-py3-none-any.whl"
    }
  }

  task {
    task_key        = "transform"
    job_cluster_key = "shared_cluster"

    depends_on {
      task_key = "ingest"
    }

    notebook_task {
      notebook_path = "/Shared/Pipeline/transform"
    }
  }

  task {
    task_key        = "validate"
    job_cluster_key = "shared_cluster"

    depends_on {
      task_key = "transform"
    }

    spark_python_task {
      python_file = "/Shared/Pipeline/validate.py"
      source      = "WORKSPACE"
      parameters  = ["--env", "prod"]
    }
  }

  task {
    task_key = "send_report"

    depends_on {
      task_key = "validate"
    }

    # Serverless — no cluster needed for SQL
    sql_task {
      warehouse_id = var.sql_warehouse_id
      query { query_id = var.report_query_id }
    }
  }

  schedule {
    quartz_cron_expression = "0 0 2 * * ?"
    timezone_id            = "UTC"
    pause_status           = "UNPAUSED"
  }

  email_notifications {
    on_failure = ["pipeline-alerts@company.com"]
  }
}
```

### File Arrival Trigger Job

```hcl
resource "databricks_job" "file_arrival" {
  provider = databricks.workspace
  name     = "Process New Files"

  task {
    task_key = "process_files"

    notebook_task {
      notebook_path = "/Shared/Ingest/process_files"
    }

    new_cluster {
      spark_version = data.databricks_spark_version.lts.id
      node_type_id  = "i3.xlarge"
      num_workers   = 2
    }
  }

  trigger {
    file_arrival {
      url                            = "s3://landing-bucket/incoming/"
      min_time_between_triggers_seconds = 300
      wait_after_last_change_seconds    = 120
    }
  }
}
```

### Git Source Job

```hcl
resource "databricks_job" "git_job" {
  provider = databricks.workspace
  name     = "Git-Sourced ETL"

  git_source {
    url      = "https://github.com/my-org/my-pipeline"
    provider = "gitHub"
    branch   = "main"
  }

  task {
    task_key = "run_etl"

    notebook_task {
      notebook_path = "notebooks/etl_main"  # Relative to repo root
      source        = "GIT"
    }

    new_cluster {
      spark_version = "15.4.x-scala2.12"
      node_type_id  = "i3.xlarge"
      num_workers   = 4
    }
  }
}
```

---

## SQL Warehouses

```hcl
resource "databricks_sql_endpoint" "shared" {
  provider         = databricks.workspace
  name             = "Shared SQL Warehouse"
  cluster_size     = "Small"      # 2X-Small, X-Small, Small, Medium, Large, X-Large, 2X-Large, 3X-Large, 4X-Large
  max_num_clusters = 3
  auto_stop_mins   = 10

  # Serverless (recommended)
  enable_serverless_compute = true

  # Tags
  tags {
    custom_tags {
      key   = "Team"
      value = "Analytics"
    }
  }
}

# Pro warehouse (required for Serverless DLT, Lakeflow)
resource "databricks_sql_endpoint" "pro" {
  provider         = databricks.workspace
  name             = "Pro SQL Warehouse"
  cluster_size     = "Medium"
  warehouse_type   = "PRO"
  max_num_clusters = 5
  auto_stop_mins   = 30
  enable_photon    = true
}
```

---

## Notebooks

```hcl
resource "databricks_notebook" "etl" {
  provider = databricks.workspace
  path     = "/Shared/ETL/main_etl"
  language = "PYTHON"
  content_base64 = base64encode(<<-EOT
    # Databricks notebook source
    # COMMAND ----------
    dbutils.widgets.text("date", "2024-01-01", "Processing Date")
    date = dbutils.widgets.get("date")
    print(f"Processing date: {date}")

    # COMMAND ----------
    df = spark.read.parquet(f"s3://landing-bucket/data/dt={date}")
    df.write.mode("overwrite").saveAsTable("main.bronze.raw_events")
  EOT
  )
}

# Import a notebook from a file
resource "databricks_notebook" "from_file" {
  provider = databricks.workspace
  path     = "/Shared/Analysis/report"
  source   = "${path.module}/notebooks/report.py"
  language = "PYTHON"
}
```

---

## Secrets

```hcl
# Secret scope (Databricks-backed)
resource "databricks_secret_scope" "app_secrets" {
  provider = databricks.workspace
  name     = "app-secrets"
}

# Azure Key Vault-backed scope
resource "databricks_secret_scope" "akv" {
  provider = databricks.workspace
  name     = "azure-kv-scope"

  keyvault_metadata {
    resource_id = azurerm_key_vault.secrets.id
    dns_name    = azurerm_key_vault.secrets.vault_uri
  }

  backend_type = "AZURE_KEYVAULT"
}

# Individual secrets
resource "databricks_secret" "db_password" {
  provider     = databricks.workspace
  key          = "db-password"
  string_value = var.db_password  # sensitive variable
  scope        = databricks_secret_scope.app_secrets.id
}

resource "databricks_secret" "api_token" {
  provider     = databricks.workspace
  key          = "api-token"
  string_value = var.api_token
  scope        = databricks_secret_scope.app_secrets.id
}

# Grant access to secrets scope
resource "databricks_secret_acl" "readers" {
  provider   = databricks.workspace
  principal  = "data_engineers"
  permission = "READ"
  scope      = databricks_secret_scope.app_secrets.id
}
```

---

## Cluster Policies

```hcl
resource "databricks_cluster_policy" "data_engineering" {
  provider = databricks.workspace
  name     = "Data Engineering Policy"

  definition = jsonencode({
    "spark_version" = {
      "type"  = "allowlist"
      "values" = ["15.4.x-scala2.12", "14.3.x-scala2.12"]
      "defaultValue" = "15.4.x-scala2.12"
    }
    "node_type_id" = {
      "type"  = "allowlist"
      "values" = ["i3.xlarge", "i3.2xlarge", "i3.4xlarge"]
    }
    "autotermination_minutes" = {
      "type"         = "range"
      "minValue"     = 10
      "maxValue"     = 120
      "defaultValue" = 30
    }
    "custom_tags.Team" = {
      "type"  = "fixed"
      "value" = "data-engineering"
    }
    # Enforce single-user mode for security
    "data_security_mode" = {
      "type"  = "fixed"
      "value" = "SINGLE_USER"
    }
    # Limit max workers
    "autoscale.max_workers" = {
      "type"     = "range"
      "maxValue" = 20
    }
  })
}

# Assign policy to a group
resource "databricks_permissions" "policy_users" {
  provider   = databricks.workspace
  cluster_policy_id = databricks_cluster_policy.data_engineering.id

  access_control {
    group_name       = "data_engineers"
    permission_level = "CAN_USE"
  }
}
```

---

## Workspace Permissions

```hcl
# Cluster permissions
resource "databricks_permissions" "cluster" {
  provider   = databricks.workspace
  cluster_id = databricks_cluster.shared_autoscaling.id

  access_control {
    group_name       = "data_engineers"
    permission_level = "CAN_RESTART"
  }
  access_control {
    group_name       = "data_analysts"
    permission_level = "CAN_ATTACH_TO"
  }
}

# Job permissions
resource "databricks_permissions" "job" {
  provider = databricks.workspace
  job_id   = databricks_job.etl_notebook.id

  access_control {
    group_name       = "data_engineers"
    permission_level = "CAN_MANAGE"
  }
  access_control {
    group_name       = "data_analysts"
    permission_level = "CAN_VIEW"
  }
}

# Notebook permissions
resource "databricks_permissions" "notebook" {
  provider      = databricks.workspace
  notebook_id   = databricks_notebook.etl.object_id

  access_control {
    group_name       = "data_engineers"
    permission_level = "CAN_EDIT"
  }
  access_control {
    group_name       = "data_analysts"
    permission_level = "CAN_READ"
  }
}

# SQL Warehouse permissions
resource "databricks_permissions" "sql_warehouse" {
  provider      = databricks.workspace
  sql_endpoint_id = databricks_sql_endpoint.shared.id

  access_control {
    group_name       = "users"  # All workspace users
    permission_level = "CAN_USE"
  }
}
```

---

## Workspace Configuration

```hcl
resource "databricks_workspace_conf" "settings" {
  provider = databricks.workspace
  custom_config = {
    "enableIpAccessLists"  = "true"
    "maxTokenLifetimeDays" = "90"
    "enableTokensConfig"   = "true"
  }
}
```

---

## Global Init Script

```hcl
resource "databricks_global_init_script" "proxy" {
  provider  = databricks.workspace
  name      = "Corporate Proxy Setup"
  position  = 0
  enabled   = true
  content_base64 = base64encode(<<-EOT
    #!/bin/bash
    echo "Setting up corporate proxy..."
    echo "https_proxy=https://proxy.company.com:8080" >> /etc/environment
  EOT
  )
}
```

---

## Token Management

```hcl
# Create a service token for automation
resource "databricks_token" "automation" {
  provider         = databricks.workspace
  comment          = "Terraform automation token"
  lifetime_seconds = 7776000  # 90 days
}

output "automation_token" {
  value     = databricks_token.automation.token_value
  sensitive = true
}
```

---

## Databricks Apps

Databricks Apps are serverless web applications that run **inside** the customer's Databricks instance with direct access to workspace data, compute, and services. Each app gets its own auto-provisioned **service principal** and a managed execution environment.

**What Terraform manages:**
- App container creation and metadata (`name`, `description`, `compute_size`)
- Resource bindings — what the app's service principal can access (warehouses, jobs, secrets, model endpoints, UC securables, Lakebase, Genie spaces)
- `user_api_scopes` — which Databricks API scopes user tokens passed to the app can exercise

**What Terraform does NOT manage:**
- App code deployment — use the Databricks CLI (`databricks apps deploy`), Asset Bundles, or a CI/CD pipeline
- App runtime configuration (`app.yaml`) — committed alongside source code

---

### Resource: `databricks_app`

#### Arguments

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `name` | string | Yes | Lowercase alphanumeric + hyphens only; unique within the workspace |
| `description` | string | No | Human-readable description |
| `compute_size` | string | No | `MEDIUM` (default) or `LARGE` |
| `budget_policy_id` | string | No | Budget policy to associate |
| `user_api_scopes` | list(string) | No | API scopes granted to user tokens the app receives |
| `resources` | list(object) | No | Resource bindings — what the app service principal can access |

#### `resources` List Object

Each entry requires `name` and exactly **one** resource-type block:

| Resource Type | Fields | Permissions |
|---------------|--------|-------------|
| `secret` | `scope`, `key` | `READ`, `WRITE`, `MANAGE` |
| `sql_warehouse` | `id` | `CAN_USE`, `CAN_MANAGE`, `IS_OWNER` |
| `serving_endpoint` | `name` | `CAN_VIEW`, `CAN_QUERY`, `CAN_MANAGE` |
| `job` | `id` | `CAN_VIEW`, `CAN_MANAGE_RUN`, `CAN_MANAGE`, `IS_OWNER` |
| `uc_securable` | `securable_type`, `securable_full_name` | e.g. `READ_VOLUME`, `WRITE_VOLUME`, `SELECT` |
| `database` | `database_name`, `instance_name` | `CAN_CONNECT_AND_CREATE` |
| `genie_space` | `name`, `space_id` | `CAN_VIEW`, `CAN_RUN`, `CAN_EDIT`, `CAN_MANAGE` |

All resource entries also accept an optional `description` field.

#### Exported Attributes

| Attribute | Description |
|-----------|-------------|
| `url` | Public URL of the deployed app |
| `app_status.state` | Application state |
| `app_status.message` | Human-readable status message |
| `compute_status.state` | Compute provisioning state |
| `compute_status.message` | Compute status message |
| `service_principal_id` | Numeric ID of the app's auto-created service principal |
| `service_principal_client_id` | OAuth client ID of the service principal |
| `service_principal_name` | Display name of the service principal |
| `default_source_code_path` | Workspace path where app code lives |
| `effective_budget_policy_id` | Applied budget policy |
| `effective_user_api_scopes` | Resolved API scopes |
| `create_time` / `creator` | Creation audit fields |
| `update_time` / `updater` | Last-update audit fields |

---

### Pattern 1: Minimal App

Just a name — binds no resources. Use this to bootstrap the app container before deploying code.

```hcl
resource "databricks_app" "my_app" {
  name        = "my-app"
  description = "My custom Databricks application"
}

output "app_url" {
  value = databricks_app.my_app.url
}

output "app_service_principal_id" {
  value       = databricks_app.my_app.service_principal_id
  description = "Grant this SP access to additional UC objects outside the resources block"
}
```

---

### Pattern 2: RAG / AI App with Model Serving + SQL Warehouse + Secret

A typical Retrieval-Augmented Generation app that queries a vector index via a warehouse, calls a model serving endpoint, and reads an API key from secrets.

```hcl
resource "databricks_app" "rag_app" {
  name        = "rag-assistant"
  description = "RAG application using Llama 3.1 and Vector Search"
  compute_size = "MEDIUM"

  resources = [
    {
      name        = "llm-endpoint"
      description = "Foundation model for generation"
      serving_endpoint = {
        name       = "databricks-meta-llama-3-1-70b-instruct"
        permission = "CAN_QUERY"
      }
    },
    {
      name        = "analytics-warehouse"
      description = "SQL warehouse for structured queries"
      sql_warehouse = {
        id         = var.sql_warehouse_id
        permission = "CAN_USE"
      }
    },
    {
      name        = "openai-api-key"
      description = "External API key stored in secrets"
      secret = {
        scope      = "app-secrets"
        key        = "openai_api_key"
        permission = "READ"
      }
    },
  ]
}

output "rag_app_url" {
  value = databricks_app.rag_app.url
}
```

---

### Pattern 3: Data App with Jobs + UC Volume + Lakebase

An app that triggers a data pipeline job, reads from a UC volume, and connects to a Lakebase database.

```hcl
resource "databricks_app" "data_app" {
  name        = "data-pipeline-app"
  description = "Triggers ETL jobs and reads from UC volumes"

  resources = [
    {
      name = "etl-job"
      job = {
        id         = var.etl_job_id
        permission = "CAN_MANAGE_RUN"  # trigger runs but not edit
      }
    },
    {
      name = "output-volume"
      uc_securable = {
        securable_type      = "volume"
        securable_full_name = "main.silver.output_volume"
        permission          = "READ_VOLUME"
      }
    },
    {
      name = "app-database"
      database = {
        database_name = "app_db"
        instance_name = var.lakebase_instance_name  # databricks_database_instance.this.name
        permission    = "CAN_CONNECT_AND_CREATE"
      }
    },
  ]
}
```

---

### Pattern 4: Dashboard App with Genie Space

An app that surfaces a Genie AI/BI space with controlled access levels.

```hcl
resource "databricks_app" "dashboard_app" {
  name        = "sales-dashboard"
  description = "Sales analytics powered by Genie"

  resources = [
    {
      name = "sales-genie"
      genie_space = {
        name       = "Sales Analytics Genie"
        space_id   = var.genie_space_id
        permission = "CAN_RUN"
      }
    },
    {
      name = "reporting-warehouse"
      sql_warehouse = {
        id         = var.sql_warehouse_id
        permission = "CAN_USE"
      }
    },
  ]
}
```

---

### Pattern 5: App with All Resource Types

Comprehensive example showing every resource-binding type in one app.

```hcl
resource "databricks_app" "full_app" {
  name         = "enterprise-app"
  description  = "Full-featured enterprise application"
  compute_size = "LARGE"

  resources = [
    # SQL Warehouse
    {
      name = "primary-warehouse"
      sql_warehouse = {
        id         = var.sql_warehouse_id
        permission = "CAN_USE"
      }
    },
    # Model serving endpoint
    {
      name = "llm"
      serving_endpoint = {
        name       = "databricks-dbrx-instruct"
        permission = "CAN_QUERY"
      }
    },
    # Scheduled job
    {
      name = "refresh-job"
      job = {
        id         = var.refresh_job_id
        permission = "CAN_MANAGE_RUN"
      }
    },
    # Databricks secret
    {
      name = "db-password"
      secret = {
        scope      = "prod-secrets"
        key        = "db_password"
        permission = "READ"
      }
    },
    # UC volume
    {
      name = "data-volume"
      uc_securable = {
        securable_type      = "volume"
        securable_full_name = "main.gold.reports_volume"
        permission          = "READ_VOLUME"
      }
    },
    # Lakebase instance
    {
      name = "app-db"
      database = {
        database_name = "app_state_db"
        instance_name = var.lakebase_instance_name
        permission    = "CAN_CONNECT_AND_CREATE"
      }
    },
    # Genie space
    {
      name = "analytics-genie"
      genie_space = {
        name       = "Enterprise Analytics"
        space_id   = var.genie_space_id
        permission = "CAN_RUN"
      }
    },
  ]

  user_api_scopes = ["sql", "serving-endpoints"]
}
```

---

### Deployment Workflow

Terraform provisions the app container; code deployment is a separate step:

```bash
# 1. Apply Terraform to create the app container
terraform apply

# 2. Deploy app code using Databricks CLI
databricks apps deploy my-app --source-code-path /Workspace/Users/me/my-app

# 3. Or use Asset Bundles (recommended for CI/CD)
# In databricks.yml:
# bundle:
#   name: my-app
# resources:
#   apps:
#     my_app:
#       name: my-app
#       source_code_path: ./app
```

---

### Import

```hcl
import {
  to = databricks_app.this
  id = "my-app"  # app name
}
```

```bash
terraform import databricks_app.this my-app
```

---

## Mosaic AI Vector Search

Mosaic AI Vector Search is a serverless similarity search engine built into Databricks. It stores vector representations of data alongside metadata for semantic/embedding search. Two resources are required: an **endpoint** (compute) and one or more **indexes** (data + vectors).

### Resource Hierarchy

```
databricks_vector_search_endpoint   (shared compute — one per team/project)
└── databricks_vector_search_index  (the searchable vector index — DELTA_SYNC or DIRECT_ACCESS)
```

---

### Resource: `databricks_vector_search_endpoint`

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `name` | string | Yes | Endpoint name. Changing forces recreation. |
| `endpoint_type` | string | Yes | Currently only `STANDARD`. Changing forces recreation. |
| `budget_policy_id` | string | No | Budget policy to associate |

**Exported attributes:**

| Attribute | Description |
|-----------|-------------|
| `id` | Endpoint name |
| `endpoint_id` | Internal UUID |
| `creator` | Creator email |
| `creation_timestamp` | Creation time (ms) |
| `num_indexes` | Number of indexes on this endpoint |
| `endpoint_status.state` | `PROVISIONING`, `ONLINE`, or `OFFLINE` |
| `endpoint_status.message` | Human-readable status message |

---

### Resource: `databricks_vector_search_index`

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `name` | string | Yes | Three-level UC name: `catalog.schema.index_name` |
| `endpoint_name` | string | Yes | Name of the Vector Search endpoint |
| `primary_key` | string | Yes | Column used as the primary key |
| `index_type` | string | Yes | `DELTA_SYNC` (auto-syncs from a Delta table) or `DIRECT_ACCESS` (manual upsert/delete via API) |
| `delta_sync_index_spec` | block | Conditional | Required when `index_type = "DELTA_SYNC"` |
| `direct_access_index_spec` | block | Conditional | Required when `index_type = "DIRECT_ACCESS"` |

#### `delta_sync_index_spec` Block

| Field | Required | Description |
|-------|----------|-------------|
| `source_table` | Yes | Delta table to sync from (three-level UC name) |
| `pipeline_type` | No | `TRIGGERED` (manual refresh) or `CONTINUOUS` (real-time stream). Default: `TRIGGERED` |
| `columns_to_sync` | No | List of columns to include; defaults to all |
| `embedding_writeback_table` | No | Write embeddings back to a Delta table for inspection |
| `embedding_source_columns` | Conditional | Text columns for model-computed embeddings (use this OR `embedding_vector_columns`) |
| `embedding_vector_columns` | Conditional | Pre-computed vector columns (use this OR `embedding_source_columns`) |

#### `embedding_source_columns` Sub-block

```hcl
embedding_source_columns {
  name                          = "text_column"        # column with raw text
  embedding_model_endpoint_name = "gte-large-en"       # model serving endpoint
  # model_endpoint_name_for_query = "..."              # optional: different model for querying
}
```

#### `embedding_vector_columns` Sub-block

```hcl
embedding_vector_columns {
  name               = "embedding"   # column containing pre-computed vectors
  embedding_dimension = 1024         # vector dimensionality
}
```

#### `direct_access_index_spec` Block

```hcl
direct_access_index_spec {
  schema_json = jsonencode({
    "primary_key" = "id"
    "columns" = [
      { "name" = "id",        "data_type" = "long" },
      { "name" = "text",      "data_type" = "string" },
      { "name" = "embedding", "data_type" = "array<float>", "embedding_dimension" = 1024 }
    ]
  })
  embedding_vector_columns {
    name               = "embedding"
    embedding_dimension = 1024
  }
}
```

**Exported attributes:**

| Attribute | Description |
|-----------|-------------|
| `id` | Index name |
| `creator` | Creator email |
| `delta_sync_index_spec.pipeline_id` | DLT pipeline ID managing the sync |
| `status.ready` | `true` when index is ready for queries |
| `status.indexed_row_count` | Number of rows indexed |
| `status.index_url` | REST API URL for direct index operations |
| `status.message` | Status description |

---

### Pattern 1: DELTA_SYNC with Model-Computed Embeddings

The most common pattern — Databricks computes embeddings from a text column using a model serving endpoint and auto-syncs from a Delta table.

```hcl
# 1. Vector Search endpoint (shared compute)
resource "databricks_vector_search_endpoint" "this" {
  name          = "${var.prefix}-vs-endpoint"
  endpoint_type = "STANDARD"
}

# 2. DELTA_SYNC index — model computes embeddings from the 'content' column
resource "databricks_vector_search_index" "documents" {
  name          = "main.rag.documents_index"
  endpoint_name = databricks_vector_search_endpoint.this.name
  primary_key   = "id"
  index_type    = "DELTA_SYNC"

  delta_sync_index_spec {
    source_table  = "main.rag.documents"       # source Delta table (UC three-level name)
    pipeline_type = "TRIGGERED"                # refresh on demand (use CONTINUOUS for real-time)

    embedding_source_columns {
      name                          = "content"      # text column to embed
      embedding_model_endpoint_name = "gte-large-en" # model serving endpoint name
    }

    columns_to_sync = ["id", "content", "title", "category", "last_updated"]
  }
}

output "index_ready" {
  value = databricks_vector_search_index.documents.status.ready
}
```

---

### Pattern 2: DELTA_SYNC with Pre-Computed Embeddings

Use when embeddings are already computed and stored as a vector column in the Delta table.

```hcl
resource "databricks_vector_search_endpoint" "this" {
  name          = "${var.prefix}-vs-endpoint"
  endpoint_type = "STANDARD"
}

resource "databricks_vector_search_index" "precomputed" {
  name          = "main.ml.embeddings_index"
  endpoint_name = databricks_vector_search_endpoint.this.name
  primary_key   = "chunk_id"
  index_type    = "DELTA_SYNC"

  delta_sync_index_spec {
    source_table  = "main.ml.document_embeddings"
    pipeline_type = "CONTINUOUS"  # real-time sync as table is updated

    embedding_vector_columns {
      name                = "embedding"  # ArrayType(FloatType()) column
      embedding_dimension = 1024
    }

    columns_to_sync = ["chunk_id", "text", "source_url", "embedding"]

    # Optional: write index contents back to a Delta table for inspection/debugging
    embedding_writeback_table = "main.ml.embeddings_index_writeback"
  }
}
```

---

### Pattern 3: DIRECT_ACCESS Index

For applications that control exactly which vectors are stored via the REST API (upsert/delete). No source Delta table required.

```hcl
resource "databricks_vector_search_endpoint" "this" {
  name          = "${var.prefix}-vs-endpoint"
  endpoint_type = "STANDARD"
}

resource "databricks_vector_search_index" "custom" {
  name          = "main.search.custom_index"
  endpoint_name = databricks_vector_search_endpoint.this.name
  primary_key   = "doc_id"
  index_type    = "DIRECT_ACCESS"

  direct_access_index_spec {
    schema_json = jsonencode({
      primary_key = "doc_id"
      columns = [
        { name = "doc_id",    data_type = "string" },
        { name = "text",      data_type = "string" },
        { name = "category",  data_type = "string" },
        { name = "embedding", data_type = "array<float>" }
      ]
    })

    embedding_vector_columns {
      name                = "embedding"
      embedding_dimension = 1536  # e.g. OpenAI text-embedding-3-small
    }
  }
}

output "index_api_url" {
  value       = databricks_vector_search_index.custom.status.index_url
  description = "REST API URL for upsert/delete/query operations"
}
```

---

### Pattern 4: Multiple Indexes on One Endpoint

A single endpoint can host multiple indexes for different use cases.

```hcl
resource "databricks_vector_search_endpoint" "shared" {
  name          = "${var.prefix}-shared-vs"
  endpoint_type = "STANDARD"
}

locals {
  indexes = {
    products = {
      uc_name     = "main.catalog.products_vs_index"
      source      = "main.catalog.products"
      text_col    = "description"
      pk          = "product_id"
      model       = "gte-large-en"
    }
    articles = {
      uc_name     = "main.knowledge.articles_vs_index"
      source      = "main.knowledge.articles"
      text_col    = "body"
      pk          = "article_id"
      model       = "gte-large-en"
    }
  }
}

resource "databricks_vector_search_index" "indexes" {
  for_each = local.indexes

  name          = each.value.uc_name
  endpoint_name = databricks_vector_search_endpoint.shared.name
  primary_key   = each.value.pk
  index_type    = "DELTA_SYNC"

  delta_sync_index_spec {
    source_table  = each.value.source
    pipeline_type = "TRIGGERED"

    embedding_source_columns {
      name                          = each.value.text_col
      embedding_model_endpoint_name = each.value.model
    }
  }
}

output "index_statuses" {
  value = { for k, v in databricks_vector_search_index.indexes : k => v.status.ready }
}
```

---

### UC Grants for Vector Search

Vector Search indexes live in Unity Catalog — use `databricks_grants` to control access.

```hcl
resource "databricks_grants" "vs_index" {
  table = databricks_vector_search_index.documents.name  # index is a UC object

  grant {
    principal  = "data_engineers"
    privileges = ["ALL_PRIVILEGES"]
  }

  grant {
    principal  = "data_analysts"
    privileges = ["SELECT"]  # query the index
  }
}
```

---

### Import (Vector Search)

```bash
terraform import databricks_vector_search_endpoint.this <endpoint-name>
terraform import databricks_vector_search_index.documents "catalog.schema.index_name"
```

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **Cluster creation fails with `CLOUD_FAILURE`** | Check IAM instance profile (AWS) or managed identity (Azure) permissions |
| **`cannot use workspace-level provider`** | Resources like clusters/jobs require workspace provider, not account-level |
| **Job schedule not triggering** | Verify `pause_status = "UNPAUSED"` and cron expression is valid Quartz format |
| **SQL warehouse in `STARTING` state forever** | Check serverless enablement for workspace; fall back to Classic if not enabled |
| **Notebook import fails** | Ensure `content_base64` is properly encoded; use `filebase64()` for file imports |
| **`CAN_RESTART` vs `CAN_MANAGE`** | Permission hierarchy: CAN_ATTACH_TO < CAN_RESTART < CAN_MANAGE |
| **Secrets not accessible in cluster** | Verify `databricks_secret_acl` grants READ to the correct group/user |
| **Policy assignment fails** | Cluster policy requires `CAN_USE` grant; only account admin can create policies |
| **App `url` is empty after apply** | App URL is populated only after first code deployment; run `databricks apps deploy` then refresh state |
| **App service principal needs additional UC grants** | Use `service_principal_id` output to grant extra UC privileges outside the `resources` block |
| **`resources` block with wrong permission value** | Each resource type has its own permission enum — check the table in the Databricks Apps section |
| **App code not updating on `terraform apply`** | Terraform only manages the container/bindings; redeploy code via CLI or Asset Bundles |
| **VS endpoint stuck in `PROVISIONING`** | Endpoint provisioning can take 10–15 min; poll `endpoint_status.state` |
| **VS index `status.ready = false`** | Index sync not yet complete; wait for the DLT pipeline run to finish |
| **`CONTINUOUS` pipeline not catching up** | Check the underlying DLT pipeline in the Delta Live Tables UI for errors |
| **`embedding_model_endpoint_name` not found** | The model serving endpoint must already exist; use `depends_on` if creating it in the same stack |
| **`DIRECT_ACCESS` upsert fails after `terraform apply`** | Index may still be initializing; check `status.ready` before writing |
| **Grants on VS index fail** | Vector Search indexes are UC objects — ensure UC is enabled and the index name uses three-level format |

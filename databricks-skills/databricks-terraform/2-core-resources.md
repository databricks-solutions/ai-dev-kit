# Core Resources

Common Databricks resources managed via Terraform.

## Clusters

### All-Purpose Cluster

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

  autoscale {
    min_workers = 1
    max_workers = 4
  }

  spark_conf = {
    "spark.databricks.io.cache.enabled" = "true"
  }

  custom_tags = {
    "Team"        = "data-engineering"
    "Environment" = "production"
  }
}
```

### Single-Node Cluster (ML / Development)

```hcl
resource "databricks_cluster" "single_node" {
  cluster_name            = "ml-single-node"
  spark_version           = data.databricks_spark_version.latest_lts.id
  node_type_id            = "i3.xlarge"
  autotermination_minutes = 60
  num_workers             = 0

  spark_conf = {
    "spark.databricks.cluster.profile" = "singleNode"
    "spark.master"                     = "local[*]"
  }
}
```

---

## Jobs

### Notebook Job with Schedule

```hcl
resource "databricks_job" "daily_etl" {
  name = "daily-etl"

  task {
    task_key = "ingest"

    notebook_task {
      notebook_path = "/Repos/team/etl/ingest"
      base_parameters = {
        "env" = "production"
      }
    }

    new_cluster {
      spark_version = data.databricks_spark_version.latest_lts.id
      node_type_id  = data.databricks_node_type.smallest.id
      num_workers   = 4
    }
  }

  schedule {
    quartz_cron_expression = "0 0 6 * * ?"
    timezone_id            = "UTC"
  }

  email_notifications {
    on_failure = ["team@company.com"]
  }
}
```

### Multi-Task Job with Dependencies

```hcl
resource "databricks_job" "pipeline" {
  name = "data-pipeline"

  task {
    task_key = "bronze"
    notebook_task {
      notebook_path = "/Repos/team/pipeline/bronze"
    }
    existing_cluster_id = databricks_cluster.shared.id
  }

  task {
    task_key = "silver"
    depends_on {
      task_key = "bronze"
    }
    notebook_task {
      notebook_path = "/Repos/team/pipeline/silver"
    }
    existing_cluster_id = databricks_cluster.shared.id
  }

  task {
    task_key = "gold"
    depends_on {
      task_key = "silver"
    }
    notebook_task {
      notebook_path = "/Repos/team/pipeline/gold"
    }
    existing_cluster_id = databricks_cluster.shared.id
  }
}
```

### Python Script Job (Serverless)

```hcl
resource "databricks_job" "serverless_etl" {
  name = "serverless-etl"

  task {
    task_key = "run"

    python_wheel_task {
      package_name = "my_etl"
      entry_point  = "main"
    }

    environment_key = "default"
  }

  environment {
    environment_key = "default"

    spec {
      client = "1"
      dependencies = [
        "my_etl==1.0.0"
      ]
    }
  }
}
```

---

## SQL Warehouses

```hcl
resource "databricks_sql_endpoint" "analytics" {
  name             = "analytics-warehouse"
  cluster_size     = "Small"
  max_num_clusters = 2
  auto_stop_mins   = 15

  warehouse_type = "PRO"

  tags {
    custom_tags {
      key   = "Team"
      value = "analytics"
    }
  }
}
```

### Serverless SQL Warehouse

```hcl
resource "databricks_sql_endpoint" "serverless" {
  name                = "serverless-warehouse"
  cluster_size        = "Small"
  max_num_clusters    = 1
  auto_stop_mins      = 10
  enable_serverless_compute = true
}
```

---

## DLT / SDP Pipelines

```hcl
resource "databricks_pipeline" "etl" {
  name    = "etl-pipeline"
  catalog = "analytics"
  schema  = "silver"

  library {
    notebook {
      path = "/Repos/team/pipelines/etl"
    }
  }

  continuous  = false
  development = false

  cluster {
    label       = "default"
    num_workers = 4
  }
}
```

---

## Model Serving

```hcl
resource "databricks_model_serving" "llm_endpoint" {
  name = "llm-endpoint"

  config {
    served_entities {
      entity_name    = "catalog.schema.my_model"
      entity_version = "1"
      workload_size  = "Small"
      scale_to_zero_enabled = true
    }

    auto_capture_config {
      catalog_name     = "analytics"
      schema_name      = "inference_logs"
      table_name_prefix = "llm_endpoint"
      enabled          = true
    }
  }
}
```

---

## Secrets

```hcl
resource "databricks_secret_scope" "app" {
  name = "app-secrets"
}

resource "databricks_secret" "api_key" {
  scope        = databricks_secret_scope.app.name
  key          = "api-key"
  string_value = var.api_key
}
```

---

## Instance Pools

```hcl
resource "databricks_instance_pool" "shared" {
  instance_pool_name = "shared-pool"
  node_type_id       = data.databricks_node_type.smallest.id

  min_idle_instances                  = 0
  max_capacity                        = 20
  idle_instance_autotermination_minutes = 10

  preloaded_spark_versions = [
    data.databricks_spark_version.latest_lts.id
  ]
}

resource "databricks_cluster" "pooled" {
  cluster_name            = "pooled-cluster"
  spark_version           = data.databricks_spark_version.latest_lts.id
  instance_pool_id        = databricks_instance_pool.shared.id
  autotermination_minutes = 30
  num_workers             = 2
}
```

---

## Cluster Policies

```hcl
resource "databricks_cluster_policy" "team_policy" {
  name = "data-engineering-policy"

  definition = jsonencode({
    "autotermination_minutes" : {
      "type" : "range",
      "minValue" : 10,
      "maxValue" : 120,
      "defaultValue" : 30
    },
    "num_workers" : {
      "type" : "range",
      "minValue" : 1,
      "maxValue" : 10
    },
    "node_type_id" : {
      "type" : "allowlist",
      "values" : ["i3.xlarge", "i3.2xlarge"]
    },
    "custom_tags.Team" : {
      "type" : "fixed",
      "value" : "data-engineering"
    }
  })
}
```

---

## Notebooks

```hcl
resource "databricks_notebook" "etl" {
  path     = "/Repos/team/etl/ingest"
  language = "PYTHON"
  content_base64 = base64encode(<<-EOT
    # Databricks notebook source
    df = spark.read.format("json").load("/Volumes/catalog/schema/volume/data/")
    df.write.mode("overwrite").saveAsTable("catalog.schema.bronze_events")
  EOT
  )
}
```

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **Cluster creation fails with "node type not found"** | Use `databricks_node_type` data source instead of hardcoding |
| **Job fails with "notebook not found"** | Ensure notebook path exists; use `depends_on` if creating notebook in same config |
| **SQL warehouse stuck creating** | Check workspace quotas; serverless warehouses may need admin enablement |
| **Pipeline fails to start** | Verify catalog/schema exist and user has permissions |

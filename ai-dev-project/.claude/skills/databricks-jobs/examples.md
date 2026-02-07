# Complete Examples

## Contents
- [ETL Pipeline with Multiple Tasks](#etl-pipeline-with-multiple-tasks)
- [Scheduled Data Warehouse Refresh](#scheduled-data-warehouse-refresh)
- [Event-Driven Pipeline](#event-driven-pipeline)
- [ML Training Pipeline](#ml-training-pipeline)
- [Multi-Environment Deployment](#multi-environment-deployment)
- [Streaming Job](#streaming-job)
- [Cross-Job Orchestration](#cross-job-orchestration)

---

## ETL Pipeline with Multiple Tasks

A classic extract-transform-load pipeline with task dependencies.

### DABs YAML

```yaml
# resources/etl_job.yml
resources:
  jobs:
    daily_etl:
      name: "[${bundle.target}] Daily ETL Pipeline"

      # Schedule: Daily at 6 AM UTC
      schedule:
        quartz_cron_expression: "0 0 6 * * ?"
        timezone_id: "UTC"
        pause_status: UNPAUSED

      # Job parameters
      parameters:
        - name: load_date
          default: "{{start_date}}"
        - name: env
          default: "${bundle.target}"

      # Shared cluster for all tasks
      job_clusters:
        - job_cluster_key: etl_cluster
          new_cluster:
            spark_version: "15.4.x-scala2.12"
            node_type_id: "i3.xlarge"
            num_workers: 4
            spark_conf:
              spark.sql.shuffle.partitions: "200"

      # Email notifications
      email_notifications:
        on_failure:
          - "data-team@example.com"
        on_success:
          - "data-team@example.com"

      tasks:
        # Extract from source systems
        - task_key: extract_orders
          job_cluster_key: etl_cluster
          notebook_task:
            notebook_path: ../src/notebooks/extract_orders.py
            base_parameters:
              load_date: "{{job.parameters.load_date}}"

        - task_key: extract_customers
          job_cluster_key: etl_cluster
          notebook_task:
            notebook_path: ../src/notebooks/extract_customers.py
            base_parameters:
              load_date: "{{job.parameters.load_date}}"

        - task_key: extract_products
          job_cluster_key: etl_cluster
          notebook_task:
            notebook_path: ../src/notebooks/extract_products.py

        # Transform: wait for all extracts
        - task_key: transform_facts
          depends_on:
            - task_key: extract_orders
            - task_key: extract_customers
            - task_key: extract_products
          job_cluster_key: etl_cluster
          notebook_task:
            notebook_path: ../src/notebooks/transform_facts.py
            base_parameters:
              load_date: "{{job.parameters.load_date}}"

        # Load: run after transform
        - task_key: load_warehouse
          depends_on:
            - task_key: transform_facts
          job_cluster_key: etl_cluster
          notebook_task:
            notebook_path: ../src/notebooks/load_warehouse.py

        # Data quality check
        - task_key: validate_data
          depends_on:
            - task_key: load_warehouse
          run_if: ALL_SUCCESS
          job_cluster_key: etl_cluster
          notebook_task:
            notebook_path: ../src/notebooks/validate_data.py

      permissions:
        - level: CAN_VIEW
          group_name: "data-analysts"
        - level: CAN_MANAGE_RUN
          group_name: "data-engineers"
```

### Python SDK Equivalent

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import (
    Task, NotebookTask, Source,
    JobCluster, ClusterSpec,
    CronSchedule, PauseStatus,
    JobEmailNotifications,
    JobParameterDefinition
)

w = WorkspaceClient()

job = w.jobs.create(
    name="Daily ETL Pipeline",
    schedule=CronSchedule(
        quartz_cron_expression="0 0 6 * * ?",
        timezone_id="UTC",
        pause_status=PauseStatus.UNPAUSED
    ),
    parameters=[
        JobParameterDefinition(name="load_date", default="{{start_date}}"),
        JobParameterDefinition(name="env", default="prod")
    ],
    job_clusters=[
        JobCluster(
            job_cluster_key="etl_cluster",
            new_cluster=ClusterSpec(
                spark_version="15.4.x-scala2.12",
                node_type_id="i3.xlarge",
                num_workers=4
            )
        )
    ],
    email_notifications=JobEmailNotifications(
        on_failure=["data-team@example.com"],
        on_success=["data-team@example.com"]
    ),
    tasks=[
        Task(
            task_key="extract_orders",
            job_cluster_key="etl_cluster",
            notebook_task=NotebookTask(
                notebook_path="/Workspace/etl/extract_orders",
                source=Source.WORKSPACE,
                base_parameters={"load_date": "{{job.parameters.load_date}}"}
            )
        ),
        Task(
            task_key="extract_customers",
            job_cluster_key="etl_cluster",
            notebook_task=NotebookTask(
                notebook_path="/Workspace/etl/extract_customers",
                source=Source.WORKSPACE
            )
        ),
        Task(
            task_key="transform_facts",
            depends_on=[
                {"task_key": "extract_orders"},
                {"task_key": "extract_customers"}
            ],
            job_cluster_key="etl_cluster",
            notebook_task=NotebookTask(
                notebook_path="/Workspace/etl/transform_facts",
                source=Source.WORKSPACE
            )
        ),
        Task(
            task_key="load_warehouse",
            depends_on=[{"task_key": "transform_facts"}],
            job_cluster_key="etl_cluster",
            notebook_task=NotebookTask(
                notebook_path="/Workspace/etl/load_warehouse",
                source=Source.WORKSPACE
            )
        )
    ]
)

print(f"Created job: {job.job_id}")
```

---

## Scheduled Data Warehouse Refresh

SQL-based warehouse refresh with multiple queries.

### DABs YAML

```yaml
resources:
  jobs:
    warehouse_refresh:
      name: "[${bundle.target}] Warehouse Refresh"

      schedule:
        quartz_cron_expression: "0 0 4 * * ?"  # 4 AM daily
        timezone_id: "America/New_York"
        pause_status: UNPAUSED

      tasks:
        # Refresh dimension tables
        - task_key: refresh_dim_customers
          sql_task:
            file:
              path: ../src/sql/refresh_dim_customers.sql
              source: WORKSPACE
            warehouse_id: ${var.warehouse_id}

        - task_key: refresh_dim_products
          sql_task:
            file:
              path: ../src/sql/refresh_dim_products.sql
              source: WORKSPACE
            warehouse_id: ${var.warehouse_id}

        # Refresh fact tables (depends on dimensions)
        - task_key: refresh_fact_sales
          depends_on:
            - task_key: refresh_dim_customers
            - task_key: refresh_dim_products
          sql_task:
            file:
              path: ../src/sql/refresh_fact_sales.sql
              source: WORKSPACE
            warehouse_id: ${var.warehouse_id}

        # Update aggregations
        - task_key: update_aggregations
          depends_on:
            - task_key: refresh_fact_sales
          sql_task:
            file:
              path: ../src/sql/update_aggregations.sql
              source: WORKSPACE
            warehouse_id: ${var.warehouse_id}

        # Refresh dashboard
        - task_key: refresh_dashboard
          depends_on:
            - task_key: update_aggregations
          sql_task:
            dashboard:
              dashboard_id: "dashboard-uuid-here"
            warehouse_id: ${var.warehouse_id}
```

---

## Event-Driven Pipeline

Pipeline triggered by file arrival and table updates.

### DABs YAML

```yaml
resources:
  jobs:
    event_driven_pipeline:
      name: "[${bundle.target}] Event-Driven Pipeline"

      # Trigger on file arrival
      trigger:
        pause_status: UNPAUSED
        file_arrival:
          url: "s3://data-lake/incoming/orders/"
          min_time_between_triggers_seconds: 300  # 5 min cooldown
          wait_after_last_change_seconds: 60  # Wait for batch completion

      # Health monitoring
      health:
        rules:
          - metric: RUN_DURATION_SECONDS
            op: GREATER_THAN
            value: 1800  # Alert if > 30 min

      email_notifications:
        on_failure:
          - "data-alerts@example.com"
        on_duration_warning_threshold_exceeded:
          - "data-alerts@example.com"

      tasks:
        - task_key: process_incoming
          notebook_task:
            notebook_path: ../src/notebooks/process_incoming_files.py
          new_cluster:
            spark_version: "15.4.x-scala2.12"
            node_type_id: "i3.xlarge"
            autoscale:
              min_workers: 2
              max_workers: 10
```

### Table Update Trigger Example

```yaml
resources:
  jobs:
    table_triggered_job:
      name: "[${bundle.target}] Table Update Handler"

      trigger:
        pause_status: UNPAUSED
        table_update:
          table_names:
            - "main.bronze.raw_orders"
            - "main.bronze.raw_inventory"
          condition: ANY_UPDATED
          min_time_between_triggers_seconds: 600
          wait_after_last_change_seconds: 120

      tasks:
        - task_key: process_updates
          notebook_task:
            notebook_path: ../src/notebooks/process_table_updates.py
```

---

## ML Training Pipeline

Machine learning workflow with training, evaluation, and deployment.

### DABs YAML

```yaml
resources:
  jobs:
    ml_training:
      name: "[${bundle.target}] ML Training Pipeline"

      # Weekly retraining
      schedule:
        quartz_cron_expression: "0 0 2 ? * SUN"  # Sunday 2 AM
        timezone_id: "UTC"
        pause_status: UNPAUSED

      parameters:
        - name: model_name
          default: "sales_forecaster"
        - name: experiment_name
          default: "/Shared/experiments/sales_forecast"

      # GPU cluster for training
      job_clusters:
        - job_cluster_key: gpu_cluster
          new_cluster:
            spark_version: "15.4.x-gpu-ml-scala2.12"
            node_type_id: "g5.xlarge"
            num_workers: 2
            aws_attributes:
              first_on_demand: 1

        - job_cluster_key: cpu_cluster
          new_cluster:
            spark_version: "15.4.x-scala2.12"
            node_type_id: "i3.xlarge"
            num_workers: 4

      # ML environment
      environments:
        - environment_key: ml_env
          spec:
            dependencies:
              - mlflow>=2.10.0
              - scikit-learn>=1.4.0
              - pandas>=2.0.0
              - xgboost>=2.0.0

      tasks:
        # Data preparation
        - task_key: prepare_training_data
          job_cluster_key: cpu_cluster
          environment_key: ml_env
          notebook_task:
            notebook_path: ../src/ml/prepare_training_data.py
            base_parameters:
              output_table: "main.ml.training_data"

        # Feature engineering
        - task_key: engineer_features
          depends_on:
            - task_key: prepare_training_data
          job_cluster_key: cpu_cluster
          environment_key: ml_env
          notebook_task:
            notebook_path: ../src/ml/engineer_features.py

        # Model training
        - task_key: train_model
          depends_on:
            - task_key: engineer_features
          job_cluster_key: gpu_cluster
          environment_key: ml_env
          notebook_task:
            notebook_path: ../src/ml/train_model.py
            base_parameters:
              model_name: "{{job.parameters.model_name}}"
              experiment_name: "{{job.parameters.experiment_name}}"

        # Model evaluation
        - task_key: evaluate_model
          depends_on:
            - task_key: train_model
          job_cluster_key: cpu_cluster
          environment_key: ml_env
          notebook_task:
            notebook_path: ../src/ml/evaluate_model.py

        # Conditional deployment (only on success)
        - task_key: deploy_model
          depends_on:
            - task_key: evaluate_model
          run_if: ALL_SUCCESS
          job_cluster_key: cpu_cluster
          environment_key: ml_env
          notebook_task:
            notebook_path: ../src/ml/deploy_model.py
            base_parameters:
              model_name: "{{job.parameters.model_name}}"
```

---

## Multi-Environment Deployment

Job configuration with environment-specific settings.

### databricks.yml

```yaml
bundle:
  name: data-pipeline

include:
  - resources/*.yml

variables:
  warehouse_id:
    lookup:
      warehouse: "Shared SQL Warehouse"
  notification_email:
    default: "data-team@example.com"

targets:
  dev:
    default: true
    mode: development
    workspace:
      profile: dev-profile
    variables:
      notification_email: "dev-team@example.com"

  staging:
    mode: development
    workspace:
      profile: staging-profile

  prod:
    mode: production
    workspace:
      profile: prod-profile
    run_as:
      service_principal_name: "production-sp"
```

### resources/jobs.yml

```yaml
resources:
  jobs:
    data_pipeline:
      name: "[${bundle.target}] Data Pipeline"

      # Only schedule in prod
      schedule:
        quartz_cron_expression: "0 0 6 * * ?"
        timezone_id: "UTC"
        pause_status: ${if(bundle.target == "prod", "UNPAUSED", "PAUSED")}

      # Environment-specific cluster sizing
      job_clusters:
        - job_cluster_key: main_cluster
          new_cluster:
            spark_version: "15.4.x-scala2.12"
            node_type_id: ${if(bundle.target == "prod", "i3.2xlarge", "i3.xlarge")}
            num_workers: ${if(bundle.target == "prod", 8, 2)}

      email_notifications:
        on_failure:
          - ${var.notification_email}

      tasks:
        - task_key: process_data
          job_cluster_key: main_cluster
          notebook_task:
            notebook_path: ../src/notebooks/process_data.py
            base_parameters:
              env: "${bundle.target}"
              catalog: "${bundle.target}_catalog"

      permissions:
        - level: CAN_VIEW
          group_name: "data-analysts"
        - level: CAN_MANAGE_RUN
          group_name: "data-engineers"
        - level: CAN_MANAGE
          service_principal_name: "deployment-sp"
```

---

## Streaming Job

Continuous streaming job with monitoring.

### DABs YAML

```yaml
resources:
  jobs:
    streaming_processor:
      name: "[${bundle.target}] Streaming Processor"

      # Continuous execution
      continuous:
        pause_status: UNPAUSED

      # Health monitoring for streaming
      health:
        rules:
          - metric: STREAMING_BACKLOG_SECONDS
            op: GREATER_THAN
            value: 300  # Alert if > 5 min behind
          - metric: STREAMING_BACKLOG_RECORDS
            op: GREATER_THAN
            value: 1000000  # Alert if > 1M records behind

      email_notifications:
        on_failure:
          - "streaming-alerts@example.com"
        on_streaming_backlog_exceeded:
          - "streaming-alerts@example.com"

      webhook_notifications:
        on_failure:
          - id: "pagerduty-streaming-alerts"
        on_streaming_backlog_exceeded:
          - id: "slack-streaming-channel"

      tasks:
        - task_key: stream_processor
          notebook_task:
            notebook_path: ../src/notebooks/stream_processor.py
          new_cluster:
            spark_version: "15.4.x-scala2.12"
            node_type_id: "i3.xlarge"
            autoscale:
              min_workers: 2
              max_workers: 16
            spark_conf:
              spark.databricks.streaming.statefulOperator.asyncCheckpoint.enabled: "true"
              spark.sql.streaming.stateStore.providerClass: "com.databricks.sql.streaming.state.RocksDBStateStoreProvider"
```

---

## Cross-Job Orchestration

Multiple jobs with dependencies using run_job_task.

### DABs YAML

```yaml
resources:
  jobs:
    # Data ingestion job
    ingestion_job:
      name: "[${bundle.target}] Data Ingestion"
      tasks:
        - task_key: ingest
          notebook_task:
            notebook_path: ../src/notebooks/ingest.py

    # Data transformation job
    transformation_job:
      name: "[${bundle.target}] Data Transformation"
      tasks:
        - task_key: transform
          notebook_task:
            notebook_path: ../src/notebooks/transform.py

    # Master orchestration job
    orchestrator:
      name: "[${bundle.target}] Master Orchestrator"

      schedule:
        quartz_cron_expression: "0 0 1 * * ?"
        timezone_id: "UTC"
        pause_status: UNPAUSED

      tasks:
        # Run ingestion first
        - task_key: run_ingestion
          run_job_task:
            job_id: ${resources.jobs.ingestion_job.id}

        # Run transformation after ingestion
        - task_key: run_transformation
          depends_on:
            - task_key: run_ingestion
          run_job_task:
            job_id: ${resources.jobs.transformation_job.id}

        # Final validation
        - task_key: validate_all
          depends_on:
            - task_key: run_transformation
          notebook_task:
            notebook_path: ../src/notebooks/validate_all.py
```

---

## For Each Task - Parallel Processing

Process multiple items in parallel using for_each_task.

### DABs YAML

```yaml
resources:
  jobs:
    parallel_processor:
      name: "[${bundle.target}] Parallel Region Processor"

      schedule:
        quartz_cron_expression: "0 0 8 * * ?"
        timezone_id: "UTC"
        pause_status: UNPAUSED

      tasks:
        # Generate list of items to process
        - task_key: get_regions
          notebook_task:
            notebook_path: ../src/notebooks/get_active_regions.py

        # Process each region in parallel
        - task_key: process_regions
          depends_on:
            - task_key: get_regions
          for_each_task:
            inputs: "{{tasks.get_regions.values.regions}}"
            concurrency: 10  # Max 10 parallel
            task:
              task_key: process_region
              notebook_task:
                notebook_path: ../src/notebooks/process_region.py
                base_parameters:
                  region: "{{input}}"

        # Aggregate results after all regions processed
        - task_key: aggregate_results
          depends_on:
            - task_key: process_regions
          run_if: ALL_DONE  # Run even if some regions failed
          notebook_task:
            notebook_path: ../src/notebooks/aggregate_results.py
```

### Notebook: get_active_regions.py

```python
# Get list of active regions to process
regions = spark.sql("""
    SELECT DISTINCT region_code
    FROM main.config.active_regions
    WHERE is_active = true
""").collect()

region_list = [row.region_code for row in regions]

# Pass to downstream for_each_task
dbutils.jobs.taskValues.set(key="regions", value=region_list)
```

### Notebook: process_region.py

```python
# Get region from parameter
region = dbutils.widgets.get("region")

# Process data for this region
df = spark.sql(f"""
    SELECT * FROM main.bronze.orders
    WHERE region = '{region}'
""")

# Transform and write
df_transformed = transform_orders(df)
df_transformed.write.mode("append").saveAsTable(f"main.silver.orders_{region}")

print(f"Processed region: {region}")
```

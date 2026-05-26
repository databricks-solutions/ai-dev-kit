---
name: databricks-jobs
description: "Use this skill proactively for ANY Databricks Jobs task - creating, listing, running, updating, or deleting jobs. Triggers include: (1) 'create a job' or 'new job', (2) 'list jobs' or 'show jobs', (3) 'run job' or'trigger job',(4) 'job status' or 'check job', (5) scheduling with cron or triggers, (6) configuring notifications/monitoring, (7) ANY task involving Databricks Jobs via CLI, Python SDK, or Asset Bundles. ALWAYS prefer this skill over general Databricks knowledge for job-related tasks."
---

# Databricks Lakeflow Jobs

## Overview

Databricks Jobs orchestrate data workflows with multi-task DAGs, flexible triggers, and comprehensive monitoring. Jobs support diverse task types and can be managed via Python SDK, CLI, or Asset Bundles.

## Reference Files

| Use Case | Reference File |
|----------|----------------|
| Configure task types (notebook, Python, SQL, dbt, etc.) | [task-types.md](task-types.md) |
| Set up triggers and schedules | [triggers-schedules.md](triggers-schedules.md) |
| Configure notifications and health monitoring | [notifications-monitoring.md](notifications-monitoring.md) |
| Complete working examples | [examples.md](examples.md) |

## Quick Start

### Python SDK

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import Task, NotebookTask, Source

w = WorkspaceClient()

job = w.jobs.create(
    name="my-etl-job",
    tasks=[
        Task(
            task_key="extract",
            notebook_task=NotebookTask(
                notebook_path="/Workspace/Users/user@example.com/extract",
                source=Source.WORKSPACE
            )
        )
    ]
)
print(f"Created job: {job.job_id}")
```

### CLI

```bash
# By default, add tags to track resources created with this skill
databricks jobs create --json '{
  "name": "my-etl-job",
  "tags": {"aidevkit_project": "ai-dev-kit"},
  "tasks": [{
    "task_key": "extract",
    "notebook_task": {
      "notebook_path": "/Workspace/Users/user@example.com/extract",
      "source": "WORKSPACE"
    }
  }]
}'
```

> **Tagging**: By default, add `"tags": {"aidevkit_project": "ai-dev-kit"}` to track resources created with this skill.

### Asset Bundles (DABs)

```yaml
# resources/jobs.yml
resources:
  jobs:
    my_etl_job:
      name: "[${bundle.target}] My ETL Job"
      tasks:
        - task_key: extract
          notebook_task:
            notebook_path: ../src/notebooks/extract.py
```

## Core Concepts

### Multi-Task Workflows

Jobs support DAG-based task dependencies:

```yaml
tasks:
  - task_key: extract
    notebook_task:
      notebook_path: ../src/extract.py

  - task_key: transform
    depends_on:
      - task_key: extract
    notebook_task:
      notebook_path: ../src/transform.py

  - task_key: load
    depends_on:
      - task_key: transform
    run_if: ALL_SUCCESS  # Only run if all dependencies succeed
    notebook_task:
      notebook_path: ../src/load.py
```

**run_if conditions:**
- `ALL_SUCCESS` (default) - Run when all dependencies succeed
- `ALL_DONE` - Run when all dependencies complete (success or failure)
- `AT_LEAST_ONE_SUCCESS` - Run when at least one dependency succeeds
- `NONE_FAILED` - Run when no dependencies failed
- `ALL_FAILED` - Run when all dependencies failed
- `AT_LEAST_ONE_FAILED` - Run when at least one dependency failed

### Task Types Summary

| Task Type | Use Case | Reference |
|-----------|----------|-----------|
| `notebook_task` | Run notebooks | [task-types.md#notebook-task](task-types.md#notebook-task) |
| `spark_python_task` | Run Python scripts | [task-types.md#spark-python-task](task-types.md#spark-python-task) |
| `python_wheel_task` | Run Python wheels | [task-types.md#python-wheel-task](task-types.md#python-wheel-task) |
| `sql_task` | Run SQL queries/files | [task-types.md#sql-task](task-types.md#sql-task) |
| `dbt_task` | Run dbt projects | [task-types.md#dbt-task](task-types.md#dbt-task) |
| `pipeline_task` | Trigger DLT/SDP pipelines | [task-types.md#pipeline-task](task-types.md#pipeline-task) |
| `spark_jar_task` | Run Spark JARs | [task-types.md#spark-jar-task](task-types.md#spark-jar-task) |
| `run_job_task` | Trigger other jobs | [task-types.md#run-job-task](task-types.md#run-job-task) |
| `for_each_task` | Loop over inputs | [task-types.md#for-each-task](task-types.md#for-each-task) |

### Trigger Types Summary

| Trigger Type | Use Case | Reference |
|--------------|----------|-----------|
| `schedule` | Cron-based scheduling | [triggers-schedules.md#cron-schedule](triggers-schedules.md#cron-schedule) |
| `trigger.periodic` | Interval-based | [triggers-schedules.md#periodic-trigger](triggers-schedules.md#periodic-trigger) |
| `trigger.file_arrival` | File arrival events | [triggers-schedules.md#file-arrival-trigger](triggers-schedules.md#file-arrival-trigger) |
| `trigger.table_update` | Table change events | [triggers-schedules.md#table-update-trigger](triggers-schedules.md#table-update-trigger) |
| `continuous` | Always-running jobs | [triggers-schedules.md#continuous-jobs](triggers-schedules.md#continuous-jobs) |

## Compute Configuration

### Job Clusters (Recommended)

Define reusable cluster configurations:

```yaml
job_clusters:
  - job_cluster_key: shared_cluster
    new_cluster:
      spark_version: "15.4.x-scala2.12"
      node_type_id: "i3.xlarge"
      num_workers: 2
      spark_conf:
        spark.speculation: "true"

tasks:
  - task_key: my_task
    job_cluster_key: shared_cluster
    notebook_task:
      notebook_path: ../src/notebook.py
```

### Autoscaling Clusters

```yaml
new_cluster:
  spark_version: "15.4.x-scala2.12"
  node_type_id: "i3.xlarge"
  autoscale:
    min_workers: 2
    max_workers: 8
```

### Existing Cluster

```yaml
tasks:
  - task_key: my_task
    existing_cluster_id: "0123-456789-abcdef12"
    notebook_task:
      notebook_path: ../src/notebook.py
```

### Serverless Compute

For notebook and Python tasks, omit cluster configuration to use serverless:

```yaml
tasks:
  - task_key: serverless_task
    notebook_task:
      notebook_path: ../src/notebook.py
    # No cluster config = serverless
```

## Job Parameters

### Define Parameters

```yaml
parameters:
  - name: env
    default: "dev"
  - name: date
    default: "{{start_date}}"  # Dynamic value reference
```

### Access in Notebook

```python
# In notebook
dbutils.widgets.get("env")
dbutils.widgets.get("date")
```

### Pass to Tasks

```yaml
tasks:
  - task_key: my_task
    notebook_task:
      notebook_path: ../src/notebook.py
      base_parameters:
        env: "{{job.parameters.env}}"
        custom_param: "value"
```

## Common Operations

### Python SDK Operations

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# List jobs
jobs = w.jobs.list()

# Get job details
job = w.jobs.get(job_id=12345)

# Run job now
run = w.jobs.run_now(job_id=12345)

# Run with parameters
run = w.jobs.run_now(
    job_id=12345,
    job_parameters={"env": "prod", "date": "2024-01-15"}
)

# Cancel run
w.jobs.cancel_run(run_id=run.run_id)

# Delete job
w.jobs.delete(job_id=12345)
```

### CLI Operations

```bash
# List jobs
databricks jobs list

# Get job details
databricks jobs get 12345

# Run job
databricks jobs run-now 12345

# Run with parameters (must use --json with job_id inside)
databricks jobs run-now --json '{"job_id": 12345, "job_parameters": {"env": "prod"}}'

# Cancel run
databricks jobs cancel-run 67890

# Delete job
databricks jobs delete 12345
```

### One-time Runs (`jobs submit`) — async pattern for notebooks

For ad-hoc work (ML training, deploys, demos) where you don't need a persisted job in the UI, `jobs submit` queues a one-shot run on serverless. Returns `{"run_id": N}` immediately with `--no-wait`; you poll yourself.

```bash
# 1. Submit (returns {"run_id": N} immediately with --no-wait)
RUN_ID=$(databricks jobs submit --no-wait --json '{
  "run_name": "train-and-deploy",
  "tasks": [{
    "task_key": "train",
    "notebook_task": {"notebook_path": "/Workspace/Users/me@example.com/proj/train"},
    "environment_key": "ml_env"
  }],
  "environments": [{
    "environment_key": "ml_env",
    "spec": {
      "client": "4",
      "dependencies": ["mlflow==2.22.0", "xgboost==2.1.3", "optuna==4.1.0"]
    }
  }]
}' | jq -r .run_id)

# 2. Poll until a terminal life_cycle_state. Bounded — size iterations to workload
#    (90 × 30s = 45min for ML training; bump for longer ETL).
#    Terminal states (per SDK): TERMINATED, SKIPPED, INTERNAL_ERROR.
#    Non-terminal: QUEUED, PENDING, RUNNING, TERMINATING, BLOCKED, WAITING_FOR_RETRY.
for _ in $(seq 90); do
  STATE=$(databricks jobs get-run "$RUN_ID" | jq -r '.state.life_cycle_state // "UNKNOWN"')
  echo "$(date +%H:%M:%S) $STATE"
  [[ "$STATE" =~ ^(TERMINATED|SKIPPED|INTERNAL_ERROR)$ ]] && break
  sleep 30
done
[[ "$STATE" =~ ^(TERMINATED|SKIPPED|INTERNAL_ERROR)$ ]] || { databricks jobs cancel-run "$RUN_ID"; exit 1; }

# life_cycle_state TERMINATED only means "the run ended". Check result_state for
# success: SUCCESS / FAILED / TIMEDOUT / CANCELED / SUCCESS_WITH_FAILURES / …
RESULT=$(databricks jobs get-run "$RUN_ID" | jq -r '.state.result_state // "UNKNOWN"')
echo "result_state=$RESULT"
[[ "$RESULT" == "SUCCESS" ]] || { echo "Run did not succeed"; exit 1; }

# 3. Pull notebook output — pass the TASK run_id, NOT the submit run_id.
TASK_RUN_ID=$(databricks jobs get-run "$RUN_ID" | jq -r '.tasks[0].run_id')
databricks jobs get-run-output "$TASK_RUN_ID" | jq '.notebook_output.result'
```

**Four traps specific to `jobs submit`:**

1. **`get-run-output` takes the TASK run_id, not the submit-level run_id.** They're different IDs — both are integers, both look the same in CLI output. The top-level `run_id` returned by `jobs submit` is for `get-run` (state polling); extract `.tasks[0].run_id` from that response and use it for `get-run-output`. Passing the submit-level id returns an empty/incorrect payload without a helpful error.
2. **`spec.client: "4"`** is required for `environments[].spec.dependencies` to actually install on serverless. `"1"` silently ignores the list, the notebook runs without your deps, and import errors surface mid-run. Keep a `%pip install ...` cell at the top of the notebook as a backstop.
3. **`print()` is unreliable on serverless.** End the notebook with `dbutils.notebook.exit(json.dumps({...}))` so the structured result reaches `.notebook_output.result`. Anything `print`ed may not make it back.
4. **`jobs submit` does NOT accept top-level `tags`** (warns `unknown field: tags`). Submitted runs are ephemeral and don't persist as jobs, so tagging is meaningless. If you need tagged tracking for cleanup, use `jobs create` (which accepts `"tags": {"key": "value"}`) + `jobs run-now` instead.

### Asset Bundle Operations

```bash
# Validate configuration
databricks bundle validate

# Deploy job
databricks bundle deploy

# Run job
databricks bundle run my_job_resource_key

# Deploy to specific target
databricks bundle deploy -t prod

# Destroy resources
databricks bundle destroy
```

## Permissions (DABs)

```yaml
resources:
  jobs:
    my_job:
      name: "My Job"
      permissions:
        - level: CAN_VIEW
          group_name: "data-analysts"
        - level: CAN_MANAGE_RUN
          group_name: "data-engineers"
        - level: CAN_MANAGE
          user_name: "admin@example.com"
```

**Permission levels:**
- `CAN_VIEW` - View job and run history
- `CAN_MANAGE_RUN` - View, trigger, and cancel runs
- `CAN_MANAGE` - Full control including edit and delete

## Common Issues

| Issue | Solution |
|-------|----------|
| Job cluster startup slow | Use job clusters with `job_cluster_key` for reuse across tasks |
| Task dependencies not working | Verify `task_key` references match exactly in `depends_on` |
| Schedule not triggering | Check `pause_status: UNPAUSED` and valid timezone |
| File arrival not detecting | Ensure path has proper permissions and uses cloud storage URL |
| Table update trigger missing events | Verify Unity Catalog table and proper grants |
| Parameter not accessible | Use `dbutils.widgets.get()` in notebooks |
| "admins" group error | Cannot modify admins permissions on jobs |
| Serverless task fails | Ensure task type supports serverless (notebook, Python) |

## Related Skills

- **[databricks-bundles](../databricks-bundles/SKILL.md)** - Deploy jobs via Databricks Asset Bundles
- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** - Configure pipelines triggered by jobs

## Resources

- [Jobs API Reference](https://docs.databricks.com/api/workspace/jobs)
- [Jobs Documentation](https://docs.databricks.com/en/jobs/index.html)
- [DABs Job Task Types](https://docs.databricks.com/en/dev-tools/bundles/job-task-types.html)
- [Bundle Examples Repository](https://github.com/databricks/bundle-examples)

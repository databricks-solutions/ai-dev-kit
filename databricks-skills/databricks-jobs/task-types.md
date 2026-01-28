# Task Types Reference

## Contents
- [Notebook Task](#notebook-task)
- [Spark Python Task](#spark-python-task)
- [Python Wheel Task](#python-wheel-task)
- [SQL Task](#sql-task)
- [dbt Task](#dbt-task)
- [Pipeline Task](#pipeline-task)
- [Spark JAR Task](#spark-jar-task)
- [Run Job Task](#run-job-task)
- [For Each Task](#for-each-task)

---

## Notebook Task

Run Databricks notebooks. Most common task type.

### Python SDK

```python
from databricks.sdk.service.jobs import Task, NotebookTask, Source

Task(
    task_key="run_notebook",
    notebook_task=NotebookTask(
        notebook_path="/Workspace/Users/user@example.com/etl_notebook",
        source=Source.WORKSPACE,
        base_parameters={
            "env": "prod",
            "date": "2024-01-15"
        }
    )
)
```

### DABs YAML

```yaml
tasks:
  - task_key: run_notebook
    notebook_task:
      notebook_path: ../src/notebooks/etl_notebook.py
      source: WORKSPACE
      base_parameters:
        env: "{{job.parameters.env}}"
        date: "{{job.parameters.date}}"
```

### CLI JSON

```json
{
  "task_key": "run_notebook",
  "notebook_task": {
    "notebook_path": "/Workspace/Users/user@example.com/etl_notebook",
    "source": "WORKSPACE",
    "base_parameters": {
      "env": "prod",
      "date": "2024-01-15"
    }
  }
}
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `notebook_path` | Yes | Absolute path to notebook |
| `source` | No | `WORKSPACE` (default) or `GIT` |
| `base_parameters` | No | Key-value parameters passed to notebook |
| `warehouse_id` | No | SQL warehouse for SQL cells (optional) |

### Access Parameters in Notebook

```python
# Get parameter with default
env = dbutils.widgets.get("env")

# Or define widget first
dbutils.widgets.text("env", "dev")
env = dbutils.widgets.get("env")
```

---

## Spark Python Task

Run Python files directly on Spark cluster.

### Python SDK

```python
from databricks.sdk.service.jobs import Task, SparkPythonTask

Task(
    task_key="run_python",
    spark_python_task=SparkPythonTask(
        python_file="/Workspace/Users/user@example.com/scripts/process.py",
        parameters=["--env", "prod", "--date", "2024-01-15"]
    )
)
```

### DABs YAML

```yaml
tasks:
  - task_key: run_python
    spark_python_task:
      python_file: ../src/scripts/process.py
      parameters:
        - "--env"
        - "prod"
        - "--date"
        - "2024-01-15"
```

### CLI JSON

```json
{
  "task_key": "run_python",
  "spark_python_task": {
    "python_file": "/Workspace/Users/user@example.com/scripts/process.py",
    "parameters": ["--env", "prod", "--date", "2024-01-15"]
  }
}
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `python_file` | Yes | Path to Python file (workspace, DBFS, or Unity Catalog volume) |
| `parameters` | No | Command-line arguments passed to script |
| `source` | No | `WORKSPACE` (default) or `GIT` |

---

## Python Wheel Task

Run Python packages distributed as wheels.

### Python SDK

```python
from databricks.sdk.service.jobs import Task, PythonWheelTask

Task(
    task_key="run_wheel",
    python_wheel_task=PythonWheelTask(
        package_name="my_package",
        entry_point="main",
        parameters=["--env", "prod"]
    ),
    libraries=[
        {"whl": "/Volumes/catalog/schema/libs/my_package-1.0.0-py3-none-any.whl"}
    ]
)
```

### DABs YAML

```yaml
tasks:
  - task_key: run_wheel
    python_wheel_task:
      package_name: my_package
      entry_point: main
      parameters:
        - "--env"
        - "prod"
    libraries:
      - whl: /Volumes/catalog/schema/libs/my_package-1.0.0-py3-none-any.whl
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `package_name` | Yes | Name of the Python package |
| `entry_point` | Yes | Entry point function or module |
| `parameters` | No | Command-line arguments |
| `named_parameters` | No | Named parameters as key-value pairs |

### Entry Point Configuration

In your package's `setup.py` or `pyproject.toml`:

```python
# setup.py
entry_points={
    'console_scripts': [
        'main=my_package.main:run',
    ],
}
```

---

## SQL Task

Run SQL queries, files, or refresh dashboards/alerts.

### Run SQL Query

```yaml
tasks:
  - task_key: run_query
    sql_task:
      query:
        query_id: "abc123-def456"  # Existing query ID
      warehouse_id: "1234567890abcdef"
```

### Run SQL File

```yaml
tasks:
  - task_key: run_sql_file
    sql_task:
      file:
        path: ../src/sql/transform.sql
        source: WORKSPACE
      warehouse_id: "1234567890abcdef"
```

### Refresh Dashboard

```yaml
tasks:
  - task_key: refresh_dashboard
    sql_task:
      dashboard:
        dashboard_id: "dashboard-uuid"
      warehouse_id: "1234567890abcdef"
```

### Refresh Alert

```yaml
tasks:
  - task_key: refresh_alert
    sql_task:
      alert:
        alert_id: "alert-uuid"
      warehouse_id: "1234567890abcdef"
```

### Python SDK

```python
from databricks.sdk.service.jobs import Task, SqlTask, SqlTaskFile

Task(
    task_key="run_sql",
    sql_task=SqlTask(
        warehouse_id="1234567890abcdef",
        file=SqlTaskFile(
            path="/Workspace/Users/user@example.com/queries/transform.sql",
            source=Source.WORKSPACE
        )
    )
)
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `warehouse_id` | Yes | SQL warehouse ID |
| `query` | One of | Run existing query by ID |
| `file` | One of | Run SQL file |
| `dashboard` | One of | Refresh dashboard |
| `alert` | One of | Refresh alert |
| `parameters` | No | Query parameters |

---

## dbt Task

Run dbt projects with Databricks.

### DABs YAML

```yaml
tasks:
  - task_key: run_dbt
    dbt_task:
      project_directory: ../src/dbt_project
      commands:
        - "dbt deps"
        - "dbt seed"
        - "dbt run --select tag:daily"
        - "dbt test"
      warehouse_id: "1234567890abcdef"
      catalog: "main"
      schema: "analytics"
```

### Python SDK

```python
from databricks.sdk.service.jobs import Task, DbtTask

Task(
    task_key="run_dbt",
    dbt_task=DbtTask(
        project_directory="/Workspace/Users/user@example.com/dbt_project",
        commands=["dbt deps", "dbt run", "dbt test"],
        warehouse_id="1234567890abcdef",
        catalog="main",
        schema="analytics"
    )
)
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `project_directory` | Yes | Path to dbt project |
| `commands` | Yes | List of dbt commands to run |
| `warehouse_id` | No | SQL warehouse (required if not using cluster) |
| `catalog` | No | Unity Catalog catalog |
| `schema` | No | Target schema |
| `profiles_directory` | No | Path to profiles.yml directory |
| `source` | No | `WORKSPACE` (default) or `GIT` |

---

## Pipeline Task

Trigger DLT or Spark Declarative Pipelines.

### DABs YAML

```yaml
tasks:
  - task_key: run_pipeline
    pipeline_task:
      pipeline_id: "pipeline-uuid-here"
      full_refresh: false
```

### With Pipeline Resource Reference (DABs)

```yaml
resources:
  pipelines:
    my_pipeline:
      name: "My Data Pipeline"
      # ... pipeline config

  jobs:
    my_job:
      name: "Orchestrate Pipeline"
      tasks:
        - task_key: run_pipeline
          pipeline_task:
            pipeline_id: ${resources.pipelines.my_pipeline.id}
```

### Python SDK

```python
from databricks.sdk.service.jobs import Task, PipelineTask

Task(
    task_key="run_pipeline",
    pipeline_task=PipelineTask(
        pipeline_id="pipeline-uuid-here",
        full_refresh=False
    )
)
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `pipeline_id` | Yes | ID of the pipeline to trigger |
| `full_refresh` | No | Force full refresh (default: false) |

---

## Spark JAR Task

Run Scala/Java JAR files on Spark.

### DABs YAML

```yaml
tasks:
  - task_key: run_jar
    spark_jar_task:
      main_class_name: "com.example.Main"
      parameters:
        - "--env"
        - "prod"
    libraries:
      - jar: /Volumes/catalog/schema/libs/my-app.jar
```

### Python SDK

```python
from databricks.sdk.service.jobs import Task, SparkJarTask

Task(
    task_key="run_jar",
    spark_jar_task=SparkJarTask(
        main_class_name="com.example.Main",
        parameters=["--env", "prod"]
    ),
    libraries=[
        {"jar": "/Volumes/catalog/schema/libs/my-app.jar"}
    ]
)
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `main_class_name` | Yes | Main class to execute |
| `parameters` | No | Command-line arguments |

---

## Run Job Task

Trigger another job as a task (job chaining).

### DABs YAML

```yaml
tasks:
  - task_key: trigger_downstream
    run_job_task:
      job_id: 12345
      job_parameters:
        source_table: "catalog.schema.table"
```

### With Job Resource Reference (DABs)

```yaml
resources:
  jobs:
    upstream_job:
      name: "Upstream Job"
      tasks:
        - task_key: process
          notebook_task:
            notebook_path: ../src/process.py

    downstream_job:
      name: "Downstream Job"
      tasks:
        - task_key: trigger_upstream
          run_job_task:
            job_id: ${resources.jobs.upstream_job.id}
```

### Python SDK

```python
from databricks.sdk.service.jobs import Task, RunJobTask

Task(
    task_key="trigger_downstream",
    run_job_task=RunJobTask(
        job_id=12345,
        job_parameters={"source_table": "catalog.schema.table"}
    )
)
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `job_id` | Yes | ID of job to trigger |
| `job_parameters` | No | Parameters to pass to triggered job |

---

## For Each Task

Loop over a collection and run a nested task for each item.

### DABs YAML - Static Inputs

```yaml
tasks:
  - task_key: process_regions
    for_each_task:
      inputs: '["us-east", "us-west", "eu-west"]'
      task:
        task_key: process_region
        notebook_task:
          notebook_path: ../src/process_region.py
          base_parameters:
            region: "{{input}}"
```

### DABs YAML - Dynamic Inputs from Previous Task

```yaml
tasks:
  - task_key: generate_list
    notebook_task:
      notebook_path: ../src/generate_countries.py

  - task_key: process_countries
    depends_on:
      - task_key: generate_list
    for_each_task:
      inputs: "{{tasks.generate_list.values.countries}}"
      task:
        task_key: process_country
        notebook_task:
          notebook_path: ../src/process_country.py
          base_parameters:
            country: "{{input}}"
```

### Generate Dynamic Inputs

In the generating notebook, return values using task values:

```python
# generate_countries.py notebook
countries = ["USA", "UK", "Germany", "France"]

# Set task value for downstream for_each_task
dbutils.jobs.taskValues.set(key="countries", value=countries)
```

### Python SDK

```python
from databricks.sdk.service.jobs import Task, ForEachTask, NotebookTask

Task(
    task_key="process_regions",
    for_each_task=ForEachTask(
        inputs='["us-east", "us-west", "eu-west"]',
        task=Task(
            task_key="process_region",
            notebook_task=NotebookTask(
                notebook_path="/Workspace/process_region",
                base_parameters={"region": "{{input}}"}
            )
        )
    )
)
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `inputs` | Yes | JSON array string or task value reference |
| `task` | Yes | Nested task to run for each input |
| `concurrency` | No | Max parallel iterations (default: 20) |

### Access Current Item

Inside the nested task, access the current item:
- In parameters: `{{input}}`
- In notebook: Use the parameter passed via `base_parameters`

---

## Task Libraries

Add libraries to tasks for dependencies.

### DABs YAML

```yaml
tasks:
  - task_key: with_libraries
    notebook_task:
      notebook_path: ../src/notebook.py
    libraries:
      - pypi:
          package: pandas==2.0.0
      - pypi:
          package: scikit-learn
      - whl: /Volumes/catalog/schema/libs/custom-1.0.0-py3-none-any.whl
      - jar: /Volumes/catalog/schema/libs/custom.jar
      - maven:
          coordinates: "org.apache.spark:spark-avro_2.12:3.5.0"
```

### Library Types

| Type | Format | Example |
|------|--------|---------|
| PyPI | `pypi.package` | `pandas==2.0.0` |
| Wheel | `whl` | Path to .whl file |
| JAR | `jar` | Path to .jar file |
| Maven | `maven.coordinates` | `group:artifact:version` |
| Egg | `egg` | Path to .egg file |

---

## Environments

Define reusable Python environments for serverless tasks with custom pip dependencies.

> **IMPORTANT:** The `client` field is **required** in the environment `spec`. It specifies the
> base serverless environment version. Use `"4"` as the value. Without it, the API returns:
> `"Either base environment or version must be provided for environment"`.
> The MCP `create_job` tool auto-injects `client: "4"` if omitted, but CLI/SDK calls require it explicitly.

### DABs YAML

```yaml
environments:
  - environment_key: ml_env
    spec:
      client: "4"
      dependencies:
        - pandas==2.0.0
        - scikit-learn==1.3.0
        - mlflow

tasks:
  - task_key: ml_task
    environment_key: ml_env
    notebook_task:
      notebook_path: ../src/train_model.py
```

### CLI JSON

```json
{
  "environments": [
    {
      "environment_key": "ml_env",
      "spec": {
        "client": "4",
        "dependencies": ["pandas==2.0.0", "scikit-learn==1.3.0"]
      }
    }
  ]
}
```

### Python SDK

```python
from databricks.sdk.service.jobs import JobEnvironment
from databricks.sdk.service.compute import Environment

environments = [
    JobEnvironment(
        environment_key="ml_env",
        spec=Environment(
            client="4",
            dependencies=["pandas==2.0.0", "scikit-learn==1.3.0"]
        )
    )
]
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `environment_key` | Yes | Unique identifier referenced by tasks via `environment_key` |
| `spec.client` | Yes | Base serverless environment version (use `"4"`) |
| `spec.dependencies` | No | List of pip packages (e.g., `["pandas==2.0.0", "dbldatagen"]`) |

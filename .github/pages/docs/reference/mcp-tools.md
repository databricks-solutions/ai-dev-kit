# MCP Tools

The MCP server exposes 50+ tools that let your AI assistant **execute actions** against your Databricks workspace. These are the functions it calls when you ask it to run SQL, create a dashboard, or deploy a job.

---

## SQL

| Tool | What it does |
|------|-------------|
| `execute_sql` | Run a SQL query, return results |
| `execute_sql_multi` | Run multiple queries in parallel |
| `list_warehouses` | List available SQL warehouses |
| `get_table_details` | Get table schemas for a catalog/schema |
| `get_best_warehouse` | Auto-select the best available warehouse |

## Compute

| Tool | What it does |
|------|-------------|
| `list_clusters` | List all clusters |
| `execute_databricks_command` | Run code on a cluster |
| `run_python_file_on_databricks` | Upload and execute a Python file |

## Files

| Tool | What it does |
|------|-------------|
| `upload_file` | Upload a file to a UC volume or workspace |
| `upload_folder` | Upload an entire folder |

## Jobs & Workflows

| Tool | What it does |
|------|-------------|
| `create_job` | Create a new job |
| `run_job_now` | Trigger a job run |
| `get_job` | Get job details |
| `list_jobs` | List all jobs |
| `wait_for_run` | Wait for a run to complete |
| `get_run` | Get run status and results |

## Pipelines (SDP/DLT)

| Tool | What it does |
|------|-------------|
| `create_or_update_pipeline` | Create or update a pipeline |
| `run_pipeline` | Trigger a pipeline update |
| `get_pipeline` | Get pipeline status |

## AI/BI Dashboards

| Tool | What it does |
|------|-------------|
| `create_or_update_dashboard` | Deploy a dashboard |
| `get_dashboard` | Get details or list all dashboards |
| `publish_dashboard` | Publish or unpublish |
| `delete_dashboard` | Move to trash |

## AI Agents

| Tool | What it does |
|------|-------------|
| `manage_ka` | Create/manage Knowledge Assistants |
| `manage_mas` | Create/manage Supervisor Agents |
| `create_or_update_genie` | Create/manage Genie Spaces |
| `find_genie_by_name` | Find a Genie Space by name |

## Model Serving

| Tool | What it does |
|------|-------------|
| `query_serving_endpoint` | Query a model serving endpoint |
| `get_serving_endpoint_status` | Check endpoint status |

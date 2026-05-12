# Databricks MCP Tool Catalog

## SQL Operations
| Tool | Use For |
|------|---------|
| `mcp__databricks__execute_sql` | Execute any SQL statement (DDL, DML, queries) |

## File & Volume Operations
| Tool | Use For |
|------|---------|
| `mcp__databricks__upload_to_volume` | Upload files/folders to volumes (handles files, folders, globs) |
| `mcp__databricks__download_from_volume` | Download files from volumes |
| `mcp__databricks__delete_from_volume` | Delete files/folders from volumes (supports recursive) |
| `mcp__databricks__list_volume_files` | List files in a volume path |

## Workspace Operations
| Tool | Use For |
|------|---------|
| `mcp__databricks__upload_to_workspace` | Upload files/folders to workspace (handles files, folders, globs) |
| `mcp__databricks__delete_from_workspace` | Delete files/folders from workspace (with safety checks) |
| `mcp__databricks__workspace_get_object` | Read notebooks/files from workspace |
| `mcp__databricks__workspace_list` | List workspace directory contents |

## Compute
| Tool | Use For |
|------|---------|
| `mcp__databricks__create_cluster` | Create a new cluster |
| `mcp__databricks__get_cluster` | Get cluster status/details |
| `mcp__databricks__list_clusters` | List available clusters |

## Jobs
| Tool | Use For |
|------|---------|
| `mcp__databricks__create_job` | Create a new job |
| `mcp__databricks__run_job` | Trigger a job run |
| `mcp__databricks__get_run` | Check job run status |
| `mcp__databricks__list_jobs` | List existing jobs |

## Model Serving
| Tool | Use For |
|------|---------|
| `mcp__databricks__query_serving_endpoint` | Query a model serving endpoint |
| `mcp__databricks__list_serving_endpoints` | List available endpoints |

## Unity Catalog
| Tool | Use For |
|------|---------|
| `mcp__databricks__list_catalogs` | List catalogs |
| `mcp__databricks__list_schemas` | List schemas in a catalog |
| `mcp__databricks__list_tables` | List tables in a schema |

## When Bash IS Appropriate
- Running `pip install` or `uv pip install` for package management
- Git operations (`git clone`, `git diff`, etc.)
- Local file system operations outside Databricks (temp files, etc.)
- Running local Python scripts for data processing
- Operations with no MCP tool equivalent

# Databricks Python SDK

Databricks development guidance including Python SDK, Databricks Connect, CLI, and REST API.

## Overview

This skill provides comprehensive reference material for working with the Databricks Python SDK (`databricks-sdk`), Databricks Connect, the Databricks CLI, and direct REST API access. It activates when writing code that interacts with Databricks services such as clusters, jobs, SQL warehouses, Unity Catalog, model serving, vector search, and more. The skill includes a complete API documentation index with method signatures and annotated example scripts for common operations.

## What's Included

```
databricks-python-sdk/
├── SKILL.md                              # Main skill: setup, authentication, core API reference, patterns
├── doc-index.md                          # Complete SDK method signatures mapped to documentation URLs
└── examples/
    ├── 1-authentication.py               # Authentication patterns and credential setup
    ├── 2-clusters-and-jobs.py            # Cluster management and job orchestration
    ├── 3-sql-and-warehouses.py           # SQL statement execution and warehouse management
    ├── 4-unity-catalog.py                # Catalogs, schemas, tables, and volumes
    └── 5-serving-and-vector-search.py    # Model serving endpoints and vector search indexes
```

## Key Topics

- Authentication (PAT, OAuth, Azure Service Principal, named profiles)
- Databricks Connect for running Spark code locally
- WorkspaceClient and AccountClient initialization
- Clusters API (create, start, stop, resize, permissions)
- Jobs API (create, run, monitor, repair)
- SQL statement execution and warehouse management
- Unity Catalog (catalogs, schemas, tables, volumes, files)
- Model serving endpoints and OpenAI-compatible clients
- Vector search indexes and queries
- Pipelines (Delta Live Tables) management
- Secrets management
- DBUtils access
- Direct REST API calls via `api_client.do()`
- Async usage patterns (`asyncio.to_thread` for FastAPI)
- Long-running operation wait patterns and pagination
- Error handling with typed exceptions

## When to Use

- Writing Python code that uses `databricks-sdk` or `databricks-connect`
- Managing Databricks resources programmatically (clusters, jobs, warehouses)
- Querying Unity Catalog metadata or executing SQL statements
- Integrating Databricks APIs into applications (FastAPI, scripts, notebooks)
- Setting up authentication or configuring Databricks CLI
- Looking up SDK method signatures or documentation URLs

## Related Skills

- [Databricks Config](../databricks-config/) -- profile and authentication setup
- [Asset Bundles](../asset-bundles/) -- deploying resources via DABs
- [Databricks Jobs](../databricks-jobs/) -- job orchestration patterns
- [Unity Catalog](../databricks-unity-catalog/) -- catalog governance
- [Model Serving](../model-serving/) -- serving endpoint management
- [Vector Search](../vector-search/) -- vector index operations
- [Lakebase Provisioned](../lakebase-provisioned/) -- managed PostgreSQL via SDK

## Resources

- [Databricks Python SDK Documentation](https://databricks-sdk-py.readthedocs.io/en/latest/)
- [Databricks SDK GitHub Repository](https://github.com/databricks/databricks-sdk-py)
- [Authentication Guide](https://databricks-sdk-py.readthedocs.io/en/latest/authentication.html)
- [DBUtils Documentation](https://databricks-sdk-py.readthedocs.io/en/latest/dbutils.html)

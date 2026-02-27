---
name: databricks-lakebase-provisioned
description: "Patterns and best practices for using Lakebase Provisioned (Databricks managed PostgreSQL) for OLTP workloads."
---

# Lakebase Provisioned

Patterns and best practices for using Lakebase Provisioned (Databricks managed PostgreSQL) for OLTP workloads.

## When to Use

Use this skill when:
- Building applications that need a PostgreSQL database for transactional workloads
- Adding persistent state to Databricks Apps
- Implementing reverse ETL from Delta Lake to an operational database
- Storing chat/agent memory for LangChain applications

## Overview

Lakebase Provisioned is Databricks' managed PostgreSQL database service for OLTP (Online Transaction Processing) workloads. It provides a fully managed PostgreSQL-compatible database that integrates with Unity Catalog and supports OAuth token-based authentication.

| Feature | Description |
|---------|-------------|
| **Managed PostgreSQL** | Fully managed instances with automatic provisioning |
| **OAuth Authentication** | Token-based auth via Databricks SDK (1-hour expiry) |
| **Unity Catalog** | Register databases for governance |
| **Reverse ETL** | Sync data from Delta tables to PostgreSQL |
| **Apps Integration** | First-class support in Databricks Apps |

**Available Regions (AWS):** us-east-1, us-east-2, us-west-2, eu-central-1, eu-west-1, ap-south-1, ap-southeast-1, ap-southeast-2

## Quick Start

Create and connect to a Lakebase Provisioned instance:

```python
from databricks.sdk import WorkspaceClient
import uuid

# Initialize client
w = WorkspaceClient()

# Create a database instance
instance = w.database.create_database_instance(
    name="my-lakebase-instance",
    capacity="CU_1",  # CU_1, CU_2, CU_4, CU_8
    stopped=False
)
print(f"Instance created: {instance.name}")
print(f"DNS endpoint: {instance.read_write_dns}")
```

## Common Patterns

### Generate OAuth Token

```python
from databricks.sdk import WorkspaceClient
import uuid

w = WorkspaceClient()

# Generate OAuth token for database connection
cred = w.database.generate_database_credential(
    request_id=str(uuid.uuid4()),
    instance_names=["my-lakebase-instance"]
)
token = cred.token  # Use this as password in connection string
```

### Connect from Notebook

```python
import psycopg
from databricks.sdk import WorkspaceClient
import uuid

# Get instance details
w = WorkspaceClient()
instance = w.database.get_database_instance(name="my-lakebase-instance")

# Generate token
cred = w.database.generate_database_credential(
    request_id=str(uuid.uuid4()),
    instance_names=["my-lakebase-instance"]
)

# Connect using psycopg3
conn_string = f"host={instance.read_write_dns} dbname=postgres user={w.current_user.me().user_name} password={cred.token} sslmode=require"
with psycopg.connect(conn_string) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT version()")
        print(cur.fetchone())
```

### SQLAlchemy with Token Refresh (Production)

For long-running applications, tokens must be refreshed (expire after 1 hour):

```python
import asyncio
import os
import uuid
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from databricks.sdk import WorkspaceClient

# Token refresh state
_current_token = None
_token_refresh_task = None
TOKEN_REFRESH_INTERVAL = 50 * 60  # 50 minutes (before 1-hour expiry)

def _generate_token(instance_name: str) -> str:
    """Generate fresh OAuth token."""
    w = WorkspaceClient()
    cred = w.database.generate_database_credential(
        request_id=str(uuid.uuid4()),
        instance_names=[instance_name]
    )
    return cred.token

async def _token_refresh_loop(instance_name: str):
    """Background task to refresh token every 50 minutes."""
    global _current_token
    while True:
        await asyncio.sleep(TOKEN_REFRESH_INTERVAL)
        _current_token = await asyncio.to_thread(_generate_token, instance_name)

def init_database(instance_name: str, database_name: str, username: str) -> AsyncEngine:
    """Initialize database with OAuth token injection."""
    global _current_token
    
    w = WorkspaceClient()
    instance = w.database.get_database_instance(name=instance_name)
    
    # Generate initial token
    _current_token = _generate_token(instance_name)
    
    # Build URL (password injected via do_connect)
    url = f"postgresql+psycopg://{username}@{instance.read_write_dns}:5432/{database_name}"
    
    engine = create_async_engine(
        url,
        pool_size=5,
        max_overflow=10,
        pool_recycle=3600,
        connect_args={"sslmode": "require"}
    )
    
    # Inject token on each connection
    @event.listens_for(engine.sync_engine, "do_connect")
    def provide_token(dialect, conn_rec, cargs, cparams):
        cparams["password"] = _current_token
    
    return engine
```

### Databricks Apps Integration

For Databricks Apps, use environment variables for configuration:

```python
# Environment variables set by Databricks Apps:
# - LAKEBASE_INSTANCE_NAME: Instance name
# - LAKEBASE_DATABASE_NAME: Database name
# - LAKEBASE_USERNAME: Username (optional, defaults to service principal)

import os

def is_lakebase_configured() -> bool:
    """Check if Lakebase is configured for this app."""
    return bool(
        os.environ.get("LAKEBASE_PG_URL") or
        (os.environ.get("LAKEBASE_INSTANCE_NAME") and 
         os.environ.get("LAKEBASE_DATABASE_NAME"))
    )
```

Add Lakebase as an app resource via CLI:

```bash
databricks apps add-resource $APP_NAME \
    --resource-type database \
    --resource-name lakebase \
    --database-instance my-lakebase-instance
```

### Register with Unity Catalog

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Register database in Unity Catalog
w.database.register_database_instance(
    name="my-lakebase-instance",
    catalog="my_catalog",
    schema="my_schema"
)
```

### MLflow Model Resources

Declare Lakebase as a model resource for automatic credential provisioning:

```python
from mlflow.models.resources import DatabricksLakebase

resources = [
    DatabricksLakebase(database_instance_name="my-lakebase-instance"),
]

# When logging model
mlflow.langchain.log_model(
    model,
    artifact_path="model",
    resources=resources,
    pip_requirements=["databricks-langchain[memory]"]
)
```

## MCP Tools

The following MCP tools are available for managing Lakebase infrastructure. Use `type="provisioned"` for Lakebase Provisioned.

### Database Management

| Tool | Description |
|------|-------------|
| `create_or_update_lakebase_database` | Create or update a database. Finds by name, creates if new, updates if existing. Use `type="provisioned"`, `capacity` (CU_1-CU_8), `stopped` params. |
| `get_lakebase_database` | Get database details or list all. Pass `name` to get one, omit to list all. Use `type="provisioned"` to filter. |
| `delete_lakebase_database` | Delete a database and its resources. Use `type="provisioned"`, `force=True` to cascade. |
| `generate_lakebase_credential` | Generate OAuth token for PostgreSQL connections (1-hour expiry). Pass `instance_names` for provisioned. |

### Reverse ETL (Catalog + Synced Tables)

| Tool | Description |
|------|-------------|
| `create_or_update_lakebase_sync` | Set up reverse ETL: ensures UC catalog registration exists, then creates a synced table from Delta to Lakebase. Params: `instance_name`, `source_table_name`, `target_table_name`, `scheduling_policy` ("TRIGGERED"/"SNAPSHOT"/"CONTINUOUS"). |
| `delete_lakebase_sync` | Remove a synced table and optionally its UC catalog registration. |

## Reference Files

- [connection-patterns.md](connection-patterns.md) - Detailed connection patterns for different use cases
- [reverse-etl.md](reverse-etl.md) - Syncing data from Delta Lake to Lakebase

## CLI Quick Reference

```bash
# Create instance
databricks database create-database-instance \
    --name my-lakebase-instance \
    --capacity CU_1

# Get instance details
databricks database get-database-instance --name my-lakebase-instance

# Generate credentials
databricks database generate-database-credential \
    --request-id $(uuidgen) \
    --json '{"instance_names": ["my-lakebase-instance"]}'

# List instances
databricks database list-database-instances

# Stop instance (saves cost)
databricks database stop-database-instance --name my-lakebase-instance

# Start instance
databricks database start-database-instance --name my-lakebase-instance
```

## Common Issues

| Issue | Solution |
|-------|----------|
| **Token expired during long query** | Implement token refresh loop (see SQLAlchemy with Token Refresh section); tokens expire after 1 hour |
| **DNS resolution fails on macOS** | Use `dig` command to resolve hostname, pass `hostaddr` to psycopg |
| **Connection refused** | Ensure instance is not stopped; check `instance.state` |
| **Permission denied** | User must be granted access to the Lakebase instance |
| **SSL required error** | Always use `sslmode=require` in connection string |

## SDK Version Requirements

- **Databricks SDK for Python**: >= 0.61.0 (0.81.0+ recommended for full API support)
- **psycopg**: 3.x (supports `hostaddr` parameter for DNS workaround)
- **SQLAlchemy**: 2.x with `postgresql+psycopg` driver

```python
%pip install -U "databricks-sdk>=0.81.0" "psycopg[binary]>=3.0" sqlalchemy
```

## Notes

- **Capacity values** use compute unit sizing: `CU_1`, `CU_2`, `CU_4`, `CU_8`.
- **Lakebase Autoscaling** is a newer offering with automatic scaling but limited regional availability. This skill focuses on **Lakebase Provisioned** which is more widely available.
- For memory/state in LangChain agents, use `databricks-langchain[memory]` which includes Lakebase support.
- Tokens are short-lived (1 hour) - production apps MUST implement token refresh.

## Related Skills

- **[databricks-app-apx](../databricks-app-apx/SKILL.md)** - full-stack apps that can use Lakebase for persistence
- **[databricks-app-python](../databricks-app-python/SKILL.md)** - Python apps with Lakebase backend
- **[databricks-python-sdk](../databricks-python-sdk/SKILL.md)** - SDK used for instance management and token generation
- **[databricks-asset-bundles](../databricks-asset-bundles/SKILL.md)** - deploying apps with Lakebase resources
- **[databricks-jobs](../databricks-jobs/SKILL.md)** - scheduling reverse ETL sync jobs

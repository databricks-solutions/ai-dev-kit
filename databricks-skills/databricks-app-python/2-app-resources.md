# App Resources and Communication Strategies

Databricks Apps integrate with platform resources via managed connections. Use resources instead of hardcoding IDs for portability and security.

**Docs**: https://docs.databricks.com/aws/en/dev-tools/databricks-apps/resources

---

## Supported Resource Types

| Resource | Default Key | Permissions | Use Case |
|----------|-------------|-------------|----------|
| SQL warehouse | `sql-warehouse` | Can use, Can manage | Querying Delta tables |
| Lakebase database | `database` | Can connect and create | Low-latency transactional data |
| Model serving endpoint | `serving-endpoint` | Can view, Can query, Can manage | AI/ML inference |
| Secret | `secret` | Can read, Can write, Can manage | API keys, tokens |
| Unity Catalog volume | `volume` | Can read, Can read and write | File storage |
| Vector search index | `vector-search-index` | Can select | Semantic search |
| Genie space | `genie-space` | Can view, Can run, Can edit | Natural language analytics |
| UC connection | `connection` | Use Connection | External data sources |
| UC function | `function` | Can execute | SQL/Python functions |
| MLflow experiment | `experiment` | Can read, Can edit | ML experiment tracking |
| Lakeflow job | `job` | Can view, Can manage run | Data pipelines |

---

## Configuring Resources in app.yaml

Use `valueFrom` to reference resources — never hardcode IDs:

```yaml
env:
  - name: DATABRICKS_WAREHOUSE_ID
    valueFrom: sql-warehouse

  - name: SERVING_ENDPOINT_NAME
    valueFrom: serving-endpoint

  - name: DB_CONNECTION_STRING
    valueFrom: database
```

Add resources via the Databricks Apps UI when creating or editing an app:
1. Navigate to Configure step
2. Click **+ Add resource**
3. Select resource type and set permissions
4. Assign a key (referenced in `valueFrom`)

---

## Communication Strategies

Choose your data backend based on access pattern:

| Strategy | When to Use | Library | Connection Pattern |
|----------|-------------|---------|-------------------|
| **SQL Warehouse** | Analytical queries on Delta tables | `databricks-sql-connector` | `sql.connect()` with `Config()` |
| **Lakebase (PostgreSQL)** | Low-latency transactional CRUD | `psycopg2` / `asyncpg` | Standard PostgreSQL via auto-injected env vars |
| **Databricks SDK** | Platform API calls (jobs, clusters, UC) | `databricks-sdk` | `WorkspaceClient()` |
| **Model Serving** | AI/ML inference requests | `requests` or SDK | REST call to serving endpoint |
| **Unity Catalog Functions** | Server-side compute (SQL/Python UDFs) | `databricks-sql-connector` | Execute via SQL warehouse |

### SQL Warehouse Pattern

```python
import os
from databricks.sdk.core import Config
from databricks import sql

cfg = Config()
conn = sql.connect(
    server_hostname=cfg.host,
    http_path=f"/sql/1.0/warehouses/{os.getenv('DATABRICKS_WAREHOUSE_ID')}",
    credentials_provider=lambda: cfg.authenticate,
)

with conn.cursor() as cursor:
    cursor.execute("SELECT * FROM catalog.schema.table LIMIT 100")
    rows = cursor.fetchall()
```

### Model Serving Pattern

```python
import os, requests
from databricks.sdk.core import Config

cfg = Config()
headers = cfg.authenticate()
headers["Content-Type"] = "application/json"

endpoint = os.getenv("SERVING_ENDPOINT_NAME")
response = requests.post(
    f"https://{cfg.host}/serving-endpoints/{endpoint}/invocations",
    headers=headers,
    json={"inputs": [{"prompt": "Hello"}]},
)
result = response.json()
```

### SDK Pattern

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()  # Auto-detects credentials
for cluster in w.clusters.list():
    print(f"{cluster.cluster_name}: {cluster.state}")
```

For Lakebase patterns, see [5-lakebase.md](5-lakebase.md).

---

## Best Practices

- Always use `valueFrom` — keeps apps portable between environments
- Grant service principal minimum required permissions (e.g., `CAN USE` not `CAN MANAGE` for SQL warehouse)
- Use Lakebase for transactional workloads; SQL warehouse for analytical workloads
- For external services, use UC connections or secrets (never hardcode API keys)

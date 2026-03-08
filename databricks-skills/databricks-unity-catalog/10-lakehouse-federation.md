# Lakehouse Federation

Comprehensive reference for Lakehouse Federation: create foreign connections to external databases (Snowflake, PostgreSQL, MySQL, SQL Server, BigQuery) and query them through Unity Catalog without moving data.

## Overview

Lakehouse Federation lets you query data in external database systems directly from Databricks, using Unity Catalog as the governance layer. You create a **connection** (credentials + endpoint), then a **foreign catalog** that mirrors the external database's schema structure into Unity Catalog.

| Component | Description |
|-----------|-------------|
| **Connection** | Stores credentials and endpoint info for an external database |
| **Foreign Catalog** | A Unity Catalog catalog backed by a connection; mirrors external schemas/tables |
| **Supported Types** | `SNOWFLAKE`, `POSTGRESQL`, `MYSQL`, `SQLSERVER`, `BIGQUERY` |

### How It Works

1. Create a connection with credentials for the external system
2. Create a foreign catalog that uses the connection
3. Query external tables using standard SQL: `SELECT * FROM foreign_catalog.schema.table`
4. Unity Catalog enforces access controls on the foreign catalog like any other catalog

### Requirements

- Unity Catalog enabled workspace
- `CREATE CONNECTION` privilege (for connections)
- `CREATE CATALOG` privilege (for foreign catalogs)
- Network connectivity from Databricks to the external database
- SQL warehouse for foreign catalog creation and queries

---

## MCP Tool Reference: `manage_uc_connections`

Use the `manage_uc_connections` tool for all connection and foreign catalog operations.

| Action | Description | Required Params |
|--------|-------------|-----------------|
| `list` | List all connections | _(none)_ |
| `create` | Create a foreign connection | `name`, `connection_type`, `options` |
| `get` | Get connection details | `name` |
| `update` | Update a connection | `name`, `options` (always required), plus optional: `comment`, `owner`, `new_name` |
| `delete` | Delete a connection | `name` |
| `create_foreign_catalog` | Create a foreign catalog | `connection_name`, `catalog_name`; optional: `catalog_options`, `warehouse_id` |

---

### List Connections

```python
manage_uc_connections(action="list")
```

**Verified response shape:**

```json
{
  "items": [
    {
      "name": "my_pg_connection",
      "connection_id": "bd7f8267-2318-48f8-b6dc-ca8d156a0bb0",
      "connection_type": "POSTGRESQL",
      "comment": "Production PostgreSQL",
      "credential_type": "USERNAME_PASSWORD",
      "full_name": "my_pg_connection",
      "metastore_id": "616f89c2-6a5b-4106-9253-2e6f81df10e4",
      "options": {"host": "pg.example.com", "port": "5432"},
      "owner": "user@example.com",
      "provisioning_info": {"state": "ACTIVE"},
      "read_only": true,
      "securable_type": "CONNECTION",
      "created_at": 1772936429402,
      "created_by": "user@example.com",
      "updated_at": 1772936429402,
      "updated_by": "user@example.com",
      "url": "jdbc://pg.example.com:5432/"
    }
  ]
}
```

> **Note:** The top-level key is `items` (not `connections`). Passwords and secrets are never returned in the `options` field.

---

### Create a Connection

```python
manage_uc_connections(
    action="create",
    name="my_pg_connection",
    connection_type="POSTGRESQL",
    options={
        "host": "pg.example.com",
        "port": "5432",
        "user": "readonly_user",
        "password": "secret"
    },
    comment="PostgreSQL analytics database"
)
```

**Verified response shape:**

```json
{
  "name": "my_pg_connection",
  "connection_id": "bd7f8267-2318-48f8-b6dc-ca8d156a0bb0",
  "connection_type": "POSTGRESQL",
  "comment": "PostgreSQL analytics database",
  "credential_type": "USERNAME_PASSWORD",
  "full_name": "my_pg_connection",
  "metastore_id": "616f89c2-6a5b-4106-9253-2e6f81df10e4",
  "options": {"host": "pg.example.com", "port": "5432"},
  "owner": "user@example.com",
  "provisioning_info": {"state": "ACTIVE"},
  "read_only": true,
  "securable_type": "CONNECTION",
  "created_at": 1772936429402,
  "created_by": "user@example.com",
  "updated_at": 1772936429402,
  "updated_by": "user@example.com",
  "url": "jdbc://pg.example.com:5432/"
}
```

> **Note:** The `options` in the response omit sensitive fields (`password`, `user`). Only non-secret options (e.g., `host`, `port`) are returned.

---

### Get Connection Details

```python
manage_uc_connections(action="get", name="my_pg_connection")
```

**Response shape:** Identical to the create response (single connection object).

---

### Update a Connection

> **Important:** The `options` parameter is **always required** for update, even when only changing the comment, owner, or name. You must pass the full options dict including credentials.

```python
# Update host + rename (options always required)
manage_uc_connections(
    action="update",
    name="my_pg_connection",
    options={
        "host": "pg-new.example.com",
        "port": "5432",
        "user": "readonly_user",
        "password": "secret"
    },
    new_name="pg_analytics_readonly"
)
```

**Verified response shape:** Same as create response. The `name` and `full_name` fields reflect the new name if renamed. The `options` field reflects updated non-secret values. The `updated_at` timestamp changes.

> **Known behavior:** The `comment` field in the update response may show the previous value. The `options` (host, port, etc.) update correctly. Use `get` after update if you need to verify the comment.

---

### Delete a Connection

```python
manage_uc_connections(action="delete", name="my_pg_connection")
```

**Verified response shape:**

```json
{
  "status": "deleted",
  "connection": "my_pg_connection"
}
```

---

### Create a Foreign Catalog

The tool executes SQL: `CREATE FOREIGN CATALOG <catalog_name> USING CONNECTION <connection_name> OPTIONS (...)`.

```python
manage_uc_connections(
    action="create_foreign_catalog",
    connection_name="my_pg_connection",
    catalog_name="pg_analytics",
    catalog_options={"database": "analytics"},
    warehouse_id="abc123def456"
)
```

`warehouse_id` is optional — if omitted, the tool uses the default SQL warehouse. `catalog_options` is also optional but typically needed to specify which database to mirror.

**Common errors (verified):**

| Error Message | Cause |
|---------------|-------|
| `<id> is not a valid endpoint id` | Invalid `warehouse_id` — warehouse validation happens first |
| `CONNECTION_NOT_FOUND: Cannot execute this command because the connection name <name> was not found` | Connection doesn't exist |
| `PERMISSION_DENIED: User does not have CREATE CATALOG on Metastore '<name>'` | Missing `CREATE CATALOG` privilege |

> **Note:** Foreign catalog creation requires a running SQL warehouse, valid connection credentials, and network reachability to the external database. Could not verify the success response shape due to permission constraints, but the generated SQL is: `CREATE FOREIGN CATALOG <name> USING CONNECTION <conn> OPTIONS ('database' = '<db>')`.

---

## Connection Type Options (Verified)

Each connection type supports specific options. Passing an unsupported option returns an error listing all valid keys.

### PostgreSQL (`POSTGRESQL`)

| Option | Required | Description |
|--------|----------|-------------|
| `host` | Yes | Hostname or IP |
| `port` | Yes | Port (typically `5432`) |
| `user` | Yes | Username |
| `password` | Yes | Password |
| `trustServerCertificate` | No | Trust self-signed certs |

```python
manage_uc_connections(
    action="create",
    name="pg_production",
    connection_type="POSTGRESQL",
    options={
        "host": "pg.example.com",
        "port": "5432",
        "user": "db_reader",
        "password": "secret"
    },
    comment="Production PostgreSQL"
)
```

> **Important:** PostgreSQL connections do NOT accept a `database` option. The database is specified in `catalog_options` when creating the foreign catalog.

### Snowflake (`SNOWFLAKE`)

| Option | Required | Description |
|--------|----------|-------------|
| `host` | Yes | Account URL (e.g., `account.snowflakecomputing.com`) |
| `user` | Yes | Username |
| `password` | Yes | Password |
| `sfWarehouse` | Yes | Snowflake warehouse name |
| `port` | No | Port (defaults to `443`) |
| `sfRole` | No | Snowflake role to use |
| `use_proxy` | No | Enable proxy (`"true"`/`"false"`) |
| `proxy_host` | No | Proxy hostname |
| `proxy_port` | No | Proxy port |

```python
manage_uc_connections(
    action="create",
    name="sf_warehouse",
    connection_type="SNOWFLAKE",
    options={
        "host": "account.snowflakecomputing.com",
        "user": "DATABRICKS_USER",
        "password": "secret",
        "sfWarehouse": "COMPUTE_WH"
    },
    comment="Snowflake data warehouse"
)
```

> **Note:** `sfWarehouse` is returned in the response `options` (non-secret). The URL defaults to port 443.

### MySQL (`MYSQL`)

| Option | Required | Description |
|--------|----------|-------------|
| `host` | Yes | Hostname or IP |
| `port` | Yes | Port (typically `3306`) |
| `user` | Yes | Username |
| `password` | Yes | Password |
| `trustServerCertificate` | No | Trust self-signed certs |

```python
manage_uc_connections(
    action="create",
    name="mysql_app",
    connection_type="MYSQL",
    options={
        "host": "mysql.example.com",
        "port": "3306",
        "user": "reader",
        "password": "secret"
    },
    comment="MySQL application database"
)
```

### SQL Server (`SQLSERVER`)

| Option | Required | Description |
|--------|----------|-------------|
| `host` | Yes | Hostname or IP |
| `port` | Yes | Port (typically `1433`) |
| `user` | Yes | Username |
| `password` | Yes | Password |
| `trustServerCertificate` | No | Trust self-signed certs |
| `applicationIntent` | No | Application intent (e.g., `ReadOnly`) |

```python
manage_uc_connections(
    action="create",
    name="sqlserver_erp",
    connection_type="SQLSERVER",
    options={
        "host": "sqlserver.example.com",
        "port": "1433",
        "user": "sa_reader",
        "password": "secret"
    },
    comment="SQL Server ERP system"
)
```

### BigQuery (`BIGQUERY`)

| Option | Required | Description |
|--------|----------|-------------|
| `GoogleServiceAccountKeyJson` | Yes | Full service account key JSON string (must include all required fields) |
| `projectId` | No | GCP project ID |

```python
manage_uc_connections(
    action="create",
    name="bq_analytics",
    connection_type="BIGQUERY",
    options={
        "GoogleServiceAccountKeyJson": "{...full service account key JSON...}"
    },
    comment="BigQuery analytics project"
)
```

> **Note:** The service account key JSON must contain all required fields: `type`, `project_id`, `private_key_id`, `private_key`, `client_email`, `client_id`, `auth_uri`, `token_uri`, `auth_provider_x509_cert_url`, `client_x509_cert_url`, `universe_domain`. The response `options` field is empty (all values are secrets). The response `url` is `https://www.googleapis.com/bigquery/v2:443`.

---

## Foreign Catalog Creation Workflow

### Step 1: Create the Connection

```python
manage_uc_connections(
    action="create",
    name="pg_analytics_conn",
    connection_type="POSTGRESQL",
    options={
        "host": "pg.example.com",
        "port": "5432",
        "user": "readonly_user",
        "password": "secret"
    },
    comment="PostgreSQL analytics connection"
)
```

### Step 2: Create the Foreign Catalog

The `database` is specified in `catalog_options`, not in the connection options:

```python
manage_uc_connections(
    action="create_foreign_catalog",
    connection_name="pg_analytics_conn",
    catalog_name="pg_analytics",
    catalog_options={"database": "analytics_db"},
    warehouse_id="your_warehouse_id"
)
```

### Step 3: Query External Data

```sql
SELECT * FROM pg_analytics.public.customers LIMIT 100;
```

---

## Querying External Data

Once a foreign catalog is created, query external tables like any Unity Catalog table:

```sql
-- Browse schemas in the foreign catalog
SHOW SCHEMAS IN pg_analytics;

-- Browse tables
SHOW TABLES IN pg_analytics.public;

-- Query external data
SELECT * FROM pg_analytics.public.customers LIMIT 100;

-- Join external data with local data
SELECT c.name, o.total
FROM pg_analytics.public.customers c
JOIN main.sales.orders o ON c.id = o.customer_id;
```

### Query Pushdown

Databricks pushes filters, projections, and aggregations down to the external database when possible, minimizing data transfer:

```sql
-- Filter pushdown: only matching rows are transferred
SELECT * FROM pg_analytics.public.orders
WHERE order_date >= '2024-01-01' AND status = 'completed';

-- Aggregation pushdown: computed in the external DB
SELECT status, COUNT(*) FROM pg_analytics.public.orders
GROUP BY status;
```

---

## Common Issues and Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `does not support the following option(s): database` | `database` is not a connection option for any type | Specify the database in `catalog_options` when creating the foreign catalog |
| `does not support the following option(s): <key>` | Invalid option key for the connection type | Check the supported options table for your connection type above; the error message lists all valid keys |
| `Connection '<name>' already exists` | Duplicate connection name | Use a different name or delete the existing connection first |
| `Connection '<name>' does not exist.` | Connection not found for get/update/delete | Check the connection name with `list` action |
| `ConnectionsAPI.update() missing 1 required positional argument: 'options'` | Update called without `options` | Always include `options` with full credentials when calling update |
| `PERMISSION_DENIED` on create connection | Missing `CREATE CONNECTION` privilege | Grant `CREATE CONNECTION` on the metastore |
| `PERMISSION_DENIED: User does not have CREATE CATALOG` | Missing catalog creation privilege | Grant `CREATE CATALOG` on the metastore |
| `<id> is not a valid endpoint id` | Invalid SQL warehouse ID for foreign catalog creation | Verify the `warehouse_id` with your workspace's SQL warehouses |
| `CONNECTION_NOT_FOUND` during foreign catalog creation | Connection name not found | Verify the connection exists with `get` action |
| `Invalid action: '<action>'` | Unrecognized action parameter | Use one of: `list`, `create`, `get`, `update`, `delete`, `create_foreign_catalog` |
| BigQuery: `Missing fields are token_uri, ...` | Incomplete service account key JSON | Provide the full JSON key file with all required fields |
| Slow queries on foreign catalog | Large result sets transferred over network | Add filters to push down predicates; consider materializing frequently-used data |
| Update response shows stale `comment` | Known behavior — comment may not reflect in update response | Use `get` after update to verify; host/port/name changes are reflected immediately |

---

## Resources

- [Lakehouse Federation Documentation](https://docs.databricks.com/en/query-federation/index.html)
- [Connection Types Reference](https://docs.databricks.com/en/query-federation/create-connection.html)
- [Foreign Catalog Setup](https://docs.databricks.com/en/query-federation/create-foreign-catalog.html)

# Delta Sharing & Lakehouse Federation

Share data securely across organizations and connect to external data sources.

## MCP Tools

| Tool | Purpose |
|------|---------|
| `manage_uc_sharing` | Create/manage shares, recipients, and providers for Delta Sharing |
| `manage_uc_connections` | Create/manage Lakehouse Federation connections to external databases |
| `manage_uc_storage` | Create/manage storage credentials and external locations |

---

## Delta Sharing

Delta Sharing enables secure, read-only sharing of data across Databricks workspaces and to non-Databricks consumers.

### Concepts

- **Share**: A named collection of tables to share
- **Recipient**: An entity (person, org, workspace) that receives shared data
- **Provider**: An entity that shares data (your workspace)

### Create a Share

```python
manage_uc_sharing(
    resource_type="share",
    action="create",
    name="partner_data_share",
    comment="Quarterly metrics shared with partners"
)
```

### Add a Table to a Share

```python
manage_uc_sharing(
    resource_type="share",
    action="add_table",
    name="partner_data_share",
    table_name="analytics.gold.quarterly_metrics",
    shared_as="quarterly_metrics"
)
```

### Add a Table with Partition Filter

```python
manage_uc_sharing(
    resource_type="share",
    action="add_table",
    name="partner_data_share",
    table_name="analytics.gold.orders",
    shared_as="orders",
    partition_spec="region = 'US'"
)
```

### Remove a Table from a Share

```python
manage_uc_sharing(
    resource_type="share",
    action="remove_table",
    name="partner_data_share",
    table_name="analytics.gold.quarterly_metrics"
)
```

### Create a Recipient

```python
# Databricks-to-Databricks sharing (uses sharing_id)
manage_uc_sharing(
    resource_type="recipient",
    action="create",
    name="partner_acme",
    authentication_type="DATABRICKS",
    sharing_id="<sharing_identifier_from_partner>",
    comment="Acme Corp data team"
)

# Open sharing (generates activation link for non-Databricks consumers)
manage_uc_sharing(
    resource_type="recipient",
    action="create",
    name="external_partner",
    authentication_type="TOKEN",
    comment="External partner using open Delta Sharing"
)
```

### Grant a Share to a Recipient

```python
manage_uc_sharing(
    resource_type="share",
    action="grant_to_recipient",
    share_name="partner_data_share",
    recipient_name="partner_acme"
)
```

### Revoke a Share from a Recipient

```python
manage_uc_sharing(
    resource_type="share",
    action="revoke_from_recipient",
    share_name="partner_data_share",
    recipient_name="partner_acme"
)
```

### List and Inspect

```python
# List all shares
manage_uc_sharing(resource_type="share", action="list")

# Get share details (shows included tables)
manage_uc_sharing(resource_type="share", action="get", name="partner_data_share")

# List recipients
manage_uc_sharing(resource_type="recipient", action="list")

# List providers (shares you've received)
manage_uc_sharing(resource_type="provider", action="list")

# List shares from a specific provider
manage_uc_sharing(resource_type="provider", action="list_shares", name="databricks-partner")
```

---

## Storage Credentials & External Locations

Required for external tables, external volumes, and Lakehouse Federation.

### Storage Credentials

```python
# List existing credentials
manage_uc_storage(resource_type="credential", action="list")

# Get credential details
manage_uc_storage(resource_type="credential", action="get", name="my-s3-credential")

# Create an AWS IAM role credential
manage_uc_storage(
    resource_type="credential",
    action="create",
    name="my-s3-credential",
    aws_iam_role_arn="arn:aws:iam::123456789012:role/unity-catalog-access",
    comment="Access to analytics S3 bucket"
)

# Validate a credential
manage_uc_storage(
    resource_type="credential",
    action="validate",
    name="my-s3-credential"
)
```

### External Locations

```python
# Create external location
manage_uc_storage(
    resource_type="external_location",
    action="create",
    name="analytics-landing",
    url="s3://my-bucket/landing/",
    credential_name="my-s3-credential",
    comment="Landing zone for raw data files"
)

# List external locations
manage_uc_storage(resource_type="external_location", action="list")
```

---

## Lakehouse Federation

Connect to external databases (PostgreSQL, MySQL, SQL Server, Snowflake, BigQuery) and query them through Unity Catalog.

### Create a Connection

```python
# PostgreSQL connection
manage_uc_connections(
    action="create",
    name="postgres_erp",
    connection_type="POSTGRESQL",
    options={
        "host": "erp-db.company.com",
        "port": "5432",
        "user": "readonly_user",
        "password": "<password>"
    },
    comment="ERP PostgreSQL database"
)

# MySQL connection
manage_uc_connections(
    action="create",
    name="mysql_legacy",
    connection_type="MYSQL",
    options={
        "host": "legacy-db.company.com",
        "port": "3306",
        "user": "reader",
        "password": "<password>"
    }
)
```

### Create a Foreign Catalog

After creating a connection, create a foreign catalog to browse and query the external database:

```python
manage_uc_connections(
    action="create_foreign_catalog",
    connection_name="postgres_erp",
    catalog_name="erp_catalog",
    catalog_options={"database": "erp_production"}
)
```

Now you can query external tables as if they were native UC tables:

```sql
SELECT * FROM erp_catalog.public.orders LIMIT 10;
```

### List and Manage Connections

```python
# List all connections
manage_uc_connections(action="list")

# Get connection details
manage_uc_connections(action="get", name="postgres_erp")

# Update connection
manage_uc_connections(
    action="update",
    name="postgres_erp",
    options={"host": "new-erp-db.company.com"},
    comment="Updated to new host"
)

# Delete connection
manage_uc_connections(action="delete", name="postgres_erp")
```

---

## Common Patterns

### Share Region-Specific Data

```python
# Share only US data with a US partner
manage_uc_sharing(
    resource_type="share",
    action="add_table",
    name="us_partner_share",
    table_name="analytics.gold.revenue",
    partition_spec="region = 'US'"
)
```

### Federated Query Across Sources

```sql
-- Join Databricks table with federated PostgreSQL table
SELECT d.customer_id, d.total_spend, e.erp_status
FROM analytics.gold.customers d
JOIN erp_catalog.public.customer_status e
  ON d.customer_id = e.customer_id;
```

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **"Share not found"** | Shares are metastore-level objects. Ensure you're connected to the right workspace/metastore |
| **Recipient can't access shared data** | Verify: (1) share is granted to recipient via `grant_to_recipient`, (2) activation link was used (for TOKEN auth), (3) table is added to the share |
| **Federation query slow** | Predicate pushdown works for simple filters. Complex joins are pulled into Spark — add filters early |
| **"Connection failed"** | Check: (1) network connectivity (firewall/VPC), (2) credentials in `options`, (3) host/port |
| **Cannot create foreign catalog** | Need `CREATE_CATALOG` and `CREATE_FOREIGN_CATALOG` privileges, plus the connection must exist |

# Lakebase (PostgreSQL) Connectivity

Lakebase provides low-latency transactional storage for Databricks Apps via a managed PostgreSQL interface.

**Docs**: https://docs.databricks.com/aws/en/dev-tools/databricks-apps/lakebase

---

## When to Use Lakebase

| Use Case | Recommended Backend |
|----------|-------------------|
| Analytical queries on Delta tables | SQL Warehouse |
| Low-latency transactional CRUD | **Lakebase** |
| App-specific metadata/config | **Lakebase** |
| User session data | **Lakebase** |
| Large-scale data exploration | SQL Warehouse |

---

## Setup

1. Add Lakebase as an app resource in the Databricks UI (resource type: **Lakebase database**)
2. Databricks auto-injects PostgreSQL connection env vars:

| Variable | Description |
|----------|-------------|
| `PGHOST` | Database hostname |
| `PGDATABASE` | Database name |
| `PGUSER` | PostgreSQL role (created per app) |
| `PGPASSWORD` | Role password |
| `PGPORT` | Port (typically 5432) |

3. Reference in `app.yaml`:

```yaml
env:
  - name: DB_CONNECTION_STRING
    valueFrom:
      resource: database
```

---

## Connection Patterns

### psycopg2 (Synchronous)

```python
import os
import psycopg2

conn = psycopg2.connect(
    host=os.getenv("PGHOST"),
    database=os.getenv("PGDATABASE"),
    user=os.getenv("PGUSER"),
    password=os.getenv("PGPASSWORD"),
    port=os.getenv("PGPORT", "5432"),
)

with conn.cursor() as cur:
    cur.execute("SELECT * FROM my_table LIMIT 10")
    rows = cur.fetchall()

conn.close()
```

### asyncpg (Asynchronous)

```python
import os
import asyncpg

async def get_data():
    conn = await asyncpg.connect(
        host=os.getenv("PGHOST"),
        database=os.getenv("PGDATABASE"),
        user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"),
        port=int(os.getenv("PGPORT", "5432")),
    )
    rows = await conn.fetch("SELECT * FROM my_table LIMIT 10")
    await conn.close()
    return rows
```

### SQLAlchemy

```python
import os
from sqlalchemy import create_engine

DATABASE_URL = (
    f"postgresql://{os.getenv('PGUSER')}:{os.getenv('PGPASSWORD')}"
    f"@{os.getenv('PGHOST')}:{os.getenv('PGPORT', '5432')}"
    f"/{os.getenv('PGDATABASE')}"
)

engine = create_engine(DATABASE_URL)
```

---

## Streamlit with Lakebase

```python
import streamlit as st
import psycopg2

@st.cache_resource
def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("PGHOST"),
        database=os.getenv("PGDATABASE"),
        user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"),
    )
```

---

## Critical: requirements.txt

`psycopg2` and `asyncpg` are **NOT pre-installed** in the Databricks Apps runtime. You **MUST** include them in `requirements.txt` or the app will crash on startup:

```
psycopg2-binary
```

For async apps:
```
asyncpg
```

**This is the most common cause of Lakebase app failures.**

## Troubleshooting: OAuth / Security Label Errors

When the app's service principal connects to Lakebase via OAuth (i.e. `PGPASSWORD` is not auto-injected), you may see:

```
FATAL: An oauth token was supplied but no role security label was configured in postgres for role "<SP_CLIENT_ID>"
```

**Root cause**: The SP's PostgreSQL role exists but lacks the `databricks_auth` security label that maps it to a Databricks identity.

**Fix**: Connect as the instance owner and set the security label:

```sql
-- 1. Find the SP's numeric ID (from Databricks workspace)
-- databricks service-principals list -o json | grep <SP_CLIENT_ID>
-- Look for the "id" field (numeric)

-- 2. Set the security label in Lakebase
SECURITY LABEL FOR databricks_auth ON ROLE "<SP_CLIENT_ID>"
  IS 'id=<SP_NUMERIC_ID>,type=SERVICE_PRINCIPAL';

-- 3. Grant schema/table access
GRANT USAGE ON SCHEMA my_schema TO "<SP_CLIENT_ID>";
GRANT SELECT ON ALL TABLES IN SCHEMA my_schema TO "<SP_CLIENT_ID>";
```

You can verify with: `SELECT * FROM pg_seclabels WHERE objtype = 'role';`

**When PGPASSWORD is empty**: If Databricks auto-injects `PGHOST` and `PGUSER` but NOT `PGPASSWORD`, use the SDK to generate an OAuth token:

```python
from databricks.sdk import WorkspaceClient
import uuid

w = WorkspaceClient()
cred = w.database.generate_database_credential(
    request_id=str(uuid.uuid4()),
    instance_names=["my-lakebase-instance"],
)
# Use cred.token as the password
```

---

## Lakebase Sync (Reverse ETL from Delta)

To sync Unity Catalog Delta tables to Lakebase for low-latency serving:

1. Add primary keys to source Delta tables (required):
```sql
ALTER TABLE catalog.schema.my_table ALTER COLUMN id SET NOT NULL;
ALTER TABLE catalog.schema.my_table ADD CONSTRAINT pk PRIMARY KEY (id);
```

2. Create synced tables via CLI:
```bash
databricks database create-synced-database-table --json '{
  "name": "catalog.schema.lb_my_table",
  "source_table_full_name": "catalog.schema.my_table",
  "scheduling_policy": {"snapshot": {}},
  "primary_key_columns": ["id"]
}'
```

The `name` field is the **destination** UC table pointer (use a prefix like `lb_` to avoid conflicts with the source table).

---

## Notes

- Lakebase is in **Public Preview**
- Each app gets its own PostgreSQL role with `Can connect and create` permission
- Lakebase is ideal alongside SQL warehouse: use Lakebase for app state, SQL warehouse for analytics
- When using Lakebase Sync, synced tables appear in the Lakebase schema with the prefix you chose

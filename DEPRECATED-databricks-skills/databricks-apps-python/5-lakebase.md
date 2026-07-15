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

## Notes

- Lakebase is in **Public Preview**
- Each app gets its own PostgreSQL role with `Can connect and create` permission
- Lakebase is ideal alongside SQL warehouse: use Lakebase for app state, SQL warehouse for analytics

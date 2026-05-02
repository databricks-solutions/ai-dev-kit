# Lakebase Connectivity

## Authentication Methods

| Method | Token Lifetime | Best For |
|--------|---------------|----------|
| **OAuth tokens** | 1 hour (must refresh) | Interactive sessions, workspace-integrated apps |
| **Native Postgres passwords** | No expiry | Long-running processes, tools without token rotation |

**Connection timeouts:** 24h idle timeout is guaranteed. Max connection lifetime beyond 24h is not guaranteed — implement reconnection logic. Always use `sslmode=require`.

## Generating OAuth Tokens

```bash
# CLI: scope a 1-hour token to a specific endpoint
databricks postgres generate-database-credential \
  projects/<PROJECT_ID>/branches/<BRANCH_ID>/endpoints/<ENDPOINT_ID> \
  --profile <PROFILE>
```

```python
# SDK
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
cred = w.postgres.generate_database_credential(
    endpoint="projects/my-app/branches/production/endpoints/ep-primary"
)
token = cred.token  # password for Postgres connection, valid ~1 hour
```

## Connection Patterns

### Pattern 1: Direct Connection (Scripts/Notebooks)

For one-off queries. Get a fresh token, connect, execute, close.

**Key parameters:**
```
host      = endpoint.status.hosts.host   (from get-endpoint)
dbname    = "databricks_postgres"         (or your database name)
user      = w.current_user.me().user_name
password  = w.postgres.generate_database_credential(endpoint=<name>).token
sslmode   = "require"
```

**Pattern (psycopg2 or psycopg3):**
```python
import psycopg
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
ep_name = "projects/<ID>/branches/<BRANCH>/endpoints/<EP>"

# 1. Get host from endpoint
endpoint = w.postgres.get_endpoint(name=ep_name)
host = endpoint.status.hosts.host

# 2. Generate OAuth token (valid 1 hour)
token = w.postgres.generate_database_credential(endpoint=ep_name).token

# 3. Connect
username = w.current_user.me().user_name
conn = psycopg.connect(
    host=host, dbname="databricks_postgres",
    user=username, password=token, sslmode="require",
)
```

### Pattern 2: Connection Pool with Token Refresh (Production)

For long-running apps. Use SQLAlchemy engine with a `creator` callback that injects the current token. Refresh the token in a background loop before expiry.

**Key config:**
```
pool_size       = 5          (adjust to workload)
max_overflow    = 10
pool_pre_ping   = True       (detect stale connections)
pool_recycle    = 3600       (recycle connections hourly)
sslmode         = "require"
```

**Pattern:**
```python
from sqlalchemy import create_engine, event

# Token management: store current token in a mutable container
current_token = [generate_initial_token()]

# Background refresh: refresh before the 1-hour expiry.
# Official docs pattern: check expiry timestamp, refresh within 2 minutes of expiry.
# Alternative: refresh every 30-40 minutes (Lakebase team guidance).
def refresh_loop():
    while True:
        sleep(refresh_interval)
        current_token[0] = generate_new_token()

# SQLAlchemy engine: inject token at connect time
engine = create_engine(url, pool_size=5, pool_pre_ping=True, pool_recycle=3600)

@event.listens_for(engine, "do_connect")
def inject_token(dialect, conn_rec, cargs, cparams):
    cparams["password"] = current_token[0]
```

For a complete async implementation with FastAPI integration, see [Databricks docs: Connect to Lakebase](https://docs.databricks.com/aws/en/oltp/projects/authentication).

### Pattern 3: Static URL (Local Development)

For local dev, use a static connection URL via environment variable:

```bash
export LAKEBASE_PG_URL="postgresql://user:password@host:5432/database?sslmode=require"
```

```python
import os
from sqlalchemy import create_engine

url = os.environ["LAKEBASE_PG_URL"]
engine = create_engine(url, pool_size=5)
```

### Pattern 4: DNS Resolution Workaround (macOS)

Python's `socket.getaddrinfo()` can fail with long Lakebase hostnames on macOS. Use `dig` as fallback and pass `hostaddr` alongside `host` (for TLS SNI):

```python
import subprocess
import socket
import psycopg

def resolve_hostname(hostname: str) -> str:
    try:
        return socket.gethostbyname(hostname)
    except socket.gaierror:
        pass
    result = subprocess.run(
        ["dig", "+short", hostname], capture_output=True, text=True, timeout=5,
    )
    for ip in result.stdout.strip().split("\n"):
        if ip and not ip.startswith(";"):
            return ip
    raise RuntimeError(f"Could not resolve hostname: {hostname}")

conn = psycopg.connect(
    host=hostname,                        # for TLS SNI
    hostaddr=resolve_hostname(hostname),  # actual IP
    dbname=database_name,
    user=username,
    password=token,
    sslmode="require",
)
```

## Best Practices

- **Always use `sslmode=require`** — Lakebase requires SSL/TLS on all connections
- **Refresh tokens before expiry** — check expiry timestamp, refresh within 2 minutes; or refresh every 30-40 minutes
- **Use connection pooling** — avoid creating a new connection per request
- **Enable `pool_pre_ping`** — detects stale connections after scale-to-zero wake-up
- **Handle scale-to-zero reconnection** — first connection after idle may take ~100ms; implement retry
- **psycopg2 or psycopg3** — both work; psycopg3 recommended for new development (better async, pooling)

## Data API

PostgREST-compatible HTTP API for CRUD operations on Postgres tables. **Autoscaling only.**

### Enabling

1. Navigate to **Data API** in the Lakebase project UI
2. Click **Enable Data API** — auto-creates the `authenticator` role and `pgrst` schema
3. The `public` schema is exposed by default

### Authentication

All requests require a Databricks OAuth bearer token:

```
Authorization: Bearer <databricks-oauth-token>
```

Each Databricks identity must have a matching Postgres role — the auto-created `authenticator` role assumes the caller's identity at query time.

**Create a role for Data API access:**

```sql
CREATE ROLE "user@example.com" LOGIN;
GRANT USAGE ON SCHEMA public TO "user@example.com";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "user@example.com";
```

### CRUD Operations

```bash
# GET — query with filters, pagination, ordering
curl -H "Authorization: Bearer $TOKEN" "$DATA_API_URL/public/users?age=gt.21&limit=10&order=created_at.desc"

# POST — insert
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "Alice", "email": "alice@example.com"}' "$DATA_API_URL/public/users"

# PATCH — update (filter required)
curl -X PATCH -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"status": "inactive"}' "$DATA_API_URL/public/users?id=eq.42"

# DELETE (filter required)
curl -X DELETE -H "Authorization: Bearer $TOKEN" "$DATA_API_URL/public/users?id=eq.42"
```

### Row-Level Security (RLS)

Strongly recommended for multi-tenant data. Policies use `current_user` (the authenticated Databricks email).

```sql
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_isolation ON users USING (email = current_user);
```

### Configuration

Via the Data API UI: exposed schemas, max rows, CORS origins, OpenAPI spec.

### Unsupported PostgREST Features

Computed relationships, inner-join embedding, custom media type handlers, stripped-nulls, planned/estimated counts, transaction control via headers, EXPLAIN/trace, pre-request functions, GUCs, PostGIS auto-GeoJSON.

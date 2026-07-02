# Lakebase Autoscaling connection patterns

Order of preference:

1. **Canonical:** `psycopg_pool.ConnectionPool` + `OAuthConnection` subclass + `max_lifetime=2700`.
2. **SQLAlchemy:** official `do_connect` auth hook; optionally rely on `pool_recycle`/`dispose()` rather than a background token loop.
3. **Direct `psycopg.connect`:** notebooks/one-shot scripts under 1 hour.
4. **Static Postgres URL/native password:** local/dev tools only, or tools unable to rotate OAuth credentials.

## Authentication facts

Lakebase OAuth database credentials:
- Mint with `WorkspaceClient().postgres.generate_database_credential(endpoint=...)`.
- Use `cred.token` as the Postgres password.
- Expire after about 1 hour.
- Expiry is enforced at login; already-open connections continue until closed by pool/platform timeouts.

Critical warning:

```python
# ✅ Lakebase-scoped credential: works for Postgres login
cred = w.postgres.generate_database_credential(endpoint=endpoint_name)
password = cred.token

# ❌ Workspace-scoped token: fails at Postgres login
password = w.config.oauth_token().access_token
# also do not use WorkspaceClient().config.token
```

Always connect with `sslmode=require`.

## 1. Canonical: psycopg pool + OAuthConnection

Use for production Databricks Apps and most Python services.

Key mechanics:
- The pool calls `OAuthConnection.connect()` whenever it opens a physical connection: initial fill, growth under load, recycle, replacement after failure.
- `connect()` mints a fresh Lakebase token just-in-time and injects it as `password`.
- `max_lifetime=2700` recycles physical connections after 45 minutes, before 1-hour token expiry.
- No background refresh thread/task is needed.

Minimal skeleton:

```python
import os
import psycopg
from psycopg_pool import ConnectionPool
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

class OAuthConnection(psycopg.Connection):
    @classmethod
    def connect(cls, conninfo="", **kwargs):
        cred = w.postgres.generate_database_credential(
            endpoint=os.environ["ENDPOINT_NAME"]
        )
        kwargs["password"] = cred.token
        return super().connect(conninfo, **kwargs)

pool = ConnectionPool(
    conninfo=(
        f"dbname={os.environ['PGDATABASE']} "
        f"user={os.environ['PGUSER']} "
        f"host={os.environ['PGHOST']} "
        f"port={os.environ.get('PGPORT', '5432')} "
        f"sslmode={os.environ.get('PGSSLMODE', 'require')}"
    ),
    connection_class=OAuthConnection,
    min_size=1,
    max_size=10,
    max_lifetime=2700,
    open=True,
)
```

Prefer `2700`; it is a defensive convention. The official Databricks tutorial leaves `max_lifetime` unset; `databricks-ai-bridge` uses `2700`.

For FastAPI or explicit startup:
- instantiate with `open=False`
- call `pool.open(wait=True, timeout=30.0)` in lifespan/startup
- call `pool.close()` on shutdown

This also avoids relying on implicit open behavior.

## Databricks Apps environment variables

When adding a Lakebase/Postgres resource to a Databricks App, these are auto-injected for the **first** DB resource:

```text
PGAPPNAME
PGHOST
PGPORT
PGDATABASE
PGUSER
PGSSLMODE
```

Gotchas:
- `PGUSER` is typically the app service principal client ID.
- Only the first database resource is auto-injected; additional resources need explicit `valueFrom`.
- `ENDPOINT_NAME` is **not** auto-injected. Add it manually because `generate_database_credential(endpoint=...)` requires the full endpoint path:

```yaml
env:
  - name: ENDPOINT_NAME
    value: "projects/<project-id>/branches/<branch-id>/endpoints/<endpoint-id>"
```

## 2. SQLAlchemy: official `do_connect` hook

Use when the app is already built around SQLAlchemy.

Important distinction:
- `do_connect` is the official Databricks-recommended SQLAlchemy credential injection hook and is used by `databricks-ai-bridge`.
- The community/extra-complexity variant is adding a background `asyncio.Task` token-refresh loop. Demote that loop, not `do_connect`.

Recommended hook shape:

```python
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
endpoint_name = "projects/my-app/branches/production/endpoints/ep-primary"
host = w.postgres.get_endpoint(name=endpoint_name).status.hosts.host
user = w.current_user.me().user_name

engine = create_async_engine(
    f"postgresql+psycopg://{user}@{host}:5432/databricks_postgres",
    connect_args={"sslmode": "require"},
    pool_recycle=2700,
)

@event.listens_for(engine.sync_engine, "do_connect")
def inject_lakebase_token(dialect, conn_rec, cargs, cparams):
    cred = w.postgres.generate_database_credential(endpoint=endpoint_name)
    cparams["password"] = cred.token
```

Notes:
- `do_connect` fires when SQLAlchemy opens a new DBAPI connection.
- `pool_recycle=2700` approximates the psycopg-pool pattern.
- If you need deterministic refresh, prefer scheduled `engine.dispose()` and let the next checkout re-open with `do_connect`.
- A background token cache/refresh task is optional complexity and can create stale-token races if implemented poorly.

## 3. Direct psycopg for notebooks/scripts

Only for short-lived sessions where connections are opened and used immediately.

Recipe:
1. Build endpoint path.
2. `get_endpoint(...).status.hosts.host`.
3. `generate_database_credential(endpoint=endpoint_name)`.
4. `psycopg.connect(host=host, dbname="databricks_postgres", user=<identity>, password=cred.token, sslmode="require")`.

Use `w.current_user.me().user_name` for user in notebooks/manual scripts. In Databricks Apps, prefer `PGUSER`.

## 4. Static URL / native password

Use only for local development, legacy tools, or clients that cannot rotate OAuth database credentials. For SQLAlchemy + psycopg3, normalize:

```text
postgresql://...        -> postgresql+psycopg://...
```

Still set `sslmode=require`.

## Endpoint discovery

Avoid hardcoding host if you can hardcode the endpoint name instead:

```python
ep = w.postgres.get_endpoint(
    name="projects/my-app/branches/production/endpoints/ep-primary"
)
host = ep.status.hosts.host
```

If no endpoint ID is known, list under branch and choose deliberately:

```python
endpoints = list(w.postgres.list_endpoints(
    parent="projects/my-app/branches/production"
))
```

Do not assume the first endpoint is the primary if read replicas exist; check endpoint type/status.

## DNS workaround for macOS

Some macOS/Python resolver combinations fail on long Lakebase hostnames.

Workaround:
- Resolve the hostname externally, commonly with `dig +short <hostname>`.
- Pass both:
  - `host=<original hostname>` for TLS/SNI/certificate validation.
  - `hostaddr=<resolved IP>` for the actual TCP connection.

psycopg3 supports `hostaddr`.

## Timeouts, scale-to-zero, and retries

Plan for:
- 1-hour Lakebase OAuth token lifetime at login.
- 24-hour idle connection timeout.
- 3-day maximum connection lifetime.
- Scale-to-zero wake-up latency; first connection/query after suspension may need retry/backoff.
- After suspension/reactivation: session context is reset, temp tables/prepared statements are gone, active transactions/connections are terminated.

Use context managers so pooled connections return promptly.

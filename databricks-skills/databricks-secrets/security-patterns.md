# Security Patterns for Databricks Secrets

## Secret References

Databricks secrets can be referenced in several contexts without exposing the raw value.

### In Notebooks (dbutils)

```python
# Read a secret value in a notebook
api_key = dbutils.secrets.get(scope="my-scope", key="api-key")
```

Secrets retrieved via `dbutils.secrets.get()` are redacted in notebook output — Databricks replaces the value with `[REDACTED]` in cell results and logs.

### In Model Serving Endpoints

Serving endpoints reference secrets using the `{{secrets/scope/key}}` syntax in environment variables:

```python
# When creating a serving endpoint with environment variables:
create_serving_endpoint(
    name="my-endpoint",
    model_name="catalog.schema.model",
    model_version="1",
    environment_vars={
        "OPENAI_API_KEY": "{{secrets/serving-credentials/openai-key}}",
        "DB_CONNECTION": "{{secrets/serving-credentials/db-conn-string}}"
    }
)
```

The secret value is injected at runtime — it never appears in the endpoint configuration or logs.

### In Jobs and Tasks

Job tasks can access secrets via `dbutils.secrets.get()` in their code. For jobs that call external APIs, store credentials in a scope and reference them in the task's Python/notebook code.

### In Spark Configuration

```python
# Set Spark config from a secret (e.g., external storage credentials)
spark.conf.set(
    "fs.azure.account.key.mystorageaccount.blob.core.windows.net",
    dbutils.secrets.get(scope="storage-keys", key="azure-blob-key")
)
```

## Access Control (ACLs)

Secret scopes support three permission levels:

| Permission | Capabilities |
|------------|-------------|
| **READ** | Read secret values via `dbutils.secrets.get()` |
| **WRITE** | Read + create/update/delete secrets within the scope |
| **MANAGE** | Write + manage ACLs + delete the scope itself |

### Default Behavior

- The scope creator gets **MANAGE** permission automatically
- No other users have access unless explicitly granted
- Use `initial_manage_principal="users"` during creation to grant all workspace users MANAGE

### ACL Recommendations

| Scenario | Pattern |
|----------|---------|
| **Shared team scope** | Create with `initial_manage_principal="users"`, or add specific groups via ACLs |
| **Production credentials** | Creator-only MANAGE, grant READ to service principals that run jobs |
| **Dev/test secrets** | Use `initial_manage_principal="users"` for easy team access |

## Naming Conventions

### Scope Names

Use a consistent naming scheme to keep scopes organized:

| Pattern | Example | Use Case |
|---------|---------|----------|
| `{app}-{env}` | `payments-prod` | Environment-specific app secrets |
| `{team}-shared` | `data-eng-shared` | Shared team credentials |
| `serving-{purpose}` | `serving-llm-keys` | Model serving endpoint secrets |

### Secret Key Names

| Pattern | Example |
|---------|---------|
| Lowercase with hyphens | `api-key`, `db-password`, `oauth-token` |
| Service-prefixed | `openai-api-key`, `snowflake-password` |

## Security Best Practices

1. **Never log secret values** — `dbutils.secrets.get()` output is auto-redacted, but avoid storing in variables that get printed
2. **Rotate regularly** — Use `put_secret` to overwrite existing keys (it's an upsert)
3. **Scope per application** — Isolate secrets by app/service to limit blast radius
4. **Audit with `list_secrets`** — Periodically check scopes for unused or stale keys
5. **Use `get_secret` to verify** — Check `value_length` to confirm a secret is set before deploying

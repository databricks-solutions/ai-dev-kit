---
name: databricks-secrets
description: "Manage Databricks secrets for storing API keys, tokens, and credentials. Covers secret scopes, CRUD operations, ACLs, and usage in notebooks, jobs, and apps. Use when storing credentials, configuring external service access, or managing secret permissions."
---

# Databricks Secrets

Manage secrets (API keys, tokens, passwords) securely on Databricks using secret scopes, ACLs, and the Secrets API.

## When to Use

- Storing API keys for external services (OpenAI, AWS, etc.)
- Configuring database credentials for ETL pipelines
- Managing tokens for model serving endpoints
- Setting up secret-based authentication in notebooks and jobs
- Controlling who can read/write secrets via ACLs

## Quick Start

### CLI

```bash
# Create a scope
databricks secrets create-scope my-scope

# Store a secret
databricks secrets put-secret my-scope api-key --string-value "sk-abc123"

# Use in a notebook
# value = dbutils.secrets.get(scope="my-scope", key="api-key")
```

### Python SDK

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

w.secrets.create_scope(scope="my-scope")
w.secrets.put_secret(scope="my-scope", key="api-key", string_value="sk-abc123")
```

## Common Patterns

### Pattern 1: Store and Retrieve Secrets

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Create scope
w.secrets.create_scope(scope="ml-credentials")

# Store secrets
w.secrets.put_secret(scope="ml-credentials", key="openai-key", string_value="sk-...")
w.secrets.put_secret(scope="ml-credentials", key="db-password", string_value="p@ssw0rd")

# List secrets (values are never returned — only metadata)
secrets = list(w.secrets.list_secrets(scope="ml-credentials"))
for s in secrets:
    print(f"  {s.key} (updated: {s.last_updated_timestamp})")
```

In a notebook:

```python
import openai

openai.api_key = dbutils.secrets.get(scope="ml-credentials", key="openai-key")
```

### Pattern 2: Secret ACLs

Control who can read, write, or manage secrets:

```python
# Grant READ access to a user
w.secrets.put_acl(
    scope="ml-credentials",
    principal="data-team@company.com",
    permission="READ"
)

# Grant WRITE access to a group
w.secrets.put_acl(
    scope="ml-credentials",
    principal="ml-engineers",
    permission="WRITE"
)

# List ACLs
acls = list(w.secrets.list_acls(scope="ml-credentials"))
for a in acls:
    print(f"  {a.principal}: {a.permission}")
```

Permission levels:

| Permission | Can Read | Can Write | Can Manage ACLs | Can Delete Scope |
|-----------|----------|-----------|-----------------|-----------------|
| READ | Yes | No | No | No |
| WRITE | Yes | Yes | No | No |
| MANAGE | Yes | Yes | Yes | Yes |

### Pattern 3: Using Secrets in Jobs and Pipelines

In Spark SQL (notebooks):

```sql
-- Reference in SQL using secret() function (DBR 15.4+)
CREATE TABLE catalog.schema.external_data
USING jdbc
OPTIONS (
    url = 'jdbc:postgresql://host:5432/db',
    user = secret('my-scope', 'db-user'),
    password = secret('my-scope', 'db-password')
);
```

In Python notebooks:

```python
password = dbutils.secrets.get(scope="my-scope", key="db-password")

df = (spark.read
    .format("jdbc")
    .option("url", "jdbc:postgresql://host:5432/db")
    .option("user", "admin")
    .option("password", password)
    .option("dbtable", "public.users")
    .load())
```

### Pattern 4: Environment Variables in Model Serving

For model serving endpoints, use secrets as environment variables:

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

w.serving_endpoints.create(
    name="my-endpoint",
    config={
        "served_entities": [{
            "entity_name": "catalog.schema.model",
            "entity_version": "1",
            "environment_vars": {
                "OPENAI_API_KEY": "{{secrets/ml-credentials/openai-key}}"
            }
        }]
    }
)
```

The `{{secrets/scope/key}}` syntax resolves at runtime.

## CLI Reference

```bash
# Scope management
databricks secrets create-scope <scope-name>
databricks secrets list-scopes
databricks secrets delete-scope <scope-name>

# Secret management
databricks secrets put-secret <scope> <key> --string-value "<value>"
databricks secrets list-secrets <scope>
databricks secrets delete-secret <scope> <key>

# ACL management
databricks secrets put-acl <scope> <principal> <permission>
databricks secrets list-acls <scope>
databricks secrets delete-acl <scope> <principal>
```

## Common Issues

| Issue | Solution |
|-------|----------|
| **`RESOURCE_ALREADY_EXISTS`** | Scope already exists — use a different name or delete first |
| **`PERMISSION_DENIED` reading secrets** | Request READ ACL from the scope owner |
| **Secret value shows `[REDACTED]`** | This is expected — `dbutils.secrets.get()` redacts in display, but the value is available in code |
| **`RESOURCE_DOES_NOT_EXIST`** | Scope or key doesn't exist — check spelling with `list-scopes` / `list-secrets` |
| **Secrets not available in serving endpoint** | Use `{{secrets/scope/key}}` syntax in `environment_vars` |
| **Can't create scope** | Requires workspace admin or `CAN_MANAGE` on the secrets API |

## Best Practices

1. **One scope per project or team** — easier to manage ACLs
2. **Never log secret values** — `dbutils.secrets.get()` auto-redacts in notebook output
3. **Use descriptive key names** — e.g., `openai-api-key`, `postgres-password`
4. **Rotate secrets regularly** — use `put_secret` to overwrite with new values
5. **Prefer `{{secrets/...}}` syntax** for serving endpoints — avoids hardcoding
6. **Use ACLs** to restrict access — default is creator-only

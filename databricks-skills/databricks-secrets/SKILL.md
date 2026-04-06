---
name: databricks-secrets
description: "Manage Databricks secret scopes and secrets. Use when creating secret scopes, storing API keys or credentials, listing secrets, or checking if a secret exists."
---

# Databricks Secrets

Manage secret scopes and secrets for secure credential storage in Databricks workspaces.

## Overview

Databricks Secrets provides a secure key-value store for sensitive data like API keys, tokens, and connection strings. Secrets are organized into scopes, and access is controlled via ACLs. Secret values are never exposed through MCP tools — only metadata (existence, byte length) is returned.

## When to Use This Skill

Use this skill when:
- Creating secret scopes to organize credentials by application or environment
- Storing API keys, tokens, or connection strings securely
- Checking whether a secret exists and its approximate size
- Listing secrets in a scope to audit what's configured
- Cleaning up unused scopes or rotating secrets

## MCP Tools

### Scope Management

| Tool | Purpose |
|------|---------|
| `create_or_update_secret_scope` | Idempotent scope creation (returns existing if present) |
| `list_secret_scopes` | List all scopes in the workspace |
| `delete_secret_scope` | Delete a scope and ALL its secrets (irreversible) |

### Secret Management

| Tool | Purpose |
|------|---------|
| `put_secret` | Create or update a secret (upsert, string or bytes) |
| `get_secret` | Check existence and byte length (value never exposed) |
| `list_secrets` | List secret keys in a scope (metadata only) |
| `delete_secret` | Delete a single secret from a scope |

## Quick Start

### 1. Create a Secret Scope

```python
create_or_update_secret_scope("my-app-secrets")
# {"scope": "my-app-secrets", "status": "created", "created": true}
```

### 2. Store a Secret

```python
put_secret("my-app-secrets", "api-key", string_value="sk-abc123...")
# {"scope": "my-app-secrets", "key": "api-key", "status": "created"}
```

### 3. Verify the Secret Exists

```python
get_secret("my-app-secrets", "api-key")
# {"scope": "my-app-secrets", "key": "api-key", "exists": true, "value_length": 42}
```

### 4. List All Secrets in a Scope

```python
list_secrets("my-app-secrets")
# [{"key": "api-key", "last_updated_timestamp": 1700000000000}, ...]
```

## Common Patterns

### Environment-Based Scopes

Organize secrets by environment for clean separation:

```python
# Create scopes per environment
create_or_update_secret_scope("myapp-dev")
create_or_update_secret_scope("myapp-staging")
create_or_update_secret_scope("myapp-prod")

# Store environment-specific credentials
put_secret("myapp-dev", "db-password", string_value="dev-password")
put_secret("myapp-prod", "db-password", string_value="prod-password")
```

### Secrets for Model Serving Endpoints

Store credentials that serving endpoints reference via `{{secrets/scope/key}}`:

```python
# Create scope for serving secrets
create_or_update_secret_scope("serving-credentials")

# Store the API key
put_secret("serving-credentials", "openai-key", string_value="sk-...")

# Reference in endpoint environment_vars:
# {"OPENAI_API_KEY": "{{secrets/serving-credentials/openai-key}}"}
```

### Audit Existing Secrets

Check what's configured before making changes:

```python
# List all scopes
list_secret_scopes()

# List keys in a scope
list_secrets("my-scope")

# Check a specific secret's size (helps verify it's set correctly)
get_secret("my-scope", "api-key")
# value_length helps verify: 0 = empty, ~40 = typical API key
```

### Cleanup

```python
# Delete a single secret
delete_secret("old-scope", "unused-key")

# Delete an entire scope (irreversible — deletes ALL secrets)
delete_secret_scope("deprecated-scope")
```

## Reference Files

| Topic | File | Description |
|-------|------|-------------|
| Security Patterns | [security-patterns.md](security-patterns.md) | Secret references in serving, notebooks, jobs, and ACL patterns |

## Common Issues

| Issue | Solution |
|-------|----------|
| **Scope name invalid** | Use alphanumeric, dashes, underscores, periods only (max 128 chars) |
| **Permission denied on scope** | Only scope creator has MANAGE by default. Use `initial_manage_principal="users"` to grant all users access |
| **Secret value not returned** | By design — `get_secret` returns metadata only. Use `dbutils.secrets.get()` in notebooks to read values |
| **Scope already exists** | `create_or_update_secret_scope` is idempotent — returns the existing scope |
| **Delete scope warning** | `delete_secret_scope` deletes ALL secrets in the scope. List secrets first to verify |

## Related Skills

- **[databricks-model-serving](../databricks-model-serving/SKILL.md)** - Serving endpoints that reference secrets via `{{secrets/scope/key}}`
- **[databricks-jobs](../databricks-jobs/SKILL.md)** - Jobs that use secrets for external API credentials

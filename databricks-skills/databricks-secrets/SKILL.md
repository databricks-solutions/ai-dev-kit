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

## MCP Tool

All secret operations use a single consolidated tool:

| Tool | Actions |
|------|---------|
| `manage_secrets(action=...)` | `create_scope`, `list_scopes`, `delete_scope`, `put`, `get`, `list`, `delete` |

### Parameters

| Parameter | Used by | Description |
|-----------|---------|-------------|
| `action` | All | One of the 7 actions above |
| `scope` | All except `list_scopes` | Secret scope name |
| `key` | `put`, `get`, `delete` | Secret key name |
| `value` | `put` | Secret value as string |
| `string_value` | `put` | Alternative to `value` |
| `bytes_value` | `put` | Base64-encoded bytes value |

## Quick Start

### 1. Create a Secret Scope

```python
manage_secrets(action="create_scope", scope="my-app-secrets")
# {"scope": "my-app-secrets", "status": "created", "created": true}
```

### 2. Store a Secret

```python
manage_secrets(action="put", scope="my-app-secrets", key="api-key", value="sk-abc123...")
# {"scope": "my-app-secrets", "key": "api-key", "status": "created"}
```

### 3. Verify the Secret Exists

```python
manage_secrets(action="get", scope="my-app-secrets", key="api-key")
# {"scope": "my-app-secrets", "key": "api-key", "exists": true, "value_length": 42}
```

### 4. List All Secrets in a Scope

```python
manage_secrets(action="list", scope="my-app-secrets")
# [{"key": "api-key", "last_updated_timestamp": 1700000000000}, ...]
```

## Common Patterns

### Environment-Based Scopes

Organize secrets by environment for clean separation:

```python
# Create scopes per environment
manage_secrets(action="create_scope", scope="myapp-dev")
manage_secrets(action="create_scope", scope="myapp-staging")
manage_secrets(action="create_scope", scope="myapp-prod")

# Store environment-specific credentials
manage_secrets(action="put", scope="myapp-dev", key="db-password", value="dev-password")
manage_secrets(action="put", scope="myapp-prod", key="db-password", value="prod-password")
```

### Secrets for Model Serving Endpoints

Store credentials that serving endpoints reference via `{{secrets/scope/key}}`:

```python
# Create scope for serving secrets
manage_secrets(action="create_scope", scope="serving-credentials")

# Store the API key
manage_secrets(action="put", scope="serving-credentials", key="openai-key", value="sk-...")

# Reference in endpoint environment_vars:
# {"OPENAI_API_KEY": "{{secrets/serving-credentials/openai-key}}"}
```

### Audit Existing Secrets

Check what's configured before making changes:

```python
# List all scopes
manage_secrets(action="list_scopes")

# List keys in a scope
manage_secrets(action="list", scope="my-scope")

# Check a specific secret's size (helps verify it's set correctly)
manage_secrets(action="get", scope="my-scope", key="api-key")
# value_length helps verify: 0 = empty, ~40 = typical API key
```

### Cleanup

```python
# Delete a single secret
manage_secrets(action="delete", scope="old-scope", key="unused-key")

# Delete an entire scope (irreversible — deletes ALL secrets)
manage_secrets(action="delete_scope", scope="deprecated-scope")
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
| **Secret value not returned** | By design — `get` action returns metadata only. Use `dbutils.secrets.get()` in notebooks to read values |
| **Scope already exists** | `create_scope` is idempotent — returns the existing scope |
| **Delete scope warning** | `delete_scope` deletes ALL secrets in the scope. List secrets first to verify |

## Related Skills

- **[databricks-model-serving](../databricks-model-serving/SKILL.md)** - Serving endpoints that reference secrets via `{{secrets/scope/key}}`
- **[databricks-jobs](../databricks-jobs/SKILL.md)** - Jobs that use secrets for external API credentials

# Detailed API Reference

Reference file for deep content that doesn't fit in SKILL.md (<500 lines target).

## When to Use

Use this reference when you need exhaustive API details, full parameter lists, or advanced configuration options that go beyond the common patterns in SKILL.md.

## API Methods

### method_name()

Creates or configures a resource.

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

result = w.some_api.method_name(
    name="my-resource",                    # Required: resource name
    description="What it does",            # Optional: human-readable description
    config={
        "setting1": True,                  # Default: False
        "setting2": "value",               # Options: "value", "other"
        "advanced_option": 42              # Only needed for specific use cases
    }
)
```

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | str | Yes | — | Resource name (lowercase, hyphens allowed) |
| `description` | str | No | `""` | Human-readable description |
| `config` | dict | No | `{}` | Configuration options |

**Returns:** `ResourceInfo` object with `.name`, `.id`, `.status` attributes.

## Common Variations

### With Custom Authentication

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient(profile="my-profile")
result = w.some_api.method_name(name="my-resource")
```

### With Error Handling

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound, PermissionDenied

w = WorkspaceClient()
try:
    result = w.some_api.method_name(name="my-resource")
except NotFound:
    print("Resource not found — check catalog and schema")
except PermissionDenied:
    print("Insufficient permissions — grant via Unity Catalog")
```

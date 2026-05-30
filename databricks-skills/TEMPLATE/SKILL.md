---
name: your-skill-name
description: "Brief description of what this skill does. Use when [specific scenario 1], [specific scenario 2], or when the user mentions [keyword1], [keyword2], [keyword3]."
---

# Skill Title

One-paragraph summary of what this skill covers and why it exists.

## When to Use

Use this skill when:
- Building or configuring [specific feature]
- Working with [specific API or tool]
- The user mentions [domain keywords]

## Overview

Brief conceptual summary. Tables work well for comparing options:

| Component | Description | When to Use |
|-----------|-------------|-------------|
| **Option A** | What it does | Best for X |
| **Option B** | What it does | Best for Y |

## Quick Start

The simplest, most common use case. Must be complete and copy-pasteable:

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Example: the most common operation for this skill
result = w.some_api.create(
    name="my-resource",
    config={"key": "value"}
)
print(f"Created: {result.name}")
```

## Common Patterns

### Pattern 1: Basic Usage

```python
# Description of what this pattern does
w.some_api.basic_operation(
    param1="value1",
    param2="value2"
)
```

### Pattern 2: Advanced Configuration

```python
# When you need more control over behavior
w.some_api.advanced_operation(
    param1="value1",
    advanced_config={
        "setting1": True,
        "setting2": "custom"
    }
)
```

## Reference Files

Link to supporting documentation if SKILL.md would exceed ~400 lines:
- [detailed-api-reference.md](detailed-api-reference.md) - Exhaustive API parameters and options
- [migration-guide.md](migration-guide.md) - Migrating from deprecated patterns

## Common Issues

| Issue | Solution |
|-------|----------|
| **`PERMISSION_DENIED` error** | Grant required permissions via Unity Catalog |
| **Resource not found** | Verify the resource exists in the correct catalog/schema |

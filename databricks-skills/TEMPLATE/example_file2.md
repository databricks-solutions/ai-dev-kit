# Migration Guide

Reference file for migration patterns from deprecated APIs or older approaches.

## When to Use

Use this reference when migrating from legacy patterns or when Claude detects deprecated API usage in existing code.

## Deprecated Patterns

### Old Pattern → New Pattern

**Before (deprecated):**
```python
# Do NOT use — this API was deprecated in version X.Y
old_api.legacy_method(param="value")
```

**After (current):**
```python
# Use this instead
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
w.new_api.current_method(param="value")
```

**Why it changed:** Brief explanation of why the API was updated and what benefits the new approach provides.

### Another Migration

**Before:**
```sql
-- Deprecated: PARTITION BY is no longer recommended
CREATE TABLE my_table
PARTITION BY (date_col)
AS SELECT * FROM source;
```

**After:**
```sql
-- Use CLUSTER BY for better performance with liquid clustering
CREATE TABLE my_table
CLUSTER BY (date_col)
AS SELECT * FROM source;
```

## Migration Checklist

| Old Pattern | New Pattern | Notes |
|-------------|-------------|-------|
| `old_function()` | `new_function()` | Direct replacement |
| `@dlt.table` | `@dp.table` | Requires import change |
| `PARTITION BY` | `CLUSTER BY` | Liquid clustering, better performance |

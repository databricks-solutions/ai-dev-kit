# AI Search Filtering Reference

Filter syntax for Databricks AI Search. Standard endpoints use a Python dict; Storage-Optimized endpoints use a SQL-like string. Both are passed to the `filters` parameter of `index.similarity_search()`.

## Quick Reference

| Operation | Standard (dict) | Storage-Optimized (SQL string) |
|-----------|----------------|-------------------------------|
| Exact match | `{"col": "val"}` | `col = 'val'` |
| Negation | `{"col NOT": "val"}` | `col != 'val'` |
| Match any in list | `{"col": ["v1", "v2"]}` | `col IN ('v1', 'v2')` |
| Greater than | `{"col >": 100}` | `col > 100` |
| Less than | `{"col <": 100}` | `col < 100` |
| Range | `{"col >=": 10, "col <=": 50}` | `col >= 10 AND col <= 50` |
| AND | Multiple dict keys | `col1 = 'v' AND col2 > 10` |
| Cross-field OR | `{"col1 OR col2 <=": ["v1", v2]}` | `col1 = 'v' OR col2 > 10` |
| LIKE | `{"col LIKE": "token"}` | `col LIKE 'val%'` |
| Boolean | `{"col": True}` | `col IS TRUE` |
| Timestamp | `{"col >": "2024-01-01T00:00:00Z"}` | `col > TO_TIMESTAMP('2024-01-01T00:00:00')` |

---

## Standard Endpoints (Dictionary Syntax)

### String columns

```python
# Exact match
filters={"make": "Toyota"}

# Negation
filters={"make NOT": "Ford"}

# Match any value (OR logic within one column)
filters={"make": ["Toyota", "Honda"]}

# Token-based LIKE — matches whole tokens only (not SQL wildcards)
filters={"description LIKE": "hybrid"}

# JSON field pattern using list of dicts for multiple conditions
filters=[{"specs LIKE": '%"drivetrain":"AWD"%'}, {"price <": 50000}]
```

### Numeric columns

```python
# Comparison operators
filters={"price >": 40000}
filters={"price <=": 55000}

# Range (AND logic via multiple keys)
filters={"price >=": 30000, "price <=": 55000}

# Integer exact match
filters={"year": 2024}
```

### Boolean columns

```python
filters={"in_stock": True}
filters={"in_stock": False}
```

### Timestamp columns

```python
# After a date
filters={"listed_at >": "2024-01-01T00:00:00Z"}

# Date range
filters={"listed_at >=": "2024-01-01T00:00:00Z", "listed_at <": "2024-04-01T00:00:00Z"}
```

### Array columns

Array columns support primitive types (e.g. `ARRAY<STRING>`, `ARRAY<INT>`). `ARRAY<STRUCT>` is not supported.

```python
# Contains a value
filters={"body_type": "sedan"}

# Contains any of these values
filters={"body_type": ["hybrid", "electric"]}
```

### AND and OR logic

```python
# AND: use multiple keys in the dict
filters={"make": "BMW", "price >": 60000}

# Cross-field OR
filters={"make OR price <=": ["Tesla", 30000]}
```

### Standard endpoint limitations

- **LIKE is token-based only** — matches whole tokens, not SQL wildcards. `{"col LIKE": "hybrid"}` matches documents containing the token "hybrid"; `%` patterns are not supported.
- **No BETWEEN** — use two keys instead: `{"price >=": 30000, "price <=": 55000}`
- **No SQL functions** in filter values
- **No nested JSON value extraction**
- **Duplicate dict keys are silently dropped** — use a list of dicts for multiple conditions on the same column

---

## Storage-Optimized Endpoints (SQL String Syntax)

### String columns

```python
# Exact match
filters="make = 'Toyota'"

# Negation
filters="make != 'Ford'"

# IN list
filters="make IN ('Toyota', 'Honda')"

# LIKE with SQL wildcards
filters="color LIKE 'bl%'"
```

### Numeric columns

```python
filters="price > 40000"
filters="price >= 30000 AND price <= 55000"
```

### Boolean columns

```python
filters="in_stock IS TRUE"
```

### Timestamp columns

Timestamp values must be wrapped in `TO_TIMESTAMP()`:

```python
filters="listed_at > TO_TIMESTAMP('2024-03-01T00:00:00')"
```

### AND and OR logic

```python
# AND
filters="make = 'BMW' AND price > 60000"

# OR with grouping
filters="make = 'Tesla' OR (make = 'BMW' AND price > 60000)"
```

### Storage-Optimized endpoint limitations

- **Array columns not supported** — `ARRAY_CONTAINS` is not available. Workaround: concatenate array values into a string column and use `LIKE`.
- **Timestamps require `TO_TIMESTAMP()`** — bare string dates are not accepted.
- **No JSON function extraction** in filter expressions.

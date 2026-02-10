# Python SDK Patterns for ABAC Policies

Databricks Python SDK patterns for managing ABAC policies via `WorkspaceClient.policies`.

**SDK Docs:** https://databricks-sdk-py.readthedocs.io/en/latest/
**ABAC Docs:** https://docs.databricks.com/data-governance/unity-catalog/abac/policies

---

## Setup

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()  # Auto-detects credentials
```

---

## List Policies

List ABAC policies on a securable (catalog, schema, or table).

```python
# List all policies on a catalog
policies = w.policies.list_policies(
    on_securable_type="CATALOG",
    on_securable_fullname="my_catalog",
    include_inherited=True,
)

for p in policies:
    print(f"{p.name}: {p.policy_type} on {p.on_securable_fullname}")

# List policies on a schema
policies = w.policies.list_policies(
    on_securable_type="SCHEMA",
    on_securable_fullname="my_catalog.my_schema",
    include_inherited=True,
)

# List policies on a specific table
policies = w.policies.list_policies(
    on_securable_type="TABLE",
    on_securable_fullname="my_catalog.my_schema.my_table",
    include_inherited=True,
)
```

### Filtering by Policy Type

```python
policies = w.policies.list_policies(
    on_securable_type="SCHEMA",
    on_securable_fullname="my_catalog.my_schema",
    include_inherited=True,
)

column_masks = [p for p in policies if p.policy_type == "COLUMN_MASK"]
row_filters = [p for p in policies if p.policy_type == "ROW_FILTER"]
```

### Extracting Policy Details

```python
for p in policies:
    p_dict = p.as_dict() if hasattr(p, "as_dict") else {}
    print({
        "name": p_dict.get("name"),
        "policy_type": p_dict.get("policy_type"),
        "to_principals": p_dict.get("to_principals", []),
        "except_principals": p_dict.get("except_principals", []),
        "on_securable_type": p_dict.get("on_securable_type"),
        "on_securable_fullname": p_dict.get("on_securable_fullname"),
        "column_mask": p_dict.get("column_mask"),
        "row_filter": p_dict.get("row_filter"),
        "match_columns": p_dict.get("match_columns", []),
    })
```

---

## Get Policy

Retrieve a specific policy by name and securable.

```python
policy = w.policies.get_policy(
    name="mask_pii_ssn",
    on_securable_type="SCHEMA",
    on_securable_fullname="my_catalog.my_schema",
)

print(f"Policy: {policy.name}")
print(f"Type: {policy.policy_type}")
print(f"Principals: {policy.to_principals}")
print(f"Except: {policy.except_principals}")
```

---

## Create Policy

### Column Mask Policy

```python
from databricks.sdk.service.catalog import (
    CreatePolicy,
    ColumnMask,
    MatchColumns,
)

policy = w.policies.create_policy(
    name="mask_pii_ssn",
    policy_type="COLUMN_MASK",
    on_securable_type="SCHEMA",
    on_securable_fullname="my_catalog.my_schema",
    for_securable_type="TABLE",
    to_principals=["analysts", "data_scientists"],
    except_principals=["gov_admin"],
    comment="Mask SSN columns for analyst groups",
    column_mask=ColumnMask(
        function_name="my_catalog.my_schema.mask_ssn",
    ),
    match_columns=[
        MatchColumns(
            tag_name="pii_type",
            tag_value="ssn",
        )
    ],
)
print(f"Created policy: {policy.name}")
```

### Row Filter Policy

```python
from databricks.sdk.service.catalog import (
    CreatePolicy,
    RowFilter,
    MatchColumns,
)

policy = w.policies.create_policy(
    name="filter_eu_data",
    policy_type="ROW_FILTER",
    on_securable_type="CATALOG",
    on_securable_fullname="my_catalog",
    for_securable_type="TABLE",
    to_principals=["us_team"],
    except_principals=["gov_admin"],
    comment="Filter EU rows for US team",
    row_filter=RowFilter(
        function_name="my_catalog.my_schema.is_not_eu_region",
    ),
    match_columns=[
        MatchColumns(
            tag_name="region",
            tag_value="eu",
        )
    ],
)
print(f"Created policy: {policy.name}")
```

### Important: Always Include `gov_admin`

Every policy **MUST** include `"gov_admin"` in `except_principals`:

```python
# CORRECT
except_principals=["gov_admin"]

# CORRECT - additional admin groups
except_principals=["gov_admin", "platform_admins"]

# WRONG - missing gov_admin
except_principals=["platform_admins"]  # gov_admin must be included!
```

---

## Update Policy

Update principals or comment on an existing policy.

```python
updated = w.policies.update_policy(
    name="mask_pii_ssn",
    on_securable_type="SCHEMA",
    on_securable_fullname="my_catalog.my_schema",
    to_principals=["analysts", "data_scientists", "new_team"],
    except_principals=["gov_admin", "senior_admins"],
    comment="Updated: added new_team to masked principals",
)
print(f"Updated policy: {updated.name}")
```

> **Note:** To change the UDF, tag matching, or scope, you must drop and recreate the policy. `update_policy` only modifies principals and comment.

---

## Delete Policy

```python
w.policies.delete_policy(
    name="mask_pii_ssn",
    on_securable_type="SCHEMA",
    on_securable_fullname="my_catalog.my_schema",
)
print("Policy deleted")
```

---

## Error Handling

```python
from databricks.sdk.errors import NotFound, PermissionDenied, BadRequest

try:
    policy = w.policies.get_policy(
        name="nonexistent_policy",
        on_securable_type="SCHEMA",
        on_securable_fullname="my_catalog.my_schema",
    )
except NotFound:
    print("Policy not found")
except PermissionDenied:
    print("Insufficient permissions - need MANAGE on securable")
except BadRequest as e:
    print(f"Invalid request: {e}")
```

---

## Common Patterns

### List All Policies in a Catalog with Counts

```python
def get_policy_summary(w, catalog: str):
    """Get a summary of all ABAC policies in a catalog."""
    policies = list(w.policies.list_policies(
        on_securable_type="CATALOG",
        on_securable_fullname=catalog,
        include_inherited=True,
    ))

    column_masks = [p for p in policies if p.policy_type == "COLUMN_MASK"]
    row_filters = [p for p in policies if p.policy_type == "ROW_FILTER"]

    return {
        "total": len(policies),
        "column_masks": len(column_masks),
        "row_filters": len(row_filters),
        "policies": [p.as_dict() for p in policies],
    }
```

### Check Policy Quotas Before Creating

```python
def check_quota(w, securable_type: str, securable_fullname: str):
    """Check if policy quota allows creating a new policy."""
    quotas = {"CATALOG": 10, "SCHEMA": 10, "TABLE": 5}
    max_policies = quotas.get(securable_type, 10)

    existing = list(w.policies.list_policies(
        on_securable_type=securable_type,
        on_securable_fullname=securable_fullname,
    ))

    # Count only direct policies (not inherited)
    direct = [p for p in existing
              if p.on_securable_fullname == securable_fullname]

    return {
        "current": len(direct),
        "max": max_policies,
        "can_create": len(direct) < max_policies,
    }
```

### Fetch Policies Without Cache (Direct API)

```python
def fetch_policies_direct(
    w,
    catalog: str,
    schema: str = None,
    table: str = None,
):
    """Fetch policies directly from REST API."""
    if table and schema:
        securable_type = "TABLE"
        securable_name = f"{catalog}.{schema}.{table}"
    elif schema:
        securable_type = "SCHEMA"
        securable_name = f"{catalog}.{schema}"
    else:
        securable_type = "CATALOG"
        securable_name = catalog

    policies = w.policies.list_policies(
        on_securable_type=securable_type,
        on_securable_fullname=securable_name,
        include_inherited=True,
    )

    results = []
    for p in policies:
        p_dict = p.as_dict() if hasattr(p, "as_dict") else {}
        results.append({
            "name": p_dict.get("name"),
            "policy_type": p_dict.get("policy_type"),
            "to_principals": p_dict.get("to_principals", []),
            "except_principals": p_dict.get("except_principals", []),
            "on_securable_type": p_dict.get("on_securable_type"),
            "on_securable_fullname": p_dict.get("on_securable_fullname"),
            "column_mask": p_dict.get("column_mask"),
            "row_filter": p_dict.get("row_filter"),
            "match_columns": p_dict.get("match_columns", []),
        })
    return results
```

---

## Async Usage (FastAPI, etc.)

The Databricks SDK is synchronous. In async applications, wrap calls with `asyncio.to_thread()`:

```python
import asyncio

async def list_policies_async(w, catalog: str):
    return await asyncio.to_thread(
        lambda: list(w.policies.list_policies(
            on_securable_type="CATALOG",
            on_securable_fullname=catalog,
            include_inherited=True,
        ))
    )

async def create_policy_async(w, **kwargs):
    return await asyncio.to_thread(
        w.policies.create_policy,
        **kwargs,
    )
```

# MCP Tools Reference for ABAC Policy Management

Reference for the MCP tools that manage ABAC policies. Core policy operations are implemented in
`databricks_tools_core.unity_catalog.abac_policies`. Discovery helpers delegate to existing
`unity_catalog` modules where possible.

**Implementation:** `databricks-tools-core/databricks_tools_core/unity_catalog/abac_policies.py`

---

## Discovery Tools

### `list_abac_policies`

List ABAC policies on a catalog, schema, or table.

**Implementation:** `unity_catalog.abac_policies.list_abac_policies`

```python
from databricks_tools_core.unity_catalog import list_abac_policies

list_abac_policies(
    securable_type: str,       # "CATALOG", "SCHEMA", or "TABLE"
    securable_fullname: str,   # e.g., "my_catalog.my_schema"
    include_inherited: bool = True,
    policy_type: str = None,   # "COLUMN_MASK" or "ROW_FILTER" (optional filter)
)
```

**Returns:**
```json
{
  "success": true,
  "securable_type": "SCHEMA",
  "securable_fullname": "my_catalog.my_schema",
  "policy_count": 3,
  "policies": [
    {
      "name": "mask_pii_ssn",
      "policy_type": "COLUMN_MASK",
      "to_principals": ["analysts"],
      "except_principals": ["gov_admin"],
      "on_securable_fullname": "my_catalog.my_schema",
      "column_mask": {"function_name": "my_catalog.my_schema.mask_ssn"},
      "match_columns": [{"tag_name": "pii_type", "tag_value": "ssn"}]
    }
  ]
}
```

### `get_abac_policy`

Get details for a specific policy by name.

**Implementation:** `unity_catalog.abac_policies.get_abac_policy`

```python
from databricks_tools_core.unity_catalog import get_abac_policy

get_abac_policy(
    policy_name: str,          # Policy name
    securable_type: str,       # "CATALOG", "SCHEMA", or "TABLE"
    securable_fullname: str,   # Fully qualified securable name
)
```

**Returns:**
```json
{
  "success": true,
  "policy": {
    "name": "mask_pii_ssn",
    "policy_type": "COLUMN_MASK",
    "comment": "Mask SSN columns for analysts",
    "to_principals": ["analysts", "data_scientists"],
    "except_principals": ["gov_admin"],
    "on_securable_type": "SCHEMA",
    "on_securable_fullname": "my_catalog.my_schema",
    "for_securable_type": "TABLE",
    "column_mask": {"function_name": "my_catalog.my_schema.mask_ssn"},
    "match_columns": [{"tag_name": "pii_type", "tag_value": "ssn"}],
    "created_at": "2025-01-15T10:30:00Z",
    "created_by": "admin@company.com",
    "updated_at": "2025-01-20T14:00:00Z",
    "updated_by": "admin@company.com"
  }
}
```

### `get_table_policies`

Get column masks and row filters for a specific table via Unity Catalog API.

**Implementation:** `unity_catalog.abac_policies.get_table_policies`

```python
from databricks_tools_core.unity_catalog import get_table_policies

get_table_policies(
    catalog: str,
    schema: str,
    table: str,
)
```

**Returns:**
```json
{
  "success": true,
  "table": "my_catalog.my_schema.my_table",
  "column_masks": [
    {
      "column_name": "ssn",
      "mask_function": "my_catalog.my_schema.mask_ssn",
      "using_column_names": []
    }
  ],
  "row_filters": [
    {
      "filter_function": "my_catalog.my_schema.is_not_eu_region",
      "using_column_names": ["region"]
    }
  ]
}
```

### `get_masking_functions`

List masking UDFs in a schema.

**Implementation:** `unity_catalog.abac_policies.get_masking_functions`

```python
from databricks_tools_core.unity_catalog import get_masking_functions

get_masking_functions(
    catalog: str,
    schema: str,
)
```

**Returns:**
```json
{
  "success": true,
  "catalog": "my_catalog",
  "schema": "my_schema",
  "function_count": 3,
  "functions": [
    {
      "name": "mask_ssn",
      "full_name": "my_catalog.my_schema.mask_ssn",
      "return_type": "STRING",
      "comment": "Masks SSN showing only last 4 digits",
      "is_deterministic": true
    }
  ]
}
```

### `get_schema_info`

Get schema metadata via Unity Catalog API.

**Implementation:** Delegates to existing `unity_catalog.schemas.get_schema`

```python
from databricks_tools_core.unity_catalog import get_schema

get_schema(
    catalog_name: str,
    schema_name: str,
)
```

### `get_catalog_info`

Get catalog metadata via Unity Catalog API.

**Implementation:** Delegates to existing `unity_catalog.catalogs.get_catalog`

```python
from databricks_tools_core.unity_catalog import get_catalog

get_catalog(
    catalog_name: str,
)
```

### `get_column_tags_api`

Get column-level tags via the Tags API.

**Implementation:** Delegates to existing `unity_catalog.tags.query_column_tags`

```python
from databricks_tools_core.unity_catalog import query_column_tags

query_column_tags(
    catalog_filter: str,    # Filter by catalog name
    table_name: str = None, # Filter by table name
    tag_name: str = None,   # Filter by tag name
    tag_value: str = None,  # Filter by tag value
    limit: int = 100,
)
```

### `list_table_policies_in_schema`

List all tables in a schema with their column masks and row filters.

**Implementation:** Compose `unity_catalog.tables.list_tables` + `unity_catalog.abac_policies.get_table_policies`

```python
from databricks_tools_core.unity_catalog import list_tables, get_table_policies

# List all tables, then get policies for each
tables = list_tables(catalog_name=catalog, schema_name=schema)
for t in tables["tables"]:
    policies = get_table_policies(catalog=catalog, schema=schema, table=t["name"])
```

---

## Quota Check

### `check_policy_quota`

Check if the policy quota allows creating a new policy on a securable.

**Implementation:** `unity_catalog.abac_policies.check_policy_quota`

```python
from databricks_tools_core.unity_catalog import check_policy_quota

check_policy_quota(
    securable_type: str,       # "CATALOG", "SCHEMA", or "TABLE"
    securable_fullname: str,   # Fully qualified securable name
)
```

**Returns:**
```json
{
  "success": true,
  "securable_type": "SCHEMA",
  "securable_fullname": "my_catalog.my_schema",
  "current": 3,
  "max": 10,
  "can_create": true
}
```

Policy quotas: CATALOG=10, SCHEMA=10, TABLE=5.

---

## Preview Tool (Human-in-the-Loop Gate)

### `preview_policy_changes`

Preview policy changes without executing. This is the critical human-in-the-loop gate.

**Implementation:** `unity_catalog.abac_policies.preview_policy_changes`

```python
from databricks_tools_core.unity_catalog import preview_policy_changes

preview_policy_changes(
    action: str,               # "CREATE", "UPDATE", or "DELETE"
    policy_name: str,
    securable_type: str,       # "CATALOG", "SCHEMA", or "TABLE"
    securable_fullname: str,
    policy_type: str = None,   # "COLUMN_MASK" or "ROW_FILTER" (for CREATE)
    to_principals: list = None,
    except_principals: list = None,
    function_name: str = None,
    tag_name: str = None,
    tag_value: str = None,
    comment: str = None,
)
```

**Returns:**
```json
{
  "success": true,
  "action": "CREATE",
  "preview": {
    "policy_name": "mask_pii_ssn",
    "policy_type": "COLUMN_MASK",
    "securable": "SCHEMA my_catalog.my_schema",
    "to_principals": ["analysts"],
    "except_principals": ["gov_admin"],
    "function": "my_catalog.my_schema.mask_ssn",
    "tag_match": "hasTagValue('pii_type', 'ssn')",
    "equivalent_sql": "CREATE OR REPLACE POLICY mask_pii_ssn\nON SCHEMA my_catalog.my_schema\n..."
  },
  "warnings": [],
  "requires_approval": true,
  "message": "Review the preview above. Reply 'approve' to execute."
}
```

**Usage in workflow:**

1. Call `preview_policy_changes` with proposed changes
2. Present preview to user
3. Wait for explicit approval
4. Only then call `create_abac_policy`, `update_abac_policy`, or `delete_abac_policy`

---

## Management Tools

### `create_abac_policy`

Create a new ABAC policy (COLUMN_MASK or ROW_FILTER).

**Implementation:** `unity_catalog.abac_policies.create_abac_policy`

```python
from databricks_tools_core.unity_catalog import create_abac_policy

create_abac_policy(
    policy_name: str,
    policy_type: str,          # "COLUMN_MASK" or "ROW_FILTER"
    securable_type: str,       # "CATALOG", "SCHEMA", or "TABLE"
    securable_fullname: str,
    function_name: str,        # Fully qualified UDF name
    to_principals: list,       # Users/groups the policy applies to
    tag_name: str,             # Tag key to match
    tag_value: str = None,     # Tag value (optional, uses hasTag vs hasTagValue)
    except_principals: list = None,  # Excluded principals
    comment: str = "",
)
```

**Returns:**
```json
{
  "success": true,
  "policy_name": "mask_pii_ssn",
  "action": "created",
  "details": {
    "policy_type": "COLUMN_MASK",
    "on_securable": "SCHEMA my_catalog.my_schema",
    "function": "my_catalog.my_schema.mask_ssn",
    "to_principals": ["analysts"],
    "except_principals": ["gov_admin"],
    "tag_match": "pii_type=ssn"
  },
  "policy": { ... }
}
```

> **Note:** Callers should include appropriate admin groups in `except_principals` to protect administrator access.

### `update_abac_policy`

Update an existing policy's principals or comment.

**Implementation:** `unity_catalog.abac_policies.update_abac_policy`

```python
from databricks_tools_core.unity_catalog import update_abac_policy

update_abac_policy(
    policy_name: str,
    securable_type: str,
    securable_fullname: str,
    to_principals: list = None,
    except_principals: list = None,
    comment: str = None,
)
```

**Returns:**
```json
{
  "success": true,
  "policy_name": "mask_pii_ssn",
  "action": "updated",
  "changes": {
    "to_principals": ["analysts", "data_scientists", "new_team"],
    "comment": "Updated: added new_team"
  },
  "policy": { ... }
}
```

> **Note:** To change the UDF, tag matching, or scope, drop and recreate the policy.

### `delete_abac_policy`

Delete an ABAC policy.

**Implementation:** `unity_catalog.abac_policies.delete_abac_policy`

```python
from databricks_tools_core.unity_catalog import delete_abac_policy

delete_abac_policy(
    policy_name: str,
    securable_type: str,
    securable_fullname: str,
)
```

**Returns:**
```json
{
  "success": true,
  "policy_name": "mask_pii_ssn",
  "action": "deleted"
}
```

---

## Human-in-the-Loop Workflow Example

Complete workflow using the implemented functions:

```python
from databricks_tools_core.unity_catalog import (
    list_abac_policies,
    query_column_tags,
    get_masking_functions,
    check_policy_quota,
    preview_policy_changes,
    create_abac_policy,
    get_abac_policy,
)

# Step 1: ANALYZE — discover current state
policies = list_abac_policies(securable_type="SCHEMA", securable_fullname="prod.finance")
tags = query_column_tags(catalog_filter="prod", table_name="customers")
udfs = get_masking_functions(catalog="prod", schema="finance")

# Step 2: RECOMMEND — agent generates policy recommendations based on tags and UDFs

# Step 3: CHECK QUOTA — ensure we can create a new policy
quota = check_policy_quota(securable_type="SCHEMA", securable_fullname="prod.finance")
assert quota["can_create"], f"Quota exceeded: {quota['current']}/{quota['max']}"

# Step 4: PREVIEW — generate SQL for human review (no changes made)
preview = preview_policy_changes(
    action="CREATE",
    policy_name="mask_ssn_finance",
    securable_type="SCHEMA",
    securable_fullname="prod.finance",
    policy_type="COLUMN_MASK",
    function_name="prod.finance.mask_ssn",
    to_principals=["analysts"],
    tag_name="pii_type",
    tag_value="ssn",
)
# → Present preview["preview"]["equivalent_sql"] to user

# Step 5: APPROVE — human reviews preview and replies "approve"

# Step 6: EXECUTE — create the policy
result = create_abac_policy(
    policy_name="mask_ssn_finance",
    policy_type="COLUMN_MASK",
    securable_type="SCHEMA",
    securable_fullname="prod.finance",
    function_name="prod.finance.mask_ssn",
    to_principals=["analysts"],
    tag_name="pii_type",
    tag_value="ssn",
)

# Step 7: VERIFY — confirm policy was created
policy = get_abac_policy(
    policy_name="mask_ssn_finance",
    securable_type="SCHEMA",
    securable_fullname="prod.finance",
)
```

---

## Error Handling

| Error | Cause | Solution |
|-------|-------|----------|
| `POLICY_QUOTA_EXCEEDED` | Too many policies on scope | Use `check_policy_quota` first; consolidate or use broader scope |
| `INVALID_TAG_VALUE` | Tag value not in governed tag's allowed values | Check governed tag config in UI |
| `UDF_NOT_FOUND` | Masking UDF doesn't exist | Create UDF first via `create_security_function`, use fully qualified name |
| `POLICY_ALREADY_EXISTS` | Duplicate policy name | Use different name or `delete_abac_policy` first |
| `INSUFFICIENT_PERMISSIONS` | Missing `MANAGE` on securable | `grant_privileges` with MANAGE |
| `INVALID_SECURABLE_TYPE` | Wrong securable type string | Use `"CATALOG"`, `"SCHEMA"`, or `"TABLE"` |
| `PRINCIPAL_NOT_FOUND` | Principal group doesn't exist | Verify group exists on the workspace |

---

## Implementation Map

| MCP Tool | Implementation | Module |
|----------|---------------|--------|
| `list_abac_policies` | `list_abac_policies()` | `abac_policies` |
| `get_abac_policy` | `get_abac_policy()` | `abac_policies` |
| `get_table_policies` | `get_table_policies()` | `abac_policies` |
| `get_masking_functions` | `get_masking_functions()` | `abac_policies` |
| `check_policy_quota` | `check_policy_quota()` | `abac_policies` |
| `get_schema_info` | `get_schema()` | `schemas` |
| `get_catalog_info` | `get_catalog()` | `catalogs` |
| `get_column_tags_api` | `query_column_tags()` | `tags` |
| `list_table_policies_in_schema` | `list_tables()` + `get_table_policies()` | `tables` + `abac_policies` |
| `preview_policy_changes` | `preview_policy_changes()` | `abac_policies` |
| `create_abac_policy` | `create_abac_policy()` | `abac_policies` |
| `update_abac_policy` | `update_abac_policy()` | `abac_policies` |
| `delete_abac_policy` | `delete_abac_policy()` | `abac_policies` |

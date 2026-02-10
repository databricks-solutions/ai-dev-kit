# MCP Tools Reference for ABAC Policy Management

Reference for the 12 MCP tools that manage ABAC policies via the Databricks Python SDK. These tools are registered in the UCABAC MCP server.

---

## Discovery Tools

### `list_abac_policies`

List ABAC policies on a catalog, schema, or table.

```python
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

```python
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

```python
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

```python
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

```python
get_schema_info(
    catalog: str,
    schema: str,
)
```

### `get_catalog_info`

Get catalog metadata via Unity Catalog API.

```python
get_catalog_info(
    catalog: str,
)
```

### `get_column_tags_api`

Get column-level tags via the Tags API.

```python
get_column_tags_api(
    catalog: str,
    schema: str,
    table: str,
)
```

### `list_table_policies_in_schema`

List all tables in a schema with their column masks and row filters.

```python
list_table_policies_in_schema(
    catalog: str,
    schema: str,
)
```

---

## Preview Tool (Human-in-the-Loop Gate)

### `preview_policy_changes`

Preview policy changes without executing. This is the critical human-in-the-loop gate.

```python
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

```python
create_abac_policy(
    policy_name: str,
    policy_type: str,          # "COLUMN_MASK" or "ROW_FILTER"
    securable_type: str,       # "CATALOG", "SCHEMA", or "TABLE"
    securable_fullname: str,
    function_name: str,        # Fully qualified UDF name
    to_principals: list,       # Users/groups the policy applies to
    tag_name: str,             # Tag key to match
    tag_value: str = None,     # Tag value (optional, uses hasTag vs hasTagValue)
    except_principals: list = None,  # Excluded principals (gov_admin auto-added)
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
    "except_principals": ["gov_admin"]
  }
}
```

> **Note:** `gov_admin` is automatically added to `except_principals` if not already present.

### `update_abac_policy`

Update an existing policy's principals or comment.

```python
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
  }
}
```

> **Note:** To change the UDF, tag matching, or scope, drop and recreate the policy.

### `delete_abac_policy`

Delete an ABAC policy.

```python
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

Complete workflow using MCP tools:

```
Step 1: ANALYZE
─────────────────────────────────
→ list_abac_policies(securable_type="SCHEMA", securable_fullname="prod.finance")
→ get_column_tags_api(catalog="prod", schema="finance", table="customers")
→ get_masking_functions(catalog="prod", schema="finance")

Step 2: RECOMMEND
─────────────────────────────────
→ Agent generates policy recommendations based on discovered tags and UDFs

Step 3: PREVIEW
─────────────────────────────────
→ preview_policy_changes(
      action="CREATE",
      policy_name="mask_ssn_finance",
      securable_type="SCHEMA",
      securable_fullname="prod.finance",
      policy_type="COLUMN_MASK",
      function_name="prod.finance.mask_ssn",
      to_principals=["analysts"],
      tag_name="pii_type",
      tag_value="ssn"
  )

Step 4: APPROVE
─────────────────────────────────
→ Human reviews preview and replies "approve"

Step 5: EXECUTE
─────────────────────────────────
→ create_abac_policy(
      policy_name="mask_ssn_finance",
      policy_type="COLUMN_MASK",
      securable_type="SCHEMA",
      securable_fullname="prod.finance",
      function_name="prod.finance.mask_ssn",
      to_principals=["analysts"],
      tag_name="pii_type",
      tag_value="ssn"
  )

Step 6: VERIFY
─────────────────────────────────
→ get_abac_policy(
      policy_name="mask_ssn_finance",
      securable_type="SCHEMA",
      securable_fullname="prod.finance"
  )
```

---

## Error Handling

| Error | Cause | Solution |
|-------|-------|----------|
| `POLICY_QUOTA_EXCEEDED` | Too many policies on scope | Consolidate policies or use broader scope |
| `INVALID_TAG_VALUE` | Tag value not in governed tag's allowed values | Check governed tag config in UI |
| `UDF_NOT_FOUND` | Masking UDF doesn't exist | Create UDF first, use fully qualified name |
| `POLICY_ALREADY_EXISTS` | Duplicate policy name | Use different name or delete existing first |
| `INSUFFICIENT_PERMISSIONS` | Missing `MANAGE` on securable | Grant `MANAGE` permission |
| `INVALID_SECURABLE_TYPE` | Wrong securable type string | Use `"CATALOG"`, `"SCHEMA"`, or `"TABLE"` |
| `gov_admin not in except_principals` | Safety check failed | Always include `gov_admin` in except list |

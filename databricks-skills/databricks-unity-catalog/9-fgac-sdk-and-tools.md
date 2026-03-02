# FGAC Policy SDK & MCP Tools

Python SDK patterns and MCP tool reference for managing FGAC policies in Unity Catalog.

**SDK Docs:** https://databricks-sdk-py.readthedocs.io/en/latest/
**FGAC Docs:** https://docs.databricks.com/data-governance/unity-catalog/abac/policies

---

## Policy Scopes

`on_securable_type` sets the **scope** of the policy. `for_securable_type` is always `TABLE`.

| Scope | `on_securable_type` | `on_securable_fullname` | Effect |
|---|---|---|---|
| Catalog | `CATALOG` | `"my_catalog"` | Applies to all tables in the catalog |
| Schema | `SCHEMA` | `"my_catalog.my_schema"` | Applies to all tables in the schema |
| Table | `TABLE` | `"my_catalog.my_schema.my_table"` | Applies to a single table |

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

## Guardrails

FGAC mutating operations (`create`, `update`, `delete`) enforce two programmatic guardrails:

### Approval Token

Every mutating call **requires** a valid `approval_token` obtained from `preview_policy_changes()`. The token is an HMAC-SHA256 signature binding the previewed parameters to a timestamp.

- Token TTL: **10 minutes** (configurable via `_TOKEN_TTL_SECONDS`)
- Parameters must match exactly between preview and mutation
- Action mapping: preview `CREATE` → mutation `create`, `UPDATE` → `update`, `DELETE` → `delete`

> **Design note:** The approval token ensures mutations match what was previewed and prevents parameter tampering, but it does **not** guarantee a human reviewed the preview. Human-in-the-loop confirmation depends on the MCP client — for example, Claude Code prompts the user to approve each tool call, creating a natural pause between preview and mutation. If using a client that auto-approves tool calls, consider adding explicit confirmation logic.

### Admin Group Check

The caller must be a member of the configured admin group before any mutating operation (create/update/delete) is allowed. Membership is verified via `w.current_user.me().groups`.

Set the `FGAC_ADMIN_GROUP` environment variable to your workspace admin group name:

```bash
# Example: use your workspace's governance admin group
export FGAC_ADMIN_GROUP="governance_admins"

# Or use the workspace admins group
export FGAC_ADMIN_GROUP="admins"
```

If unset, defaults to `"admins"`. This should match an existing group in your Databricks workspace that contains users authorized to manage FGAC policies.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FGAC_ADMIN_GROUP` | `admins` | Databricks workspace group whose members can create/update/delete FGAC policies |

---

## MCP Tools

### Discovery Tools

#### `list_fgac_policies`

List FGAC policies on a catalog, schema, or table.

```python
list_fgac_policies(
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
      "column_mask": {"function_name": "my_catalog.my_schema.mask_ssn", "on_column": "masked_col"},
      "match_columns": [{"alias": "masked_col", "condition": "hasTagValue('pii_type', 'ssn')"}]
    }
  ]
}
```

#### `get_fgac_policy`

Get details for a specific policy by name.

```python
get_fgac_policy(
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
    "column_mask": {"function_name": "my_catalog.my_schema.mask_ssn", "on_column": "masked_col"},
    "match_columns": [{"alias": "masked_col", "condition": "hasTagValue('pii_type', 'ssn')"}]
  }
}
```

#### `get_table_policies`

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
      "column_type": "STRING",
      "mask_functions": ["my_catalog.my_schema.mask_ssn"]
    }
  ],
  "row_filters": [
    {
      "function_name": "my_catalog.my_schema.is_not_eu_region",
      "input_column_names": ["region"]
    }
  ]
}
```

#### `get_masking_functions`

List masking UDFs in a schema.

> **Cross-catalog UDFs:** Masking UDFs can reside in any catalog/schema, not just the policy scope. Use `udf_catalog` and `udf_schema` to discover UDFs stored in a shared governance schema (e.g., `governance.masking_udfs`). These default to `catalog`/`schema` when not specified.

```python
get_masking_functions(
    catalog: str,
    schema: str,
    # To discover UDFs in a different catalog/schema:
    udf_catalog: str = None,  # defaults to catalog
    udf_schema: str = None,   # defaults to schema
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

#### `get_column_tags_api`

Get column-level tags for a table via the Tags API (queries `system.information_schema.column_tags`).

```python
get_column_tags_api(
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
  "tags": [
    {
      "catalog_name": "my_catalog",
      "schema_name": "my_schema",
      "table_name": "my_table",
      "column_name": "ssn",
      "tag_name": "pii_type",
      "tag_value": "ssn"
    }
  ]
}
```

#### `get_schema_info`

Get schema metadata via Unity Catalog API.

```python
get_schema_info(catalog: str, schema: str)
```

**Returns:**
```json
{
  "success": true,
  "schema": {
    "name": "my_schema",
    "full_name": "my_catalog.my_schema",
    "catalog_name": "my_catalog",
    "owner": "admin_user",
    "comment": "Production finance schema",
    "created_at": 1700000000000,
    "updated_at": 1700100000000
  }
}
```

#### `get_catalog_info`

Get catalog metadata via Unity Catalog API.

```python
get_catalog_info(catalog: str)
```

**Returns:**
```json
{
  "success": true,
  "catalog": {
    "name": "my_catalog",
    "owner": "admin_user",
    "comment": "Production catalog",
    "created_at": 1700000000000,
    "updated_at": 1700100000000
  }
}
```

#### `list_table_policies_in_schema`

List all tables in a schema with their column masks and row filters.

```python
list_table_policies_in_schema(
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
  "table_count": 3,
  "tables": [
    {
      "table": "customers",
      "column_masks": [
        {"column_name": "ssn", "column_type": "STRING", "mask_functions": ["my_catalog.my_schema.mask_ssn"]}
      ],
      "row_filters": []
    },
    {
      "table": "orders",
      "column_masks": [],
      "row_filters": []
    }
  ]
}
```

#### `analyze_fgac_coverage`

Analyze FGAC policy coverage for a catalog or schema. Identifies tagged columns that lack policy coverage and suggests actions.

```python
analyze_fgac_coverage(
    catalog: str,
    schema: str = None,  # Optional; omit to analyze entire catalog
)
```

**Returns:**
```json
{
  "success": true,
  "scope": "SCHEMA my_catalog.my_schema",
  "summary": {
    "tables_scanned": 10,
    "tagged_columns": 5,
    "existing_policies": 2,
    "available_udfs": 3,
    "covered_tags": ["pii_type:ssn"],
    "uncovered_tags": ["pii_type:email"]
  },
  "gaps": [
    {
      "tag_name": "pii_type",
      "tag_value": "email",
      "columns": [{"table": "my_catalog.my_schema.customers", "column": "email"}],
      "suggestion": "No policy covers this tag. Consider creating a COLUMN_MASK policy."
    }
  ],
  "existing_policies": [{"name": "mask_pii_ssn", "policy_type": "COLUMN_MASK", "...": "..."}],
  "available_udfs": [{"name": "mask_ssn", "full_name": "my_catalog.my_schema.mask_ssn", "...": "..."}]
}
```

#### `check_policy_quota`

Check if the policy quota allows creating a new policy on a securable.

```python
check_policy_quota(
    securable_type: str,       # "CATALOG", "SCHEMA", or "TABLE"
    securable_fullname: str,   # e.g., "my_catalog.my_schema"
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

**Quotas:** CATALOG=10, SCHEMA=10, TABLE=5.

### Preview Tool (Human-in-the-Loop Gate)

#### `preview_policy_changes`

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
  "approval_token": "a1b2c3...:eyJhY3Rpb24i...",
  "message": "Review the preview above. Reply 'approve' to execute, passing the approval_token."
}
```

**Usage in workflow:**

1. Call `preview_policy_changes` with proposed changes
2. Present preview to user (includes `approval_token`)
3. Wait for explicit approval
4. Pass `approval_token` to `create_fgac_policy`, `update_fgac_policy`, or `delete_fgac_policy`

### Management Tools

#### `create_fgac_policy`

Create a new FGAC policy (COLUMN_MASK or ROW_FILTER).

```python
create_fgac_policy(
    policy_name: str,
    policy_type: str,          # "COLUMN_MASK" or "ROW_FILTER"
    securable_type: str,       # "CATALOG", "SCHEMA", or "TABLE"
    securable_fullname: str,
    function_name: str,        # Fully qualified UDF name
    to_principals: list,       # Users/groups the policy applies to
    tag_name: str,             # Tag key to match
    approval_token: str,       # Token from preview_policy_changes()
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

#### `update_fgac_policy`

Update an existing policy's principals or comment.

```python
update_fgac_policy(
    policy_name: str,
    securable_type: str,
    securable_fullname: str,
    approval_token: str,       # Token from preview_policy_changes()
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

#### `delete_fgac_policy`

Delete an FGAC policy.

```python
delete_fgac_policy(
    policy_name: str,
    securable_type: str,
    securable_fullname: str,
    approval_token: str,       # Token from preview_policy_changes()
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
→ analyze_fgac_coverage(catalog="prod", schema="finance")
  # Or analyze individual components:
→ list_fgac_policies(securable_type="SCHEMA", securable_fullname="prod.finance")
→ get_column_tags_api(catalog="prod", schema="finance", table="customers")
→ get_masking_functions(catalog="prod", schema="finance")
  # If UDFs are in a shared governance schema:
→ get_masking_functions(catalog="prod", schema="finance",
      udf_catalog="governance", udf_schema="masking_udfs")

Step 2: RECOMMEND
─────────────────────────────────
→ Agent generates policy recommendations based on coverage gaps and available UDFs

Step 3: PREVIEW (returns approval_token)
─────────────────────────────────
→ result = preview_policy_changes(
      action="CREATE",
      policy_name="mask_ssn_finance",
      securable_type="SCHEMA",
      securable_fullname="prod.finance",
      policy_type="COLUMN_MASK",
      function_name="governance.masking_udfs.mask_ssn",
      to_principals=["analysts"],
      tag_name="pii_type",
      tag_value="ssn"
  )
→ token = result["approval_token"]

Step 4: APPROVE
─────────────────────────────────
→ Human reviews preview and replies "approve"

Step 5: EXECUTE (pass approval_token)
─────────────────────────────────
→ create_fgac_policy(
      policy_name="mask_ssn_finance",
      policy_type="COLUMN_MASK",
      securable_type="SCHEMA",
      securable_fullname="prod.finance",
      function_name="governance.masking_udfs.mask_ssn",
      to_principals=["analysts"],
      tag_name="pii_type",
      tag_value="ssn",
      approval_token=token
  )

Step 6: VERIFY
─────────────────────────────────
→ get_fgac_policy(
      policy_name="mask_ssn_finance",
      securable_type="SCHEMA",
      securable_fullname="prod.finance"
  )
```

---

## Python SDK Direct Usage

For writing custom code outside MCP tools, use the Databricks Python SDK directly.

### Setup

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()  # Auto-detects credentials
```

### SDK Types

```python
from databricks.sdk.service.catalog import (
    ColumnMaskOptions,
    MatchColumn,
    PolicyInfo,
    PolicyType,
    RowFilterOptions,
    SecurableType,
)
```

### List Policies

```python
policies = w.policies.list_policies(
    on_securable_type="CATALOG",
    on_securable_fullname="my_catalog",
    include_inherited=True,
)

for p in policies:
    print(f"{p.name}: {p.policy_type} on {p.on_securable_fullname}")

# Filter by type
column_masks = [p for p in policies if p.policy_type == "COLUMN_MASK"]
row_filters = [p for p in policies if p.policy_type == "ROW_FILTER"]
```

### Get Policy

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

### Create Column Mask Policy

```python
policy_info = PolicyInfo(
    name="mask_pii_ssn_schema",
    policy_type=PolicyType.POLICY_TYPE_COLUMN_MASK,
    on_securable_type=SecurableType.SCHEMA,
    on_securable_fullname="my_catalog.my_schema",
    for_securable_type=SecurableType.TABLE,
    to_principals=["analysts", "data_scientists"],
    except_principals=["gov_admin"],
    comment="Mask SSN columns in schema",
    column_mask=ColumnMaskOptions(
        function_name="my_catalog.my_schema.mask_ssn",
        on_column="masked_col",
    ),
    match_columns=[
        MatchColumn(
            alias="masked_col",
            condition="hasTagValue('pii_type', 'ssn')",
        )
    ],
)
policy = w.policies.create_policy(policy_info=policy_info)
```

Change `on_securable_type` and `on_securable_fullname` to target catalog or table scope.

### Create Column Mask Policy (Cross-Catalog UDF)

The UDF can live in a separate governance catalog/schema from the policy scope:

```python
# UDF in governance.masking_udfs, policy on prod.finance
policy_info = PolicyInfo(
    name="mask_ssn_finance",
    policy_type=PolicyType.POLICY_TYPE_COLUMN_MASK,
    on_securable_type=SecurableType.SCHEMA,
    on_securable_fullname="prod.finance",
    for_securable_type=SecurableType.TABLE,
    to_principals=["analysts"],
    except_principals=["gov_admin"],
    comment="Mask SSN columns in prod.finance using shared governance UDF",
    column_mask=ColumnMaskOptions(
        function_name="governance.masking_udfs.mask_ssn",
        on_column="masked_col",
    ),
    match_columns=[
        MatchColumn(
            alias="masked_col",
            condition="hasTagValue('pii_type', 'ssn')",
        )
    ],
)
policy = w.policies.create_policy(policy_info=policy_info)
```

### Create Row Filter Policy

```python
policy_info = PolicyInfo(
    name="filter_eu_data_schema",
    policy_type=PolicyType.POLICY_TYPE_ROW_FILTER,
    on_securable_type=SecurableType.SCHEMA,
    on_securable_fullname="my_catalog.my_schema",
    for_securable_type=SecurableType.TABLE,
    to_principals=["us_team"],
    except_principals=["gov_admin"],
    comment="Filter EU rows in schema",
    row_filter=RowFilterOptions(
        function_name="my_catalog.my_schema.is_not_eu_region",
    ),
    match_columns=[
        MatchColumn(
            alias="filter_col",
            condition="hasTagValue('region', 'eu')",
        )
    ],
)
policy = w.policies.create_policy(policy_info=policy_info)
```

### Update Policy

Update principals or comment on an existing policy.

```python
update_info = PolicyInfo(
    to_principals=["analysts", "data_scientists", "new_team"],
    except_principals=["gov_admin", "senior_admins"],
    comment="Updated: added new_team to masked principals",
    for_securable_type=SecurableType.TABLE,
    policy_type=PolicyType.POLICY_TYPE_COLUMN_MASK,
)
updated = w.policies.update_policy(
    name="mask_pii_ssn",
    on_securable_type="SCHEMA",
    on_securable_fullname="my_catalog.my_schema",
    policy_info=update_info,
    update_mask="to_principals,except_principals,comment",
)
```

> **Note:** To change the UDF, tag matching, or scope, you must drop and recreate the policy. `update_policy` only modifies principals and comment via `update_mask`.

### Delete Policy

```python
w.policies.delete_policy(
    name="mask_pii_ssn",
    on_securable_type="SCHEMA",
    on_securable_fullname="my_catalog.my_schema",
)
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

| Error | Cause | Solution |
|-------|-------|----------|
| `POLICY_QUOTA_EXCEEDED` | Too many policies on scope | Consolidate policies or use broader scope |
| `INVALID_TAG_VALUE` | Tag value not in governed tag's allowed values | Check governed tag config in UI |
| `UDF_NOT_FOUND` | Masking UDF doesn't exist | Create UDF first, use fully qualified name |
| `POLICY_ALREADY_EXISTS` | Duplicate policy name | Use different name or delete existing first |
| `INSUFFICIENT_PERMISSIONS` | Missing `MANAGE` on securable | Grant `MANAGE` permission |
| `INVALID_SECURABLE_TYPE` | Wrong securable type string | Use `"CATALOG"`, `"SCHEMA"`, or `"TABLE"` |

---

## Common Patterns

### Policy Summary with Counts

```python
def get_policy_summary(w, catalog: str):
    """Get a summary of all FGAC policies in a catalog."""
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

### Async Usage (FastAPI, etc.)

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
```

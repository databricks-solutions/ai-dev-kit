# Row Filters & Column Masks

Apply fine-grained access control to tables using SQL functions as row filters and column masks.

## MCP Tool

| Tool | Purpose |
|------|---------|
| `manage_uc_security_policies` | Create security functions, apply/remove row filters and column masks |

---

## How It Works

- **Row filter**: A SQL function that returns `BOOLEAN`. Rows where the function returns `FALSE` are hidden from the user.
- **Column mask**: A SQL function that returns the same type as the column. The function can redact, hash, or transform values based on the user's identity.

Both use `IS_ACCOUNT_GROUP_MEMBER()` or `CURRENT_USER()` to make access decisions at query time.

---

## Row Filters

### Step 1: Create a Filter Function

```python
manage_uc_security_policies(
    action="create_security_function",
    function_name="analytics.gold.region_filter",
    parameter_name="region_val",
    parameter_type="STRING",
    return_type="BOOLEAN",
    function_body="RETURN IF(IS_ACCOUNT_GROUP_MEMBER('global-admins'), TRUE, region_val = 'US')",
    function_comment="Non-admins can only see US region data"
)
```

### Step 2: Apply to a Table

```python
manage_uc_security_policies(
    action="set_row_filter",
    table_name="analytics.gold.orders",
    filter_function="analytics.gold.region_filter",
    filter_columns=["region"]
)
```

Now when a non-admin queries `analytics.gold.orders`, they only see rows where `region = 'US'`.

### Remove a Row Filter

```python
manage_uc_security_policies(
    action="drop_row_filter",
    table_name="analytics.gold.orders"
)
```

---

## Column Masks

### Mask an Email Column

```python
# Create mask function
manage_uc_security_policies(
    action="create_security_function",
    function_name="analytics.gold.mask_email",
    parameter_name="email_val",
    parameter_type="STRING",
    return_type="STRING",
    function_body="RETURN IF(IS_ACCOUNT_GROUP_MEMBER('pii-readers'), email_val, CONCAT(LEFT(email_val, 2), '***@***.com'))",
    function_comment="Show full email only to PII readers group"
)

# Apply to column
manage_uc_security_policies(
    action="set_column_mask",
    table_name="analytics.gold.customers",
    column_name="email",
    mask_function="analytics.gold.mask_email"
)
```

Result: non-PII users see `st***@***.com` instead of `steven.tan@company.com`.

### Mask a Numeric Column (e.g., Salary)

```python
manage_uc_security_policies(
    action="create_security_function",
    function_name="hr.secure.mask_salary",
    parameter_name="salary_val",
    parameter_type="DECIMAL(10,2)",
    return_type="DECIMAL(10,2)",
    function_body="RETURN IF(IS_ACCOUNT_GROUP_MEMBER('hr-admins'), salary_val, NULL)",
    function_comment="Only HR admins can see salary values"
)

manage_uc_security_policies(
    action="set_column_mask",
    table_name="hr.employees.staff",
    column_name="salary",
    mask_function="hr.secure.mask_salary"
)
```

### Remove a Column Mask

```python
manage_uc_security_policies(
    action="drop_column_mask",
    table_name="analytics.gold.customers",
    column_name="email"
)
```

---

## Common Patterns

### Multi-Column Masking

Apply masks to several PII columns on the same table:

```python
pii_masks = [
    ("email", "STRING", "CONCAT(LEFT(val, 2), '***@***.com')"),
    ("phone", "STRING", "CONCAT('***-***-', RIGHT(val, 4))"),
    ("ssn", "STRING", "'***-**-****'"),
]

for col, dtype, mask_expr in pii_masks:
    func_name = f"analytics.gold.mask_{col}"
    manage_uc_security_policies(
        action="create_security_function",
        function_name=func_name,
        parameter_name="val",
        parameter_type=dtype,
        return_type=dtype,
        function_body=f"RETURN IF(IS_ACCOUNT_GROUP_MEMBER('pii-readers'), val, {mask_expr})"
    )
    manage_uc_security_policies(
        action="set_column_mask",
        table_name="analytics.gold.customers",
        column_name=col,
        mask_function=func_name
    )
```

### Row Filter by User's Department

```python
manage_uc_security_policies(
    action="create_security_function",
    function_name="analytics.gold.dept_filter",
    parameter_name="dept_val",
    parameter_type="STRING",
    return_type="BOOLEAN",
    function_body="""RETURN
      IS_ACCOUNT_GROUP_MEMBER('global-admins')
      OR IS_ACCOUNT_GROUP_MEMBER(CONCAT('dept-', LOWER(dept_val)))""",
    function_comment="Users only see rows for their department group"
)
```

---

## Important Notes

- Row filters and column masks are enforced at **query time** — they apply to all SQL, BI tools, and notebooks
- Functions must be in the **same catalog** as the table (or in a catalog the user has access to)
- `IS_ACCOUNT_GROUP_MEMBER()` checks account-level groups, not workspace-local groups
- Only **metastore admins** and **account admins** bypass row filters and column masks. Table owners and users with `ALL_PRIVILEGES` do NOT automatically bypass them
- Performance impact is minimal for simple functions; avoid expensive joins in filter/mask functions

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **"Function not found"** | Function must exist before applying. Use `create_security_function` first |
| **Filter not working for admins** | Only metastore admins and account admins bypass filters/masks. `ALL_PRIVILEGES` and table ownership do NOT bypass them |
| **Type mismatch** | Column mask `return_type` must exactly match the column's data type |
| **Cannot apply to view** | Row filters and column masks only work on tables, not views. Use view-level logic instead |
| **"Cannot create function"** | Need `CREATE_FUNCTION` privilege on the schema |

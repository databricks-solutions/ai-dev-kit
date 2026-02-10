"""
Databricks SDK - ABAC Policy Management Examples

ABAC Policies: https://docs.databricks.com/data-governance/unity-catalog/abac/policies
Python SDK: https://databricks-sdk-py.readthedocs.io/en/latest/
"""

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound, PermissionDenied, BadRequest

w = WorkspaceClient()

# =============================================================================
# LIST POLICIES
# =============================================================================

# List all ABAC policies on a catalog (includes inherited policies)
for policy in w.policies.list_policies(
    on_securable_type="CATALOG",
    on_securable_fullname="my_catalog",
    include_inherited=True,
):
    print(f"{policy.name}: {policy.policy_type}")

# List policies on a schema
for policy in w.policies.list_policies(
    on_securable_type="SCHEMA",
    on_securable_fullname="my_catalog.my_schema",
    include_inherited=True,
):
    p_dict = policy.as_dict() if hasattr(policy, "as_dict") else {}
    print(f"  {p_dict.get('name')}: type={p_dict.get('policy_type')}, "
          f"principals={p_dict.get('to_principals')}")

# List policies on a specific table
for policy in w.policies.list_policies(
    on_securable_type="TABLE",
    on_securable_fullname="my_catalog.my_schema.my_table",
    include_inherited=True,
):
    print(f"{policy.name}: {policy.policy_type}")

# Filter by policy type
all_policies = list(w.policies.list_policies(
    on_securable_type="SCHEMA",
    on_securable_fullname="my_catalog.my_schema",
    include_inherited=True,
))
column_masks = [p for p in all_policies if p.policy_type == "COLUMN_MASK"]
row_filters = [p for p in all_policies if p.policy_type == "ROW_FILTER"]
print(f"Column masks: {len(column_masks)}, Row filters: {len(row_filters)}")


# =============================================================================
# GET POLICY DETAILS
# =============================================================================

# Get a specific policy by name
policy = w.policies.get_policy(
    name="mask_pii_ssn",
    on_securable_type="SCHEMA",
    on_securable_fullname="my_catalog.my_schema",
)
print(f"Policy: {policy.name}")
print(f"Type: {policy.policy_type}")
print(f"Principals: {policy.to_principals}")
print(f"Except: {policy.except_principals}")


# =============================================================================
# CREATE COLUMN MASK POLICY
# =============================================================================

# Create a column mask policy that masks SSN columns for analysts
# The policy matches columns tagged with pii_type='ssn' and applies mask_ssn UDF
from databricks.sdk.service.catalog import ColumnMask, MatchColumns

created = w.policies.create_policy(
    name="mask_pii_ssn",
    policy_type="COLUMN_MASK",
    on_securable_type="SCHEMA",
    on_securable_fullname="my_catalog.my_schema",
    for_securable_type="TABLE",
    to_principals=["analysts", "data_scientists"],
    except_principals=["gov_admin"],  # ALWAYS include gov_admin
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
print(f"Created policy: {created.name}")


# =============================================================================
# CREATE ROW FILTER POLICY
# =============================================================================

# Create a row filter policy that hides EU rows from the US team
from databricks.sdk.service.catalog import RowFilter

created = w.policies.create_policy(
    name="filter_eu_data",
    policy_type="ROW_FILTER",
    on_securable_type="CATALOG",
    on_securable_fullname="my_catalog",
    for_securable_type="TABLE",
    to_principals=["us_team"],
    except_principals=["gov_admin"],  # ALWAYS include gov_admin
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
print(f"Created policy: {created.name}")


# =============================================================================
# UPDATE POLICY
# =============================================================================

# Update policy principals (cannot change UDF, tags, or scope - drop and recreate)
updated = w.policies.update_policy(
    name="mask_pii_ssn",
    on_securable_type="SCHEMA",
    on_securable_fullname="my_catalog.my_schema",
    to_principals=["analysts", "data_scientists", "new_team"],
    except_principals=["gov_admin", "senior_admins"],
    comment="Updated: added new_team to masked principals",
)
print(f"Updated policy: {updated.name}")


# =============================================================================
# DELETE POLICY
# =============================================================================

# Delete a policy
w.policies.delete_policy(
    name="mask_pii_ssn",
    on_securable_type="SCHEMA",
    on_securable_fullname="my_catalog.my_schema",
)
print("Policy deleted")


# =============================================================================
# ERROR HANDLING
# =============================================================================

# Handle common errors
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


# =============================================================================
# UTILITY: POLICY SUMMARY
# =============================================================================

# Get a summary of all ABAC policies in a catalog
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
    }


summary = get_policy_summary(w, "my_catalog")
print(f"Total: {summary['total']}, "
      f"Column masks: {summary['column_masks']}, "
      f"Row filters: {summary['row_filters']}")

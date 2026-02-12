"""
Integration tests for Unity Catalog FGAC Policy operations.

Tests the fgac_policies module functions:
- list_fgac_policies
- get_fgac_policy
- get_table_policies
- get_masking_functions
- check_policy_quota
- preview_policy_changes
- create_fgac_policy / update_fgac_policy / delete_fgac_policy

Governed Tags
-------------
FGAC policies require **governed tags** (not regular metadata tags).
The CRUD tests automatically create and clean up governed tags via the
Tag Policies API (``w.tag_policies``). No manual UI setup is needed.
"""

import logging
import time

import pytest

from databricks_tools_core.auth import get_workspace_client
from databricks_tools_core.sql import execute_sql
from databricks_tools_core.unity_catalog import (
    create_security_function,
    set_tags,
)
from databricks_tools_core.unity_catalog.fgac_policies import (
    list_fgac_policies,
    get_fgac_policy,
    get_table_policies,
    get_masking_functions,
    get_column_tags_api,
    get_schema_info,
    get_catalog_info,
    list_table_policies_in_schema,
    analyze_fgac_coverage,
    check_policy_quota,
    preview_policy_changes,
    create_fgac_policy,
    update_fgac_policy,
    delete_fgac_policy,
    _check_admin_group,
)

logger = logging.getLogger(__name__)

UC_TEST_PREFIX = "uc_test"


# ---------------------------------------------------------------------------
# Discovery tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestListFgacPolicies:
    """Tests for listing FGAC policies."""

    def test_list_policies_on_catalog(self, test_catalog: str):
        """Should list policies on a catalog (may be empty)."""
        result = list_fgac_policies(
            securable_type="CATALOG",
            securable_fullname=test_catalog,
        )

        assert result["success"] is True
        assert result["securable_type"] == "CATALOG"
        assert result["securable_fullname"] == test_catalog
        assert isinstance(result["policies"], list)
        assert isinstance(result["policy_count"], int)
        logger.info(f"Found {result['policy_count']} policies on catalog {test_catalog}")

    def test_list_policies_on_schema(self, test_catalog: str, uc_test_schema: str):
        """Should list policies on a schema."""
        full_name = f"{test_catalog}.{uc_test_schema}"
        result = list_fgac_policies(
            securable_type="SCHEMA",
            securable_fullname=full_name,
        )

        assert result["success"] is True
        assert result["securable_type"] == "SCHEMA"
        assert isinstance(result["policies"], list)
        logger.info(f"Found {result['policy_count']} policies on schema {full_name}")

    def test_list_policies_with_type_filter(self, test_catalog: str):
        """Should filter policies by type."""
        result = list_fgac_policies(
            securable_type="CATALOG",
            securable_fullname=test_catalog,
            policy_type="COLUMN_MASK",
        )

        assert result["success"] is True
        for p in result["policies"]:
            assert p.get("policy_type") == "COLUMN_MASK"
        logger.info(f"Found {result['policy_count']} COLUMN_MASK policies")

    def test_list_policies_without_inherited(self, test_catalog: str):
        """Should list only direct policies when include_inherited=False."""
        result = list_fgac_policies(
            securable_type="CATALOG",
            securable_fullname=test_catalog,
            include_inherited=False,
        )

        assert result["success"] is True
        assert isinstance(result["policies"], list)
        logger.info(f"Found {result['policy_count']} direct policies")


@pytest.mark.integration
class TestGetTablePolicies:
    """Tests for getting column masks and row filters on a table."""

    def test_get_table_policies(self, test_catalog: str, uc_test_schema: str, uc_test_table: str):
        """Should return column masks and row filters for a table."""
        # uc_test_table is "catalog.schema.table"
        parts = uc_test_table.split(".")
        result = get_table_policies(
            catalog=parts[0],
            schema=parts[1],
            table=parts[2],
        )

        assert result["success"] is True
        assert result["table"] == uc_test_table
        assert isinstance(result["column_masks"], list)
        assert isinstance(result["row_filters"], list)
        logger.info(f"Table {uc_test_table}: {len(result['column_masks'])} masks, {len(result['row_filters'])} filters")


@pytest.mark.integration
class TestGetMaskingFunctions:
    """Tests for listing masking UDFs in a schema."""

    def test_get_masking_functions(
        self,
        test_catalog: str,
        uc_test_schema: str,
        unique_name: str,
        warehouse_id: str,
        cleanup_functions,
    ):
        """Should list UDFs in the schema."""
        # Create a test function so there's at least one
        fn_name = f"{test_catalog}.{uc_test_schema}.{UC_TEST_PREFIX}_mask_{unique_name}"
        cleanup_functions(fn_name)

        create_security_function(
            function_name=fn_name,
            parameter_name="val",
            parameter_type="STRING",
            return_type="STRING",
            function_body="RETURN CASE WHEN val IS NULL THEN NULL ELSE '***' END",
            warehouse_id=warehouse_id,
        )

        result = get_masking_functions(
            catalog=test_catalog,
            schema=uc_test_schema,
        )

        assert result["success"] is True
        assert result["catalog"] == test_catalog
        assert result["schema"] == uc_test_schema
        assert isinstance(result["functions"], list)
        assert result["function_count"] > 0

        # Verify our function appears
        func_names = [f["name"] for f in result["functions"]]
        expected_name = f"{UC_TEST_PREFIX}_mask_{unique_name}"
        assert expected_name in func_names, f"Expected {expected_name} in {func_names}"
        logger.info(f"Found {result['function_count']} functions in schema")


# ---------------------------------------------------------------------------
# Analysis & Discovery tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGetColumnTagsApi:
    """Tests for get_column_tags_api."""

    def test_get_column_tags_api(
        self,
        test_catalog: str,
        uc_test_schema: str,
        uc_test_table: str,
        unique_name: str,
        warehouse_id: str,
    ):
        """Should return column tags for a table."""
        parts = uc_test_table.split(".")
        tag_key = f"uc_test_tag_{unique_name}"

        # Tag a column so there's something to find
        set_tags(
            object_type="column",
            full_name=uc_test_table,
            column_name="email",
            tags={tag_key: "test_val"},
            warehouse_id=warehouse_id,
        )

        result = get_column_tags_api(
            catalog=parts[0],
            schema=parts[1],
            table=parts[2],
        )

        assert result["success"] is True
        assert result["table"] == uc_test_table
        assert isinstance(result["tags"], list)
        logger.info(f"Found {len(result['tags'])} column tags on {uc_test_table}")


@pytest.mark.integration
class TestGetSchemaInfo:
    """Tests for get_schema_info."""

    def test_get_schema_info(self, test_catalog: str, uc_test_schema: str):
        """Should return schema metadata."""
        result = get_schema_info(
            catalog=test_catalog,
            schema=uc_test_schema,
        )

        assert result["success"] is True
        assert result["schema"]["name"] == uc_test_schema
        assert result["schema"]["catalog_name"] == test_catalog
        assert result["schema"]["full_name"] == f"{test_catalog}.{uc_test_schema}"
        assert "owner" in result["schema"]
        logger.info(f"Schema info: {result['schema']['full_name']} owned by {result['schema']['owner']}")


@pytest.mark.integration
class TestGetCatalogInfo:
    """Tests for get_catalog_info."""

    def test_get_catalog_info(self, test_catalog: str):
        """Should return catalog metadata."""
        result = get_catalog_info(catalog=test_catalog)

        assert result["success"] is True
        assert result["catalog"]["name"] == test_catalog
        assert "owner" in result["catalog"]
        logger.info(f"Catalog info: {result['catalog']['name']} owned by {result['catalog']['owner']}")


@pytest.mark.integration
class TestListTablePoliciesInSchema:
    """Tests for list_table_policies_in_schema."""

    def test_list_table_policies_in_schema(self, test_catalog: str, uc_test_schema: str, uc_test_table: str):
        """Should list tables with their policies."""
        result = list_table_policies_in_schema(
            catalog=test_catalog,
            schema=uc_test_schema,
        )

        assert result["success"] is True
        assert result["catalog"] == test_catalog
        assert result["schema"] == uc_test_schema
        assert isinstance(result["tables"], list)
        assert result["table_count"] > 0

        # Each table should have column_masks and row_filters keys
        for t in result["tables"]:
            assert "table" in t
            assert "column_masks" in t
            assert "row_filters" in t
        logger.info(f"Found {result['table_count']} tables in {test_catalog}.{uc_test_schema}")


@pytest.mark.integration
class TestAnalyzeFgacCoverage:
    """Tests for analyze_fgac_coverage."""

    def test_analyze_coverage_schema_scope(self, test_catalog: str, uc_test_schema: str, uc_test_table: str):
        """Should return coverage analysis for a schema."""
        result = analyze_fgac_coverage(
            catalog=test_catalog,
            schema=uc_test_schema,
        )

        assert result["success"] is True
        assert result["scope"] == f"SCHEMA {test_catalog}.{uc_test_schema}"

        summary = result["summary"]
        assert isinstance(summary["tables_scanned"], int)
        assert isinstance(summary["tagged_columns"], int)
        assert isinstance(summary["existing_policies"], int)
        assert isinstance(summary["available_udfs"], int)
        assert isinstance(summary["covered_tags"], list)
        assert isinstance(summary["uncovered_tags"], list)
        assert isinstance(result["gaps"], list)
        assert isinstance(result["existing_policies"], list)
        assert isinstance(result["available_udfs"], list)
        logger.info(
            f"Coverage analysis: {summary['tables_scanned']} tables, "
            f"{summary['tagged_columns']} tagged cols, "
            f"{summary['existing_policies']} policies, "
            f"{len(result['gaps'])} gaps"
        )

    def test_analyze_coverage_catalog_scope(self, test_catalog: str, uc_test_schema: str, uc_test_table: str):
        """Should return coverage analysis for an entire catalog."""
        result = analyze_fgac_coverage(catalog=test_catalog)

        assert result["success"] is True
        assert result["scope"] == f"CATALOG {test_catalog}"
        assert isinstance(result["summary"]["tables_scanned"], int)
        assert isinstance(result["gaps"], list)
        logger.info(f"Catalog coverage: {result['summary']['tables_scanned']} tables scanned")


# ---------------------------------------------------------------------------
# Quota check tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCheckPolicyQuota:
    """Tests for policy quota checking."""

    def test_check_quota_on_catalog(self, test_catalog: str):
        """Should return quota info for a catalog."""
        result = check_policy_quota(
            securable_type="CATALOG",
            securable_fullname=test_catalog,
        )

        assert result["success"] is True
        assert result["securable_type"] == "CATALOG"
        assert result["max"] == 10
        assert isinstance(result["current"], int)
        assert isinstance(result["can_create"], bool)
        logger.info(f"Catalog quota: {result['current']}/{result['max']}")

    def test_check_quota_on_schema(self, test_catalog: str, uc_test_schema: str):
        """Should return quota info for a schema."""
        full_name = f"{test_catalog}.{uc_test_schema}"
        result = check_policy_quota(
            securable_type="SCHEMA",
            securable_fullname=full_name,
        )

        assert result["success"] is True
        assert result["max"] == 10
        logger.info(f"Schema quota: {result['current']}/{result['max']}")

    def test_check_quota_on_table(self, uc_test_table: str):
        """Should return quota info for a table."""
        result = check_policy_quota(
            securable_type="TABLE",
            securable_fullname=uc_test_table,
        )

        assert result["success"] is True
        assert result["max"] == 5
        logger.info(f"Table quota: {result['current']}/{result['max']}")


# ---------------------------------------------------------------------------
# Preview tests (no side effects)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestPreviewPolicyChanges:
    """Tests for preview_policy_changes (human-in-the-loop gate)."""

    def test_preview_create_column_mask(self):
        """Should generate CREATE preview with SQL for a column mask."""
        result = preview_policy_changes(
            action="CREATE",
            policy_name="test_mask_ssn",
            securable_type="SCHEMA",
            securable_fullname="my_catalog.my_schema",
            policy_type="COLUMN_MASK",
            to_principals=["analysts"],
            function_name="my_catalog.my_schema.mask_ssn",
            tag_name="pii_type",
            tag_value="ssn",
            comment="Test mask SSN",
        )

        assert result["success"] is True
        assert result["action"] == "CREATE"
        assert result["requires_approval"] is True

        preview = result["preview"]
        assert preview["policy_name"] == "test_mask_ssn"
        assert preview["policy_type"] == "COLUMN_MASK"
        assert "analysts" in preview["to_principals"]
        assert "hasTagValue('pii_type', 'ssn')" in preview["tag_match"]
        assert "COLUMN MASK" in preview["equivalent_sql"]
        assert "MATCH COLUMNS" in preview["equivalent_sql"]
        logger.info(f"Preview SQL:\n{preview['equivalent_sql']}")

    def test_preview_create_row_filter(self):
        """Should generate CREATE preview with SQL for a row filter."""
        result = preview_policy_changes(
            action="CREATE",
            policy_name="test_filter_eu",
            securable_type="CATALOG",
            securable_fullname="my_catalog",
            policy_type="ROW_FILTER",
            to_principals=["us_team"],
            function_name="my_catalog.my_schema.is_not_eu",
            tag_name="region",
            tag_value="eu",
        )

        assert result["success"] is True
        preview = result["preview"]
        assert preview["policy_type"] == "ROW_FILTER"
        assert "ROW FILTER" in preview["equivalent_sql"]
        assert "USING COLUMNS" in preview["equivalent_sql"]
        logger.info(f"Preview SQL:\n{preview['equivalent_sql']}")

    def test_preview_create_with_has_tag(self):
        """Should use hasTag when tag_value is omitted."""
        result = preview_policy_changes(
            action="CREATE",
            policy_name="test_mask_all_pii",
            securable_type="SCHEMA",
            securable_fullname="my_catalog.my_schema",
            policy_type="COLUMN_MASK",
            to_principals=["external_users"],
            function_name="my_catalog.my_schema.mask_full",
            tag_name="pii_type",
        )

        assert result["success"] is True
        assert "hasTag('pii_type')" in result["preview"]["tag_match"]
        logger.info("Preview uses hasTag (no tag_value)")

    def test_preview_delete(self):
        """Should generate DELETE preview with DROP SQL."""
        result = preview_policy_changes(
            action="DELETE",
            policy_name="test_mask_ssn",
            securable_type="SCHEMA",
            securable_fullname="my_catalog.my_schema",
        )

        assert result["success"] is True
        assert result["action"] == "DELETE"
        assert "DROP POLICY" in result["preview"]["equivalent_sql"]
        assert len(result["warnings"]) > 0  # Should warn about irreversibility
        logger.info(f"Delete preview: {result['preview']['equivalent_sql']}")

    def test_preview_update(self):
        """Should generate UPDATE preview."""
        result = preview_policy_changes(
            action="UPDATE",
            policy_name="test_mask_ssn",
            securable_type="SCHEMA",
            securable_fullname="my_catalog.my_schema",
            to_principals=["analysts", "new_team"],
            comment="Updated principals",
        )

        assert result["success"] is True
        assert result["action"] == "UPDATE"
        assert "to_principals" in result["preview"]["changes"]
        assert "comment" in result["preview"]["changes"]
        logger.info(f"Update preview changes: {result['preview']['changes']}")


# ---------------------------------------------------------------------------
# Validation tests (no Databricks connection needed)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestFgacPolicyValidation:
    """Tests for input validation in FGAC policy functions."""

    def test_invalid_securable_type_raises(self):
        """Should raise ValueError for invalid securable type."""
        with pytest.raises(ValueError) as exc_info:
            list_fgac_policies(
                securable_type="INVALID",
                securable_fullname="test",
            )

        assert "invalid securable_type" in str(exc_info.value).lower()

    def test_invalid_policy_type_raises(self):
        """Should raise ValueError for invalid policy type."""
        with pytest.raises(ValueError) as exc_info:
            preview_policy_changes(
                action="CREATE",
                policy_name="test",
                securable_type="SCHEMA",
                securable_fullname="cat.sch",
                policy_type="INVALID",
                to_principals=["x"],
                function_name="fn",
                tag_name="t",
            )

        assert "invalid policy_type" in str(exc_info.value).lower()

    def test_invalid_action_raises(self):
        """Should raise ValueError for invalid action."""
        with pytest.raises(ValueError) as exc_info:
            preview_policy_changes(
                action="INVALID",
                policy_name="test",
                securable_type="SCHEMA",
                securable_fullname="cat.sch",
            )

        assert "invalid action" in str(exc_info.value).lower()

    def test_create_preview_missing_policy_type_raises(self):
        """Should raise ValueError when policy_type missing for CREATE."""
        with pytest.raises(ValueError) as exc_info:
            preview_policy_changes(
                action="CREATE",
                policy_name="test",
                securable_type="SCHEMA",
                securable_fullname="cat.sch",
                to_principals=["x"],
                function_name="fn",
                tag_name="t",
            )

        assert "policy_type" in str(exc_info.value).lower()

    def test_create_preview_missing_function_name_raises(self):
        """Should raise ValueError when function_name missing for CREATE."""
        with pytest.raises(ValueError) as exc_info:
            preview_policy_changes(
                action="CREATE",
                policy_name="test",
                securable_type="SCHEMA",
                securable_fullname="cat.sch",
                policy_type="COLUMN_MASK",
                to_principals=["x"],
                tag_name="t",
            )

        assert "function_name" in str(exc_info.value).lower()

    def test_create_preview_missing_tag_name_raises(self):
        """Should raise ValueError when tag_name missing for CREATE."""
        with pytest.raises(ValueError) as exc_info:
            preview_policy_changes(
                action="CREATE",
                policy_name="test",
                securable_type="SCHEMA",
                securable_fullname="cat.sch",
                policy_type="COLUMN_MASK",
                to_principals=["x"],
                function_name="fn",
            )

        assert "tag_name" in str(exc_info.value).lower()

    def test_create_preview_missing_principals_raises(self):
        """Should raise ValueError when to_principals missing for CREATE."""
        with pytest.raises(ValueError) as exc_info:
            preview_policy_changes(
                action="CREATE",
                policy_name="test",
                securable_type="SCHEMA",
                securable_fullname="cat.sch",
                policy_type="COLUMN_MASK",
                function_name="fn",
                tag_name="t",
            )

        assert "to_principals" in str(exc_info.value).lower()

    def test_invalid_identifier_raises(self):
        """Should raise ValueError for SQL injection attempts."""
        with pytest.raises(ValueError) as exc_info:
            list_fgac_policies(
                securable_type="CATALOG",
                securable_fullname="DROP TABLE; --",
            )

        assert "invalid sql identifier" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Approval token enforcement tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestApprovalTokenEnforcement:
    """Tests for approval token guardrails on mutating operations."""

    def test_create_without_token_raises(self):
        """create_fgac_policy without approval_token should raise TypeError."""
        with pytest.raises(TypeError):
            create_fgac_policy(
                policy_name="test_no_token",
                policy_type="COLUMN_MASK",
                securable_type="SCHEMA",
                securable_fullname="cat.sch",
                function_name="cat.sch.fn",
                to_principals=["analysts"],
                tag_name="pii",
            )

    def test_create_with_invalid_token_raises_value_error(self):
        """create_fgac_policy with an invalid token should raise ValueError before admin check."""
        with pytest.raises(ValueError, match="Invalid or expired approval token"):
            create_fgac_policy(
                policy_name="test_bad_token",
                policy_type="COLUMN_MASK",
                securable_type="SCHEMA",
                securable_fullname="cat.sch",
                function_name="cat.sch.fn",
                to_principals=["analysts"],
                tag_name="pii",
                approval_token="garbage",
            )

    def test_create_without_admin_group_raises_permission_error(self):
        """create_fgac_policy should raise PermissionError if user is not in admin group."""
        # Get a valid token via preview so we pass token validation
        preview = preview_policy_changes(
            action="CREATE",
            policy_name="test_admin_check",
            securable_type="SCHEMA",
            securable_fullname="cat.sch",
            policy_type="COLUMN_MASK",
            to_principals=["analysts"],
            function_name="cat.sch.fn",
            tag_name="pii",
        )
        with pytest.raises(PermissionError, match="not a member of admin group"):
            create_fgac_policy(
                policy_name="test_admin_check",
                policy_type="COLUMN_MASK",
                securable_type="SCHEMA",
                securable_fullname="cat.sch",
                function_name="cat.sch.fn",
                to_principals=["analysts"],
                tag_name="pii",
                approval_token=preview["approval_token"],
            )

    def test_preview_returns_approval_token(self):
        """preview_policy_changes should return an approval_token."""
        result = preview_policy_changes(
            action="CREATE",
            policy_name="test_token_preview",
            securable_type="SCHEMA",
            securable_fullname="my_catalog.my_schema",
            policy_type="COLUMN_MASK",
            to_principals=["analysts"],
            function_name="my_catalog.my_schema.mask_ssn",
            tag_name="pii_type",
            tag_value="ssn",
        )

        assert result["success"] is True
        assert "approval_token" in result
        assert isinstance(result["approval_token"], str)
        assert ":" in result["approval_token"]
        logger.info("Preview returned approval token")

    def test_full_preview_then_create_workflow(
        self,
        test_catalog: str,
        uc_test_schema: str,
        uc_test_table: str,
        unique_name: str,
        warehouse_id: str,
        cleanup_functions,
        cleanup_policies,
    ):
        """Should preview, extract token, then create with token (happy path)."""
        full_schema = f"{test_catalog}.{uc_test_schema}"
        policy_name = f"{UC_TEST_PREFIX}_tok_{unique_name}"
        tag_key = f"uc_test_tok_{unique_name}"
        tag_value = "email"

        cleanup_policies((policy_name, "SCHEMA", full_schema))

        TestFgacPolicyCRUD._create_governed_tag(tag_key, [tag_value])

        try:
            fn_name = f"{test_catalog}.{uc_test_schema}.{UC_TEST_PREFIX}_tok_fn_{unique_name}"
            cleanup_functions(fn_name)

            create_security_function(
                function_name=fn_name,
                parameter_name="val",
                parameter_type="STRING",
                return_type="STRING",
                function_body="RETURN CASE WHEN val IS NULL THEN NULL ELSE '***' END",
                warehouse_id=warehouse_id,
            )

            set_tags(
                object_type="column",
                full_name=uc_test_table,
                column_name="email",
                tags={tag_key: tag_value},
                warehouse_id=warehouse_id,
            )

            # Preview to get token
            preview = preview_policy_changes(
                action="CREATE",
                policy_name=policy_name,
                securable_type="SCHEMA",
                securable_fullname=full_schema,
                policy_type="COLUMN_MASK",
                to_principals=["account users"],
                function_name=fn_name,
                tag_name=tag_key,
                tag_value=tag_value,
                comment=f"Token test {unique_name}",
            )
            token = preview["approval_token"]

            # Create with token
            result = create_fgac_policy(
                policy_name=policy_name,
                policy_type="COLUMN_MASK",
                securable_type="SCHEMA",
                securable_fullname=full_schema,
                function_name=fn_name,
                to_principals=["account users"],
                tag_name=tag_key,
                approval_token=token,
                tag_value=tag_value,
                comment=f"Token test {unique_name}",
            )

            assert result["success"] is True
            assert result["action"] == "created"
            logger.info("Full preview-then-create workflow passed")

            # Clean up via SDK directly (bypass guardrails)
            w = get_workspace_client()
            w.policies.delete_policy(
                on_securable_type="SCHEMA",
                on_securable_fullname=full_schema,
                name=policy_name,
            )

        finally:
            TestFgacPolicyCRUD._delete_governed_tag(tag_key)

    def test_token_with_mismatched_params_raises(self):
        """Token from preview with name A should not work for create with name B."""
        preview = preview_policy_changes(
            action="CREATE",
            policy_name="policy_a",
            securable_type="SCHEMA",
            securable_fullname="cat.sch",
            policy_type="COLUMN_MASK",
            to_principals=["analysts"],
            function_name="cat.sch.mask",
            tag_name="pii",
        )
        token = preview["approval_token"]

        with pytest.raises((ValueError, PermissionError)):
            create_fgac_policy(
                policy_name="policy_b",  # Different name!
                policy_type="COLUMN_MASK",
                securable_type="SCHEMA",
                securable_fullname="cat.sch",
                function_name="cat.sch.mask",
                to_principals=["analysts"],
                tag_name="pii",
                approval_token=token,
            )


# ---------------------------------------------------------------------------
# Admin group check tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAdminGroupCheck:
    """Tests for admin group membership verification."""

    def test_admin_check_passes(self):
        """Should pass for workspace admin user (test profile user)."""
        result = _check_admin_group()
        assert result["is_admin"] is True
        assert result["user"] is not None
        assert result["admin_group"] == "admins"
        logger.info(f"Admin check passed for user: {result['user']}")

    def test_admin_check_custom_group_fails(self):
        """Should raise PermissionError for a non-existent group."""
        import databricks_tools_core.unity_catalog.fgac_policies as fgac_mod

        original = fgac_mod._ADMIN_GROUP
        try:
            fgac_mod._ADMIN_GROUP = "nonexistent_group_xyz_12345"
            with pytest.raises(PermissionError) as exc_info:
                _check_admin_group()
            assert "nonexistent_group_xyz_12345" in str(exc_info.value)
            logger.info("Admin check correctly denied for non-existent group")
        finally:
            fgac_mod._ADMIN_GROUP = original


# ---------------------------------------------------------------------------
# CRUD lifecycle tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestFgacPolicyCRUD:
    """Tests for create, get, update, and delete policy operations.

    Each test creates its own governed tag via the Tag Policies API,
    then cleans it up afterwards. No manual UI setup is required.
    """

    @staticmethod
    def _create_governed_tag(tag_key: str, allowed_values: list[str]) -> None:
        """Create a governed tag via the Tag Policies API."""
        from databricks.sdk.service.tags import TagPolicy, Value

        w = get_workspace_client()
        w.tag_policies.create_tag_policy(
            tag_policy=TagPolicy(
                tag_key=tag_key,
                description=f"Integration test tag ({tag_key})",
                values=[Value(name=v) for v in allowed_values],
            )
        )
        logger.info(f"Created governed tag: {tag_key} (values={allowed_values})")

        # Wait for governed tag to propagate to the FGAC policy system
        logger.info("Waiting 30s for governed tag propagation...")
        time.sleep(30)

    @staticmethod
    def _delete_governed_tag(tag_key: str) -> None:
        """Delete a governed tag via the Tag Policies API."""
        try:
            w = get_workspace_client()
            w.tag_policies.delete_tag_policy(tag_key=tag_key)
            logger.info(f"Deleted governed tag: {tag_key}")
        except Exception as e:
            logger.warning(f"Failed to delete governed tag {tag_key}: {e}")

    def test_create_get_update_delete_column_mask_policy(
        self,
        test_catalog: str,
        uc_test_schema: str,
        uc_test_table: str,
        unique_name: str,
        warehouse_id: str,
        cleanup_functions,
        cleanup_policies,
    ):
        """Should create, get, update, and delete a column mask policy."""
        full_schema = f"{test_catalog}.{uc_test_schema}"
        policy_name = f"{UC_TEST_PREFIX}_mask_{unique_name}"

        # Unique governed tag for this test run
        tag_key = f"uc_test_pii_{unique_name}"
        tag_value = "email"

        # Register for cleanup
        cleanup_policies((policy_name, "SCHEMA", full_schema))

        # --- Setup: governed tag, masking UDF, column tag ---
        self._create_governed_tag(tag_key, [tag_value])

        try:
            fn_name = f"{test_catalog}.{uc_test_schema}.{UC_TEST_PREFIX}_mask_fn_{unique_name}"
            cleanup_functions(fn_name)

            create_security_function(
                function_name=fn_name,
                parameter_name="val",
                parameter_type="STRING",
                return_type="STRING",
                function_body="RETURN CASE WHEN val IS NULL THEN NULL ELSE '***' END",
                warehouse_id=warehouse_id,
            )
            logger.info(f"Created masking UDF: {fn_name}")

            # Apply governed tag to column
            set_tags(
                object_type="column",
                full_name=uc_test_table,
                column_name="email",
                tags={tag_key: tag_value},
                warehouse_id=warehouse_id,
            )
            logger.info(f"Tagged column email with {tag_key}={tag_value}")

            # --- PREVIEW CREATE ---
            logger.info(f"Previewing FGAC policy creation: {policy_name}")
            create_preview = preview_policy_changes(
                action="CREATE",
                policy_name=policy_name,
                securable_type="SCHEMA",
                securable_fullname=full_schema,
                policy_type="COLUMN_MASK",
                to_principals=["account users"],
                function_name=fn_name,
                tag_name=tag_key,
                tag_value=tag_value,
                comment=f"Test policy {unique_name}",
            )
            assert "approval_token" in create_preview
            create_token = create_preview["approval_token"]

            # --- CREATE ---
            logger.info(f"Creating FGAC policy: {policy_name}")
            create_result = create_fgac_policy(
                policy_name=policy_name,
                policy_type="COLUMN_MASK",
                securable_type="SCHEMA",
                securable_fullname=full_schema,
                function_name=fn_name,
                to_principals=["account users"],
                tag_name=tag_key,
                approval_token=create_token,
                tag_value=tag_value,
                comment=f"Test policy {unique_name}",
            )

            assert create_result["success"] is True
            assert create_result["policy_name"] == policy_name
            assert create_result["action"] == "created"
            logger.info(f"Policy created: {create_result['details']}")

            # --- GET ---
            logger.info(f"Getting policy: {policy_name}")
            get_result = get_fgac_policy(
                policy_name=policy_name,
                securable_type="SCHEMA",
                securable_fullname=full_schema,
            )

            assert get_result["success"] is True
            assert get_result["policy"]["name"] == policy_name
            logger.info(f"Policy details: {get_result['policy']}")

            # --- PREVIEW UPDATE ---
            logger.info(f"Previewing update for: {policy_name}")
            update_preview = preview_policy_changes(
                action="UPDATE",
                policy_name=policy_name,
                securable_type="SCHEMA",
                securable_fullname=full_schema,
                comment=f"Updated test policy {unique_name}",
            )
            update_token = update_preview["approval_token"]

            # --- UPDATE ---
            logger.info(f"Updating policy: {policy_name}")
            update_result = update_fgac_policy(
                policy_name=policy_name,
                securable_type="SCHEMA",
                securable_fullname=full_schema,
                approval_token=update_token,
                comment=f"Updated test policy {unique_name}",
            )

            assert update_result["success"] is True
            assert update_result["action"] == "updated"
            assert "comment" in update_result["changes"]
            logger.info(f"Policy updated: {update_result['changes']}")

            # --- Verify in list ---
            list_result = list_fgac_policies(
                securable_type="SCHEMA",
                securable_fullname=full_schema,
            )
            policy_names = [p.get("name") for p in list_result["policies"]]
            assert policy_name in policy_names, f"Expected {policy_name} in {policy_names}"
            logger.info(f"Policy found in list ({list_result['policy_count']} total)")

            # --- PREVIEW DELETE ---
            logger.info(f"Previewing delete for: {policy_name}")
            delete_preview = preview_policy_changes(
                action="DELETE",
                policy_name=policy_name,
                securable_type="SCHEMA",
                securable_fullname=full_schema,
            )
            delete_token = delete_preview["approval_token"]

            # --- DELETE ---
            logger.info(f"Deleting policy: {policy_name}")
            delete_result = delete_fgac_policy(
                policy_name=policy_name,
                securable_type="SCHEMA",
                securable_fullname=full_schema,
                approval_token=delete_token,
            )

            assert delete_result["success"] is True
            assert delete_result["action"] == "deleted"
            logger.info("Policy deleted")

        finally:
            self._delete_governed_tag(tag_key)

    def test_create_row_filter_policy(
        self,
        test_catalog: str,
        uc_test_schema: str,
        uc_test_table: str,
        unique_name: str,
        warehouse_id: str,
        cleanup_functions,
        cleanup_policies,
    ):
        """Should create and delete a row filter policy."""
        full_schema = f"{test_catalog}.{uc_test_schema}"
        policy_name = f"{UC_TEST_PREFIX}_filter_{unique_name}"

        # Unique governed tag for this test run
        tag_key = f"uc_test_dept_{unique_name}"
        tag_value = "filter"

        cleanup_policies((policy_name, "SCHEMA", full_schema))

        # --- Setup: governed tag, zero-arg UDF, column tag ---
        self._create_governed_tag(tag_key, [tag_value])

        try:
            fn_name = f"{test_catalog}.{uc_test_schema}.{UC_TEST_PREFIX}_rf_fn_{unique_name}"
            cleanup_functions(fn_name)

            execute_sql(
                sql_query=f"""
                    CREATE OR REPLACE FUNCTION {fn_name}()
                    RETURNS BOOLEAN
                    RETURN TRUE
                """,
                warehouse_id=warehouse_id,
            )
            logger.info(f"Created row filter UDF (0-arg): {fn_name}")

            # Apply governed tag to column
            set_tags(
                object_type="column",
                full_name=uc_test_table,
                column_name="department",
                tags={tag_key: tag_value},
                warehouse_id=warehouse_id,
            )
            logger.info(f"Tagged column department with {tag_key}={tag_value}")

            # Preview create
            logger.info(f"Previewing row filter policy creation: {policy_name}")
            create_preview = preview_policy_changes(
                action="CREATE",
                policy_name=policy_name,
                securable_type="SCHEMA",
                securable_fullname=full_schema,
                policy_type="ROW_FILTER",
                to_principals=["account users"],
                function_name=fn_name,
                tag_name=tag_key,
                tag_value=tag_value,
                comment=f"Test row filter {unique_name}",
            )
            create_token = create_preview["approval_token"]

            # Create row filter policy
            logger.info(f"Creating row filter policy: {policy_name}")
            result = create_fgac_policy(
                policy_name=policy_name,
                policy_type="ROW_FILTER",
                securable_type="SCHEMA",
                securable_fullname=full_schema,
                function_name=fn_name,
                to_principals=["account users"],
                tag_name=tag_key,
                approval_token=create_token,
                tag_value=tag_value,
                comment=f"Test row filter {unique_name}",
            )

            assert result["success"] is True
            assert result["action"] == "created"
            assert result["details"]["policy_type"] == "ROW_FILTER"
            logger.info(f"Row filter policy created: {result['details']}")

            # Preview delete
            delete_preview = preview_policy_changes(
                action="DELETE",
                policy_name=policy_name,
                securable_type="SCHEMA",
                securable_fullname=full_schema,
            )
            delete_token = delete_preview["approval_token"]

            # Delete policy
            delete_fgac_policy(
                policy_name=policy_name,
                securable_type="SCHEMA",
                securable_fullname=full_schema,
                approval_token=delete_token,
            )
            logger.info("Row filter policy deleted")

        finally:
            self._delete_governed_tag(tag_key)

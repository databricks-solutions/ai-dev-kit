"""
Integration tests for Unity Catalog ABAC Policy operations.

Tests the abac_policies module functions:
- list_abac_policies
- get_abac_policy
- get_table_policies
- get_masking_functions
- check_policy_quota
- preview_policy_changes
- create_abac_policy / update_abac_policy / delete_abac_policy

Governed Tags
-------------
ABAC policies require **governed tags** (not regular metadata tags).
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
from databricks_tools_core.unity_catalog.abac_policies import (
    list_abac_policies,
    get_abac_policy,
    get_table_policies,
    get_masking_functions,
    check_policy_quota,
    preview_policy_changes,
    create_abac_policy,
    update_abac_policy,
    delete_abac_policy,
)

logger = logging.getLogger(__name__)

UC_TEST_PREFIX = "uc_test"


# ---------------------------------------------------------------------------
# Discovery tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestListAbacPolicies:
    """Tests for listing ABAC policies."""

    def test_list_policies_on_catalog(self, test_catalog: str):
        """Should list policies on a catalog (may be empty)."""
        result = list_abac_policies(
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
        result = list_abac_policies(
            securable_type="SCHEMA",
            securable_fullname=full_name,
        )

        assert result["success"] is True
        assert result["securable_type"] == "SCHEMA"
        assert isinstance(result["policies"], list)
        logger.info(f"Found {result['policy_count']} policies on schema {full_name}")

    def test_list_policies_with_type_filter(self, test_catalog: str):
        """Should filter policies by type."""
        result = list_abac_policies(
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
        result = list_abac_policies(
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
        logger.info(
            f"Table {uc_test_table}: {len(result['column_masks'])} masks, "
            f"{len(result['row_filters'])} filters"
        )


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
class TestAbacPolicyValidation:
    """Tests for input validation in ABAC policy functions."""

    def test_invalid_securable_type_raises(self):
        """Should raise ValueError for invalid securable type."""
        with pytest.raises(ValueError) as exc_info:
            list_abac_policies(
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
            list_abac_policies(
                securable_type="CATALOG",
                securable_fullname="DROP TABLE; --",
            )

        assert "invalid sql identifier" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# CRUD lifecycle tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAbacPolicyCRUD:
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

        # Wait for governed tag to propagate to the ABAC policy system
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

            # --- CREATE ---
            logger.info(f"Creating ABAC policy: {policy_name}")
            create_result = create_abac_policy(
                policy_name=policy_name,
                policy_type="COLUMN_MASK",
                securable_type="SCHEMA",
                securable_fullname=full_schema,
                function_name=fn_name,
                to_principals=["account users"],
                tag_name=tag_key,
                tag_value=tag_value,
                comment=f"Test policy {unique_name}",
            )

            assert create_result["success"] is True
            assert create_result["policy_name"] == policy_name
            assert create_result["action"] == "created"
            logger.info(f"Policy created: {create_result['details']}")

            # --- GET ---
            logger.info(f"Getting policy: {policy_name}")
            get_result = get_abac_policy(
                policy_name=policy_name,
                securable_type="SCHEMA",
                securable_fullname=full_schema,
            )

            assert get_result["success"] is True
            assert get_result["policy"]["name"] == policy_name
            logger.info(f"Policy details: {get_result['policy']}")

            # --- UPDATE ---
            logger.info(f"Updating policy: {policy_name}")
            update_result = update_abac_policy(
                policy_name=policy_name,
                securable_type="SCHEMA",
                securable_fullname=full_schema,
                comment=f"Updated test policy {unique_name}",
            )

            assert update_result["success"] is True
            assert update_result["action"] == "updated"
            assert "comment" in update_result["changes"]
            logger.info(f"Policy updated: {update_result['changes']}")

            # --- Verify in list ---
            list_result = list_abac_policies(
                securable_type="SCHEMA",
                securable_fullname=full_schema,
            )
            policy_names = [p.get("name") for p in list_result["policies"]]
            assert policy_name in policy_names, f"Expected {policy_name} in {policy_names}"
            logger.info(f"Policy found in list ({list_result['policy_count']} total)")

            # --- DELETE ---
            logger.info(f"Deleting policy: {policy_name}")
            delete_result = delete_abac_policy(
                policy_name=policy_name,
                securable_type="SCHEMA",
                securable_fullname=full_schema,
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

            # Create row filter policy
            logger.info(f"Creating row filter policy: {policy_name}")
            result = create_abac_policy(
                policy_name=policy_name,
                policy_type="ROW_FILTER",
                securable_type="SCHEMA",
                securable_fullname=full_schema,
                function_name=fn_name,
                to_principals=["account users"],
                tag_name=tag_key,
                tag_value=tag_value,
                comment=f"Test row filter {unique_name}",
            )

            assert result["success"] is True
            assert result["action"] == "created"
            assert result["details"]["policy_type"] == "ROW_FILTER"
            logger.info(f"Row filter policy created: {result['details']}")

            # Delete policy
            delete_abac_policy(
                policy_name=policy_name,
                securable_type="SCHEMA",
                securable_fullname=full_schema,
            )
            logger.info("Row filter policy deleted")

        finally:
            self._delete_governed_tag(tag_key)


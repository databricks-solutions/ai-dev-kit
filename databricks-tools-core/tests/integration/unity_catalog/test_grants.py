"""
Integration tests for Unity Catalog - Grant operations.

Tests:
- grant_privileges
- revoke_privileges
- get_grants
- get_effective_grants
"""

import logging
import pytest

from databricks_tools_core.unity_catalog import (
    grant_privileges,
    revoke_privileges,
    get_grants,
    get_effective_grants,
)
from databricks_tools_core.auth import get_workspace_client

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def current_user() -> str:
    """Get the current user's email for grant tests."""
    w = get_workspace_client()
    return w.current_user.me().user_name


@pytest.mark.integration
class TestGetGrants:
    """Tests for getting grants on objects."""

    def test_get_grants_on_catalog(self, test_catalog: str):
        """Should get grants on a catalog."""
        result = get_grants(
            securable_type="catalog",
            full_name=test_catalog,
        )

        logger.info(
            f"Grants on catalog {test_catalog}: {len(result['assignments'])} assignments"
        )
        for a in result["assignments"]:
            logger.info(f"  - {a['principal']}: {a['privileges']}")

        assert result["securable_type"] == "catalog"
        assert result["full_name"] == test_catalog
        assert isinstance(result["assignments"], list)

    def test_get_grants_on_schema(self, test_catalog: str, uc_test_schema: str):
        """Should get grants on a schema."""
        full_name = f"{test_catalog}.{uc_test_schema}"
        result = get_grants(
            securable_type="schema",
            full_name=full_name,
        )

        logger.info(
            f"Grants on schema {full_name}: {len(result['assignments'])} assignments"
        )
        assert result["securable_type"] == "schema"
        assert isinstance(result["assignments"], list)

    def test_get_grants_filtered_by_principal(
        self, test_catalog: str, current_user: str
    ):
        """Should filter grants by principal."""
        result = get_grants(
            securable_type="catalog",
            full_name=test_catalog,
            principal=current_user,
        )

        logger.info(f"Grants for {current_user}: {result['assignments']}")
        assert isinstance(result["assignments"], list)


@pytest.mark.integration
class TestGetEffectiveGrants:
    """Tests for getting effective (inherited) grants."""

    def test_get_effective_grants_on_table(self, uc_test_table: str):
        """Should get effective grants on a table (including inherited)."""
        result = get_effective_grants(
            securable_type="table",
            full_name=uc_test_table,
        )

        logger.info(
            f"Effective grants on {uc_test_table}: {len(result['effective_assignments'])} assignments"
        )
        for a in result["effective_assignments"][:3]:
            logger.info(f"  - {a['principal']}: {len(a['privileges'])} privileges")

        assert result["securable_type"] == "table"
        assert isinstance(result["effective_assignments"], list)


@pytest.mark.integration
class TestGrantRevoke:
    """Tests for granting and revoking privileges."""

    def test_grant_and_revoke_on_schema(self, test_catalog: str, uc_test_schema: str):
        """Should grant and then revoke SELECT on a schema."""
        full_name = f"{test_catalog}.{uc_test_schema}"
        principal = "account users"

        # Grant
        logger.info(f"Granting SELECT to '{principal}' on {full_name}")
        grant_result = grant_privileges(
            securable_type="schema",
            full_name=full_name,
            principal=principal,
            privileges=["SELECT"],
        )

        assert grant_result["status"] == "granted"
        assert grant_result["principal"] == principal
        logger.info(f"Grant result: {grant_result['status']}")

        # Verify grant exists
        grants = get_grants(
            securable_type="schema",
            full_name=full_name,
            principal=principal,
        )
        principals = [a["principal"] for a in grants["assignments"]]
        assert principal in principals, f"Expected '{principal}' in grants"

        # Revoke
        logger.info(f"Revoking SELECT from '{principal}' on {full_name}")
        revoke_result = revoke_privileges(
            securable_type="schema",
            full_name=full_name,
            principal=principal,
            privileges=["SELECT"],
        )

        assert revoke_result["status"] == "revoked"
        logger.info(f"Revoke result: {revoke_result['status']}")

    def test_grant_multiple_privileges(self, test_catalog: str, uc_test_schema: str):
        """Should grant multiple privileges at once."""
        full_name = f"{test_catalog}.{uc_test_schema}"
        principal = "account users"

        try:
            result = grant_privileges(
                securable_type="schema",
                full_name=full_name,
                principal=principal,
                privileges=["SELECT", "MODIFY"],
            )

            assert result["status"] == "granted"
            assert len(result["privileges"]) == 2
            logger.info(f"Multiple privileges granted: {result['privileges']}")

        finally:
            # Cleanup
            try:
                revoke_privileges(
                    securable_type="schema",
                    full_name=full_name,
                    principal=principal,
                    privileges=["SELECT", "MODIFY"],
                )
            except Exception:
                pass

    def test_invalid_securable_type_raises(self):
        """Should raise ValueError for invalid securable type."""
        with pytest.raises(ValueError) as exc_info:
            grant_privileges(
                securable_type="invalid_type",
                full_name="test",
                principal="user",
                privileges=["SELECT"],
            )

        assert "invalid securable_type" in str(exc_info.value).lower()

    def test_invalid_privilege_raises(self, test_catalog: str):
        """Should raise ValueError for invalid privilege."""
        with pytest.raises(ValueError) as exc_info:
            grant_privileges(
                securable_type="catalog",
                full_name=test_catalog,
                principal="account users",
                privileges=["INVALID_PRIVILEGE_XYZ"],
            )

        assert "invalid privilege" in str(exc_info.value).lower()

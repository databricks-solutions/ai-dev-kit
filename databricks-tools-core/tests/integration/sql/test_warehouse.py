"""
Integration tests for SQL warehouse functions.

Tests:
- list_warehouses
- get_best_warehouse
"""

import pytest
from databricks_tools_core.sql import list_warehouses, get_best_warehouse


@pytest.mark.integration
class TestListWarehouses:
    """Tests for list_warehouses function."""

    def test_list_warehouses_returns_list(self):
        """Should return a list of warehouses."""
        warehouses = list_warehouses()

        assert isinstance(warehouses, list)
        assert len(warehouses) > 0, "Expected at least one warehouse"

    def test_list_warehouses_structure(self):
        """Each warehouse should have expected fields."""
        warehouses = list_warehouses()

        for w in warehouses:
            assert "id" in w, "Warehouse should have 'id'"
            assert "name" in w, "Warehouse should have 'name'"
            assert "state" in w, "Warehouse should have 'state'"
            assert w["id"] is not None
            assert w["name"] is not None

    def test_list_warehouses_running_first(self):
        """Running warehouses should be listed first."""
        warehouses = list_warehouses()

        # Find first non-running warehouse
        first_non_running_idx = None
        for i, w in enumerate(warehouses):
            if w["state"] != "RUNNING":
                first_non_running_idx = i
                break

        # If we found a non-running warehouse, all before it should be running
        if first_non_running_idx is not None:
            for i in range(first_non_running_idx):
                assert warehouses[i]["state"] == "RUNNING", f"Warehouse at index {i} should be RUNNING"

    def test_list_warehouses_with_limit(self):
        """Should respect the limit parameter."""
        warehouses_5 = list_warehouses(limit=5)
        warehouses_2 = list_warehouses(limit=2)

        assert len(warehouses_2) <= 2
        assert len(warehouses_5) <= 5


@pytest.mark.integration
class TestGetBestWarehouse:
    """Tests for get_best_warehouse function."""

    def test_get_best_warehouse_returns_string(self):
        """Should return a warehouse ID string."""
        warehouse_id = get_best_warehouse()

        # May be None if no warehouses available
        if warehouse_id is not None:
            assert isinstance(warehouse_id, str)
            assert len(warehouse_id) > 0

    def test_get_best_warehouse_returns_valid_id(self):
        """Returned ID should be in the warehouse list."""
        warehouse_id = get_best_warehouse()

        if warehouse_id is not None:
            warehouses = list_warehouses()
            warehouse_ids = [w["id"] for w in warehouses]
            assert warehouse_id in warehouse_ids, f"Warehouse ID {warehouse_id} not found in list"

    def test_get_best_warehouse_prefers_running(self):
        """Should prefer running warehouses."""
        warehouse_id = get_best_warehouse()

        if warehouse_id is not None:
            warehouses = list_warehouses()
            selected = next((w for w in warehouses if w["id"] == warehouse_id), None)

            # If there are any running warehouses, selected should be running
            running_exists = any(w["state"] == "RUNNING" for w in warehouses)
            if running_exists:
                assert selected["state"] == "RUNNING", "Should select a running warehouse when available"

"""Unit tests for LLM endpoint discovery."""

import pytest
from unittest.mock import patch

from databricks_tools_core.pdf.llm import _discover_databricks_gpt_endpoints, _get_model_name, LLMConfigurationError


class TestEndpointDiscovery:
    """Test dynamic databricks-gpt endpoint discovery."""

    def setup_method(self):
        """Clear the lru_cache before each test."""
        _discover_databricks_gpt_endpoints.cache_clear()

    @patch("databricks_tools_core.pdf.llm.list_serving_endpoints")
    def test_discover_latest_gpt_endpoints(self, mock_list):
        """Test discovering the latest databricks-gpt endpoints."""
        mock_list.return_value = [
            {"name": "databricks-gpt-5-2", "state": "READY"},
            {"name": "databricks-gpt-5-4", "state": "READY"},
            {"name": "databricks-gpt-5-3", "state": "READY"},
            {"name": "databricks-gpt-5-4-nano", "state": "READY"},
            {"name": "databricks-gpt-5-2-nano", "state": "READY"},
            {"name": "other-endpoint", "state": "READY"},
        ]

        main_model, nano_model = _discover_databricks_gpt_endpoints()

        assert main_model == "databricks-gpt-5-4"
        assert nano_model == "databricks-gpt-5-4-nano"

    @patch("databricks_tools_core.pdf.llm.list_serving_endpoints")
    def test_discover_no_nano_falls_back_to_main(self, mock_list):
        """Test that nano falls back to main model if no nano available."""
        mock_list.return_value = [
            {"name": "databricks-gpt-5-4", "state": "READY"},
            {"name": "databricks-gpt-5-3", "state": "READY"},
        ]

        main_model, nano_model = _discover_databricks_gpt_endpoints()

        assert main_model == "databricks-gpt-5-4"
        assert nano_model == "databricks-gpt-5-4"  # Falls back to main

    @patch("databricks_tools_core.pdf.llm.list_serving_endpoints")
    def test_discover_ignores_not_ready_endpoints(self, mock_list):
        """Test that NOT_READY endpoints are ignored."""
        mock_list.return_value = [
            {"name": "databricks-gpt-5-5", "state": "NOT_READY"},
            {"name": "databricks-gpt-5-4", "state": "READY"},
        ]

        main_model, nano_model = _discover_databricks_gpt_endpoints()

        assert main_model == "databricks-gpt-5-4"

    @patch("databricks_tools_core.pdf.llm.list_serving_endpoints")
    def test_discover_no_gpt_endpoints(self, mock_list):
        """Test when no databricks-gpt endpoints exist."""
        mock_list.return_value = [
            {"name": "my-custom-model", "state": "READY"},
        ]

        main_model, nano_model = _discover_databricks_gpt_endpoints()

        assert main_model is None
        assert nano_model is None

    @patch("databricks_tools_core.pdf.llm.list_serving_endpoints")
    def test_discover_handles_api_error(self, mock_list):
        """Test graceful handling of API errors."""
        mock_list.side_effect = Exception("API error")

        main_model, nano_model = _discover_databricks_gpt_endpoints()

        assert main_model is None
        assert nano_model is None


class TestGetModelName:
    """Test model name resolution with priority order."""

    def setup_method(self):
        """Clear the lru_cache before each test."""
        _discover_databricks_gpt_endpoints.cache_clear()

    def test_explicit_model_name_takes_priority(self):
        """Test that explicit model_name parameter wins."""
        result = _get_model_name(mini=False, model_name="my-custom-model")
        assert result == "my-custom-model"

    @patch.dict("os.environ", {"DATABRICKS_MODEL": "env-model"})
    def test_env_var_takes_priority_over_discovery(self):
        """Test that env var is used before auto-discovery."""
        result = _get_model_name(mini=False)
        assert result == "env-model"

    @patch.dict("os.environ", {"DATABRICKS_MODEL_NANO": "env-nano-model"})
    def test_nano_env_var_for_mini(self):
        """Test that DATABRICKS_MODEL_NANO is used for mini=True."""
        result = _get_model_name(mini=True)
        assert result == "env-nano-model"

    @patch.dict("os.environ", {}, clear=True)
    @patch("databricks_tools_core.pdf.llm._discover_databricks_gpt_endpoints")
    def test_auto_discovery_when_no_env(self, mock_discover):
        """Test auto-discovery when no env vars set."""
        mock_discover.return_value = ("databricks-gpt-5-4", "databricks-gpt-5-4-nano")

        result = _get_model_name(mini=False)
        assert result == "databricks-gpt-5-4"

        result = _get_model_name(mini=True)
        assert result == "databricks-gpt-5-4-nano"

    @patch.dict("os.environ", {}, clear=True)
    @patch("databricks_tools_core.pdf.llm._discover_databricks_gpt_endpoints")
    def test_raises_error_when_no_model_found(self, mock_discover):
        """Test that LLMConfigurationError is raised when no model available."""
        mock_discover.return_value = (None, None)

        with pytest.raises(LLMConfigurationError) as exc_info:
            _get_model_name(mini=False)

        assert "No LLM model configured" in str(exc_info.value)

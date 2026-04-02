"""Unit tests for Model Serving metrics export."""

from unittest import mock

import pytest
from databricks.sdk.errors import ResourceDoesNotExist

from databricks_tools_core.serving import export_serving_endpoint_metrics
from databricks_tools_core.serving.endpoints import _parse_prometheus_metrics

_GET_CLIENT = "databricks_tools_core.serving.endpoints.get_workspace_client"

SAMPLE_PROMETHEUS = """# HELP cpu_usage_percentage Average CPU utilization
# TYPE cpu_usage_percentage gauge
cpu_usage_percentage{endpoint_name="test-ep",served_model="model-1"} 45.2
# HELP request_count_total Number of requests processed
# TYPE request_count_total counter
request_count_total{endpoint_name="test-ep",served_model="model-1"} 1234
# HELP request_latency_ms Round-trip latency
# TYPE request_latency_ms histogram
request_latency_ms_bucket{endpoint_name="test-ep",le="50"} 100
request_latency_ms_bucket{endpoint_name="test-ep",le="100"} 200
request_latency_ms_sum{endpoint_name="test-ep"} 5678.9
request_latency_ms_count{endpoint_name="test-ep"} 300
"""


class TestParsePrometheusMetrics:
    """Tests for _parse_prometheus_metrics."""

    def test_parse_gauge(self):
        """Parses gauge metrics with labels."""
        metrics = _parse_prometheus_metrics(SAMPLE_PROMETHEUS)
        cpu = [m for m in metrics if m["name"] == "cpu_usage_percentage"]
        assert len(cpu) == 1
        assert cpu[0]["value"] == 45.2
        assert cpu[0]["labels"]["endpoint_name"] == "test-ep"
        assert cpu[0]["type"] == "gauge"
        assert cpu[0]["help"] == "Average CPU utilization"

    def test_parse_counter(self):
        """Parses counter metrics."""
        metrics = _parse_prometheus_metrics(SAMPLE_PROMETHEUS)
        count = [m for m in metrics if m["name"] == "request_count_total"]
        assert len(count) == 1
        assert count[0]["value"] == 1234.0
        assert count[0]["type"] == "counter"

    def test_parse_histogram_buckets(self):
        """Parses histogram bucket, sum, and count metrics."""
        metrics = _parse_prometheus_metrics(SAMPLE_PROMETHEUS)
        buckets = [m for m in metrics if m["name"] == "request_latency_ms_bucket"]
        assert len(buckets) == 2
        assert buckets[0]["labels"]["le"] == "50"
        assert buckets[0]["value"] == 100.0

    def test_parse_empty(self):
        """Returns empty list for empty input."""
        assert _parse_prometheus_metrics("") == []
        assert _parse_prometheus_metrics("# just comments\n# TYPE foo gauge") == []

    def test_parse_no_labels(self):
        """Parses metrics without labels."""
        text = "up 1\n"
        metrics = _parse_prometheus_metrics(text)
        assert len(metrics) == 1
        assert metrics[0]["name"] == "up"
        assert metrics[0]["value"] == 1.0
        assert metrics[0]["labels"] == {}

    def test_parse_with_timestamp(self):
        """Parses metrics with optional Prometheus timestamp."""
        text = 'request_count_total{endpoint="ep"} 42.0 1775162940000\n'
        metrics = _parse_prometheus_metrics(text)
        assert len(metrics) == 1
        assert metrics[0]["value"] == 42.0
        assert metrics[0]["labels"]["endpoint"] == "ep"


class TestExportServingEndpointMetrics:
    """Tests for export_serving_endpoint_metrics."""

    @mock.patch(_GET_CLIENT)
    def test_export_metrics_success(self, mock_get_client):
        """export_metrics returns parsed metrics and raw text."""
        mock_client = mock.Mock()
        mock_contents = mock.Mock()
        mock_contents.read.return_value = SAMPLE_PROMETHEUS.encode("utf-8")
        mock_response = mock.Mock()
        mock_response.contents = mock_contents
        mock_client.serving_endpoints.export_metrics.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = export_serving_endpoint_metrics(name="test-ep")

        assert result["name"] == "test-ep"
        assert len(result["metrics"]) > 0
        assert SAMPLE_PROMETHEUS in result["raw"]
        mock_client.serving_endpoints.export_metrics.assert_called_once_with(name="test-ep")

    @mock.patch(_GET_CLIENT)
    def test_export_metrics_not_found(self, mock_get_client):
        """export_metrics raises for non-existent endpoint."""
        mock_client = mock.Mock()
        mock_client.serving_endpoints.export_metrics.side_effect = ResourceDoesNotExist("Endpoint does not exist")
        mock_get_client.return_value = mock_client

        with pytest.raises(Exception, match="not found"):
            export_serving_endpoint_metrics(name="missing-ep")

    @mock.patch(_GET_CLIENT)
    def test_export_metrics_empty(self, mock_get_client):
        """export_metrics handles empty metrics response."""
        mock_client = mock.Mock()
        mock_contents = mock.Mock()
        mock_contents.read.return_value = b""
        mock_response = mock.Mock()
        mock_response.contents = mock_contents
        mock_client.serving_endpoints.export_metrics.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = export_serving_endpoint_metrics(name="test-ep")

        assert result["metrics"] == []
        assert result["raw"] == ""

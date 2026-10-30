"""Unit tests for serverless code execution (run timeout and timeout handling)."""

from unittest import mock

import pytest
from databricks.sdk.service.jobs import RunResultState

from databricks_tools_core.compute import serverless
from databricks_tools_core.compute.serverless import run_code_on_serverless

RUN_ID = 12345
NOTEBOOK_PATH = "/Workspace/Users/me/.ai_dev_kit_tmp/serverless_abc"


@pytest.fixture
def mock_ws():
    """Patch the workspace client and notebook helpers used by run_code_on_serverless."""
    w = mock.Mock()
    wait = mock.Mock()
    wait.run_id = RUN_ID
    w.jobs.submit.return_value = wait
    w.jobs.get_run.return_value.run_page_url = "https://host/run/12345"

    with (
        mock.patch.object(serverless, "get_workspace_client", return_value=w),
        mock.patch.object(serverless, "_get_temp_notebook_path", return_value=NOTEBOOK_PATH),
        mock.patch.object(serverless, "_upload_temp_notebook"),
        mock.patch.object(serverless, "_cleanup_temp_notebook") as cleanup,
    ):
        w.cleanup = cleanup
        yield w


def _make_successful_run(w):
    run = mock.Mock()
    run.state.result_state = RunResultState.SUCCESS
    run.state.state_message = None
    run.run_page_url = "https://host/run/12345"
    run.tasks = []
    w.jobs.submit.return_value.result.return_value = run


class TestRunTimeoutSeconds:
    """The run must always be bounded server-side (issue #607)."""

    def test_timeout_is_sent_as_timeout_seconds(self, mock_ws):
        _make_successful_run(mock_ws)

        run_code_on_serverless("print(1)", timeout=60)

        assert mock_ws.jobs.submit.call_args.kwargs["timeout_seconds"] == 60

    def test_job_extra_params_timeout_seconds_overrides(self, mock_ws):
        _make_successful_run(mock_ws)

        run_code_on_serverless("print(1)", timeout=60, job_extra_params={"timeout_seconds": 7200})

        assert mock_ws.jobs.submit.call_args.kwargs["timeout_seconds"] == 7200

    def test_success_cleans_up_notebook(self, mock_ws):
        _make_successful_run(mock_ws)

        result = run_code_on_serverless("print(1)")

        assert result.success
        mock_ws.cleanup.assert_called_once_with(NOTEBOOK_PATH)


class TestClientTimeout:
    """When the client wait expires the run is cancelled, or reported as still running."""

    @pytest.fixture(autouse=True)
    def _wait_times_out(self, mock_ws):
        mock_ws.jobs.submit.return_value.result.side_effect = TimeoutError("timed out")

    def test_cancels_run_and_reports_canceled(self, mock_ws):
        result = run_code_on_serverless("print(1)", timeout=60)

        mock_ws.jobs.cancel_run.assert_called_once()
        assert mock_ws.jobs.cancel_run.call_args.kwargs.get("run_id", RUN_ID) == RUN_ID
        assert not result.success
        assert result.state == "CANCELED"
        mock_ws.cleanup.assert_called_once_with(NOTEBOOK_PATH)

    def test_cancel_failure_reports_still_running_and_keeps_notebook(self, mock_ws):
        mock_ws.jobs.cancel_run.side_effect = Exception("permission denied")

        result = run_code_on_serverless("print(1)", timeout=60)

        assert result.state == "STILL_RUNNING"
        assert result.workspace_path == NOTEBOOK_PATH
        assert "https://host/run/12345" in result.message
        mock_ws.cleanup.assert_not_called()

    def test_opt_out_does_not_cancel(self, mock_ws):
        result = run_code_on_serverless("print(1)", timeout=60, cancel_on_timeout=False)

        mock_ws.jobs.cancel_run.assert_not_called()
        assert result.state == "STILL_RUNNING"
        mock_ws.cleanup.assert_not_called()

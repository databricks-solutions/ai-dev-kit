"""Unit tests for serverless code execution (run timeout and timeout handling)."""

import datetime
from unittest import mock

import pytest
from databricks.sdk.service.jobs import RunLifeCycleState, RunResultState

from databricks_tools_core.compute import serverless
from databricks_tools_core.compute.serverless import run_code_on_serverless

RUN_ID = 12345
RUN_URL = "https://host/run/12345"
NOTEBOOK_PATH = "/Workspace/Users/me/.ai_dev_kit_tmp/serverless_abc"
GRACE = serverless._CLIENT_WAIT_GRACE_SECONDS


@pytest.fixture
def mock_ws():
    """Patch the workspace client and notebook helpers used by run_code_on_serverless."""
    w = mock.Mock()
    wait = mock.Mock()
    wait.run_id = RUN_ID
    w.jobs.submit.return_value = wait
    # get_run reports an active run unless a test says otherwise.
    w.jobs.get_run.return_value.run_page_url = RUN_URL
    w.jobs.get_run.return_value.state.life_cycle_state = RunLifeCycleState.RUNNING

    with (
        mock.patch.object(serverless, "get_workspace_client", return_value=w),
        mock.patch.object(serverless, "_get_temp_notebook_path", return_value=NOTEBOOK_PATH),
        mock.patch.object(serverless, "_upload_temp_notebook"),
        mock.patch.object(serverless, "_cleanup_temp_notebook") as cleanup,
        mock.patch.object(serverless, "_get_run_output", return_value={"output": None, "error": None}),
    ):
        w.cleanup = cleanup
        yield w


def _make_run(life_cycle_state, result_state):
    run = mock.Mock()
    run.state.life_cycle_state = life_cycle_state
    run.state.result_state = result_state
    run.state.state_message = None
    run.run_page_url = RUN_URL
    run.tasks = []
    return run


def _make_successful_run(w):
    w.jobs.submit.return_value.result.return_value = _make_run(RunLifeCycleState.TERMINATED, RunResultState.SUCCESS)


def _client_wait_seconds(w):
    return w.jobs.submit.return_value.result.call_args.kwargs["timeout"]


class TestRunTimeoutSeconds:
    """The run must always be bounded server-side (issue #607)."""

    def test_timeout_is_sent_as_timeout_seconds(self, mock_ws):
        _make_successful_run(mock_ws)

        run_code_on_serverless("print(1)", timeout=60)

        assert mock_ws.jobs.submit.call_args.kwargs["timeout_seconds"] == 60
        assert _client_wait_seconds(mock_ws) == datetime.timedelta(seconds=60 + GRACE)

    def test_job_extra_params_timeout_seconds_overrides_run_limit_and_wait(self, mock_ws):
        _make_successful_run(mock_ws)

        run_code_on_serverless("print(1)", timeout=60, job_extra_params={"timeout_seconds": 7200})

        assert mock_ws.jobs.submit.call_args.kwargs["timeout_seconds"] == 7200
        assert _client_wait_seconds(mock_ws) == datetime.timedelta(seconds=7200 + GRACE)

    @pytest.mark.parametrize("timeout", [0, -5])
    def test_non_positive_timeout_is_rejected(self, mock_ws, timeout):
        result = run_code_on_serverless("print(1)", timeout=timeout)

        assert result.state == "INVALID_INPUT"
        mock_ws.jobs.submit.assert_not_called()

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

    def test_finished_run_reports_real_state_without_cancelling(self, mock_ws):
        mock_ws.jobs.get_run.return_value = _make_run(RunLifeCycleState.TERMINATED, RunResultState.TIMEDOUT)

        result = run_code_on_serverless("print(1)", timeout=60)

        mock_ws.jobs.cancel_run.assert_not_called()
        assert result.state == "TIMEDOUT"
        mock_ws.cleanup.assert_called_once_with(NOTEBOOK_PATH)

    def test_cancels_active_run_and_reports_canceled(self, mock_ws):
        result = run_code_on_serverless("print(1)", timeout=60)

        mock_ws.jobs.cancel_run.assert_called_once_with(run_id=RUN_ID)
        assert not result.success
        assert result.state == "CANCELED"
        assert result.workspace_path is None
        mock_ws.cleanup.assert_called_once_with(NOTEBOOK_PATH)

    def test_unconfirmed_cancel_reports_still_running_and_keeps_notebook(self, mock_ws):
        mock_ws.jobs.cancel_run.return_value.result.side_effect = TimeoutError("still terminating")

        result = run_code_on_serverless("print(1)", timeout=60)

        assert result.state == "STILL_RUNNING"
        assert result.workspace_path == NOTEBOOK_PATH
        assert RUN_URL in result.message
        mock_ws.cleanup.assert_not_called()

    def test_cancel_failure_reports_still_running_and_keeps_notebook(self, mock_ws):
        mock_ws.jobs.cancel_run.side_effect = Exception("permission denied")

        result = run_code_on_serverless("print(1)", timeout=60)

        assert result.state == "STILL_RUNNING"
        assert result.workspace_path == NOTEBOOK_PATH
        mock_ws.cleanup.assert_not_called()

    def test_opt_out_does_not_cancel(self, mock_ws):
        result = run_code_on_serverless("print(1)", timeout=60, cancel_on_timeout=False)

        mock_ws.jobs.cancel_run.assert_not_called()
        assert result.state == "STILL_RUNNING"
        mock_ws.cleanup.assert_not_called()

    def test_persistent_mode_returns_workspace_path_when_canceled(self, mock_ws):
        saved = "/Workspace/Users/me/project/nb"

        result = run_code_on_serverless("print(1)", timeout=60, workspace_path=saved)

        assert result.state == "CANCELED"
        assert result.workspace_path == saved
        mock_ws.cleanup.assert_not_called()

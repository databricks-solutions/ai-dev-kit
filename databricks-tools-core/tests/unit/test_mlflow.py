"""Unit tests for MLflow experiment and run operations."""

from unittest import mock
from unittest.mock import MagicMock

import pytest

from databricks.sdk.errors import NotFound, ResourceDoesNotExist

from databricks_tools_core.mlflow import (
    get_experiment,
    list_experiments,
    search_experiments,
    create_experiment,
    set_experiment_tag,
    delete_experiment,
    get_run,
    search_runs,
    get_run_metrics_history,
    list_run_artifacts,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_experiment(experiment_id="123", name="/Users/me/exp", lifecycle_stage="active"):
    exp = MagicMock()
    exp.experiment_id = experiment_id
    exp.name = name
    exp.artifact_location = f"dbfs:/databricks/mlflow-tracking/{experiment_id}"
    exp.lifecycle_stage = lifecycle_stage
    exp.last_update_time = 1700000000000
    exp.creation_time = 1699000000000
    exp.tags = []
    return exp


def _make_run(run_id="abc123", status_value="FINISHED"):
    run = MagicMock()
    info = MagicMock()
    info.run_id = run_id
    info.run_name = "test-run"
    info.experiment_id = "123"

    status = MagicMock()
    status.value = status_value
    info.status = status

    info.start_time = 1700000000000
    info.end_time = 1700000060000
    info.artifact_uri = f"dbfs:/artifacts/{run_id}"
    info.lifecycle_stage = "active"
    info.user_id = "user@example.com"

    data = MagicMock()
    metric = MagicMock()
    metric.key = "accuracy"
    metric.value = 0.95
    data.metrics = [metric]

    param = MagicMock()
    param.key = "model_type"
    param.value = "xgboost"
    data.params = [param]

    tag = MagicMock()
    tag.key = "mlflow.runName"
    tag.value = "test-run"
    data.tags = [tag]

    run.info = info
    run.data = data
    return run


# ---------------------------------------------------------------------------
# Experiment tests
# ---------------------------------------------------------------------------


class TestGetExperiment:
    @mock.patch("databricks_tools_core.mlflow.experiments.get_workspace_client")
    def test_get_by_id(self, mock_client):
        exp = _make_experiment()
        resp = MagicMock()
        resp.experiment = exp
        mock_client.return_value.experiments.get_experiment.return_value = resp

        result = get_experiment(experiment_id="123")

        assert result["experiment_id"] == "123"
        assert result["name"] == "/Users/me/exp"
        assert result["lifecycle_stage"] == "active"
        mock_client.return_value.experiments.get_experiment.assert_called_once_with(experiment_id="123")

    @mock.patch("databricks_tools_core.mlflow.experiments.get_workspace_client")
    def test_get_by_name(self, mock_client):
        exp = _make_experiment()
        resp = MagicMock()
        resp.experiment = exp
        mock_client.return_value.experiments.get_by_name.return_value = resp

        result = get_experiment(name="/Users/me/exp")

        assert result["experiment_id"] == "123"
        mock_client.return_value.experiments.get_by_name.assert_called_once_with(experiment_name="/Users/me/exp")

    @mock.patch("databricks_tools_core.mlflow.experiments.get_workspace_client")
    def test_not_found(self, mock_client):
        mock_client.return_value.experiments.get_experiment.side_effect = ResourceDoesNotExist("not found")

        result = get_experiment(experiment_id="999")

        assert result["status"] == "not_found"
        assert "not found" in result["error"].lower()

    def test_no_args_raises(self):
        with pytest.raises(ValueError, match="Must provide"):
            get_experiment()

    @mock.patch("databricks_tools_core.mlflow.experiments.get_workspace_client")
    def test_null_experiment_returns_not_found(self, mock_client):
        resp = MagicMock()
        resp.experiment = None
        mock_client.return_value.experiments.get_experiment.return_value = resp

        result = get_experiment(experiment_id="123")

        assert result["status"] == "not_found"


class TestListExperiments:
    @mock.patch("databricks_tools_core.mlflow.experiments.get_workspace_client")
    def test_list_returns_experiments(self, mock_client):
        exps = [_make_experiment(f"{i}", f"/exp-{i}") for i in range(3)]
        mock_client.return_value.experiments.list_experiments.return_value = iter(exps)

        result = list_experiments(max_results=10)

        assert result["count"] == 3
        assert len(result["experiments"]) == 3
        assert result["experiments"][0]["experiment_id"] == "0"

    @mock.patch("databricks_tools_core.mlflow.experiments.get_workspace_client")
    def test_list_respects_max_results(self, mock_client):
        exps = [_make_experiment(f"{i}", f"/exp-{i}") for i in range(10)]
        mock_client.return_value.experiments.list_experiments.return_value = iter(exps)

        result = list_experiments(max_results=3)

        assert result["count"] == 3

    @mock.patch("databricks_tools_core.mlflow.experiments.get_workspace_client")
    def test_list_empty(self, mock_client):
        mock_client.return_value.experiments.list_experiments.return_value = iter([])

        result = list_experiments()

        assert result["count"] == 0
        assert result["experiments"] == []


class TestSearchExperiments:
    @mock.patch("databricks_tools_core.mlflow.experiments.get_workspace_client")
    def test_search_with_filter(self, mock_client):
        exps = [_make_experiment("1", "/matching")]
        mock_client.return_value.experiments.search_experiments.return_value = iter(exps)

        result = search_experiments(filter_string="name LIKE '%matching%'")

        assert result["count"] == 1
        assert result["experiments"][0]["name"] == "/matching"


class TestCreateExperiment:
    @mock.patch("databricks_tools_core.mlflow.experiments.get_workspace_client")
    def test_create_success(self, mock_client):
        resp = MagicMock()
        resp.experiment_id = "456"
        mock_client.return_value.experiments.create_experiment.return_value = resp

        result = create_experiment(name="/Users/me/new-exp")

        assert result["experiment_id"] == "456"
        assert result["status"] == "created"

    @mock.patch("databricks_tools_core.mlflow.experiments.get_workspace_client")
    def test_create_already_exists(self, mock_client):
        mock_client.return_value.experiments.create_experiment.side_effect = Exception("RESOURCE_ALREADY_EXISTS")

        result = create_experiment(name="/Users/me/existing")

        assert result["status"] == "already_exists"

    @mock.patch("databricks_tools_core.mlflow.experiments.get_workspace_client")
    def test_create_with_tags(self, mock_client):
        resp = MagicMock()
        resp.experiment_id = "789"
        mock_client.return_value.experiments.create_experiment.return_value = resp

        result = create_experiment(name="/Users/me/tagged", tags={"team": "ml"})

        assert result["status"] == "created"
        call_kwargs = mock_client.return_value.experiments.create_experiment.call_args
        assert call_kwargs.kwargs["tags"] is not None


class TestCreateExperimentKind:
    @mock.patch("databricks_tools_core.mlflow.experiments.get_workspace_client")
    def test_create_with_genai_kind(self, mock_client):
        resp = MagicMock()
        resp.experiment_id = "789"
        mock_client.return_value.experiments.create_experiment.return_value = resp

        result = create_experiment(name="/Users/me/agent", experiment_kind="genai")

        assert result["status"] == "created"
        call_kwargs = mock_client.return_value.experiments.create_experiment.call_args
        tags = call_kwargs.kwargs["tags"]
        tag_dict = {t.key: t.value for t in tags}
        assert tag_dict["mlflow.experimentKind"] == "genai_development"

    @mock.patch("databricks_tools_core.mlflow.experiments.get_workspace_client")
    def test_create_with_ml_kind(self, mock_client):
        resp = MagicMock()
        resp.experiment_id = "790"
        mock_client.return_value.experiments.create_experiment.return_value = resp

        create_experiment(name="/Users/me/ml-exp", experiment_kind="ml")

        call_kwargs = mock_client.return_value.experiments.create_experiment.call_args
        tags = call_kwargs.kwargs["tags"]
        tag_dict = {t.key: t.value for t in tags}
        assert tag_dict["mlflow.experimentKind"] == "custom_model_development"

    @mock.patch("databricks_tools_core.mlflow.experiments.get_workspace_client")
    def test_create_with_kind_and_extra_tags(self, mock_client):
        resp = MagicMock()
        resp.experiment_id = "791"
        mock_client.return_value.experiments.create_experiment.return_value = resp

        create_experiment(name="/Users/me/exp", experiment_kind="genai", tags={"team": "ml"})

        call_kwargs = mock_client.return_value.experiments.create_experiment.call_args
        tags = call_kwargs.kwargs["tags"]
        tag_dict = {t.key: t.value for t in tags}
        assert tag_dict["mlflow.experimentKind"] == "genai_development"
        assert tag_dict["team"] == "ml"


class TestSetExperimentTag:
    @mock.patch("databricks_tools_core.mlflow.experiments.get_workspace_client")
    def test_set_tag_success(self, mock_client):
        mock_client.return_value.experiments.set_experiment_tag.return_value = None

        result = set_experiment_tag("123", "team", "ml-eng")

        assert result["status"] == "set"
        assert result["key"] == "team"
        assert result["value"] == "ml-eng"
        mock_client.return_value.experiments.set_experiment_tag.assert_called_once_with(
            experiment_id="123", key="team", value="ml-eng"
        )

    @mock.patch("databricks_tools_core.mlflow.experiments.get_workspace_client")
    def test_set_tag_not_found(self, mock_client):
        mock_client.return_value.experiments.set_experiment_tag.side_effect = NotFound("not found")

        result = set_experiment_tag("999", "key", "val")

        assert result["status"] == "not_found"


class TestDeleteExperiment:
    @mock.patch("databricks_tools_core.mlflow.experiments.get_workspace_client")
    def test_delete_success(self, mock_client):
        mock_client.return_value.experiments.delete_experiment.return_value = None

        result = delete_experiment(experiment_id="123")

        assert result["status"] == "deleted"
        mock_client.return_value.experiments.delete_experiment.assert_called_once_with(experiment_id="123")

    @mock.patch("databricks_tools_core.mlflow.experiments.get_workspace_client")
    def test_delete_not_found(self, mock_client):
        mock_client.return_value.experiments.delete_experiment.side_effect = NotFound("not found")

        result = delete_experiment(experiment_id="999")

        assert result["status"] == "not_found"


# ---------------------------------------------------------------------------
# Run tests
# ---------------------------------------------------------------------------


class TestGetRun:
    @mock.patch("databricks_tools_core.mlflow.experiments.get_workspace_client")
    def test_get_run_success(self, mock_client):
        run = _make_run()
        resp = MagicMock()
        resp.run = run
        mock_client.return_value.experiments.get_run.return_value = resp

        result = get_run(run_id="abc123")

        assert result["run_id"] == "abc123"
        assert result["status"] == "FINISHED"
        assert result["metrics"]["accuracy"] == 0.95
        assert result["params"]["model_type"] == "xgboost"

    @mock.patch("databricks_tools_core.mlflow.experiments.get_workspace_client")
    def test_get_run_not_found(self, mock_client):
        mock_client.return_value.experiments.get_run.side_effect = ResourceDoesNotExist("not found")

        result = get_run(run_id="missing")

        assert result["status"] == "not_found"


class TestSearchRuns:
    @mock.patch("databricks_tools_core.mlflow.experiments.get_workspace_client")
    def test_search_runs_success(self, mock_client):
        runs = [_make_run("run1"), _make_run("run2")]
        mock_client.return_value.experiments.search_runs.return_value = iter(runs)

        result = search_runs(experiment_ids=["123"], max_results=10)

        assert result["count"] == 2
        assert result["runs"][0]["run_id"] == "run1"

    @mock.patch("databricks_tools_core.mlflow.experiments.get_workspace_client")
    def test_search_runs_with_filter(self, mock_client):
        runs = [_make_run("best")]
        mock_client.return_value.experiments.search_runs.return_value = iter(runs)

        result = search_runs(
            experiment_ids=["123"],
            filter_string="metrics.accuracy > 0.9",
            order_by=["metrics.accuracy DESC"],
        )

        assert result["count"] == 1

    @mock.patch("databricks_tools_core.mlflow.experiments.get_workspace_client")
    def test_search_runs_respects_max(self, mock_client):
        runs = [_make_run(f"run{i}") for i in range(10)]
        mock_client.return_value.experiments.search_runs.return_value = iter(runs)

        result = search_runs(experiment_ids=["123"], max_results=3)

        assert result["count"] == 3


class TestGetRunMetricsHistory:
    @mock.patch("databricks_tools_core.mlflow.experiments.get_workspace_client")
    def test_metric_history(self, mock_client):
        metrics = []
        for i in range(5):
            m = MagicMock()
            m.value = 0.5 - (i * 0.1)
            m.timestamp = 1700000000000 + i
            m.step = i
            metrics.append(m)
        mock_client.return_value.experiments.get_history.return_value = iter(metrics)

        result = get_run_metrics_history(run_id="abc", metric_key="loss")

        assert result["metric_key"] == "loss"
        assert result["count"] == 5
        assert result["history"][0]["value"] == 0.5

    @mock.patch("databricks_tools_core.mlflow.experiments.get_workspace_client")
    def test_metric_history_not_found(self, mock_client):
        mock_client.return_value.experiments.get_history.side_effect = ResourceDoesNotExist("not found")

        result = get_run_metrics_history(run_id="missing", metric_key="loss")

        assert result["status"] == "not_found"


class TestListRunArtifacts:
    @mock.patch("databricks_tools_core.mlflow.experiments.get_workspace_client")
    def test_list_artifacts(self, mock_client):
        artifacts = []
        for name, is_dir, size in [("model", True, None), ("metrics.json", False, 1024)]:
            f = MagicMock()
            f.path = name
            f.is_dir = is_dir
            f.file_size = size
            artifacts.append(f)
        mock_client.return_value.experiments.list_artifacts.return_value = iter(artifacts)

        result = list_run_artifacts(run_id="abc")

        assert result["count"] == 2
        assert result["artifacts"][0]["path"] == "model"
        assert result["artifacts"][0]["is_dir"] is True
        assert result["artifacts"][1]["file_size"] == 1024

    @mock.patch("databricks_tools_core.mlflow.experiments.get_workspace_client")
    def test_list_artifacts_not_found(self, mock_client):
        mock_client.return_value.experiments.list_artifacts.side_effect = NotFound("not found")

        result = list_run_artifacts(run_id="missing")

        assert result["status"] == "not_found"

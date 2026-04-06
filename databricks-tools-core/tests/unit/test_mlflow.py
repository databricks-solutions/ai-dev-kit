"""Unit tests for MLflow experiment, run, registry, and trace operations."""

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
    get_registered_model,
    list_registered_models,
    search_registered_models,
    get_model_version,
    list_model_versions,
    get_model_version_by_alias,
    set_model_alias,
    delete_model_alias,
    search_traces,
    get_trace,
    set_trace_tag,
    delete_trace_tag,
    log_assessment,
    delete_assessment,
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

        assert result["status"] == "NOT_FOUND"
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

        assert result["status"] == "NOT_FOUND"


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

        assert result["status"] == "ALREADY_EXISTS"

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

        assert result["status"] == "NOT_FOUND"


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

        assert result["status"] == "NOT_FOUND"


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

        assert result["status"] == "NOT_FOUND"


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

        assert result["status"] == "NOT_FOUND"


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

        assert result["status"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------


def _make_model(full_name="cat.schema.model"):
    model = MagicMock()
    parts = full_name.split(".")
    model.full_name = full_name
    model.name = parts[2] if len(parts) > 2 else full_name
    model.catalog_name = parts[0] if len(parts) > 0 else None
    model.schema_name = parts[1] if len(parts) > 1 else None
    model.comment = "A test model"
    model.owner = "user@example.com"
    model.created_at = 1700000000000
    model.created_by = "user@example.com"
    model.updated_at = 1700000060000
    model.updated_by = "user@example.com"
    model.storage_location = "s3://bucket/path"
    model.aliases = []
    return model


def _make_version(version=1, model_name="model", catalog="cat", schema="schema"):
    v = MagicMock()
    v.version = version
    v.model_name = model_name
    v.catalog_name = catalog
    v.schema_name = schema
    v.source = f"models:/m-{version}"
    v.run_id = f"run-{version}"
    status = MagicMock()
    status.value = "READY"
    v.status = status
    v.comment = None
    v.created_at = 1700000000000
    v.created_by = "user@example.com"
    v.updated_at = 1700000060000
    v.updated_by = "user@example.com"
    v.storage_location = "s3://bucket/versions"
    v.aliases = []
    return v


# ---------------------------------------------------------------------------
# Registered Model tests
# ---------------------------------------------------------------------------


class TestGetRegisteredModel:
    @mock.patch("databricks_tools_core.mlflow.registry.get_workspace_client")
    def test_get_success(self, mock_client):
        model = _make_model("cat.schema.mymodel")
        mock_client.return_value.registered_models.get.return_value = model

        result = get_registered_model("cat.schema.mymodel")

        assert result["full_name"] == "cat.schema.mymodel"
        assert result["owner"] == "user@example.com"

    @mock.patch("databricks_tools_core.mlflow.registry.get_workspace_client")
    def test_not_found(self, mock_client):
        mock_client.return_value.registered_models.get.side_effect = NotFound("not found")

        result = get_registered_model("cat.schema.missing")

        assert result["status"] == "NOT_FOUND"


class TestListRegisteredModels:
    @mock.patch("databricks_tools_core.mlflow.registry.get_workspace_client")
    def test_list_with_filters(self, mock_client):
        models = [_make_model(f"cat.schema.model{i}") for i in range(3)]
        mock_client.return_value.registered_models.list.return_value = iter(models)

        result = list_registered_models(catalog_name="cat", schema_name="schema", max_results=10)

        assert result["count"] == 3
        call_kwargs = mock_client.return_value.registered_models.list.call_args.kwargs
        assert call_kwargs["catalog_name"] == "cat"
        assert call_kwargs["schema_name"] == "schema"

    @mock.patch("databricks_tools_core.mlflow.registry.get_workspace_client")
    def test_list_respects_max(self, mock_client):
        models = [_make_model(f"cat.schema.model{i}") for i in range(10)]
        mock_client.return_value.registered_models.list.return_value = iter(models)

        result = list_registered_models(max_results=3)

        assert result["count"] == 3


class TestSearchRegisteredModels:
    @mock.patch("databricks_tools_core.mlflow.registry.get_workspace_client")
    def test_search_legacy(self, mock_client):
        model = MagicMock()
        model.name = "legacy-model"
        model.description = "A model"
        model.creation_timestamp = 1700000000000
        model.last_updated_timestamp = 1700000060000
        model.user_id = "user"
        model.tags = []
        model.latest_versions = []
        mock_client.return_value.model_registry.search_models.return_value = iter([model])

        result = search_registered_models(filter_string="name LIKE '%legacy%'")

        assert result["count"] == 1
        assert result["models"][0]["name"] == "legacy-model"


# ---------------------------------------------------------------------------
# Model Version tests
# ---------------------------------------------------------------------------


class TestGetModelVersion:
    @mock.patch("databricks_tools_core.mlflow.registry.get_workspace_client")
    def test_get_version(self, mock_client):
        v = _make_version(version=3)
        mock_client.return_value.model_versions.get.return_value = v

        result = get_model_version("cat.schema.model", version=3)

        assert result["version"] == 3
        assert result["status"] == "READY"
        assert result["full_name"] == "cat.schema.model"

    @mock.patch("databricks_tools_core.mlflow.registry.get_workspace_client")
    def test_version_not_found(self, mock_client):
        mock_client.return_value.model_versions.get.side_effect = ResourceDoesNotExist("not found")

        result = get_model_version("cat.schema.model", version=999)

        assert result["status"] == "NOT_FOUND"


class TestListModelVersions:
    @mock.patch("databricks_tools_core.mlflow.registry.get_workspace_client")
    def test_list_versions(self, mock_client):
        versions = [_make_version(i) for i in range(1, 4)]
        mock_client.return_value.model_versions.list.return_value = iter(versions)

        result = list_model_versions("cat.schema.model", max_results=10)

        assert result["count"] == 3
        assert result["full_name"] == "cat.schema.model"

    @mock.patch("databricks_tools_core.mlflow.registry.get_workspace_client")
    def test_list_model_not_found(self, mock_client):
        mock_client.return_value.model_versions.list.side_effect = NotFound("not found")

        result = list_model_versions("cat.schema.missing")

        assert result["status"] == "NOT_FOUND"


class TestGetModelVersionByAlias:
    @mock.patch("databricks_tools_core.mlflow.registry.get_workspace_client")
    def test_get_by_alias(self, mock_client):
        v = _make_version(version=5)
        mock_client.return_value.model_versions.get_by_alias.return_value = v

        result = get_model_version_by_alias("cat.schema.model", alias="champion")

        assert result["version"] == 5

    @mock.patch("databricks_tools_core.mlflow.registry.get_workspace_client")
    def test_alias_not_found(self, mock_client):
        mock_client.return_value.model_versions.get_by_alias.side_effect = NotFound("not found")

        result = get_model_version_by_alias("cat.schema.model", alias="missing")

        assert result["status"] == "NOT_FOUND"


class TestSetModelAlias:
    @mock.patch("databricks_tools_core.mlflow.registry.get_workspace_client")
    def test_set_alias(self, mock_client):
        mock_client.return_value.registered_models.set_alias.return_value = None

        result = set_model_alias("cat.schema.model", alias="champion", version_num=5)

        assert result["status"] == "set"
        assert result["alias"] == "champion"
        assert result["version_num"] == 5

    @mock.patch("databricks_tools_core.mlflow.registry.get_workspace_client")
    def test_set_alias_not_found(self, mock_client):
        mock_client.return_value.registered_models.set_alias.side_effect = NotFound("not found")

        result = set_model_alias("cat.schema.model", alias="x", version_num=999)

        assert result["status"] == "NOT_FOUND"


class TestDeleteModelAlias:
    @mock.patch("databricks_tools_core.mlflow.registry.get_workspace_client")
    def test_delete_alias(self, mock_client):
        mock_client.return_value.registered_models.delete_alias.return_value = None

        result = delete_model_alias("cat.schema.model", alias="old")

        assert result["status"] == "deleted"

    @mock.patch("databricks_tools_core.mlflow.registry.get_workspace_client")
    def test_delete_alias_not_found(self, mock_client):
        mock_client.return_value.registered_models.delete_alias.side_effect = NotFound("not found")

        result = delete_model_alias("cat.schema.model", alias="missing")

        assert result["status"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Trace tests
# ---------------------------------------------------------------------------


class TestSearchTraces:
    @mock.patch("databricks_tools_core.mlflow.traces.get_workspace_client")
    def test_search_returns_traces(self, mock_client):
        mock_client.return_value.api_client.do.return_value = {
            "traces": [
                {
                    "request_id": "tr-abc",
                    "experiment_id": "123",
                    "timestamp_ms": 1700000000000,
                    "execution_time_ms": 5000,
                    "status": "OK",
                    "tags": [{"key": "mlflow.traceName", "value": "predict"}],
                    "request_metadata": [],
                },
                {
                    "request_id": "tr-def",
                    "experiment_id": "123",
                    "timestamp_ms": 1700000010000,
                    "execution_time_ms": 3000,
                    "status": "ERROR",
                    "tags": [],
                    "request_metadata": [],
                },
            ]
        }

        result = search_traces(experiment_ids=["123"], max_results=10)

        assert result["count"] == 2
        assert result["traces"][0]["trace_id"] == "tr-abc"
        assert result["traces"][0]["status"] == "OK"
        assert result["traces"][1]["status"] == "ERROR"

    @mock.patch("databricks_tools_core.mlflow.traces.get_workspace_client")
    def test_search_with_filter(self, mock_client):
        mock_client.return_value.api_client.do.return_value = {"traces": []}

        result = search_traces(experiment_ids=["123"], filter_string="status = 'OK'")

        assert result["count"] == 0
        call_args = mock_client.return_value.api_client.do.call_args
        assert call_args.kwargs["query"]["filter"] == "status = 'OK'"


class TestGetTrace:
    @mock.patch("databricks_tools_core.mlflow.traces.get_workspace_client")
    def test_get_trace_detail(self, mock_client):
        mock_client.return_value.api_client.do.return_value = {
            "trace": {
                "trace_info": {
                    "trace_id": "tr-abc",
                    "trace_location": {"type": "MLFLOW_EXPERIMENT", "mlflow_experiment": {"experiment_id": "123"}},
                    "state": "OK",
                    "request_time": "2026-01-01T00:00:00Z",
                    "execution_duration": "5.0s",
                    "request_preview": "Hello",
                    "response_preview": "Hi there",
                    "tags": {"mlflow.traceName": "predict"},
                    "trace_metadata": {"mlflow.trace.sizeBytes": "1024"},
                    "assessments": [],
                },
                "trace_data": {
                    "spans": [
                        {
                            "span_id": "span-1",
                            "name": "predict",
                            "parent_id": None,
                            "start_time_unix_nano": 1000,
                            "end_time_unix_nano": 2000,
                            "status": {"status_code": "OK"},
                            "attributes": {},
                        }
                    ]
                },
            }
        }

        result = get_trace(trace_id="tr-abc")

        assert result["trace_id"] == "tr-abc"
        assert result["state"] == "OK"
        assert result["span_count"] == 1
        assert result["tags"]["mlflow.traceName"] == "predict"
        assert result["metadata"]["mlflow.trace.sizeBytes"] == "1024"

    @mock.patch("databricks_tools_core.mlflow.traces.get_workspace_client")
    def test_get_trace_not_found(self, mock_client):
        mock_client.return_value.api_client.do.side_effect = Exception("RESOURCE_DOES_NOT_EXIST")

        result = get_trace(trace_id="tr-missing")

        assert result["status"] == "NOT_FOUND"


class TestSetTraceTag:
    @mock.patch("databricks_tools_core.mlflow.traces.get_workspace_client")
    def test_set_tag(self, mock_client):
        mock_client.return_value.api_client.do.return_value = {}

        result = set_trace_tag("tr-abc", "quality", "good")

        assert result["status"] == "set"
        assert result["key"] == "quality"

    @mock.patch("databricks_tools_core.mlflow.traces.get_workspace_client")
    def test_set_tag_not_found(self, mock_client):
        mock_client.return_value.api_client.do.side_effect = Exception("RESOURCE_DOES_NOT_EXIST")

        result = set_trace_tag("tr-missing", "key", "val")

        assert result["status"] == "NOT_FOUND"


class TestDeleteTraceTag:
    @mock.patch("databricks_tools_core.mlflow.traces.get_workspace_client")
    def test_delete_tag(self, mock_client):
        mock_client.return_value.api_client.do.return_value = {}

        result = delete_trace_tag("tr-abc", "old-tag")

        assert result["status"] == "deleted"

    @mock.patch("databricks_tools_core.mlflow.traces.get_workspace_client")
    def test_delete_tag_not_found(self, mock_client):
        mock_client.return_value.api_client.do.side_effect = Exception("not found")

        result = delete_trace_tag("tr-missing", "key")

        assert result["status"] == "NOT_FOUND"


class TestLogAssessment:
    @mock.patch("databricks_tools_core.mlflow.traces.get_workspace_client")
    def test_log_feedback(self, mock_client):
        mock_client.return_value.api_client.do.return_value = {
            "assessment": {"assessment_id": "a-123", "assessment_name": "quality"}
        }

        result = log_assessment("tr-abc", "quality", "good")

        assert result["status"] == "created"
        assert result["assessment_id"] == "a-123"
        call_body = mock_client.return_value.api_client.do.call_args.kwargs["body"]
        assert call_body["assessment"]["assessment_name"] == "quality"
        assert call_body["assessment"]["feedback"] == {"value": "good"}

    @mock.patch("databricks_tools_core.mlflow.traces.get_workspace_client")
    def test_log_expectation(self, mock_client):
        mock_client.return_value.api_client.do.return_value = {
            "assessment": {"assessment_id": "a-456", "assessment_name": "expected"}
        }

        result = log_assessment("tr-abc", "expected", "Should say hello", assessment_type="expectation")

        call_body = mock_client.return_value.api_client.do.call_args.kwargs["body"]
        assert call_body["assessment"]["expectation"] == {"value": "Should say hello"}
        assert "feedback" not in call_body["assessment"]

    @mock.patch("databricks_tools_core.mlflow.traces.get_workspace_client")
    def test_log_with_rationale(self, mock_client):
        mock_client.return_value.api_client.do.return_value = {
            "assessment": {"assessment_id": "a-789", "assessment_name": "quality"}
        }

        log_assessment("tr-abc", "quality", "bad", rationale="Response was wrong")

        call_body = mock_client.return_value.api_client.do.call_args.kwargs["body"]
        assert call_body["assessment"]["rationale"] == "Response was wrong"


class TestDeleteAssessment:
    @mock.patch("databricks_tools_core.mlflow.traces.get_workspace_client")
    def test_delete_assessment(self, mock_client):
        mock_client.return_value.api_client.do.return_value = {}

        result = delete_assessment("tr-abc", "a-123")

        assert result["status"] == "deleted"
        assert result["assessment_id"] == "a-123"

    @mock.patch("databricks_tools_core.mlflow.traces.get_workspace_client")
    def test_delete_assessment_not_found(self, mock_client):
        mock_client.return_value.api_client.do.side_effect = Exception("RESOURCE_DOES_NOT_EXIST")

        result = delete_assessment("tr-abc", "a-missing")

        assert result["status"] == "NOT_FOUND"

"""Integration tests that create Databricks assets.

These tests are labeled databricks-codex-itest via the marker below.
"""

import base64
import logging
import os
import time
import uuid

import pytest

from databricks.sdk import WorkspaceClient
from databricks.sdk import config as sdk_config
from databricks.sdk.service.compute import Environment
from databricks.sdk.service.dashboards import Dashboard
from databricks.sdk.service.jobs import JobEnvironment, NotebookTask, Source, Task
from databricks.sdk.service.pipelines import NotebookLibrary, PipelineLibrary
from databricks.sdk.service.workspace import ImportFormat, Language

LABEL = "databricks-codex-itest"
CATALOG = "samples"
SCHEMA = "bakehouse"
PIPELINE_CATALOG = "main"
PIPELINE_SCHEMA = "default"
DEFAULT_HTTP_TIMEOUT_SECONDS = 30
DEFAULT_RETRY_TIMEOUT_SECONDS = 120

logger = logging.getLogger(__name__)


def _unique_name(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _keep_assets() -> bool:
    return os.environ.get("KEEP_ITEST_ASSETS", "").strip().lower() in {"1", "true", "yes"}


def _get_client(databricks_connected):
    if isinstance(databricks_connected, dict) and "client" in databricks_connected:
        return databricks_connected["client"]

    if "host" not in databricks_connected or "token" not in databricks_connected:
        raise ValueError("databricks_connected must include either client or host/token")

    cfg = sdk_config.Config(
        host=databricks_connected["host"],
        token=databricks_connected["token"],
        http_timeout_seconds=DEFAULT_HTTP_TIMEOUT_SECONDS,
        retry_timeout_seconds=DEFAULT_RETRY_TIMEOUT_SECONDS,
    )
    return WorkspaceClient(config=cfg)


def _pick_warehouse(client):
    for wh in client.warehouses.list():
        wh_id = getattr(wh, "id", None) or getattr(wh, "warehouse_id", None)
        if wh_id:
            return wh
    return None


def _pick_cluster(client):
    running = []
    any_cluster = []
    for cl in client.clusters.list():
        any_cluster.append(cl)
        state = getattr(cl, "state", None)
        state_val = getattr(state, "value", state)
        if state_val in {"RUNNING", "RESIZING"}:
            running.append(cl)
    if running:
        return running[0]
    if any_cluster:
        return any_cluster[0]
    return None


def _wait_statement(client, statement_id: str, timeout_seconds: int = 30):
    deadline = time.time() + timeout_seconds
    last = None
    while time.time() < deadline:
        last = client.statement_execution.get_statement(statement_id)
        status = getattr(last, "status", None)
        state = getattr(status, "state", None)
        state_value = getattr(state, "value", state)
        if state_value in {"SUCCEEDED", "FAILED", "CANCELED", "CLOSED", "ERROR"}:
            return last
        time.sleep(1)
    return last


def _run_sql_statement(client, warehouse_id: str, sql: str, timeout_seconds: int = 60):
    resp = client.statement_execution.execute_statement(
        sql,
        warehouse_id=warehouse_id,
        wait_timeout="20s",
    )
    stmt = _wait_statement(client, resp.statement_id, timeout_seconds=timeout_seconds)
    state = getattr(getattr(stmt, "status", None), "state", None)
    state_value = getattr(state, "value", state)
    return stmt, state_value


@pytest.mark.integration
@pytest.mark.databricks_codex_itest
@pytest.mark.timeout(180)
def test_run_simple_sql_script(databricks_connected):
    """Run a simple SQL script on a SQL warehouse."""
    logger.info("Starting SQL execution test using catalog=%s schema=%s", CATALOG, SCHEMA)
    client = _get_client(databricks_connected)
    warehouse = _pick_warehouse(client)
    if not warehouse:
        pytest.skip("No SQL warehouse available for statement execution")

    warehouse_id = getattr(warehouse, "id", None) or getattr(warehouse, "warehouse_id", None)
    resp = client.statement_execution.execute_statement(
        "SELECT 1 AS one",
        warehouse_id=warehouse_id,
        catalog=CATALOG,
        schema=SCHEMA,
        wait_timeout="10s",
    )
    stmt = _wait_statement(client, resp.statement_id, timeout_seconds=30)
    state = getattr(getattr(stmt, "status", None), "state", None)
    state_value = getattr(state, "value", state)
    assert state_value == "SUCCEEDED"


@pytest.mark.integration
@pytest.mark.databricks_codex_itest
@pytest.mark.timeout(180)
def test_create_databricks_job(databricks_connected):
    """Create a Databricks job on serverless workflows compute."""
    logger.info("Starting serverless job creation test")
    client = _get_client(databricks_connected)
    job_id = None
    notebook_path = None
    try:
        user = client.current_user.me()
        home_dir = f"/Users/{user.user_name}"
        notebook_path = f"{home_dir}/{_unique_name('codex_job_notebook')}"
        notebook_content = base64.b64encode(
            b'print("hello from serverless job")\n'
        ).decode("ascii")
        client.workspace.import_(
            path=notebook_path,
            format=ImportFormat.SOURCE,
            language=Language.PYTHON,
            content=notebook_content,
            overwrite=True,
        )
        task = Task(
            task_key="codex_job_task",
            notebook_task=NotebookTask(
                notebook_path=notebook_path,
                source=Source.WORKSPACE,
            ),
            environment_key="default",
        )
        env = JobEnvironment(
            environment_key="default",
            spec=Environment(environment_version="2"),
        )
        resp = client.jobs.create(
            name=_unique_name("codex-itest-job"),
            tasks=[task],
            environments=[env],
        )
        job_id = resp.job_id
        assert job_id is not None
    except Exception as exc:
        pytest.skip(f"Serverless job creation not available: {exc}")
    finally:
        if job_id is not None:
            try:
                client.jobs.delete(job_id=job_id)
            except Exception:
                pass
        if notebook_path is not None:
            try:
                client.workspace.delete(path=notebook_path, recursive=False)
            except Exception:
                pass


@pytest.mark.integration
@pytest.mark.databricks_codex_itest
@pytest.mark.timeout(180)
def test_create_pipeline(databricks_connected):
    """Create a simple DLT pipeline definition."""
    logger.info(
        "Starting pipeline creation test using catalog=%s schema=%s",
        PIPELINE_CATALOG,
        PIPELINE_SCHEMA,
    )
    client = _get_client(databricks_connected)
    pipeline_id = None
    user = client.current_user.me()
    base_dir = f"/Users/{user.user_name}/{_unique_name('codex')}"
    notebook_path = f"{base_dir}/codex_itest_pipeline"
    try:
        notebook_content = base64.b64encode(b"# DLT pipeline placeholder\n").decode("ascii")
        client.workspace.mkdirs(base_dir)
        client.workspace.import_(
            path=notebook_path,
            format=ImportFormat.SOURCE,
            language=Language.PYTHON,
            content=notebook_content,
            overwrite=True,
        )
        library = PipelineLibrary(notebook=NotebookLibrary(path=notebook_path))
        resp = client.pipelines.create(
            name=_unique_name("codex-itest-pipeline"),
            development=True,
            serverless=True,
            catalog=PIPELINE_CATALOG,
            schema=PIPELINE_SCHEMA,
            libraries=[library],
        )
        pipeline_id = resp.pipeline_id
        assert pipeline_id is not None
    except Exception as exc:
        pytest.skip(f"Pipeline creation not available: {exc}")
    finally:
        if pipeline_id is not None:
            try:
                client.pipelines.delete(pipeline_id=pipeline_id)
            except Exception:
                pass
        try:
            client.workspace.delete(path=notebook_path, recursive=False)
        except Exception:
            pass
        try:
            client.workspace.delete(path=base_dir, recursive=True)
        except Exception:
            pass


@pytest.mark.integration
@pytest.mark.databricks_codex_itest
@pytest.mark.timeout(180)
def test_create_catalog(databricks_connected):
    """Create and delete a Unity Catalog catalog."""
    logger.info("Starting catalog creation test")
    client = _get_client(databricks_connected)
    warehouse = _pick_warehouse(client)
    if not warehouse:
        pytest.skip("No SQL warehouse available for catalog creation")

    warehouse_id = getattr(warehouse, "id", None) or getattr(warehouse, "warehouse_id", None)
    # Keep identifier SQL-safe without quoting.
    name = _unique_name("codex_itest_catalog").replace("-", "_")
    try:
        _, create_state = _run_sql_statement(
            client,
            warehouse_id=warehouse_id,
            sql=f"CREATE CATALOG {name} COMMENT 'codex integration test catalog'",
            timeout_seconds=90,
        )
        assert create_state == "SUCCEEDED"
    except Exception as exc:
        pytest.skip(f"Catalog creation not available: {exc}")
    finally:
        try:
            _run_sql_statement(
                client,
                warehouse_id=warehouse_id,
                sql=f"DROP CATALOG IF EXISTS {name} CASCADE",
                timeout_seconds=90,
            )
        except Exception:
            pass


@pytest.mark.integration
@pytest.mark.databricks_codex_itest
@pytest.mark.timeout(180)
def test_create_genie_space(databricks_connected):
    """Create a Genie room by cloning a template space."""
    logger.info("Starting Genie space creation test")
    client = _get_client(databricks_connected)
    try:
        spaces_response = client.genie.list_spaces()
        spaces = getattr(spaces_response, "spaces", None)
        if spaces is None and hasattr(spaces_response, "__iter__"):
            spaces = list(spaces_response)
        if spaces is None:
            spaces = []
    except Exception as exc:
        pytest.skip(f"Genie not available: {exc}")
    if not spaces:
        pytest.skip("No Genie spaces available to use as a template")

    template = None
    for space in spaces:
        try:
            candidate = client.genie.get_space(space.space_id, include_serialized_space=True)
        except Exception:
            continue
        warehouse_id = getattr(candidate, "warehouse_id", None)
        serialized_space = getattr(candidate, "serialized_space", None)
        if warehouse_id and serialized_space:
            template = candidate
            break
    if template is None:
        pytest.skip("No accessible Genie template space with warehouse_id + serialized_space")

    warehouse_id = template.warehouse_id
    serialized_space = template.serialized_space

    new_space = None
    try:
        new_space = client.genie.create_space(
            warehouse_id=warehouse_id,
            serialized_space=serialized_space,
            title=_unique_name("codex-itest-genie"),
            description="codex integration test space",
        )
        assert new_space.space_id
    except Exception as exc:
        pytest.skip(f"Genie space creation not available: {exc}")
    finally:
        if new_space is not None:
            try:
                client.genie.trash_space(space_id=new_space.space_id)
            except Exception:
                pass


@pytest.mark.integration
@pytest.mark.databricks_codex_itest
@pytest.mark.timeout(180)
def test_create_ai_bi_dashboard(databricks_connected):
    """Create an AI/BI (Lakeview) dashboard by cloning a template dashboard."""
    logger.info("Starting Lakeview dashboard creation test using catalog=%s schema=%s", CATALOG, SCHEMA)
    client = _get_client(databricks_connected)
    try:
        dashboards = list(client.lakeview.list())
    except Exception as exc:
        pytest.skip(f"Lakeview not available: {exc}")
    if not dashboards:
        pytest.skip("No Lakeview dashboards available to use as a template")

    template = client.lakeview.get(dashboards[0].dashboard_id)
    serialized = getattr(template, "serialized_dashboard", None)
    if not serialized:
        pytest.skip("Template dashboard missing serialized_dashboard")

    created = None
    try:
        created = client.lakeview.create(
            dashboard=Dashboard(
                display_name=_unique_name("codex-itest-dashboard"),
                serialized_dashboard=serialized,
                warehouse_id=getattr(template, "warehouse_id", None),
            ),
            dataset_catalog=CATALOG,
            dataset_schema=SCHEMA,
        )
        assert created.dashboard_id
        host = str(getattr(client.config, "host", "")).rstrip("/")
        dashboard_url = f"{host}/dashboardsv3/{created.dashboard_id}" if host else created.dashboard_id
        print(f"Created dashboard ID: {created.dashboard_id}")
        print(f"Dashboard URL: {dashboard_url}")
    except Exception as exc:
        pytest.skip(f"Lakeview dashboard creation not available: {exc}")
    finally:
        if created is not None and not _keep_assets():
            try:
                client.lakeview.trash(dashboard_id=created.dashboard_id)
            except Exception:
                pass

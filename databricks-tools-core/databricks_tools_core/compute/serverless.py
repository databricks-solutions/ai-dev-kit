"""
Compute - Serverless Code Execution

Execute Python or SQL code on Databricks serverless compute via the Jobs API
(runs/submit). No interactive cluster required.

Usage:
    from databricks_tools_core.compute.serverless import run_code_on_serverless

    result = run_code_on_serverless("print('hello')", language="python")
    result = run_code_on_serverless("SELECT 1", language="sql")
"""

import base64
import datetime
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Dict, Any, Optional

from databricks.sdk.service.compute import Environment
from databricks.sdk.service.jobs import (
    JobEnvironment,
    NotebookTask,
    RunResultState,
    SubmitTask,
)
from databricks.sdk.service.workspace import ImportFormat, Language

from ..auth import get_workspace_client, get_current_username

logger = logging.getLogger(__name__)

# Language string to workspace Language enum
_LANGUAGE_MAP = {
    "python": Language.PYTHON,
    "sql": Language.SQL,
}


@dataclass
class ServerlessRunResult:
    """Result from serverless code execution via Jobs API.

    Attributes:
        success: Whether the execution completed successfully.
        output: The output from the execution (notebook result or logs).
        error: Error message if execution failed.
        run_id: Databricks Jobs run ID.
        run_url: URL to the run in the Databricks UI.
        duration_seconds: Wall-clock duration of the execution.
        state: Final state string (SUCCESS, FAILED, TIMEDOUT, CANCELED, etc.).
        message: Human-readable summary of the result.
    """

    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    run_id: Optional[int] = None
    run_url: Optional[str] = None
    duration_seconds: Optional[float] = None
    state: Optional[str] = None
    message: Optional[str] = None
    workspace_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        d = {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "run_id": self.run_id,
            "run_url": self.run_url,
            "duration_seconds": self.duration_seconds,
            "state": self.state,
            "message": self.message,
        }
        if self.workspace_path:
            d["workspace_path"] = self.workspace_path
        return d


def _get_temp_notebook_path(run_label: str) -> str:
    """Build a workspace path for a temporary serverless notebook.

    Args:
        run_label: Unique label for this run.

    Returns:
        Workspace path string under the current user's home directory.
    """
    username = get_current_username()
    base = f"/Workspace/Users/{username}" if username else "/Workspace"
    return f"{base}/.ai_dev_kit_tmp/{run_label}"


def _is_ipynb(content: str) -> bool:
    """Check if content is a Jupyter notebook (.ipynb) JSON structure."""
    try:
        data = json.loads(content)
        return isinstance(data, dict) and "cells" in data
    except (json.JSONDecodeError, ValueError):
        return False


def _upload_temp_notebook(
    code: str, language: str, workspace_path: str, is_jupyter: bool = False
) -> None:
    """Upload code as a temporary notebook to the Databricks workspace.

    Args:
        code: Source code or .ipynb JSON content to upload.
        language: Language string ("python" or "sql"). Ignored for Jupyter uploads.
        workspace_path: Target workspace path (without file extension).
        is_jupyter: If True, upload as Jupyter format (ImportFormat.JUPYTER).

    Raises:
        Exception: If the upload fails.
    """
    w = get_workspace_client()
    content_b64 = base64.b64encode(code.encode("utf-8")).decode("utf-8")

    # Ensure parent directory exists
    parent = workspace_path.rsplit("/", 1)[0]
    try:
        w.workspace.mkdirs(parent)
    except Exception:
        pass  # Directory may already exist

    if is_jupyter:
        w.workspace.import_(
            path=workspace_path,
            content=content_b64,
            format=ImportFormat.JUPYTER,
            overwrite=True,
        )
    else:
        lang_enum = _LANGUAGE_MAP[language]
        w.workspace.import_(
            path=workspace_path,
            content=content_b64,
            language=lang_enum,
            format=ImportFormat.SOURCE,
            overwrite=True,
        )


def _cleanup_temp_notebook(workspace_path: str) -> None:
    """Delete a temporary notebook from the workspace (best-effort)."""
    try:
        w = get_workspace_client()
        w.workspace.delete(path=workspace_path, recursive=False)
    except Exception as e:
        logger.debug(f"Cleanup of {workspace_path} failed (non-fatal): {e}")


def _get_run_output(task_run_id: int) -> Dict[str, Optional[str]]:
    """Retrieve output and error text from a completed task run.

    Args:
        task_run_id: The run ID of the specific task (not the parent run).

    Returns:
        Dict with ``output`` and ``error`` keys (both may be None).
    """
    w = get_workspace_client()
    result: Dict[str, Optional[str]] = {"output": None, "error": None}

    try:
        run_output = w.jobs.get_run_output(run_id=task_run_id)

        # Notebook output (from dbutils.notebook.exit() or last cell)
        if run_output.notebook_output and run_output.notebook_output.result:
            result["output"] = run_output.notebook_output.result

        # Logs (stdout/stderr, typically for spark_python_task)
        if run_output.logs:
            if result["output"]:
                result["output"] += f"\n\n--- Logs ---\n{run_output.logs}"
            else:
                result["output"] = run_output.logs

        # Error details
        if run_output.error:
            error_parts = [run_output.error]
            if run_output.error_trace:
                error_parts.append(run_output.error_trace)
            result["error"] = "\n\n".join(error_parts)

    except Exception as e:
        logger.debug(f"Failed to get output for task run {task_run_id}: {e}")
        result["error"] = str(e)

    return result


def run_code_on_serverless(
    code: str,
    language: str = "python",
    timeout: int = 1800,
    run_name: Optional[str] = None,
    cleanup: bool = True,
    workspace_path: Optional[str] = None,
) -> ServerlessRunResult:
    """Execute code on serverless compute via Jobs API runs/submit.

    Uploads the code as a notebook, submits it as a one-time run on serverless
    compute (no cluster required), waits for completion, and retrieves output.

    Two modes:
    - **Ephemeral** (default): Uploads to a temp path and cleans up after.
    - **Persistent**: If ``workspace_path`` is provided, uploads to that path
      and keeps it after execution. Useful for project notebooks (model training,
      ETL) the user wants saved in their workspace.

    Jupyter notebooks (.ipynb) are also supported. If the code content is
    detected as .ipynb JSON (contains "cells" key), it is uploaded using
    Databricks' native Jupyter import (ImportFormat.JUPYTER). The language
    parameter is ignored in this case since the notebook carries its own
    kernel metadata.

    SQL is supported but SELECT query results are NOT captured in the output.
    SQL via this tool is only useful for DDL/DML (CREATE TABLE, INSERT, MERGE).
    For SQL that needs result rows, use execute_sql() instead.

    Args:
        code: Code to execute, or raw .ipynb JSON content (auto-detected).
        language: Programming language ("python" or "sql"). Ignored for .ipynb.
        timeout: Maximum wait time in seconds (default: 1800 = 30 minutes).
        run_name: Optional human-readable run name. Auto-generated if omitted.
        cleanup: Delete the notebook after execution (default: True).
            Ignored when ``workspace_path`` is provided (persistent mode never cleans up).
        workspace_path: Optional workspace path to save the notebook to
            (e.g. "/Workspace/Users/user@company.com/my-project/train").
            If provided, the notebook is persisted at this path. If omitted,
            a temporary path is used and cleaned up after execution.

    Returns:
        ServerlessRunResult with output, error, run_id, run_url, and timing info.
    """
    if not code or not code.strip():
        return ServerlessRunResult(
            success=False,
            error="Code cannot be empty.",
            state="INVALID_INPUT",
            message="No code provided to execute.",
        )

    # Auto-detect .ipynb content
    is_jupyter = _is_ipynb(code)

    language = language.lower()
    if not is_jupyter and language not in _LANGUAGE_MAP:
        return ServerlessRunResult(
            success=False,
            error=f"Unsupported language: {language!r}. Must be 'python' or 'sql'.",
            state="INVALID_INPUT",
            message=f"Unsupported language {language!r}. Use 'python' or 'sql'.",
        )

    unique_id = uuid.uuid4().hex[:12]
    if not run_name:
        run_name = f"ai_dev_kit_serverless_{unique_id}"

    # Persistent mode: user-specified path, never cleanup
    if workspace_path:
        notebook_path = workspace_path
        cleanup = False
    else:
        notebook_path = _get_temp_notebook_path(f"serverless_{unique_id}")

    start_time = time.time()
    w = get_workspace_client()

    # --- Step 1: Upload code as a notebook ---
    try:
        _upload_temp_notebook(code, language, notebook_path, is_jupyter=is_jupyter)
    except Exception as e:
        return ServerlessRunResult(
            success=False,
            error=f"Failed to upload code to workspace: {e}",
            state="UPLOAD_FAILED",
            message=f"Could not upload temporary notebook: {e}",
        )

    run_id = None
    run_url = None

    try:
        # --- Step 2: Submit serverless run ---
        try:
            wait = w.jobs.submit(
                run_name=run_name,
                tasks=[
                    SubmitTask(
                        task_key="main",
                        notebook_task=NotebookTask(notebook_path=notebook_path),
                        environment_key="Default",
                    )
                ],
                environments=[
                    JobEnvironment(
                        environment_key="Default",
                        spec=Environment(client="1"),
                    )
                ],
            )
            # Extract run_id from the Wait object
            run_id = getattr(wait, "run_id", None)
            if run_id is None and hasattr(wait, "response"):
                run_id = getattr(wait.response, "run_id", None)

            # Get the canonical run URL immediately via get_run so the user
            # can monitor progress even before the run completes.
            if run_id:
                try:
                    initial_run = w.jobs.get_run(run_id=run_id)
                    run_url = initial_run.run_page_url
                except Exception:
                    pass  # Fall back to no URL rather than a guessed one

        except Exception as e:
            return ServerlessRunResult(
                success=False,
                error=f"Failed to submit serverless run: {e}",
                state="SUBMIT_FAILED",
                message=f"Jobs API runs/submit call failed: {e}",
            )

        # --- Step 3: Wait for completion ---
        try:
            run = wait.result(timeout=datetime.timedelta(seconds=timeout))
        except TimeoutError:
            elapsed = time.time() - start_time
            return ServerlessRunResult(
                success=False,
                error=f"Run timed out after {timeout}s.",
                run_id=run_id,
                run_url=run_url,
                duration_seconds=round(elapsed, 2),
                state="TIMEDOUT",
                message=(f"Serverless run {run_id} did not complete within {timeout}s. Check status at {run_url}"),
            )
        except Exception as e:
            elapsed = time.time() - start_time
            error_text = str(e)

            # Best-effort: retrieve the actual error traceback from run output
            if run_id:
                try:
                    failed_run = w.jobs.get_run(run_id=run_id)
                    if failed_run.tasks:
                        task_run_id = failed_run.tasks[0].run_id
                        output_data = _get_run_output(task_run_id)
                        if output_data.get("error"):
                            error_text = output_data["error"]
                except Exception:
                    pass  # Fall back to the original exception message

            return ServerlessRunResult(
                success=False,
                error=error_text,
                run_id=run_id,
                run_url=run_url,
                duration_seconds=round(elapsed, 2),
                state="FAILED",
                message=f"Run {run_id} failed: {e}",
            )

        elapsed = time.time() - start_time

        # --- Step 4: Determine result state ---
        result_state = None
        state_message = None
        if run.state:
            result_state = run.state.result_state
            state_message = run.state.state_message

        # Prefer the canonical URL from the Run object
        if run.run_page_url:
            run_url = run.run_page_url

        is_success = result_state == RunResultState.SUCCESS
        state_str = result_state.value if result_state else "UNKNOWN"

        # --- Step 5: Retrieve output ---
        task_run_id = None
        if run.tasks:
            task_run_id = run.tasks[0].run_id

        output_text = None
        error_text = None

        if task_run_id:
            output_data = _get_run_output(task_run_id)
            output_text = output_data["output"]
            error_text = output_data["error"]

        # Fallback error from state message
        if not is_success and not error_text:
            error_text = state_message or f"Run ended with state: {state_str}"

        if is_success:
            if not output_text:
                output_text = "Success (no output)"
            message = f"Code executed successfully on serverless compute in {round(elapsed, 1)}s."
        else:
            message = f"Serverless run failed with state {state_str}. Check {run_url} for details."

        return ServerlessRunResult(
            success=is_success,
            output=output_text if is_success else None,
            error=error_text if not is_success else None,
            run_id=run_id,
            run_url=run_url,
            duration_seconds=round(elapsed, 2),
            state=state_str,
            message=message,
            workspace_path=notebook_path if workspace_path else None,
        )

    finally:
        # --- Step 6: Cleanup temporary notebook ---
        if cleanup:
            _cleanup_temp_notebook(notebook_path)

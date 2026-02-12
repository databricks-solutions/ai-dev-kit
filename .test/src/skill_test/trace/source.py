"""Trace source detection and retrieval.

Provides hybrid trace source selection:
1. MLflow (preferred when configured via `mlflow autolog claude`)
2. Local fallback (~/.claude/projects/{hash}/*.jsonl)
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from .models import TraceMetrics
from .parser import parse_and_compute_metrics


@dataclass
class AutologStatus:
    """MLflow autolog configuration status."""

    enabled: bool
    tracking_uri: Optional[str] = None
    experiment_name: Optional[str] = None
    experiment_id: Optional[str] = None
    error: Optional[str] = None


def check_autolog_status(directory: str = ".") -> AutologStatus:
    """Check if mlflow autolog claude is configured.

    Args:
        directory: Directory to check (default: current)

    Returns:
        AutologStatus with configuration details
    """
    try:
        result = subprocess.run(
            ["mlflow", "autolog", "claude", "--status"],
            capture_output=True,
            text=True,
            cwd=directory,
            timeout=10,
        )

        if result.returncode == 0:
            output = result.stdout
            # Parse status output for tracking URI and experiment
            # Example: "Tracing enabled: tracking_uri=databricks, experiment=..."
            if "enabled" in output.lower() or "tracking_uri" in output.lower():
                # Extract tracking URI if present
                tracking_uri = None
                experiment_name = None
                for line in output.split("\n"):
                    line_lower = line.lower()
                    if "tracking_uri" in line_lower:
                        # Try to extract value after = or :
                        if "=" in line:
                            tracking_uri = line.split("=")[-1].strip()
                        elif ":" in line:
                            tracking_uri = line.split(":")[-1].strip()
                    if "experiment" in line_lower and "experiment_id" not in line_lower:
                        if "=" in line:
                            experiment_name = line.split("=")[-1].strip()
                        elif ":" in line:
                            experiment_name = line.split(":")[-1].strip()

                return AutologStatus(
                    enabled=True,
                    tracking_uri=tracking_uri,
                    experiment_name=experiment_name,
                )

        return AutologStatus(enabled=False)

    except FileNotFoundError:
        return AutologStatus(enabled=False, error="mlflow CLI not found")
    except subprocess.TimeoutExpired:
        return AutologStatus(enabled=False, error="mlflow command timed out")
    except Exception as e:
        return AutologStatus(enabled=False, error=str(e))


def get_current_session_trace_path() -> Optional[Path]:
    """Get the trace file path for the current Claude Code session.

    Claude Code stores session traces at:
    ~/.claude/projects/{project-hash}/{session-id}.jsonl

    Returns:
        Path to the current session's JSONL trace file, or None if not found
    """
    claude_projects = Path.home() / ".claude" / "projects"

    if not claude_projects.exists():
        return None

    # Find project directory for current working directory
    # Claude Code uses a hash of the path, formatted as: -Users-name-path-to-project
    cwd = Path.cwd()
    project_hash = str(cwd).replace("/", "-").replace("\\", "-")
    if project_hash.startswith("-"):
        project_hash = project_hash[1:]

    project_dir = claude_projects / project_hash

    if not project_dir.exists():
        # Try alternative: look for any project dir that might match
        # by checking if the cwd path appears in directory names
        for d in claude_projects.iterdir():
            if d.is_dir() and str(cwd).replace("/", "-").replace("\\", "-") in d.name:
                project_dir = d
                break
        else:
            return None

    # Find most recent JSONL file (current session)
    jsonl_files = sorted(
        project_dir.glob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if jsonl_files:
        return jsonl_files[0]

    return None


def get_trace_from_best_source(
    skill_name: str,
    session_id: Optional[str] = None,
    prefer_mlflow: bool = True,
) -> Tuple[TraceMetrics, str]:
    """Get trace from the best available source.

    Priority:
    1. If MLflow autolog is enabled and prefer_mlflow=True: query MLflow
    2. Otherwise: use local session trace

    Args:
        skill_name: Skill name (for experiment naming)
        session_id: Optional specific session ID to find
        prefer_mlflow: Whether to prefer MLflow over local (default: True)

    Returns:
        Tuple of (TraceMetrics, source_description)

    Raises:
        FileNotFoundError: If no trace found from any source
    """
    status = check_autolog_status()

    # Try MLflow first if enabled and preferred
    if status.enabled and prefer_mlflow:
        try:
            from .mlflow_integration import get_latest_trace_run, get_trace_from_mlflow

            experiment = status.experiment_name or f"/Shared/{skill_name}-skill-test-traces"

            run_id = get_latest_trace_run(experiment)
            if run_id:
                metrics = get_trace_from_mlflow(run_id)
                return metrics, f"mlflow:{run_id}"
        except Exception:
            # Fall through to local
            pass

    # Fall back to local trace
    trace_path = get_current_session_trace_path()
    if trace_path and trace_path.exists():
        metrics = parse_and_compute_metrics(trace_path)
        return metrics, f"local:{trace_path}"

    raise FileNotFoundError(
        "No trace found. Either configure MLflow autolog or ensure Claude Code session trace exists locally."
    )


def list_local_traces(limit: int = 10) -> dict:
    """List local Claude Code trace files.

    Args:
        limit: Maximum number of traces to return

    Returns:
        Dictionary with trace listing results
    """
    claude_projects = Path.home() / ".claude" / "projects"

    if not claude_projects.exists():
        return {"success": False, "error": "No local traces found", "traces": []}

    # Find current project directory
    cwd = Path.cwd()
    project_hash = str(cwd).replace("/", "-").replace("\\", "-")
    if project_hash.startswith("-"):
        project_hash = project_hash[1:]

    project_dir = claude_projects / project_hash

    if not project_dir.exists():
        # Try to find matching project dir
        for d in claude_projects.iterdir():
            if d.is_dir() and str(cwd).replace("/", "-").replace("\\", "-") in d.name:
                project_dir = d
                break
        else:
            return {
                "success": False,
                "error": f"No traces for project: {cwd}",
                "traces": [],
            }

    # List JSONL files sorted by modification time
    jsonl_files = sorted(
        project_dir.glob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit]

    traces = []
    for f in jsonl_files:
        stat = f.stat()
        traces.append(
            {
                "source": "local",
                "path": str(f),
                "session_id": f.stem,
                "modified": stat.st_mtime,
                "size_bytes": stat.st_size,
            }
        )

    return {
        "success": True,
        "source": "local",
        "project_dir": str(project_dir),
        "count": len(traces),
        "traces": traces,
    }


def get_setup_instructions(skill_name: str) -> str:
    """Get MLflow autolog setup instructions.

    Args:
        skill_name: Skill name for experiment naming

    Returns:
        Setup instructions string
    """
    experiment = f"/Shared/{skill_name}-skill-test-traces"
    return f"""
MLflow autolog is not configured. Traces will use local fallback.

To enable MLflow tracing:

1. Set Databricks authentication:
   export DATABRICKS_HOST="https://your-workspace.cloud.databricks.com"
   export DATABRICKS_TOKEN="your-personal-access-token"

2. Configure autolog in your project:
   mlflow autolog claude -u databricks -n "{experiment}"

3. Verify setup:
   mlflow autolog claude --status

Note: Local traces at ~/.claude/projects/.../*.jsonl will be used as fallback.
"""

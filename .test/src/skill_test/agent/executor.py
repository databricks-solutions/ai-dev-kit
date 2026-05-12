"""Claude Agent SDK executor for agent-based skill evaluation.

Wraps claude_agent_sdk.query() to run a real Claude Code instance with
a candidate SKILL.md injected as system prompt, captures streaming events,
and builds TraceMetrics from the session.

Usage:
    result = await run_agent(
        prompt="Create a metric view for order analytics",
        skill_md="# Metric Views\n...",
        mcp_config={"databricks": databricks_server},
    )
    print(result.response_text)
    print(result.trace_metrics.to_dict())
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..trace.models import FileOperation, ToolCall, TraceMetrics, TokenUsage

logger = logging.getLogger(__name__)

_mlflow_env_lock = threading.Lock()
_mlflow_env_configured = False

# Serialize process_transcript calls across parallel agents to avoid
# burst HTTP load on the MLflow tracking server when multiple agents
# finish concurrently (e.g. --parallel-agents 3).
# Lazy per-loop factory: asyncio.Semaphore binds to the running loop at
# creation time. When _run_in_fresh_loop creates a new loop the module-level
# semaphore would crash with "attached to a different loop". Instead we
# cache one semaphore per event-loop id.
_transcript_semaphores: dict[int, asyncio.Semaphore] = {}
_transcript_semaphore_lock = threading.Lock()


def _get_transcript_semaphore() -> asyncio.Semaphore:
    """Return a Semaphore(1) bound to the current running event loop."""
    loop_id = id(asyncio.get_running_loop())
    with _transcript_semaphore_lock:
        if loop_id not in _transcript_semaphores:
            _transcript_semaphores[loop_id] = asyncio.Semaphore(1)
        return _transcript_semaphores[loop_id]


@dataclass
class AgentEvent:
    """A captured event from the agent execution stream."""

    type: str  # tool_use, tool_result, text, result, system, error
    timestamp: datetime
    data: dict[str, Any]


@dataclass
class AgentResult:
    """Result of a single agent execution.

    Contains the final response text, trace metrics built from captured
    events, and the raw event stream for detailed analysis.
    """

    response_text: str
    trace_metrics: TraceMetrics
    events: list[AgentEvent] = field(default_factory=list)
    session_id: str | None = None
    duration_ms: int | None = None
    success: bool = True
    error: str | None = None


def _build_trace_metrics(
    events: list[AgentEvent],
    session_id: str,
) -> TraceMetrics:
    """Build TraceMetrics from captured agent events.

    Maps the SDK streaming events back to the same TraceMetrics model
    used by the JSONL transcript parser, enabling reuse of all existing
    trace scorers.
    """
    metrics = TraceMetrics(session_id=session_id)

    tool_calls_by_id: dict[str, ToolCall] = {}
    total_input = 0
    total_output = 0
    total_cache_creation = 0
    total_cache_read = 0
    num_turns = 0
    num_user_messages = 1  # The initial prompt counts as one

    for event in events:
        ts = event.timestamp

        if metrics.start_time is None:
            metrics.start_time = ts

        if event.type == "tool_use":
            tc = ToolCall(
                id=event.data.get("id", str(uuid.uuid4())),
                name=event.data.get("name", "unknown"),
                input=event.data.get("input", {}),
                timestamp=ts,
            )
            tool_calls_by_id[tc.id] = tc
            metrics.tool_calls.append(tc)

        elif event.type == "tool_result":
            tool_use_id = event.data.get("tool_use_id", "")
            result_text = event.data.get("content", "")
            is_error = event.data.get("is_error", False)

            if tool_use_id in tool_calls_by_id:
                tc = tool_calls_by_id[tool_use_id]
                tc.result = result_text[:2000] if isinstance(result_text, str) else str(result_text)[:2000]
                tc.success = not is_error

                # Extract file operations from tool results
                tool_name = tc.name
                tool_input = tc.input
                if tool_name == "Write" and tc.success:
                    fp = tool_input.get("file_path", "")
                    if fp:
                        metrics.files_created.append(fp)
                        metrics.file_operations.append(FileOperation(type="create", file_path=fp, timestamp=ts))
                elif tool_name == "Edit" and tc.success:
                    fp = tool_input.get("file_path", "")
                    if fp:
                        metrics.files_modified.append(fp)
                        metrics.file_operations.append(FileOperation(type="edit", file_path=fp, timestamp=ts))
                elif tool_name == "Read":
                    fp = tool_input.get("file_path", "")
                    if fp:
                        metrics.files_read.append(fp)
                        metrics.file_operations.append(FileOperation(type="read", file_path=fp, timestamp=ts))

        elif event.type == "assistant_turn":
            num_turns += 1
            usage = event.data.get("usage", {})
            if usage:
                total_input += usage.get("input_tokens", 0)
                total_output += usage.get("output_tokens", 0)
                total_cache_creation += usage.get("cache_creation_input_tokens", 0)
                total_cache_read += usage.get("cache_read_input_tokens", 0)

        elif event.type == "result":
            metrics.end_time = ts

    # If no explicit end time, use last event timestamp
    if metrics.end_time is None and events:
        metrics.end_time = events[-1].timestamp

    # Aggregate tool counts
    for tc in metrics.tool_calls:
        metrics.tool_counts[tc.name] = metrics.tool_counts.get(tc.name, 0) + 1
        cat = tc.tool_category
        metrics.tool_category_counts[cat] = metrics.tool_category_counts.get(cat, 0) + 1

    metrics.total_tool_calls = len(metrics.tool_calls)
    metrics.total_input_tokens = total_input
    metrics.total_output_tokens = total_output
    metrics.total_cache_creation_tokens = total_cache_creation
    metrics.total_cache_read_tokens = total_cache_read
    metrics.num_turns = num_turns
    metrics.num_user_messages = num_user_messages

    return metrics


def _find_repo_root() -> str:
    """Walk up from this file to find the repo root (contains .git)."""
    from pathlib import Path

    d = Path(__file__).resolve().parent
    for _ in range(10):
        if (d / ".git").exists():
            return str(d)
        d = d.parent
    return os.getcwd()


def _load_mcp_config() -> dict[str, Any]:
    """Load MCP server config from .mcp.json, resolving variable references."""
    import json
    from pathlib import Path

    repo_root = Path(_find_repo_root())
    mcp_json = repo_root / ".mcp.json"
    if not mcp_json.exists():
        return {}

    try:
        data = json.loads(mcp_json.read_text())
    except (json.JSONDecodeError, OSError):
        return {}

    servers = data.get("mcpServers", {})
    resolved: dict[str, Any] = {}
    for name, cfg in servers.items():
        resolved_cfg: dict[str, Any] = {}
        for key, val in cfg.items():
            if key == "defer_loading":
                continue  # Not relevant for agent SDK
            if isinstance(val, str):
                resolved_cfg[key] = val.replace("${CLAUDE_PLUGIN_ROOT}", str(repo_root))
            elif isinstance(val, list):
                resolved_cfg[key] = [
                    v.replace("${CLAUDE_PLUGIN_ROOT}", str(repo_root)) if isinstance(v, str) else v for v in val
                ]
            else:
                resolved_cfg[key] = val
        if resolved_cfg:
            resolved[name] = resolved_cfg
    return resolved


_ENV_PREFIXES = (
    "ANTHROPIC_",
    "CLAUDE_CODE_",
    "DATABRICKS_",
    "MLFLOW_",
)


def _resolve_env_refs(value: str) -> str:
    """Expand ${VAR} references in a settings value using os.environ.

    Supports ${VAR} and ${VAR:-default} syntax. Unresolved refs with no
    default are left as-is.
    """
    import re

    def _replacer(m: re.Match) -> str:
        var = m.group(1)
        if ":-" in var:
            name, default = var.split(":-", 1)
            return os.environ.get(name, default)
        return os.environ.get(var, m.group(0))

    return re.sub(r"\$\{([^}]+)\}", _replacer, value)


def _get_agent_env() -> dict[str, str]:
    """Build environment variables for the Claude agent subprocess.

    Loads Databricks FMAPI configuration from a settings file (same pattern
    as databricks-builder-app), with env var overrides on top.

    Settings file search order (relative to repo root):
        1. .test/claude_agent_settings.json
        2. .claude/agent_settings.json

    Expected format (same as builder app):
        {
            "env": {
                "ANTHROPIC_MODEL": "databricks-claude-opus-4-6",
                "ANTHROPIC_BASE_URL": "https://<host>/anthropic",
                "ANTHROPIC_AUTH_TOKEN": "${DATABRICKS_TOKEN}",
                "DATABRICKS_CONFIG_PROFILE": "e2-demo-field-eng",
                ...
            }
        }

    Values support ${VAR} and ${VAR:-default} interpolation from env vars.
    Environment variables with matching prefixes override settings file values.
    """
    import json
    from pathlib import Path

    env: dict[str, str] = {}

    # 1. Load from settings file (if exists)
    repo_root = Path(_find_repo_root())
    search_paths = [
        repo_root / ".test" / "claude_agent_settings.json",
        repo_root / ".claude" / "agent_settings.json",
    ]
    for p in search_paths:
        if p.exists():
            try:
                settings = json.loads(p.read_text())
                file_env = settings.get("env", {})
                for k, v in file_env.items():
                    if isinstance(v, str):
                        env[k] = _resolve_env_refs(v)
                logger.info("Loaded agent env from %s (%d vars)", p, len(file_env))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load %s: %s", p, e)
            break  # use first found

    # 2. Env vars with known prefixes override settings file values
    # Skip internal Claude Code vars that would confuse the subprocess
    _skip_keys = {
        "CLAUDE_CODE_SSE_PORT",
        "CLAUDE_CODE_ENTRYPOINT",
        "CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY",
    }
    for key, value in os.environ.items():
        if key in _skip_keys:
            continue
        if any(key.startswith(p) for p in _ENV_PREFIXES) and value:
            env[key] = value

    # Remove internal Claude Code vars that may have leaked from settings file
    for k in _skip_keys:
        env.pop(k, None)

    # 3. Ensure required defaults
    env.setdefault("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS", "1")
    env.setdefault("CLAUDE_CODE_STREAM_CLOSE_TIMEOUT", "600000")  # 10 min

    return env


def _get_mlflow_stop_hook(mlflow_experiment: str | None = None, skill_name: str | None = None):
    """Create an MLflow Stop hook that processes the transcript into a real trace.

    Mirrors the pattern from databricks-builder-app/server/services/agent.py:
    - MLflow tracking URI and experiment are set at hook CREATION time
    - The hook itself just calls setup_mlflow() then process_transcript()
    - No conditional gates — configure every time for reliability

    Returns hook_fn or None if MLflow is not available.
    """
    try:
        from mlflow.claude_code.tracing import process_transcript, setup_mlflow
        import mlflow
    except ImportError:
        logger.warning(
            "mlflow.claude_code.tracing not available — traces will not be logged. Ensure mlflow>=3.10.1 is installed."
        )
        return None

    # One-time environment and MLflow configuration (thread-safe).
    # All os.environ writes happen here, once, to avoid races in parallel runs.
    global _mlflow_env_configured
    with _mlflow_env_lock:
        if not _mlflow_env_configured:
            # Apply DATABRICKS_* and MLFLOW_* vars from agent settings to os.environ
            # so SkillTestConfig / MLflow can pick them up for auth.
            agent_env = _get_agent_env()
            for key, value in agent_env.items():
                if key.startswith(("DATABRICKS_", "MLFLOW_")):
                    os.environ[key] = value

            # Configure MLflow at hook creation time (matches builder app pattern).
            from ..config import SkillTestConfig

            agent_experiment = mlflow_experiment or os.environ.get(
                "SKILL_TEST_MLFLOW_EXPERIMENT",
                "/Shared/skill-tests",
            )
            os.environ["MLFLOW_EXPERIMENT_NAME"] = agent_experiment

            stc = SkillTestConfig()
            tracking_uri = stc.mlflow.tracking_uri
            experiment_name = agent_experiment

            # Sync env vars so setup_mlflow() from mlflow.claude_code.tracing agrees
            os.environ["MLFLOW_TRACKING_URI"] = tracking_uri
            os.environ["MLFLOW_EXPERIMENT_NAME"] = experiment_name
            os.environ["MLFLOW_CLAUDE_TRACING_ENABLED"] = "true"

            mlflow.set_tracking_uri(tracking_uri)
            mlflow.set_registry_uri("databricks-uc")
            try:
                mlflow.set_experiment(experiment_name)
            except Exception as e:
                logger.warning("MLflow set_experiment('%s') failed: %s", experiment_name, e)
                try:
                    mlflow.create_experiment(experiment_name)
                    mlflow.set_experiment(experiment_name)
                except Exception:
                    logger.warning(
                        "Cannot access MLflow experiment '%s' on %s. "
                        "Traces will not be logged. Check DATABRICKS_CONFIG_PROFILE.",
                        experiment_name,
                        tracking_uri,
                    )
                    return None

            print(f"    [MLflow] Tracing configured: uri={tracking_uri} experiment={experiment_name}")
            _mlflow_env_configured = True

    async def _upload_trace_background(session_id, transcript_path):
        """Upload transcript to MLflow in the background (best-effort).

        Judges are field-based and don't consume MLflow traces, so this is
        purely for observability logging.  Fire-and-forget avoids blocking
        the evaluation pipeline on slow HTTP I/O to the tracking server.
        """
        try:
            setup_mlflow()
            loop = asyncio.get_running_loop()
            async with _get_transcript_semaphore():
                trace = await asyncio.wait_for(
                    loop.run_in_executor(None, process_transcript, transcript_path, session_id),
                    timeout=60.0,
                )
            if trace:
                print(f"    [MLflow] Trace uploaded (background): {trace.info.trace_id}")
                try:
                    client = mlflow.MlflowClient()
                    trace_id = trace.info.trace_id
                    requested_model = os.environ.get("ANTHROPIC_MODEL", "")
                    base_url = os.environ.get("ANTHROPIC_BASE_URL", "")
                    if requested_model:
                        client.set_trace_tag(trace_id, "databricks.requested_model", requested_model)
                    if base_url:
                        client.set_trace_tag(trace_id, "databricks.model_serving_endpoint", base_url)
                    client.set_trace_tag(trace_id, "mlflow.source", "skill-test-agent-eval")
                    if skill_name:
                        client.set_trace_tag(trace_id, "skill_name", skill_name)
                except Exception as tag_err:
                    print(f"    [MLflow] Warning: could not add tags: {tag_err}")
        except asyncio.TimeoutError:
            print(f"    [MLflow] Warning: background trace upload timed out (session={session_id})")
        except Exception as e:
            print(f"    [MLflow] Warning: background trace upload failed: {e}")

    async def mlflow_stop_hook(input_data, tool_use_id, context):
        """Fire-and-forget transcript upload when agent stops.

        Launches background task and returns immediately so the agent
        result is available for scoring without waiting on MLflow I/O.
        """
        session_id = input_data.get("session_id")
        transcript_path = input_data.get("transcript_path")

        print(f"    [MLflow] Stop hook fired: session={session_id}, transcript={transcript_path}")

        # Best-effort background upload — don't block scoring pipeline
        asyncio.ensure_future(_upload_trace_background(session_id, transcript_path))
        return {"continue": True}

    return mlflow_stop_hook


async def run_agent(
    prompt: str,
    skill_md: str | None = None,
    mcp_config: dict[str, Any] | None = None,
    allowed_tools: list[str] | None = None,
    cwd: str | None = None,
    timeout_seconds: int = 300,
    model: str | None = None,
    mlflow_experiment: str | None = None,
    skill_name: str | None = None,
) -> AgentResult:
    """Run a Claude Code agent with optional skill injection.

    Args:
        prompt: The user prompt to send to the agent.
        skill_md: Optional SKILL.md content to inject as system prompt.
        mcp_config: Optional MCP server configuration dict.
            Keys are server names, values are McpServerConfig objects.
        allowed_tools: List of allowed tool names. Defaults to common builtins.
        cwd: Working directory for the agent. Defaults to current dir.
        timeout_seconds: Maximum execution time. Default 300s (5 min).
        model: Override the model to use (via env var).

    Returns:
        AgentResult with response text, trace metrics, and raw events.
    """
    try:
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher
        from claude_agent_sdk.types import (
            AssistantMessage,
            ResultMessage,
            SystemMessage,
            TextBlock,
            ToolResultBlock,
            ToolUseBlock,
            UserMessage,
        )
    except ImportError:
        return AgentResult(
            response_text="",
            trace_metrics=TraceMetrics(session_id="error"),
            success=False,
            error="claude-agent-sdk not installed. Install with: pip install claude-agent-sdk>=0.1.39",
        )

    session_id = str(uuid.uuid4())
    events: list[AgentEvent] = []
    response_parts: list[str] = []

    # Auto-load MCP config from .mcp.json if not explicitly provided
    if mcp_config is None:
        mcp_config = _load_mcp_config()
        if mcp_config:
            logger.info("Auto-loaded MCP config: %s", list(mcp_config.keys()))

    # Build options
    if allowed_tools is None:
        if mcp_config:
            # MCP tools are discovered dynamically — don't restrict
            allowed_tools = None
        else:
            allowed_tools = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]

    env = _get_agent_env()
    if model:
        env["ANTHROPIC_MODEL"] = model
    # Ensure subprocess doesn't think it's nested inside another Claude Code session.
    # Instead of mutating os.environ (not thread-safe), exclude it from the subprocess env.
    env.pop("CLAUDECODE", None)

    # Pass Databricks auth env vars to MCP server processes
    if mcp_config:
        mcp_env = {k: v for k, v in env.items() if k.startswith(("DATABRICKS_",))}
        for _server_name, server_cfg in mcp_config.items():
            if "env" not in server_cfg and mcp_env:
                server_cfg["env"] = mcp_env

    # Set up MLflow tracing via Stop hook (fire-and-forget for observability)
    mlflow_hook = _get_mlflow_stop_hook(mlflow_experiment=mlflow_experiment, skill_name=skill_name)
    hooks = {}
    if mlflow_hook:
        hooks["Stop"] = [HookMatcher(hooks=[mlflow_hook])]

    # Capture stderr from the Claude subprocess for debugging
    stderr_lines: list[str] = []

    def _stderr_callback(line: str):
        stripped = line.strip()
        if stripped:
            stderr_lines.append(stripped)
            logger.debug("[Claude stderr] %s", stripped)

    options = ClaudeAgentOptions(
        cwd=cwd or os.getcwd(),
        allowed_tools=allowed_tools,
        permission_mode="bypassPermissions",
        mcp_servers=mcp_config or {},
        system_prompt=skill_md or "",
        setting_sources=[],  # No project skills — we inject our own
        env=env,
        hooks=hooks if hooks else None,
        stderr=_stderr_callback,
    )

    start_time = time.monotonic()

    # Use ClaudeSDKClient (not query()) — Stop hooks only fire with the client.
    try:
        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)
            async for msg in client.receive_response():
                now = datetime.now(timezone.utc)
                elapsed = time.monotonic() - start_time

                if elapsed > timeout_seconds:
                    events.append(
                        AgentEvent(
                            type="error",
                            timestamp=now,
                            data={"message": f"Timeout after {timeout_seconds}s"},
                        )
                    )
                    break

                # Dispatch on message type — same pattern as builder app
                if isinstance(msg, AssistantMessage):
                    usage_data = {}
                    if hasattr(msg, "usage") and msg.usage:
                        usage_data = {
                            "input_tokens": getattr(msg.usage, "input_tokens", 0),
                            "output_tokens": getattr(msg.usage, "output_tokens", 0),
                            "cache_creation_input_tokens": getattr(msg.usage, "cache_creation_input_tokens", 0),
                            "cache_read_input_tokens": getattr(msg.usage, "cache_read_input_tokens", 0),
                        }
                    events.append(
                        AgentEvent(
                            type="assistant_turn",
                            timestamp=now,
                            data={"usage": usage_data},
                        )
                    )

                    for block in getattr(msg, "content", []):
                        if isinstance(block, TextBlock):
                            response_parts.append(block.text)
                            events.append(
                                AgentEvent(
                                    type="text",
                                    timestamp=now,
                                    data={"text": block.text},
                                )
                            )
                        elif isinstance(block, ToolUseBlock):
                            events.append(
                                AgentEvent(
                                    type="tool_use",
                                    timestamp=now,
                                    data={
                                        "id": block.id,
                                        "name": block.name,
                                        "input": block.input if isinstance(block.input, dict) else {},
                                    },
                                )
                            )
                        elif isinstance(block, ToolResultBlock):
                            events.append(
                                AgentEvent(
                                    type="tool_result",
                                    timestamp=now,
                                    data={
                                        "tool_use_id": getattr(block, "tool_use_id", ""),
                                        "content": getattr(block, "content", ""),
                                        "is_error": getattr(block, "is_error", False),
                                    },
                                )
                            )

                elif isinstance(msg, UserMessage):
                    # Tool results come back as UserMessage with ToolResultBlock content
                    for block in getattr(msg, "content", []):
                        if isinstance(block, ToolResultBlock):
                            events.append(
                                AgentEvent(
                                    type="tool_result",
                                    timestamp=now,
                                    data={
                                        "tool_use_id": getattr(block, "tool_use_id", ""),
                                        "content": getattr(block, "content", ""),
                                        "is_error": getattr(block, "is_error", False),
                                    },
                                )
                            )

                elif isinstance(msg, ResultMessage):
                    events.append(
                        AgentEvent(
                            type="result",
                            timestamp=now,
                            data={
                                "session_id": getattr(msg, "session_id", session_id),
                                "duration_ms": getattr(msg, "duration_ms", None),
                                "cost": getattr(msg, "cost", None),
                            },
                        )
                    )
                    session_id = getattr(msg, "session_id", session_id)

                elif isinstance(msg, SystemMessage):
                    events.append(
                        AgentEvent(
                            type="system",
                            timestamp=now,
                            data={
                                "subtype": getattr(msg, "subtype", ""),
                                "data": getattr(msg, "data", {}),
                            },
                        )
                    )

    except asyncio.TimeoutError:
        events.append(
            AgentEvent(
                type="error",
                timestamp=datetime.now(timezone.utc),
                data={"message": f"asyncio.TimeoutError after {timeout_seconds}s"},
            )
        )
    except Exception as e:
        stderr_detail = "; ".join(stderr_lines[-5:]) if stderr_lines else "no stderr"
        logger.error("Agent execution failed: %s | stderr: %s", e, stderr_detail)
        events.append(
            AgentEvent(
                type="error",
                timestamp=datetime.now(timezone.utc),
                data={"message": f"{e} | stderr: {stderr_detail}"},
            )
        )

    duration_ms = int((time.monotonic() - start_time) * 1000)

    # Build trace metrics from captured events
    trace_metrics = _build_trace_metrics(events, session_id)

    # Determine model from env
    trace_metrics.model = model or os.environ.get("ANTHROPIC_MODEL")

    response_text = "\n".join(response_parts)
    has_error = any(e.type == "error" for e in events)

    return AgentResult(
        response_text=response_text,
        trace_metrics=trace_metrics,
        events=events,
        session_id=session_id,
        duration_ms=duration_ms,
        success=not has_error,
        error=next((e.data.get("message") for e in events if e.type == "error"), None),
    )


def _run_in_fresh_loop(coro) -> Any:
    """Run a coroutine in a fresh event loop in a dedicated thread.

    Same pattern as databricks-builder-app/server/services/agent.py —
    avoids subprocess transport cleanup errors by running the entire
    event loop lifecycle in an isolated thread.
    """
    import concurrent.futures

    result_holder: dict[str, Any] = {}

    def _thread_target():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result_holder["value"] = loop.run_until_complete(coro)
        except Exception as e:
            result_holder["error"] = e
        finally:
            try:
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.run_until_complete(loop.shutdown_asyncgens())
                # Don't block on shutdown_default_executor() — background tasks
                # (e.g. trace uploads) may still be running.
                try:
                    loop.run_until_complete(asyncio.wait_for(loop.shutdown_default_executor(), timeout=5.0))
                except (asyncio.TimeoutError, Exception):
                    pass  # Let the default executor GC naturally
            except Exception:
                pass
            # Suppress "Loop ... is closed" from subprocess transport __del__
            # that runs during GC after the loop closes. This is harmless —
            # the subprocess has already exited.
            _original_check = loop._check_closed
            loop._check_closed = lambda: None
            loop.close()

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(_thread_target)
        future.result(timeout=600)  # wait for thread to finish
    except concurrent.futures.TimeoutError:
        # Don't let shutdown(wait=True) block — the thread is still running
        pool.shutdown(wait=False)
        raise
    else:
        pool.shutdown(wait=True)

    if "error" in result_holder:
        raise result_holder["error"]
    return result_holder["value"]


def run_agent_sync_wrapper(
    prompt: str,
    skill_md: str | None = None,
    **kwargs: Any,
) -> AgentResult:
    """Synchronous wrapper for run_agent.

    Runs the async agent in a fresh event loop on a dedicated thread,
    following the same pattern as databricks-builder-app to avoid
    anyio cancel-scope and subprocess transport cleanup issues.
    """
    return _run_in_fresh_loop(run_agent(prompt=prompt, skill_md=skill_md, **kwargs))

"""Claude Code Agent service for managing agent sessions.

Uses the claude-agent-sdk to create and manage Claude Code agent sessions
with directory-scoped file permissions and Databricks tools.

Databricks tools are loaded in-process from databricks-mcp-server using
the SDK tool wrapper. Auth is handled via contextvars for multi-user support.

MLflow Tracing:
  This module integrates with MLflow for tracing Claude Code conversations.
  Uses query() with a custom Stop hook for proper streaming + tracing.
  See: https://mlflow.org/docs/latest/genai/tracing/integrations/listing/claude_code/

NOTE: Fresh event loop workaround applied to fix claude-agent-sdk issue #462
where subprocess transport fails in FastAPI/uvicorn contexts.
See: https://github.com/anthropics/claude-agent-sdk-python/issues/462
"""

import asyncio
import json
import logging
import os
import queue
import re
import sys
import threading
import time
import traceback
from contextvars import copy_context
from pathlib import Path
from typing import AsyncIterator

from claude_agent_sdk import ClaudeAgentOptions, query, HookMatcher
from claude_agent_sdk.types import (
  AssistantMessage,
  PermissionResultAllow,
  PermissionResultDeny,
  ResultMessage,
  StreamEvent,
  SystemMessage,
  TextBlock,
  ThinkingBlock,
  ToolPermissionContext,
  ToolResultBlock,
  ToolUseBlock,
  UserMessage,
)
import databricks_tools_core.auth as _dt_auth
from databricks_tools_core.auth import set_databricks_auth, clear_databricks_auth

_original_get_workspace_client = _dt_auth.get_workspace_client


def _obo_workspace_client():
  """OBO: user token (when set) takes priority over SP OAuth for workspace ops."""
  host = _dt_auth._host_ctx.get() or os.environ.get('DATABRICKS_HOST')
  token = _dt_auth._token_ctx.get()
  if token:
    if not host:
      raise ValueError('Databricks host is required when using a context token')
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.credentials_provider import CredentialsStrategy
    from databricks_tools_core.identity import PRODUCT_NAME, PRODUCT_VERSION, tag_client

    _t = token

    class _OBOStrategy(CredentialsStrategy):
      def auth_type(self) -> str:
        return 'pat'

      def __call__(self, cfg):
        return lambda: {'Authorization': f'Bearer {_t}'}

    return tag_client(WorkspaceClient(
      host=host,
      credentials_strategy=_OBOStrategy(),
      product=PRODUCT_NAME,
      product_version=PRODUCT_VERSION,
    ))
  return _original_get_workspace_client()


_dt_auth.get_workspace_client = _obo_workspace_client

from .backup_manager import ensure_project_directory as _ensure_project_directory
from .databricks_tools import load_databricks_tools, create_filtered_databricks_server
from .system_prompt import get_system_prompt

logger = logging.getLogger(__name__)

_IMAGE_PATH_RE = re.compile(
  r'(?:dbfs:/|/dbfs/|/Volumes/|/Workspace/|/Users/|/Shared/)'
  r'[^\s\'"<>\]]*\.(?:png|jpg|jpeg|gif|svg|webp)',
  re.IGNORECASE,
)
_CLUSTER_ID_RE = re.compile(r'"cluster_id"\s*:\s*"([^"]+)"')
_CLUSTER_NAME_RE = re.compile(r'"cluster_name"\s*:\s*"([^"]+)"')
_CONTEXT_ID_RE = re.compile(r'"context_id"\s*:\s*"([^"]+)"')
_cluster_name_cache: dict[str, str] = {
  '__serverless__': 'Serverless Compute',
  'serverless': 'Serverless Compute',
}


def _extract_image_paths(content: str) -> list[str]:
  """Return normalised Databricks paths for any image files mentioned in tool output."""
  paths = []
  for m in _IMAGE_PATH_RE.finditer(content):
    p = m.group(0)
    if p.startswith('/dbfs/'):
      p = 'dbfs:/' + p[6:]
    paths.append(p)
  return paths


def _is_inline_image_tool(tool_name: str | None) -> bool:
  """True for MCP tools whose output may include renderable image paths."""
  if not tool_name:
    return False
  normalized = tool_name.strip()
  return (
    normalized == 'execute_databricks_command'
    or normalized.endswith('__execute_databricks_command')
    or normalized == 'check_operation_status'
    or normalized.endswith('__check_operation_status')
  )


def _is_command_execution_tool(tool_name: str | None) -> bool:
  """True only for Databricks command-execution MCP tool names."""
  if not tool_name:
    return False
  normalized = tool_name.strip()
  return (
    normalized == 'execute_databricks_command'
    or normalized.endswith('__execute_databricks_command')
  )


def _resolve_cluster_name(cluster_id: str | None) -> str | None:
  """Best-effort cluster name lookup from a cluster_id."""
  if not cluster_id:
    return None

  cached = _cluster_name_cache.get(cluster_id)
  if cached:
    return cached

  try:
    client = _dt_auth.get_workspace_client()
    cluster = client.clusters.get(cluster_id=cluster_id)
    cluster_name = getattr(cluster, 'cluster_name', None)
    if cluster_name:
      _cluster_name_cache[cluster_id] = cluster_name
      return cluster_name
  except Exception:
    logger.debug('Failed to resolve cluster name for cluster_id=%s', cluster_id, exc_info=True)

  return None


def _extract_command_execution_metadata(
  content: str,
  default_cluster_id: str | None = None,
) -> dict[str, str]:
  """Extract command execution metadata from tool output text."""
  cluster_id: str | None = None
  cluster_name: str | None = None
  context_id: str | None = None

  try:
    parsed = json.loads(content)
    if isinstance(parsed, dict):
      raw_cluster_id = parsed.get('cluster_id')
      raw_cluster_name = parsed.get('cluster_name')
      raw_context_id = parsed.get('context_id')
      if isinstance(raw_cluster_id, str) and raw_cluster_id:
        cluster_id = raw_cluster_id
      if isinstance(raw_cluster_name, str) and raw_cluster_name:
        cluster_name = raw_cluster_name
      if isinstance(raw_context_id, str) and raw_context_id:
        context_id = raw_context_id
  except Exception:
    # Expected for mixed/plain outputs; fall back to regex below.
    pass

  if not cluster_id:
    m = _CLUSTER_ID_RE.search(content)
    if m:
      cluster_id = m.group(1)
  if not cluster_name:
    m = _CLUSTER_NAME_RE.search(content)
    if m:
      cluster_name = m.group(1)
  if not context_id:
    m = _CONTEXT_ID_RE.search(content)
    if m:
      context_id = m.group(1)

  if not cluster_id and default_cluster_id:
    cluster_id = default_cluster_id
  if not cluster_name:
    cluster_name = _resolve_cluster_name(cluster_id)

  metadata: dict[str, str] = {}
  if cluster_id:
    metadata['cluster_id'] = cluster_id
  if cluster_name:
    metadata['cluster_name'] = cluster_name
  if context_id:
    metadata['context_id'] = context_id
  return metadata

# Built-in Claude Code tools
BUILTIN_TOOLS = [
  'Read',
  'Write',
  'Edit',
#  'Bash',
  'Glob',
  'Grep',
]

# Cached Databricks tools (loaded once)
_databricks_server = None
_databricks_tool_names = None

# Cached Claude settings (loaded once)
_claude_settings = None


def _load_claude_settings() -> dict:
  """Initialize Claude settings dictionary.

  Previously loaded from .claude/settings.json, but now all auth settings
  are injected dynamically from the user's Databricks credentials and
  environment variables set in app.yaml.

  Returns:
      Dictionary of environment variables to pass to Claude subprocess
  """
  global _claude_settings

  if _claude_settings is not None:
    return _claude_settings

  # Start with empty dict - auth settings are added dynamically per-request
  _claude_settings = {}
  return _claude_settings


def get_databricks_tools(force_reload: bool = False):
  """Get Databricks tools, optionally forcing a reload.

  Args:
      force_reload: If True, recreate the MCP server to clear any corrupted state

  Returns:
      Tuple of (server, tool_names)
  """
  global _databricks_server, _databricks_tool_names
  if _databricks_server is None or force_reload:
    if force_reload:
      logger.info('Force reloading Databricks MCP server')
    _databricks_server, _databricks_tool_names = load_databricks_tools()
  return _databricks_server, _databricks_tool_names


def get_project_directory(project_id: str) -> Path:
  """Get the directory path for a project.

  If the directory doesn't exist, attempts to restore from backup.
  If no backup exists, creates an empty directory.

  Args:
      project_id: The project UUID

  Returns:
      Path to the project directory
  """
  return _ensure_project_directory(project_id)


def _get_mlflow_stop_hook(experiment_name: str | None = None):
  """Get the MLflow Stop hook for tracing Claude Code conversations.

  This hook processes the transcript after the conversation ends and
  creates an MLflow trace. Works with query() function unlike autolog
  which only works with ClaudeSDKClient.

  Args:
      experiment_name: Optional MLflow experiment name

  Returns:
      The async hook function, or None if MLflow is not available
  """
  try:
    import mlflow
    from mlflow.claude_code.tracing import process_transcript, setup_mlflow

    # Set up MLflow tracking
    mlflow.set_tracking_uri('databricks')
    if experiment_name:
      try:
        # Support both experiment IDs (numeric) and experiment names (paths)
        if experiment_name.isdigit():
          mlflow.set_experiment(experiment_id=experiment_name)
          logger.info(f'MLflow experiment set by ID: {experiment_name}')
        else:
          mlflow.set_experiment(experiment_name)
          logger.info(f'MLflow experiment set to: {experiment_name}')
      except Exception as e:
        logger.warning(f'Could not set MLflow experiment: {e}')

    async def mlflow_stop_hook(input_data: dict, tool_use_id: str | None, context) -> dict:
      """Process transcript and create MLflow trace when conversation ends."""
      try:
        session_id = input_data.get('session_id')
        transcript_path = input_data.get('transcript_path')

        logger.info(f'MLflow Stop hook triggered: session={session_id}')

        # Ensure MLflow is set up (tracking URI and experiment)
        setup_mlflow()

        # Process transcript and create trace
        trace = process_transcript(transcript_path, session_id)

        if trace:
          logger.info(f'MLflow trace created: {trace.info.trace_id}')

          # Add requested model name as trace tags
          # The trace captures the response model (e.g., claude-opus-4-5-20251101)
          # but we want to also record the Databricks endpoint name we requested
          try:
            client = mlflow.MlflowClient()
            trace_id = trace.info.trace_id
            requested_model = os.environ.get('ANTHROPIC_MODEL', 'databricks-claude-opus-4-5')
            requested_model_mini = os.environ.get('ANTHROPIC_MODEL_MINI', 'databricks-claude-sonnet-4-5')
            base_url = os.environ.get('ANTHROPIC_BASE_URL', '')

            # Set tags to clarify the Databricks model endpoint used
            client.set_trace_tag(trace_id, 'databricks.requested_model', requested_model)
            client.set_trace_tag(trace_id, 'databricks.requested_model_mini', requested_model_mini)
            if base_url:
              client.set_trace_tag(trace_id, 'databricks.model_serving_endpoint', base_url)
            client.set_trace_tag(trace_id, 'llm.provider', 'databricks-fmapi')

            logger.info(f'Added Databricks model tags to trace {trace_id}: {requested_model}')
          except Exception as tag_err:
            logger.warning(f'Could not add model tags to trace: {tag_err}')
        else:
          logger.debug('MLflow trace creation returned None (possibly empty transcript)')

        return {'continue': True}
      except Exception as e:
        logger.error(f'Error in MLflow Stop hook: {e}', exc_info=True)
        # Return continue=True to not interrupt the conversation
        return {'continue': True}

    logger.info(f'MLflow tracing hook configured: {mlflow.get_tracking_uri()}')
    return mlflow_stop_hook

  except ImportError as e:
    logger.debug(f'MLflow not available: {e}')
    return None
  except Exception as e:
    logger.warning(f'Failed to create MLflow stop hook: {e}')
    return None


def _run_agent_in_fresh_loop(message, options, result_queue, context, is_cancelled_fn, mlflow_experiment=None, images=None):
  """Run agent in a fresh event loop (workaround for issue #462).

  This function runs in a separate thread with a fresh event loop to avoid
  the subprocess transport issues in FastAPI/uvicorn contexts.

  Uses query() for proper streaming, with a custom MLflow Stop hook for tracing.
  The Stop hook processes the transcript after the conversation ends.

  Args:
      message: User message to send to the agent
      options: ClaudeAgentOptions for the agent
      result_queue: Queue to send results back to the main thread
      context: Copy of contextvars context (for Databricks auth, etc.)
      is_cancelled_fn: Callable that returns True if the request has been cancelled
      mlflow_experiment: Optional MLflow experiment name for tracing

  See: https://github.com/anthropics/claude-agent-sdk-python/issues/462
  """
  # Run in the copied context to preserve contextvars (like Databricks auth)
  def run_with_context():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Add MLflow Stop hook for tracing if experiment is configured
    exp_name = mlflow_experiment or os.environ.get('MLFLOW_EXPERIMENT_NAME')
    if exp_name:
      mlflow_hook = _get_mlflow_stop_hook(exp_name)
      if mlflow_hook:
        # Add the hook to options
        if options.hooks is None:
          options.hooks = {}
        if 'Stop' not in options.hooks:
          options.hooks['Stop'] = []
        options.hooks['Stop'].append(HookMatcher(hooks=[mlflow_hook]))
        logger.info('MLflow Stop hook added to agent options')

    async def run_query():
      """Run agent using query() for proper streaming."""
      # Create prompt generator in the fresh event loop context
      async def prompt_generator():
        if images:
          content = [{'type': 'image', 'source': img} for img in images]
          content.append({'type': 'text', 'text': message})
          yield {'type': 'user', 'message': {'role': 'user', 'content': content}}
        else:
          yield {'type': 'user', 'message': {'role': 'user', 'content': message}}

      try:
        msg_count = 0
        async for msg in query(prompt=prompt_generator(), options=options):
          msg_count += 1
          msg_type = type(msg).__name__
          logger.debug(f"[AGENT DEBUG] Received message #{msg_count}: {msg_type}")

          # Log more details for specific message types
          if hasattr(msg, 'content'):
            content = msg.content
            if isinstance(content, list):
              block_types = [type(b).__name__ for b in content]
              logger.debug(f"[AGENT DEBUG]   Content blocks: {block_types}")
          if hasattr(msg, 'is_error') and msg.is_error:
            logger.debug('[AGENT DEBUG]   is_error=True')
          if hasattr(msg, 'session_id'):
            logger.debug(f"[AGENT DEBUG]   session_id={msg.session_id}")

          # Check for cancellation before processing each message
          if is_cancelled_fn():
            logger.info("Agent cancelled by user request")
            result_queue.put(('cancelled', None))
            return
          result_queue.put(('message', msg))
        logger.debug(f"[AGENT DEBUG] query() loop completed normally after {msg_count} messages")
      except asyncio.CancelledError:
        logger.warning("Agent query was cancelled (asyncio.CancelledError)")
        result_queue.put(('error', Exception("Agent query cancelled - likely due to stream timeout or connection issue")))
      except ConnectionError as e:
        logger.error(f"Connection error in agent query: {e}")
        result_queue.put(('error', Exception(f"Connection error: {e}. This may occur when tools take longer than the stream timeout (50s).")))
      except BrokenPipeError as e:
        logger.error(f"Broken pipe in agent query: {e}")
        result_queue.put(('error', Exception(f"Broken pipe: {e}. The agent subprocess communication was interrupted.")))
      except Exception as e:
        logger.exception(f"Unexpected error in agent query: {type(e).__name__}: {e}")
        result_queue.put(('error', e))
      finally:
        result_queue.put(('done', None))

    try:
      loop.run_until_complete(run_query())
    finally:
      loop.close()

  # Execute in the copied context
  context.run(run_with_context)


def _process_tool_result(
  block: ToolResultBlock,
  ask_user_tool_ids: set[str],
  tool_name: str | None = None,
  default_cluster_id: str | None = None,
) -> dict:
  """Extract and normalize content from a ToolResultBlock for streaming."""
  content = block.content
  if isinstance(content, list):
    texts = []
    for item in content:
      if isinstance(item, dict) and 'text' in item:
        texts.append(item['text'])
      elif isinstance(item, str):
        texts.append(item)
      elif hasattr(item, 'text'):
        texts.append(item.text)
      else:
        texts.append(str(item))
    content = '\n'.join(texts) if texts else str(block.content)
  elif not isinstance(content, str):
    content = str(content)

  # Rewrite AskUserQuestion results — the can_use_tool callback provides
  # synthetic answers, but the CLI result text is misleading (e.g. "User has
  # answered your questions: ..."). Replace with a clear message.
  if block.tool_use_id in ask_user_tool_ids:
    content = 'Asking user questions directly in conversation'
  elif block.is_error and 'Stream closed' in content:
    content = f'Tool execution interrupted: {content}. This may occur when operations exceed timeout limits or when the connection is interrupted. Check backend logs for more details.'
    logger.warning(f'Tool result error (improved): {content}')

  result = {
    'type': 'tool_result',
    'tool_use_id': block.tool_use_id,
    'content': content,
    'is_error': block.is_error,
  }
  if _is_command_execution_tool(tool_name):
    command_execution = _extract_command_execution_metadata(
      content,
      default_cluster_id=default_cluster_id,
    )
    if command_execution:
      result['command_execution'] = command_execution
  return result


async def stream_agent_response(
  project_id: str,
  message: str,
  images: list[dict] | None = None,
  session_id: str | None = None,
  cluster_id: str | None = None,
  default_catalog: str | None = None,
  default_schema: str | None = None,
  warehouse_id: str | None = None,
  workspace_folder: str | None = None,
  fmapi_host: str | None = None,
  fmapi_token: str | None = None,
  databricks_host: str | None = None,
  databricks_token: str | None = None,
  is_cross_workspace: bool = False,
  is_cancelled_fn: callable = None,
  enabled_skills: list[str] | None = None,
  mlflow_experiment_name: str | None = None,
  custom_system_prompt: str | None = None,
  user_email: str | None = None,
  user_access_token: str | None = None,
  anthropic_model: str | None = None,
  anthropic_model_mini: str | None = None,
) -> AsyncIterator[dict]:
  """Stream Claude agent response with all event types.

  Uses query() with custom MLflow Stop hook for tracing.
  Yields normalized event dicts for the frontend.

  Args:
      project_id: The project UUID
      message: User message to send
      session_id: Optional session ID for resuming conversations
      cluster_id: Optional Databricks cluster ID for code execution
      default_catalog: Optional default Unity Catalog name
      default_schema: Optional default schema name
      warehouse_id: Optional Databricks SQL warehouse ID for queries
      workspace_folder: Optional workspace folder for file uploads
      fmapi_host: Builder App workspace URL for Claude API (FMAPI)
      fmapi_token: Builder App token for Claude API authentication
      databricks_host: Target workspace URL for Databricks tool operations
      databricks_token: Target workspace token for Databricks tool auth
      is_cross_workspace: When True, tool operations target a different workspace
          than the Builder App. Enables force_token in auth context.
      is_cancelled_fn: Optional callable that returns True if request is cancelled
      enabled_skills: Optional list of enabled skill names. None means all skills.

  Yields:
      Event dicts with 'type' field for frontend consumption
  """
  project_dir = get_project_directory(project_id)

  if session_id:
    logger.info(f'Resuming session {session_id} in {project_dir}: {message[:100]}...')
  else:
    logger.info(f'Starting new session in {project_dir}: {message[:100]}...')

  # Log the working directory for debugging path issues
  logger.info(f'Agent working directory (cwd): {project_dir}')
  logger.info(f'Workspace folder (remote): {workspace_folder}')

  # Use user's access token for tool operations when available
  if user_access_token:
    databricks_token = user_access_token
  # Set auth context for tool operations (targets the specified workspace)
  # When cross-workspace, force_token ensures the target credentials are used
  # even when OAuth M2M credentials exist in environment
  set_databricks_auth(databricks_host, databricks_token, force_token=is_cross_workspace)

  try:
    # Build allowed tools list
    allowed_tools = BUILTIN_TOOLS.copy()

    # Sync project skills directory before running agent
    from .skills_manager import sync_project_skills, get_available_skills, get_allowed_mcp_tools
    sync_project_skills(project_dir, enabled_skills=enabled_skills)

    # Sync user's personal workspace skills if token is available
    if user_email and user_access_token:
      try:
        from .workspace_personal import sync_personal_skills_to_project
        synced = sync_personal_skills_to_project(user_email, user_access_token, project_dir)
        if synced:
          logger.info(f'Synced {synced} personal skills to project')
      except Exception as e:
        logger.warning(f'Failed to sync personal skills: {e}')

    # Get Databricks tools and filter based on enabled skills.
    # We must create a filtered MCP server (not just filter allowed_tools)
    # because bypassPermissions mode exposes all tools in registered MCP servers.
    databricks_server, databricks_tool_names = get_databricks_tools()
    filtered_tool_names = get_allowed_mcp_tools(databricks_tool_names, enabled_skills=enabled_skills)

    if len(filtered_tool_names) < len(databricks_tool_names):
      # Some tools are blocked — create a filtered MCP server with only allowed tools
      databricks_server, filtered_tool_names = create_filtered_databricks_server(filtered_tool_names)
      blocked_count = len(databricks_tool_names) - len(filtered_tool_names)
      logger.info(f'Databricks MCP server: {len(filtered_tool_names)} tools allowed, {blocked_count} blocked by disabled skills')
    else:
      logger.info(f'Databricks MCP server configured with {len(filtered_tool_names)} tools')

    allowed_tools.extend(filtered_tool_names)

    # Only add the Skill tool if there are enabled skills for the agent to use
    available = get_available_skills(enabled_skills=enabled_skills)
    if available:
      allowed_tools.append('Skill')

    # Generate system prompt with available skills, cluster, warehouse, and catalog/schema context
    system_prompt = get_system_prompt(
      cluster_id=cluster_id,
      default_catalog=default_catalog,
      default_schema=default_schema,
      warehouse_id=warehouse_id,
      workspace_folder=workspace_folder,
      workspace_url=databricks_host,
      enabled_skills=enabled_skills,
    )

    # Override with custom system prompt if provided
    if custom_system_prompt:
      system_prompt = custom_system_prompt

    # Load Claude settings for Databricks model serving authentication
    claude_env = _load_claude_settings()

    # Log auth state for debugging
    logger.info(
      f'Auth state: fmapi_host={fmapi_host}, databricks_host={databricks_host}, '
      f'is_cross_workspace={is_cross_workspace}'
    )

    # Configure Claude subprocess to use Databricks FMAPI on the Builder App's
    # workspace. FMAPI auth always points at the Builder App, even when tool
    # operations target a different workspace (cross-workspace mode).
    # Fall back to databricks_host/token for callers that don't split FMAPI creds.
    effective_fmapi_host = fmapi_host or databricks_host
    effective_fmapi_token = fmapi_token or databricks_token
    if effective_fmapi_host and effective_fmapi_token:
      host = effective_fmapi_host.replace('https://', '').replace('http://', '').rstrip('/')
      anthropic_base_url = f'https://{host}/serving-endpoints/anthropic'

      # Route through the local proxy so unsupported fields/headers
      # (context_management, betas, anthropic-beta) are stripped before
      # hitting Databricks FMAPI.
      app_port = os.environ.get('DATABRICKS_APP_PORT', '8000')
      proxy_base_url = f'http://localhost:{app_port}/anthropic-proxy'
      claude_env['ANTHROPIC_BASE_URL'] = proxy_base_url
      claude_env['ANTHROPIC_API_KEY'] = effective_fmapi_token
      claude_env['ANTHROPIC_AUTH_TOKEN'] = effective_fmapi_token

      # Store the real FMAPI URL server-side so the proxy can read it
      # directly (avoids header-parsing issues with ANTHROPIC_CUSTOM_HEADERS).
      from ..routers.anthropic_proxy import set_fmapi_base_url
      set_fmapi_base_url(anthropic_base_url)

      # Enable coding agent mode on FMAPI (matches upstream format)
      claude_env['ANTHROPIC_CUSTOM_HEADERS'] = 'x-databricks-use-coding-agent-mode: true'

      # Set the model: user setting > env var > default
      effective_model = anthropic_model or os.environ.get('ANTHROPIC_MODEL', 'databricks-claude-opus-4-6')
      claude_env['ANTHROPIC_MODEL'] = effective_model
      if anthropic_model_mini:
        claude_env['ANTHROPIC_SMALL_FAST_MODEL'] = anthropic_model_mini

      # Extra safety: disable experimental betas at the SDK level too
      claude_env['CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS'] = '1'

      logger.info(f'Configured Databricks model serving via proxy: {proxy_base_url} → {anthropic_base_url} with model {effective_model}')
      logger.info(f'Claude env vars: BASE_URL={claude_env.get("ANTHROPIC_BASE_URL")}, MODEL={claude_env.get("ANTHROPIC_MODEL")}')

    # Databricks SDK upstream tracking for subprocess user-agent attribution
    from databricks_tools_core.identity import PRODUCT_NAME, PRODUCT_VERSION
    claude_env['DATABRICKS_SDK_UPSTREAM'] = PRODUCT_NAME
    claude_env['DATABRICKS_SDK_UPSTREAM_VERSION'] = PRODUCT_VERSION

    # Ensure stream timeout is set (1 hour to handle long tool sequences)
    stream_timeout = os.environ.get('CLAUDE_CODE_STREAM_CLOSE_TIMEOUT', '3600000')
    claude_env['CLAUDE_CODE_STREAM_CLOSE_TIMEOUT'] = stream_timeout

    # Hardening for non-interactive app runtime:
    # some subprocess paths invoke terminal capabilities (e.g., tput) and can
    # fail when TERM/TTY expectations are not met inside Databricks Apps.
    claude_env.setdefault('TERM', 'xterm')
    claude_env.setdefault('CI', '1')
    claude_env.setdefault('NO_COLOR', '1')
    claude_env.setdefault('CLICOLOR', '0')

    # Stderr callback to capture Claude subprocess output for debugging
    def stderr_callback(line: str):
      logger.debug(f'[Claude stderr] {line.strip()}')
      # Also print to stderr for immediate visibility during development
      print(f'[Claude stderr] {line.strip()}', file=sys.stderr, flush=True)

    # Handle AskUserQuestion tool calls gracefully.
    # With bypassPermissions and no callback, AskUserQuestion triggers an SDK
    # error ("canUseTool callback is not provided") which produces is_error=True
    # tool results — showing as "Failed" in downstream UIs like Lemma.
    # This callback allows AskUserQuestion with a synthetic answer that redirects
    # Claude to ask questions as normal text, avoiding the error path entirely.
    async def can_use_tool(
      tool_name: str, input_data: dict, _context: ToolPermissionContext,
    ) -> PermissionResultAllow | PermissionResultDeny:
      if tool_name == "AskUserQuestion":
        questions = input_data.get("questions", [])
        answers = {
          q.get("question", ""): "Please ask this question directly in your text response."
          for q in questions
        }
        return PermissionResultAllow(
          updated_input={"questions": questions, "answers": answers},
        )
      return PermissionResultAllow(updated_input=input_data)

    # Required for can_use_tool in Python: a PreToolUse hook that keeps the
    # stream open so the permission callback can be invoked.
    async def _keepalive_hook(_input_data, _tool_use_id, _context):
      return {"continue_": True}

    options = ClaudeAgentOptions(
      cwd=str(project_dir),
      allowed_tools=allowed_tools,
      permission_mode='bypassPermissions',  # Auto-accept all tools including MCP
      can_use_tool=can_use_tool,  # Handle AskUserQuestion gracefully
      hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[_keepalive_hook])]},
      resume=session_id,  # Resume from previous session if provided
      mcp_servers={'databricks': databricks_server},  # In-process SDK tools
      system_prompt=system_prompt,  # Databricks-focused system prompt
      setting_sources=["user", "project"],  # Load Skills from filesystem
      env=claude_env,  # Pass Databricks auth settings (ANTHROPIC_AUTH_TOKEN, etc.)
      include_partial_messages=True,  # Enable token-by-token streaming
      stderr=stderr_callback,  # Capture stderr for debugging
    )

    # Run agent in fresh event loop to avoid subprocess transport issues (#462)
    # Copy the context to preserve contextvars (Databricks auth) in the new thread
    ctx = copy_context()
    result_queue = queue.Queue()
    # Default to always-false if no cancellation function provided
    cancel_check = is_cancelled_fn if is_cancelled_fn else lambda: False

    # Get MLflow experiment name from request param, falling back to environment
    mlflow_experiment = mlflow_experiment_name or os.environ.get('MLFLOW_EXPERIMENT_NAME')

    agent_thread = threading.Thread(
      target=_run_agent_in_fresh_loop,
      args=(message, options, result_queue, ctx, cancel_check, mlflow_experiment, images),
      daemon=True
    )
    agent_thread.start()

    # Process messages from the queue with keepalive for long operations
    KEEPALIVE_INTERVAL = 15  # seconds - send keepalive if no activity
    last_activity = time.time()
    # Track AskUserQuestion tool IDs to rewrite their results in the stream
    ask_user_tool_ids: set[str] = set()
    _tool_name_by_id: dict[str, str] = {}
    _last_tool_use_name: str = ''
    _emitted_inline_image_paths: set[str] = set()
    _total_input_tokens: int = 0
    _total_output_tokens: int = 0
    _total_cache_read_tokens: int = 0
    _total_cache_creation_tokens: int = 0

    while True:
      # Use timeout on queue.get to allow keepalive emission
      def get_with_timeout():
        try:
          return result_queue.get(timeout=KEEPALIVE_INTERVAL)
        except queue.Empty:
          return ('keepalive', None)

      msg_type, msg = await asyncio.get_event_loop().run_in_executor(
        None, get_with_timeout
      )

      if msg_type == 'keepalive':
        # Emit keepalive event to keep the stream active during long tool execution
        elapsed = time.time() - last_activity
        logger.debug(f'Emitting keepalive after {elapsed:.0f}s of inactivity')
        yield {
          'type': 'keepalive',
          'elapsed_since_last_event': elapsed,
        }
        continue

      # Update last activity time for non-keepalive messages
      last_activity = time.time()

      if msg_type == 'done':
        break
      elif msg_type == 'cancelled':
        logger.info("Agent execution cancelled")
        yield {'type': 'cancelled'}
        break
      elif msg_type == 'error':
        raise msg
      elif msg_type == 'message':
        # Handle different message types
        if isinstance(msg, AssistantMessage):
          # Process content blocks
          for block in msg.content:
            if isinstance(block, TextBlock):
              yield {
                'type': 'text',
                'text': block.text,
              }
            elif isinstance(block, ThinkingBlock):
              yield {
                'type': 'thinking',
                'thinking': block.thinking,
              }
            elif isinstance(block, ToolUseBlock):
              # Track AskUserQuestion calls so we can rewrite their results
              if block.name == 'AskUserQuestion':
                ask_user_tool_ids.add(block.id)
              _tool_name_by_id[block.id] = block.name
              _last_tool_use_name = block.name
              yield {
                'type': 'tool_use',
                'tool_id': block.id,
                'tool_name': block.name,
                'tool_input': block.input,
              }
            elif isinstance(block, ToolResultBlock):
              raw_tid = block.tool_use_id
              tool_name = _tool_name_by_id.get(raw_tid, '') if raw_tid else _last_tool_use_name
              result_event = _process_tool_result(
                block,
                ask_user_tool_ids,
                tool_name=tool_name,
                default_cluster_id=cluster_id,
              )
              yield result_event
              if not block.is_error and _is_inline_image_tool(tool_name):
                for img_path in _extract_image_paths(result_event.get('content', '')):
                  if img_path not in _emitted_inline_image_paths:
                    _emitted_inline_image_paths.add(img_path)
                    yield {'type': 'inline_image', 'path': img_path}

        elif isinstance(msg, ResultMessage):
          yield {
            'type': 'result',
            'session_id': msg.session_id,
            'duration_ms': msg.duration_ms,
            'total_cost_usd': msg.total_cost_usd,
            'is_error': msg.is_error,
            'num_turns': msg.num_turns,
            'input_tokens': _total_input_tokens,
            'output_tokens': _total_output_tokens,
            'cache_read_tokens': _total_cache_read_tokens,
            'cache_creation_tokens': _total_cache_creation_tokens,
          }

        elif isinstance(msg, SystemMessage):
          yield {
            'type': 'system',
            'subtype': msg.subtype,
            'data': msg.data if hasattr(msg, 'data') else None,
          }

        elif isinstance(msg, UserMessage):
          # UserMessage can contain tool results (sent back to Claude after tool execution)
          msg_content = msg.content
          if isinstance(msg_content, list):
            for block in msg_content:
              if isinstance(block, ToolResultBlock):
                raw_tid = block.tool_use_id
                tool_name = _tool_name_by_id.get(raw_tid, '') if raw_tid else _last_tool_use_name
                result_event = _process_tool_result(
                  block,
                  ask_user_tool_ids,
                  tool_name=tool_name,
                  default_cluster_id=cluster_id,
                )
                yield result_event
                if not block.is_error and _is_inline_image_tool(tool_name):
                  for img_path in _extract_image_paths(result_event.get('content', '')):
                    if img_path not in _emitted_inline_image_paths:
                      _emitted_inline_image_paths.add(img_path)
                      yield {'type': 'inline_image', 'path': img_path}
          # Skip string content (just echo of user input)

        elif isinstance(msg, StreamEvent):
          # Handle streaming events for token-by-token updates
          event_data = msg.event
          event_type = event_data.get('type', '')

          # Handle text delta events (token streaming)
          if event_type == 'content_block_delta':
            delta = event_data.get('delta', {})
            delta_type = delta.get('type', '')
            if delta_type == 'text_delta':
              text = delta.get('text', '')
              if text:
                yield {
                  'type': 'text_delta',
                  'text': text,
                }
            elif delta_type == 'thinking_delta':
              thinking = delta.get('thinking', '')
              if thinking:
                yield {
                  'type': 'thinking_delta',
                  'thinking': thinking,
                }
          elif event_type == 'message_start':
            usage = event_data.get('message', {}).get('usage', {})
            _total_input_tokens += usage.get('input_tokens', 0)
            _total_output_tokens += usage.get('output_tokens', 0)
            _total_cache_read_tokens += usage.get('cache_read_input_tokens', 0)
            _total_cache_creation_tokens += usage.get('cache_creation_input_tokens', 0)
          elif event_type == 'message_delta':
            usage = event_data.get('usage', {})
            _total_output_tokens += usage.get('output_tokens', 0)
          # Pass through other stream events if needed
          elif event_type not in ('content_block_start', 'content_block_stop', 'message_delta', 'message_stop'):
            yield {
              'type': 'stream_event',
              'event': event_data,
              'session_id': msg.session_id,
            }

  except Exception as e:
    # Log full traceback for debugging
    error_msg = f'Error during Claude query: {e}'
    full_traceback = traceback.format_exc()

    # Use print to stderr for immediate visibility
    print(f'\n{"="*60}', file=sys.stderr)
    print(f'AGENT ERROR: {error_msg}', file=sys.stderr)
    print(full_traceback, file=sys.stderr)

    # Also log normally
    logger.error(error_msg)
    logger.error(full_traceback)

    # If it's an ExceptionGroup, log all sub-exceptions
    if hasattr(e, 'exceptions'):
      for i, sub_exc in enumerate(e.exceptions):
        sub_tb = ''.join(traceback.format_exception(type(sub_exc), sub_exc, sub_exc.__traceback__))
        print(f'Sub-exception {i}: {sub_exc}', file=sys.stderr)
        print(sub_tb, file=sys.stderr)
        logger.error(f'Sub-exception {i}: {sub_exc}')
        logger.error(sub_tb)

    print(f'{"="*60}\n', file=sys.stderr)

    yield {
      'type': 'error',
      'error': str(e),
    }
  finally:
    # Always clear auth context when done
    clear_databricks_auth()


# Keep simple aliases for backward compatibility
async def simple_query(project_id: str, message: str) -> AsyncIterator[dict]:
  """Simple stateless query to Claude within a project directory."""
  async for event in stream_agent_response(project_id, message):
    yield event

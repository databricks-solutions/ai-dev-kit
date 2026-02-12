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
  ResultMessage,
  StreamEvent,
  SystemMessage,
  TextBlock,
  ThinkingBlock,
  ToolResultBlock,
  ToolUseBlock,
  UserMessage,
)
from databricks_tools_core.auth import set_databricks_auth, clear_databricks_auth

from .backup_manager import ensure_project_directory as _ensure_project_directory
from .databricks_tools import load_databricks_tools, create_filtered_databricks_server
from .system_prompt import get_system_prompt

logger = logging.getLogger(__name__)

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


def _run_agent_in_fresh_loop(message, options, result_queue, context, is_cancelled_fn, mlflow_experiment=None):
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
        yield {'type': 'user', 'message': {'role': 'user', 'content': message}}

      try:
        msg_count = 0
        async for msg in query(prompt=prompt_generator(), options=options):
          msg_count += 1
          msg_type = type(msg).__name__
          logger.info(f"[AGENT DEBUG] Received message #{msg_count}: {msg_type}")

          # Log more details for specific message types
          if hasattr(msg, 'content'):
            content = msg.content
            if isinstance(content, list):
              block_types = [type(b).__name__ for b in content]
              logger.info(f"[AGENT DEBUG]   Content blocks: {block_types}")
          if hasattr(msg, 'is_error') and msg.is_error:
            logger.error(f"[AGENT DEBUG]   is_error=True")
          if hasattr(msg, 'session_id'):
            logger.info(f"[AGENT DEBUG]   session_id={msg.session_id}")

          # Check for cancellation before processing each message
          if is_cancelled_fn():
            logger.info("Agent cancelled by user request")
            result_queue.put(('cancelled', None))
            return
          result_queue.put(('message', msg))
        logger.info(f"[AGENT DEBUG] query() loop completed normally after {msg_count} messages")
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


async def stream_agent_response(
  project_id: str,
  message: str,
  session_id: str | None = None,
  cluster_id: str | None = None,
  default_catalog: str | None = None,
  default_schema: str | None = None,
  warehouse_id: str | None = None,
  workspace_folder: str | None = None,
  databricks_host: str | None = None,
  databricks_token: str | None = None,
  is_cancelled_fn: callable = None,
  enabled_skills: list[str] | None = None,
  mlflow_experiment_name: str | None = None,
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
      databricks_host: Databricks workspace URL for auth context
      databricks_token: User's Databricks access token for auth context
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

  # Set auth context for this request (enables per-user Databricks auth)
  set_databricks_auth(databricks_host, databricks_token)

  try:
    # Build allowed tools list
    allowed_tools = BUILTIN_TOOLS.copy()

    # Sync project skills directory before running agent
    from .skills_manager import sync_project_skills, get_available_skills, get_allowed_mcp_tools
    sync_project_skills(project_dir, enabled_skills=enabled_skills)

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

    # Load Claude settings for Databricks model serving authentication
    claude_env = _load_claude_settings()

    # Log auth state for debugging
    logger.info(f'Auth state: databricks_host={databricks_host}, token_present={databricks_token is not None and len(str(databricks_token)) > 0}')

    # Ensure Databricks model serving endpoint is used
    # Pass OAuth/PAT token for authentication with Databricks FMAPI
    if databricks_host and databricks_token:
      # Build the Anthropic base URL from Databricks host
      # Format: https://<workspace>/serving-endpoints/anthropic
      host = databricks_host.replace('https://', '').replace('http://', '').rstrip('/')
      anthropic_base_url = f'https://{host}/serving-endpoints/anthropic'

      # Set environment variables for Claude Code subprocess
      # These ensure Claude Code uses Databricks model serving
      # Note: Claude SDK uses ANTHROPIC_API_KEY for authentication
      claude_env['ANTHROPIC_BASE_URL'] = anthropic_base_url
      claude_env['ANTHROPIC_API_KEY'] = databricks_token
      claude_env['ANTHROPIC_AUTH_TOKEN'] = databricks_token

      # Set the model to use (required for Databricks FMAPI)
      anthropic_model = os.environ.get('ANTHROPIC_MODEL', 'databricks-claude-opus-4-5')
      claude_env['ANTHROPIC_MODEL'] = anthropic_model

      # Disable beta headers for Databricks FMAPI compatibility
      claude_env['ANTHROPIC_CUSTOM_HEADERS'] = 'x-databricks-disable-beta-headers: true'

      logger.info(f'Configured Databricks model serving: {anthropic_base_url} with model {anthropic_model}')
      logger.info(f'Claude env vars: BASE_URL={claude_env.get("ANTHROPIC_BASE_URL")}, MODEL={claude_env.get("ANTHROPIC_MODEL")}')

    # Ensure stream timeout is set (1 hour to handle long tool sequences)
    stream_timeout = os.environ.get('CLAUDE_CODE_STREAM_CLOSE_TIMEOUT', '3600000')
    claude_env['CLAUDE_CODE_STREAM_CLOSE_TIMEOUT'] = stream_timeout

    # Stderr callback to capture Claude subprocess output for debugging
    def stderr_callback(line: str):
      logger.debug(f'[Claude stderr] {line.strip()}')
      # Also print to stderr for immediate visibility during development
      print(f'[Claude stderr] {line.strip()}', file=sys.stderr, flush=True)

    options = ClaudeAgentOptions(
      cwd=str(project_dir),
      allowed_tools=allowed_tools,
      permission_mode='bypassPermissions',  # Auto-accept all tools including MCP
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
      args=(message, options, result_queue, ctx, cancel_check, mlflow_experiment),
      daemon=True
    )
    agent_thread.start()

    # Process messages from the queue with keepalive for long operations
    KEEPALIVE_INTERVAL = 15  # seconds - send keepalive if no activity
    last_activity = time.time()

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
              yield {
                'type': 'tool_use',
                'tool_id': block.id,
                'tool_name': block.name,
                'tool_input': block.input,
              }
            elif isinstance(block, ToolResultBlock):
              # Extract content - may be string, list, or complex structure
              content = block.content
              if isinstance(content, list):
                # Handle list of content blocks (e.g., [{'type': 'text', 'text': '...'}])
                texts = []
                for item in content:
                  if isinstance(item, dict) and 'text' in item:
                    texts.append(item['text'])
                  elif isinstance(item, str):
                    texts.append(item)
                  else:
                    texts.append(str(item))
                content = '\n'.join(texts) if texts else str(block.content)
              elif not isinstance(content, str):
                content = str(content)

              # Improve generic "Stream closed" error messages
              if block.is_error and 'Stream closed' in content:
                content = f'Tool execution interrupted: {content}. This may occur when operations exceed timeout limits or when the connection is interrupted. Check backend logs for more details.'
                logger.warning(f'Tool result error (improved): {content}')

              yield {
                'type': 'tool_result',
                'tool_use_id': block.tool_use_id,
                'content': content,
                'is_error': block.is_error,
              }

        elif isinstance(msg, ResultMessage):
          yield {
            'type': 'result',
            'session_id': msg.session_id,
            'duration_ms': msg.duration_ms,
            'total_cost_usd': msg.total_cost_usd,
            'is_error': msg.is_error,
            'num_turns': msg.num_turns,
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
                # Extract content - may be string, list, or complex structure
                content = block.content
                if isinstance(content, list):
                  texts = []
                  for item in content:
                    if isinstance(item, dict) and 'text' in item:
                      texts.append(item['text'])
                    elif isinstance(item, str):
                      texts.append(item)
                    else:
                      texts.append(str(item))
                  content = '\n'.join(texts) if texts else str(block.content)
                elif not isinstance(content, str):
                  content = str(content)

                # Improve generic "Stream closed" error messages
                if block.is_error and 'Stream closed' in content:
                  content = f'Tool execution interrupted: {content}. This may occur when operations exceed timeout limits or when the connection is interrupted. Check backend logs for more details.'
                  logger.warning(f'Tool result error (improved): {content}')

                yield {
                  'type': 'tool_result',
                  'tool_use_id': block.tool_use_id,
                  'content': content,
                  'is_error': block.is_error,
                }
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
          # Pass through other stream events if needed
          elif event_type not in ('content_block_start', 'content_block_stop', 'message_start', 'message_delta', 'message_stop'):
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

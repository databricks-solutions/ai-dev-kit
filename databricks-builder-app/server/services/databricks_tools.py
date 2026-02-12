"""Dynamic tool loader for Databricks tools.

Scans FastMCP tools from databricks-mcp-server and creates
in-process SDK tools for the Claude Code Agent SDK.

Includes async handoff for long-running operations to prevent
Claude connection timeouts. When a tool exceeds SAFE_EXECUTION_THRESHOLD,
execution continues in background and returns an operation ID for polling.
"""

import asyncio
import json
import logging
import threading
import time
from contextvars import copy_context
from typing import Any

from claude_agent_sdk import tool, create_sdk_mcp_server

from .operation_tracker import (
    create_operation,
    complete_operation,
    get_operation,
    list_operations,
)

logger = logging.getLogger(__name__)

# Seconds before switching to async mode to avoid connection timeout
# Anthropic API has ~50s stream idle timeout, we switch early to keep messages flowing
# Lower threshold ensures tool results return quickly, preventing cumulative timeout
SAFE_EXECUTION_THRESHOLD = 10


def load_databricks_tools():
    """Dynamically scan FastMCP tools and create in-process SDK MCP server.

    Returns:
        Tuple of (server_config, tool_names) where:
        - server_config: McpSdkServerConfig for ClaudeAgentOptions.mcp_servers
        - tool_names: List of tool names in mcp__databricks__* format
    """
    sdk_tools, tool_names = _get_all_sdk_tools()

    logger.info(f'Loaded {len(sdk_tools)} Databricks tools: {[n.split("__")[-1] for n in tool_names]}')

    server = create_sdk_mcp_server(name='databricks', tools=sdk_tools)
    return server, tool_names


# Cached SDK tools (loaded once, reused for filtered server creation)
_all_sdk_tools = None
_all_tool_names = None


def _get_all_sdk_tools():
    """Load and cache all SDK tool wrappers.

    Returns:
        Tuple of (sdk_tools, tool_names)
    """
    global _all_sdk_tools, _all_tool_names

    if _all_sdk_tools is not None:
        return _all_sdk_tools, _all_tool_names

    # Import triggers @mcp.tool registration
    from databricks_mcp_server.server import mcp
    from databricks_mcp_server.tools import sql, compute, file, pipelines  # noqa: F401

    sdk_tools = []
    tool_names = []

    # Wrap all Databricks MCP tools
    for name, mcp_tool in mcp._tool_manager._tools.items():
        input_schema = _convert_schema(mcp_tool.parameters)
        sdk_tool = _make_wrapper(name, mcp_tool.description, input_schema, mcp_tool.fn)
        sdk_tools.append(sdk_tool)
        tool_names.append(f'mcp__databricks__{name}')

    # Add operation tracking tools (for async handoff pattern)
    sdk_tools.append(_create_check_operation_status_tool())
    tool_names.append('mcp__databricks__check_operation_status')

    sdk_tools.append(_create_list_operations_tool())
    tool_names.append('mcp__databricks__list_operations')

    _all_sdk_tools = sdk_tools
    _all_tool_names = tool_names
    return sdk_tools, tool_names


def create_filtered_databricks_server(allowed_tool_names: list[str]):
    """Create an MCP server with only the specified tools.

    Used to restrict which Databricks tools the agent can access based on
    which skills are enabled.

    Args:
        allowed_tool_names: List of tool names in mcp__databricks__* format

    Returns:
        Tuple of (server_config, filtered_tool_names)
    """
    all_sdk_tools, all_tool_names = _get_all_sdk_tools()

    allowed_set = set(allowed_tool_names)
    filtered_tools = []
    filtered_names = []

    for sdk_tool, tool_name in zip(all_sdk_tools, all_tool_names):
        if tool_name in allowed_set:
            filtered_tools.append(sdk_tool)
            filtered_names.append(tool_name)

    logger.info(
        f'Created filtered Databricks server: {len(filtered_names)}/{len(all_tool_names)} tools '
        f'({len(all_tool_names) - len(filtered_names)} blocked)'
    )

    server = create_sdk_mcp_server(name='databricks', tools=filtered_tools)
    return server, filtered_names


def _create_check_operation_status_tool():
    """Create the check_operation_status tool for polling async operations."""

    @tool(
        "check_operation_status",
        """Check status of an async operation.

Use this to get results of long-running operations that were moved to
background execution. When a tool takes longer than 30 seconds, it returns
an operation_id instead of blocking. Use this tool to poll for the result.

Args:
    operation_id: The operation ID returned by the long-running tool

Returns:
    - status: 'running', 'completed', or 'failed'
    - tool_name: Name of the original tool
    - result: The operation result (if completed)
    - error: Error message (if failed)
    - elapsed_seconds: Time since operation started
""",
        {"operation_id": str},
    )
    async def check_operation_status(args: dict[str, Any]) -> dict[str, Any]:
        operation_id = args.get("operation_id", "")

        op = get_operation(operation_id)
        if not op:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "status": "not_found",
                                "error": f"Operation {operation_id} not found. It may have expired (TTL: 1 hour) or never existed.",
                            }
                        ),
                    }
                ]
            }

        result = {
            "status": op.status,
            "operation_id": op.operation_id,
            "tool_name": op.tool_name,
            "elapsed_seconds": round(time.time() - op.started_at, 1),
        }

        if op.status == "completed":
            result["result"] = op.result
        elif op.status == "failed":
            result["error"] = op.error

        return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}

    return check_operation_status


def _create_list_operations_tool():
    """Create the list_operations tool for viewing all tracked operations."""

    @tool(
        "list_operations",
        """List all tracked async operations.

Use this to see all operations that are running or recently completed.
Useful for checking what's in progress or finding an operation ID.

Args:
    status: Optional filter - 'running', 'completed', or 'failed'

Returns:
    List of operations with their status and elapsed time
""",
        {"status": str},
    )
    async def list_ops(args: dict[str, Any]) -> dict[str, Any]:
        status_filter = args.get("status")
        if status_filter == "":
            status_filter = None

        ops = list_operations(status_filter)
        return {"content": [{"type": "text", "text": json.dumps(ops, default=str)}]}

    return list_ops


def _convert_schema(json_schema: dict) -> dict[str, type]:
    """Convert JSON schema to SDK simple format: {"param": type}"""
    type_map = {
        'string': str,
        'integer': int,
        'number': float,
        'boolean': bool,
        'array': list,
        'object': dict,
    }
    result = {}

    for param, spec in json_schema.get('properties', {}).items():
        # Handle anyOf (optional types like "string | null")
        if 'anyOf' in spec:
            for opt in spec['anyOf']:
                if opt.get('type') != 'null':
                    result[param] = type_map.get(opt.get('type'), str)
                    break
        else:
            result[param] = type_map.get(spec.get('type'), str)

    return result


def _make_wrapper(name: str, description: str, schema: dict, fn):
    """Create SDK tool wrapper for a FastMCP function.

    The wrapper runs the sync function in a thread pool to avoid
    blocking the async event loop. It also handles JSON string parsing
    for complex types (lists, dicts) that the Claude agent may pass as strings.

    Includes async handoff for long-running operations:
    - Operations completing within SAFE_EXECUTION_THRESHOLD return normally
    - Operations exceeding the threshold switch to background execution
      and return an operation_id for polling via check_operation_status
    """

    @tool(name, description, schema)
    async def wrapper(args: dict[str, Any]) -> dict[str, Any]:
        import sys
        import traceback
        import concurrent.futures

        start_time = time.time()
        print(f'[MCP TOOL] {name} called with args: {args}', file=sys.stderr, flush=True)
        logger.info(f'[MCP] Tool {name} called with args: {args}')
        try:
            # Parse JSON strings for complex types (Claude agent sometimes sends these as strings)
            parsed_args = {}
            for key, value in args.items():
                if isinstance(value, str) and value.strip().startswith(('[', '{')):
                    # Try to parse as JSON if it looks like a list or dict
                    try:
                        parsed_args[key] = json.loads(value)
                        print(f'[MCP TOOL] Parsed {key} from JSON string', file=sys.stderr, flush=True)
                    except json.JSONDecodeError:
                        # Not valid JSON, keep as string
                        parsed_args[key] = value
                else:
                    parsed_args[key] = value

            # FastMCP tools are sync - run in thread pool with heartbeat
            print(f'[MCP TOOL] Running {name} in thread pool with heartbeat...', file=sys.stderr, flush=True)

            # Copy context to propagate Databricks auth contextvars to the thread
            ctx = copy_context()

            def run_in_context():
                """Run the tool function within the copied context."""
                return ctx.run(fn, **parsed_args)

            # Run tool in executor so we can poll for completion with heartbeat
            # Use executor.submit() to get a concurrent.futures.Future (thread-safe)
            # instead of loop.run_in_executor() which returns an asyncio.Future
            loop = asyncio.get_event_loop()
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            cf_future = executor.submit(run_in_context)  # concurrent.futures.Future
            # Wrap in asyncio.Future for async waiting
            future = asyncio.wrap_future(cf_future, loop=loop)

            # Heartbeat every 10 seconds while waiting for the tool to complete
            HEARTBEAT_INTERVAL = 10
            heartbeat_count = 0
            while True:
                try:
                    # Wait for result with timeout
                    result = await asyncio.wait_for(
                        asyncio.shield(future),
                        timeout=HEARTBEAT_INTERVAL
                    )
                    # Tool completed successfully
                    break
                except asyncio.TimeoutError:
                    # Tool still running - emit heartbeat
                    heartbeat_count += 1
                    elapsed = time.time() - start_time
                    print(f'[MCP HEARTBEAT] {name} still running... ({elapsed:.0f}s elapsed, heartbeat #{heartbeat_count})', file=sys.stderr, flush=True)
                    logger.debug(f'[MCP] Heartbeat for {name}: {elapsed:.0f}s elapsed')

                    # Check if we should switch to async mode to avoid connection timeout
                    if elapsed > SAFE_EXECUTION_THRESHOLD:
                        op_id = create_operation(name, parsed_args)
                        print(
                            f'[MCP ASYNC] {name} exceeded {SAFE_EXECUTION_THRESHOLD}s, '
                            f'switching to async mode (operation_id: {op_id})',
                            file=sys.stderr,
                            flush=True,
                        )
                        logger.info(
                            f'[MCP] Tool {name} switched to async mode after {elapsed:.0f}s '
                            f'(operation_id: {op_id})'
                        )

                        # Start background thread to complete the operation
                        # We use threading.Thread instead of asyncio.create_task because
                        # the fresh event loop pattern may not keep tasks alive
                        def complete_in_background(op_id, cf_future, executor):
                            """Background thread to wait for completion and store result."""
                            try:
                                # Block until the future completes (it's already running)
                                # cf_future is a concurrent.futures.Future which is thread-safe
                                result = cf_future.result()  # This blocks
                                complete_operation(op_id, result=result)
                                print(
                                    f'[MCP ASYNC] Operation {op_id} completed successfully',
                                    file=sys.stderr,
                                    flush=True,
                                )
                            except Exception as e:
                                import traceback
                                error_details = traceback.format_exc()
                                complete_operation(op_id, error=str(e))
                                print(
                                    f'[MCP ASYNC] Operation {op_id} failed: {e}',
                                    file=sys.stderr,
                                    flush=True,
                                )
                                print(
                                    f'[MCP ASYNC] Traceback:\n{error_details}',
                                    file=sys.stderr,
                                    flush=True,
                                )
                            finally:
                                executor.shutdown(wait=False)

                        bg_thread = threading.Thread(
                            target=complete_in_background,
                            args=(op_id, cf_future, executor),
                            daemon=True,
                        )
                        bg_thread.start()

                        # Return immediately with operation info
                        return {
                            'content': [
                                {
                                    'type': 'text',
                                    'text': json.dumps({
                                        'status': 'async',
                                        'operation_id': op_id,
                                        'tool_name': name,
                                        'message': (
                                            f'Operation is taking longer than {SAFE_EXECUTION_THRESHOLD}s '
                                            f'and has been moved to background execution. '
                                            f'Use check_operation_status("{op_id}") to poll for results.'
                                        ),
                                        'elapsed_seconds': round(elapsed, 1),
                                    }),
                                }
                            ]
                        }

                    # Continue waiting
                    continue

            elapsed = time.time() - start_time
            result_str = json.dumps(result, default=str)
            print(f'[MCP TOOL] {name} completed in {elapsed:.2f}s, result length: {len(result_str)}', file=sys.stderr, flush=True)
            logger.info(f'[MCP] Tool {name} completed in {elapsed:.2f}s')
            return {'content': [{'type': 'text', 'text': result_str}]}
        except asyncio.CancelledError:
            elapsed = time.time() - start_time
            error_msg = f'Tool execution cancelled after {elapsed:.2f}s (likely due to stream timeout)'
            print(f'[MCP TOOL] {name} CANCELLED: {error_msg}', file=sys.stderr, flush=True)
            logger.error(f'[MCP] Tool {name} cancelled: {error_msg}')
            return {'content': [{'type': 'text', 'text': f'Error: {error_msg}'}], 'is_error': True}
        except TimeoutError as e:
            elapsed = time.time() - start_time
            error_msg = f'Tool execution timed out after {elapsed:.2f}s: {e}'
            print(f'[MCP TOOL] {name} TIMEOUT: {error_msg}', file=sys.stderr, flush=True)
            logger.error(f'[MCP] Tool {name} timeout: {error_msg}')
            return {'content': [{'type': 'text', 'text': f'Error: {error_msg}'}], 'is_error': True}
        except Exception as e:
            elapsed = time.time() - start_time
            error_details = traceback.format_exc()
            error_msg = f'{type(e).__name__}: {str(e)}'
            print(f'[MCP TOOL] {name} FAILED after {elapsed:.2f}s: {error_msg}', file=sys.stderr, flush=True)
            print(f'[MCP TOOL] Stack trace:\n{error_details}', file=sys.stderr, flush=True)
            logger.exception(f'[MCP] Tool {name} failed after {elapsed:.2f}s: {error_msg}')
            return {'content': [{'type': 'text', 'text': f'Error ({type(e).__name__}): {str(e)}\n\nThis error occurred after {elapsed:.2f}s. If this is a long-running operation, it may have exceeded the stream timeout (50s).'}], 'is_error': True}

    return wrapper

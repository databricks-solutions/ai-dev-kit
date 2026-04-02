"""
Middleware for the Databricks MCP Server.

Provides cross-cutting concerns like timeout and error handling for all MCP tool calls.
"""

import anyio
import json
import logging
import traceback

from fastmcp.server.middleware import Middleware, MiddlewareContext, CallNext
from fastmcp.tools.tool import ToolResult
from mcp.types import CallToolRequestParams, TextContent

logger = logging.getLogger(__name__)


class TimeoutHandlingMiddleware(Middleware):
    """Catches errors from any tool and returns structured results.

    This middleware provides two key functions:

    1. **Timeout handling**: When async operations (job runs, pipeline updates,
       resource provisioning) exceed their timeout, converts the exception into
       a JSON response that tells the agent the operation is still in progress
       and should NOT be retried blindly. Without this, agents interpret timeout
       errors as failures and retry — potentially creating duplicate resources.

    2. **Error handling**: Catches all other exceptions and returns them as
       structured JSON responses instead of crashing the MCP server. This ensures
       the server stays up and the agent gets actionable error information.

    Note: For timeouts to work on sync tools, the server must wrap sync functions
    in asyncio.to_thread() (see server.py _patch_tool_decorator_for_async).
    """

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        tool_name = context.message.name
        arguments = context.message.arguments

        try:
            result = await call_next(context)

            # Fix for FastMCP not populating structured_content automatically.
            # When a tool has a return type annotation (e.g., -> Dict[str, Any]),
            # FastMCP generates an outputSchema but doesn't set structured_content.
            # MCP SDK then fails validation: "outputSchema defined but no structured output"
            # We fix this by parsing the JSON text content and setting structured_content.
            if result and not result.structured_content and result.content:
                if len(result.content) == 1 and isinstance(result.content[0], TextContent):
                    try:
                        parsed = json.loads(result.content[0].text)
                        if isinstance(parsed, dict):
                            # Create new ToolResult with structured_content populated
                            result = ToolResult(
                                content=result.content,
                                structured_content=parsed,
                            )
                    except (json.JSONDecodeError, TypeError):
                        pass  # Not valid JSON, leave as-is

            return result

        except TimeoutError as e:
            # In Python 3.11+, asyncio.TimeoutError is an alias for TimeoutError,
            # so this single handler catches both
            logger.warning(
                "Tool '%s' timed out. Returning structured result.",
                tool_name,
            )
            # Don't set structured_content for errors - it would be validated against
            # the tool's outputSchema and fail (error dict doesn't match expected type)
            return ToolResult(
                content=[TextContent(type="text", text=json.dumps({
                    "error": True,
                    "error_type": "timeout",
                    "tool": tool_name,
                    "message": str(e) or "Operation timed out",
                    "action_required": (
                        "Operation may still be in progress. "
                        "Do NOT retry the same call. "
                        "Use the appropriate get/status tool to check current state."
                    ),
                }))]
            )

        except anyio.get_cancelled_exc_class():
            # Re-raise CancelledError so MCP SDK's handler catches it and skips
            # calling message.respond(). If we return a result here, the SDK will
            # try to respond, but the request may already be marked as responded
            # by the cancellation handler, causing an AssertionError crash.
            # See: https://github.com/modelcontextprotocol/python-sdk/pull/1153
            logger.warning(
                "Tool '%s' was cancelled. Re-raising to let MCP SDK handle cleanup.",
                tool_name,
            )
            raise

        except Exception as e:
            # Log the full traceback for debugging
            logger.error(
                "Tool '%s' raised an exception: %s\n%s",
                tool_name,
                str(e),
                traceback.format_exc(),
            )

            # Return error as text content only - don't set structured_content.
            # Setting structured_content would cause MCP SDK to validate it against
            # the tool's outputSchema, which fails (error dict doesn't match expected type).
            return ToolResult(
                content=[TextContent(type="text", text=json.dumps({
                    "error": True,
                    "error_type": type(e).__name__,
                    "tool": tool_name,
                    "message": str(e),
                }))]
            )

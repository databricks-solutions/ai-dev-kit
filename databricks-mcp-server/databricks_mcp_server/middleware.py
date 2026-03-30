"""
Middleware for the Databricks MCP Server.

Provides cross-cutting concerns like timeout and error handling for all MCP tool calls.
"""

import asyncio
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
            return await call_next(context)

        except TimeoutError as e:
            # In Python 3.11+, asyncio.TimeoutError is an alias for TimeoutError,
            # so this single handler catches both
            logger.warning(
                "Tool '%s' timed out. Returning structured result.",
                tool_name,
            )
            return ToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {
                                "error": True,
                                "error_type": "timeout",
                                "tool": tool_name,
                                "message": str(e) or "Operation timed out",
                                "action_required": (
                                    "Operation may still be in progress. "
                                    "Do NOT retry the same call. "
                                    "Use the appropriate get/status tool to check current state."
                                ),
                            }
                        ),
                    )
                ]
            )

        except asyncio.CancelledError:
            logger.warning(
                "Tool '%s' was cancelled. Returning structured result.",
                tool_name,
            )
            return ToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {
                                "error": True,
                                "error_type": "cancelled",
                                "tool": tool_name,
                                "message": "Operation was cancelled by the client",
                            }
                        ),
                    )
                ]
            )

        except Exception as e:
            # Log the full traceback for debugging
            logger.error(
                "Tool '%s' raised an exception: %s\n%s",
                tool_name,
                str(e),
                traceback.format_exc(),
            )

            # Return a structured error response
            error_message = str(e)
            error_type = type(e).__name__

            return ToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {
                                "error": True,
                                "error_type": error_type,
                                "tool": tool_name,
                                "message": error_message,
                            }
                        ),
                    )
                ]
            )

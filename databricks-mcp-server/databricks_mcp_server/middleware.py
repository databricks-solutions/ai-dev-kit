"""
Middleware for the Databricks MCP Server.

Provides cross-cutting concerns like timeout handling for all MCP tool calls.
"""

import json
import logging

from fastmcp.server.middleware import Middleware, MiddlewareContext, CallNext
from fastmcp.tools.tool import ToolResult
from mcp.types import CallToolRequestParams, TextContent

logger = logging.getLogger(__name__)


class TimeoutHandlingMiddleware(Middleware):
    """Catches TimeoutError from any tool and returns a structured result.

    When async operations (job runs, pipeline updates, resource provisioning)
    exceed their timeout, this middleware converts the exception into a JSON
    response that tells the agent the operation is still in progress and
    should NOT be retried blindly.

    Without this middleware, a TimeoutError bubbles up as an MCP error,
    which agents interpret as a failure and retry — potentially creating
    duplicate resources (see GitHub issue #65).
    """

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        try:
            return await call_next(context)
        except TimeoutError as e:
            tool_name = context.message.name
            arguments = context.message.arguments

            logger.warning(
                "Tool '%s' timed out. Returning structured result instead of error.",
                tool_name,
            )

            return ToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {
                                "timed_out": True,
                                "tool": tool_name,
                                "arguments": arguments,
                                "message": str(e),
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

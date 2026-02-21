"""Client for Codex running as MCP server.

Enables Databricks workflows to use Codex AI capabilities through
the MCP protocol.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from databricks_codex.models import MCPToolInfo

logger = logging.getLogger(__name__)


class MCPClientConfig(BaseModel):
    """Configuration for MCP client connection."""

    # Stdio transport (default for Codex)
    command: Optional[str] = Field(None, description="Command to run MCP server")
    args: List[str] = Field(default_factory=list, description="Command arguments")
    env: Dict[str, str] = Field(default_factory=dict, description="Environment variables")

    # HTTP transport (alternative)
    url: Optional[str] = Field(None, description="HTTP URL for MCP server")
    bearer_token_env_var: Optional[str] = Field(
        None, description="Environment variable containing bearer token"
    )

    # Common settings
    timeout: int = Field(default=120, description="Request timeout in seconds")


@dataclass
class MCPError(Exception):
    """MCP protocol error."""

    code: int
    message: str
    data: Optional[Any] = None


class CodexMCPClient:
    """Client to interact with Codex running as MCP server.

    Supports both stdio and HTTP transports as documented in
    Codex CLI reference.

    Example:
        >>> async with CodexMCPClient() as client:
        ...     tools = await client.list_tools()
        ...     result = await client.call_tool("generate_code", {"prompt": "..."})
    """

    def __init__(self, config: Optional[MCPClientConfig] = None):
        """Initialize the MCP client.

        Args:
            config: Connection configuration (defaults to Codex mcp-server via stdio)
        """
        self.config = config or MCPClientConfig(
            command="codex",
            args=["mcp-server"],
        )
        self._process: Optional[asyncio.subprocess.Process] = None
        self._http_client: Optional[Any] = None  # httpx.AsyncClient if available
        self._request_id = 0
        self._connected = False
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None

    async def connect(self) -> None:
        """Establish connection to Codex MCP server.

        Raises:
            ConnectionError: If connection fails
        """
        if self.config.url:
            await self._connect_http()
        else:
            await self._connect_stdio()
        self._connected = True
        logger.info("Connected to Codex MCP server")

    async def _connect_stdio(self) -> None:
        """Connect via stdio transport."""
        if not self.config.command:
            raise ValueError("command required for stdio transport")

        cmd = [self.config.command] + self.config.args

        logger.info(f"Starting Codex MCP server: {' '.join(cmd)}")

        import os

        env = os.environ.copy()
        env.update(self.config.env)

        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        # Start background reader for responses
        self._reader_task = asyncio.create_task(self._read_responses())

        # Send initialize request
        response = await self._send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "databricks-codex",
                    "version": "0.1.0",
                },
            },
        )

        logger.debug(f"MCP initialize response: {response}")

    async def _connect_http(self) -> None:
        """Connect via HTTP transport."""
        try:
            import httpx
        except ImportError:
            raise ImportError("httpx required for HTTP transport: pip install httpx")

        headers: Dict[str, str] = {"Content-Type": "application/json"}

        if self.config.bearer_token_env_var:
            import os

            token = os.environ.get(self.config.bearer_token_env_var)
            if token:
                headers["Authorization"] = f"Bearer {token}"

        self._http_client = httpx.AsyncClient(
            base_url=self.config.url,
            headers=headers,
            timeout=self.config.timeout,
        )

    async def disconnect(self) -> None:
        """Close the connection."""
        self._connected = False

        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        if self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()
            self._process = None

        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

        logger.info("Disconnected from Codex MCP server")

    async def list_tools(self) -> List[MCPToolInfo]:
        """List available tools from the MCP server.

        Returns:
            List of available tools with their schemas

        Example:
            >>> tools = await client.list_tools()
            >>> for tool in tools:
            ...     print(f"{tool.name}: {tool.description}")
        """
        result = await self._send_request("tools/list", {})

        tools = []
        for tool_data in result.get("tools", []):
            tools.append(
                MCPToolInfo(
                    name=tool_data["name"],
                    description=tool_data.get("description", ""),
                    input_schema=tool_data.get("inputSchema", {}),
                )
            )

        return tools

    async def call_tool(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Call an MCP tool.

        Args:
            name: Tool name
            arguments: Tool arguments
            timeout: Optional timeout override

        Returns:
            Tool result as dictionary

        Example:
            >>> result = await client.call_tool(
            ...     "generate_code",
            ...     {"prompt": "Create a hello world function"}
            ... )
        """
        result = await self._send_request(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
            timeout=timeout,
        )

        # Parse content from result
        content = result.get("content", [])
        if content and isinstance(content, list) and len(content) > 0:
            first_content = content[0]
            if isinstance(first_content, dict) and first_content.get("type") == "text":
                text = first_content.get("text", "")
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return {"text": text}

        return result

    async def _send_request(
        self,
        method: str,
        params: Dict[str, Any],
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Send a JSON-RPC request to the MCP server."""
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }

        if self._http_client:
            return await self._send_http(request, timeout)
        else:
            return await self._send_stdio(request, timeout)

    async def _send_stdio(
        self,
        request: Dict[str, Any],
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Send request via stdio."""
        if not self._process or not self._process.stdin:
            raise RuntimeError("Not connected")

        request_id = request["id"]

        # Create future for response
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future

        # Send request
        request_bytes = (json.dumps(request) + "\n").encode()
        self._process.stdin.write(request_bytes)
        await self._process.stdin.drain()

        # Wait for response
        try:
            response = await asyncio.wait_for(
                future,
                timeout=timeout or self.config.timeout,
            )
            return response
        finally:
            self._pending_requests.pop(request_id, None)

    async def _read_responses(self) -> None:
        """Background task to read responses from stdout."""
        if not self._process or not self._process.stdout:
            return

        try:
            while self._connected:
                line = await self._process.stdout.readline()
                if not line:
                    break

                try:
                    response = json.loads(line.decode())
                    request_id = response.get("id")

                    if request_id and request_id in self._pending_requests:
                        future = self._pending_requests[request_id]
                        if "error" in response:
                            error = response["error"]
                            future.set_exception(
                                MCPError(
                                    code=error.get("code", -1),
                                    message=error.get("message", "Unknown error"),
                                    data=error.get("data"),
                                )
                            )
                        else:
                            future.set_result(response.get("result", {}))
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON response: {line}")
                except Exception as e:
                    logger.exception(f"Error processing response: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(f"Reader task error: {e}")

    async def _send_http(
        self,
        request: Dict[str, Any],
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Send request via HTTP."""
        if not self._http_client:
            raise RuntimeError("Not connected")

        response = await self._http_client.post(
            "/",
            json=request,
            timeout=timeout or self.config.timeout,
        )
        response.raise_for_status()

        data = response.json()

        if "error" in data:
            error = data["error"]
            raise MCPError(
                code=error.get("code", -1),
                message=error.get("message", "Unknown error"),
                data=error.get("data"),
            )

        return data.get("result", {})

    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._connected

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *args):
        await self.disconnect()

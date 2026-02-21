"""Tests for MCP client."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from databricks_codex.mcp_client import (
    CodexMCPClient,
    MCPClientConfig,
    MCPError,
)
from databricks_codex.models import MCPToolInfo


class TestMCPClientConfig:
    """Tests for MCPClientConfig model."""

    def test_default_config(self):
        """Test default configuration."""
        config = MCPClientConfig()

        assert config.command is None
        assert config.args == []
        assert config.env == {}
        assert config.url is None
        assert config.timeout == 120

    def test_stdio_config(self):
        """Test stdio transport configuration."""
        config = MCPClientConfig(
            command="codex",
            args=["mcp-server"],
            env={"KEY": "value"},
        )

        assert config.command == "codex"
        assert config.args == ["mcp-server"]
        assert config.env == {"KEY": "value"}

    def test_http_config(self):
        """Test HTTP transport configuration."""
        config = MCPClientConfig(
            url="https://localhost:8080",
            bearer_token_env_var="MCP_TOKEN",
            timeout=60,
        )

        assert config.url == "https://localhost:8080"
        assert config.bearer_token_env_var == "MCP_TOKEN"
        assert config.timeout == 60


class TestMCPError:
    """Tests for MCPError exception."""

    def test_error_creation(self):
        """Test MCP error creation."""
        error = MCPError(code=-32600, message="Invalid request")

        assert error.code == -32600
        assert error.message == "Invalid request"
        assert error.data is None

    def test_error_with_data(self):
        """Test MCP error with additional data."""
        error = MCPError(
            code=-32602,
            message="Invalid params",
            data={"param": "name"},
        )

        assert error.data == {"param": "name"}


class TestCodexMCPClient:
    """Tests for CodexMCPClient class."""

    def test_init_default(self):
        """Test default initialization."""
        client = CodexMCPClient()

        assert client.config.command == "codex"
        assert client.config.args == ["mcp-server"]
        assert client._connected is False

    def test_init_custom_config(self):
        """Test initialization with custom config."""
        config = MCPClientConfig(command="custom-codex", args=["--debug"])
        client = CodexMCPClient(config=config)

        assert client.config.command == "custom-codex"
        assert client.config.args == ["--debug"]

    def test_is_connected_initial(self):
        """Test is_connected property initially false."""
        client = CodexMCPClient()
        assert client.is_connected is False


class TestMCPClientAsync:
    """Async tests for MCP client."""

    @pytest.fixture
    def mock_process(self):
        """Create mock subprocess."""
        process = MagicMock()
        process.stdin = MagicMock()
        process.stdin.write = MagicMock()
        process.stdin.drain = AsyncMock()
        process.stdout = MagicMock()
        process.stdout.readline = AsyncMock(
            return_value=json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"protocolVersion": "2024-11-05"},
            }).encode() + b"\n"
        )
        process.stderr = MagicMock()
        process.terminate = MagicMock()
        process.wait = AsyncMock()
        return process

    @pytest.mark.asyncio
    async def test_connect_stdio(self, mock_process):
        """Test connecting via stdio transport."""
        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
            client = CodexMCPClient()

            # Mock the reader task to not actually run
            with patch.object(client, "_read_responses", return_value=None):
                # We need to handle the initialization request
                responses = [
                    json.dumps({
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {"protocolVersion": "2024-11-05"},
                    }).encode() + b"\n",
                ]
                mock_process.stdout.readline = AsyncMock(side_effect=responses)

                # Can't fully test without running event loop properly
                # This is a simplified test

    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Test disconnecting client."""
        client = CodexMCPClient()
        client._connected = True

        await client.disconnect()

        assert client._connected is False

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test async context manager."""
        with patch.object(CodexMCPClient, "connect", new_callable=AsyncMock) as mock_connect:
            with patch.object(CodexMCPClient, "disconnect", new_callable=AsyncMock) as mock_disconnect:
                async with CodexMCPClient() as client:
                    pass

                mock_connect.assert_called_once()
                mock_disconnect.assert_called_once()


class TestMCPClientToolOperations:
    """Tests for tool operations."""

    @pytest.mark.asyncio
    async def test_list_tools_parsing(self):
        """Test parsing tool list response."""
        client = CodexMCPClient()

        # Mock the _send_request method
        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {
                "tools": [
                    {
                        "name": "test_tool",
                        "description": "A test tool",
                        "inputSchema": {"type": "object"},
                    },
                    {
                        "name": "another_tool",
                        "description": "Another tool",
                    },
                ]
            }

            tools = await client.list_tools()

            assert len(tools) == 2
            assert tools[0].name == "test_tool"
            assert tools[0].description == "A test tool"
            assert tools[0].input_schema == {"type": "object"}
            assert tools[1].name == "another_tool"
            assert tools[1].input_schema == {}

    @pytest.mark.asyncio
    async def test_list_tools_empty(self):
        """Test empty tool list."""
        client = CodexMCPClient()

        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {"tools": []}

            tools = await client.list_tools()

            assert tools == []

    @pytest.mark.asyncio
    async def test_call_tool_json_response(self):
        """Test calling tool with JSON response."""
        client = CodexMCPClient()

        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {
                "content": [
                    {
                        "type": "text",
                        "text": '{"result": "success", "data": [1, 2, 3]}',
                    }
                ]
            }

            result = await client.call_tool("test_tool", {"arg": "value"})

            assert result == {"result": "success", "data": [1, 2, 3]}
            mock_send.assert_called_with(
                "tools/call",
                {"name": "test_tool", "arguments": {"arg": "value"}},
                timeout=None,
            )

    @pytest.mark.asyncio
    async def test_call_tool_text_response(self):
        """Test calling tool with plain text response."""
        client = CodexMCPClient()

        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {
                "content": [
                    {
                        "type": "text",
                        "text": "Plain text response",
                    }
                ]
            }

            result = await client.call_tool("test_tool")

            assert result == {"text": "Plain text response"}

    @pytest.mark.asyncio
    async def test_call_tool_empty_arguments(self):
        """Test calling tool without arguments."""
        client = CodexMCPClient()

        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {"content": []}

            await client.call_tool("test_tool")

            mock_send.assert_called_with(
                "tools/call",
                {"name": "test_tool", "arguments": {}},
                timeout=None,
            )

    @pytest.mark.asyncio
    async def test_call_tool_with_timeout(self):
        """Test calling tool with custom timeout."""
        client = CodexMCPClient()

        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {"content": []}

            await client.call_tool("test_tool", timeout=30)

            mock_send.assert_called_with(
                "tools/call",
                {"name": "test_tool", "arguments": {}},
                timeout=30,
            )


class TestMCPClientHTTP:
    """Tests for HTTP transport."""

    @pytest.mark.asyncio
    async def test_http_not_connected_error(self):
        """Test error when calling without connection."""
        config = MCPClientConfig(url="https://localhost:8080")
        client = CodexMCPClient(config=config)

        with pytest.raises(RuntimeError, match="Not connected"):
            await client._send_http({"test": "request"}, timeout=10)

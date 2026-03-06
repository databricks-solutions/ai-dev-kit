#!/usr/bin/env python
"""
Example: Build an agent that uses the AI Dev Kit MCP Server.

This example shows how to create a simple agent that connects to the
deployed MCP server and uses its tools to interact with Databricks.

Based on the Databricks managed MCP documentation:
https://learn.microsoft.com/en-us/azure/databricks/generative-ai/mcp/managed-mcp

Usage:
    python agent_example.py
"""

import os
import json
import uuid
from typing import Any, Callable, List

from pydantic import BaseModel
import mlflow
from mlflow.pyfunc import ResponsesAgent
from mlflow.types.responses import ResponsesAgentRequest, ResponsesAgentResponse
from databricks_mcp import DatabricksMCPClient
from databricks.sdk import WorkspaceClient


# =============================================================================
# CONFIGURATION - Update these values
# =============================================================================

# Databricks CLI profile for authentication
DATABRICKS_CLI_PROFILE = os.getenv("DATABRICKS_CLI_PROFILE", "DEFAULT")

# LLM endpoint to use for the agent
LLM_ENDPOINT_NAME = os.getenv("LLM_ENDPOINT_NAME", "databricks-claude-sonnet-4-5")

# System prompt for the agent
SYSTEM_PROMPT = """You are a helpful Databricks assistant. You have access to tools that let you:
- Execute SQL queries on Databricks SQL warehouses
- Run Python code on Databricks clusters  
- Manage Unity Catalog objects (catalogs, schemas, tables, volumes)
- Create and manage Databricks Jobs
- Work with AI/BI dashboards
- Interact with Genie spaces
- And more!

Use these tools to help users with their Databricks tasks. Always explain what you're doing and show results clearly."""

# AI Dev Kit MCP Server URL (update after deployment)
AI_DEV_KIT_MCP_URL = os.getenv("AI_DEV_KIT_MCP_URL", "")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _to_chat_messages(msg: dict[str, Any]) -> List[dict]:
    """Convert ResponsesAgent message dict to ChatCompletions format."""
    msg_type = msg.get("type")
    
    if msg_type == "function_call":
        return [{
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": msg["call_id"],
                "type": "function",
                "function": {
                    "name": msg["name"],
                    "arguments": msg["arguments"],
                },
            }],
        }]
    elif msg_type == "message" and isinstance(msg["content"], list):
        return [{
            "role": "assistant" if msg["role"] == "assistant" else msg["role"],
            "content": content["text"],
        } for content in msg["content"]]
    elif msg_type == "function_call_output":
        return [{
            "role": "tool",
            "content": msg["output"],
            "tool_call_id": msg["tool_call_id"],
        }]
    else:
        return [{
            k: v for k, v in msg.items()
            if k in ("role", "content", "name", "tool_calls", "tool_call_id")
        }]


def _make_exec_fn(server_url: str, tool_name: str, ws: WorkspaceClient) -> Callable[..., str]:
    """Create a function that executes an MCP tool."""
    def exec_fn(**kwargs):
        mcp_client = DatabricksMCPClient(server_url=server_url, workspace_client=ws)
        response = mcp_client.call_tool(tool_name, kwargs)
        return "".join([c.text for c in response.content])
    return exec_fn


class ToolInfo(BaseModel):
    """Information about an MCP tool."""
    name: str
    spec: dict
    exec_fn: Callable


def _fetch_tool_infos(ws: WorkspaceClient, server_url: str) -> List[ToolInfo]:
    """Fetch available tools from an MCP server."""
    print(f"Listing tools from MCP server {server_url}")
    infos: List[ToolInfo] = []
    
    mcp_client = DatabricksMCPClient(server_url=server_url, workspace_client=ws)
    mcp_tools = mcp_client.list_tools()
    
    for t in mcp_tools:
        schema = t.inputSchema.copy()
        if "properties" not in schema:
            schema["properties"] = {}
        
        spec = {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": schema,
            },
        }
        infos.append(ToolInfo(
            name=t.name,
            spec=spec,
            exec_fn=_make_exec_fn(server_url, t.name, ws)
        ))
    
    return infos


# =============================================================================
# AGENT CLASS
# =============================================================================

class AIDevKitAgent(ResponsesAgent):
    """
    Agent that uses the AI Dev Kit MCP Server for Databricks operations.
    
    This agent can execute SQL, run Python code, manage Unity Catalog,
    and perform many other Databricks operations through MCP tools.
    """
    
    def _call_llm(self, history: List[dict], ws: WorkspaceClient, tool_infos: List[ToolInfo]):
        """Send history to LLM and get response."""
        client = ws.serving_endpoints.get_open_ai_client()
        
        flat_msgs = []
        for msg in history:
            flat_msgs.extend(_to_chat_messages(msg))
        
        return client.chat.completions.create(
            model=LLM_ENDPOINT_NAME,
            messages=flat_msgs,
            tools=[ti.spec for ti in tool_infos] if tool_infos else None,
        )
    
    def predict(self, request: ResponsesAgentRequest) -> ResponsesAgentResponse:
        """Process a request and return a response."""
        ws = WorkspaceClient(profile=DATABRICKS_CLI_PROFILE)
        
        # Build initial history
        history: List[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        for inp in request.input:
            history.append(inp.model_dump())
        
        # Get available tools from MCP server
        mcp_server_urls = []
        if AI_DEV_KIT_MCP_URL:
            mcp_server_urls.append(AI_DEV_KIT_MCP_URL)
        
        tool_infos = []
        for url in mcp_server_urls:
            tool_infos.extend(_fetch_tool_infos(ws, url))
        
        tools_dict = {ti.name: ti for ti in tool_infos}
        
        # Call LLM
        llm_resp = self._call_llm(history, ws, tool_infos)
        raw_choice = llm_resp.choices[0].message.to_dict()
        raw_choice["id"] = uuid.uuid4().hex
        history.append(raw_choice)
        
        tool_calls = raw_choice.get("tool_calls") or []
        
        if tool_calls:
            # Execute tool call
            fc = tool_calls[0]
            name = fc["function"]["name"]
            args = json.loads(fc["function"]["arguments"])
            
            try:
                tool_info = tools_dict[name]
                result = tool_info.exec_fn(**args)
            except Exception as e:
                result = f"Error invoking {name}: {e}"
            
            # Append tool output
            history.append({
                "type": "function_call_output",
                "role": "tool",
                "id": uuid.uuid4().hex,
                "tool_call_id": fc["id"],
                "output": result,
            })
            
            # Get final response
            followup = self._call_llm(history, ws, tool_infos=[]).choices[0].message.to_dict()
            followup["id"] = uuid.uuid4().hex
            assistant_text = followup.get("content", "")
            
            return ResponsesAgentResponse(
                output=[{
                    "id": uuid.uuid4().hex,
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": assistant_text}],
                }],
                custom_outputs=request.custom_inputs,
            )
        
        # No tool calls - return direct response
        assistant_text = raw_choice.get("content", "")
        return ResponsesAgentResponse(
            output=[{
                "id": uuid.uuid4().hex,
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": assistant_text}],
            }],
            custom_outputs=request.custom_inputs,
        )


# Register the agent with MLflow
mlflow.models.set_model(AIDevKitAgent())


# =============================================================================
# MAIN - Test the agent locally
# =============================================================================

if __name__ == "__main__":
    if not AI_DEV_KIT_MCP_URL:
        print("ERROR: Set AI_DEV_KIT_MCP_URL environment variable")
        print("Example: export AI_DEV_KIT_MCP_URL='https://your-app.apps.databricks.com/mcp'")
        exit(1)
    
    print("Testing AI Dev Kit Agent...")
    print(f"MCP Server: {AI_DEV_KIT_MCP_URL}")
    print(f"LLM Endpoint: {LLM_ENDPOINT_NAME}")
    print()
    
    # Test query
    req = ResponsesAgentRequest(
        input=[{"role": "user", "content": "List the available Unity Catalog catalogs"}]
    )
    
    agent = AIDevKitAgent()
    resp = agent.predict(req)
    
    print("Response:")
    for item in resp.output:
        if item.get("type") == "message":
            for content in item.get("content", []):
                print(content.get("text", ""))

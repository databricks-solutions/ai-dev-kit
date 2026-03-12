#!/usr/bin/env python
"""
Test connection to the deployed AI Dev Kit MCP Server.

This script validates that your MCP server is deployed and accessible,
then lists all available tools.

Usage:
    python test_connection.py --profile <databricks-profile> --app-url <app-url>
"""

import argparse
import sys


def test_connection(profile: str, app_url: str):
    """Test connection to the MCP server and list tools."""
    try:
        from databricks_mcp import DatabricksMCPClient
        from databricks.sdk import WorkspaceClient
    except ImportError:
        print("ERROR: Required packages not installed.")
        print("Install with: pip install databricks-sdk databricks-mcp")
        sys.exit(1)
    
    print(f"Connecting to MCP server...")
    print(f"  Profile: {profile}")
    print(f"  App URL: {app_url}")
    print()
    
    # Initialize workspace client
    workspace_client = WorkspaceClient(profile=profile)
    
    # Construct MCP server URL
    mcp_server_url = f"{app_url.rstrip('/')}/mcp"
    print(f"MCP Server URL: {mcp_server_url}")
    print()
    
    # Connect to MCP server
    mcp_client = DatabricksMCPClient(
        server_url=mcp_server_url,
        workspace_client=workspace_client
    )
    
    # List available tools
    print("Listing available tools...")
    tools = mcp_client.list_tools()
    
    print(f"\nDiscovered {len(tools)} tools:\n")
    print("-" * 60)
    
    # Group tools by category (based on naming convention)
    categories = {}
    for tool in tools:
        # Extract category from tool name (e.g., "execute_sql" -> "sql")
        parts = tool.name.split("_")
        if len(parts) > 1:
            category = parts[-1] if parts[0] in ["execute", "run", "get", "list", "create", "delete", "update"] else parts[0]
        else:
            category = "general"
        
        if category not in categories:
            categories[category] = []
        categories[category].append(tool)
    
    for category, cat_tools in sorted(categories.items()):
        print(f"\n{category.upper()}:")
        for tool in cat_tools:
            desc = tool.description[:60] + "..." if len(tool.description) > 60 else tool.description
            print(f"  - {tool.name}: {desc}")
    
    print("\n" + "-" * 60)
    print("\nConnection successful!")
    print("\nExample usage in your agent code:")
    print()
    print(f'''
from databricks_mcp import DatabricksMCPClient
from databricks.sdk import WorkspaceClient

ws = WorkspaceClient(profile="{profile}")
mcp = DatabricksMCPClient(server_url="{mcp_server_url}", workspace_client=ws)

# Execute SQL
result = mcp.call_tool("execute_sql", {{
    "sql": "SELECT current_date()",
    "warehouse_id": "your-warehouse-id"
}})
print(result.content)
''')


def main():
    parser = argparse.ArgumentParser(
        description="Test connection to AI Dev Kit MCP Server"
    )
    parser.add_argument(
        "--profile", "-p",
        required=True,
        help="Databricks CLI profile name"
    )
    parser.add_argument(
        "--app-url", "-u",
        required=True,
        help="Databricks App URL (e.g., https://abc123.apps.databricks.com)"
    )
    
    args = parser.parse_args()
    test_connection(args.profile, args.app_url)


if __name__ == "__main__":
    main()

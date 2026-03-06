#!/usr/bin/env python
"""
AI Dev Kit MCP Server - Main entry point

Serves the ai-dev-kit MCP server over HTTP/SSE transport for use with
Databricks managed MCP clients and AI agents.

Includes health check endpoints for browser testing.
"""

import os
import sys
import json
import logging

# Add parent directory to sys.path for local package imports
app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CORSMiddleware:
    """
    Middleware to handle CORS preflight requests (OPTIONS).
    Required for browser-based MCP clients like the Databricks AI Playground.
    """
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            method = scope.get("method", "")
            
            # Handle CORS preflight requests
            # Allow all common headers used by Databricks UI and MCP clients
            if method == "OPTIONS":
                headers = [
                    [b"access-control-allow-origin", b"*"],
                    [b"access-control-allow-methods", b"GET, POST, OPTIONS, DELETE, PUT, PATCH"],
                    [b"access-control-allow-headers", b"*"],  # Allow all headers
                    [b"access-control-expose-headers", b"*"],
                    [b"access-control-max-age", b"86400"],
                    [b"content-length", b"0"],
                ]
                await send({
                    "type": "http.response.start",
                    "status": 204,
                    "headers": headers,
                })
                await send({"type": "http.response.body", "body": b""})
                return
            
            # For other requests, add CORS headers to response
            async def send_with_cors(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append([b"access-control-allow-origin", b"*"])
                    headers.append([b"access-control-allow-methods", b"GET, POST, OPTIONS, DELETE, PUT, PATCH"])
                    headers.append([b"access-control-allow-headers", b"*"])
                    headers.append([b"access-control-expose-headers", b"*"])
                    message = {**message, "headers": headers}
                await send(message)
            
            await self.app(scope, receive, send_with_cors)
            return
        
        await self.app(scope, receive, send)


class PATAuthMiddleware:
    """
    Middleware to accept PAT tokens for authentication.
    Validates PAT tokens against Databricks API when platform OAuth is bypassed.
    """
    
    def __init__(self, app):
        self.app = app
        self._validated_tokens = {}  # Cache validated tokens
        self._workspace_host = os.getenv("DATABRICKS_HOST", "")
    
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            auth_header = headers.get(b"authorization", b"").decode()
            
            # Check if it's a PAT token (starts with "dapi")
            if auth_header.startswith("Bearer dapi"):
                token = auth_header.replace("Bearer ", "")
                
                # Validate the token (with caching)
                if token not in self._validated_tokens:
                    is_valid = await self._validate_pat(token)
                    self._validated_tokens[token] = is_valid
                
                if not self._validated_tokens[token]:
                    # Return 401 for invalid PAT
                    response_body = json.dumps({"error": "Invalid PAT token"}).encode()
                    await send({
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [[b"content-type", b"application/json"]],
                    })
                    await send({"type": "http.response.body", "body": response_body})
                    return
                
                # Valid PAT - continue to app
                logger.info("PAT token validated successfully")
        
        await self.app(scope, receive, send)
    
    async def _validate_pat(self, token: str) -> bool:
        """Validate PAT token by calling Databricks API."""
        import httpx
        try:
            # Get workspace host from environment or config
            host = self._workspace_host
            if not host:
                # Try to get from Databricks SDK config
                try:
                    from databricks.sdk import WorkspaceClient
                    ws = WorkspaceClient()
                    host = ws.config.host
                except:
                    # Fallback: extract from app URL
                    host = os.getenv("DATABRICKS_WORKSPACE_URL", "")
            
            if not host:
                logger.warning("No workspace host configured, accepting PAT token")
                return True
            
            # Validate by calling /api/2.0/preview/scim/v2/Me
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{host}/api/2.0/preview/scim/v2/Me",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10.0
                )
                return resp.status_code == 200
        except Exception as e:
            logger.warning(f"PAT validation failed: {e}, accepting token")
            return True  # Fail open for now


class MCPFallbackMiddleware:
    """
    Middleware to handle GET requests to /mcp that don't have proper SSE Accept header.
    This provides a JSON fallback for proxies that probe the endpoint.
    """
    
    def __init__(self, app, skills_count: int = 0):
        self.app = app
        self.skills_count = skills_count
    
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            method = scope.get("method", "")
            
            # Check if this is a GET to /mcp without proper Accept header
            if method == "GET" and path in ("/mcp", "/mcp/"):
                headers = dict(scope.get("headers", []))
                accept = headers.get(b"accept", b"").decode()
                
                # If no text/event-stream in Accept, return JSON info
                if "text/event-stream" not in accept:
                    logger.info(f"GET /mcp without SSE Accept header - returning JSON info")
                    response_body = json.dumps({
                        "jsonrpc": "2.0",
                        "result": {
                            "name": "ai-dev-kit-mcp",
                            "version": "1.0.0",
                            "protocolVersion": "2024-11-05",
                            "capabilities": {
                                "tools": {"listChanged": True},
                                "resources": {},
                                "prompts": {}
                            },
                            "serverInfo": {
                                "name": "AI Dev Kit MCP Server",
                                "skills_count": self.skills_count
                            }
                        }
                    }).encode()
                    
                    await send({
                        "type": "http.response.start",
                        "status": 200,
                        "headers": [
                            [b"content-type", b"application/json"],
                            [b"content-length", str(len(response_body)).encode()],
                        ],
                    })
                    await send({
                        "type": "http.response.body",
                        "body": response_body,
                    })
                    return
        
        await self.app(scope, receive, send)


async def get_tools_async(mcp) -> list:
    """Get tools list using async MCP methods."""
    try:
        # Use the public async get_tools() API
        tools_dict = await mcp.get_tools()
        if isinstance(tools_dict, dict):
            return [{"name": name, "description": t.description[:100] if hasattr(t, 'description') and t.description else ""} 
                    for name, t in tools_dict.items()]
    except Exception as e:
        logger.warning(f"get_tools() failed: {e}")
    
    try:
        # Fallback: Try _tool_manager._tools (sync access)
        if hasattr(mcp, '_tool_manager') and hasattr(mcp._tool_manager, '_tools'):
            tools = mcp._tool_manager._tools
            return [{"name": name, "description": t.description[:100] if hasattr(t, 'description') and t.description else ""} 
                    for name, t in tools.items()]
    except Exception as e:
        logger.debug(f"_tool_manager fallback failed: {e}")
    
    return []


def main():
    """Start the MCP server with health endpoints."""
    import uvicorn
    from starlette.responses import JSONResponse, HTMLResponse
    
    port = int(os.getenv("PORT", "8000"))
    
    logger.info(f"Starting AI Dev Kit MCP Server on port {port}")
    
    try:
        # Import the MCP server
        from databricks_mcp_server.server import mcp
        
        # Get skills list (this is file-based, so works synchronously)
        skills = []
        try:
            from databricks_mcp_server.tools.skills import _get_skills_dir
            skills_path = _get_skills_dir()
            logger.info(f"Skills directory: {skills_path}")
            logger.info(f"Skills dir exists: {skills_path.exists()}")
            
            if skills_path.exists():
                for skill_dir in sorted(skills_path.iterdir()):
                    if skill_dir.is_dir() and not skill_dir.name.startswith('.') and skill_dir.name != 'TEMPLATE':
                        skill_file = skill_dir / "SKILL.md"
                        if skill_file.exists():
                            # Parse frontmatter for description
                            content = skill_file.read_text()
                            description = ""
                            if content.startswith('---'):
                                parts = content.split('---', 2)
                                if len(parts) >= 3:
                                    for line in parts[1].strip().split('\n'):
                                        if line.startswith('description:'):
                                            description = line.split(':', 1)[1].strip().strip('"\'')
                                            break
                            skills.append({
                                "name": skill_dir.name,
                                "description": description[:100] if description else "No description"
                            })
            logger.info(f"Loaded {len(skills)} skills")
        except Exception as e:
            logger.warning(f"Could not load skills: {e}")
            import traceback
            traceback.print_exc()
        
        # Build skills HTML for home page
        skills_html = ""
        for s in skills:
            skills_html += f'<div class="skill"><code>{s["name"]}</code> - {s["description"]}</div>'
        
        # Home page with dynamic tool loading via JavaScript
        home_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>AI Dev Kit MCP Server</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                       max-width: 900px; margin: 50px auto; padding: 20px; }}
                h1 {{ color: #1b3a57; }}
                h2 {{ color: #2c5282; margin-top: 30px; }}
                .endpoint {{ background: #f5f5f5; padding: 10px; margin: 10px 0; border-radius: 5px; }}
                code {{ background: #e0e0e0; padding: 2px 6px; border-radius: 3px; font-size: 13px; }}
                .section {{ max-height: 350px; overflow-y: auto; border: 1px solid #ddd; 
                           border-radius: 5px; padding: 10px; margin: 10px 0; }}
                .tool, .skill {{ padding: 8px 5px; border-bottom: 1px solid #eee; }}
                .tool:last-child, .skill:last-child {{ border-bottom: none; }}
                .columns {{ display: flex; gap: 20px; }}
                .column {{ flex: 1; }}
                pre {{ background: #f8f8f8; padding: 15px; border-radius: 5px; overflow-x: auto; }}
                .stats {{ display: flex; gap: 20px; margin: 20px 0; }}
                .stat {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                        color: white; padding: 20px; border-radius: 10px; text-align: center; flex: 1; }}
                .stat-number {{ font-size: 36px; font-weight: bold; }}
                .stat-label {{ font-size: 14px; opacity: 0.9; }}
                .loading {{ color: #999; font-style: italic; }}
            </style>
        </head>
        <body>
            <h1>AI Dev Kit MCP Server</h1>
            <p>Model Context Protocol server providing tools and skills for Databricks development.</p>
            
            <div class="stats">
                <div class="stat">
                    <div class="stat-number" id="tools-count">...</div>
                    <div class="stat-label">Tools</div>
                </div>
                <div class="stat">
                    <div class="stat-number">{len(skills)}</div>
                    <div class="stat-label">Skills</div>
                </div>
            </div>
            
            <h2>Endpoints</h2>
            <div class="endpoint"><strong>GET /</strong> - This page</div>
            <div class="endpoint"><strong>GET /health</strong> - Health check (JSON)</div>
            <div class="endpoint"><strong>GET /tools</strong> - List all tools (JSON)</div>
            <div class="endpoint"><strong>GET /skills</strong> - List all skills (JSON)</div>
            <div class="endpoint"><strong>POST /mcp</strong> - MCP protocol endpoint (for MCP clients)</div>
            
            <div class="columns">
                <div class="column">
                    <h2>Available Tools (<span id="tools-header-count">...</span>)</h2>
                    <div class="section" id="tools-list">
                        <div class="loading">Loading tools...</div>
                    </div>
                </div>
                <div class="column">
                    <h2>Available Skills ({len(skills)})</h2>
                    <div class="section">
                        {skills_html if skills_html else '<div class="skill">No skills loaded</div>'}
                    </div>
                </div>
            </div>
            
            <script>
                // Fetch tools dynamically after page load
                fetch('/tools')
                    .then(r => r.json())
                    .then(data => {{
                        document.getElementById('tools-count').textContent = data.count;
                        document.getElementById('tools-header-count').textContent = data.count;
                        const toolsList = document.getElementById('tools-list');
                        if (data.tools && data.tools.length > 0) {{
                            toolsList.innerHTML = data.tools
                                .sort((a, b) => a.name.localeCompare(b.name))
                                .map(t => `<div class="tool"><code>${{t.name}}</code></div>`)
                                .join('');
                        }} else {{
                            toolsList.innerHTML = '<div class="tool">No tools loaded</div>';
                        }}
                    }})
                    .catch(err => {{
                        document.getElementById('tools-count').textContent = '?';
                        document.getElementById('tools-header-count').textContent = '?';
                        document.getElementById('tools-list').innerHTML = '<div class="tool">Error loading tools</div>';
                    }});
            </script>
        </body>
        </html>
        """
        
        # Add custom routes to the MCP server using fastmcp's custom_route decorator
        @mcp.custom_route("/", methods=["GET"])
        async def home_route(request):
            return HTMLResponse(home_html)
        
        @mcp.custom_route("/health", methods=["GET"])
        async def health_route(request):
            tools = await get_tools_async(mcp)
            return JSONResponse({
                "status": "healthy",
                "server": "ai-dev-kit-mcp",
                "tools_count": len(tools),
                "skills_count": len(skills),
                "mcp_endpoint": "/mcp"
            })
        
        @mcp.custom_route("/tools", methods=["GET"])
        async def tools_route(request):
            tools = await get_tools_async(mcp)
            return JSONResponse({"tools": tools, "count": len(tools)})
        
        @mcp.custom_route("/skills", methods=["GET"])
        async def skills_route(request):
            return JSONResponse({"skills": skills, "count": len(skills)})
        
        # Create the HTTP app with MCP at /mcp (standard Databricks MCP path)
        app = mcp.http_app(path="/mcp")
        
        # Wrap with middleware to handle GET /mcp fallback for proxies
        app = MCPFallbackMiddleware(app, skills_count=len(skills))
        
        # Wrap with PAT auth middleware to accept PAT tokens from UC HTTP connections
        app = PATAuthMiddleware(app)
        
        # Wrap with CORS middleware to handle browser preflight requests
        app = CORSMiddleware(app)
        
        logger.info(f"MCP Server initialized with {len(skills)} skills")
        logger.info("Endpoints: / (info), /health, /tools, /skills, /mcp (MCP protocol)")
        
        uvicorn.run(app, host="0.0.0.0", port=port)
        
    except ImportError as e:
        logger.error(f"Failed to import: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

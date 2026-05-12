"""MCP Gateway — exposes Databricks tools over HTTP for Genie Code and MCP clients.

When ENABLE_MCP_GATEWAY=true, the builder app mounts this gateway at /mcp,
turning the app into a dual-purpose deployment: visual builder UI at / and
MCP server at /mcp.

The gateway reuses the same FastMCP server instance and tool registrations
that the in-process Claude agent uses — no duplicate tool loading.

Architecture (external → internal):
    POST /mcp       → MCP protocol endpoint (Streamable HTTP)
    GET  /mcp/health → JSON health check
    GET  /mcp/tools  → JSON tool listing
    GET  /mcp/skills → JSON skill listing
    GET  /mcp/info   → HTML info page

Design matches the reference app at databricks-mcp-app/server/main.py:
    - mcp.http_app(path="/mcp") for the protocol endpoint
    - Pure ASGI middleware for CORS, PAT auth, and diagnostic routes
    - Lifespan events pass through to the MCP ASGI app
"""

import asyncio
import json
import logging
import os
from pathlib import Path

import httpx
from starlette.responses import HTMLResponse, JSONResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ASGI Middleware (scoped to /mcp* only — does not affect the main app)
# ---------------------------------------------------------------------------


class GatewayCORSMiddleware:
    """Permissive CORS for browser-based MCP clients (AI Playground, Genie Code).

    Scoped to the MCP gateway sub-app only; the main FastAPI app keeps its own
    stricter CORS policy.  Non-HTTP scopes (lifespan, websocket) pass through.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if scope.get("method") == "OPTIONS":
            headers = [
                [b"access-control-allow-origin", b"*"],
                [b"access-control-allow-methods", b"GET, POST, OPTIONS, DELETE, PUT, PATCH"],
                [b"access-control-allow-headers", b"*"],
                [b"access-control-expose-headers", b"*"],
                [b"access-control-max-age", b"86400"],
                [b"content-length", b"0"],
            ]
            await send({"type": "http.response.start", "status": 204, "headers": headers})
            await send({"type": "http.response.body", "body": b""})
            return

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


class PATAuthMiddleware:
    """Accept Databricks PAT tokens for authentication.

    UC HTTP connections may send a PAT instead of platform OAuth.
    Validates by calling the SCIM /Me endpoint, with a per-process cache.
    Non-HTTP scopes pass through.
    """

    def __init__(self, app):
        self.app = app
        self._validated_tokens: dict[str, bool] = {}
        self._workspace_host = os.getenv("DATABRICKS_HOST", "")

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            auth_header = headers.get(b"authorization", b"").decode()

            if auth_header.startswith("Bearer dapi"):
                token = auth_header.replace("Bearer ", "")

                if token not in self._validated_tokens:
                    self._validated_tokens[token] = await self._validate_pat(token)

                if not self._validated_tokens[token]:
                    body = json.dumps({"error": "Invalid PAT token"}).encode()
                    await send({
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [[b"content-type", b"application/json"]],
                    })
                    await send({"type": "http.response.body", "body": body})
                    return

        await self.app(scope, receive, send)

    async def _validate_pat(self, token: str) -> bool:
        host = self._workspace_host
        if not host:
            try:
                from databricks.sdk import WorkspaceClient
                host = WorkspaceClient().config.host
            except Exception:
                host = os.getenv("DATABRICKS_WORKSPACE_URL", "")
        if not host:
            logger.warning("No workspace host configured, accepting PAT token")
            return True
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{host}/api/2.0/preview/scim/v2/Me",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10.0,
                )
                return resp.status_code == 200
        except Exception as e:
            logger.warning(f"PAT validation failed: {e}, accepting token")
            return True


class MCPFallbackMiddleware:
    """Return JSON server info for GET /mcp probes without an SSE Accept header.

    Proxies and health-check bots hit GET /mcp; without this middleware they
    would get a confusing SSE error.  Non-HTTP scopes pass through.
    """

    def __init__(self, app, *, skills_count: int = 0):
        self.app = app
        self.skills_count = skills_count

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            method = scope.get("method", "")

            if method == "GET" and path in ("/mcp", "/mcp/"):
                headers = dict(scope.get("headers", []))
                accept = headers.get(b"accept", b"").decode()

                if "text/event-stream" not in accept:
                    body = json.dumps({
                        "jsonrpc": "2.0",
                        "result": {
                            "name": "databricks-builder-mcp",
                            "version": "1.0.0",
                            "protocolVersion": "2024-11-05",
                            "capabilities": {"tools": {"listChanged": True}},
                            "serverInfo": {
                                "name": "Databricks Builder MCP Gateway",
                                "skills_count": self.skills_count,
                            },
                        },
                    }).encode()
                    await send({
                        "type": "http.response.start",
                        "status": 200,
                        "headers": [
                            [b"content-type", b"application/json"],
                            [b"content-length", str(len(body)).encode()],
                        ],
                    })
                    await send({"type": "http.response.body", "body": body})
                    return

        await self.app(scope, receive, send)


class DiagnosticRoutesMiddleware:
    """Handle GET /mcp/health, /mcp/tools, /mcp/skills, /mcp/info.

    Intercepts diagnostic GET routes before they reach the MCP protocol handler.
    Everything else (POST /mcp, DELETE /mcp, lifespan, etc.) passes through.
    """

    def __init__(self, app, *, mcp_server, skills: list[dict]):
        self.app = app
        self.mcp_server = mcp_server
        self.skills = skills

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") != "GET":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        if path == "/mcp/health":
            tools = await _get_tools(self.mcp_server)
            resp = JSONResponse({
                "status": "healthy",
                "server": "databricks-builder-mcp-gateway",
                "tools_count": len(tools),
                "skills_count": len(self.skills),
                "mcp_endpoint": "/mcp",
            })
            await resp(scope, receive, send)
        elif path == "/mcp/tools":
            tools = await _get_tools(self.mcp_server)
            resp = JSONResponse({"tools": tools, "count": len(tools)})
            await resp(scope, receive, send)
        elif path == "/mcp/skills":
            resp = JSONResponse({"skills": self.skills, "count": len(self.skills)})
            await resp(scope, receive, send)
        elif path == "/mcp/info":
            resp = HTMLResponse(_build_info_html(len(self.skills)))
            await resp(scope, receive, send)
        else:
            await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_skills_metadata() -> list[dict]:
    """Read skill names and descriptions from the skills directory."""
    skills = []
    try:
        from databricks_mcp_server.tools.skills import _get_skills_dir
        skills_path = _get_skills_dir()
    except Exception:
        skills_path = Path(os.getenv("SKILLS_DIR", "./skills"))

    if not skills_path.exists():
        return skills

    for skill_dir in sorted(skills_path.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name.startswith(".") or skill_dir.name == "TEMPLATE":
            continue
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue
        description = ""
        content = skill_file.read_text()
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].strip().split("\n"):
                    if line.startswith("description:"):
                        description = line.split(":", 1)[1].strip().strip("\"'")
                        break
        skills.append({"name": skill_dir.name, "description": description[:120] or "No description"})
    return skills


async def _get_tools(mcp_server) -> list[dict]:
    """Get the list of registered tools from the FastMCP server.

    FastMCP 3.x exposes list_tools() returning a list of FunctionTool objects.
    FastMCP 2.x used _tool_manager._tools (dict). We try both.
    """
    if hasattr(mcp_server, "list_tools"):
        try:
            tools_list = await mcp_server.list_tools()
            return [
                {"name": t.name, "description": (t.description or "")[:120]}
                for t in tools_list
            ]
        except Exception as e:
            logger.warning(f"list_tools() failed: {e}")

    try:
        tm = getattr(mcp_server, "_tool_manager", None)
        if tm and hasattr(tm, "_tools"):
            return [
                {"name": name, "description": (t.description or "")[:120]}
                for name, t in tm._tools.items()
            ]
    except Exception as e:
        logger.warning(f"_tool_manager fallback failed: {e}")

    return []


# ---------------------------------------------------------------------------
# Lifespan helpers — start/stop the MCP ASGI app's session manager
# ---------------------------------------------------------------------------


async def start_mcp_lifespan(mcp_asgi_app):
    """Start the MCP ASGI app's lifespan via synthetic ASGI events.

    The StreamableHTTPSessionManager requires lifespan.startup to initialize
    its task group.  Returns (task, shutdown_event) for later cleanup.
    """
    startup_complete = asyncio.Event()
    startup_failed = False
    shutdown_event = asyncio.Event()

    async def fake_receive():
        if not startup_complete.is_set():
            return {"type": "lifespan.startup"}
        await shutdown_event.wait()
        return {"type": "lifespan.shutdown"}

    async def fake_send(message):
        nonlocal startup_failed
        msg_type = message.get("type", "")
        if msg_type == "lifespan.startup.complete":
            startup_complete.set()
        elif msg_type == "lifespan.startup.failed":
            startup_failed = True
            startup_complete.set()
        # shutdown.complete is handled by the task ending

    scope = {"type": "lifespan", "asgi": {"version": "3.0"}}
    task = asyncio.create_task(mcp_asgi_app(scope, fake_receive, fake_send))

    await startup_complete.wait()

    if startup_failed:
        task.cancel()
        raise RuntimeError("MCP gateway lifespan startup failed")

    logger.info("MCP Gateway lifespan started (StreamableHTTPSessionManager initialized)")
    return task, shutdown_event


async def stop_mcp_lifespan(task, shutdown_event):
    """Gracefully shut down the MCP ASGI app's lifespan."""
    shutdown_event.set()
    try:
        await asyncio.wait_for(task, timeout=5.0)
    except asyncio.TimeoutError:
        logger.warning("MCP Gateway lifespan shutdown timed out, cancelling")
        task.cancel()
    except asyncio.CancelledError:
        pass
    logger.info("MCP Gateway lifespan stopped")


# ---------------------------------------------------------------------------
# Gateway factory
# ---------------------------------------------------------------------------


def create_mcp_gateway():
    """Create the MCP gateway ASGI app.

    Returns (gateway_app, mcp_asgi_app) where:
    - gateway_app: the fully-wrapped ASGI app to handle /mcp* requests
    - mcp_asgi_app: the inner FastMCP ASGI app (needs lifespan management)

    The caller MUST start the mcp_asgi_app's lifespan via start_mcp_lifespan()
    before the gateway can handle MCP protocol requests.
    """
    from databricks_mcp_server.server import mcp as mcp_server

    skills = _load_skills_metadata()
    logger.info(f"MCP Gateway: loaded {len(skills)} skill metadata entries")

    # Core MCP ASGI app — protocol endpoint at /mcp (matching reference app)
    mcp_asgi = mcp_server.http_app(
        path="/mcp",
        stateless_http=True,
    )

    # Middleware stack (innermost → outermost):
    #   mcp_asgi → DiagnosticRoutes → MCPFallback → PATAuth → CORS
    # All middleware passes non-HTTP scopes (lifespan) straight through.
    app = DiagnosticRoutesMiddleware(mcp_asgi, mcp_server=mcp_server, skills=skills)
    app = MCPFallbackMiddleware(app, skills_count=len(skills))
    app = PATAuthMiddleware(app)
    app = GatewayCORSMiddleware(app)

    logger.info("MCP Gateway created — /mcp (protocol), /mcp/health, /mcp/tools, /mcp/skills, /mcp/info")
    return app, mcp_asgi


# ---------------------------------------------------------------------------
# Info HTML page (served at /mcp/info)
# ---------------------------------------------------------------------------


def _build_info_html(skills_count: int) -> str:
    return f"""\
<!DOCTYPE html>
<html>
<head>
  <title>Builder App — MCP Gateway</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
           max-width: 800px; margin: 50px auto; padding: 20px; color: #1a1a1a; }}
    h1 {{ color: #1b3a57; }}
    h2 {{ color: #2c5282; margin-top: 28px; }}
    .ep {{ background: #f5f5f5; padding: 10px 14px; margin: 8px 0; border-radius: 6px; }}
    code {{ background: #e0e0e0; padding: 2px 6px; border-radius: 3px; font-size: 13px; }}
    .stats {{ display: flex; gap: 20px; margin: 20px 0; }}
    .stat {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
             color: white; padding: 20px; border-radius: 10px; text-align: center; flex: 1; }}
    .stat-number {{ font-size: 36px; font-weight: bold; }}
    .stat-label {{ font-size: 14px; opacity: 0.9; }}
    .section {{ max-height: 300px; overflow-y: auto; border: 1px solid #ddd;
                border-radius: 6px; padding: 10px; margin: 10px 0; }}
    .tool {{ padding: 6px 4px; border-bottom: 1px solid #eee; }}
    .tool:last-child {{ border-bottom: none; }}
    .loading {{ color: #999; font-style: italic; }}
  </style>
</head>
<body>
  <h1>Databricks Builder App — MCP Gateway</h1>
  <p>This MCP endpoint exposes Databricks tools for Genie Code, AI Playground, and other MCP clients.</p>
  <div class="stats">
    <div class="stat"><div class="stat-number" id="tc">…</div><div class="stat-label">Tools</div></div>
    <div class="stat"><div class="stat-number">{skills_count}</div><div class="stat-label">Skills</div></div>
  </div>
  <h2>Endpoints</h2>
  <div class="ep"><strong>POST /mcp</strong> — MCP protocol (Streamable HTTP)</div>
  <div class="ep"><strong>GET /mcp/health</strong> — Health check (JSON)</div>
  <div class="ep"><strong>GET /mcp/tools</strong> — List tools (JSON)</div>
  <div class="ep"><strong>GET /mcp/skills</strong> — List skills (JSON)</div>
  <div class="ep"><strong>GET /mcp/info</strong> — This page</div>
  <h2>Available Tools (<span id="thc">…</span>)</h2>
  <div class="section" id="tl"><div class="loading">Loading…</div></div>
  <script>
    fetch('/mcp/tools').then(r=>r.json()).then(d=>{{
      document.getElementById('tc').textContent=d.count;
      document.getElementById('thc').textContent=d.count;
      const el=document.getElementById('tl');
      if(d.tools&&d.tools.length){{
        const items=d.tools.sort((a,b)=>a.name.localeCompare(b.name))
          .map(t=>{{const div=document.createElement('div');div.className='tool';
            const c=document.createElement('code');c.textContent=t.name;div.appendChild(c);return div;}});
        el.replaceChildren(...items);
      }}else{{ el.textContent='No tools loaded'; }}
    }}).catch(()=>{{
      document.getElementById('tc').textContent='?';
      document.getElementById('tl').textContent='Error loading tools';
    }});
  </script>
</body>
</html>"""

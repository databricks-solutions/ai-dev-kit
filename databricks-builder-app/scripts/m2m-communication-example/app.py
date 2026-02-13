"""Demo Databricks App that calls the Builder App as an agent-as-a-service.

This minimal FastAPI application demonstrates the full app-to-app integration
pattern: authenticating via M2M OAuth, invoking the agent, and streaming
the response back to a simple HTML frontend.

Environment variables:
  BUILDER_APP_URL: Base URL of the deployed builder app
                   (e.g. https://workspace.cloud.databricks.com/apps/builder-app)
  DATABRICKS_TOKEN: (optional) PAT for local development
"""

import json
import logging
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from builder_client import BuilderClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title='Builder App Demo Client')

# ---------------------------------------------------------------------------
# Client singleton
# ---------------------------------------------------------------------------

_client: BuilderClient | None = None
# Cache project ID so we don't create one per request
_project_id: str | None = None


def get_client() -> BuilderClient:
  """Get or create the BuilderClient singleton."""
  global _client
  if _client is None:
    url = os.environ.get('BUILDER_APP_URL', '')
    if not url:
      raise RuntimeError(
        'BUILDER_APP_URL environment variable is required. '
        'Set it to the base URL of the deployed builder app.'
      )
    _client = BuilderClient(builder_app_url=url)
  return _client


async def get_or_create_project() -> str:
  """Get or create a shared demo project."""
  global _project_id
  if _project_id:
    return _project_id

  client = get_client()

  # Try to find an existing demo project
  try:
    projects = await client.list_projects()
    for p in projects:
      if p.get('name') == 'M2M Communication Example':
        _project_id = p['id']
        logger.info(f'Reusing existing project: {_project_id}')
        return _project_id
  except Exception as e:
    logger.warning(f'Could not list projects: {e}')

  # Create a new one
  project = await client.create_project('M2M Communication Example')
  _project_id = project['id']
  logger.info(f'Created demo project: {_project_id}')
  return _project_id


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class AskRequest(BaseModel):
  """Request body for the /ask endpoint."""

  message: str


class AskResponse(BaseModel):
  """Response body from the /ask endpoint."""

  response: str
  execution_id: str
  conversation_id: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get('/', response_class=HTMLResponse)
async def index() -> str:
  """Serve the demo UI."""
  return HTML_PAGE


@app.post('/ask', response_model=AskResponse)
async def ask(body: AskRequest) -> AskResponse:
  """Send a message to the builder app agent and return the full response.

  Creates a project and conversation automatically, invokes the agent,
  streams the response to completion, and returns the full text.
  """
  client = get_client()
  project_id = await get_or_create_project()

  # Invoke the agent (creates a new conversation automatically)
  try:
    invoke_result = await client.invoke_agent(
      project_id=project_id,
      message=body.message,
    )
  except Exception as e:
    logger.error(f'Failed to invoke agent: {e}')
    raise HTTPException(status_code=502, detail=f'Failed to invoke agent: {e}')

  execution_id = invoke_result['execution_id']
  conversation_id = invoke_result['conversation_id']

  # Collect the streamed response
  full_text = ''
  try:
    async for event in client.stream_events(execution_id):
      event_type = event.get('type', '')
      if event_type == 'text_delta':
        full_text += event.get('text', '')
      elif event_type == 'text':
        full_text += event.get('text', '')
      elif event_type == 'error':
        raise HTTPException(
          status_code=502,
          detail=f'Agent error: {event.get("error", "Unknown")}',
        )
  except HTTPException:
    raise
  except Exception as e:
    logger.error(f'Streaming failed: {e}')
    raise HTTPException(status_code=502, detail=f'Streaming failed: {e}')

  return AskResponse(
    response=full_text,
    execution_id=execution_id,
    conversation_id=conversation_id,
  )


@app.get('/stream/{execution_id}')
async def stream_proxy(execution_id: str) -> StreamingResponse:
  """Proxy SSE events from the builder app to the demo frontend.

  This allows the frontend to display streaming output in real time
  instead of waiting for the full response.
  """
  client = get_client()

  async def generate():
    try:
      async for event in client.stream_events(execution_id):
        yield f'data: {json.dumps(event)}\n\n'
      yield 'data: [DONE]\n\n'
    except Exception as e:
      yield f'data: {json.dumps({"type": "error", "error": str(e)})}\n\n'
      yield 'data: [DONE]\n\n'

  return StreamingResponse(
    generate(),
    media_type='text/event-stream',
    headers={
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
      'X-Accel-Buffering': 'no',
    },
  )


@app.post('/invoke')
async def invoke(body: AskRequest) -> dict:
  """Invoke the agent and return the execution_id for streaming.

  Use this with GET /stream/{execution_id} for real-time streaming.
  """
  client = get_client()
  project_id = await get_or_create_project()

  try:
    result = await client.invoke_agent(
      project_id=project_id,
      message=body.message,
    )
    return result
  except Exception as e:
    logger.error(f'Failed to invoke agent: {e}')
    raise HTTPException(status_code=502, detail=f'Failed to invoke agent: {e}')


@app.get('/health')
async def health() -> dict:
  """Health check — also pings the builder app."""
  client = get_client()
  try:
    builder_health = await client.health()
  except Exception as e:
    builder_health = {'status': 'unreachable', 'error': str(e)}

  return {
    'status': 'healthy',
    'builder_app': builder_health,
  }


# ---------------------------------------------------------------------------
# HTML UI
# ---------------------------------------------------------------------------

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Builder App Demo Client</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: #0f1117;
      color: #e4e4e7;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 2rem 1rem;
    }
    .container {
      width: 100%;
      max-width: 760px;
    }
    h1 {
      font-size: 1.5rem;
      font-weight: 600;
      margin-bottom: 0.25rem;
    }
    .subtitle {
      color: #a1a1aa;
      font-size: 0.875rem;
      margin-bottom: 2rem;
    }
    .input-row {
      display: flex;
      gap: 0.5rem;
      margin-bottom: 1.5rem;
    }
    textarea {
      flex: 1;
      background: #1c1c24;
      border: 1px solid #2e2e3a;
      border-radius: 8px;
      color: #e4e4e7;
      padding: 0.75rem 1rem;
      font-size: 0.9375rem;
      font-family: inherit;
      resize: vertical;
      min-height: 48px;
      max-height: 200px;
    }
    textarea:focus { outline: none; border-color: #6366f1; }
    button {
      background: #6366f1;
      color: #fff;
      border: none;
      border-radius: 8px;
      padding: 0.75rem 1.5rem;
      font-size: 0.9375rem;
      font-weight: 500;
      cursor: pointer;
      white-space: nowrap;
      align-self: flex-end;
    }
    button:hover { background: #4f46e5; }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    .response-box {
      background: #1c1c24;
      border: 1px solid #2e2e3a;
      border-radius: 8px;
      padding: 1.25rem;
      min-height: 120px;
      white-space: pre-wrap;
      word-break: break-word;
      font-size: 0.9375rem;
      line-height: 1.6;
    }
    .response-box.empty {
      color: #52525b;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .status {
      font-size: 0.8125rem;
      color: #a1a1aa;
      margin-bottom: 0.5rem;
    }
    .status.error { color: #f87171; }
    .spinner {
      display: inline-block;
      width: 12px;
      height: 12px;
      border: 2px solid #6366f1;
      border-top-color: transparent;
      border-radius: 50%;
      animation: spin 0.6s linear infinite;
      margin-right: 6px;
      vertical-align: middle;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>
  <div class="container">
    <h1>Builder App Demo Client</h1>
    <p class="subtitle">App-to-app integration &mdash; this app calls the Builder App's agent API</p>

    <div class="input-row">
      <textarea id="message" rows="2" placeholder="Ask the agent something..."></textarea>
      <button id="send" onclick="sendMessage()">Send</button>
    </div>

    <div id="status" class="status"></div>
    <div id="response" class="response-box empty">Response will appear here</div>
  </div>

  <script>
    async function sendMessage() {
      const msg = document.getElementById('message').value.trim();
      if (!msg) return;

      const btn = document.getElementById('send');
      const status = document.getElementById('status');
      const resp = document.getElementById('response');

      btn.disabled = true;
      resp.textContent = '';
      resp.classList.remove('empty');
      status.className = 'status';
      status.innerHTML = '<span class="spinner"></span> Invoking agent...';

      try {
        // Step 1: invoke the agent
        const invokeResp = await fetch('/invoke', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: msg }),
        });

        if (!invokeResp.ok) {
          const err = await invokeResp.json();
          throw new Error(err.detail || 'Invoke failed');
        }

        const { execution_id } = await invokeResp.json();
        status.innerHTML = '<span class="spinner"></span> Streaming response...';

        // Step 2: stream events via SSE
        const evtSource = new EventSource('/stream/' + execution_id);
        evtSource.onmessage = (e) => {
          if (e.data === '[DONE]') {
            evtSource.close();
            status.textContent = 'Done';
            btn.disabled = false;
            return;
          }

          try {
            const event = JSON.parse(e.data);
            if (event.type === 'text_delta') {
              resp.textContent += event.text;
            } else if (event.type === 'text') {
              resp.textContent += event.text;
            } else if (event.type === 'error') {
              status.className = 'status error';
              status.textContent = 'Error: ' + event.error;
              evtSource.close();
              btn.disabled = false;
            } else if (event.type === 'tool_use') {
              status.innerHTML = '<span class="spinner"></span> Using tool: ' + event.tool_name;
            } else if (event.type === 'stream.completed') {
              evtSource.close();
              status.textContent = 'Done';
              btn.disabled = false;
            }
          } catch (parseErr) {
            // ignore unparseable lines
          }
        };

        evtSource.onerror = () => {
          evtSource.close();
          if (!resp.textContent) {
            status.className = 'status error';
            status.textContent = 'Connection lost';
          } else {
            status.textContent = 'Done';
          }
          btn.disabled = false;
        };

      } catch (err) {
        status.className = 'status error';
        status.textContent = 'Error: ' + err.message;
        btn.disabled = false;
      }
    }

    // Allow Ctrl+Enter to send
    document.getElementById('message').addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        sendMessage();
      }
    });
  </script>
</body>
</html>
"""

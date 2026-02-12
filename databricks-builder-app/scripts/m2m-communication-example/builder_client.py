"""HTTP client for the Databricks Builder App API.

Handles authentication, REST calls, and SSE streaming for app-to-app
communication. Designed for use by other Databricks Apps that want to
call the builder app as an "agent-as-a-service".

Auth strategy:
  - In Databricks Apps: uses WorkspaceClient().config.authenticate() to get
    Bearer tokens from the calling app's auto-provisioned service principal.
  - In local dev: uses an explicit token or DATABRICKS_TOKEN env var.
"""

import json
import logging
import os
import time
from typing import Any, AsyncGenerator, Optional

import httpx

logger = logging.getLogger(__name__)

# Token refresh buffer: refresh 10 min before expiry (tokens last ~60 min)
_TOKEN_REFRESH_BUFFER = 600


class BuilderClient:
  """Async HTTP client for the Builder App API.

  Args:
      builder_app_url: Base URL of the builder app (e.g. https://workspace.cloud.databricks.com/apps/my-app)
      token: Explicit Bearer token (for local dev). Falls back to DATABRICKS_TOKEN env var.
  """

  def __init__(self, builder_app_url: str, token: Optional[str] = None) -> None:
    self.base_url = builder_app_url.rstrip('/')
    self._explicit_token = token or os.environ.get('DATABRICKS_TOKEN')

    # Cached auth headers from WorkspaceClient (for Databricks Apps runtime)
    self._auth_headers_cache: Optional[dict[str, str]] = None
    self._auth_expires_at: float = 0

  async def _get_auth_headers(self) -> dict[str, str]:
    """Get authorization headers for requests to the builder app.

    Auth priority:
      1. Explicit token (constructor param or DATABRICKS_TOKEN env var)
      2. Remote workspace credentials (BUILDER_DATABRICKS_HOST + token or SP creds)
      3. Same-workspace auto-auth via WorkspaceClient().config.authenticate()

    Returns:
        Dict with Authorization header.
    """
    # 1. Local dev / explicit token path
    if self._explicit_token:
      return {'Authorization': f'Bearer {self._explicit_token}'}

    # Check cached headers (applies to both remote and same-workspace paths)
    now = time.time()
    if self._auth_headers_cache and now < self._auth_expires_at:
      return self._auth_headers_cache

    # Import here to avoid hard dependency when using explicit token
    from databricks.sdk import WorkspaceClient

    # 2. Remote workspace credentials (for cross-workspace calls)
    remote_host = os.environ.get('BUILDER_DATABRICKS_HOST')
    if remote_host:
      remote_token = os.environ.get('BUILDER_DATABRICKS_TOKEN')
      client_id = os.environ.get('BUILDER_DATABRICKS_CLIENT_ID')
      client_secret = os.environ.get('BUILDER_DATABRICKS_CLIENT_SECRET')

      if remote_token:
        # Static token — no caching needed, return directly
        logger.info('Using BUILDER_DATABRICKS_TOKEN for remote workspace auth')
        return {'Authorization': f'Bearer {remote_token}'}
      elif client_id and client_secret:
        # SP credentials for the remote workspace — generate OAuth token
        logger.info(f'Refreshing auth via SP credentials for {remote_host}')
        client = WorkspaceClient(
          host=remote_host,
          client_id=client_id,
          client_secret=client_secret,
        )
        headers = client.config.authenticate()
        self._auth_headers_cache = headers
        self._auth_expires_at = now + 3000
        return headers

    # 3. Same-workspace auto-auth (default)
    logger.info('Refreshing auth headers via WorkspaceClient.config.authenticate()')
    client = WorkspaceClient()
    headers = client.config.authenticate()

    self._auth_headers_cache = headers
    # Cache for 50 min (tokens typically last 60 min)
    self._auth_expires_at = now + 3000
    return headers

  def _api_url(self, path: str) -> str:
    """Build full API URL from a relative path."""
    return f'{self.base_url}/api{path}'

  # ---------------------------------------------------------------------------
  # REST methods
  # ---------------------------------------------------------------------------

  async def health(self) -> dict[str, Any]:
    """Check builder app health.

    Returns:
        Health status dict, e.g. {"status": "healthy"}
    """
    async with httpx.AsyncClient() as client:
      resp = await client.get(self._api_url('/health'), timeout=10)
      resp.raise_for_status()
      return resp.json()

  async def list_projects(self) -> list[dict[str, Any]]:
    """List all projects for the authenticated user.

    Returns:
        List of project dicts.
    """
    headers = await self._get_auth_headers()
    async with httpx.AsyncClient() as client:
      resp = await client.get(self._api_url('/projects'), headers=headers, timeout=30)
      resp.raise_for_status()
      return resp.json()

  async def create_project(self, name: str) -> dict[str, Any]:
    """Create a new project.

    Args:
        name: Project name.

    Returns:
        Created project dict.
    """
    headers = await self._get_auth_headers()
    async with httpx.AsyncClient() as client:
      resp = await client.post(
        self._api_url('/projects'),
        headers=headers,
        json={'name': name},
        timeout=30,
      )
      resp.raise_for_status()
      return resp.json()

  async def create_conversation(
    self, project_id: str, title: str = 'New Conversation'
  ) -> dict[str, Any]:
    """Create a new conversation in a project.

    Args:
        project_id: Project ID.
        title: Conversation title.

    Returns:
        Created conversation dict.
    """
    headers = await self._get_auth_headers()
    async with httpx.AsyncClient() as client:
      resp = await client.post(
        self._api_url(f'/projects/{project_id}/conversations'),
        headers=headers,
        json={'title': title},
        timeout=30,
      )
      resp.raise_for_status()
      return resp.json()

  async def get_conversation(
    self, project_id: str, conversation_id: str
  ) -> dict[str, Any]:
    """Get a conversation with its messages.

    Args:
        project_id: Project ID.
        conversation_id: Conversation ID.

    Returns:
        Conversation dict with messages.
    """
    headers = await self._get_auth_headers()
    async with httpx.AsyncClient() as client:
      resp = await client.get(
        self._api_url(f'/projects/{project_id}/conversations/{conversation_id}'),
        headers=headers,
        timeout=30,
      )
      resp.raise_for_status()
      return resp.json()

  async def invoke_agent(
    self,
    project_id: str,
    message: str,
    conversation_id: Optional[str] = None,
    cluster_id: Optional[str] = None,
    warehouse_id: Optional[str] = None,
    default_catalog: Optional[str] = None,
    default_schema: Optional[str] = None,
    workspace_folder: Optional[str] = None,
  ) -> dict[str, Any]:
    """Invoke the agent and get an execution_id for streaming.

    Args:
        project_id: Project to run the agent in.
        message: User message to send.
        conversation_id: Existing conversation ID (creates new if omitted).
        cluster_id: Databricks cluster for code execution.
        warehouse_id: SQL warehouse for queries.
        default_catalog: Default Unity Catalog.
        default_schema: Default schema.
        workspace_folder: Workspace folder for file uploads.

    Returns:
        Dict with execution_id and conversation_id.
    """
    headers = await self._get_auth_headers()
    body: dict[str, Any] = {
      'project_id': project_id,
      'message': message,
    }
    if conversation_id:
      body['conversation_id'] = conversation_id
    if cluster_id:
      body['cluster_id'] = cluster_id
    if warehouse_id:
      body['warehouse_id'] = warehouse_id
    if default_catalog:
      body['default_catalog'] = default_catalog
    if default_schema:
      body['default_schema'] = default_schema
    if workspace_folder:
      body['workspace_folder'] = workspace_folder

    async with httpx.AsyncClient() as client:
      resp = await client.post(
        self._api_url('/invoke_agent'),
        headers=headers,
        json=body,
        timeout=30,
      )
      resp.raise_for_status()
      return resp.json()

  async def stop_execution(self, execution_id: str) -> dict[str, Any]:
    """Stop/cancel an active execution.

    Args:
        execution_id: Execution to cancel.

    Returns:
        Stop result dict.
    """
    headers = await self._get_auth_headers()
    async with httpx.AsyncClient() as client:
      resp = await client.post(
        self._api_url(f'/stop_stream/{execution_id}'),
        headers=headers,
        timeout=30,
      )
      resp.raise_for_status()
      return resp.json()

  # ---------------------------------------------------------------------------
  # SSE streaming
  # ---------------------------------------------------------------------------

  async def stream_events(
    self, execution_id: str, last_timestamp: Optional[float] = None
  ) -> AsyncGenerator[dict[str, Any], None]:
    """Stream SSE events from an active execution.

    Handles automatic reconnection when the builder app sends
    stream.reconnect events (every ~50 seconds).

    Args:
        execution_id: Execution to stream events from.
        last_timestamp: Resume cursor (timestamp of last received event).

    Yields:
        Parsed event dicts from the SSE stream.
    """
    cursor = last_timestamp or 0.0

    while True:
      headers = await self._get_auth_headers()
      reconnect = False

      async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=65.0)) as client:
        async with client.stream(
          'POST',
          self._api_url(f'/stream_progress/{execution_id}'),
          headers=headers,
          json={'last_event_timestamp': cursor},
        ) as resp:
          resp.raise_for_status()

          async for line in resp.aiter_lines():
            if not line.startswith('data: '):
              continue

            payload = line[6:]  # strip "data: " prefix

            # Terminal signal
            if payload == '[DONE]':
              return

            try:
              event = json.loads(payload)
            except json.JSONDecodeError:
              logger.warning(f'Failed to parse SSE payload: {payload[:100]}')
              continue

            event_type = event.get('type', '')

            if event_type == 'stream.reconnect':
              # Update cursor and reconnect
              cursor = event.get('last_timestamp', cursor)
              reconnect = True
              break

            if event_type == 'stream.completed':
              yield event
              return

            yield event

      # If we got a reconnect signal, loop to reconnect
      if not reconnect:
        return

  async def ask(
    self,
    project_id: str,
    message: str,
    conversation_id: Optional[str] = None,
    **kwargs: Any,
  ) -> str:
    """Convenience: invoke agent and collect the full text response.

    Args:
        project_id: Project to run the agent in.
        message: User message to send.
        conversation_id: Existing conversation ID (creates new if omitted).
        **kwargs: Additional arguments passed to invoke_agent.

    Returns:
        The agent's full text response.
    """
    result = await self.invoke_agent(
      project_id=project_id,
      message=message,
      conversation_id=conversation_id,
      **kwargs,
    )
    execution_id = result['execution_id']

    full_text = ''
    async for event in self.stream_events(execution_id):
      event_type = event.get('type', '')
      if event_type == 'text_delta':
        full_text += event.get('text', '')
      elif event_type == 'text':
        full_text += event.get('text', '')
      elif event_type == 'error':
        raise RuntimeError(f'Agent error: {event.get("error", "Unknown")}')

    return full_text

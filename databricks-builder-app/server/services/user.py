"""User service for getting the current authenticated user and token.

In production (Databricks Apps):
- User email is available in the X-Forwarded-User header
- Access token is available in the X-Forwarded-Access-Token header

In development, we fall back to environment variables and WorkspaceClient.
"""

import asyncio
import logging
import os
from typing import Optional

from databricks.sdk import WorkspaceClient
from fastapi import Request

logger = logging.getLogger(__name__)

# Cache for dev user to avoid repeated API calls
_dev_user_cache: Optional[str] = None
_workspace_url_cache: Optional[str] = None


def _is_local_development() -> bool:
  """Check if running in local development mode."""
  return os.getenv('ENV', 'development') == 'development'


def _has_oauth_credentials() -> bool:
  """Check if OAuth credentials (SP) are configured in environment."""
  return bool(os.environ.get('DATABRICKS_CLIENT_ID') and os.environ.get('DATABRICKS_CLIENT_SECRET'))


def _get_workspace_client() -> WorkspaceClient:
  """Get a WorkspaceClient with proper auth handling.

  In Databricks Apps, explicitly uses OAuth M2M to avoid conflicts with other auth methods.
  """
  if _has_oauth_credentials():
    # Explicitly configure OAuth M2M to prevent auth conflicts
    return WorkspaceClient(
      host=os.environ.get('DATABRICKS_HOST', ''),
      client_id=os.environ.get('DATABRICKS_CLIENT_ID', ''),
      client_secret=os.environ.get('DATABRICKS_CLIENT_SECRET', ''),
    )
  # Development mode - use default SDK auth
  return WorkspaceClient()


async def get_current_user(request: Request) -> str:
  """Get the current user's email from the request.

  In production (Databricks Apps), extracts user from X-Forwarded-User header.
  In development, calls WorkspaceClient.current_user.me() and caches the result.

  Args:
      request: FastAPI Request object

  Returns:
      User's email address

  Raises:
      ValueError: If user cannot be determined
  """
  # Try to get user from header first (production mode)
  user = request.headers.get('X-Forwarded-User')
  if user:
    logger.debug(f'Got user from X-Forwarded-User header: {user}')
    return user

  # Fall back to WorkspaceClient for development
  if _is_local_development():
    return await _get_dev_user()

  # Production without header - this shouldn't happen
  raise ValueError(
    'No X-Forwarded-User header found and not in development mode. '
    'Ensure the app is deployed with user authentication enabled.'
  )


async def get_current_token(request: Request) -> str | None:
  """Get the current user's Databricks access token for workspace operations.

  In production (Databricks Apps), returns None to use SP OAuth credentials
  from environment variables (set by Databricks Apps automatically).
  In development, uses DATABRICKS_TOKEN env var.

  Args:
      request: FastAPI Request object

  Returns:
      Access token string, or None to use default credentials
  """
  # In production, return None to let WorkspaceClient use SP OAuth from env
  if not _is_local_development():
    logger.debug('Production mode: using SP OAuth credentials from environment')
    return None

  # Fall back to env var for development
  token = os.getenv('DATABRICKS_TOKEN')
  if token:
    logger.debug('Got token from DATABRICKS_TOKEN env var')
    return token

  return None


async def get_fmapi_token(request: Request) -> str | None:
  """Get a token for Databricks Foundation Model API (Claude endpoints).

  In production (Databricks Apps), generates a fresh OAuth token using the
  Service Principal credentials from environment variables.
  In development, uses DATABRICKS_TOKEN env var.

  Args:
      request: FastAPI Request object

  Returns:
      Access token string for FMAPI authentication
  """
  # In production, generate OAuth token from SP credentials
  if not _is_local_development():
    try:
      # Use helper that explicitly configures OAuth M2M to avoid auth conflicts
      client = _get_workspace_client()
      # Call the config's authenticate method to get a fresh token
      headers = client.config.authenticate()
      if headers and 'Authorization' in headers:
        # Extract token from "Bearer <token>" format
        auth_header = headers['Authorization']
        if auth_header.startswith('Bearer '):
          token = auth_header[7:]
          logger.info(f'Got FMAPI token from SP OAuth (length: {len(token)})')
          return token
    except Exception as e:
      logger.warning(f'Failed to get SP OAuth token: {e}')

  # Fall back to env var for development
  token = os.getenv('DATABRICKS_TOKEN')
  if token:
    logger.debug('Got FMAPI token from DATABRICKS_TOKEN env var')
    return token

  return None


async def _get_dev_user() -> str:
  """Get user email from WorkspaceClient in development mode."""
  global _dev_user_cache

  if _dev_user_cache is not None:
    logger.debug(f'Using cached dev user: {_dev_user_cache}')
    return _dev_user_cache

  logger.info('Fetching current user from WorkspaceClient')

  # Run the synchronous SDK call in a thread pool to avoid blocking
  user_email = await asyncio.to_thread(_fetch_user_from_workspace)

  _dev_user_cache = user_email
  logger.info(f'Cached dev user: {user_email}')

  return user_email


def _fetch_user_from_workspace() -> str:
  """Synchronous helper to fetch user from WorkspaceClient."""
  try:
    # Use helper that properly handles OAuth vs PAT auth
    client = _get_workspace_client()
    me = client.current_user.me()

    if not me.user_name:
      raise ValueError('WorkspaceClient returned user without email/user_name')

    return me.user_name

  except Exception as e:
    logger.error(f'Failed to get current user from WorkspaceClient: {e}')
    raise ValueError(f'Could not determine current user: {e}') from e


def get_workspace_url() -> str:
  """Get the Databricks workspace URL.

  Uses DATABRICKS_HOST env var, or fetches from WorkspaceClient config.
  Result is cached for subsequent calls.

  Returns:
      Workspace URL (e.g., https://company-dev.cloud.databricks.com)
  """
  global _workspace_url_cache

  if _workspace_url_cache is not None:
    return _workspace_url_cache

  # Try env var first
  host = os.getenv('DATABRICKS_HOST')
  if host:
    _workspace_url_cache = host.rstrip('/')
    logger.debug(f'Got workspace URL from env: {_workspace_url_cache}')
    return _workspace_url_cache

  # Fall back to WorkspaceClient config (just reads from config, not a network call)
  try:
    client = _get_workspace_client()
    _workspace_url_cache = client.config.host.rstrip('/')
    logger.debug(f'Got workspace URL from WorkspaceClient: {_workspace_url_cache}')
    return _workspace_url_cache
  except Exception as e:
    logger.error(f'Failed to get workspace URL: {e}')
    return ''

"""Warehouses service for listing Databricks SQL warehouses with caching."""

import asyncio
import logging
import time
from itertools import islice
from threading import Lock
from typing import Optional

from databricks_tools_core.auth import get_workspace_client

logger = logging.getLogger(__name__)

# Cache configuration
CACHE_TTL_SECONDS = 300  # 5 minutes
_cache: dict = {
  'warehouses': None,
  'last_updated': 0,
  'is_refreshing': False,
}
_cache_lock = Lock()


def _fetch_warehouses_sync(limit: int = 50, timeout: int = 15) -> list[dict]:
  """Synchronously fetch SQL warehouses from Databricks using SDK.

  Returns warehouses sorted by priority:
  1. Serverless + running (highest priority)
  2. Serverless + not running
  3. Running + "shared" in name
  4. Running (without "shared")
  5. Not running + "shared" in name
  6. Everything else

  Args:
      limit: Maximum number of warehouses to return
      timeout: Timeout in seconds for the API call
  """
  from databricks.sdk.service.sql import State

  # Use get_workspace_client to pick up auth context if set
  client = get_workspace_client()

  # Fetch warehouses
  warehouses = list(islice(client.warehouses.list(), limit * 2))

  # Sort by priority: serverless first, then running + shared > running > shared > rest
  def sort_key(w):
    is_running = w.state == State.RUNNING if w.state else False
    is_shared = 'shared' in (w.name or '').lower()
    is_serverless = getattr(w, 'enable_serverless_compute', False) or False
    # Serverless warehouses always come first
    if is_serverless and is_running:
      priority = 0
    elif is_serverless:
      priority = 1
    elif is_running and is_shared:
      priority = 2
    elif is_running:
      priority = 3
    elif is_shared:
      priority = 4
    else:
      priority = 5
    return priority

  warehouses.sort(key=sort_key)

  return [
    {
      'warehouse_id': w.id,
      'warehouse_name': w.name,
      'state': w.state.value if w.state else 'UNKNOWN',
      'cluster_size': w.cluster_size,
      'creator_name': w.creator_name,
      'is_serverless': getattr(w, 'enable_serverless_compute', False) or False,
    }
    for w in warehouses[:limit]
  ]


async def _refresh_cache(timeout_seconds: int = 30) -> None:
  """Refresh the warehouse cache in the background.

  Args:
      timeout_seconds: Maximum time to wait for the API call
  """
  global _cache

  with _cache_lock:
    if _cache['is_refreshing']:
      return  # Another refresh is already in progress
    _cache['is_refreshing'] = True

  try:
    logger.info('Refreshing warehouses cache...')
    start = time.time()

    # Use wait_for to add a timeout to the thread operation
    warehouses = await asyncio.wait_for(
      asyncio.to_thread(_fetch_warehouses_sync),
      timeout=timeout_seconds,
    )

    with _cache_lock:
      _cache['warehouses'] = warehouses
      _cache['last_updated'] = time.time()

    logger.info(f'Warehouses cache refreshed: {len(warehouses)} warehouses in {time.time() - start:.2f}s')

  except asyncio.TimeoutError:
    logger.error(f'Warehouses cache refresh timed out after {timeout_seconds}s')

  except Exception as e:
    logger.error(f'Failed to refresh warehouses cache: {e}')

  finally:
    with _cache_lock:
      _cache['is_refreshing'] = False


def _is_cache_valid() -> bool:
  """Check if the cache is still valid."""
  with _cache_lock:
    if _cache['warehouses'] is None:
      return False
    return (time.time() - _cache['last_updated']) < CACHE_TTL_SECONDS


def _get_cached_warehouses() -> Optional[list[dict]]:
  """Get warehouses from cache if available."""
  with _cache_lock:
    return _cache['warehouses']


async def list_warehouses_async() -> list[dict]:
  """List available Databricks SQL warehouses with caching.

  Returns cached data immediately if available, and triggers
  a background refresh if the cache is stale.

  Returns:
      List of warehouse dictionaries with warehouse_id, warehouse_name, state, etc.
  """
  cached = _get_cached_warehouses()

  if cached is not None:
    # We have cached data - return it immediately
    if not _is_cache_valid():
      # Cache is stale, trigger background refresh
      asyncio.create_task(_refresh_cache())
    return cached

  # No cache - we must wait for the first fetch
  await _refresh_cache()
  return _get_cached_warehouses() or []

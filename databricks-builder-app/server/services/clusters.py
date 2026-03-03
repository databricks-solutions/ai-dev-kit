"""Clusters service for listing Databricks clusters with caching."""

import asyncio
import logging
import time
from itertools import islice
from threading import Lock
from typing import Optional

from databricks.sdk.config import Config
from databricks.sdk.service.compute import State
from databricks_tools_core.auth import get_workspace_client

logger = logging.getLogger(__name__)

# Cache configuration
CACHE_TTL_SECONDS = 300  # 5 minutes
_cache: dict = {
  'clusters': None,
  'last_updated': 0,
  'is_refreshing': False,
}
_cache_lock = Lock()


SERVERLESS_CLUSTER_ID = '__serverless__'


def _fetch_clusters_sync(limit: int = 50, timeout: int = 15) -> list[dict]:
  """Synchronously fetch clusters from Databricks using SDK.

  Returns a "Serverless Compute" entry first (always), followed by real clusters
  sorted by: running first, "shared" in name second, then alphabetically.

  Args:
      limit: Maximum number of clusters to return
      timeout: Timeout in seconds for the API call
  """
  from databricks.sdk.service.compute import ClusterSource, ListClustersFilterBy

  # Use get_workspace_client to pick up auth context if set
  client = get_workspace_client()

  # Filter out serverless and job clusters at the API level
  filter_by = ListClustersFilterBy(
    cluster_sources=[ClusterSource.UI, ClusterSource.API],
  )

  # Use page_size to fetch efficiently, islice to stop early
  clusters = list(islice(client.clusters.list(filter_by=filter_by, page_size=limit * 2), limit * 2))

  # No need to filter serverless anymore - done at API level
  filtered_clusters = clusters

  # Sort: running first, then "shared" in name
  def sort_key(c):
    is_running = c.state == State.RUNNING if c.state else False
    is_shared = 'shared' in (c.cluster_name or '').lower()
    return (not is_running, not is_shared)

  filtered_clusters.sort(key=sort_key)

  # Build result with Serverless Compute as the first (default) entry
  result = [
    {
      'cluster_id': SERVERLESS_CLUSTER_ID,
      'cluster_name': 'Serverless Compute',
      'state': 'RUNNING',
      'creator_user_name': None,
    },
  ]

  result.extend(
    {
      'cluster_id': c.cluster_id,
      'cluster_name': c.cluster_name,
      'state': c.state.value if c.state else 'UNKNOWN',
      'creator_user_name': c.creator_user_name,
    }
    for c in filtered_clusters[:limit]
  )

  return result


async def _refresh_cache(timeout_seconds: int = 30) -> None:
  """Refresh the cluster cache in the background.

  Args:
      timeout_seconds: Maximum time to wait for the API call
  """
  global _cache

  with _cache_lock:
    if _cache['is_refreshing']:
      return  # Another refresh is already in progress
    _cache['is_refreshing'] = True

  try:
    logger.info('Refreshing clusters cache...')
    start = time.time()

    # Use wait_for to add a timeout to the thread operation
    clusters = await asyncio.wait_for(
      asyncio.to_thread(_fetch_clusters_sync),
      timeout=timeout_seconds,
    )

    with _cache_lock:
      _cache['clusters'] = clusters
      _cache['last_updated'] = time.time()

    logger.info(f'Clusters cache refreshed: {len(clusters)} clusters in {time.time() - start:.2f}s')

  except asyncio.TimeoutError:
    logger.error(f'Clusters cache refresh timed out after {timeout_seconds}s')

  except Exception as e:
    logger.error(f'Failed to refresh clusters cache: {e}')

  finally:
    with _cache_lock:
      _cache['is_refreshing'] = False


def _is_cache_valid() -> bool:
  """Check if the cache is still valid."""
  with _cache_lock:
    if _cache['clusters'] is None:
      return False
    return (time.time() - _cache['last_updated']) < CACHE_TTL_SECONDS


def _get_cached_clusters() -> Optional[list[dict]]:
  """Get clusters from cache if available."""
  with _cache_lock:
    return _cache['clusters']


async def list_clusters_async() -> list[dict]:
  """List available Databricks clusters with caching.

  Returns cached data immediately if available, and triggers
  a background refresh if the cache is stale.

  Returns:
      List of cluster dictionaries with cluster_id, cluster_name, state, creator
  """
  cached = _get_cached_clusters()

  if cached is not None:
    # We have cached data - return it immediately
    if not _is_cache_valid():
      # Cache is stale, trigger background refresh
      asyncio.create_task(_refresh_cache())
    return cached

  # No cache - we must wait for the first fetch
  await _refresh_cache()
  result = _get_cached_clusters()
  if result:
    return result

  # Even if the API call failed, always return the serverless option
  return [
    {
      'cluster_id': SERVERLESS_CLUSTER_ID,
      'cluster_name': 'Serverless Compute',
      'state': 'RUNNING',
      'creator_user_name': None,
    },
  ]

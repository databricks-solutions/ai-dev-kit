"""Tests for clusters service."""

import asyncio
import time

import pytest


def test_fetch_clusters_sync_performance():
  """Test that raw API cluster fetching is fast (< 10s)."""
  from server.services.clusters import _fetch_clusters_sync

  start = time.time()
  clusters = _fetch_clusters_sync(limit=50)
  elapsed = time.time() - start

  print(f'\nFetched {len(clusters)} clusters in {elapsed:.2f}s')
  if clusters:
    print(f'First cluster: {clusters[0]["cluster_name"]} ({clusters[0]["state"]})')

  # Should complete in under 10 seconds
  assert elapsed < 10, f'Cluster fetch took too long: {elapsed:.2f}s'
  assert len(clusters) <= 50, f'Got more than limit: {len(clusters)}'


def test_clusters_sorted_correctly():
  """Test that clusters are sorted: serverless first, then running, shared, then rest."""
  from server.services.clusters import _fetch_clusters_sync, SERVERLESS_CLUSTER_ID

  clusters = _fetch_clusters_sync(limit=50)

  # First entry should always be Serverless Compute
  assert clusters[0]['cluster_id'] == SERVERLESS_CLUSTER_ID
  assert clusters[0]['cluster_name'] == 'Serverless Compute'

  # Skip the synthetic serverless entry for sort order checking
  real_clusters = [c for c in clusters if c['cluster_id'] != SERVERLESS_CLUSTER_ID]

  if len(real_clusters) < 2:
    pytest.skip('Not enough real clusters to test sorting')

  # Check running clusters come first among real clusters
  found_non_running = False
  for c in real_clusters:
    if c['state'] != 'RUNNING':
      found_non_running = True
    elif found_non_running:
      # Found a RUNNING cluster after a non-running one - bad sort
      pytest.fail(f"Running cluster {c['cluster_name']} found after non-running cluster")

  print(f'\nFirst 5 clusters:')
  for c in clusters[:5]:
    print(f"  {c['cluster_name']} ({c['state']})")


@pytest.mark.asyncio
async def test_list_clusters_async_caching():
  """Test that caching works - second call should be instant."""
  from server.services.clusters import _cache, list_clusters_async

  # Clear cache first
  _cache['clusters'] = None
  _cache['last_updated'] = 0

  # First call - should fetch from API
  start = time.time()
  clusters1 = await list_clusters_async()
  first_call_time = time.time() - start
  print(f'\nFirst call: {len(clusters1)} clusters in {first_call_time:.2f}s')

  # Second call - should be from cache (instant)
  start = time.time()
  clusters2 = await list_clusters_async()
  second_call_time = time.time() - start
  print(f'Second call: {len(clusters2)} clusters in {second_call_time:.4f}s')

  assert first_call_time < 15, f'First call too slow: {first_call_time:.2f}s'
  assert second_call_time < 0.01, f'Cached call too slow: {second_call_time:.4f}s'
  assert clusters1 == clusters2, 'Cached data should match'


if __name__ == '__main__':
  # Run sync test directly
  print('=== Testing sync fetch performance ===')
  test_fetch_clusters_sync_performance()

  print('\n=== Testing sorting ===')
  test_clusters_sorted_correctly()

  print('\n=== Testing async caching ===')
  asyncio.run(test_list_clusters_async_caching())

  print('\n=== All tests passed! ===')

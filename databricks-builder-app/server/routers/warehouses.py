"""Warehouse management endpoints."""

import logging

from fastapi import APIRouter, Request
from databricks_tools_core.auth import set_databricks_auth, clear_databricks_auth

from ..services.warehouses import list_warehouses_async
from ..services.user import get_databricks_token, get_workspace_url

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get('/warehouses')
async def get_warehouses(request: Request):
  """Get available Databricks SQL warehouses.

  Returns warehouses sorted by priority:
  1. Running + "shared" in name (highest priority)
  2. Running (without "shared")
  3. Not running + "shared" in name
  4. Everything else

  Results are cached for 5 minutes with background refresh.
  """
  workspace_url = get_workspace_url()
  user_token = await get_databricks_token(request)

  set_databricks_auth(workspace_url, user_token)

  try:
    # Get warehouses (cached with async refresh)
    warehouses = await list_warehouses_async()
    return warehouses
  finally:
    clear_databricks_auth()

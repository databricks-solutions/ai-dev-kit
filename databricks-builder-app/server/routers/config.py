"""Configuration and user info endpoints."""

import logging
import os
from typing import Optional

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from ..db import get_lakebase_project_id, is_postgres_configured, test_database_connection
from ..services.system_prompt import get_system_prompt
from ..services.user import get_current_user, get_workspace_url

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get('/me')
async def get_user_info(request: Request):
  """Get current user information and app configuration."""
  user_email = await get_current_user(request)
  workspace_url = get_workspace_url()
  lakebase_configured = is_postgres_configured()
  lakebase_project_id = get_lakebase_project_id()

  # Test database connection if configured
  lakebase_error = None
  if lakebase_configured:
    lakebase_error = await test_database_connection()

  return {
    'user': user_email,
    'workspace_url': workspace_url,
    'lakebase_configured': lakebase_configured,
    'lakebase_project_id': lakebase_project_id,
    'lakebase_error': lakebase_error,
  }


@router.get('/health')
async def health_check():
  """Health check endpoint."""
  return {'status': 'healthy'}


@router.get('/system_prompt')
async def get_system_prompt_endpoint(
  cluster_id: Optional[str] = Query(None),
  warehouse_id: Optional[str] = Query(None),
  default_catalog: Optional[str] = Query(None),
  default_schema: Optional[str] = Query(None),
  workspace_folder: Optional[str] = Query(None),
  project_id: Optional[str] = Query(None),
):
  """Get the system prompt with current configuration."""
  enabled_skills = None
  if project_id:
    from ..services.agent import get_project_directory
    from ..services.skills_manager import get_project_enabled_skills
    project_dir = get_project_directory(project_id)
    enabled_skills = get_project_enabled_skills(project_dir)

  prompt = get_system_prompt(
    cluster_id=cluster_id,
    default_catalog=default_catalog,
    default_schema=default_schema,
    warehouse_id=warehouse_id,
    workspace_folder=workspace_folder,
    enabled_skills=enabled_skills,
  )
  return {'system_prompt': prompt}


@router.get('/mlflow/status')
async def mlflow_status_endpoint():
  """Get MLflow tracing status and configuration.

  Returns current MLflow tracing state including:
  - Whether tracing is enabled (via MLFLOW_EXPERIMENT_NAME env var)
  - Tracking URI
  - Current experiment info
  """
  experiment_name = os.environ.get('MLFLOW_EXPERIMENT_NAME', '')
  tracking_uri = os.environ.get('MLFLOW_TRACKING_URI', 'databricks')

  return {
    'enabled': bool(experiment_name),
    'tracking_uri': tracking_uri,
    'experiment_name': experiment_name,
    'info': 'MLflow tracing is configured via environment variables in app.yaml',
  }

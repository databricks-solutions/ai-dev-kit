"""Shared project ownership checks for API routes."""

from fastapi import HTTPException, Request

from ..db.models import Project
from .project_paths import validate_project_id
from .storage import ProjectStorage
from .user import get_current_user


async def require_owned_project(request: Request, project_id: str) -> tuple[str, Project]:
  """Authenticate the caller and verify they own the project."""
  try:
    validate_project_id(project_id)
  except ValueError:
    raise HTTPException(status_code=400, detail='Invalid project_id')

  user_email = await get_current_user(request)
  project = await ProjectStorage(user_email).get(project_id)
  if not project:
    raise HTTPException(status_code=404, detail=f'Project not found: {project_id}')
  return user_email, project


async def require_stream_owner(request: Request, user_email: str) -> str:
  """Authenticate the caller and verify they own an active stream."""
  if not user_email:
    raise HTTPException(status_code=403, detail='Access denied')
  caller = await get_current_user(request)
  if caller != user_email:
    raise HTTPException(status_code=403, detail='Access denied')
  return caller

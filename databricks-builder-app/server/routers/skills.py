"""Skills explorer and management API endpoints."""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..services import (
  get_available_skills,
  get_project_directory,
  get_project_enabled_skills,
  reload_project_skills,
  set_project_enabled_skills,
  sync_project_skills,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class UpdateEnabledSkillsRequest(BaseModel):
  """Request to update enabled skills for a project."""

  enabled_skills: list[str] | None = None  # None means all skills enabled


def _get_skills_dir(project_id: str) -> Path:
  """Get the skills directory for a project."""
  project_dir = get_project_directory(project_id)
  return project_dir / '.claude' / 'skills'


def _build_tree_node(path: Path, base_path: Path) -> dict:
  """Build a tree node for a file or directory."""
  relative_path = str(path.relative_to(base_path))
  name = path.name

  if path.is_dir():
    children = []
    # Sort: directories first, then files, alphabetically
    items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    for item in items:
      # Skip hidden files and __pycache__
      if item.name.startswith('.') or item.name == '__pycache__':
        continue
      children.append(_build_tree_node(item, base_path))
    return {
      'name': name,
      'path': relative_path,
      'type': 'directory',
      'children': children,
    }
  else:
    return {
      'name': name,
      'path': relative_path,
      'type': 'file',
    }


@router.get('/projects/{project_id}/skills/tree')
async def get_skills_tree(project_id: str):
  """Get the skills directory tree for a project."""
  skills_dir = _get_skills_dir(project_id)

  if not skills_dir.exists():
    return {'tree': []}

  tree = []
  items = sorted(skills_dir.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))

  for item in items:
    if item.name.startswith('.'):
      continue
    tree.append(_build_tree_node(item, skills_dir))

  return {'tree': tree}


@router.get('/projects/{project_id}/skills/file')
async def get_skill_file(
  project_id: str,
  path: str = Query(..., description='Relative path to the file within the skills folder'),
):
  """Get the content of a skill file."""
  skills_dir = _get_skills_dir(project_id)

  try:
    requested_path = (skills_dir / path).resolve()

    if not str(requested_path).startswith(str(skills_dir.resolve())):
      raise HTTPException(status_code=403, detail='Access denied: path outside skills directory')

    if not requested_path.exists():
      raise HTTPException(status_code=404, detail='File not found')

    if not requested_path.is_file():
      raise HTTPException(status_code=400, detail='Path is not a file')

    content = requested_path.read_text(encoding='utf-8')
    return {
      'path': path,
      'content': content,
      'filename': requested_path.name,
    }

  except HTTPException:
    raise
  except Exception as e:
    logger.error(f'Failed to read skill file: {e}')
    raise HTTPException(status_code=500, detail=f'Failed to read file: {str(e)}')


@router.get('/projects/{project_id}/skills/available')
async def get_available_skills_for_project(project_id: str):
  """Get all available skills with their enabled/disabled status for a project."""
  project_dir = get_project_directory(project_id)
  enabled_skills = get_project_enabled_skills(project_dir)

  # Get all skills (unfiltered) from app cache
  all_skills = get_available_skills()

  result = []
  for skill in all_skills:
    result.append({
      'name': skill['name'],
      'description': skill['description'],
      'enabled': enabled_skills is None or skill['name'] in enabled_skills,
    })

  enabled_count = len(result) if enabled_skills is None else sum(1 for s in result if s['enabled'])

  return {
    'skills': result,
    'all_enabled': enabled_skills is None,
    'enabled_count': enabled_count,
    'total_count': len(result),
  }


@router.put('/projects/{project_id}/skills/enabled')
async def update_enabled_skills(project_id: str, body: UpdateEnabledSkillsRequest):
  """Update the list of enabled skills for a project.

  Setting enabled_skills to null re-enables all skills.
  After updating, syncs the project's .claude/skills directory.
  """
  project_dir = get_project_directory(project_id)

  # Write to filesystem
  success = set_project_enabled_skills(project_dir, body.enabled_skills)
  if not success:
    raise HTTPException(status_code=500, detail='Failed to update enabled skills')

  # Sync the project's skills directory
  sync_project_skills(project_dir, body.enabled_skills)

  return {
    'success': True,
    'enabled_skills': body.enabled_skills,
    'all_enabled': body.enabled_skills is None,
  }


@router.post('/projects/{project_id}/skills/reload')
async def reload_skills(project_id: str):
  """Reload skills for a project (respects enabled skills)."""
  try:
    project_dir = get_project_directory(project_id)
    enabled_skills = get_project_enabled_skills(project_dir)

    success = reload_project_skills(project_dir, enabled_skills=enabled_skills)

    if success:
      return {'success': True, 'message': 'Skills reloaded successfully'}
    else:
      raise HTTPException(status_code=500, detail='Failed to reload skills')

  except HTTPException:
    raise
  except Exception as e:
    logger.error(f'Failed to reload skills: {e}')
    raise HTTPException(status_code=500, detail=f'Failed to reload skills: {str(e)}')

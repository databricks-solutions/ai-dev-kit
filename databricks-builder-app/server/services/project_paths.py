"""Safe project directory resolution."""

import os
import uuid
from pathlib import Path

PROJECTS_BASE_DIR = os.getenv('PROJECTS_BASE_DIR', './projects')


def validate_project_id(project_id: str) -> None:
  """Reject non-UUID project IDs before any filesystem access."""
  try:
    uuid.UUID(project_id)
  except (ValueError, AttributeError, TypeError) as exc:
    raise ValueError(f'Invalid project_id: {project_id!r}') from exc


def resolve_project_dir(project_id: str) -> Path:
  """Return the resolved project directory, blocking path traversal."""
  validate_project_id(project_id)
  root = Path(PROJECTS_BASE_DIR).resolve()
  project_dir = (root / project_id).resolve()
  if not project_dir.is_relative_to(root):
    raise ValueError(f'Invalid project_id path: {project_id!r}')
  return project_dir

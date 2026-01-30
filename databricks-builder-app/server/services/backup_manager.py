"""Backup manager service for project files.

Handles zipping project folders and storing/restoring from PostgreSQL.
Runs a background loop every 10 minutes to process pending backups.
"""

import asyncio
import logging
import os
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from ..db.database import session_scope
from ..db.models import ProjectBackup

logger = logging.getLogger(__name__)

# Configuration
BACKUP_INTERVAL = 600  # 10 minutes
PROJECTS_BASE_DIR = os.getenv('PROJECTS_BASE_DIR', './projects')

# In-memory queue of project IDs needing backup
_backup_queue: set[str] = set()
_backup_task: Optional[asyncio.Task] = None


def mark_for_backup(project_id: str) -> None:
  """Mark a project for backup.

  Called after agent query completes. The project will be backed up
  in the next backup loop iteration.

  Args:
      project_id: The project UUID to backup
  """
  _backup_queue.add(project_id)
  logger.debug(f'Project {project_id} marked for backup')


async def create_backup(project_id: str) -> bool:
  """Create a backup of the project folder.

  Zips all files in the project directory and stores in the database.

  Args:
      project_id: The project UUID to backup

  Returns:
      True if backup was created, False if project folder doesn't exist
  """
  project_dir = Path(PROJECTS_BASE_DIR).resolve() / project_id

  if not project_dir.exists():
    logger.warning(f'Project directory does not exist: {project_dir}')
    return False

  # Create zip in memory
  buffer = BytesIO()
  file_count = 0

  with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
    for file_path in project_dir.rglob('*'):
      if file_path.is_file():
        arcname = str(file_path.relative_to(project_dir))
        zf.write(file_path, arcname)
        file_count += 1

  if file_count == 0:
    logger.debug(f'Project {project_id} has no files to backup')
    return False

  backup_data = buffer.getvalue()

  # Upsert to database (INSERT ON CONFLICT UPDATE)
  async with session_scope() as session:
    stmt = insert(ProjectBackup).values(
      project_id=project_id,
      backup_data=backup_data,
    )
    stmt = stmt.on_conflict_do_update(
      index_elements=['project_id'],
      set_={'backup_data': backup_data, 'updated_at': ProjectBackup.updated_at.default.arg()},
    )
    await session.execute(stmt)

  logger.info(f'Backed up project {project_id} ({file_count} files, {len(backup_data)} bytes)')
  return True


async def restore_backup(project_id: str) -> bool:
  """Restore a project from backup.

  Downloads the zip from database and extracts to project directory.

  Args:
      project_id: The project UUID to restore

  Returns:
      True if restored, False if no backup exists
  """
  async with session_scope() as session:
    result = await session.execute(
      select(ProjectBackup.backup_data).where(ProjectBackup.project_id == project_id)
    )
    row = result.scalar_one_or_none()

    if row is None:
      logger.debug(f'No backup found for project {project_id}')
      return False

    backup_data = row

  # Create project directory
  project_dir = Path(PROJECTS_BASE_DIR).resolve() / project_id
  project_dir.mkdir(parents=True, exist_ok=True)

  # Extract zip
  buffer = BytesIO(backup_data)
  with zipfile.ZipFile(buffer, 'r') as zf:
    zf.extractall(project_dir)

  logger.info(f'Restored project {project_id} from backup')
  return True


def _create_default_claude_md(project_dir: Path) -> None:
  """Create a default CLAUDE.md file for a new project.

  Args:
      project_dir: Path to the project directory
  """
  claude_md_path = project_dir / 'CLAUDE.md'
  if claude_md_path.exists():
    return

  default_content = """# Project Context

This file tracks the Databricks resources created in this project.
The AI assistant will update this file as resources are created.

## Configuration

- **Catalog:** (not yet configured)
- **Schema:** (not yet configured)

## Resources Created

### Tables
(none yet)

### Volumes
(none yet)

### Pipelines
(none yet)

### Jobs
(none yet)

## Notes

Add any project-specific notes or context here.
"""

  try:
    claude_md_path.write_text(default_content)
    logger.info(f'Created default CLAUDE.md in {project_dir}')
  except Exception as e:
    logger.warning(f'Failed to create CLAUDE.md: {e}')


def ensure_project_directory(project_id: str) -> Path:
  """Ensure project directory exists, restoring from backup if needed.

  This is the main entry point for getting a project directory.
  If the directory doesn't exist, attempts to restore from backup.
  If no backup exists, creates an empty directory.
  Also ensures skills are copied to the project and CLAUDE.md exists.

  Args:
      project_id: The project UUID

  Returns:
      Path to the project directory
  """
  from .skills_manager import copy_skills_to_project

  project_dir = Path(PROJECTS_BASE_DIR).resolve() / project_id
  needs_skills = not project_dir.exists() or not (project_dir / '.claude' / 'skills').exists()
  is_new_project = not project_dir.exists()

  if not project_dir.exists():
    # Try to restore from backup
    try:
      loop = asyncio.get_event_loop()
      if loop.is_running():
        # We're in an async context, create a new task
        future = asyncio.ensure_future(restore_backup(project_id))
        # This is a sync function called from async code, we need to handle this
        # For now, just create the directory - the restore will happen async
        project_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f'Created empty project directory: {project_dir}')
      else:
        restored = loop.run_until_complete(restore_backup(project_id))
        if not restored:
          project_dir.mkdir(parents=True, exist_ok=True)
          logger.debug(f'Created empty project directory: {project_dir}')
    except RuntimeError:
      # No event loop, use asyncio.run
      restored = asyncio.run(restore_backup(project_id))
      if not restored:
        project_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f'Created empty project directory: {project_dir}')

  # Copy skills to project if needed
  if needs_skills:
    copy_skills_to_project(project_dir)

  # Create default CLAUDE.md for new projects (or if it doesn't exist)
  if is_new_project or not (project_dir / 'CLAUDE.md').exists():
    _create_default_claude_md(project_dir)

  return project_dir


async def ensure_project_directory_async(project_id: str) -> Path:
  """Async version of ensure_project_directory.

  Args:
      project_id: The project UUID

  Returns:
      Path to the project directory
  """
  project_dir = Path(PROJECTS_BASE_DIR).resolve() / project_id

  if not project_dir.exists():
    restored = await restore_backup(project_id)
    if not restored:
      project_dir.mkdir(parents=True, exist_ok=True)
      logger.debug(f'Created empty project directory: {project_dir}')

  return project_dir


async def _backup_loop() -> None:
  """Background loop that processes pending backups every 10 minutes."""
  logger.info(f'Backup worker started (interval: {BACKUP_INTERVAL}s)')

  while True:
    await asyncio.sleep(BACKUP_INTERVAL)

    if not _backup_queue:
      continue

    # Get and clear pending backups
    pending = _backup_queue.copy()
    _backup_queue.clear()

    logger.info(f'Processing {len(pending)} pending backups')

    for project_id in pending:
      try:
        await create_backup(project_id)
      except Exception as e:
        logger.error(f'Backup failed for project {project_id}: {e}')


def start_backup_worker() -> None:
  """Start the background backup loop.

  Should be called during app startup.
  """
  global _backup_task
  _backup_task = asyncio.create_task(_backup_loop())
  logger.info('Backup worker task created')


def stop_backup_worker() -> None:
  """Stop the background backup loop.

  Should be called during app shutdown.
  """
  global _backup_task
  if _backup_task:
    _backup_task.cancel()
    logger.info('Backup worker stopped')

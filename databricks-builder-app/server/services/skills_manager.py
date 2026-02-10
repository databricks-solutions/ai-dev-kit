"""Skills manager for copying and managing Databricks skills.

Handles copying skills from the source repository to the app and project directories.
"""

import json
import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Skill → MCP tool mapping
# Maps skill names to their exclusive Databricks MCP tool function names.
# Tools NOT listed here (sql, compute, file, operation tracking) are always
# available regardless of which skills are enabled.
# ---------------------------------------------------------------------------
SKILL_TOOL_MAPPING: dict[str, list[str]] = {
  'agent-bricks': [
    'create_or_update_ka', 'get_ka', 'find_ka_by_name', 'delete_ka',
    'create_or_update_mas', 'get_mas', 'find_mas_by_name', 'delete_mas',
  ],
  'aibi-dashboards': [
    'create_or_update_dashboard', 'get_dashboard', 'list_dashboards',
    'trash_dashboard', 'publish_dashboard', 'unpublish_dashboard',
  ],
  'databricks-genie': [
    'list_genie', 'create_or_update_genie', 'get_genie', 'delete_genie',
    'ask_genie', 'ask_genie_followup',
  ],
  'spark-declarative-pipelines': [
    'create_pipeline', 'get_pipeline', 'update_pipeline', 'delete_pipeline',
    'start_update', 'get_update', 'stop_pipeline', 'get_pipeline_events',
    'create_or_update_pipeline', 'find_pipeline_by_name',
  ],
  'model-serving': [
    'get_serving_endpoint_status', 'query_serving_endpoint', 'list_serving_endpoints',
  ],
  'databricks-jobs': [
    'list_jobs', 'get_job', 'find_job_by_name', 'create_job', 'update_job',
    'delete_job', 'run_job_now', 'get_run', 'get_run_output', 'cancel_run',
    'list_runs', 'wait_for_run',
  ],
  'databricks-unity-catalog': [
    'manage_uc_objects', 'manage_uc_grants', 'manage_uc_storage',
    'manage_uc_connections', 'manage_uc_tags', 'manage_uc_security_policies',
    'manage_uc_monitors', 'manage_uc_sharing',
    'list_volume_files', 'upload_to_volume', 'download_from_volume',
    'delete_volume_file', 'delete_volume_directory', 'create_volume_directory',
    'get_volume_file_info',
  ],
}


def get_allowed_mcp_tools(
  all_tool_names: list[str],
  enabled_skills: list[str] | None = None,
) -> list[str]:
  """Filter MCP tool names based on enabled skills.

  Tools mapped to disabled skills are removed. Tools not mapped to any skill
  (e.g. execute_sql, compute tools) are always kept.

  Args:
      all_tool_names: Full list of MCP tool names (mcp__databricks__xxx format)
      enabled_skills: List of enabled skill names, or None for all skills.

  Returns:
      Filtered list of allowed MCP tool names.
  """
  if enabled_skills is None:
    return all_tool_names

  # Collect tool names that belong to DISABLED skills
  enabled_set = set(enabled_skills)
  blocked_tools: set[str] = set()
  for skill_name, tool_names in SKILL_TOOL_MAPPING.items():
    if skill_name not in enabled_set:
      blocked_tools.update(tool_names)

  # Don't block a tool if it's also claimed by an ENABLED skill
  for skill_name in enabled_skills:
    for tool_name in SKILL_TOOL_MAPPING.get(skill_name, []):
      blocked_tools.discard(tool_name)

  # Filter: tool name format is mcp__databricks__{name}
  prefix = 'mcp__databricks__'
  return [
    t for t in all_tool_names
    if not t.startswith(prefix) or t[len(prefix):] not in blocked_tools
  ]


# Source skills directory - check multiple locations
# 1. Sibling to this app (local development): ../../databricks-skills
# 2. Deployed location (Databricks Apps): ./skills at app root
_DEV_SKILLS_DIR = Path(__file__).parent.parent.parent.parent / 'databricks-skills'
_DEPLOYED_SKILLS_DIR = Path(__file__).parent.parent.parent / 'skills'

# Local cache of skills within this app (copied on startup)
APP_SKILLS_DIR = Path(__file__).parent.parent.parent / 'skills'

# Prefer dev location (sibling repo) when available to avoid self-deletion:
# APP_SKILLS_DIR == _DEPLOYED_SKILLS_DIR, so using deployed as source would
# delete the source during copy_skills_to_app(). Only fall back to deployed
# location when the dev source repo isn't available (actual deployment).
if _DEV_SKILLS_DIR.exists() and any(_DEV_SKILLS_DIR.iterdir()):
  SKILLS_SOURCE_DIR = _DEV_SKILLS_DIR
elif _DEPLOYED_SKILLS_DIR.exists() and any(_DEPLOYED_SKILLS_DIR.iterdir()):
  SKILLS_SOURCE_DIR = _DEPLOYED_SKILLS_DIR
else:
  SKILLS_SOURCE_DIR = _DEV_SKILLS_DIR


def _get_enabled_skills() -> list[str] | None:
  """Get list of enabled skills from environment.

  Returns:
      List of skill names to include, or None to include all skills
  """
  enabled = os.environ.get('ENABLED_SKILLS', '').strip()
  if not enabled:
    return None
  return [s.strip() for s in enabled.split(',') if s.strip()]


def get_available_skills(enabled_skills: list[str] | None = None) -> list[dict]:
  """Get list of available skills with their metadata.

  Args:
      enabled_skills: Optional list of skill names to include.
          If None, all skills are returned.

  Returns:
      List of dicts with name, description, and path for each skill
  """
  skills = []

  if not APP_SKILLS_DIR.exists():
    logger.warning(f'Skills directory not found: {APP_SKILLS_DIR}')
    return skills

  for skill_dir in APP_SKILLS_DIR.iterdir():
    if not skill_dir.is_dir():
      continue

    skill_md = skill_dir / 'SKILL.md'
    if not skill_md.exists():
      continue

    # Parse frontmatter to get name and description
    try:
      content = skill_md.read_text()
      if content.startswith('---'):
        # Extract YAML frontmatter
        end_idx = content.find('---', 3)
        if end_idx > 0:
          frontmatter = content[3:end_idx].strip()
          name = None
          description = None

          for line in frontmatter.split('\n'):
            if line.startswith('name:'):
              name = line.split(':', 1)[1].strip().strip('"\'')
            elif line.startswith('description:'):
              description = line.split(':', 1)[1].strip().strip('"\'')

          if name:
            # Filter by enabled_skills if provided
            if enabled_skills is not None and name not in enabled_skills:
              continue
            skills.append({
              'name': name,
              'description': description or '',
              'path': str(skill_dir),
            })
    except Exception as e:
      logger.warning(f'Failed to parse skill {skill_dir}: {e}')

  return skills


class SkillNotFoundError(Exception):
  """Raised when an enabled skill is not found in the source directory."""

  pass


def copy_skills_to_app() -> bool:
  """Copy skills from source repo to app's skills directory.

  Called on server startup to ensure we have the latest skills.
  Only copies skills listed in ENABLED_SKILLS env var (if set).

  Returns:
      True if successful, False otherwise

  Raises:
      SkillNotFoundError: If an enabled skill folder doesn't exist or lacks SKILL.md
  """
  if not SKILLS_SOURCE_DIR.exists():
    logger.warning(f'Skills source directory not found: {SKILLS_SOURCE_DIR}')
    return False

  # Guard against self-deletion: in deployed apps, SKILLS_SOURCE_DIR and
  # APP_SKILLS_DIR resolve to the same directory. Deleting APP_SKILLS_DIR
  # would destroy the source. Skills are already in place, so skip the copy.
  if SKILLS_SOURCE_DIR.resolve() == APP_SKILLS_DIR.resolve():
    logger.info(f'Skills source and app directory are the same ({APP_SKILLS_DIR}), skipping copy')
    return True

  enabled_skills = _get_enabled_skills()
  if enabled_skills:
    logger.info(f'Filtering skills to: {enabled_skills}')

    # Validate that all enabled skills exist before copying
    for skill_name in enabled_skills:
      skill_path = SKILLS_SOURCE_DIR / skill_name
      skill_md_path = skill_path / 'SKILL.md'

      if not skill_path.exists():
        raise SkillNotFoundError(
          f"Skill '{skill_name}' not found. "
          f"Directory does not exist: {skill_path}. "
          f"Check ENABLED_SKILLS in your .env file."
        )

      if not skill_md_path.exists():
        raise SkillNotFoundError(
          f"Skill '{skill_name}' is invalid. "
          f"Missing SKILL.md file in: {skill_path}. "
          f"Each skill must have a SKILL.md file."
        )

  try:
    # Remove existing skills directory if it exists
    if APP_SKILLS_DIR.exists():
      shutil.rmtree(APP_SKILLS_DIR)

    # Copy skill directories (filtered by ENABLED_SKILLS if set)
    APP_SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    copied_count = 0
    for item in SKILLS_SOURCE_DIR.iterdir():
      if item.is_dir() and (item / 'SKILL.md').exists():
        # Skip if not in enabled list (when list is specified)
        if enabled_skills and item.name not in enabled_skills:
          logger.debug(f'Skipping skill (not enabled): {item.name}')
          continue

        dest = APP_SKILLS_DIR / item.name
        shutil.copytree(item, dest)
        copied_count += 1
        logger.debug(f'Copied skill: {item.name}')

    logger.info(f'Copied {copied_count} skills to {APP_SKILLS_DIR}')
    return True

  except SkillNotFoundError:
    raise  # Re-raise validation errors
  except Exception as e:
    logger.error(f'Failed to copy skills: {e}')
    return False


def copy_skills_to_project(project_dir: Path, enabled_skills: list[str] | None = None) -> bool:
  """Copy skills to a project's .claude/skills directory.

  Args:
      project_dir: Path to the project directory
      enabled_skills: Optional list of skill names to copy.
          If None, all skills are copied (backward compatible).

  Returns:
      True if successful, False otherwise
  """
  if not APP_SKILLS_DIR.exists():
    logger.warning('App skills directory not found, trying to copy from source')
    copy_skills_to_app()

  if not APP_SKILLS_DIR.exists():
    logger.warning('No skills available to copy')
    return False

  # Build a set of enabled skill directory names by matching SKILL.md name to dir
  enabled_dir_names = None
  if enabled_skills is not None:
    enabled_dir_names = set()
    for skill_dir in APP_SKILLS_DIR.iterdir():
      if not skill_dir.is_dir() or not (skill_dir / 'SKILL.md').exists():
        continue
      skill_name = _parse_skill_name(skill_dir)
      if skill_name and skill_name in enabled_skills:
        enabled_dir_names.add(skill_dir.name)

  try:
    # Create .claude/skills directory in project
    project_skills_dir = project_dir / '.claude' / 'skills'
    project_skills_dir.mkdir(parents=True, exist_ok=True)

    # Copy skills (filtered if enabled_dir_names is set)
    copied_count = 0
    for skill_dir in APP_SKILLS_DIR.iterdir():
      if skill_dir.is_dir() and (skill_dir / 'SKILL.md').exists():
        if enabled_dir_names is not None and skill_dir.name not in enabled_dir_names:
          continue
        dest = project_skills_dir / skill_dir.name
        if dest.exists():
          shutil.rmtree(dest)
        shutil.copytree(skill_dir, dest)
        copied_count += 1

    logger.info(f'Copied {copied_count} skills to project: {project_dir}')
    return True

  except Exception as e:
    logger.error(f'Failed to copy skills to project: {e}')
    return False


def sync_project_skills(project_dir: Path, enabled_skills: list[str] | None = None) -> bool:
  """Sync a project's skills directory to match the enabled skills list.

  Removes skills not in the enabled list and adds missing ones.
  More efficient than a full wipe-and-recopy for incremental changes.

  Args:
      project_dir: Path to the project directory
      enabled_skills: List of enabled skill names, or None for all skills

  Returns:
      True if successful, False otherwise
  """
  if not APP_SKILLS_DIR.exists():
    logger.warning('App skills directory not found')
    return False

  try:
    project_skills_dir = project_dir / '.claude' / 'skills'
    project_skills_dir.mkdir(parents=True, exist_ok=True)

    # Build mapping: skill_name -> app_skills_dir_name
    name_to_dir = {}
    for skill_dir in APP_SKILLS_DIR.iterdir():
      if not skill_dir.is_dir() or not (skill_dir / 'SKILL.md').exists():
        continue
      skill_name = _parse_skill_name(skill_dir)
      if skill_name:
        name_to_dir[skill_name] = skill_dir.name

    # Determine which dir names should be present
    if enabled_skills is not None:
      desired_dirs = {name_to_dir[name] for name in enabled_skills if name in name_to_dir}
    else:
      desired_dirs = set(name_to_dir.values())

    # Remove skills that shouldn't be there
    for existing in project_skills_dir.iterdir():
      if existing.is_dir() and existing.name not in desired_dirs:
        logger.debug(f'Removing disabled skill from project: {existing.name}')
        shutil.rmtree(existing)

    # Add missing skills
    for dir_name in desired_dirs:
      dest = project_skills_dir / dir_name
      if not dest.exists():
        src = APP_SKILLS_DIR / dir_name
        if src.exists():
          logger.debug(f'Adding enabled skill to project: {dir_name}')
          shutil.copytree(src, dest)

    logger.info(f'Synced project skills: {len(desired_dirs)} enabled')
    return True

  except Exception as e:
    logger.error(f'Failed to sync project skills: {e}')
    return False


def _parse_skill_name(skill_dir: Path) -> str | None:
  """Parse the skill name from a skill directory's SKILL.md frontmatter.

  Args:
      skill_dir: Path to the skill directory

  Returns:
      Skill name string, or None if not parseable
  """
  skill_md = skill_dir / 'SKILL.md'
  if not skill_md.exists():
    return None
  try:
    content = skill_md.read_text()
    if content.startswith('---'):
      end_idx = content.find('---', 3)
      if end_idx > 0:
        frontmatter = content[3:end_idx].strip()
        for line in frontmatter.split('\n'):
          if line.startswith('name:'):
            return line.split(':', 1)[1].strip().strip('"\'')
  except Exception:
    pass
  return None


def reload_project_skills(project_dir: Path, enabled_skills: list[str] | None = None) -> bool:
  """Reload skills for a project by refreshing from source.

  This function:
  1. Refreshes the app's skills cache from the source repo
  2. Removes the project's existing skills
  3. Copies the updated skills to the project (filtered by enabled_skills)

  Args:
      project_dir: Path to the project directory
      enabled_skills: Optional list of skill names to include.
          If None, all skills are copied.

  Returns:
      True if successful, False otherwise
  """
  try:
    # First, refresh app skills from source
    logger.info('Refreshing app skills from source...')
    copy_skills_to_app()

    # Remove existing project skills
    project_skills_dir = project_dir / '.claude' / 'skills'
    if project_skills_dir.exists():
      logger.info(f'Removing existing project skills: {project_skills_dir}')
      shutil.rmtree(project_skills_dir)

    # Copy fresh skills to project (filtered by enabled_skills)
    logger.info('Copying fresh skills to project...')
    return copy_skills_to_project(project_dir, enabled_skills=enabled_skills)

  except Exception as e:
    logger.error(f'Failed to reload project skills: {e}')
    return False


def get_skills_summary() -> str:
  """Get a summary of available skills for the system prompt.

  Returns:
      Markdown-formatted summary of skills
  """
  skills = get_available_skills()

  if not skills:
    return ''

  lines = ['## Available Skills', '']
  lines.append('Use the `Skill` tool to invoke these skills for specialized guidance:')
  lines.append('')

  for skill in skills:
    lines.append(f"- **{skill['name']}**: {skill['description']}")

  lines.append('')
  lines.append('To use a skill, invoke it by name (e.g., `skill: "sdp"`).')

  return '\n'.join(lines)


# ---------------------------------------------------------------------------
# File-based enabled skills storage (no DB migration required)
# Stored at: project_dir/.claude/enabled_skills.json
# ---------------------------------------------------------------------------

_ENABLED_SKILLS_FILENAME = 'enabled_skills.json'


def get_project_enabled_skills(project_dir: Path) -> list[str] | None:
  """Read the enabled skills list for a project from the filesystem.

  Returns:
      List of enabled skill names, or None if all skills are enabled.
  """
  config_path = project_dir / '.claude' / _ENABLED_SKILLS_FILENAME
  if not config_path.exists():
    return None
  try:
    data = json.loads(config_path.read_text())
    if isinstance(data, list):
      return data
    return None
  except (json.JSONDecodeError, OSError) as e:
    logger.warning(f'Failed to read enabled skills config: {e}')
    return None


def set_project_enabled_skills(project_dir: Path, enabled_skills: list[str] | None) -> bool:
  """Write the enabled skills list for a project to the filesystem.

  Args:
      project_dir: Path to the project directory
      enabled_skills: List of skill names to enable, or None for all skills.

  Returns:
      True if successful, False otherwise
  """
  claude_dir = project_dir / '.claude'
  config_path = claude_dir / _ENABLED_SKILLS_FILENAME
  try:
    if enabled_skills is None:
      # All skills enabled — remove the config file if it exists
      if config_path.exists():
        config_path.unlink()
    else:
      claude_dir.mkdir(parents=True, exist_ok=True)
      config_path.write_text(json.dumps(enabled_skills, indent=2))
    return True
  except OSError as e:
    logger.error(f'Failed to write enabled skills config: {e}')
    return False

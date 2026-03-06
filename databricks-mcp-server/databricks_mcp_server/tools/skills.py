"""
Skills tools for the MCP server.

Exposes the databricks-skills as MCP resources and tools, allowing agents
to discover and read skill documentation for guidance on Databricks tasks.
"""

import os
import re
from pathlib import Path
from typing import Optional, Tuple

from ..server import mcp


def _get_skills_dir() -> Path:
    """Get the skills directory path."""
    # Check for skills in multiple locations
    possible_paths = [
        # Environment variable override (highest priority)
        Path(os.getenv("SKILLS_DIR", "")),
        # Databricks App deployment: skills folder at app root
        Path("/Workspace") / os.getenv("DATABRICKS_APP_ROOT", "") / "skills",
        # Deployed alongside the MCP server package
        Path(__file__).parent.parent.parent / "skills",
        # Development: sibling directory
        Path(__file__).parent.parent.parent.parent / "databricks-skills",
    ]
    
    for path in possible_paths:
        if path and str(path) and path.exists() and path.is_dir():
            return path
    
    # Default to the relative path
    return Path(__file__).parent.parent.parent / "skills"


def _parse_skill_frontmatter(content: str) -> Tuple[dict, str]:
    """
    Parse YAML frontmatter from a skill file.
    
    Returns:
        Tuple of (frontmatter dict, remaining content)
    """
    frontmatter = {}
    body = content
    
    # Check for YAML frontmatter (starts with ---)
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            yaml_content = parts[1].strip()
            body = parts[2].strip()
            
            # Simple YAML parsing for key: value pairs
            for line in yaml_content.split('\n'):
                line = line.strip()
                if ':' in line and not line.startswith('#'):
                    key, _, value = line.partition(':')
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    frontmatter[key] = value
    
    return frontmatter, body


def _build_skill_tree(path: Path, base_path: Path) -> dict:
    """Build a tree structure for a skill directory."""
    relative_path = str(path.relative_to(base_path))
    name = path.name
    
    if path.is_dir():
        children = []
        items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        for item in items:
            # Skip hidden files and non-markdown/non-directory items
            if item.name.startswith('.') or item.name == '__pycache__':
                continue
            if item.is_dir() or item.suffix in ['.md', '.py', '.sql', '.yaml', '.yml']:
                children.append(_build_skill_tree(item, base_path))
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


@mcp.tool()
def list_skills() -> dict:
    """
    List all available Databricks skills.
    
    Returns a list of skill directories with their descriptions parsed from
    YAML frontmatter. Skills provide guidance for various Databricks tasks
    like creating dashboards, configuring jobs, working with Unity Catalog, etc.
    
    Returns:
        dict: List of skills with names, descriptions, and available files
    """
    skills_dir = _get_skills_dir()
    
    if not skills_dir.exists():
        return {
            'skills_dir': str(skills_dir),
            'exists': False,
            'skills': [],
            'message': 'Skills directory not found. Skills may not be deployed.'
        }
    
    skills = []
    for item in sorted(skills_dir.iterdir()):
        if item.is_dir() and not item.name.startswith('.') and item.name != 'TEMPLATE':
            # Try to read SKILL.md for metadata
            skill_md = item / 'SKILL.md'
            name = item.name
            description = ""
            
            if skill_md.exists():
                try:
                    content = skill_md.read_text()
                    frontmatter, _ = _parse_skill_frontmatter(content)
                    
                    # Use frontmatter values if available
                    if 'name' in frontmatter:
                        name = frontmatter['name']
                    if 'description' in frontmatter:
                        description = frontmatter['description']
                except Exception:
                    pass
            
            # Get list of files in this skill
            files = []
            for f in item.rglob('*.md'):
                if not f.name.startswith('.'):
                    files.append(str(f.relative_to(item)))
            for f in item.rglob('*.py'):
                if not f.name.startswith('.') and '__pycache__' not in str(f):
                    files.append(str(f.relative_to(item)))
            
            skills.append({
                'name': name,
                'folder': item.name,
                'description': description,
                'has_skill_md': skill_md.exists(),
                'files': sorted(files),
            })
    
    return {
        'skills_dir': str(skills_dir),
        'exists': True,
        'count': len(skills),
        'skills': skills,
    }


@mcp.tool()
def get_skill(skill_name: str, file_path: Optional[str] = None) -> dict:
    """
    Get the content of a skill file.
    
    Retrieves the documentation for a specific Databricks skill, which provides
    guidance on how to perform various tasks like creating dashboards, 
    configuring jobs, working with pipelines, etc.
    
    Args:
        skill_name: Name of the skill folder (e.g., 'aibi-dashboards', 'databricks-jobs')
        file_path: Optional specific file within the skill (e.g., 'examples.md'). 
                   If not provided, returns SKILL.md
    
    Returns:
        dict: Skill content with frontmatter metadata and body
    """
    skills_dir = _get_skills_dir()
    skill_dir = skills_dir / skill_name
    
    if not skill_dir.exists():
        available = [d.name for d in skills_dir.iterdir() if d.is_dir() and not d.name.startswith('.') and d.name != 'TEMPLATE']
        return {
            'error': f"Skill '{skill_name}' not found",
            'available_skills': available
        }
    
    # Determine which file to read
    if file_path:
        target_file = skill_dir / file_path
    else:
        target_file = skill_dir / 'SKILL.md'
    
    if not target_file.exists():
        # List available files in the skill
        available_files = []
        for f in skill_dir.rglob('*'):
            if f.is_file() and not f.name.startswith('.') and '__pycache__' not in str(f):
                available_files.append(str(f.relative_to(skill_dir)))
        return {
            'error': f"File '{file_path or 'SKILL.md'}' not found in skill '{skill_name}'",
            'available_files': sorted(available_files)
        }
    
    # Security check: ensure path is within skill directory
    try:
        target_file.resolve().relative_to(skill_dir.resolve())
    except ValueError:
        return {'error': 'Access denied: path outside skill directory'}
    
    content = target_file.read_text()
    
    # Parse frontmatter for markdown files
    result = {
        'skill_name': skill_name,
        'file_path': str(target_file.relative_to(skill_dir)),
        'size': len(content),
    }
    
    if target_file.suffix == '.md':
        frontmatter, body = _parse_skill_frontmatter(content)
        if frontmatter:
            result['metadata'] = frontmatter
        result['content'] = body
    else:
        result['content'] = content
    
    return result


@mcp.tool()
def get_skill_tree(skill_name: str) -> dict:
    """
    Get the file tree structure of a skill.
    
    Returns a nested structure showing all files and subdirectories
    within a skill directory.
    
    Args:
        skill_name: Name of the skill directory (e.g., 'mlflow-evaluation')
    
    Returns:
        dict: Tree structure of the skill directory
    """
    skills_dir = _get_skills_dir()
    skill_dir = skills_dir / skill_name
    
    if not skill_dir.exists():
        return {
            'error': f"Skill '{skill_name}' not found",
            'available_skills': [d.name for d in skills_dir.iterdir() if d.is_dir() and not d.name.startswith('.')]
        }
    
    tree = _build_skill_tree(skill_dir, skill_dir)
    
    return {
        'skill_name': skill_name,
        'tree': tree['children'] if 'children' in tree else [],
    }


@mcp.tool()
def search_skills(query: str) -> dict:
    """
    Search across all skills for relevant content.
    
    Searches skill names, descriptions, and content for the given query.
    Useful for finding which skill to use for a particular task.
    
    Args:
        query: Search term (case-insensitive)
    
    Returns:
        dict: Matching skills and files with relevance context
    """
    skills_dir = _get_skills_dir()
    query_lower = query.lower()
    
    if not skills_dir.exists():
        return {'error': 'Skills directory not found', 'matches': []}
    
    matches = []
    
    for skill_dir in skills_dir.iterdir():
        if not skill_dir.is_dir() or skill_dir.name.startswith('.'):
            continue
        
        skill_name = skill_dir.name
        
        # Check if query matches skill name
        if query_lower in skill_name.lower():
            matches.append({
                'skill': skill_name,
                'match_type': 'skill_name',
                'file': None,
                'context': f"Skill name matches: {skill_name}",
            })
        
        # Search in markdown files
        for md_file in skill_dir.rglob('*.md'):
            try:
                content = md_file.read_text()
                if query_lower in content.lower():
                    # Extract context around the match
                    idx = content.lower().find(query_lower)
                    start = max(0, idx - 50)
                    end = min(len(content), idx + len(query) + 50)
                    context = content[start:end].replace('\n', ' ').strip()
                    if start > 0:
                        context = '...' + context
                    if end < len(content):
                        context = context + '...'
                    
                    matches.append({
                        'skill': skill_name,
                        'match_type': 'content',
                        'file': str(md_file.relative_to(skill_dir)),
                        'context': context,
                    })
            except Exception:
                pass  # Skip files that can't be read
    
    return {
        'query': query,
        'match_count': len(matches),
        'matches': matches[:20],  # Limit results
    }

#!/usr/bin/env python3
"""Validate skill structure and frontmatter.

Checks:
1. Every skill directory has a SKILL.md file
2. SKILL.md has valid YAML frontmatter with a 'name' field
3. Skills match the ALL_SKILLS list in install_skills.sh
"""

import re
import sys
from pathlib import Path

import yaml

SKILLS_DIR = Path("databricks-skills")
INSTALL_SCRIPT = SKILLS_DIR / "install_skills.sh"
SKIP_DIRS = {"TEMPLATE"}


def parse_frontmatter(content: str) -> dict | None:
    """Extract YAML frontmatter from markdown content."""
    match = re.match(r"^---\n(.+?)\n---", content, re.DOTALL)
    if match:
        try:
            return yaml.safe_load(match.group(1))
        except yaml.YAMLError:
            return None
    return None


def get_databricks_skills_from_script() -> set[str]:
    """Parse DATABRICKS_SKILLS list from install_skills.sh (local skills)."""
    content = INSTALL_SCRIPT.read_text()
    match = re.search(r'DATABRICKS_SKILLS="([^"]+)"', content)
    if match:
        return set(match.group(1).split())
    return set()


def get_all_skills_from_script() -> set[str]:
    """Parse ALL_SKILLS list from install_skills.sh."""
    content = INSTALL_SCRIPT.read_text()
    match = re.search(r'ALL_SKILLS="([^"]+)"', content)
    if match:
        return set(match.group(1).split())
    return set()


def main() -> int:
    errors = []

    # Get actual skill directories
    actual_skills = {
        d.name
        for d in SKILLS_DIR.iterdir()
        if d.is_dir() and d.name not in SKIP_DIRS and not d.name.startswith(".")
    }

    # Get skills registered in install script (only local Databricks skills)
    # MLflow skills are fetched from external repo, not validated locally
    registered_skills = get_databricks_skills_from_script()

    # Validate each skill directory
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        if skill_dir.name in SKIP_DIRS or skill_dir.name.startswith("."):
            continue

        skill_md = skill_dir / "SKILL.md"

        # Check SKILL.md exists
        if not skill_md.exists():
            errors.append(f"{skill_dir.name}: Missing SKILL.md")
            continue

        # Check frontmatter
        content = skill_md.read_text()
        frontmatter = parse_frontmatter(content)

        if frontmatter is None:
            errors.append(f"{skill_dir.name}: Invalid or missing frontmatter in SKILL.md")
        elif "name" not in frontmatter:
            errors.append(f"{skill_dir.name}: Missing 'name' field in frontmatter")

    # Check for skills not in install script
    orphaned = actual_skills - registered_skills
    if orphaned:
        errors.append(f"Skills exist but not in install_skills.sh ALL_SKILLS: {sorted(orphaned)}")

    # Check for skills in script but missing directory
    missing = registered_skills - actual_skills
    if missing:
        errors.append(f"Skills in install_skills.sh but no directory found: {sorted(missing)}")

    # Report results
    if errors:
        print("Skill validation failed:\n")
        for error in errors:
            # GitHub Actions annotation format - shows as error in UI
            print(f"::error::{error}")
        print()
        print(f"Found {len(errors)} error(s)")
        return 1

    print(f"All {len(actual_skills)} skills validated successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())

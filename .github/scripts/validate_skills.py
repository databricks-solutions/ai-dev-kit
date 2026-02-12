#!/usr/bin/env python3
"""Validate skill structure and frontmatter.

Checks:
1. Every skill directory has a SKILL.md file
2. SKILL.md has valid YAML frontmatter per best practices:
   - name: required, ≤64 chars, lowercase letters/numbers/hyphens only,
     no XML tags, no reserved words ("anthropic", "claude")
   - description: required, non-empty, ≤1024 chars, no XML tags
3. Local skill directories are registered in install_skills.sh
   (skill-list variables are auto-discovered, not hardcoded)
"""

import re
import sys
from pathlib import Path

import yaml

SKILLS_DIR = Path("databricks-skills")
INSTALL_SCRIPT = SKILLS_DIR / "install_skills.sh"
SKIP_DIRS = {"TEMPLATE"}

RESERVED_WORDS = {"anthropic", "claude"}
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
XML_TAG_RE = re.compile(r"<[^>]+>")


def parse_frontmatter(content: str) -> dict | None:
    """Extract YAML frontmatter from markdown content."""
    match = re.match(r"^---\n(.+?)\n---", content, re.DOTALL)
    if match:
        try:
            return yaml.safe_load(match.group(1))
        except yaml.YAMLError:
            return None
    return None


def validate_name(name: str) -> list[str]:
    """Validate the name field per best practices."""
    errors = []
    if len(name) > 64:
        errors.append(f"name '{name}' exceeds 64 characters ({len(name)})")
    if not NAME_RE.match(name):
        errors.append(f"name '{name}' must contain only lowercase letters, numbers, and hyphens")
    if XML_TAG_RE.search(name):
        errors.append(f"name '{name}' must not contain XML tags")
    for word in RESERVED_WORDS:
        if word in name:
            errors.append(f"name '{name}' must not contain reserved word '{word}'")
    return errors


def validate_description(description: str) -> list[str]:
    """Validate the description field per best practices."""
    errors = []
    if not description or not description.strip():
        errors.append("description must not be empty")
    if len(description) > 1024:
        errors.append(f"description exceeds 1024 characters ({len(description)})")
    if XML_TAG_RE.search(description):
        errors.append("description must not contain XML tags")
    return errors


def parse_skill_variables(
    content: str,
) -> tuple[dict[str, list[str]], set[str]]:
    """Auto-discover skill-list variables from install_skills.sh.

    Finds all UPPER_CASE="..." variable definitions, resolves $VAR
    references, and returns only variables whose values look like
    space-separated skill names (lowercase-hyphenated strings).

    Returns:
        (resolved_vars, composite_var_names) — composite variables are those
        defined via $VAR references (e.g. ALL_SKILLS="$A $B"). They are
        resolved for the orphan check but excluded from per-variable
        missing-directory checks since their components are validated
        individually.
    """
    # First pass: collect raw variable values
    raw_vars: dict[str, str] = {}
    for match in re.finditer(r'^([A-Z_]+)="([^"]*)"', content, re.MULTILINE):
        raw_vars[match.group(1)] = match.group(2).strip()

    # Second pass: resolve variable references and filter to skill lists
    resolved: dict[str, list[str]] = {}
    composite_vars: set[str] = set()
    for var_name, var_value in raw_vars.items():
        skills: list[str] = []
        has_ref = False
        for token in var_value.split():
            if token.startswith("$"):
                has_ref = True
                ref_name = token.lstrip("$")
                if ref_name in raw_vars:
                    skills.extend(raw_vars[ref_name].split())
            else:
                skills.append(token)
        # Only keep variables whose tokens all look like skill names
        if skills and all(NAME_RE.match(s) for s in skills):
            resolved[var_name] = skills
            if has_ref:
                composite_vars.add(var_name)

    return resolved, composite_vars


def get_local_skill_dirs() -> set[str]:
    """Get actual skill directories on the filesystem."""
    return {
        d.name for d in SKILLS_DIR.iterdir() if d.is_dir() and d.name not in SKIP_DIRS and not d.name.startswith(".")
    }


def main() -> int:
    errors: list[str] = []
    actual_skills = get_local_skill_dirs()

    # --- Validate each skill directory's SKILL.md and frontmatter ---
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        if skill_dir.name in SKIP_DIRS or skill_dir.name.startswith("."):
            continue

        skill_md = skill_dir / "SKILL.md"

        if not skill_md.exists():
            errors.append(f"{skill_dir.name}: Missing SKILL.md")
            continue

        content = skill_md.read_text()
        frontmatter = parse_frontmatter(content)

        if frontmatter is None:
            errors.append(f"{skill_dir.name}: Invalid or missing frontmatter in SKILL.md")
            continue

        # Validate name
        if "name" not in frontmatter:
            errors.append(f"{skill_dir.name}: Missing 'name' field in frontmatter")
        else:
            for err in validate_name(str(frontmatter["name"])):
                errors.append(f"{skill_dir.name}: {err}")

        # Validate description
        if "description" not in frontmatter:
            errors.append(f"{skill_dir.name}: Missing 'description' field in frontmatter")
        else:
            for err in validate_description(str(frontmatter["description"])):
                errors.append(f"{skill_dir.name}: {err}")

    # --- Cross-reference with install_skills.sh ---
    install_content = INSTALL_SCRIPT.read_text()
    skill_vars, composite_vars = parse_skill_variables(install_content)

    # Collect every skill name mentioned across all variables
    all_registered: set[str] = set()
    for skills in skill_vars.values():
        all_registered.update(skills)

    # Every local directory should appear in at least one variable
    orphaned = actual_skills - all_registered
    if orphaned:
        errors.append(f"Skill directories not registered in install_skills.sh: {sorted(orphaned)}")

    # For each *primary* (non-composite) variable where the majority of
    # skills have local dirs, treat it as a "local" variable and flag any
    # missing directories.  Composite variables (e.g. ALL_SKILLS) are
    # skipped because their component variables are validated individually.
    for var_name, skills in skill_vars.items():
        if var_name in composite_vars:
            continue
        skills_set = set(skills)
        local_count = len(skills_set & actual_skills)
        if local_count > len(skills_set) / 2:
            missing = skills_set - actual_skills
            if missing:
                errors.append(f"Skills in {var_name} but no directory found: {sorted(missing)}")

    # --- Report ---
    if errors:
        print("Skill validation failed:\n")
        for error in errors:
            print(f"::error::{error}")
        print()
        print(f"Found {len(errors)} error(s)")
        return 1

    print(f"All {len(actual_skills)} local skills validated successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())

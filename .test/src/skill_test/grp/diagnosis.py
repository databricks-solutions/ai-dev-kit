"""Failure diagnosis - analyze errors and find relevant skill sections."""
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any


@dataclass
class SkillSection:
    """A relevant section from a skill file."""
    file_path: str
    section_name: str
    excerpt: str
    line_number: int


@dataclass
class Diagnosis:
    """Complete diagnosis of a failure."""
    error: str
    code_block: str
    relevant_sections: List[SkillSection]
    suggested_action: str


def find_skill_files(skill_name: str, base_path: str = ".claude/skills") -> List[Path]:
    """Find all markdown files for a skill."""
    skill_path = Path(base_path) / skill_name
    if not skill_path.exists():
        return []
    return list(skill_path.glob("**/*.md"))


def extract_sections(file_path: Path) -> List[Dict[str, Any]]:
    """Extract markdown sections from a file."""
    content = file_path.read_text()
    sections = []

    # Split by headers
    pattern = r'^(#{1,3})\s+(.+)$'
    lines = content.split('\n')
    current_section = None
    current_content = []
    current_line = 0

    for i, line in enumerate(lines):
        match = re.match(pattern, line)
        if match:
            if current_section:
                sections.append({
                    "name": current_section,
                    "content": '\n'.join(current_content),
                    "line": current_line
                })
            current_section = match.group(2)
            current_content = []
            current_line = i + 1
        elif current_section:
            current_content.append(line)

    if current_section:
        sections.append({
            "name": current_section,
            "content": '\n'.join(current_content),
            "line": current_line
        })

    return sections


def find_relevant_sections(
    error: str,
    code_block: str,
    skill_name: str
) -> List[SkillSection]:
    """Find skill sections relevant to an error."""
    relevant = []

    # Extract keywords from error and code
    keywords = set()

    # Common error patterns
    if "STREAMING TABLE" in code_block or "streaming" in error.lower():
        keywords.add("streaming")
    if "CLUSTER BY" in code_block or "partition" in error.lower():
        keywords.update(["cluster", "partition"])
    if "read_files" in code_block or "autoloader" in error.lower():
        keywords.update(["read_files", "autoloader", "ingestion"])

    # Search skill files
    for file_path in find_skill_files(skill_name):
        sections = extract_sections(file_path)
        for section in sections:
            section_lower = section["content"].lower()
            name_lower = section["name"].lower()

            # Check if section is relevant
            relevance_score = sum(
                1 for kw in keywords
                if kw in section_lower or kw in name_lower
            )

            if relevance_score > 0:
                # Extract a relevant excerpt (first 200 chars with keyword)
                excerpt = section["content"][:200]
                if len(section["content"]) > 200:
                    excerpt += "..."

                # Get relative path from .claude/skills
                try:
                    rel_path = file_path.relative_to(".claude/skills")
                except ValueError:
                    rel_path = file_path

                relevant.append(SkillSection(
                    file_path=str(rel_path),
                    section_name=section["name"],
                    excerpt=excerpt.strip(),
                    line_number=section["line"]
                ))

    return relevant[:5]  # Limit to top 5 relevant sections


def analyze_failure(
    error: str,
    code_block: str,
    skill_name: str
) -> Diagnosis:
    """Analyze a failure and produce diagnosis."""
    relevant = find_relevant_sections(error, code_block, skill_name)

    # Generate suggested action
    suggested_action = "Review the relevant skill sections and update documentation."

    if "syntax" in error.lower():
        suggested_action = "Check for syntax examples in skill documentation."
    elif "import" in error.lower():
        suggested_action = "Verify import statements match documented patterns."
    elif "STREAMING TABLE" in code_block and "OR REFRESH" not in code_block:
        suggested_action = "Update skill to emphasize 'CREATE OR REFRESH STREAMING TABLE' syntax."

    return Diagnosis(
        error=error,
        code_block=code_block,
        relevant_sections=relevant,
        suggested_action=suggested_action
    )

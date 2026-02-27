#!/usr/bin/env python3
"""Generate ground_truth.yaml and manifest.yaml for skills missing test cases.

Reads each SKILL.md, extracts code examples, headers, and key patterns,
then generates test cases that enable GEPA scorers to produce real signal.

Usage:
    # Generate for a specific skill
    uv run python .test/scripts/generate_ground_truth.py databricks-metric-views

    # Generate for all missing skills
    uv run python .test/scripts/generate_ground_truth.py --all

    # Preview without writing (dry run)
    uv run python .test/scripts/generate_ground_truth.py --all --dry-run
"""

import argparse
import re
import sys
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CodeBlock:
    language: str
    code: str
    context: str  # surrounding prose/header text


@dataclass
class Section:
    level: int  # 2 for ##, 3 for ###
    title: str
    content: str
    code_blocks: list[CodeBlock] = field(default_factory=list)


@dataclass
class Pattern:
    pattern: str
    description: str
    min_count: int = 1


# ---------------------------------------------------------------------------
# SKILL.md parsing
# ---------------------------------------------------------------------------

def extract_frontmatter(content: str) -> dict[str, str]:
    """Extract YAML frontmatter from SKILL.md."""
    m = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if m:
        try:
            return yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            return {}
    return {}


def extract_code_blocks(content: str) -> list[CodeBlock]:
    """Extract fenced code blocks with their language and surrounding context."""
    blocks = []
    # Match ```lang ... ```
    for m in re.finditer(
        r"```(\w+)\s*\n(.*?)```",
        content,
        re.DOTALL,
    ):
        lang = m.group(1).lower()
        code = m.group(2).strip()
        # Get surrounding context (up to 200 chars before)
        start = max(0, m.start() - 200)
        ctx = content[start : m.start()].strip()
        # Find the nearest header
        header_match = re.search(r"#+\s+(.+)", ctx)
        context = header_match.group(1) if header_match else ctx[-100:] if ctx else ""
        blocks.append(CodeBlock(language=lang, code=code, context=context))
    return blocks


def extract_sections(content: str) -> list[Section]:
    """Extract H2 and H3 sections with their content and code blocks."""
    # Remove frontmatter
    content = re.sub(r"^---\s*\n.*?\n---\s*\n", "", content, flags=re.DOTALL)

    sections = []
    # Split by headers
    parts = re.split(r"(^#{2,3}\s+.+$)", content, flags=re.MULTILINE)

    current_title = ""
    current_level = 0
    current_content = ""

    for part in parts:
        header_match = re.match(r"^(#{2,3})\s+(.+)$", part)
        if header_match:
            # Save previous section
            if current_title:
                code_blocks = extract_code_blocks(current_content)
                sections.append(Section(
                    level=current_level,
                    title=current_title,
                    content=current_content.strip(),
                    code_blocks=code_blocks,
                ))
            current_level = len(header_match.group(1))
            current_title = header_match.group(2).strip()
            current_content = ""
        else:
            current_content += part

    # Don't forget last section
    if current_title:
        code_blocks = extract_code_blocks(current_content)
        sections.append(Section(
            level=current_level,
            title=current_title,
            content=current_content.strip(),
            code_blocks=code_blocks,
        ))

    return sections


def extract_patterns_from_code(code: str, language: str) -> list[Pattern]:
    """Extract function/class/keyword patterns from a code block."""
    patterns = []

    if language in ("python", "py"):
        # Function calls: word(
        for m in re.finditer(r"\b([a-z_]\w+)\s*\(", code):
            name = m.group(1)
            if name not in ("print", "str", "int", "float", "len", "range", "list",
                            "dict", "set", "tuple", "type", "isinstance", "if", "for",
                            "while", "return", "import", "from", "as", "with", "round",
                            "max", "min", "abs", "sum", "enumerate", "zip", "map",
                            "filter", "sorted", "any", "all", "open", "format", "bool",
                            "append", "extend"):
                patterns.append(Pattern(
                    pattern=re.escape(name),
                    description=f"Uses {name}()",
                ))
        # Class names: CapitalWord
        for m in re.finditer(r"\b([A-Z][a-zA-Z]+(?:[A-Z][a-zA-Z]+)*)\b", code):
            name = m.group(1)
            if name not in ("True", "False", "None", "String", "Int", "Float",
                            "IMPORTANT", "NOTE", "WARNING", "TODO"):
                patterns.append(Pattern(
                    pattern=re.escape(name),
                    description=f"References {name}",
                ))
    elif language in ("sql",):
        # SQL keywords and functions
        for m in re.finditer(r"\b(CREATE\s+(?:OR\s+REPLACE\s+)?(?:MATERIALIZED\s+VIEW|VIEW|TABLE|PROCEDURE|CONNECTION))", code, re.IGNORECASE):
            patterns.append(Pattern(
                pattern=m.group(1).replace("  ", " "),
                description=f"Uses {m.group(1).strip()}",
            ))
        # Function calls in SQL
        for m in re.finditer(r"\b([a-z_]\w+)\s*\(", code, re.IGNORECASE):
            name = m.group(1).lower()
            if name not in ("select", "from", "where", "and", "or", "not",
                            "group", "order", "having", "limit", "insert",
                            "update", "delete", "values", "into", "set",
                            "join", "on", "as", "case", "when", "then",
                            "else", "end", "in", "between", "like", "is",
                            "null", "exists", "count", "sum", "avg", "min", "max"):
                patterns.append(Pattern(
                    pattern=re.escape(name),
                    description=f"Uses {name}() function",
                ))
    elif language in ("yaml", "yml"):
        # Key YAML keys
        for m in re.finditer(r"^\s*(\w[\w_-]+):", code, re.MULTILINE):
            key = m.group(1)
            if key not in ("name", "description", "type", "default", "value",
                           "true", "false"):
                patterns.append(Pattern(
                    pattern=re.escape(key),
                    description=f"Includes {key} configuration",
                ))
    elif language in ("bash", "sh"):
        # CLI commands
        for m in re.finditer(r"\b(databricks\s+\w+(?:\s+\w+)?)", code):
            patterns.append(Pattern(
                pattern=re.escape(m.group(1)),
                description=f"Uses {m.group(1)} command",
            ))

    # Deduplicate by pattern string
    seen = set()
    unique = []
    for p in patterns:
        if p.pattern not in seen:
            seen.add(p.pattern)
            unique.append(p)
    return unique


def extract_facts_from_section(section: Section) -> list[str]:
    """Extract key factual statements from a section's prose."""
    facts = []
    # Look for bullet points with key info
    for line in section.content.split("\n"):
        line = line.strip()
        # Bullet points with bold terms
        m = re.match(r"[-*]\s+\*\*(.+?)\*\*\s*[-:]\s*(.+)", line)
        if m:
            facts.append(f"{m.group(1)}: {m.group(2).strip()}")
            continue
        # Table rows with useful info
        m = re.match(r"\|\s*`?(\w[\w_.-]+)`?\s*\|\s*(.+?)\s*\|", line)
        if m and not m.group(1).startswith("-"):
            facts.append(f"{m.group(1)}: {m.group(2).strip()}")

    return facts[:5]  # Limit to top 5


# ---------------------------------------------------------------------------
# Test case generation
# ---------------------------------------------------------------------------

def generate_prompt_from_section(section: Section, skill_name: str) -> str:
    """Generate a natural user prompt from a section's content."""
    title = section.title

    # Map section titles to natural prompts
    prompt_templates = {
        "Quick Start": f"Show me how to get started with {skill_name.replace('databricks-', '')}",
        "Create": f"Create a {title.lower().replace('create ', '')}",
        "Common Patterns": f"Show me common patterns for {skill_name.replace('databricks-', '')}",
        "Configuration": f"How do I configure {skill_name.replace('databricks-', '')}?",
        "Filtering": f"How do I filter results when querying?",
        "Common Issues": f"What are common issues with {skill_name.replace('databricks-', '')}?",
    }

    # Check if any template matches
    for key, template in prompt_templates.items():
        if key.lower() in title.lower():
            return template

    # Generate from code blocks if present
    if section.code_blocks:
        block = section.code_blocks[0]
        if block.language in ("python", "py"):
            return f"Write Python code to {title.lower()}"
        elif block.language == "sql":
            return f"Write SQL to {title.lower()}"
        elif block.language in ("yaml", "yml"):
            return f"Show me the YAML configuration for {title.lower()}"
        elif block.language in ("bash", "sh"):
            return f"Show me the CLI commands to {title.lower()}"

    # Default: use section title
    return f"How do I {title.lower()} with {skill_name.replace('databricks-', '')}?"


def generate_response_from_section(section: Section) -> str:
    """Generate an expected response from a section's code blocks and content."""
    parts = []

    # Add brief explanation from prose
    prose_lines = []
    for line in section.content.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("|") and not stripped.startswith("```"):
            if not stripped.startswith("#"):
                prose_lines.append(stripped)
        if len(prose_lines) >= 3:
            break

    if prose_lines:
        parts.append(" ".join(prose_lines[:3]))

    # Add code blocks
    for block in section.code_blocks[:2]:  # Max 2 code blocks per test case
        parts.append(f"\n```{block.language}\n{block.code}\n```")

    return "\n\n".join(parts) if parts else section.content[:500]


def build_test_case(
    skill_name: str,
    section: Section,
    index: int,
    difficulty: str = "easy",
) -> dict:
    """Build a single test case from a section."""
    # Generate ID
    feature = re.sub(r"[^a-z0-9]+", "_", section.title.lower()).strip("_")[:30]
    case_id = f"{skill_name}_{feature}_{index:03d}"

    prompt = generate_prompt_from_section(section, skill_name)
    response = generate_response_from_section(section)

    # Collect patterns from all code blocks
    all_patterns = []
    for block in section.code_blocks:
        all_patterns.extend(extract_patterns_from_code(block.code, block.language))

    # Limit patterns to top 5 most relevant
    patterns_data = []
    seen = set()
    for p in all_patterns[:8]:
        if p.pattern not in seen:
            seen.add(p.pattern)
            patterns_data.append({
                "pattern": p.pattern,
                "min_count": p.min_count,
                "description": p.description,
            })
        if len(patterns_data) >= 5:
            break

    # Extract facts
    facts = extract_facts_from_section(section)
    if not facts:
        # Fall back to key terms from code blocks
        for block in section.code_blocks:
            if block.language in ("python", "py"):
                facts.append(f"Uses Python {block.language}")
            elif block.language == "sql":
                facts.append("Uses SQL syntax")

    # Build guidelines from section context
    guidelines = []
    if any(b.language in ("python", "py") for b in section.code_blocks):
        guidelines.append("Code must be valid Python syntax")
    if any(b.language == "sql" for b in section.code_blocks):
        guidelines.append("SQL must follow Databricks SQL syntax")
    if section.code_blocks:
        guidelines.append("Response must include working code examples")

    return {
        "id": case_id,
        "inputs": {"prompt": prompt},
        "outputs": {
            "response": response,
            "execution_success": True,
        },
        "expectations": {
            "expected_facts": facts if facts else [],
            "expected_patterns": patterns_data if patterns_data else [],
            "guidelines": guidelines if guidelines else [],
        },
        "metadata": {
            "category": "happy_path",
            "difficulty": difficulty,
            "source": "auto_generated",
            "section": section.title,
        },
    }


def detect_languages(sections: list[Section]) -> set[str]:
    """Detect which languages are used across all sections."""
    langs = set()
    for s in sections:
        for b in s.code_blocks:
            langs.add(b.language)
    return langs


def generate_manifest(skill_name: str, description: str, languages: set[str]) -> dict:
    """Generate a manifest.yaml for a skill."""
    enabled_scorers = ["pattern_adherence", "no_hallucinated_apis", "expected_facts_present"]
    if "python" in languages or "py" in languages:
        enabled_scorers.insert(0, "python_syntax")
    if "sql" in languages:
        enabled_scorers.insert(0, "sql_syntax")

    default_guidelines = [
        "Response must address the user's request completely",
        "Code examples must follow documented best practices",
        "Response must use modern APIs (not deprecated ones)",
    ]

    return {
        "skill_name": skill_name,
        "description": description or f"Test cases for {skill_name} skill",
        "scorers": {
            "enabled": enabled_scorers,
            "llm_scorers": ["Safety", "guidelines_from_expectations"],
            "default_guidelines": default_guidelines,
            "trace_expectations": {
                "tool_limits": {"Bash": 10, "Read": 20},
                "token_budget": {"max_total": 100000},
                "required_tools": ["Read"],
                "banned_tools": [],
                "expected_files": [],
            },
        },
        "quality_gates": {
            "syntax_valid": 1.0,
            "pattern_adherence": 0.9,
            "execution_success": 0.8,
        },
    }


# ---------------------------------------------------------------------------
# Section selection: pick the best sections for test cases
# ---------------------------------------------------------------------------

def select_sections_for_tests(sections: list[Section], target: int = 7) -> list[Section]:
    """Select the best sections for test case generation.

    Prefers sections with code blocks and diverse topics.
    """
    # Score sections by relevance
    scored = []
    for s in sections:
        score = 0
        # Sections with code are much more valuable
        score += len(s.code_blocks) * 3
        # Prefer H2 over H3
        if s.level == 2:
            score += 1
        # Skip meta sections
        skip_titles = {"related skills", "resources", "reference files", "notes",
                       "common issues", "current limitations", "sdk version requirements",
                       "prerequisites", "prerequisites check", "when to use",
                       "environment configuration", "best practices"}
        if s.title.lower() in skip_titles:
            score -= 5
        # Boost pattern/example sections
        if any(kw in s.title.lower() for kw in ("pattern", "example", "start", "create", "common")):
            score += 2
        # Boost if has substantial content
        if len(s.content) > 200:
            score += 1

        scored.append((score, s))

    # Sort by score descending, take top N
    scored.sort(key=lambda x: x[0], reverse=True)
    selected = [s for _, s in scored if _ > 0][:target]

    return selected


# ---------------------------------------------------------------------------
# Main generation logic
# ---------------------------------------------------------------------------

def generate_skill_tests(skill_name: str, repo_root: Path) -> tuple[list[dict], dict]:
    """Generate test cases and manifest for a single skill.

    Returns:
        (test_cases, manifest) tuple
    """
    skill_md_path = repo_root / "databricks-skills" / skill_name / "SKILL.md"
    if not skill_md_path.exists():
        raise FileNotFoundError(f"SKILL.md not found: {skill_md_path}")

    content = skill_md_path.read_text()
    frontmatter = extract_frontmatter(content)
    description = frontmatter.get("description", "")
    sections = extract_sections(content)

    # Select best sections for test cases
    selected = select_sections_for_tests(sections, target=7)

    if not selected:
        raise ValueError(f"No suitable sections found in {skill_md_path}")

    # Generate test cases
    test_cases = []
    difficulties = ["easy", "easy", "easy", "medium", "medium", "medium", "hard", "hard"]
    for i, section in enumerate(selected):
        difficulty = difficulties[i] if i < len(difficulties) else "medium"
        tc = build_test_case(skill_name, section, i + 1, difficulty)
        test_cases.append(tc)

    # Generate manifest
    languages = detect_languages(sections)
    manifest = generate_manifest(skill_name, description, languages)

    return test_cases, manifest


def write_skill_tests(
    skill_name: str,
    test_cases: list[dict],
    manifest: dict,
    output_dir: Path,
    dry_run: bool = False,
) -> None:
    """Write ground_truth.yaml and manifest.yaml for a skill."""
    skill_dir = output_dir / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)

    gt_data = {
        "metadata": {
            "skill_name": skill_name,
            "version": "0.1.0",
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f"),
        },
        "test_cases": test_cases,
    }

    gt_path = skill_dir / "ground_truth.yaml"
    manifest_path = skill_dir / "manifest.yaml"

    if dry_run:
        print(f"  [DRY RUN] Would write {gt_path} ({len(test_cases)} test cases)")
        print(f"  [DRY RUN] Would write {manifest_path}")
        return

    # Custom YAML representer for multiline strings
    class MultilineDumper(yaml.SafeDumper):
        pass

    def str_representer(dumper, data):
        if "\n" in data:
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
        return dumper.represent_scalar("tag:yaml.org,2002:str", data)

    MultilineDumper.add_representer(str, str_representer)

    with open(gt_path, "w") as f:
        yaml.dump(gt_data, f, Dumper=MultilineDumper, default_flow_style=False,
                  sort_keys=False, allow_unicode=True, width=120)

    with open(manifest_path, "w") as f:
        yaml.dump(manifest, f, Dumper=MultilineDumper, default_flow_style=False,
                  sort_keys=False, allow_unicode=True, width=120)

    print(f"  Wrote {gt_path} ({len(test_cases)} test cases)")
    print(f"  Wrote {manifest_path}")


# ---------------------------------------------------------------------------
# Skills that are missing test cases
# ---------------------------------------------------------------------------

MISSING_SKILLS = [
    "databricks-app-apx",
    "databricks-config",
    "databricks-dbsql",
    "databricks-docs",
    "databricks-jobs",
    "databricks-lakebase-autoscale",
    "databricks-lakebase-provisioned",
    "databricks-metric-views",
    "databricks-mlflow-evaluation",
    "databricks-python-sdk",
    "databricks-spark-structured-streaming",
    "databricks-synthetic-data-generation",
    "databricks-unity-catalog",
    "databricks-unstructured-pdf-generation",
    "databricks-vector-search",
]


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate ground_truth.yaml test cases for skills",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "skill_name",
        nargs="?",
        help="Skill name (e.g., databricks-metric-views)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Generate for all missing skills",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing files",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing ground_truth.yaml files",
    )

    args = parser.parse_args()

    if not args.skill_name and not args.all:
        parser.error("Provide a skill name or use --all")

    # Find repo root
    repo_root = Path(__file__).resolve().parent.parent.parent
    if not (repo_root / "databricks-skills").exists():
        print(f"ERROR: databricks-skills/ not found at {repo_root}", file=sys.stderr)
        sys.exit(1)

    output_dir = repo_root / ".test" / "skills"

    # Determine which skills to process
    if args.all:
        skills = MISSING_SKILLS
    else:
        skills = [args.skill_name]

    success = 0
    errors = 0

    for skill_name in skills:
        print(f"\n{'=' * 50}")
        print(f"  {skill_name}")
        print(f"{'=' * 50}")

        # Check if already exists
        if not args.force and (output_dir / skill_name / "ground_truth.yaml").exists():
            print(f"  SKIP: ground_truth.yaml already exists (use --force to overwrite)")
            continue

        try:
            test_cases, manifest = generate_skill_tests(skill_name, repo_root)
            write_skill_tests(skill_name, test_cases, manifest, output_dir, dry_run=args.dry_run)
            success += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            errors += 1

    print(f"\n{'=' * 50}")
    print(f"  Done: {success} generated, {errors} errors")
    print(f"{'=' * 50}")

    sys.exit(1 if errors > 0 else 0)


if __name__ == "__main__":
    main()

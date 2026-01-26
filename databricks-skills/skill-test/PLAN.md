# Implementation Plan: skill-test Framework

## Overview

A skill-testing framework for evaluating Databricks skills with **offline YAML-first** approach, **human-in-the-loop review**, and **interactive skill improvement**. Unity Catalog datasets are deferred to a later phase.

**Key Architectural Decisions:**
1. **Offline YAML first** - Local YAML files are primary data source; UC datasets later via DatasetSource abstraction
2. **Pre-computed outputs** - Uses Pattern 2 from mlflow-evaluation (no predict_fn required)
3. **Human review required** - All ground truth cases need human approval, even successful executions
4. **Skill improvement loop** - Test failures trigger diagnosis and skill updates
5. **Skill routing evaluation** - NEW: Tests Claude Code's ability to route prompts to correct skills

---

## Directory Structure

```
databricks-skills/skill-test/
├── SKILL.md                           # Navigation hub with workflows
├── PLAN.md                            # This file
├── references/
│   ├── GOTCHAS.md                     # Common mistakes to avoid
│   ├── patterns-test-definitions.md  # How to write test cases (YAML)
│   └── patterns-scorers.md           # Scorer implementation patterns
│
├── src/                               # Python implementation
│   ├── __init__.py
│   ├── config.py                      # Quality gates, env vars, settings
│   ├── dataset.py                     # DatasetSource abstraction (YAML-only Phase 1)
│   ├── ground_truth.py                # Dataclasses + YAML loader
│   ├── scorers/
│   │   ├── __init__.py
│   │   ├── universal.py               # Tier 1: Syntax, patterns, artifacts
│   │   ├── routing.py                 # NEW: Skill routing scorer
│   │   └── llm_judges.py              # Tier 3: Guidelines-based judges
│   ├── grp/
│   │   ├── __init__.py
│   │   ├── executor.py                # Code block extraction + execution
│   │   ├── pipeline.py                # Generate → Execute → Fix → Review → Promote
│   │   ├── diagnosis.py               # Failure analysis + skill section finder
│   │   └── reviewer.py                # Human review interface + approval recording
│   └── runners/
│       ├── __init__.py
│       ├── evaluate.py                # Main evaluation runner
│       └── compare.py                 # Version comparison
│
├── skills/                            # Per-skill test definitions
│   ├── _routing/                      # NEW: Skill routing test cases
│   │   ├── manifest.yaml
│   │   └── ground_truth.yaml
│   ├── spark-declarative-pipelines/
│   │   ├── manifest.yaml
│   │   ├── ground_truth.yaml          # Verified test cases
│   │   └── candidates.yaml            # GRP candidates pending review
│   ├── databricks-app-apx/
│   ├── databricks-app-python/
│   ├── asset-bundles/
│   ├── databricks-python-sdk/
│   ├── databricks-jobs/
│   ├── synthetic-data-generation/
│   ├── mlflow-evaluation/
│   └── agent-bricks/
│
└── baselines/                         # Regression baselines (JSON)
    ├── spark-declarative-pipelines.json
    └── routing.json
```

---

## Data Architecture: Offline YAML First

### Phase 1: Local YAML (Current Focus)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATA FLOW (Phase 1)                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────┐     ┌──────────────────┐                             │
│  │  Manual YAML     │     │  GRP Pipeline    │                             │
│  │  (human-written) │     │  (generated)     │                             │
│  └────────┬─────────┘     └────────┬─────────┘                             │
│           │                        │                                        │
│           ▼                        ▼                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                    YAMLDatasetSource.load()                          │  │
│  │                    (src/dataset.py)                                  │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                    │                                        │
│                                    ▼                                        │
│           ┌────────────────────────────────────────────────┐               │
│           │     Local YAML File (ground_truth.yaml)        │               │
│           │     skills/{skill-name}/ground_truth.yaml      │               │
│           │                                                │               │
│           │  - inputs: dict (prompt)                       │               │
│           │  - outputs: dict (pre-computed response)       │               │
│           │  - expectations: dict (facts, patterns)        │               │
│           │  - metadata: dict (source, reviewer, commit)   │               │
│           └────────────────────────────────────────────────┘               │
│                                    │                                        │
│                                    ▼                                        │
│           ┌────────────────────────────────────────────────┐               │
│           │          mlflow.genai.evaluate()               │               │
│           │       (pre-computed outputs, no predict_fn)    │               │
│           └────────────────────────────────────────────────┘               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Phase 2: Unity Catalog (Later)

```python
# DatasetSource abstraction enables future UC integration
class DatasetSource(Protocol):
    def load(self) -> List[EvalRecord]: ...

# Phase 1: YAML (implemented)
YAMLDatasetSource(yaml_path).load()  # Returns list[dict]

# Phase 2: UC (stub for now)
UCDatasetSource(uc_table_name).load()  # Raises NotImplementedError
```

---

## Extended GRP Workflow: Generate → Execute → Fix → Review → Promote

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  GENERATE   │ →  │   EXECUTE   │ →  │    FIX      │ →  │   REVIEW    │ →  │   PROMOTE   │
│ Invoke skill│    │ Run code    │    │ (if failed) │    │ Human MUST  │    │ Add to GT   │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
                         │                   │                   │
                         ▼                   ▼                   ▼
                   Pass/Fail         Show diagnosis       Record approval
                                     Update skill         with metadata
                                     Retest
```

### Human Review (Required for ALL)

- Even successful code executions need human approval before becoming ground truth
- Review interface shows: prompt, response, execution results, expectations
- Human can: **Approve**, **Reject with reason**, **Edit expectations**

### Failure Diagnosis

When execution fails, show:
1. **Error details** - Exception, stack trace, line numbers
2. **Relevant skill sections** - Parse SKILL.md, show sections that may need updating
3. **Pattern matches** - Which documented patterns were violated

```yaml
# Diagnosis output example
failure:
  error: "SyntaxError: invalid syntax at line 5"
  code_block: |
    CREATE STREAMING TABLE...  # Missing OR REFRESH
  relevant_skill_sections:
    - file: "spark-declarative-pipelines/SKILL.md"
      section: "## Streaming Tables"
      excerpt: "Always use CREATE OR REFRESH STREAMING TABLE..."
    - file: "spark-declarative-pipelines/1-ingestion-patterns.md"
      section: "## Bronze Ingestion"
      excerpt: "Pattern: CREATE OR REFRESH STREAMING TABLE..."
  suggested_action: "Update skill to emphasize 'OR REFRESH' keyword"
```

### Skill Update Tracking (Dual: Git + YAML Metadata)

**Git tracking:**
```bash
# Auto-generated commit message when skill is fixed
git commit -m "fix(spark-declarative-pipelines): Add OR REFRESH emphasis

Triggered by: test case sdp_bronze_001
Error: Missing OR REFRESH keyword in streaming table
Fixes: SKILL.md line 45"
```

**YAML metadata:**
```yaml
test_cases:
  - id: "sdp_bronze_001"
    # ... inputs, outputs, expectations ...
    metadata:
      category: "happy_path"
      source: "grp"
      # Traceability fields
      approved_by: "alex.miller"
      approved_at: "2026-01-23T10:30:00Z"
      skill_version: "1.2.0"        # Skill version at approval time
      fixed_by_commit: "abc123"     # If this test triggered a skill fix
      fix_description: "Added OR REFRESH emphasis in SKILL.md"
```

---

## Key Files and Code

### 1. Configuration (`src/config.py`)

```python
"""Configuration for skill-test framework."""
import os
from dataclasses import dataclass, field
from typing import List

@dataclass
class QualityGate:
    """A single quality gate threshold."""
    metric: str
    threshold: float
    comparison: str = ">="  # >=, >, ==, <, <=

@dataclass
class QualityGates:
    """Quality thresholds that must pass for evaluation success."""
    gates: List[QualityGate] = field(default_factory=lambda: [
        QualityGate("syntax_valid/score/mean", 1.0),        # 100% - all code must parse
        QualityGate("pattern_adherence/score/mean", 0.90),  # 90% - follow patterns
        QualityGate("no_hallucinated_apis/score/mean", 1.0),# 100% - no fake APIs
        QualityGate("execution_success/score/mean", 0.80),  # 80% - code runs
        QualityGate("routing_accuracy/score/mean", 0.90),   # 90% - correct routing
    ])

@dataclass
class MLflowConfig:
    """MLflow configuration from environment variables."""
    tracking_uri: str = field(
        default_factory=lambda: os.getenv("MLFLOW_TRACKING_URI", "databricks")
    )
    experiment_name: str = field(
        default_factory=lambda: os.getenv(
            "MLFLOW_EXPERIMENT_NAME",
            "/Shared/skill-tests"
        )
    )

@dataclass
class SkillTestConfig:
    """Main configuration for skill-test framework."""
    quality_gates: QualityGates = field(default_factory=QualityGates)
    mlflow: MLflowConfig = field(default_factory=MLflowConfig)

    # Paths
    skills_root: str = "databricks-skills"
    test_definitions_path: str = "databricks-skills/skill-test/skills"

    # GRP settings
    grp_timeout_seconds: int = 30
    grp_max_retries: int = 3
    human_review_required: bool = True  # Always True for ground truth
```

### 2. Dataset Abstraction (`src/dataset.py`)

```python
"""DatasetSource abstraction - YAML-only initially, UC interface defined for later."""
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional, Protocol
import yaml

@dataclass
class EvalRecord:
    """Standard evaluation record format (matches mlflow-evaluation patterns)."""
    id: str
    inputs: Dict[str, Any]
    outputs: Optional[Dict[str, Any]] = None  # Pre-computed for Pattern 2
    expectations: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_eval_dict(self) -> Dict[str, Any]:
        """Convert to MLflow evaluation format."""
        result = {"inputs": self.inputs}
        if self.outputs:
            result["outputs"] = self.outputs
        if self.expectations:
            result["expectations"] = self.expectations
        return result

class DatasetSource(Protocol):
    """Protocol for dataset sources - enables future UC integration."""

    def load(self) -> List[EvalRecord]:
        """Load evaluation records."""
        ...

@dataclass
class YAMLDatasetSource:
    """Load evaluation dataset from YAML file (Phase 1 implementation)."""
    yaml_path: Path

    def load(self) -> List[EvalRecord]:
        """Load records from YAML ground_truth.yaml file."""
        with open(self.yaml_path) as f:
            data = yaml.safe_load(f)

        records = []
        for case in data.get("test_cases", []):
            records.append(EvalRecord(
                id=case["id"],
                inputs=case["inputs"],
                outputs=case.get("outputs"),
                expectations=case.get("expectations"),
                metadata=case.get("metadata", {})
            ))
        return records

    def save(self, records: List[EvalRecord]) -> None:
        """Save records back to YAML file."""
        data = {
            "test_cases": [
                {
                    "id": r.id,
                    "inputs": r.inputs,
                    "outputs": r.outputs,
                    "expectations": r.expectations,
                    "metadata": r.metadata
                }
                for r in records
            ]
        }
        with open(self.yaml_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

@dataclass
class UCDatasetSource:
    """Load evaluation dataset from Unity Catalog (Phase 2 - stub only)."""
    uc_table_name: str

    def load(self) -> List[EvalRecord]:
        """Placeholder for UC integration."""
        raise NotImplementedError(
            "UC datasets deferred to Phase 2. "
            "Use YAMLDatasetSource for now."
        )

def get_dataset_source(skill_name: str, base_path: Path = None) -> DatasetSource:
    """Get the appropriate dataset source for a skill."""
    if base_path is None:
        base_path = Path("databricks-skills/skill-test/skills")

    yaml_path = base_path / skill_name / "ground_truth.yaml"
    if yaml_path.exists():
        return YAMLDatasetSource(yaml_path)

    raise FileNotFoundError(f"No ground_truth.yaml found for {skill_name}")
```

### 3. GRP Executor (`src/grp/executor.py`)

```python
"""Execute code blocks from skill responses to verify they work."""
import ast
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Optional
import time

@dataclass
class ExecutionResult:
    """Result of code block execution."""
    success: bool
    output: str
    error: Optional[str] = None
    execution_time_ms: float = 0

@dataclass
class CodeBlock:
    """Extracted code block with metadata."""
    language: str
    code: str
    line_number: int

def extract_code_blocks(response: str) -> List[CodeBlock]:
    """Extract code blocks from markdown response."""
    pattern = r'```(\w+)\n(.*?)```'
    blocks = []

    for match in re.finditer(pattern, response, re.DOTALL):
        language = match.group(1).lower()
        code = match.group(2)
        line_number = response[:match.start()].count('\n') + 1
        blocks.append(CodeBlock(language, code, line_number))

    return blocks

def verify_python_syntax(code: str) -> Tuple[bool, Optional[str]]:
    """Verify Python code syntax without execution."""
    try:
        ast.parse(code)
        return True, None
    except SyntaxError as e:
        return False, f"Line {e.lineno}: {e.msg}"

def execute_python_block(
    code: str,
    timeout_seconds: int = 30,
    verify_imports: bool = True
) -> ExecutionResult:
    """
    Execute Python code block.

    For safety, this verifies syntax and imports.
    Full execution requires sandbox environment.
    """
    start_time = time.time()

    # Verify syntax
    syntax_ok, syntax_error = verify_python_syntax(code)
    if not syntax_ok:
        return ExecutionResult(
            success=False,
            output="",
            error=f"Syntax error: {syntax_error}",
            execution_time_ms=(time.time() - start_time) * 1000
        )

    # Verify imports resolve
    if verify_imports:
        try:
            tree = ast.parse(code)
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name.split('.')[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module.split('.')[0])

            for imp in imports:
                try:
                    __import__(imp)
                except ImportError as e:
                    return ExecutionResult(
                        success=False,
                        output="",
                        error=f"Import error: {e}",
                        execution_time_ms=(time.time() - start_time) * 1000
                    )
        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Import analysis failed: {e}",
                execution_time_ms=(time.time() - start_time) * 1000
            )

    return ExecutionResult(
        success=True,
        output="Syntax valid, imports resolved",
        error=None,
        execution_time_ms=(time.time() - start_time) * 1000
    )

def verify_sql_structure(code: str) -> ExecutionResult:
    """Verify SQL code structure (cannot actually execute)."""
    issues = []

    # Check for valid SQL statements
    statements = ["SELECT", "CREATE", "INSERT", "UPDATE", "DELETE", "WITH", "MERGE"]
    has_statement = any(stmt in code.upper() for stmt in statements)
    if not has_statement:
        issues.append("No recognizable SQL statement found")

    # Check balanced constructs
    if code.count('(') != code.count(')'):
        issues.append("Unbalanced parentheses")

    if issues:
        return ExecutionResult(
            success=False,
            output="",
            error="; ".join(issues)
        )

    return ExecutionResult(
        success=True,
        output="SQL structure valid",
        error=None
    )

def execute_code_blocks(response: str) -> Tuple[int, int, List[dict]]:
    """
    Execute all code blocks in a response.

    Returns: (total_blocks, passed_blocks, execution_details)
    """
    blocks = extract_code_blocks(response)
    details = []
    passed = 0

    for block in blocks:
        if block.language == "python":
            result = execute_python_block(block.code)
        elif block.language == "sql":
            result = verify_sql_structure(block.code)
        else:
            # Skip unknown languages
            continue

        details.append({
            "language": block.language,
            "line": block.line_number,
            "success": result.success,
            "output": result.output,
            "error": result.error,
            "execution_time_ms": result.execution_time_ms
        })

        if result.success:
            passed += 1

    return len(blocks), passed, details
```

### 4. GRP Diagnosis (`src/grp/diagnosis.py`)

```python
"""Failure diagnosis - analyze errors and find relevant skill sections."""
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional

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

def find_skill_files(skill_name: str, base_path: str = "databricks-skills") -> List[Path]:
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

                relevant.append(SkillSection(
                    file_path=str(file_path.relative_to("databricks-skills")),
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
```

### 5. GRP Pipeline (`src/grp/pipeline.py`)

```python
"""Generate-Review-Promote pipeline for ground truth creation."""
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Literal
import yaml

from .executor import extract_code_blocks, execute_code_blocks
from .diagnosis import analyze_failure, Diagnosis

@dataclass
class GRPCandidate:
    """A candidate test case in the GRP pipeline."""
    id: str
    prompt: str
    response: str
    skill_name: str

    # Execution results
    code_blocks_found: int = 0
    code_blocks_passed: int = 0
    execution_success: bool = False
    execution_details: List[Dict[str, Any]] = field(default_factory=list)

    # Diagnosis (if failed)
    diagnosis: Optional[Diagnosis] = None

    # Review status
    status: str = "pending"  # pending, approved, rejected
    reviewer: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_notes: str = ""

    # Skill fix tracking
    fixed_by_commit: Optional[str] = None
    fix_description: Optional[str] = None

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    source: str = "grp"

@dataclass
class GRPResult:
    """Result of GRP pipeline execution."""
    status: Literal["promoted", "rejected", "skipped", "pending"]
    case_id: Optional[str] = None
    reason: Optional[str] = None

@dataclass
class ApprovalMetadata:
    """Metadata from human approval."""
    approved: bool
    reviewer: str
    reason: Optional[str] = None
    expectations_edited: bool = False

def generate_candidate(
    skill_name: str,
    prompt: str,
    response: str
) -> GRPCandidate:
    """
    Generate a candidate from prompt/response pair.
    Executes code blocks to determine execution_success.
    """
    candidate = GRPCandidate(
        id=f"grp_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        skill_name=skill_name,
        prompt=prompt,
        response=response
    )

    # Execute code blocks
    total, passed, details = execute_code_blocks(response)
    candidate.code_blocks_found = total
    candidate.code_blocks_passed = passed
    candidate.execution_details = details
    candidate.execution_success = (total == 0 or passed == total)

    # Generate diagnosis if failed
    if not candidate.execution_success:
        failed_blocks = [d for d in details if not d["success"]]
        if failed_blocks:
            first_failure = failed_blocks[0]
            # Get the actual code block
            blocks = extract_code_blocks(response)
            failed_code = ""
            for block in blocks:
                if block.line_number == first_failure["line"]:
                    failed_code = block.code
                    break

            candidate.diagnosis = analyze_failure(
                error=first_failure["error"] or "Unknown error",
                code_block=failed_code,
                skill_name=skill_name
            )

    return candidate

def save_candidates(
    candidates: List[GRPCandidate],
    output_path: Path
) -> None:
    """Save candidates to YAML for review."""
    data = {
        "candidates": [
            {
                "id": c.id,
                "skill_name": c.skill_name,
                "status": c.status,
                "prompt": c.prompt,
                "response": c.response,
                "execution_success": c.execution_success,
                "code_blocks_found": c.code_blocks_found,
                "code_blocks_passed": c.code_blocks_passed,
                "execution_details": c.execution_details,
                "diagnosis": {
                    "error": c.diagnosis.error,
                    "code_block": c.diagnosis.code_block,
                    "relevant_sections": [
                        {
                            "file": s.file_path,
                            "section": s.section_name,
                            "excerpt": s.excerpt,
                            "line": s.line_number
                        }
                        for s in c.diagnosis.relevant_sections
                    ],
                    "suggested_action": c.diagnosis.suggested_action
                } if c.diagnosis else None,
                "created_at": c.created_at.isoformat(),
                "reviewer": c.reviewer,
                "reviewed_at": c.reviewed_at.isoformat() if c.reviewed_at else None,
                "review_notes": c.review_notes,
                "fixed_by_commit": c.fixed_by_commit,
                "fix_description": c.fix_description
            }
            for c in candidates
        ]
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

def promote_approved(
    candidates_path: Path,
    ground_truth_path: Path
) -> int:
    """Promote approved candidates to ground truth."""
    with open(candidates_path) as f:
        candidates_data = yaml.safe_load(f)

    # Load existing ground truth
    if ground_truth_path.exists():
        with open(ground_truth_path) as f:
            gt_data = yaml.safe_load(f) or {"test_cases": []}
    else:
        gt_data = {"test_cases": []}

    promoted = 0
    remaining = []

    for c in candidates_data.get("candidates", []):
        if c["status"] == "approved":
            # Convert to ground truth format
            gt_case = {
                "id": c["id"],
                "inputs": {"prompt": c["prompt"]},
                "outputs": {
                    "response": c["response"],
                    "execution_success": c["execution_success"]
                },
                "expectations": {},  # Filled by reviewer during approval
                "metadata": {
                    "category": "happy_path",
                    "difficulty": "medium",
                    "source": "grp",
                    "approved_by": c.get("reviewer"),
                    "approved_at": c.get("reviewed_at"),
                    "skill_version": c.get("skill_version"),
                    "fixed_by_commit": c.get("fixed_by_commit"),
                    "fix_description": c.get("fix_description")
                }
            }
            gt_data["test_cases"].append(gt_case)
            promoted += 1
        elif c["status"] == "pending":
            remaining.append(c)
        # rejected candidates are discarded

    # Save updated ground truth
    ground_truth_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ground_truth_path, 'w') as f:
        yaml.dump(gt_data, f, default_flow_style=False, sort_keys=False)

    # Update candidates file with remaining
    candidates_data["candidates"] = remaining
    with open(candidates_path, 'w') as f:
        yaml.dump(candidates_data, f, default_flow_style=False, sort_keys=False)

    return promoted

def grp_interactive(
    skill_name: str,
    prompt: str,
    invoke_skill_fn,  # Callable[[str, str], str]
    human_review_fn,  # Callable[[GRPCandidate], ApprovalMetadata]
    max_retries: int = 3
) -> GRPResult:
    """
    Full GRP with fix loop and human review.

    Args:
        skill_name: Name of skill to test
        prompt: Test prompt
        invoke_skill_fn: Function to invoke skill and get response
        human_review_fn: Function to get human approval
        max_retries: Max retry attempts after skill fixes

    Returns:
        GRPResult with status and case_id
    """
    retries = 0

    while retries <= max_retries:
        # 1. GENERATE
        response = invoke_skill_fn(skill_name, prompt)
        candidate = generate_candidate(skill_name, prompt, response)

        # 2. EXECUTE (already done in generate_candidate)

        # 3. FIX (if failed)
        if not candidate.execution_success:
            if retries >= max_retries:
                return GRPResult(
                    status="skipped",
                    reason=f"Max retries ({max_retries}) exceeded"
                )

            # Show diagnosis to human (in real implementation)
            # Human edits skill files...
            # Then retry
            retries += 1
            continue

        break  # Execution succeeded, proceed to review

    # 4. REVIEW (required for ALL)
    approval = human_review_fn(candidate)

    if not approval.approved:
        return GRPResult(
            status="rejected",
            case_id=candidate.id,
            reason=approval.reason
        )

    # Record approval metadata
    candidate.status = "approved"
    candidate.reviewer = approval.reviewer
    candidate.reviewed_at = datetime.now()

    # 5. PROMOTE happens separately via promote_approved()
    return GRPResult(
        status="promoted",
        case_id=candidate.id
    )
```

### 6. Skill Routing Scorer (`src/scorers/routing.py`)

```python
"""Skill routing scorer - evaluates Claude Code's skill selection."""
from mlflow.genai.scorers import scorer
from mlflow.entities import Feedback
from typing import Dict, Any, Set

# Skill trigger patterns (extracted from SKILL.md description fields)
SKILL_TRIGGERS = {
    "spark-declarative-pipelines": [
        "streaming table", "dlt", "delta live", "lakeflow",
        "sdp", "ldp", "medallion", "bronze", "silver", "gold",
        "cdc", "change data capture", "scd", "auto loader"
    ],
    "databricks-app-apx": [
        "databricks app", "apx", "fastapi", "react", "full-stack app"
    ],
    "databricks-app-python": [
        "python app", "streamlit", "dash", "flask", "gradio"
    ],
    "asset-bundles": [
        "dabs", "databricks asset bundle", "deploy", "bundle.yaml"
    ],
    "databricks-python-sdk": [
        "python sdk", "databricks-sdk", "workspaceclient",
        "databricks connect", "rest api"
    ],
    "databricks-jobs": [
        "job", "workflow", "task", "schedule", "trigger"
    ],
    "synthetic-data-generation": [
        "synthetic data", "fake data", "generate data", "mock data", "faker"
    ],
    "mlflow-evaluation": [
        "mlflow eval", "evaluate agent", "scorer", "genai.evaluate", "llm judge"
    ],
    "agent-bricks": [
        "agent brick", "knowledge assistant", "genie", "multi-agent", "supervisor"
    ]
}

def detect_skills_from_prompt(prompt: str) -> Set[str]:
    """Detect which skills a prompt should trigger."""
    prompt_lower = prompt.lower()
    detected = set()

    for skill, triggers in SKILL_TRIGGERS.items():
        for trigger in triggers:
            if trigger in prompt_lower:
                detected.add(skill)
                break

    return detected

@scorer
def skill_routing_accuracy(
    inputs: Dict[str, Any],
    expectations: Dict[str, Any]
) -> Feedback:
    """
    Score skill routing accuracy.

    Compares detected skills from prompt against expected skills.
    Handles both single-skill and multi-skill scenarios.
    """
    prompt = inputs.get("prompt", "").lower()
    expected_skills = set(expectations.get("expected_skills", []))
    is_multi_skill = expectations.get("is_multi_skill", False)

    detected_skills = detect_skills_from_prompt(prompt)

    # Both empty = correct (no skill should match)
    if not expected_skills and not detected_skills:
        return Feedback(
            name="routing_accuracy",
            value="yes",
            rationale="Correctly identified no skill match"
        )

    # Expected none but got some
    if not expected_skills:
        return Feedback(
            name="routing_accuracy",
            value="no",
            rationale=f"Expected no skills but detected: {detected_skills}"
        )

    # Expected some but got none
    if not detected_skills:
        return Feedback(
            name="routing_accuracy",
            value="no",
            rationale=f"Expected {expected_skills} but no skills detected"
        )

    # Check overlap
    if is_multi_skill:
        # For multi-skill: all expected skills should be detected
        missing = expected_skills - detected_skills
        if not missing:
            return Feedback(
                name="routing_accuracy",
                value="yes",
                rationale=f"All expected skills detected: {detected_skills}"
            )
        else:
            return Feedback(
                name="routing_accuracy",
                value="no",
                rationale=f"Missing skills: {missing}. Detected: {detected_skills}"
            )
    else:
        # For single-skill: expected should be subset of detected
        if expected_skills <= detected_skills:
            return Feedback(
                name="routing_accuracy",
                value="yes",
                rationale=f"Expected skill(s) detected. Expected: {expected_skills}, Got: {detected_skills}"
            )
        else:
            return Feedback(
                name="routing_accuracy",
                value="no",
                rationale=f"Expected: {expected_skills}, Detected: {detected_skills}"
            )

@scorer
def routing_precision(
    inputs: Dict[str, Any],
    expectations: Dict[str, Any]
) -> Feedback:
    """Measure precision - avoid false positives (extra skills)."""
    prompt = inputs.get("prompt", "")
    expected_skills = set(expectations.get("expected_skills", []))
    detected_skills = detect_skills_from_prompt(prompt)

    if not detected_skills:
        return Feedback(
            name="routing_precision",
            value=1.0,
            rationale="No skills detected (no false positives possible)"
        )

    correct = expected_skills & detected_skills
    precision = len(correct) / len(detected_skills)

    return Feedback(
        name="routing_precision",
        value=precision,
        rationale=f"Precision: {len(correct)}/{len(detected_skills)}"
    )

@scorer
def routing_recall(
    inputs: Dict[str, Any],
    expectations: Dict[str, Any]
) -> Feedback:
    """Measure recall - avoid false negatives (missing skills)."""
    prompt = inputs.get("prompt", "")
    expected_skills = set(expectations.get("expected_skills", []))

    if not expected_skills:
        return Feedback(
            name="routing_recall",
            value=1.0,
            rationale="No expected skills (recall not applicable)"
        )

    detected_skills = detect_skills_from_prompt(prompt)
    correct = expected_skills & detected_skills
    recall = len(correct) / len(expected_skills)

    return Feedback(
        name="routing_recall",
        value=recall,
        rationale=f"Recall: {len(correct)}/{len(expected_skills)}"
    )
```

### 7. Universal Scorers (`src/scorers/universal.py`)

```python
"""Tier 1 deterministic scorers - fast and reliable."""
from mlflow.genai.scorers import scorer
from mlflow.entities import Feedback
import ast
import re
from typing import Dict, Any, List

@scorer
def python_syntax(outputs: Dict[str, Any]) -> Feedback:
    """Check if Python code blocks have valid syntax."""
    response = outputs.get("response", "")

    python_blocks = re.findall(r'```python\n(.*?)```', response, re.DOTALL)

    if not python_blocks:
        return Feedback(
            name="python_syntax",
            value="skip",
            rationale="No Python code blocks found"
        )

    errors = []
    for i, block in enumerate(python_blocks):
        try:
            ast.parse(block)
        except SyntaxError as e:
            errors.append(f"Block {i+1}: {e.msg} at line {e.lineno}")

    if errors:
        return Feedback(
            name="python_syntax",
            value="no",
            rationale=f"Syntax errors: {'; '.join(errors)}"
        )

    return Feedback(
        name="python_syntax",
        value="yes",
        rationale=f"All {len(python_blocks)} Python blocks parse successfully"
    )

@scorer
def sql_syntax(outputs: Dict[str, Any]) -> Feedback:
    """Basic SQL syntax validation (structural checks)."""
    response = outputs.get("response", "")

    sql_blocks = re.findall(r'```sql\n(.*?)```', response, re.DOTALL)

    if not sql_blocks:
        return Feedback(
            name="sql_syntax",
            value="skip",
            rationale="No SQL code blocks found"
        )

    errors = []
    for i, block in enumerate(sql_blocks):
        if not re.search(r'(SELECT|CREATE|INSERT|UPDATE|DELETE|WITH|MERGE)', block, re.I):
            errors.append(f"Block {i+1}: No recognizable SQL statement")
        if block.count('(') != block.count(')'):
            errors.append(f"Block {i+1}: Unbalanced parentheses")

    if errors:
        return Feedback(
            name="sql_syntax",
            value="no",
            rationale=f"SQL issues: {'; '.join(errors)}"
        )

    return Feedback(
        name="sql_syntax",
        value="yes",
        rationale=f"All {len(sql_blocks)} SQL blocks look valid"
    )

@scorer
def pattern_adherence(
    outputs: Dict[str, Any],
    expectations: Dict[str, Any]
) -> List[Feedback]:
    """Check for required patterns in response."""
    response = outputs.get("response", "")
    expected_patterns = expectations.get("expected_patterns", [])

    if not expected_patterns:
        return [Feedback(
            name="pattern_adherence",
            value="skip",
            rationale="No expected_patterns defined"
        )]

    feedbacks = []
    for pattern_spec in expected_patterns:
        if isinstance(pattern_spec, str):
            pattern = pattern_spec
            min_count = 1
            description = pattern[:30]
        else:
            pattern = pattern_spec["pattern"]
            min_count = pattern_spec.get("min_count", 1)
            description = pattern_spec.get("description", pattern[:30])

        matches = len(re.findall(pattern, response, re.IGNORECASE))
        passed = matches >= min_count

        feedbacks.append(Feedback(
            name=f"pattern_{description}",
            value="yes" if passed else "no",
            rationale=f"Found {matches} matches (need {min_count})"
        ))

    return feedbacks

@scorer
def no_hallucinated_apis(outputs: Dict[str, Any]) -> Feedback:
    """Check for common API hallucinations in Databricks context."""
    response = outputs.get("response", "")

    hallucinations = [
        (r'@dlt\.table', "Legacy @dlt.table - should use @dp.table"),
        (r'dlt\.read', "Legacy dlt.read - use spark.read or dp.read"),
        (r'PARTITION BY', "PARTITION BY deprecated - use CLUSTER BY"),
        (r'mlflow\.evaluate\(', "Old mlflow.evaluate - use mlflow.genai.evaluate"),
    ]

    found = []
    for pattern, description in hallucinations:
        if re.search(pattern, response):
            found.append(description)

    if found:
        return Feedback(
            name="no_hallucinated_apis",
            value="no",
            rationale=f"Issues: {'; '.join(found)}"
        )

    return Feedback(
        name="no_hallucinated_apis",
        value="yes",
        rationale="No common API hallucinations detected"
    )

@scorer
def expected_facts_present(
    outputs: Dict[str, Any],
    expectations: Dict[str, Any]
) -> Feedback:
    """Check if expected facts are mentioned in response."""
    response = outputs.get("response", "").lower()
    expected_facts = expectations.get("expected_facts", [])

    if not expected_facts:
        return Feedback(
            name="expected_facts",
            value="skip",
            rationale="No expected_facts defined"
        )

    missing = []
    for fact in expected_facts:
        if fact.lower() not in response:
            missing.append(fact)

    if missing:
        return Feedback(
            name="expected_facts",
            value="no",
            rationale=f"Missing facts: {missing}"
        )

    return Feedback(
        name="expected_facts",
        value="yes",
        rationale=f"All {len(expected_facts)} expected facts present"
    )
```

### 8. Evaluation Runner (`src/runners/evaluate.py`)

```python
"""Main evaluation runner with MLflow integration."""
import os
from pathlib import Path
from typing import List, Optional, Dict, Any
import mlflow
from mlflow.genai.scorers import Guidelines, Safety

from ..config import SkillTestConfig
from ..dataset import YAMLDatasetSource, get_dataset_source
from ..scorers.universal import (
    python_syntax, sql_syntax, pattern_adherence,
    no_hallucinated_apis, expected_facts_present
)
from ..scorers.routing import (
    skill_routing_accuracy, routing_precision, routing_recall
)

def setup_mlflow(config: SkillTestConfig) -> None:
    """Configure MLflow from environment variables."""
    mlflow.set_tracking_uri(config.mlflow.tracking_uri)
    mlflow.set_experiment(config.mlflow.experiment_name)

def evaluate_skill(
    skill_name: str,
    config: Optional[SkillTestConfig] = None,
    run_name: Optional[str] = None,
    filter_category: Optional[str] = None
) -> Dict[str, Any]:
    """
    Evaluate a skill using pre-computed outputs (Pattern 2).

    Args:
        skill_name: Name of skill to evaluate
        config: Configuration (uses defaults if None)
        run_name: MLflow run name
        filter_category: Filter test cases by category

    Returns:
        Evaluation results dict with metrics and run_id
    """
    if config is None:
        config = SkillTestConfig()

    setup_mlflow(config)

    # Load ground truth
    dataset_source = get_dataset_source(skill_name)
    records = dataset_source.load()

    # Filter if requested
    if filter_category:
        records = [
            r for r in records
            if r.metadata and r.metadata.get("category") == filter_category
        ]

    # Convert to MLflow format (Pattern 2: pre-computed outputs)
    eval_data = [r.to_eval_dict() for r in records]

    # Build scorer list
    scorers = [
        python_syntax,
        sql_syntax,
        pattern_adherence,
        no_hallucinated_apis,
        expected_facts_present,
        Safety(),
        Guidelines(
            name="skill_quality",
            guidelines=[
                "Response must address the user's request completely",
                "Code examples must follow documented best practices",
                "Response must use modern APIs (not deprecated ones)"
            ]
        )
    ]

    # Run evaluation
    with mlflow.start_run(run_name=run_name or f"{skill_name}_eval"):
        mlflow.set_tags({
            "skill_name": skill_name,
            "test_count": len(eval_data),
            "filter_category": filter_category or "all"
        })

        # No predict_fn - using pre-computed outputs
        results = mlflow.genai.evaluate(
            data=eval_data,
            scorers=scorers
        )

        return {
            "run_id": mlflow.active_run().info.run_id,
            "metrics": results.metrics,
            "skill_name": skill_name,
            "test_count": len(eval_data)
        }

def evaluate_routing(
    config: Optional[SkillTestConfig] = None,
    run_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Evaluate skill routing accuracy.

    Tests Claude Code's ability to route prompts to correct skills.
    """
    if config is None:
        config = SkillTestConfig()

    setup_mlflow(config)

    # Load routing test cases
    dataset_source = get_dataset_source("_routing")
    records = dataset_source.load()

    # Convert to MLflow format
    eval_data = [
        {
            "inputs": {"prompt": r.inputs.get("prompt", "")},
            "expectations": r.expectations or {}
        }
        for r in records
    ]

    # Routing-specific scorers
    scorers = [
        skill_routing_accuracy,
        routing_precision,
        routing_recall
    ]

    with mlflow.start_run(run_name=run_name or "routing_eval"):
        mlflow.set_tags({
            "evaluation_type": "routing",
            "test_count": len(eval_data)
        })

        results = mlflow.genai.evaluate(
            data=eval_data,
            scorers=scorers
        )

        return {
            "run_id": mlflow.active_run().info.run_id,
            "metrics": results.metrics,
            "evaluation_type": "routing",
            "test_count": len(eval_data)
        }
```

---

## YAML Schemas

### Skill Manifest (`skills/{skill}/manifest.yaml`)

```yaml
skill:
  name: "spark-declarative-pipelines"
  source_path: "databricks-skills/spark-declarative-pipelines"
  description: "Streaming tables, CDC, medallion architecture"

evaluation:
  datasets:
    - path: ground_truth.yaml
      type: yaml

  scorers:
    tier1:  # Deterministic (fast)
      - python_syntax
      - sql_syntax
      - pattern_adherence
      - no_hallucinated_apis
    tier2:  # Execution-based
      - code_executes
    tier3:  # LLM Judge
      - Guidelines

  quality_gates:
    tier1_pass_rate: 1.0
    tier2_pass_rate: 0.8
    tier3_pass_rate: 0.85
```

### Ground Truth (`skills/{skill}/ground_truth.yaml`)

```yaml
test_cases:
  - id: "sdp_bronze_ingestion_001"

    inputs:
      prompt: "Create a bronze ingestion pipeline for JSON files in /Volumes/raw/orders"

    outputs:
      response: |
        Here's a bronze ingestion pipeline using Spark Declarative Pipelines...

        ```sql
        CREATE OR REFRESH STREAMING TABLE bronze_orders
        CLUSTER BY (order_date)
        AS SELECT *, current_timestamp() AS _ingested_at
        FROM read_files('/Volumes/raw/orders', format => 'json');
        ```
      execution_success: true

    expectations:
      expected_facts:
        - "Uses STREAMING TABLE for incremental ingestion"
        - "Uses CLUSTER BY instead of PARTITION BY"
        - "Includes _ingested_at timestamp"

      expected_patterns:
        - pattern: "CREATE OR REFRESH STREAMING TABLE"
          min_count: 1
        - pattern: "CLUSTER BY"
          min_count: 1
        - pattern: "read_files\\s*\\("
          min_count: 1

      guidelines:
        - "Must use modern SDP syntax, not legacy DLT"
        - "Should include metadata columns for lineage"

    metadata:
      category: "happy_path"
      difficulty: "easy"
      source: "manual"
      tags: ["bronze", "ingestion", "autoloader"]
```

### Skill Routing (`skills/_routing/ground_truth.yaml`)

```yaml
test_cases:
  # Single-skill routing
  - id: "routing_sdp_001"
    inputs:
      prompt: "Create a streaming table for ingesting JSON events"
    expectations:
      expected_skills: ["spark-declarative-pipelines"]
      is_multi_skill: false
    metadata:
      category: "single_skill"
      difficulty: "easy"
      reasoning: "Mentions 'streaming table' - clear SDP trigger"

  - id: "routing_sdk_001"
    inputs:
      prompt: "How do I list clusters using the Python SDK?"
    expectations:
      expected_skills: ["databricks-python-sdk"]
      is_multi_skill: false
    metadata:
      category: "single_skill"
      difficulty: "easy"

  # Multi-skill routing
  - id: "routing_multi_001"
    inputs:
      prompt: "Create a data pipeline with streaming tables and deploy it using DABs"
    expectations:
      expected_skills:
        - "spark-declarative-pipelines"
        - "asset-bundles"
      is_multi_skill: true
    metadata:
      category: "multi_skill"
      difficulty: "medium"

  - id: "routing_multi_002"
    inputs:
      prompt: "Generate synthetic customer data and evaluate the agent with MLflow"
    expectations:
      expected_skills:
        - "synthetic-data-generation"
        - "mlflow-evaluation"
      is_multi_skill: true
    metadata:
      category: "multi_skill"
      difficulty: "medium"

  # No skill match
  - id: "routing_no_match_001"
    inputs:
      prompt: "What is the weather like today?"
    expectations:
      expected_skills: []
      is_multi_skill: false
    metadata:
      category: "no_match"
      difficulty: "easy"
```

---

## MLflow Integration

Uses environment variables (no hardcoded config):
- `MLFLOW_TRACKING_URI` - defaults to "databricks"
- `MLFLOW_EXPERIMENT_NAME` - defaults to "/Shared/skill-tests"

Works with Databricks CLI setup:
- `DATABRICKS_HOST`
- `DATABRICKS_TOKEN`
- `DATABRICKS_CONFIG_PROFILE`

**Pattern 2 (pre-computed outputs):** No predict_fn needed
```python
# Data has outputs already
eval_data = [
    {"inputs": {...}, "outputs": {...}, "expectations": {...}}
]

results = mlflow.genai.evaluate(
    data=eval_data,
    scorers=scorers
)
```

---

## Implementation Phases

### Phase 1: Foundation
- `src/config.py`
- `src/dataset.py` (YAML only)
- `src/ground_truth.py`
- `skills/_routing/manifest.yaml` + `ground_truth.yaml`

### Phase 2: Scoring
- `src/scorers/universal.py`
- `src/scorers/routing.py`
- `skills/spark-declarative-pipelines/ground_truth.yaml` (3-5 cases)

### Phase 3: GRP Pipeline (Extended)
- `src/grp/executor.py`
- `src/grp/pipeline.py`
- `src/grp/diagnosis.py`
- `src/grp/reviewer.py`

### Phase 4: MLflow Integration
- `src/runners/evaluate.py`
- `baselines/spark-declarative-pipelines.json`

### Phase 5: UC Datasets (Later)
- Implement `UCDatasetSource.load()`
- Add `sync_yaml_to_uc()` function

---

## Quality Gates (CI/CD)

| Metric | Threshold | Description |
|--------|-----------|-------------|
| syntax_valid/mean | 100% | All code must parse |
| pattern_adherence/mean | 90% | Follow documented patterns |
| no_hallucinated_apis/mean | 100% | No deprecated/fake APIs |
| execution_success/mean | 80% | Code blocks should run |
| routing_accuracy/mean | 90% | Correct skill routing |

---

## Verification Plan

1. **Unit test scorers** - Each scorer with known good/bad inputs
2. **Run routing evaluation** - Validate routing scorer accuracy
3. **Run SDP evaluation** - Full eval with 3 ground truth cases
4. **GRP pipeline test** - Full flow: Generate → Execute → Fix → Review → Promote
5. **Failure diagnosis test** - Intentionally fail, verify relevant skill sections shown
6. **Human review test** - Verify approval metadata captured correctly
7. **Skill update tracking** - Fix a skill, verify git commit + YAML metadata linked
8. **MLflow check** - Verify experiments in workspace

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| LLM judge inconsistency | Prioritize deterministic scorers; set temperature=0 |
| Skill output variability | Use pattern matching, not exact matching |
| Infrastructure requirements | Tag tests by requirements; support mock mode |
| Test maintenance burden | GRP pipeline generates tests from skill usage |
| Human review bottleneck | Batch review interface; auto-approve on high confidence |

---

## Critical References

**mlflow-evaluation skill** (primary reference):
- `references/patterns-datasets.md` - Dataset patterns
- `references/patterns-scorers.md` - Scorer implementation patterns
- `references/CRITICAL-interfaces.md` - API schemas
- `SKILL.md` - Workflow structure model

**mlflow-eval-agent benchmarks** (proven patterns):
- `benchmarks/skills/mlflow_evaluation/` - Working YAML-first implementation
- `ground_truth.yaml` format
- `DatasetSource` abstraction pattern

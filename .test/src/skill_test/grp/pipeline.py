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
    execution_details: list[dict[str, Any]] = field(default_factory=list)

    # Diagnosis (if failed)
    diagnosis: Diagnosis | None = None

    # Review status
    status: str = "pending"  # pending, approved, rejected
    reviewer: str | None = None
    reviewed_at: datetime | None = None
    review_notes: str = ""

    # Skill fix tracking
    fixed_by_commit: str | None = None
    fix_description: str | None = None

    # Trace linkage (MLflow trace captured via mlflow autolog claude)
    trace_run_id: str | None = None

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    source: str = "grp"


@dataclass
class GRPResult:
    """Result of GRP pipeline execution."""

    status: Literal["promoted", "rejected", "skipped", "pending"]
    case_id: str | None = None
    reason: str | None = None


@dataclass
class ApprovalMetadata:
    """Metadata from human approval."""

    approved: bool
    reviewer: str
    reason: str | None = None
    expectations_edited: bool = False


def generate_candidate(skill_name: str, prompt: str, response: str) -> GRPCandidate:
    """
    Generate a candidate from prompt/response pair.
    Executes code blocks to determine execution_success.
    """
    candidate = GRPCandidate(
        id=f"grp_{datetime.now().strftime('%Y%m%d_%H%M%S')}", skill_name=skill_name, prompt=prompt, response=response
    )

    # Execute code blocks
    total, passed, details = execute_code_blocks(response)
    candidate.code_blocks_found = total
    candidate.code_blocks_passed = passed
    candidate.execution_details = details
    candidate.execution_success = total == 0 or passed == total

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
                error=first_failure["error"] or "Unknown error", code_block=failed_code, skill_name=skill_name
            )

    return candidate


def save_candidates(candidates: list[GRPCandidate], output_path: Path) -> None:
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
                        {"file": s.file_path, "section": s.section_name, "excerpt": s.excerpt, "line": s.line_number}
                        for s in c.diagnosis.relevant_sections
                    ],
                    "suggested_action": c.diagnosis.suggested_action,
                }
                if c.diagnosis
                else None,
                "created_at": c.created_at.isoformat(),
                "reviewer": c.reviewer,
                "reviewed_at": c.reviewed_at.isoformat() if c.reviewed_at else None,
                "review_notes": c.review_notes,
                "fixed_by_commit": c.fixed_by_commit,
                "fix_description": c.fix_description,
                "trace_run_id": c.trace_run_id,  # Link to MLflow trace
            }
            for c in candidates
        ]
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def promote_approved(candidates_path: Path, ground_truth_path: Path) -> int:
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
                "outputs": {"response": c["response"], "execution_success": c["execution_success"]},
                "expectations": {},  # Filled by reviewer during approval
                "metadata": {
                    "category": "happy_path",
                    "difficulty": "medium",
                    "source": "grp",
                    "approved_by": c.get("reviewer"),
                    "approved_at": c.get("reviewed_at"),
                    "skill_version": c.get("skill_version"),
                    "fixed_by_commit": c.get("fixed_by_commit"),
                    "fix_description": c.get("fix_description"),
                    "trace_run_id": c.get("trace_run_id"),  # Preserve MLflow trace link
                },
            }
            gt_data["test_cases"].append(gt_case)
            promoted += 1
        elif c["status"] == "pending":
            remaining.append(c)
        # rejected candidates are discarded

    # Save updated ground truth
    ground_truth_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ground_truth_path, "w") as f:
        yaml.dump(gt_data, f, default_flow_style=False, sort_keys=False)

    # Update candidates file with remaining
    candidates_data["candidates"] = remaining
    with open(candidates_path, "w") as f:
        yaml.dump(candidates_data, f, default_flow_style=False, sort_keys=False)

    return promoted


def grp_interactive(
    skill_name: str,
    prompt: str,
    invoke_skill_fn,  # Callable[[str, str], str]
    human_review_fn,  # Callable[[GRPCandidate], ApprovalMetadata]
    max_retries: int = 3,
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
                return GRPResult(status="skipped", reason=f"Max retries ({max_retries}) exceeded")

            # Show diagnosis to human (in real implementation)
            # Human edits skill files...
            # Then retry
            retries += 1
            continue

        break  # Execution succeeded, proceed to review

    # 4. REVIEW (required for ALL)
    approval = human_review_fn(candidate)

    if not approval.approved:
        return GRPResult(status="rejected", case_id=candidate.id, reason=approval.reason)

    # Record approval metadata
    candidate.status = "approved"
    candidate.reviewer = approval.reviewer
    candidate.reviewed_at = datetime.now()

    # 5. PROMOTE happens separately via promote_approved()
    return GRPResult(status="promoted", case_id=candidate.id)

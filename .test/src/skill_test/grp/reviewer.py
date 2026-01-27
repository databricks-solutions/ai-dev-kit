"""Human review interface for GRP candidates."""
import os
from datetime import datetime
from pathlib import Path
from typing import Dict
import yaml

from .pipeline import GRPCandidate, ApprovalMetadata
from .diagnosis import Diagnosis, SkillSection


def display_candidate(candidate: GRPCandidate) -> None:
    """Display a candidate for review in the terminal."""
    print("\n" + "=" * 80)
    print(f"CANDIDATE REVIEW: {candidate.id}")
    print("=" * 80)

    print(f"\nSkill: {candidate.skill_name}")
    print(f"Status: {candidate.status}")
    print(f"Created: {candidate.created_at}")

    print("\n" + "-" * 40)
    print("PROMPT:")
    print("-" * 40)
    print(candidate.prompt)

    print("\n" + "-" * 40)
    print("RESPONSE:")
    print("-" * 40)
    print(candidate.response[:2000])  # Truncate long responses
    if len(candidate.response) > 2000:
        print(f"\n... [truncated, {len(candidate.response)} total chars]")

    print("\n" + "-" * 40)
    print("EXECUTION RESULTS:")
    print("-" * 40)
    print(f"Code blocks found: {candidate.code_blocks_found}")
    print(f"Code blocks passed: {candidate.code_blocks_passed}")
    print(f"Execution success: {candidate.execution_success}")

    if candidate.execution_details:
        for i, detail in enumerate(candidate.execution_details):
            status = "PASS" if detail["success"] else "FAIL"
            print(f"\n  Block {i+1} ({detail['language']}) at line {detail['line']}: {status}")
            if detail["error"]:
                print(f"    Error: {detail['error']}")

    if candidate.diagnosis:
        print("\n" + "-" * 40)
        print("DIAGNOSIS:")
        print("-" * 40)
        print(f"Error: {candidate.diagnosis.error}")
        print(f"Suggested action: {candidate.diagnosis.suggested_action}")
        if candidate.diagnosis.relevant_sections:
            print("\nRelevant skill sections:")
            for section in candidate.diagnosis.relevant_sections:
                print(f"  - {section.file_path}:{section.line_number}")
                print(f"    Section: {section.section_name}")

    print("\n" + "=" * 80)


def prompt_review_decision(candidate: GRPCandidate) -> ApprovalMetadata:
    """
    Prompt for human review decision.

    Returns ApprovalMetadata with the reviewer's decision.
    """
    display_candidate(candidate)

    print("\nREVIEW OPTIONS:")
    print("  [a] Approve - Add to ground truth")
    print("  [r] Reject - Discard this candidate")
    print("  [s] Skip - Keep as pending for later")
    print("  [e] Edit - Modify expectations before approving")

    reviewer = os.getenv("USER", "unknown")

    while True:
        choice = input(f"\nYour decision [{reviewer}]: ").strip().lower()

        if choice == 'a':
            return ApprovalMetadata(
                approved=True,
                reviewer=reviewer,
                reason=None,
                expectations_edited=False
            )
        elif choice == 'r':
            reason = input("Rejection reason: ").strip()
            return ApprovalMetadata(
                approved=False,
                reviewer=reviewer,
                reason=reason or "Rejected without reason",
                expectations_edited=False
            )
        elif choice == 's':
            return ApprovalMetadata(
                approved=False,
                reviewer=reviewer,
                reason="Skipped - pending",
                expectations_edited=False
            )
        elif choice == 'e':
            # In a real implementation, this would open an editor
            print("Expectation editing not yet implemented - approving as-is")
            return ApprovalMetadata(
                approved=True,
                reviewer=reviewer,
                reason=None,
                expectations_edited=True
            )
        else:
            print("Invalid choice. Please enter 'a', 'r', 's', or 'e'.")


def review_candidates_file(candidates_path: Path) -> Dict[str, int]:
    """
    Review all pending candidates in a file.

    Returns summary of review actions taken.
    """
    with open(candidates_path) as f:
        data = yaml.safe_load(f)

    candidates = data.get("candidates", [])
    pending = [c for c in candidates if c.get("status") == "pending"]

    print(f"\nFound {len(pending)} pending candidates to review")

    stats = {"approved": 0, "rejected": 0, "skipped": 0}

    for i, c_data in enumerate(pending):
        print(f"\n[{i+1}/{len(pending)}]")

        # Convert dict to GRPCandidate for display
        diagnosis = None
        if c_data.get("diagnosis"):
            d = c_data["diagnosis"]
            diagnosis = Diagnosis(
                error=d["error"],
                code_block=d["code_block"],
                relevant_sections=[
                    SkillSection(
                        file_path=s["file"],
                        section_name=s["section"],
                        excerpt=s["excerpt"],
                        line_number=s["line"]
                    )
                    for s in d.get("relevant_sections", [])
                ],
                suggested_action=d["suggested_action"]
            )

        candidate = GRPCandidate(
            id=c_data["id"],
            skill_name=c_data["skill_name"],
            prompt=c_data["prompt"],
            response=c_data["response"],
            code_blocks_found=c_data.get("code_blocks_found", 0),
            code_blocks_passed=c_data.get("code_blocks_passed", 0),
            execution_success=c_data.get("execution_success", False),
            execution_details=c_data.get("execution_details", []),
            diagnosis=diagnosis,
            status=c_data.get("status", "pending"),
            created_at=datetime.fromisoformat(c_data["created_at"]) if c_data.get("created_at") else datetime.now()
        )

        approval = prompt_review_decision(candidate)

        # Update the candidate data
        if approval.approved:
            c_data["status"] = "approved"
            stats["approved"] += 1
        elif approval.reason == "Skipped - pending":
            stats["skipped"] += 1
        else:
            c_data["status"] = "rejected"
            stats["rejected"] += 1

        c_data["reviewer"] = approval.reviewer
        c_data["reviewed_at"] = datetime.now().isoformat()
        c_data["review_notes"] = approval.reason or ""

    # Save updated candidates
    with open(candidates_path, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    print(f"\nReview complete: {stats}")
    return stats


def batch_approve(
    candidates_path: Path,
    filter_fn=None,
    reviewer: str = None
) -> int:
    """
    Batch approve candidates matching a filter.

    Args:
        candidates_path: Path to candidates YAML
        filter_fn: Optional function(candidate_dict) -> bool
        reviewer: Reviewer name (defaults to $USER)

    Returns:
        Number of candidates approved
    """
    with open(candidates_path) as f:
        data = yaml.safe_load(f)

    reviewer = reviewer or os.getenv("USER", "batch-approve")
    approved = 0

    for c in data.get("candidates", []):
        if c.get("status") != "pending":
            continue

        if filter_fn and not filter_fn(c):
            continue

        c["status"] = "approved"
        c["reviewer"] = reviewer
        c["reviewed_at"] = datetime.now().isoformat()
        c["review_notes"] = "Batch approved"
        approved += 1

    with open(candidates_path, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    return approved

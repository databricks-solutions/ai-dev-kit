"""Integration tests for the GRP review workflow.

Tests actual candidate review and promotion with real file I/O.
No mocks - files are actually modified on disk.
"""
import sys
from pathlib import Path

import pytest
import yaml

# Add src to path for imports
_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root / "src") not in sys.path:
    sys.path.insert(0, str(_repo_root / "src"))


class TestRealReviewWorkflow:
    """Test review command with real file operations."""

    def test_batch_review_modifies_real_files(self, real_skill_dir, cli_context):
        """Verify batch review actually updates candidates.yaml and ground_truth.yaml."""
        from skill_test.cli.commands import review

        candidates_path = real_skill_dir / "candidates.yaml"
        ground_truth_path = real_skill_dir / "ground_truth.yaml"

        # Read initial state
        with open(candidates_path) as f:
            initial_candidates = yaml.safe_load(f)
        with open(ground_truth_path) as f:
            initial_gt = yaml.safe_load(f)

        initial_pending = len([c for c in initial_candidates["candidates"] if c["status"] == "pending"])
        initial_gt_count = len(initial_gt.get("test_cases", []))

        # Run batch review
        result = review(
            skill_name="integration-test-skill",
            ctx=cli_context,
            batch=True
        )

        assert result["success"] is True
        assert result["mode"] == "batch"
        assert result["approved"] >= 0

        # Verify files were actually modified
        with open(candidates_path) as f:
            updated_candidates = yaml.safe_load(f)
        with open(ground_truth_path) as f:
            updated_gt = yaml.safe_load(f)

        # Pending candidates should be processed
        remaining_pending = len([c for c in updated_candidates.get("candidates", []) if c["status"] == "pending"])
        assert remaining_pending < initial_pending

        # Ground truth should have new entries
        final_gt_count = len(updated_gt.get("test_cases", []))
        assert final_gt_count >= initial_gt_count

    def test_batch_review_with_success_filter(self, real_skill_dir, cli_context):
        """Verify batch review with filter_success only approves successful candidates."""
        from skill_test.cli.commands import review

        # First reset candidates to initial state
        candidates_path = real_skill_dir / "candidates.yaml"
        from datetime import datetime
        candidates = {
            "candidates": [
                {
                    "id": "success_001",
                    "skill_name": "integration-test-skill",
                    "status": "pending",
                    "prompt": "Good prompt",
                    "response": "```sql\nSELECT 1;\n```",
                    "execution_success": True,
                    "code_blocks_found": 1,
                    "code_blocks_passed": 1,
                    "created_at": datetime.now().isoformat()
                },
                {
                    "id": "failure_001",
                    "skill_name": "integration-test-skill",
                    "status": "pending",
                    "prompt": "Bad prompt",
                    "response": "```python\ninvalid\n```",
                    "execution_success": False,
                    "code_blocks_found": 1,
                    "code_blocks_passed": 0,
                    "created_at": datetime.now().isoformat()
                }
            ]
        }
        with open(candidates_path, 'w') as f:
            yaml.dump(candidates, f)

        # Run batch review with filter
        result = review(
            skill_name="integration-test-skill",
            ctx=cli_context,
            batch=True,
            filter_success=True
        )

        assert result["success"] is True
        assert result["filter_success"] is True
        assert result["approved"] == 1  # Only successful one
        assert result["skipped"] == 1  # Failed one skipped

    def test_review_no_pending_returns_empty(self, tmp_path):
        """Verify review with no pending candidates returns properly."""
        from skill_test.cli.commands import review, CLIContext

        # Create skill with no pending candidates
        skill_dir = tmp_path / "skills" / "empty-skill"
        skill_dir.mkdir(parents=True)

        candidates = {"candidates": []}
        with open(skill_dir / "candidates.yaml", 'w') as f:
            yaml.dump(candidates, f)

        ctx = CLIContext(base_path=tmp_path / "skills")
        result = review(
            skill_name="empty-skill",
            ctx=ctx,
            batch=True
        )

        assert result["success"] is True
        assert result["reviewed"] == 0
        assert "no pending" in result["message"].lower()

    def test_review_missing_candidates_returns_error(self, tmp_path):
        """Verify review returns error when candidates.yaml doesn't exist."""
        from skill_test.cli.commands import review, CLIContext

        skill_dir = tmp_path / "skills" / "no-candidates-skill"
        skill_dir.mkdir(parents=True)

        ctx = CLIContext(base_path=tmp_path / "skills")
        result = review(
            skill_name="no-candidates-skill",
            ctx=ctx,
            batch=True
        )

        assert result["success"] is False
        assert "error" in result


class TestPromoteApproved:
    """Test the promote_approved function directly."""

    def test_promote_moves_approved_to_ground_truth(self, tmp_path):
        """Verify approved candidates are moved to ground_truth.yaml."""
        from skill_test.grp.pipeline import promote_approved
        from datetime import datetime

        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()

        # Create candidates with one approved
        candidates = {
            "candidates": [
                {
                    "id": "approved_001",
                    "skill_name": "test",
                    "status": "approved",
                    "prompt": "Test prompt",
                    "response": "Test response",
                    "execution_success": True,
                    "reviewer": "test_user",
                    "reviewed_at": datetime.now().isoformat()
                },
                {
                    "id": "pending_001",
                    "skill_name": "test",
                    "status": "pending",
                    "prompt": "Pending prompt",
                    "response": "Pending response",
                    "execution_success": True
                }
            ]
        }
        candidates_path = skill_dir / "candidates.yaml"
        with open(candidates_path, 'w') as f:
            yaml.dump(candidates, f)

        ground_truth_path = skill_dir / "ground_truth.yaml"

        # Run promote
        promoted_count = promote_approved(candidates_path, ground_truth_path)

        assert promoted_count == 1

        # Verify ground truth was created with the approved candidate
        with open(ground_truth_path) as f:
            gt = yaml.safe_load(f)
        assert len(gt["test_cases"]) == 1
        assert gt["test_cases"][0]["id"] == "approved_001"

        # Verify candidates file only has pending
        with open(candidates_path) as f:
            remaining = yaml.safe_load(f)
        assert len(remaining["candidates"]) == 1
        assert remaining["candidates"][0]["status"] == "pending"

    def test_promote_preserves_existing_ground_truth(self, tmp_path):
        """Verify existing ground truth entries are preserved."""
        from skill_test.grp.pipeline import promote_approved
        from datetime import datetime

        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()

        # Create existing ground truth
        existing_gt = {
            "test_cases": [
                {
                    "id": "existing_001",
                    "inputs": {"prompt": "Existing"},
                    "outputs": {"response": "Existing response"}
                }
            ]
        }
        ground_truth_path = skill_dir / "ground_truth.yaml"
        with open(ground_truth_path, 'w') as f:
            yaml.dump(existing_gt, f)

        # Create candidates
        candidates = {
            "candidates": [
                {
                    "id": "new_001",
                    "skill_name": "test",
                    "status": "approved",
                    "prompt": "New prompt",
                    "response": "New response",
                    "execution_success": True
                }
            ]
        }
        candidates_path = skill_dir / "candidates.yaml"
        with open(candidates_path, 'w') as f:
            yaml.dump(candidates, f)

        promote_approved(candidates_path, ground_truth_path)

        # Verify both entries exist
        with open(ground_truth_path) as f:
            gt = yaml.safe_load(f)
        assert len(gt["test_cases"]) == 2
        ids = [tc["id"] for tc in gt["test_cases"]]
        assert "existing_001" in ids
        assert "new_001" in ids

    def test_promote_removes_rejected_candidates(self, tmp_path):
        """Verify rejected candidates are removed from candidates.yaml."""
        from skill_test.grp.pipeline import promote_approved

        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()

        candidates = {
            "candidates": [
                {
                    "id": "rejected_001",
                    "skill_name": "test",
                    "status": "rejected",
                    "prompt": "Bad prompt",
                    "response": "Bad response",
                    "execution_success": False
                }
            ]
        }
        candidates_path = skill_dir / "candidates.yaml"
        with open(candidates_path, 'w') as f:
            yaml.dump(candidates, f)

        ground_truth_path = skill_dir / "ground_truth.yaml"

        promote_approved(candidates_path, ground_truth_path)

        # Rejected should be removed
        with open(candidates_path) as f:
            remaining = yaml.safe_load(f)
        assert len(remaining["candidates"]) == 0


class TestBatchApprove:
    """Test the batch_approve function directly."""

    def test_batch_approve_updates_status(self, tmp_path):
        """Verify batch_approve sets status to approved."""
        from skill_test.grp.reviewer import batch_approve
        from datetime import datetime

        candidates_path = tmp_path / "candidates.yaml"
        candidates = {
            "candidates": [
                {
                    "id": "pending_001",
                    "status": "pending",
                    "prompt": "Test",
                    "response": "Test"
                },
                {
                    "id": "pending_002",
                    "status": "pending",
                    "prompt": "Test 2",
                    "response": "Test 2"
                }
            ]
        }
        with open(candidates_path, 'w') as f:
            yaml.dump(candidates, f)

        approved_count = batch_approve(candidates_path)

        assert approved_count == 2

        with open(candidates_path) as f:
            updated = yaml.safe_load(f)

        for c in updated["candidates"]:
            assert c["status"] == "approved"
            assert "reviewer" in c
            assert "reviewed_at" in c

    def test_batch_approve_with_filter(self, tmp_path):
        """Verify batch_approve respects filter function."""
        from skill_test.grp.reviewer import batch_approve

        candidates_path = tmp_path / "candidates.yaml"
        candidates = {
            "candidates": [
                {"id": "good_001", "status": "pending", "execution_success": True},
                {"id": "bad_001", "status": "pending", "execution_success": False}
            ]
        }
        with open(candidates_path, 'w') as f:
            yaml.dump(candidates, f)

        # Only approve successful ones
        approved_count = batch_approve(
            candidates_path,
            filter_fn=lambda c: c.get("execution_success", False)
        )

        assert approved_count == 1

        with open(candidates_path) as f:
            updated = yaml.safe_load(f)

        approved = [c for c in updated["candidates"] if c["status"] == "approved"]
        pending = [c for c in updated["candidates"] if c["status"] == "pending"]
        assert len(approved) == 1
        assert len(pending) == 1
        assert approved[0]["id"] == "good_001"


class TestFullGRPPipeline:
    """Test complete Generate-Review-Promote cycle."""

    def test_full_grp_cycle(self, real_skill_dir, cli_context):
        """Test complete GRP pipeline from candidate to ground truth."""
        from skill_test.cli.commands import interactive, review
        from datetime import datetime

        # Step 1: Generate a candidate via interactive
        result = interactive(
            skill_name="integration-test-skill",
            prompt="Create a simple table",
            response="```sql\nCREATE TABLE test (id INT);\n```",
            ctx=cli_context,
            auto_approve_on_success=False  # Don't auto-approve, test full flow
        )

        # The result should be saved to candidates
        assert result.success is True

        # Step 2: Batch approve
        review_result = review(
            skill_name="integration-test-skill",
            ctx=cli_context,
            batch=True,
            filter_success=True
        )

        assert review_result["success"] is True
        assert review_result["promoted"] >= 0

        # Step 3: Verify ground truth was updated
        ground_truth_path = real_skill_dir / "ground_truth.yaml"
        with open(ground_truth_path) as f:
            gt = yaml.safe_load(f)

        # Should have test cases
        assert len(gt.get("test_cases", [])) > 0

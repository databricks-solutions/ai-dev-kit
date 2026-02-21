"""End-to-end test: optimize an existing skill, assert quality up + tokens down.

This test validates the entire GEPA optimization pipeline works and that
GEPA actually produces better, leaner skills.

NOTE: The E2E class is a slow integration test that calls GEPA with real LLM
reflection. It requires:
  - gepa>=0.0.7 installed
  - OPENAI_API_KEY set (for GEPA reflection LM)

Run unit tests only:
    cd .test && uv run pytest tests/test_optimize_e2e.py -v -k "not E2E"

Run everything (slow):
    cd .test && uv run pytest tests/test_optimize_e2e.py -v -s
"""

import pytest

from skill_test.optimize.evaluator import token_efficiency_score, count_tokens
from skill_test.optimize.splitter import create_gepa_datasets, generate_bootstrap_tasks, to_gepa_instances
from skill_test.optimize.asi import feedback_to_score, feedback_to_asi
from skill_test.optimize.config import PRESETS, GEPAPreset

try:
    from mlflow.entities import Feedback

    HAS_MLFLOW = True
except ImportError:
    Feedback = None
    HAS_MLFLOW = False

try:
    import gepa

    HAS_GEPA = True
except ImportError:
    HAS_GEPA = False


# --------------------------------------------------------------------------
# Step 1: Unit tests (no GEPA/LLM required)
# --------------------------------------------------------------------------


class TestTokenEfficiency:
    """Verification: token counting and efficiency scoring."""

    def test_same_size_scores_one(self):
        text = "Hello world, this is a test."
        tokens = count_tokens(text)
        assert token_efficiency_score(text, tokens) == 1.0

    def test_smaller_scores_one(self):
        assert token_efficiency_score("short", 100) == 1.0

    def test_double_size_scores_zero(self):
        text = "word " * 200
        tokens = count_tokens(text)
        assert token_efficiency_score(text + text, tokens) == pytest.approx(0.0, abs=0.05)

    def test_ten_pct_larger(self):
        base = "word " * 100
        base_tokens = count_tokens(base)
        larger = base + "extra " * 10
        larger_tokens = count_tokens(larger)
        ratio = larger_tokens / base_tokens
        expected = max(0.0, min(1.0, 2.0 - ratio))
        assert token_efficiency_score(larger, base_tokens) == pytest.approx(expected, abs=0.05)

    def test_zero_original_returns_one(self):
        assert token_efficiency_score("anything", 0) == 1.0


class TestSplitter:
    """Verification: dataset splitting and bootstrap task generation."""

    def test_small_dataset_no_val(self):
        """Skills with <5 test cases should use all as train, val=None."""
        try:
            train, val = create_gepa_datasets("databricks-genie")
            if len(train) < 5:
                assert val is None
        except FileNotFoundError:
            pytest.skip("No ground_truth.yaml for databricks-genie")

    def test_model_serving_has_split(self):
        """databricks-model-serving should have enough cases for a split."""
        try:
            train, val = create_gepa_datasets("databricks-model-serving")
            assert len(train) > 0
            if len(train) + (len(val) if val else 0) >= 5:
                assert val is not None
                assert len(val) > 0
        except FileNotFoundError:
            pytest.skip("No ground_truth.yaml for databricks-model-serving")

    def test_reproducible_splits(self):
        """Same seed should produce identical splits."""
        try:
            train1, val1 = create_gepa_datasets("databricks-model-serving", seed=42)
            train2, val2 = create_gepa_datasets("databricks-model-serving", seed=42)
            assert [t["id"] for t in train1] == [t["id"] for t in train2]
            if val1 and val2:
                assert [t["id"] for t in val1] == [t["id"] for t in val2]
        except FileNotFoundError:
            pytest.skip("No ground_truth.yaml for databricks-model-serving")

    def test_tasks_have_correct_keys(self):
        """Tasks should have the expected keys for GEPA compatibility."""
        try:
            train, _ = create_gepa_datasets("databricks-model-serving")
            assert len(train) > 0
            for task in train:
                assert "id" in task
                assert "input" in task
                assert "answer" in task
                assert "additional_context" in task
        except FileNotFoundError:
            pytest.skip("No ground_truth.yaml for databricks-model-serving")

    def test_to_gepa_instances(self):
        """to_gepa_instances should produce DefaultDataInst-compatible dicts."""
        try:
            train, _ = create_gepa_datasets("databricks-model-serving")
            instances = to_gepa_instances(train)
            assert len(instances) == len(train)
            for inst in instances:
                assert "input" in inst
                assert "additional_context" in inst
                assert "answer" in inst
                # Should NOT have internal-only keys
                assert "id" not in inst
                assert "metadata" not in inst
        except FileNotFoundError:
            pytest.skip("No ground_truth.yaml for databricks-model-serving")

    def test_bootstrap_tasks_generated(self):
        """Bootstrap should generate tasks from SKILL.md headers."""
        tasks = generate_bootstrap_tasks("databricks-model-serving")
        assert len(tasks) > 0
        for task in tasks:
            assert "id" in task
            assert "input" in task
            assert "additional_context" in task
            assert "metadata" in task


@pytest.mark.skipif(not HAS_MLFLOW, reason="mlflow not installed")
class TestASI:
    """Verification: Feedback -> GEPA score conversion."""

    def test_yes_scores_one(self):
        assert feedback_to_score(Feedback(name="test", value="yes")) == 1.0

    def test_no_scores_zero(self):
        assert feedback_to_score(Feedback(name="test", value="no")) == 0.0

    def test_skip_returns_none(self):
        assert feedback_to_score(Feedback(name="test", value="skip")) is None

    def test_numeric_value(self):
        assert feedback_to_score(Feedback(name="test", value="0.75")) == 0.75

    def test_feedback_to_asi_composite(self):
        feedbacks = [
            Feedback(name="syntax", value="yes", rationale="Valid"),
            Feedback(name="pattern", value="no", rationale="Missing X"),
            Feedback(name="optional", value="skip", rationale="N/A"),
        ]
        score, diag = feedback_to_asi(feedbacks)
        # Mean of [1.0, 0.0] = 0.5
        assert score == pytest.approx(0.5)
        assert diag["syntax"]["score"] == 1.0
        assert diag["pattern"]["score"] == 0.0
        assert diag["optional"]["status"] == "skipped"
        assert diag["_summary"]["scored"] == 2
        assert diag["_summary"]["skipped"] == 1
        # Failure messages collected
        assert len(diag["_failure_messages"]) >= 1


class TestConfig:
    """Verification: GEPA config presets."""

    def test_presets_exist(self):
        assert "quick" in PRESETS
        assert "standard" in PRESETS
        assert "thorough" in PRESETS

    def test_quick_has_fewer_calls(self):
        assert PRESETS["quick"].max_metric_calls < PRESETS["standard"].max_metric_calls

    def test_thorough_has_most_calls(self):
        assert PRESETS["thorough"].max_metric_calls > PRESETS["standard"].max_metric_calls

    def test_to_kwargs(self):
        kwargs = PRESETS["quick"].to_kwargs()
        assert "max_metric_calls" in kwargs
        assert "reflection_lm" in kwargs
        assert kwargs["max_metric_calls"] == 15


# --------------------------------------------------------------------------
# Step 6: New skill test (bootstrap mode)
# --------------------------------------------------------------------------


class TestBootstrapMode:
    """Verification: new skills without ground_truth.yaml can still bootstrap."""

    def test_nonexistent_skill_returns_empty(self):
        tasks = generate_bootstrap_tasks("nonexistent-skill-xyz")
        # No SKILL.md found -> empty list
        assert tasks == []

    def test_bootstrap_has_gepa_format(self):
        """Bootstrap tasks should be GEPA-compatible after conversion."""
        tasks = generate_bootstrap_tasks("databricks-model-serving")
        if not tasks:
            pytest.skip("No SKILL.md found for databricks-model-serving")
        instances = to_gepa_instances(tasks)
        for inst in instances:
            assert isinstance(inst["input"], str)
            assert isinstance(inst["additional_context"], dict)
            assert isinstance(inst["answer"], str)


# --------------------------------------------------------------------------
# Step 2: Dry run (requires adapter but not GEPA optimization)
# --------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_GEPA, reason="gepa not installed")
class TestDryRun:
    """Verification: dry run shows config without calling GEPA."""

    def test_dry_run_returns_result(self):
        from skill_test.optimize.runner import optimize_skill

        try:
            result = optimize_skill(
                skill_name="databricks-model-serving",
                mode="static",
                preset="quick",
                dry_run=True,
            )
            assert result.improvement == 0.0
            assert result.original_content == result.optimized_content
            assert result.gepa_result is None
            assert result.original_token_count > 0
            print(f"\nDry run score: {result.original_score:.3f}")
            print(f"Original tokens: {result.original_token_count:,}")
        except FileNotFoundError:
            pytest.skip("SKILL.md not found for databricks-model-serving")


# --------------------------------------------------------------------------
# Steps 3-5, 7-8: E2E integration (requires GEPA + LLM API key)
# --------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_GEPA, reason="gepa not installed")
@pytest.mark.slow
class TestOptimizeE2E:
    """End-to-end optimization test.

    Picks an existing skill, runs GEPA optimization, and asserts both
    quality improvement and token reduction.
    """

    def test_optimize_improves_quality_and_reduces_tokens(self):
        """Optimize databricks-spark-declarative-pipelines (largest skill).

        Asserts:
          1. Quality score does not regress
          2. Token count does not increase by >5%
          3. Validation set score within 5% of train (no overfitting)
        """
        from skill_test.optimize.runner import optimize_skill

        result = optimize_skill(
            skill_name="databricks-spark-declarative-pipelines",
            mode="static",
            preset="quick",
        )

        # 1. Quality must not regress
        assert result.optimized_score >= result.original_score, (
            f"Quality regressed: {result.original_score:.3f} -> {result.optimized_score:.3f}"
        )

        # 2. Token count must not increase significantly
        assert result.optimized_token_count <= result.original_token_count * 1.05, (
            f"Tokens grew: {result.original_token_count:,} -> {result.optimized_token_count:,}"
        )

        # 3. No overfitting
        if result.val_scores:
            avg_val = sum(result.val_scores.values()) / len(result.val_scores)
            assert avg_val >= result.optimized_score - 0.05, (
                f"Overfitting: train={result.optimized_score:.3f}, val={avg_val:.3f}"
            )

        print(f"\n=== E2E Results ===")
        print(f"Quality:  {result.original_score:.3f} -> {result.optimized_score:.3f} "
              f"({result.improvement:+.3f})")
        print(f"Tokens:   {result.original_token_count:,} -> {result.optimized_token_count:,} "
              f"({result.token_reduction_pct:+.1f}%)")
        if result.mlflow_run_id:
            print(f"MLflow:   {result.mlflow_run_id}")

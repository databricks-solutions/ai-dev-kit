"""End-to-end tests for GEPA skill optimization using optimize_anything API.

Unit tests run without API keys. E2E tests require GEPA reflection LM access.

Run unit tests:
    cd .test && uv run pytest tests/test_optimize_e2e.py -v -k "not TestOptimizeE2E"

Run everything (slow, requires API key):
    cd .test && uv run pytest tests/test_optimize_e2e.py -v -s
"""

import pytest

from skill_test.optimize.evaluator import token_efficiency_score, count_tokens, SKILL_KEY
from skill_test.optimize.splitter import create_gepa_datasets, generate_bootstrap_tasks, to_gepa_instances
from skill_test.optimize.asi import feedback_to_score, feedback_to_asi

try:
    from mlflow.entities import Feedback
    HAS_MLFLOW = True
except ImportError:
    Feedback = None
    HAS_MLFLOW = False

try:
    from gepa.optimize_anything import GEPAConfig, EngineConfig, ReflectionConfig
    HAS_GEPA = True
except ImportError:
    HAS_GEPA = False


# --------------------------------------------------------------------------
# Unit tests (no GEPA/LLM required)
# --------------------------------------------------------------------------

class TestTokenEfficiency:
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

    def test_zero_original_returns_one(self):
        assert token_efficiency_score("anything", 0) == 1.0


class TestSplitter:
    def test_model_serving_has_split(self):
        try:
            train, val = create_gepa_datasets("databricks-model-serving")
            assert len(train) > 0
            if len(train) + (len(val) if val else 0) >= 5:
                assert val is not None
        except FileNotFoundError:
            pytest.skip("No ground_truth.yaml")

    def test_reproducible_splits(self):
        try:
            t1, v1 = create_gepa_datasets("databricks-model-serving", seed=42)
            t2, v2 = create_gepa_datasets("databricks-model-serving", seed=42)
            assert [t["id"] for t in t1] == [t["id"] for t in t2]
        except FileNotFoundError:
            pytest.skip("No ground_truth.yaml")

    def test_tasks_have_correct_keys(self):
        try:
            train, _ = create_gepa_datasets("databricks-model-serving")
            for task in train:
                assert "id" in task
                assert "input" in task
                assert "answer" in task
                assert "additional_context" in task
        except FileNotFoundError:
            pytest.skip("No ground_truth.yaml")

    def test_to_gepa_instances(self):
        try:
            train, _ = create_gepa_datasets("databricks-model-serving")
            instances = to_gepa_instances(train)
            assert len(instances) == len(train)
            for inst in instances:
                assert "input" in inst
                assert "additional_context" in inst
                assert "answer" in inst
                assert "id" not in inst
        except FileNotFoundError:
            pytest.skip("No ground_truth.yaml")

    def test_bootstrap_tasks_generated(self):
        tasks = generate_bootstrap_tasks("databricks-model-serving")
        assert len(tasks) > 0
        for task in tasks:
            assert "id" in task
            assert "input" in task


@pytest.mark.skipif(not HAS_MLFLOW, reason="mlflow not installed")
class TestASI:
    def test_yes_scores_one(self):
        assert feedback_to_score(Feedback(name="test", value="yes")) == 1.0

    def test_no_scores_zero(self):
        assert feedback_to_score(Feedback(name="test", value="no")) == 0.0

    def test_skip_returns_none(self):
        assert feedback_to_score(Feedback(name="test", value="skip")) is None

    def test_feedback_to_asi_composite(self):
        feedbacks = [
            Feedback(name="syntax", value="yes", rationale="Valid"),
            Feedback(name="pattern", value="no", rationale="Missing X"),
            Feedback(name="optional", value="skip", rationale="N/A"),
        ]
        score, si = feedback_to_asi(feedbacks)
        assert score == pytest.approx(0.5)
        assert si["syntax"]["score"] == 1.0
        assert si["pattern"]["score"] == 0.0
        assert si["optional"]["status"] == "skipped"
        assert si["_summary"]["scored"] == 2


@pytest.mark.skipif(not HAS_GEPA, reason="gepa not installed")
class TestConfig:
    def test_presets_exist(self):
        from skill_test.optimize.config import PRESETS
        assert "quick" in PRESETS
        assert "standard" in PRESETS
        assert "thorough" in PRESETS

    def test_quick_has_fewer_calls(self):
        from skill_test.optimize.config import PRESETS
        assert PRESETS["quick"].engine.max_metric_calls < PRESETS["standard"].engine.max_metric_calls

    def test_presets_are_gepa_configs(self):
        from skill_test.optimize.config import PRESETS
        for name, cfg in PRESETS.items():
            assert isinstance(cfg, GEPAConfig), f"{name} is not GEPAConfig"
            assert isinstance(cfg.engine, EngineConfig)
            assert isinstance(cfg.reflection, ReflectionConfig)


class TestBootstrapMode:
    def test_nonexistent_skill_returns_empty(self):
        tasks = generate_bootstrap_tasks("nonexistent-skill-xyz")
        assert tasks == []

    def test_bootstrap_has_gepa_format(self):
        tasks = generate_bootstrap_tasks("databricks-model-serving")
        if not tasks:
            pytest.skip("No SKILL.md found")
        instances = to_gepa_instances(tasks)
        for inst in instances:
            assert isinstance(inst["input"], str)
            assert isinstance(inst["additional_context"], dict)


@pytest.mark.skipif(not HAS_GEPA, reason="gepa not installed")
class TestToolExtraction:
    def test_extract_tools(self):
        from skill_test.optimize.tools import extract_tool_descriptions, get_tool_stats
        stats = get_tool_stats()
        assert stats["modules"] > 0
        assert stats["total_tools"] > 0

    def test_tools_to_gepa_components(self):
        from skill_test.optimize.tools import extract_tool_descriptions, tools_to_gepa_components
        tool_map = extract_tool_descriptions(modules=["sql"])
        components = tools_to_gepa_components(tool_map)
        assert "tools_sql" in components
        assert "### TOOL:" in components["tools_sql"]


@pytest.mark.skipif(not HAS_GEPA, reason="gepa not installed")
class TestDryRun:
    def test_dry_run_skill_only(self):
        from skill_test.optimize.runner import optimize_skill
        try:
            result = optimize_skill("databricks-model-serving", preset="quick", dry_run=True)
            assert result.improvement == 0.0
            assert result.original_content == result.optimized_content
            assert result.gepa_result is None
            assert result.original_token_count > 0
        except FileNotFoundError:
            pytest.skip("SKILL.md not found")

    def test_dry_run_with_tools(self):
        from skill_test.optimize.runner import optimize_skill
        try:
            result = optimize_skill(
                "databricks-model-serving", preset="quick", dry_run=True,
                include_tools=True, tool_modules=["serving"],
            )
            assert SKILL_KEY in result.components
            assert "tools_serving" in result.components
            assert result.original_token_count > 0
        except FileNotFoundError:
            pytest.skip("SKILL.md not found")


# --------------------------------------------------------------------------
# E2E integration (requires GEPA + LLM API key)
# --------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_GEPA, reason="gepa not installed")
@pytest.mark.slow
class TestOptimizeE2E:
    def test_optimize_improves_quality_and_reduces_tokens(self):
        from skill_test.optimize.runner import optimize_skill
        result = optimize_skill(
            skill_name="databricks-spark-declarative-pipelines",
            mode="static",
            preset="quick",
        )
        assert result.optimized_score >= result.original_score
        assert result.optimized_token_count <= result.original_token_count * 1.05

        if result.val_scores:
            avg_val = sum(result.val_scores.values()) / len(result.val_scores)
            assert avg_val >= result.optimized_score - 0.05

        print(f"\nQuality: {result.original_score:.3f} -> {result.optimized_score:.3f}")
        print(f"Tokens: {result.original_token_count:,} -> {result.optimized_token_count:,}")

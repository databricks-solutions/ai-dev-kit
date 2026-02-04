"""Integration tests for trace evaluation.

Tests real trace file parsing and evaluation against expectations.
No mocks - uses actual file I/O and real JSONL parsing.
"""
import sys
from pathlib import Path

import pytest

# Add src to path for imports
_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root / "src") not in sys.path:
    sys.path.insert(0, str(_repo_root / "src"))


class TestRealTraceParsing:
    """Test actual JSONL parsing with real trace format."""

    def test_parse_real_trace_computes_metrics(self, real_trace_file):
        """Parse real trace and verify metrics computation."""
        from skill_test.trace.parser import parse_and_compute_metrics

        metrics = parse_and_compute_metrics(real_trace_file)

        # Verify basic metrics are computed
        assert metrics.session_id is not None
        assert metrics.session_id == "integration-test-session"
        assert metrics.total_tool_calls >= 0
        assert metrics.total_input_tokens >= 0
        assert metrics.total_output_tokens >= 0

    def test_parse_trace_extracts_tool_calls(self, real_trace_file):
        """Verify tool calls are properly extracted."""
        from skill_test.trace.parser import parse_and_compute_metrics

        metrics = parse_and_compute_metrics(real_trace_file)

        # Should have tool calls from the fixture
        assert metrics.total_tool_calls > 0
        assert "Read" in metrics.tool_counts
        assert "Write" in metrics.tool_counts
        assert "Bash" in metrics.tool_counts
        assert "mcp__databricks__execute_sql" in metrics.tool_counts

    def test_parse_trace_extracts_file_operations(self, real_trace_file):
        """Verify file operations are tracked."""
        from skill_test.trace.parser import parse_and_compute_metrics

        metrics = parse_and_compute_metrics(real_trace_file)

        # Should have file read and create operations
        assert len(metrics.files_read) > 0 or len(metrics.files_created) > 0

    def test_parse_trace_computes_token_totals(self, real_trace_file):
        """Verify token usage is aggregated correctly."""
        from skill_test.trace.parser import parse_and_compute_metrics

        metrics = parse_and_compute_metrics(real_trace_file)

        # Token totals should be computed from fixture data
        # Fixture has: 1500+1200+1000+800 = 4500 input tokens
        assert metrics.total_input_tokens > 0
        assert metrics.total_output_tokens > 0
        assert metrics.total_tokens == metrics.total_input_tokens + metrics.total_output_tokens

    def test_parse_trace_counts_turns(self, real_trace_file):
        """Verify turn counting works."""
        from skill_test.trace.parser import parse_and_compute_metrics

        metrics = parse_and_compute_metrics(real_trace_file)

        # Fixture has 4 assistant turns
        assert metrics.num_turns == 4

    def test_parse_trace_to_dict_serialization(self, real_trace_file):
        """Verify trace can be serialized to dict."""
        from skill_test.trace.parser import parse_and_compute_metrics

        metrics = parse_and_compute_metrics(real_trace_file)
        trace_dict = metrics.to_dict()

        # Verify structure matches what scorers expect
        assert "session_id" in trace_dict
        assert "tokens" in trace_dict
        assert "tools" in trace_dict
        assert "files" in trace_dict
        assert "conversation" in trace_dict

        assert "total" in trace_dict["tokens"]
        assert "by_name" in trace_dict["tools"]
        assert "by_category" in trace_dict["tools"]

    def test_parse_nonexistent_file_raises(self, tmp_path):
        """Verify proper error on missing file."""
        from skill_test.trace.parser import parse_and_compute_metrics

        with pytest.raises(FileNotFoundError):
            parse_and_compute_metrics(tmp_path / "nonexistent.jsonl")


class TestRealTraceEvaluation:
    """Test trace_eval command with real files and expectations."""

    def test_evaluate_local_trace_file(self, real_trace_file, real_skill_dir, cli_context):
        """Evaluate a real trace file against real manifest expectations."""
        from skill_test.cli.commands import trace_eval

        result = trace_eval(
            skill_name="integration-test-skill",
            ctx=cli_context,
            trace_path=str(real_trace_file)
        )

        # Should return structured result
        assert "success" in result
        assert "skill_name" in result
        assert result["skill_name"] == "integration-test-skill"
        assert "results" in result
        assert "all_violations" in result
        assert "traces_evaluated" in result
        assert result["traces_evaluated"] == 1

    def test_evaluate_trace_directory(self, real_trace_dir, real_skill_dir, cli_context):
        """Evaluate multiple trace files in a directory."""
        from skill_test.cli.commands import trace_eval

        result = trace_eval(
            skill_name="integration-test-skill",
            ctx=cli_context,
            trace_dir=str(real_trace_dir)
        )

        # Should evaluate all traces in directory
        assert result["traces_evaluated"] >= 2
        assert len(result["results"]) >= 2

    def test_evaluate_returns_scorer_results(self, real_trace_file, real_skill_dir, cli_context):
        """Verify scorer results are included in output."""
        from skill_test.cli.commands import trace_eval

        result = trace_eval(
            skill_name="integration-test-skill",
            ctx=cli_context,
            trace_path=str(real_trace_file)
        )

        # Should have scorer results
        assert len(result["results"]) > 0
        first_result = result["results"][0]
        assert "scorer_results" in first_result
        assert len(first_result["scorer_results"]) > 0

        # Each scorer result should have expected fields
        for scorer_result in first_result["scorer_results"]:
            assert "name" in scorer_result
            assert "value" in scorer_result
            assert "rationale" in scorer_result

    def test_evaluate_detects_tool_limit_violations(self, tmp_path, cli_context):
        """Verify tool limit violations are detected."""
        import json
        import yaml
        from datetime import datetime
        from skill_test.cli.commands import trace_eval

        # Create a trace with many Bash calls (exceeding limit)
        trace_path = tmp_path / "bash-heavy.jsonl"
        entries = []
        for i in range(25):  # Exceed the 20 Bash limit
            entries.append({
                "uuid": f"bash-{i}",
                "type": "assistant",
                "timestamp": datetime.now().isoformat(),
                "sessionId": "bash-test",
                "message": {
                    "model": "claude-3-5-sonnet-20241022",
                    "role": "assistant",
                    "usage": {"input_tokens": 100, "output_tokens": 50},
                    "content": [
                        {"type": "tool_use", "id": f"toolu_bash_{i}", "name": "Bash", "input": {"command": "ls"}}
                    ]
                }
            })

        with open(trace_path, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + '\n')

        result = trace_eval(
            skill_name="integration-test-skill",
            ctx=cli_context,
            trace_path=str(trace_path)
        )

        # Should detect violation
        violations = result.get("all_violations", [])
        tool_count_violations = [v for v in violations if "Bash" in v.get("rationale", "")]
        assert len(tool_count_violations) > 0

    def test_evaluate_validates_required_tools(self, tmp_path, cli_context):
        """Verify required tools check works."""
        import json
        import yaml
        from datetime import datetime
        from skill_test.cli.commands import trace_eval

        # Create a trace WITHOUT the required Read tool
        trace_path = tmp_path / "no-read.jsonl"
        entries = [
            {
                "uuid": "write-only",
                "type": "assistant",
                "timestamp": datetime.now().isoformat(),
                "sessionId": "no-read-test",
                "message": {
                    "model": "claude-3-5-sonnet-20241022",
                    "role": "assistant",
                    "usage": {"input_tokens": 100, "output_tokens": 50},
                    "content": [
                        {"type": "tool_use", "id": "toolu_write_1", "name": "Write", "input": {"file_path": "/test.txt"}}
                    ]
                }
            }
        ]

        with open(trace_path, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + '\n')

        result = trace_eval(
            skill_name="integration-test-skill",
            ctx=cli_context,
            trace_path=str(trace_path)
        )

        # Should detect missing required tool
        violations = result.get("all_violations", [])
        required_violations = [v for v in violations if "required" in v.get("scorer", "").lower()]
        assert len(required_violations) > 0

    def test_evaluate_missing_trace_returns_error(self, cli_context):
        """Verify proper error when trace file doesn't exist."""
        from skill_test.cli.commands import trace_eval

        result = trace_eval(
            skill_name="integration-test-skill",
            ctx=cli_context,
            trace_path="/nonexistent/path.jsonl"
        )

        assert result["success"] is False
        assert "error" in result

    def test_evaluate_no_source_returns_error(self, cli_context):
        """Verify error when no trace source provided."""
        from skill_test.cli.commands import trace_eval

        result = trace_eval(
            skill_name="integration-test-skill",
            ctx=cli_context,
        )

        assert result["success"] is False
        assert "error" in result
        assert "must provide" in result["error"].lower()

    def test_evaluate_no_expectations_returns_error(self, tmp_path, real_trace_file):
        """Verify error when skill has no trace_expectations."""
        import sys
        from skill_test.cli.commands import trace_eval, CLIContext

        # Create skill without trace_expectations
        skill_dir = tmp_path / "skills" / "no-expectations-skill"
        skill_dir.mkdir(parents=True)

        import yaml
        manifest = {
            "skill_name": "no-expectations-skill",
            "scorers": {"enabled": ["python_syntax"]}
            # No trace_expectations
        }
        with open(skill_dir / "manifest.yaml", 'w') as f:
            yaml.dump(manifest, f)

        ctx = CLIContext(base_path=tmp_path / "skills")
        result = trace_eval(
            skill_name="no-expectations-skill",
            ctx=ctx,
            trace_path=str(real_trace_file)
        )

        assert result["success"] is False
        assert "trace_expectations" in result["error"].lower()


class TestRealMlflowTraceEvaluation:
    """Test trace evaluation from MLflow.

    These tests require MLflow and Databricks configuration.
    """

    def test_evaluate_mlflow_trace(self, mlflow_configured, databricks_configured, real_skill_dir, cli_context):
        """Fetch and evaluate trace from real MLflow experiment."""
        from skill_test.trace.mlflow_integration import get_latest_trace_run
        from skill_test.cli.commands import trace_eval

        # Get real run ID from MLflow
        try:
            run_id = get_latest_trace_run("/Shared/skill-test-traces")
            if not run_id:
                pytest.skip("No MLflow traces available")
        except Exception as e:
            pytest.skip(f"MLflow not accessible: {e}")

        result = trace_eval(
            skill_name="integration-test-skill",
            ctx=cli_context,
            run_id=run_id
        )

        assert "success" in result
        assert "results" in result


class TestTraceMetricsSummary:
    """Test trace metrics summary generation."""

    def test_metrics_summary_included_in_results(self, real_trace_file, real_skill_dir, cli_context):
        """Verify metrics summary is included in evaluation results."""
        from skill_test.cli.commands import trace_eval

        result = trace_eval(
            skill_name="integration-test-skill",
            ctx=cli_context,
            trace_path=str(real_trace_file)
        )

        assert result["success"] in [True, False]
        first_result = result["results"][0]
        assert "metrics_summary" in first_result

        summary = first_result["metrics_summary"]
        assert "session_id" in summary
        assert "total_tokens" in summary
        assert "total_tool_calls" in summary
        assert "num_turns" in summary

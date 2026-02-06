"""Version comparison for regression detection."""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict


@dataclass
class BaselineMetrics:
    """Baseline metrics for comparison."""

    skill_name: str
    run_id: str
    timestamp: str
    metrics: dict[str, float]
    test_count: int
    git_commit: str | None = None
    skill_version: str | None = None


@dataclass
class ComparisonResult:
    """Result of comparing current metrics to baseline."""

    skill_name: str
    improved: list[str]
    regressed: list[str]
    unchanged: list[str]
    new_metrics: list[str]
    removed_metrics: list[str]
    passed_gates: bool
    details: dict[str, dict[str, float]]


def save_baseline(
    skill_name: str,
    run_id: str,
    metrics: dict[str, float],
    test_count: int,
    baselines_dir: Path = None,
    git_commit: str | None = None,
    skill_version: str | None = None,
) -> Path:
    """
    Save evaluation metrics as a baseline.

    Args:
        skill_name: Name of the skill
        run_id: MLflow run ID
        metrics: Evaluation metrics dict
        test_count: Number of test cases
        baselines_dir: Directory for baselines (default: baselines/)
        git_commit: Optional git commit hash
        skill_version: Optional skill version string

    Returns:
        Path to saved baseline file
    """
    if baselines_dir is None:
        baselines_dir = Path(".test/baselines")

    baselines_dir.mkdir(parents=True, exist_ok=True)

    baseline = BaselineMetrics(
        skill_name=skill_name,
        run_id=run_id,
        timestamp=datetime.now().isoformat(),
        metrics=metrics,
        test_count=test_count,
        git_commit=git_commit,
        skill_version=skill_version,
    )

    baseline_path = baselines_dir / f"{skill_name}.json"
    with open(baseline_path, "w") as f:
        json.dump(asdict(baseline), f, indent=2)

    return baseline_path


def load_baseline(skill_name: str, baselines_dir: Path = None) -> BaselineMetrics | None:
    """
    Load baseline metrics for a skill.

    Returns None if no baseline exists.
    """
    if baselines_dir is None:
        baselines_dir = Path(".test/baselines")

    baseline_path = baselines_dir / f"{skill_name}.json"

    if not baseline_path.exists():
        return None

    with open(baseline_path) as f:
        data = json.load(f)

    return BaselineMetrics(**data)


def compare_baselines(
    skill_name: str, current_metrics: dict[str, float], threshold: float = 0.05, baselines_dir: Path = None
) -> ComparisonResult:
    """
    Compare current metrics against baseline.

    Args:
        skill_name: Name of the skill
        current_metrics: Current evaluation metrics
        threshold: Minimum change to be considered regression/improvement
        baselines_dir: Directory containing baselines

    Returns:
        ComparisonResult with categorized metrics
    """
    baseline = load_baseline(skill_name, baselines_dir)

    if baseline is None:
        # No baseline - all metrics are new
        return ComparisonResult(
            skill_name=skill_name,
            improved=[],
            regressed=[],
            unchanged=[],
            new_metrics=list(current_metrics.keys()),
            removed_metrics=[],
            passed_gates=True,
            details={k: {"current": v, "baseline": None, "delta": None} for k, v in current_metrics.items()},
        )

    improved = []
    regressed = []
    unchanged = []
    new_metrics = []
    removed_metrics = []
    details = {}

    baseline_metrics = baseline.metrics

    # Check current metrics against baseline
    for metric, current_value in current_metrics.items():
        if metric not in baseline_metrics:
            new_metrics.append(metric)
            details[metric] = {"current": current_value, "baseline": None, "delta": None}
            continue

        baseline_value = baseline_metrics[metric]
        delta = current_value - baseline_value

        details[metric] = {"current": current_value, "baseline": baseline_value, "delta": delta}

        if abs(delta) < threshold:
            unchanged.append(metric)
        elif delta > 0:
            improved.append(metric)
        else:
            regressed.append(metric)

    # Check for removed metrics
    for metric in baseline_metrics:
        if metric not in current_metrics:
            removed_metrics.append(metric)
            details[metric] = {"current": None, "baseline": baseline_metrics[metric], "delta": None}

    # Determine if quality gates pass (no regressions in critical metrics)
    critical_metrics = ["syntax_valid/score/mean", "no_hallucinated_apis/score/mean"]
    passed_gates = not any(m in regressed for m in critical_metrics)

    return ComparisonResult(
        skill_name=skill_name,
        improved=improved,
        regressed=regressed,
        unchanged=unchanged,
        new_metrics=new_metrics,
        removed_metrics=removed_metrics,
        passed_gates=passed_gates,
        details=details,
    )


def format_comparison_report(result: ComparisonResult) -> str:
    """Format comparison result as a human-readable report."""
    lines = [f"Comparison Report: {result.skill_name}", "=" * 50, ""]

    if result.passed_gates:
        lines.append("Status: PASSED (no critical regressions)")
    else:
        lines.append("Status: FAILED (critical regressions detected)")

    lines.append("")

    if result.improved:
        lines.append(f"Improved ({len(result.improved)}):")
        for m in result.improved:
            d = result.details[m]
            lines.append(f"  + {m}: {d['baseline']:.3f} -> {d['current']:.3f} ({d['delta']:+.3f})")

    if result.regressed:
        lines.append(f"\nRegressed ({len(result.regressed)}):")
        for m in result.regressed:
            d = result.details[m]
            lines.append(f"  - {m}: {d['baseline']:.3f} -> {d['current']:.3f} ({d['delta']:+.3f})")

    if result.unchanged:
        lines.append(f"\nUnchanged ({len(result.unchanged)}):")
        for m in result.unchanged:
            d = result.details[m]
            lines.append(f"  = {m}: {d['current']:.3f}")

    if result.new_metrics:
        lines.append(f"\nNew metrics ({len(result.new_metrics)}):")
        for m in result.new_metrics:
            d = result.details[m]
            lines.append(f"  * {m}: {d['current']:.3f}")

    if result.removed_metrics:
        lines.append(f"\nRemoved metrics ({len(result.removed_metrics)}):")
        for m in result.removed_metrics:
            lines.append(f"  x {m}")

    return "\n".join(lines)

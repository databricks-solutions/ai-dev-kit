"""CLI commands for /skill-test interactive workflow.

This module provides commands for the /skill-test CLI skill. The actual MCP tools
are injected via CLIContext at runtime by the skill handler.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Literal
import yaml

from ..grp.executor import (
    DatabricksExecutionConfig,
    execute_code_blocks,
    execute_code_blocks_on_databricks,
    MCPExecuteCommand,
    MCPExecuteSQL,
    MCPGetBestWarehouse,
    MCPGetBestCluster,
)
from ..grp.pipeline import (
    generate_candidate,
)
from ..fixtures import (
    TestFixtureConfig,
    FixtureResult,
    setup_fixtures,
    teardown_fixtures,
)
from ..fixtures.setup import MCPUploadFile
from ..dataset import YAMLDatasetSource


@dataclass
class CLIContext:
    """Context for CLI commands with MCP tool injection.

    The skill handler injects actual MCP tool functions at runtime.
    This allows the CLI commands to execute code on Databricks.
    """

    # MCP tools for Databricks execution
    mcp_execute_command: Optional[MCPExecuteCommand] = None
    mcp_execute_sql: Optional[MCPExecuteSQL] = None
    mcp_upload_file: Optional[MCPUploadFile] = None
    mcp_get_best_warehouse: Optional[MCPGetBestWarehouse] = None
    mcp_get_best_cluster: Optional[MCPGetBestCluster] = None

    # Configuration
    base_path: Path = field(default_factory=lambda: Path(".test/skills"))
    execution_config: DatabricksExecutionConfig = field(
        default_factory=DatabricksExecutionConfig
    )

    def has_databricks_tools(self) -> bool:
        """Check if Databricks execution tools are available."""
        return self.mcp_execute_command is not None or self.mcp_execute_sql is not None


@dataclass
class InteractiveResult:
    """Result of interactive test generation."""

    success: bool
    test_id: str
    skill_name: str
    execution_mode: Literal["databricks", "local", "dry_run"]

    # Execution results
    total_blocks: int = 0
    passed_blocks: int = 0
    execution_details: List[Dict[str, Any]] = field(default_factory=list)

    # Fixture results
    fixtures_setup: bool = False
    fixtures_teardown: bool = False
    fixture_details: Optional[Dict[str, Any]] = None

    # Output handling
    saved_to: Optional[str] = None  # "ground_truth.yaml" or "candidates.yaml"
    auto_approved: bool = False  # True if all blocks passed and auto-promoted

    # Errors
    error: Optional[str] = None
    message: str = ""


def run(
    skill_name: str,
    ctx: CLIContext,
    test_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Run evaluation against ground truth for a skill.

    Args:
        skill_name: Name of the skill to evaluate
        ctx: CLI context with MCP tools
        test_ids: Optional list of specific test IDs to run

    Returns:
        Dictionary with evaluation results
    """
    # Load ground truth
    gt_path = ctx.base_path / skill_name / "ground_truth.yaml"
    if not gt_path.exists():
        return {
            "success": False,
            "error": f"No ground_truth.yaml found for skill '{skill_name}'",
            "path": str(gt_path),
        }

    source = YAMLDatasetSource(gt_path)
    records = source.load()

    if test_ids:
        records = [r for r in records if r.id in test_ids]

    results = []
    passed = 0
    failed = 0

    for record in records:
        response = record.outputs.get("response", "") if record.outputs else ""

        # Execute code blocks
        if (
            ctx.has_databricks_tools()
            and ctx.mcp_execute_command
            and ctx.mcp_execute_sql
        ):
            exec_result = execute_code_blocks_on_databricks(
                response,
                ctx.execution_config,
                ctx.mcp_execute_command,
                ctx.mcp_execute_sql,
                ctx.mcp_get_best_warehouse,
                ctx.mcp_get_best_cluster,
            )
            execution_mode = exec_result.execution_mode
            total_blocks = exec_result.total_blocks
            passed_blocks = exec_result.passed_blocks
            details = exec_result.details
        else:
            # Local execution (syntax validation only)
            total_blocks, passed_blocks, details = execute_code_blocks(response)
            execution_mode = "local"

        test_passed = total_blocks == 0 or passed_blocks == total_blocks

        results.append(
            {
                "id": record.id,
                "passed": test_passed,
                "total_blocks": total_blocks,
                "passed_blocks": passed_blocks,
                "execution_mode": execution_mode,
                "details": details,
            }
        )

        if test_passed:
            passed += 1
        else:
            failed += 1

    return {
        "success": failed == 0,
        "skill_name": skill_name,
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "results": results,
    }


def regression(
    skill_name: str,
    ctx: CLIContext,
    baseline_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Compare current results against baseline.

    Args:
        skill_name: Name of the skill to evaluate
        ctx: CLI context with MCP tools
        baseline_run_id: Optional specific baseline run ID to compare against

    Returns:
        Dictionary with regression comparison results
    """
    # Load baseline
    baseline_path = ctx.base_path.parent / "baselines" / skill_name / "baseline.yaml"
    if not baseline_path.exists():
        return {
            "success": False,
            "error": f"No baseline found for skill '{skill_name}'",
            "path": str(baseline_path),
            "hint": "Run 'run' first and save as baseline",
        }

    with open(baseline_path) as f:
        baseline = yaml.safe_load(f)

    # Run current evaluation
    current = run(skill_name, ctx)

    if not current.get("success", False) and "error" in current:
        return current

    # Compare metrics
    baseline_metrics = baseline.get("metrics", {})
    current_metrics = {
        "pass_rate": current["passed"] / current["total"]
        if current["total"] > 0
        else 0,
        "total_tests": current["total"],
        "passed_tests": current["passed"],
    }

    regressions = []
    improvements = []

    baseline_pass_rate = baseline_metrics.get("pass_rate", 0)
    current_pass_rate = current_metrics["pass_rate"]

    if current_pass_rate < baseline_pass_rate:
        regressions.append(
            {
                "metric": "pass_rate",
                "baseline": baseline_pass_rate,
                "current": current_pass_rate,
                "delta": current_pass_rate - baseline_pass_rate,
            }
        )
    elif current_pass_rate > baseline_pass_rate:
        improvements.append(
            {
                "metric": "pass_rate",
                "baseline": baseline_pass_rate,
                "current": current_pass_rate,
                "delta": current_pass_rate - baseline_pass_rate,
            }
        )

    return {
        "success": len(regressions) == 0,
        "skill_name": skill_name,
        "baseline_run_id": baseline.get("run_id"),
        "baseline_metrics": baseline_metrics,
        "current_metrics": current_metrics,
        "regressions": regressions,
        "improvements": improvements,
        "passed_gates": len(regressions) == 0,
    }


def init(
    skill_name: str,
    ctx: CLIContext,
) -> Dict[str, Any]:
    """Initialize test scaffolding for a new skill.

    Creates the directory structure and template files for testing a skill.

    Args:
        skill_name: Name of the skill to initialize
        ctx: CLI context

    Returns:
        Dictionary with initialization status
    """
    skill_dir = ctx.base_path / skill_name

    if skill_dir.exists():
        return {
            "success": False,
            "error": f"Skill '{skill_name}' already has test definitions",
            "path": str(skill_dir),
        }

    # Create directory
    skill_dir.mkdir(parents=True, exist_ok=True)

    # Create template ground_truth.yaml
    gt_template = {
        "metadata": {
            "skill_name": skill_name,
            "version": "0.1.0",
            "created_at": datetime.now().isoformat(),
        },
        "test_cases": [
            {
                "id": f"{skill_name}_001",
                "inputs": {"prompt": "Example prompt for the skill"},
                "outputs": {
                    "response": "Example response from the skill",
                    "execution_success": True,
                },
                "expectations": {
                    "expected_facts": ["fact1", "fact2"],
                    "expected_patterns": [
                        {"pattern": "pattern_to_match", "min_count": 1}
                    ],
                    "guidelines": ["Guideline for evaluation"],
                },
                "metadata": {"category": "happy_path", "difficulty": "easy"},
            }
        ],
    }

    gt_path = skill_dir / "ground_truth.yaml"
    with open(gt_path, "w") as f:
        yaml.dump(gt_template, f, default_flow_style=False, sort_keys=False)

    # Create empty candidates.yaml
    candidates_template = {"candidates": []}
    candidates_path = skill_dir / "candidates.yaml"
    with open(candidates_path, "w") as f:
        yaml.dump(candidates_template, f, default_flow_style=False, sort_keys=False)

    # Create manifest.yaml
    manifest_template = {
        "skill_name": skill_name,
        "description": f"Test cases for {skill_name} skill",
        "triggers": [f"{skill_name} related prompt"],
        "scorers": {
            "enabled": [
                "python_syntax",
                "sql_syntax",
                "pattern_adherence",
                "no_hallucinated_apis",
                "expected_facts_present",
            ],
            "llm_scorers": ["Safety", "guidelines_from_expectations"],
            "default_guidelines": [
                "Response must address the user's request completely",
                "Code examples must follow documented best practices",
                "Response must use modern APIs (not deprecated ones)",
            ],
        },
        "quality_gates": {
            "syntax_valid": 1.0,
            "pattern_adherence": 0.9,
            "execution_success": 0.8,
        },
    }
    manifest_path = skill_dir / "manifest.yaml"
    with open(manifest_path, "w") as f:
        yaml.dump(manifest_template, f, default_flow_style=False, sort_keys=False)

    return {
        "success": True,
        "skill_name": skill_name,
        "path": str(skill_dir),
        "files_created": ["ground_truth.yaml", "candidates.yaml", "manifest.yaml"],
        "message": f"Initialized test scaffolding for '{skill_name}'",
    }


def sync(
    skill_name: str,
    ctx: CLIContext,
    direction: Literal["to_uc", "from_uc"] = "to_uc",
) -> Dict[str, Any]:
    """Sync YAML test definitions with Unity Catalog (stub for Phase 2).

    Args:
        skill_name: Name of the skill to sync
        ctx: CLI context
        direction: Sync direction - "to_uc" or "from_uc"

    Returns:
        Dictionary with sync status
    """
    return {
        "success": False,
        "error": "UC sync not yet implemented (Phase 2)",
        "skill_name": skill_name,
        "direction": direction,
        "hint": "Use YAML files directly for now",
    }


def baseline(
    skill_name: str,
    ctx: CLIContext,
) -> Dict[str, Any]:
    """Save current evaluation results as baseline for regression testing.

    Runs the evaluation and saves the metrics as a baseline that can be
    compared against in future runs using the `regression` command.

    Args:
        skill_name: Name of the skill to baseline
        ctx: CLI context with MCP tools

    Returns:
        Dictionary with baseline creation status
    """
    # Run evaluation first
    results = run(skill_name, ctx)

    if not results.get("success", False) and "error" in results:
        return results

    # Create baseline directory
    baseline_dir = ctx.base_path.parent / "baselines" / skill_name
    baseline_dir.mkdir(parents=True, exist_ok=True)

    # Calculate metrics
    total = results.get("total", 0)
    passed = results.get("passed", 0)
    pass_rate = passed / total if total > 0 else 0

    baseline_data = {
        "run_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "created_at": datetime.now().isoformat(),
        "skill_name": skill_name,
        "metrics": {
            "pass_rate": pass_rate,
            "total_tests": total,
            "passed_tests": passed,
            "failed_tests": results.get("failed", 0),
        },
        "test_results": [
            {
                "id": r["id"],
                "passed": r["passed"],
                "execution_mode": r.get("execution_mode", "unknown"),
            }
            for r in results.get("results", [])
        ],
    }

    baseline_path = baseline_dir / "baseline.yaml"
    with open(baseline_path, "w") as f:
        yaml.dump(baseline_data, f, default_flow_style=False, sort_keys=False)

    return {
        "success": True,
        "skill_name": skill_name,
        "baseline_path": str(baseline_path),
        "metrics": baseline_data["metrics"],
        "message": f"Baseline saved to {baseline_path}",
    }


def mlflow_eval(
    skill_name: str,
    ctx: CLIContext,  # Reserved for future Databricks execution integration
) -> Dict[str, Any]:
    """Run MLflow evaluation with LLM judges.

    Executes the full MLflow evaluation pipeline including LLM-based scorers
    and logs results to MLflow for tracking.

    Args:
        skill_name: Name of the skill to evaluate
        ctx: CLI context with MCP tools (reserved for future use)

    Returns:
        Dictionary with MLflow evaluation results
    """
    _ = ctx  # Reserved for future Databricks execution integration
    try:
        from ..runners import evaluate_skill
    except ImportError as e:
        return {
            "success": False,
            "error": f"Failed to import evaluate_skill: {e}",
            "hint": "Ensure mlflow and required dependencies are installed",
        }

    try:
        results = evaluate_skill(skill_name)
        return {
            "success": True,
            "skill_name": skill_name,
            "results": results,
            "message": f"MLflow evaluation complete for '{skill_name}'",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "skill_name": skill_name,
            "hint": "Check MLflow configuration and ground_truth.yaml exists",
        }


def interactive(
    skill_name: str,
    prompt: str,
    response: str,
    ctx: CLIContext,
    fixture_config: Optional[TestFixtureConfig] = None,
    auto_approve_on_success: bool = True,
) -> InteractiveResult:
    """Interactive test generation with Databricks execution.

    This is the core workflow for /skill-test:
    1. Optionally set up fixtures (catalog, schema, volume, tables)
    2. Execute code blocks on Databricks (serverless by default)
    3. If ALL blocks pass and auto_approve_on_success: save to ground_truth.yaml
    4. If ANY block fails: save to candidates.yaml for GRP review
    5. Optionally tear down fixtures

    Args:
        skill_name: Name of the skill being tested
        prompt: The test prompt
        response: The skill's response containing code blocks
        ctx: CLI context with MCP tools
        fixture_config: Optional fixture configuration for test setup
        auto_approve_on_success: If True, auto-save to ground_truth on success

    Returns:
        InteractiveResult with execution details and outcome
    """
    test_id = f"grp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    result = InteractiveResult(
        success=False, test_id=test_id, skill_name=skill_name, execution_mode="local"
    )

    # 1. Set up fixtures if provided
    if fixture_config and ctx.mcp_execute_sql and ctx.mcp_upload_file:
        fixture_result = setup_fixtures(
            fixture_config,
            ctx.mcp_execute_sql,
            ctx.mcp_upload_file,
            ctx.mcp_get_best_warehouse,
            base_path=str(ctx.base_path.parent.parent),  # Go up to skill-test root
        )
        result.fixtures_setup = fixture_result.success
        result.fixture_details = fixture_result.details

        if not fixture_result.success:
            result.error = f"Fixture setup failed: {fixture_result.error}"
            result.message = fixture_result.message
            return result

    # 2. Execute code blocks
    if ctx.has_databricks_tools() and ctx.mcp_execute_command and ctx.mcp_execute_sql:
        exec_result = execute_code_blocks_on_databricks(
            response,
            ctx.execution_config,
            ctx.mcp_execute_command,
            ctx.mcp_execute_sql,
            ctx.mcp_get_best_warehouse,
            ctx.mcp_get_best_cluster,
        )
        result.execution_mode = exec_result.execution_mode
        result.total_blocks = exec_result.total_blocks
        result.passed_blocks = exec_result.passed_blocks
        result.execution_details = exec_result.details
    else:
        # Fall back to local execution
        total, passed, details = execute_code_blocks(response)
        result.execution_mode = "local"
        result.total_blocks = total
        result.passed_blocks = passed
        result.execution_details = details

    all_passed = result.total_blocks == 0 or result.passed_blocks == result.total_blocks

    # 3. Save results
    skill_dir = ctx.base_path / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)

    if all_passed and auto_approve_on_success:
        # Auto-approve: save directly to ground_truth.yaml
        gt_path = skill_dir / "ground_truth.yaml"

        # Load existing or create new
        if gt_path.exists():
            with open(gt_path) as f:
                gt_data = yaml.safe_load(f) or {"test_cases": []}
        else:
            gt_data = {"test_cases": []}

        # Add new test case
        new_case = {
            "id": test_id,
            "inputs": {"prompt": prompt},
            "outputs": {"response": response, "execution_success": True},
            "expectations": {
                "expected_facts": [],  # To be filled by reviewer
                "expected_patterns": [],
                "guidelines": [],
            },
            "metadata": {
                "category": "happy_path",
                "source": "interactive",
                "created_at": datetime.now().isoformat(),
                "execution_verified": {
                    "mode": result.execution_mode,
                    "verified_date": datetime.now().strftime("%Y-%m-%d"),
                },
            },
        }

        # Add fixture info if used
        if fixture_config:
            new_case["fixtures"] = {
                "catalog": fixture_config.catalog,
                "schema": fixture_config.schema,
                "volume": fixture_config.volume,
                "files": [
                    {"local_path": f.local_path, "volume_path": f.volume_path}
                    for f in fixture_config.files
                ],
                "tables": [
                    {"name": t.name, "ddl": t.ddl} for t in fixture_config.tables
                ],
                "cleanup_after": fixture_config.cleanup_after,
            }

        gt_data["test_cases"].append(new_case)

        with open(gt_path, "w") as f:
            yaml.dump(gt_data, f, default_flow_style=False, sort_keys=False)

        result.saved_to = "ground_truth.yaml"
        result.auto_approved = True
        result.success = True
        result.message = f"All {result.total_blocks} code blocks passed. Auto-approved to ground_truth.yaml"

    else:
        # Save to candidates for GRP review
        candidate = generate_candidate(skill_name, prompt, response)

        # Override execution details with our Databricks results
        candidate.code_blocks_found = result.total_blocks
        candidate.code_blocks_passed = result.passed_blocks
        candidate.execution_details = result.execution_details
        candidate.execution_success = all_passed

        candidates_path = skill_dir / "candidates.yaml"

        # Load existing or create new
        if candidates_path.exists():
            with open(candidates_path) as f:
                candidates_data = yaml.safe_load(f) or {"candidates": []}
        else:
            candidates_data = {"candidates": []}

        # We need to serialize the candidate properly
        candidate_dict = {
            "id": candidate.id,
            "skill_name": candidate.skill_name,
            "status": "pending",
            "prompt": candidate.prompt,
            "response": candidate.response,
            "execution_success": candidate.execution_success,
            "code_blocks_found": candidate.code_blocks_found,
            "code_blocks_passed": candidate.code_blocks_passed,
            "execution_details": candidate.execution_details,
            "created_at": candidate.created_at.isoformat(),
        }

        if candidate.diagnosis:
            candidate_dict["diagnosis"] = {
                "error": candidate.diagnosis.error,
                "code_block": candidate.diagnosis.code_block,
                "suggested_action": candidate.diagnosis.suggested_action,
            }

        candidates_data["candidates"].append(candidate_dict)

        with open(candidates_path, "w") as f:
            yaml.dump(candidates_data, f, default_flow_style=False, sort_keys=False)

        result.saved_to = "candidates.yaml"
        result.auto_approved = False
        result.success = True
        failed_count = result.total_blocks - result.passed_blocks
        result.message = f"{failed_count}/{result.total_blocks} code blocks failed. Saved to candidates.yaml for GRP review"

    # 4. Tear down fixtures if configured
    if fixture_config and fixture_config.cleanup_after and ctx.mcp_execute_sql:
        teardown_result = teardown_fixtures(
            fixture_config,
            ctx.mcp_execute_sql,
            ctx.mcp_get_best_warehouse,
        )
        result.fixtures_teardown = teardown_result.success
        if result.fixture_details:
            result.fixture_details["teardown"] = teardown_result.details

    return result


def scorers(
    skill_name: str,
    ctx: CLIContext,
) -> Dict[str, Any]:
    """List configured scorers for a skill.

    Reads the manifest.yaml for the skill and returns the scorer configuration.

    Args:
        skill_name: Name of the skill
        ctx: CLI context

    Returns:
        Dictionary with scorer configuration
    """
    manifest_path = ctx.base_path / skill_name / "manifest.yaml"
    if not manifest_path.exists():
        return {
            "success": False,
            "error": f"No manifest found for skill '{skill_name}'",
            "path": str(manifest_path),
        }

    with open(manifest_path) as f:
        manifest = yaml.safe_load(f) or {}

    # Support both new flat format and existing nested format
    if "scorers" in manifest:
        scorer_config = manifest["scorers"]
    elif "evaluation" in manifest and "scorers" in manifest["evaluation"]:
        # Legacy format
        eval_scorers = manifest["evaluation"]["scorers"]
        scorer_config = {
            "enabled": eval_scorers.get("tier1", []) + eval_scorers.get("tier2", []),
            "llm_scorers": eval_scorers.get("tier3", []),
        }
    else:
        scorer_config = {}

    return {
        "success": True,
        "skill_name": skill_name,
        "enabled_scorers": scorer_config.get("enabled", []),
        "llm_scorers": scorer_config.get("llm_scorers", []),
        "default_guidelines": scorer_config.get("default_guidelines", []),
        "manifest_path": str(manifest_path),
    }


def scorers_update(
    skill_name: str,
    ctx: CLIContext,
    add_scorers: Optional[List[str]] = None,
    remove_scorers: Optional[List[str]] = None,
    add_guidelines: Optional[List[str]] = None,
    remove_guidelines: Optional[List[str]] = None,
    set_guidelines: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Update scorer configuration for a skill.

    Modifies the manifest.yaml to add/remove scorers or update default guidelines.

    Args:
        skill_name: Name of the skill
        ctx: CLI context
        add_scorers: List of scorer names to add to enabled list
        remove_scorers: List of scorer names to remove
        add_guidelines: List of guidelines to add to default_guidelines
        remove_guidelines: List of guidelines to remove
        set_guidelines: If provided, replaces all default_guidelines

    Returns:
        Dictionary with update status and new configuration
    """
    manifest_path = ctx.base_path / skill_name / "manifest.yaml"
    if not manifest_path.exists():
        return {
            "success": False,
            "error": f"No manifest found for skill '{skill_name}'",
            "path": str(manifest_path),
        }

    with open(manifest_path) as f:
        manifest = yaml.safe_load(f) or {}

    # Initialize scorers section if not present
    if "scorers" not in manifest:
        # Check for legacy format and migrate
        if "evaluation" in manifest and "scorers" in manifest["evaluation"]:
            eval_scorers = manifest["evaluation"]["scorers"]
            manifest["scorers"] = {
                "enabled": eval_scorers.get("tier1", [])
                + eval_scorers.get("tier2", []),
                "llm_scorers": eval_scorers.get("tier3", []),
                "default_guidelines": [],
            }
        else:
            manifest["scorers"] = {
                "enabled": [],
                "llm_scorers": [],
                "default_guidelines": [],
            }

    scorer_config = manifest["scorers"]

    # Ensure lists exist
    if "enabled" not in scorer_config:
        scorer_config["enabled"] = []
    if "llm_scorers" not in scorer_config:
        scorer_config["llm_scorers"] = []
    if "default_guidelines" not in scorer_config:
        scorer_config["default_guidelines"] = []

    changes = []

    # Add scorers
    if add_scorers:
        for scorer_name in add_scorers:
            # Determine if it's an LLM scorer or deterministic
            llm_scorers = ["Safety", "Guidelines", "guidelines_from_expectations"]
            if scorer_name in llm_scorers or scorer_name.startswith("Guidelines:"):
                if scorer_name not in scorer_config["llm_scorers"]:
                    scorer_config["llm_scorers"].append(scorer_name)
                    changes.append(f"Added LLM scorer: {scorer_name}")
            else:
                if scorer_name not in scorer_config["enabled"]:
                    scorer_config["enabled"].append(scorer_name)
                    changes.append(f"Added scorer: {scorer_name}")

    # Remove scorers
    if remove_scorers:
        for scorer_name in remove_scorers:
            if scorer_name in scorer_config["enabled"]:
                scorer_config["enabled"].remove(scorer_name)
                changes.append(f"Removed scorer: {scorer_name}")
            if scorer_name in scorer_config["llm_scorers"]:
                scorer_config["llm_scorers"].remove(scorer_name)
                changes.append(f"Removed LLM scorer: {scorer_name}")

    # Handle guidelines
    if set_guidelines is not None:
        scorer_config["default_guidelines"] = set_guidelines
        changes.append(f"Set {len(set_guidelines)} default guidelines")
    else:
        if add_guidelines:
            for guideline in add_guidelines:
                if guideline not in scorer_config["default_guidelines"]:
                    scorer_config["default_guidelines"].append(guideline)
                    changes.append(f"Added guideline: {guideline[:50]}...")

        if remove_guidelines:
            for guideline in remove_guidelines:
                if guideline in scorer_config["default_guidelines"]:
                    scorer_config["default_guidelines"].remove(guideline)
                    changes.append(f"Removed guideline: {guideline[:50]}...")

    # Save updated manifest
    with open(manifest_path, "w") as f:
        yaml.dump(manifest, f, default_flow_style=False, sort_keys=False)

    return {
        "success": True,
        "skill_name": skill_name,
        "changes": changes,
        "enabled_scorers": scorer_config["enabled"],
        "llm_scorers": scorer_config["llm_scorers"],
        "default_guidelines": scorer_config["default_guidelines"],
        "manifest_path": str(manifest_path),
    }


def setup_test_fixtures(
    skill_name: str,
    test_id: str,
    ctx: CLIContext,
) -> FixtureResult:
    """Set up fixtures for a specific test case from ground_truth.yaml.

    Reads the fixture configuration from the test case and sets up
    the required infrastructure.

    Args:
        skill_name: Name of the skill
        test_id: ID of the test case with fixture definition
        ctx: CLI context with MCP tools

    Returns:
        FixtureResult with setup status
    """
    # Load ground truth
    gt_path = ctx.base_path / skill_name / "ground_truth.yaml"
    if not gt_path.exists():
        return FixtureResult(
            success=False,
            message=f"No ground_truth.yaml found for skill '{skill_name}'",
            error="File not found",
        )

    with open(gt_path) as f:
        gt_data = yaml.safe_load(f)

    # Find test case
    test_case = None
    for case in gt_data.get("test_cases", []):
        if case.get("id") == test_id:
            test_case = case
            break

    if not test_case:
        return FixtureResult(
            success=False,
            message=f"Test case '{test_id}' not found",
            error="Test case not found",
        )

    # Check for fixtures
    fixtures_def = test_case.get("fixtures")
    if not fixtures_def:
        return FixtureResult(
            success=True,
            message="No fixtures defined for this test case",
            details={"test_id": test_id},
        )

    # Create fixture config
    fixture_config = TestFixtureConfig.from_dict(fixtures_def)

    # Check for required MCP tools
    if not ctx.mcp_execute_sql:
        return FixtureResult(
            success=False,
            message="MCP execute_sql tool required for fixture setup",
            error="Missing MCP tool",
        )

    if not ctx.mcp_upload_file and fixture_config.files:
        return FixtureResult(
            success=False,
            message="MCP upload_file tool required for file fixtures",
            error="Missing MCP tool",
        )

    # Set up fixtures
    return setup_fixtures(
        fixture_config,
        ctx.mcp_execute_sql,
        ctx.mcp_upload_file,
        ctx.mcp_get_best_warehouse,
        base_path=str(ctx.base_path.parent.parent),
    )

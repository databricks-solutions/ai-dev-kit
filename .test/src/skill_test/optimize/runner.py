"""End-to-end orchestrator for GEPA skill optimization.

Uses optimize_anything API: evaluator function + GEPAConfig.
Supports two evaluation modes:
  - skillbench (default): fast proxy using litellm.completion + judges
  - agent-eval (hybrid): proxy for GEPA iterations, real Claude Code agent
    for baseline scoring and final validation
  - agent-eval-full: real Claude Code agent for all GEPA iterations
"""

import copy
import difflib
from dataclasses import dataclass
from typing import Any

from gepa.optimize_anything import optimize_anything

from ..config import SkillTestConfig
from ..runners.evaluate import setup_mlflow
from .config import (
    get_preset,
    validate_reflection_context,
    estimate_pass_duration,
    DEFAULT_GEN_LM,
    DEFAULT_TOKEN_BUDGET,
)
from .utils import SKILL_KEY, count_tokens, find_skill_md
from .skillbench_evaluator import (
    create_skillbench_evaluator,
    build_skillbench_background,
)
from .splitter import (
    create_gepa_datasets,
    generate_bootstrap_tasks,
    to_gepa_instances,
    create_cross_skill_dataset,
)
from .tools import (
    extract_tool_descriptions,
    tools_to_gepa_components,
    get_tool_stats,
)


@dataclass
class OptimizationResult:
    """Result of a GEPA optimization run."""

    skill_name: str
    original_score: float
    optimized_score: float
    improvement: float
    original_content: str
    optimized_content: str
    original_token_count: int
    optimized_token_count: int
    token_reduction_pct: float
    diff_summary: str
    val_scores: dict[str, float]
    mlflow_run_id: str | None
    gepa_result: Any
    components: dict[str, str] | None = None
    original_components: dict[str, str] | None = None
    tool_map: Any = None
    evaluator_type: str = "skillbench"
    skillbench_side_info: dict[str, dict] | None = None
    # Agent evaluation results (populated when --agent-eval is used)
    agent_baseline_score: float | None = None
    agent_validation_score: float | None = None
    agent_side_info: dict[str, dict] | None = None


def _compute_diff_summary(original: str, optimized: str) -> str:
    """Generate a human-readable summary of changes."""
    original_lines = original.splitlines(keepends=True)
    optimized_lines = optimized.splitlines(keepends=True)
    diff = list(
        difflib.unified_diff(
            original_lines,
            optimized_lines,
            fromfile="original",
            tofile="optimized",
            n=1,
        )
    )

    if not diff:
        return "No changes"

    added = sum(
        1 for line in diff if line.startswith("+") and not line.startswith("+++")
    )
    removed = sum(
        1 for line in diff if line.startswith("-") and not line.startswith("---")
    )

    parts = []
    if added:
        parts.append(f"+{added} lines added")
    if removed:
        parts.append(f"-{removed} lines removed")

    changed_sections = set()
    for line in diff:
        content = (
            line[1:].strip()
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
            else ""
        )
        if content.startswith("#"):
            changed_sections.add(content)

    summary = ", ".join(parts)
    if changed_sections:
        sections = "\n".join(f"  ~ {s}" for s in sorted(changed_sections)[:10])
        summary += f"\n\nChanged sections:\n{sections}"

    return summary


def _evaluate_on_tasks(evaluator, candidate, tasks, label: str = "Evaluating"):
    """Run evaluator on tasks and return mean score, per-task scores, and per-task side_info.

    Returns:
        (mean_score, per_task_scores, side_info_by_id, side_info_by_input)
    """

    gepa_instances = to_gepa_instances(tasks)
    total = len(gepa_instances)
    per_task = {}
    side_info_by_id = {}
    side_info_by_input = {}
    for i, inst in enumerate(gepa_instances):
        task_id = tasks[i].get("id", f"task_{i}")
        print(f"\r  {label}: {i + 1}/{total} ({task_id})...", end="", flush=True)
        score, side_info = evaluator(candidate, inst)
        per_task[task_id] = score
        side_info_by_id[task_id] = side_info
        side_info_by_input[inst.get("input", f"task_{i}")] = side_info
    mean = sum(per_task.values()) / len(per_task) if per_task else 0.0
    print(f"\r  {label}: {total}/{total} done. Mean: {mean:.3f}        ")
    return mean, per_task, side_info_by_id, side_info_by_input


def _log_detailed_judge_metrics(
    mlflow_mod,
    si_by_id: dict[str, dict],
    val_scores: dict[str, float] | None,
    agent_baseline_score: float | None,
    agent_validation_score: float | None,
    agent_validation_si: dict[str, dict] | None,
):
    """Log detailed per-task judge metrics, aggregates, and rationales to the active MLflow run."""
    # Score keys we expect from skillbench judges
    JUDGE_SCORE_KEYS = [
        "quality_with",
        "quality_without",
        "skill_effectiveness",
        "structure",
        "token_efficiency",
    ]
    AGENT_SCORE_KEYS = [
        "tool_correctness",
        "tool_efficiency",
        "behavioral",
        "execution_success",
    ]

    # --- A. Per-task skillbench scores ---
    metrics = {}
    rationales: dict[str, dict] = {}
    aggregates: dict[str, list[float]] = {k: [] for k in JUDGE_SCORE_KEYS}

    for task_id, si in si_by_id.items():
        scores = si.get("scores", {})
        rationale = si.get("rationale", si.get("judge_rationale", ""))
        task_rationale_entry: dict[str, Any] = {"scores": scores}
        if rationale:
            task_rationale_entry["rationale"] = rationale

        for key in JUDGE_SCORE_KEYS:
            if key in scores:
                metrics[f"task/{task_id}/{key}"] = float(scores[key])
                aggregates[key].append(float(scores[key]))

        final = scores.get("final", si.get("score"))
        if final is not None:
            metrics[f"task/{task_id}/final"] = float(final)

        rationales[task_id] = task_rationale_entry

    # --- B. Aggregate judge scores ---
    for key, vals in aggregates.items():
        if vals:
            metrics[f"judge_mean/{key}"] = sum(vals) / len(vals)

    # --- C. Validation scores ---
    if val_scores:
        for task_id, score in val_scores.items():
            metrics[f"val/{task_id}/score"] = float(score)
        metrics["val_mean_score"] = sum(val_scores.values()) / len(val_scores)

    # --- D. Agent scores ---
    agent_rationales: dict[str, dict] = {}
    if agent_baseline_score is not None:
        metrics["agent/baseline_score"] = agent_baseline_score
    if agent_validation_score is not None:
        metrics["agent/validation_score"] = agent_validation_score
    if agent_baseline_score is not None and agent_validation_score is not None:
        metrics["agent/improvement"] = agent_validation_score - agent_baseline_score

    if agent_validation_si:
        agent_aggregates: dict[str, list[float]] = {k: [] for k in AGENT_SCORE_KEYS}
        for task_id, si in agent_validation_si.items():
            scores = si.get("scores", {})
            rationale = si.get("rationale", si.get("judge_rationale", ""))
            agent_task_entry: dict[str, Any] = {"scores": scores}
            if rationale:
                agent_task_entry["rationale"] = rationale

            for key in AGENT_SCORE_KEYS:
                if key in scores:
                    metrics[f"agent_task/{task_id}/{key}"] = float(scores[key])
                    agent_aggregates[key].append(float(scores[key]))

            final = scores.get("final", si.get("score"))
            if final is not None:
                metrics[f"agent_task/{task_id}/final"] = float(final)

            agent_rationales[task_id] = agent_task_entry

        for key, vals in agent_aggregates.items():
            if vals:
                metrics[f"agent_mean/{key}"] = sum(vals) / len(vals)

    # Log all metrics
    if metrics:
        mlflow_mod.log_metrics(metrics)

    # --- E. Judge rationales as JSON artifacts ---
    if rationales:
        mlflow_mod.log_dict(rationales, "judge_rationales.json")
    if agent_rationales:
        mlflow_mod.log_dict(agent_rationales, "agent_judge_rationales.json")


def optimize_skill(
    skill_name: str,
    preset: str = "standard",
    gen_model: str | None = None,
    reflection_lm: str | None = None,
    include_tools: bool = False,
    tool_modules: list[str] | None = None,
    tools_only: bool = False,
    dry_run: bool = False,
    max_passes: int = 5,
    max_metric_calls: int | None = None,
    token_budget: int | None = None,
    judge_model: str | None = None,
    align: bool = False,
    run_dir: str | None = None,
    # Agent evaluation
    agent_eval: bool = False,
    agent_eval_full: bool = False,
    agent_model: str | None = None,
    agent_timeout: int = 300,
    mlflow_experiment: str | None = None,
    mcp_config: dict | None = None,
    agent_allowed_tools: list[str] | None = None,
    # MLflow assessment injection
    mlflow_assessment_experiment: str | None = None,
    # Cross-skill dataset
    max_per_skill: int | None = None,
    # Focus areas for steering optimization
    focus_areas: list[str] | None = None,
    # Deprecated params kept for backward compat
    mode: str = "static",
    task_lm: str | None = None,
    evaluator_type: str = "skillbench",
    use_judges: bool = True,
) -> OptimizationResult:
    """Run end-to-end GEPA optimization on a skill and/or tools.

    Uses optimize_anything API with judge-based evaluation.
    Runs up to ``max_passes`` optimization passes per component, feeding
    each pass's best candidate as the seed for the next.

    Args:
        skill_name: Name of the skill to optimize
        preset: "quick" (15), "standard" (50), "thorough" (150)
        gen_model: LLM for generative evaluation
        reflection_lm: Override reflection LM
        include_tools: Include MCP tool descriptions as additional components
        tool_modules: Specific tool modules (None = all)
        tools_only: Optimize ONLY tool descriptions
        dry_run: Show config without running
        max_passes: Maximum optimization passes (default 5)
        max_metric_calls: Override max metric calls per pass
        token_budget: Hard token ceiling
        judge_model: Override judge model (future use)
        align: Use MemAlign alignment (future use)
        run_dir: Directory for GEPA checkpoints. Resumes from last state if dir exists.
        agent_eval: Use hybrid mode — proxy for GEPA iterations, real agent for
            baseline scoring and final validation.
        agent_eval_full: Use agent evaluator for ALL GEPA iterations (slow but accurate).
        agent_model: Model to use for agent execution (e.g., databricks-claude-sonnet-4-6).
        agent_timeout: Timeout per agent run in seconds (default 300).
        mcp_config: MCP server configuration for agent execution.
        agent_allowed_tools: Allowed tools for agent execution.
    """
    # 1. Load SKILL.md
    skill_path = find_skill_md(skill_name)
    if not tools_only and skill_path is None:
        raise FileNotFoundError(f"Could not find SKILL.md for '{skill_name}'")

    original_content = skill_path.read_text() if skill_path else ""

    # 1b. Load MCP tool descriptions
    tool_map = None
    tool_components: dict[str, str] = {}
    tool_context_str: str | None = None

    # Always load tool descriptions for context
    try:
        tool_map = extract_tool_descriptions(modules=tool_modules)
        tool_components = tools_to_gepa_components(tool_map, per_module=True)
        stats = get_tool_stats(modules=tool_modules)
        print(
            f"Tool modules: {stats['modules']}, tools: {stats['total_tools']}, "
            f"description chars: {stats['total_description_chars']:,}"
        )
    except FileNotFoundError:
        pass  # No MCP tools directory — skip

    # Build read-only tool context string (for skill optimization)
    if tool_components:
        tool_context_str = "\n\n".join(
            tool_components[k] for k in sorted(tool_components)
        )

    # 2. Build seed_candidate (multi-component dict)
    seed_candidate: dict[str, str] = {}
    original_token_counts: dict[str, int] = {}

    if tools_only:
        # Tools-only mode: tool descriptions ARE the GEPA components
        for comp_name, comp_text in tool_components.items():
            seed_candidate[comp_name] = comp_text
            original_token_counts[comp_name] = count_tokens(comp_text)
        tool_context_str = None  # tools are in candidate, not read-only context
    elif include_tools:
        # Explicit --include-tools: both skill and tools are GEPA components
        seed_candidate[SKILL_KEY] = original_content
        original_token_counts[SKILL_KEY] = count_tokens(original_content)
        for comp_name, comp_text in tool_components.items():
            seed_candidate[comp_name] = comp_text
            original_token_counts[comp_name] = count_tokens(comp_text)
        tool_context_str = None  # tools are in candidate, not read-only context
    else:
        # Default: skill is the only GEPA component; tools are read-only context
        seed_candidate[SKILL_KEY] = original_content
        original_token_counts[SKILL_KEY] = count_tokens(original_content)

    total_original_tokens = sum(original_token_counts.values())

    # Resolve token budget
    token_budget = token_budget or DEFAULT_TOKEN_BUDGET

    # 3. Load datasets
    if tools_only:
        # Cross-skill dataset for tool optimization
        train = create_cross_skill_dataset(
            max_per_skill=max_per_skill or 5, tool_modules=tool_modules
        )
        val = None
        if train:
            source_skills = {
                t.get("metadata", {}).get("source_skill", "?") for t in train
            }
            print(
                f"Cross-skill dataset: {len(train)} tasks from {len(source_skills)} skill(s)"
            )
        else:
            # Fall back to single-skill dataset
            try:
                train, val = create_gepa_datasets(skill_name)
            except FileNotFoundError:
                train, val = [], None
    else:
        try:
            train, val = create_gepa_datasets(skill_name)
        except FileNotFoundError:
            train, val = [], None

    if not train:
        train = generate_bootstrap_tasks(skill_name)
        val = None
        print(f"No test cases found. Using {len(train)} auto-generated tasks.")

    # 3b. Fetch MLflow assessments if requested
    assessment_summary = None
    assessment_by_task: dict[str, list] = {}
    if mlflow_assessment_experiment:
        from .assessment_fetcher import (
            fetch_assessments,
            summarize_assessment_patterns,
            match_assessments_to_tasks,
        )

        records = fetch_assessments(mlflow_assessment_experiment, skill_name=skill_name)
        if records:
            assessment_summary = summarize_assessment_patterns(records)
            assessment_by_task = match_assessments_to_tasks(records, train)
            print(
                f"MLflow assessments: {len(records)} traces, {len(assessment_by_task)} tasks matched"
            )
            if assessment_summary:
                print(f"  {assessment_summary.splitlines()[0]}")
        else:
            print("MLflow assessments: no traces with assessments found")

    # 4. Build evaluator
    effective_gen_model = gen_model or task_lm or DEFAULT_GEN_LM
    if effective_gen_model:
        print(f"Generation model: {effective_gen_model}")

    from .judges import DEFAULT_JUDGE_LM

    effective_judge_model = judge_model or DEFAULT_JUDGE_LM
    print(f"Judge model: {effective_judge_model}")
    print("Evaluator: skillbench (judge-driven)")

    if not effective_gen_model:
        raise ValueError(
            "SkillBench evaluator requires a gen_model. Pass --gen-model or set GEPA_GEN_LM env var."
        )
    evaluator = create_skillbench_evaluator(
        skill_name,
        gen_model=effective_gen_model,
        original_token_counts=original_token_counts,
        token_budget=token_budget,
        judge_model=judge_model,
        tool_context=tool_context_str,
        assessment_by_task=assessment_by_task if assessment_by_task else None,
    )

    # 4b. Build agent evaluator if requested
    agent_evaluator = None
    agent_baseline_score = None
    agent_baseline_per_task = None
    agent_baseline_si = None

    if agent_eval or agent_eval_full:
        from .agent_evaluator import create_agent_evaluator, build_agent_eval_background

        print("Agent evaluation: ENABLED")
        agent_evaluator = create_agent_evaluator(
            skill_name,
            original_token_counts=original_token_counts,
            token_budget=token_budget,
            judge_model=judge_model,
            mcp_config=mcp_config,
            allowed_tools=agent_allowed_tools,
            agent_model=agent_model,
            agent_timeout=agent_timeout,
            mlflow_experiment=mlflow_experiment,
        )

        if agent_eval_full:
            # Use agent evaluator for all GEPA iterations
            evaluator = agent_evaluator
            print("Mode: agent-eval-full (agent for ALL iterations)")
        else:
            print(
                "Mode: agent-eval hybrid (proxy for GEPA, agent for baseline + validation)"
            )

    # 5. Get config (scaled by component count)
    num_components = len(seed_candidate)
    config = get_preset(
        preset,
        reflection_lm=reflection_lm,
        num_components=num_components,
        max_metric_calls_override=max_metric_calls,
    )
    print(f"Reflection model: {config.reflection.reflection_lm}")

    # 5b. Validate reflection model context window
    validate_reflection_context(
        config.reflection.reflection_lm,
        total_original_tokens,
    )

    # 5c. Replace GEPA's reflection_lm string with a fallback-aware callable.
    # GEPA internally calls make_litellm_lm() which wraps litellm.completion
    # with no fallback. We pre-convert it so GEPA uses our version with
    # model fallback on rate limit errors.
    from .judges import completion_with_fallback

    _reflection_model_name = config.reflection.reflection_lm or ""
    if isinstance(config.reflection.reflection_lm, str):

        def _reflection_lm_with_fallback(prompt):
            if isinstance(prompt, str):
                messages = [{"role": "user", "content": prompt}]
            else:
                messages = prompt
            result = completion_with_fallback(
                model=_reflection_model_name,
                messages=messages,
            )
            return result.choices[0].message.content

        config.reflection.reflection_lm = _reflection_lm_with_fallback

    # Same for refiner_lm if present
    if config.refiner is not None and isinstance(config.refiner.refiner_lm, str):
        _refiner_model_name = config.refiner.refiner_lm

        def _refiner_lm_with_fallback(prompt):
            if isinstance(prompt, str):
                messages = [{"role": "user", "content": prompt}]
            else:
                messages = prompt
            result = completion_with_fallback(
                model=_refiner_model_name,
                messages=messages,
            )
            return result.choices[0].message.content

        config.refiner.refiner_lm = _refiner_lm_with_fallback

    # Dry run
    if dry_run:
        print(f"\n=== Dry Run: {skill_name} (skillbench) ===")
        if not tools_only:
            print(f"SKILL.md path: {skill_path}")
        print(f"Components: {list(seed_candidate.keys())}")
        print(f"Total original tokens: {total_original_tokens:,}")
        for comp, tokens in original_token_counts.items():
            print(f"  {comp}: {tokens:,} tokens")
        if tool_context_str:
            print(
                f"Tool context (read-only): {count_tokens(tool_context_str):,} tokens"
            )
        print(f"Train tasks: {len(train)}")
        print(f"Val tasks: {len(val) if val else 'None (single-task mode)'}")
        print(f"Generation model: {effective_gen_model}")
        print(
            f"Preset: {preset} (max_metric_calls={config.engine.max_metric_calls}, "
            f"scaled for {num_components} component(s))"
        )
        print(f"Max passes: {max_passes}")
        if run_dir:
            print(f"Run dir: {run_dir}")
        print(f"Reflection LM: {config.reflection.reflection_lm}")

        print(f"\nScoring baseline ({len(train)} tasks, ~5 LLM calls each)...")
        original_score, original_per_task, si_by_id, _ = _evaluate_on_tasks(
            evaluator, seed_candidate, train, label="Baseline"
        )
        print(f"Current score: {original_score:.3f}")
        for task_id, score in original_per_task.items():
            print(f"  {task_id}: {score:.3f}")

        background = build_skillbench_background(
            skill_name,
            total_original_tokens,
            component_names=list(seed_candidate.keys()),
            baseline_scores=original_per_task,
            baseline_side_info=si_by_id,
            token_budget=token_budget,
            assessment_summary=assessment_summary,
            focus_areas=focus_areas,
        )
        print(f"\nBackground preview:\n{background[:500]}...")

        # Agent baseline in dry run
        dry_run_agent_score = None
        dry_run_agent_si = None
        if agent_evaluator:
            print(f"\nAgent baseline ({len(train)} tasks)...")
            dry_run_agent_score, agent_per_task, dry_run_agent_si, _ = (
                _evaluate_on_tasks(
                    agent_evaluator, seed_candidate, train, label="Agent baseline"
                )
            )
            print(f"Agent baseline score: {dry_run_agent_score:.3f}")
            for task_id, score in agent_per_task.items():
                print(f"  {task_id}: {score:.3f}")

        return OptimizationResult(
            skill_name=skill_name,
            original_score=original_score,
            optimized_score=original_score,
            improvement=0.0,
            original_content=original_content,
            optimized_content=original_content,
            original_token_count=total_original_tokens,
            optimized_token_count=total_original_tokens,
            token_reduction_pct=0.0,
            diff_summary="Dry run - no optimization performed",
            val_scores={},
            mlflow_run_id=None,
            gepa_result=None,
            components=dict(seed_candidate),
            original_components=dict(seed_candidate),
            tool_map=tool_map,
            evaluator_type="skillbench",
            skillbench_side_info=si_by_id,
            agent_baseline_score=dry_run_agent_score,
            agent_validation_score=None,
            agent_side_info=dry_run_agent_si,
        )

    # Evaluate original and capture per-task detail for baseline context
    print(f"\nScoring baseline ({len(train)} tasks, ~5 LLM calls each)...")
    original_score, original_per_task, si_by_id, si_by_input = _evaluate_on_tasks(
        evaluator, seed_candidate, train, label="Baseline"
    )

    # 6. Build background and objective
    background = build_skillbench_background(
        skill_name,
        total_original_tokens,
        component_names=list(seed_candidate.keys()),
        baseline_scores=original_per_task,
        baseline_side_info=si_by_id,
        token_budget=token_budget,
        assessment_summary=assessment_summary,
        focus_areas=focus_areas,
    )
    objective = (
        f"Refine and improve the existing '{skill_name}' skill. "
        "Score is based on SKILL EFFECTIVENESS (35%) and TOKEN EFFICIENCY (25%). "
        "Judge rationale in side_info explains exactly what failed. "
        "Focus on what the agent would otherwise get wrong. "
        "Be concise — remove redundant examples and verbose explanations."
    )
    if focus_areas:
        focus_text = "\n".join(f"- {f}" for f in focus_areas)
        objective += (
            f"\n\nUSER PRIORITY — The user has asked to prioritize:\n{focus_text}\n"
            "Weight these priorities heavily when deciding what to add, change, or emphasize."
        )

    # 6b. Agent baseline scoring (hybrid mode: before GEPA loop)
    if agent_evaluator and not agent_eval_full:
        print(f"\n  Agent baseline scoring ({len(train)} tasks)...")
        agent_baseline_score, agent_baseline_per_task, agent_baseline_si, _ = (
            _evaluate_on_tasks(
                agent_evaluator, seed_candidate, train, label="Agent baseline"
            )
        )
        print(f"  Agent baseline score: {agent_baseline_score:.3f}")
        for task_id, score in agent_baseline_per_task.items():
            print(f"    {task_id}: {score:.3f}")

    # 7. Convert datasets to GEPA format
    trainset = to_gepa_instances(train)
    valset = to_gepa_instances(val) if val else None

    # 8. Multi-pass optimization loop
    current_seed = dict(seed_candidate)
    best = dict(seed_candidate)
    best_score = original_score
    best_si_by_id = si_by_id  # side_info from baseline eval
    last_result = None
    total_metric_calls = 0
    improvement_threshold = 0.0005

    print(
        f"\n  Starting multi-pass optimization (up to {max_passes} passes, "
        f"{num_components} component(s), {config.engine.max_metric_calls} metric calls/pass)"
    )

    # estimate_pass_duration expects the model name string, not the callable
    _est_reflection_lm = (
        _reflection_model_name
        if _reflection_model_name
        else str(reflection_lm or DEFAULT_GEN_LM)
    )
    est_secs = estimate_pass_duration(
        config.engine.max_metric_calls,
        _est_reflection_lm,
        total_original_tokens,
        num_dataset_examples=len(train),
    )
    if est_secs is not None:
        est_mins = est_secs / 60
        if est_mins > 5:
            print(
                f"  Estimated ~{est_mins:.0f} min/pass ({est_mins * max_passes:.0f} min total for {max_passes} passes)"
            )

    for pass_num in range(1, max_passes + 1):
        print(
            f"\n  --- Pass {pass_num}/{max_passes} (best score so far: {best_score:.4f}) ---"
        )

        pass_config = copy.deepcopy(config)

        # Set per-pass checkpoint directory
        if run_dir:
            pass_config.engine.run_dir = f"{run_dir}/pass_{pass_num}"

        result = optimize_anything(
            seed_candidate=current_seed,
            evaluator=evaluator,
            dataset=trainset,
            valset=valset,
            objective=objective,
            background=background,
            config=pass_config,
        )
        total_metric_calls += result.total_metric_calls or 0

        candidate = result.best_candidate
        pass_score, _, pass_si_by_id, _ = _evaluate_on_tasks(
            evaluator, candidate, train, label=f"Pass {pass_num}"
        )
        improvement = pass_score - best_score

        print(
            f"  Pass {pass_num} score: {pass_score:.4f} (delta: {'+' if improvement >= 0 else ''}{improvement:.4f})"
        )

        if pass_score > best_score + improvement_threshold:
            best = dict(candidate)
            best_score = pass_score
            best_si_by_id = pass_si_by_id
            last_result = result
            current_seed = dict(candidate)
        else:
            print(f"  No significant improvement in pass {pass_num} -- stopping early.")
            if last_result is None:
                last_result = result
            break
    else:
        print(f"  Completed all {max_passes} passes.")

    if last_result is None:
        last_result = result

    # 9. Extract results
    optimized_content = best.get(SKILL_KEY, original_content)
    optimized_token_count = sum(count_tokens(v) for v in best.values())

    optimized_score = best_score

    val_scores: dict[str, float] = {}
    if val:
        _, val_scores, _, _ = _evaluate_on_tasks(
            evaluator, best, val, label="Validation"
        )

    token_reduction_pct = (
        (total_original_tokens - optimized_token_count) / total_original_tokens * 100
        if total_original_tokens > 0
        else 0.0
    )

    diff_summary = _compute_diff_summary(original_content, optimized_content)

    # 10. Agent validation (hybrid mode: after GEPA loop)
    agent_validation_score = None
    agent_validation_si = None

    if agent_evaluator and not agent_eval_full:
        print(f"\n  Agent validation scoring ({len(train)} tasks on best candidate)...")
        agent_validation_score, agent_val_per_task, agent_validation_si, _ = (
            _evaluate_on_tasks(agent_evaluator, best, train, label="Agent validation")
        )
        print(f"  Agent validation score: {agent_validation_score:.3f}")
        for task_id, score in agent_val_per_task.items():
            print(f"    {task_id}: {score:.3f}")

        # Report comparison
        if agent_baseline_score is not None:
            agent_improvement = agent_validation_score - agent_baseline_score
            print("\n  Agent score comparison:")
            print(f"    Baseline: {agent_baseline_score:.3f}")
            print(f"    Validated: {agent_validation_score:.3f}")
            print(f"    Improvement: {agent_improvement:+.3f}")
            print("\n  Proxy score comparison:")
            print(f"    Baseline: {original_score:.3f}")
            print(f"    Optimized: {optimized_score:.3f}")
            print(f"    Improvement: {optimized_score - original_score:+.3f}")

    # 11. MLflow logging (best-effort, after all evaluations complete)
    mlflow_run_id = None
    try:
        import mlflow

        stc = SkillTestConfig()
        if mlflow_experiment:
            stc.mlflow.experiment_name = mlflow_experiment
        setup_mlflow(stc)
        with mlflow.start_run(run_name=f"{skill_name}_optimize_{preset}"):
            mlflow.set_tags(
                {
                    "optimizer": "gepa",
                    "skill_name": skill_name,
                    "preset": preset,
                    "evaluator_type": "agent" if agent_eval_full else "skillbench",
                }
            )
            mlflow.log_metrics(
                {
                    "original_score": original_score,
                    "optimized_score": optimized_score,
                    "improvement": optimized_score - original_score,
                    "original_tokens": float(total_original_tokens),
                    "optimized_tokens": float(optimized_token_count),
                    "token_reduction_pct": token_reduction_pct,
                    "total_metric_calls": float(total_metric_calls),
                }
            )
            _log_detailed_judge_metrics(
                mlflow_mod=mlflow,
                si_by_id=best_si_by_id,
                val_scores=val_scores if val_scores else None,
                agent_baseline_score=agent_baseline_score,
                agent_validation_score=agent_validation_score,
                agent_validation_si=agent_validation_si,
            )
            mlflow_run_id = mlflow.active_run().info.run_id
    except Exception:
        pass

    return OptimizationResult(
        skill_name=skill_name,
        original_score=original_score,
        optimized_score=optimized_score,
        improvement=optimized_score - original_score,
        original_content=original_content,
        optimized_content=optimized_content,
        original_token_count=total_original_tokens,
        optimized_token_count=optimized_token_count,
        token_reduction_pct=token_reduction_pct,
        diff_summary=diff_summary,
        val_scores=val_scores,
        mlflow_run_id=mlflow_run_id,
        gepa_result=last_result,
        components=dict(best),
        original_components=dict(seed_candidate),
        tool_map=tool_map,
        evaluator_type="agent" if agent_eval_full else "skillbench",
        skillbench_side_info=best_si_by_id,
        agent_baseline_score=agent_baseline_score,
        agent_validation_score=agent_validation_score,
        agent_side_info=agent_validation_si,
    )

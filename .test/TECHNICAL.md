# Technical Deep Dive: Skill Evaluation & Optimization

This document explains the internals of the evaluation and optimization framework — how scoring works, what GEPA does under the hood, the agent evaluation pipeline, and MLflow integration.

For setup instructions and CLI usage, see [README.md](README.md).

---

## Table of Contents

- [The Core Question](#the-core-question)
- [Evaluation Methodology](#evaluation-methodology)
- [Proxy Evaluator (SkillBench)](#proxy-evaluator-skillbench)
- [Agent Evaluator](#agent-evaluator)
- [GEPA Optimization Loop](#gepa-optimization-loop)
- [Multi-Pass Optimization](#multi-pass-optimization)
- [Judges & Assertions](#judges--assertions)
- [Adaptive Evaluation Criteria](#adaptive-evaluation-criteria)
- [MLflow Assessment Injection](#mlflow-assessment-injection)
- [MLflow Tracing Integration](#mlflow-tracing-integration)
- [Component Scaling](#component-scaling)
- [Scoring Weights](#scoring-weights)
- [Dataset Splitting](#dataset-splitting)
- [Model Fallback Chain](#model-fallback-chain)
- [Skills vs Tools Optimization](#skills-vs-tools-optimization)
- [Architecture Diagram](#architecture-diagram)

---

## The Core Question

> "Does this skill actually help an agent produce better responses?"

A SKILL.md is only valuable if an agent produces **better responses with the skill than without it**. This is a testable claim — we generate responses both ways and compare. That comparison is the foundation of all evaluation and optimization.

---

## Evaluation Methodology

Every evaluation follows a controlled experiment:

```
                      ┌─────────────────────────────┐
                      │        Same LLM + Prompt     │
                      │                               │
                      │   ┌─────────┐   ┌─────────┐  │
                      │   │  WITH   │   │ WITHOUT │  │
                      │   │  skill  │   │  skill  │  │
                      │   └────┬────┘   └────┬────┘  │
                      │        │              │       │
                      │   ┌────▼────┐   ┌────▼────┐  │
                      │   │ Judge   │   │ Judge   │  │
                      │   │ scores  │   │ scores  │  │
                      │   └────┬────┘   └────┬────┘  │
                      │        │              │       │
                      │   quality_with   quality_without
                      │        │              │       │
                      │    effectiveness = delta      │
                      └─────────────────────────────┘
```

1. **WITH-skill trial** — LLM generates a response with the SKILL.md in system context. The skill teaches Databricks-specific patterns the model wouldn't otherwise know.
2. **WITHOUT-skill trial** — Same LLM, same prompt, no skill in context. This is the control — what the model already knows on its own.
3. **Judge both** — An MLflow judge scores each response against expected facts, patterns, and guidelines from the test case (0.0–1.0 + written rationale).

The WITHOUT-skill response is **cached by prompt hash** — since the model and prompt don't change, the baseline is stable across all GEPA iterations. Every candidate SKILL.md is compared against the same fixed control.

### Two layers of comparison

| Layer | What's compared | What it measures |
|-------|----------------|-----------------|
| **Within each evaluation** | WITH vs WITHOUT skill | Whether a given SKILL.md adds value over a bare LLM |
| **Across optimization** | Original vs optimized SKILL.md | Whether GEPA's mutations improved the skill |

### Why this is rigorous

- **Same model, same prompts** — the only variable is the skill content
- **Cached baselines** — WITHOUT-skill responses don't change between iterations
- **Judge rationale** — every score comes with a written explanation (auditable)
- **Train/val split** — with 5+ test cases, stratified splitting prevents overfitting
- **Deterministic structure checks** — syntax validation uses regex/AST parsing, not LLM judgment

---

## Proxy Evaluator (SkillBench)

The default evaluator (`skillbench_evaluator.py`) uses `litellm.completion` to generate responses, an MLflow quality judge to score them, and deterministic assertions to check fact/pattern coverage. It's fast (~3 LLM calls per task per iteration) but doesn't test actual tool usage.

### Per-task evaluation flow

1. **Generate WITH-skill response** — `litellm.completion` with skill + tool descriptions as system context, temperature=0
2. **Generate WITHOUT-skill response** — Same prompt, no skill. Cached by prompt hash (computed once, reused across all GEPA iterations)
3. **Multi-judge scoring** — Three focused judges score responses with categorical `"excellent"` / `"acceptable"` / `"poor"` verdicts:
   - **Correctness judge** — scores WITH + WITHOUT (WITHOUT cached). Evaluates factual accuracy, API correctness, code syntax.
   - **Completeness judge** — scores WITH + WITHOUT (WITHOUT cached). Evaluates question coverage, expected facts/patterns presence.
   - **Guideline adherence judge** — scores WITH only (meaningless without skill). Evaluates Databricks patterns, conventions, `--focus` areas.
   - **Regression judge** — fires only when effectiveness delta < -0.05. Identifies what the skill broke.
4. **Deterministic assertions** — `assertions.py` runs binary pass/fail checks for each `expected_fact` (substring match) and `expected_pattern` (regex match) on both WITH and WITHOUT responses. Zero LLM cost.
5. **Compute composite score** — Weighted combination of per-dimension effectiveness deltas, quality composite, fact/pattern coverage, guideline adherence, structure validation, token efficiency, and regression penalty.

**Cost per task:** 5 LLM calls initially (correctness×2 + completeness×2 + guideline_adherence×1). After caching WITHOUT calls: 3 LLM calls per task on subsequent iterations.

**Categorical-to-float conversion:** `excellent=1.0`, `acceptable=0.6`, `poor=0.0`. Nonlinear: "acceptable" contributes positively (above 0.5) but the 0.4 gap to "excellent" incentivizes GEPA to push higher.

### Proxy scoring weights

| Weight | Dimension | Source |
|--------|-----------|--------|
| **30%** | Effectiveness Delta | Mean of (correctness_delta + completeness_delta) |
| **20%** | Quality Composite | Mean of (correctness + completeness + guideline_adherence) WITH scores |
| **15%** | Fact/Pattern Coverage | Deterministic assertions from `assertions.py` |
| **10%** | Guideline Adherence | Dedicated weight for Databricks patterns |
| **5%** | Structure | Python/SQL syntax validation |
| **10%** | Token Efficiency | Smaller = higher score (bonus up to 1.15x) |
| **-10%** | Regression Penalty | Explicit penalty when regression_judge detects harm |

### Rate limiting

A module-level rate limiter caps concurrent LLM calls at 4 with a 0.2s minimum interval to avoid overwhelming serving endpoints.

---

## Agent Evaluator

The agent evaluator (`agent_evaluator.py`) runs a **real Claude Code instance** via `claude_agent_sdk.ClaudeSDKClient` and scores actual agent behavior — tool selection, multi-turn reasoning, and execution success.

### How it works

1. **Run agent WITH skill** — Claude Code executes with candidate SKILL.md injected as system prompt
2. **Run agent WITHOUT skill** — Same task, no skill (cached by prompt hash)
3. **Quality judge** — Scores final response text
4. **Effectiveness delta** — score_with - score_without
5. **Tool correctness** — MLflow `ToolCallCorrectness` judge on actual tool calls
6. **Tool efficiency** — MLflow `ToolCallEfficiency` judge or deterministic `tool_count` scorer
7. **Behavioral compliance** — Deterministic trace scorers (`required_tools`, `banned_tools`, `tool_sequence`)
8. **Execution success** — Ratio of successful tool calls
9. **Token efficiency** — Candidate size vs budget

### Agent scoring weights

| Weight | Dimension | Source |
|--------|-----------|--------|
| **20%** | Content quality | `quality_judge` on final response text |
| **20%** | Skill effectiveness | WITH vs WITHOUT delta |
| **20%** | Tool call correctness | MLflow `ToolCallCorrectness` or `required_tools` scorer |
| **10%** | Tool call efficiency | MLflow `ToolCallEfficiency` or `tool_count` scorer |
| **15%** | Behavioral compliance | Deterministic trace scorers |
| **10%** | Execution success | Ratio of successful tool calls |
| **5%** | Token efficiency | Smaller candidates score higher |

### Two modes

| Mode | Flag | GEPA iterations | Baseline + validation | Speed |
|------|------|----------------|----------------------|-------|
| **Hybrid** | `--agent-eval` | Fast proxy | Real agent | ~12-20 min |
| **Full agent** | `--agent-eval-full` | Real agent | Real agent | ~30-60 min |

Hybrid mode is recommended — fast GEPA iteration with real agent validation at start and end.

### Hybrid mode flow

```
1. Agent baseline:   Run real agent on original SKILL.md (all training tasks)
2. GEPA loop:        Use fast proxy evaluator for mutations
3. Agent validation:  Run real agent on best candidate (all training tasks)
4. Compare:          Report proxy scores vs agent scores side-by-side
```

### Claude Code agent execution (`executor.py`)

The `run_agent_sync_wrapper()` function:

1. **Loads environment** from `.test/claude_agent_settings.json` with `${VAR:-default}` interpolation
2. **Creates `ClaudeAgentOptions`** with MCP servers, system prompt (candidate SKILL.md), allowed tools, and `bypassPermissions` mode
3. **Streams events** via `ClaudeSDKClient` — captures `AssistantMessage` (tool uses, text), `UserMessage` (tool results), `SystemMessage`, `ResultMessage`
4. **Builds `TraceMetrics`** from events — tool calls, token counts, file operations, turn counts
5. **MLflow Stop hook** fires on completion — calls `mlflow.claude_code.tracing.process_transcript()` to convert the transcript into an MLflow trace

### Estimated cost (hybrid mode)

| Phase | Calls | Cost | Time |
|-------|-------|------|------|
| Agent baseline (8 tasks x WITH + WITHOUT) | 16 agent runs | ~$4 | ~5-10 min |
| GEPA proxy iterations (quick preset) | ~350 LLM calls | ~$0 (Databricks) | ~3-4 min |
| Agent validation (8 tasks x WITH only) | 8 agent runs | ~$2 | ~3-5 min |
| **Total** | | **~$6** | **~12-20 min** |

---

## GEPA Optimization Loop

[GEPA](https://github.com/gepa-ai/gepa) (Generalized Evolutionary Prompt Architect) treats the SKILL.md as a text artifact to optimize. Its `optimize_anything` API takes a seed candidate, an evaluator function, and a dataset.

```
┌──────────────────────────────────────────────────┐
│                GEPA optimize_anything             │
│                                                   │
│  seed_candidate ──► evaluator(candidate, task)    │
│       │                    │                      │
│       │              (score, side_info)           │
│       │                    │                      │
│       │           reflection LM reads             │
│       │           side_info rationale             │
│       │                    │                      │
│       │              proposes mutation             │
│       │                    │                      │
│       └──── best_candidate (Pareto frontier) ◄───┘│
└──────────────────────────────────────────────────┘
```

Each iteration within a pass:

1. **Reflect** — The reflection LM reads `side_info` from the previous evaluation. This includes full judge rationale: which expected facts were missing, which patterns weren't found, which regressions occurred.
2. **Mutate** — Based on the rationale, proposes a targeted mutation to the SKILL.md. Mutations are surgical — informed by exactly what the judges flagged.
3. **Evaluate** — The evaluator scores the mutated candidate on a task (WITH/WITHOUT, judges, composite score).
4. **Select** — GEPA tracks a Pareto frontier of best candidates. Improvements are kept; others discarded.

The key insight: because `side_info` contains **full judge rationale** (not truncated), the reflection LM sees exactly what failed — leading to more targeted mutations.

### `side_info` structure

```python
side_info = {
    "Task": "Create a metric view for order analytics...",

    # Per-dimension judge feedback — GEPA sees each as a separate section
    "Judge_correctness_with":    {"verdict": "acceptable", "score": 0.6, "rationale": "..."},
    "Judge_correctness_without": {"verdict": "poor",       "score": 0.0, "rationale": "..."},
    "Judge_completeness_with":   {"verdict": "excellent",  "score": 1.0, "rationale": "..."},
    "Judge_completeness_without":{"verdict": "poor",       "score": 0.0, "rationale": "..."},
    "Judge_guideline_adherence": {"verdict": "acceptable", "score": 0.6, "rationale": "..."},

    # Per-dimension effectiveness deltas
    "Judge_effectiveness": {
        "verdict": "improved",
        "correctness_delta": +0.6,
        "completeness_delta": +1.0,
        "overall_delta": +0.8,
    },

    # Regression analysis (only when regression detected)
    "Regression_Analysis": {"rationale": "..."},  # from regression_judge

    # Assertion-based structured feedback — GEPA renders each as a markdown header
    "Missing_Facts": ["Missing: MEASURE() function for querying metric views"],
    "Missing_Patterns": ["Found 0 matches (need >=1)"],  # pattern_MEASURE\(
    "Passed_Facts": [
        "Found: Uses CREATE OR REPLACE VIEW with WITH METRICS LANGUAGE YAML",
        "Found: Defines measures with name and expr using aggregate functions",
    ],
    "Passed_Patterns": ["Found 1 matches (need >=1)"],  # WITH METRICS LANGUAGE YAML
    # skill_md_specific_info — only shown when reflecting on the skill component
    "skill_md_specific_info": {
        "Assertion_Diagnostics": "NEEDS_SKILL: fact — 'MEASURE() function for querying metric views'",
        "Regressions": "",
    },
    "scores": {
        "correctness_with": 0.6,
        "correctness_without": 0.0,
        "completeness_with": 1.0,
        "completeness_without": 0.0,
        "guideline_adherence": 0.6,
        "quality_composite": 0.73,    # mean of (0.6 + 1.0 + 0.6) / 3
        "correctness_delta": 0.6,
        "completeness_delta": 1.0,
        "skill_effectiveness": 0.8,   # mean of deltas
        "effectiveness_verdict": "improved",
        "regression_penalty": 0.0,
        "fact_coverage": 0.67,        # 2/3 facts passed
        "pattern_adherence": 0.5,     # 1/2 patterns passed
        "structure": 1.0,
        "token_efficiency": 0.92,
        "final": 0.71,
    },
    "token_counts": {"candidate_total": 1198, "original_total": 1234, "budget": 2000},
    # If MLflow assessments were injected:
    "real_world_assessments": [
        {"name": "ToolCallCorrectness", "value": "no", "rationale": "Agent used Bash instead of execute_sql"}
    ]
}
```

GEPA renders each top-level key as a markdown header. The **key names are the headers** — so `Missing_Facts` becomes `## Missing_Facts` followed by a bulleted list. This gives the reflection LM precise, actionable information instead of having to parse prose rationale.

---

## Multi-Pass Optimization

The runner (`runner.py`) wraps GEPA in a multi-pass loop (default: up to 5 passes):

```
Pass 1: seed = original SKILL.md
  └─► GEPA runs up to max_metric_calls iterations
  └─► Re-evaluate best candidate on ALL training tasks
  └─► If improvement > 0.0005: seed Pass 2 with best

Pass 2: seed = best from Pass 1
  └─► GEPA runs again, starting from the improved candidate
  └─► If improvement > 0.0005: seed Pass 3 with best

...continues until improvement ≤ 0.0005 or max_passes reached
```

Each pass creates a refinement chain — incremental improvements compound across passes. Early stopping prevents wasting compute when the skill has converged.

### Baseline scoring

Before optimization starts, the evaluator scores the original SKILL.md on all training tasks:

- **Per-task score** — composite score for each test case
- **Mean baseline score** — average across all tasks (e.g., `0.909`)
- **Diagnostic labels** — each task classified:
  - **OK** — skill helped (quality delta > +0.05)
  - **NEEDS_SKILL** — WITH-skill quality below 0.5 (skill isn't teaching enough)
  - **REGRESSION** — skill hurt the response (quality delta < -0.05)

This baseline context is included in GEPA's background prompt so the reflection LM knows what's working and what needs improvement.

### What "improvement" means

```
improvement = optimized_score - original_score
```

Both scores come from the same evaluator, same judges, same prompts, same cached WITHOUT-skill baselines. The only variable is the SKILL.md content. An improvement of +0.03 means the optimized skill produced measurably better quality deltas across test cases.

---

## Judges & Assertions

The framework uses two complementary scoring mechanisms:

### 1. Multi-judge architecture (LLM-based)

Built with [MLflow's `make_judge`](https://mlflow.org/docs/latest/genai/eval-monitor/scorers/llm-judge/custom-judges/) (`judges.py`). Three focused custom judges evaluate independent dimensions:

| Judge | Focus | Feedback type | Runs on | GEPA signal |
|-------|-------|--------------|---------|-------------|
| **Correctness** | Facts, API references, code syntax | `Literal["excellent", "acceptable", "poor"]` | WITH + WITHOUT | `Judge_correctness_with` / `Judge_correctness_without` |
| **Completeness** | All parts addressed, expected info | `Literal["excellent", "acceptable", "poor"]` | WITH + WITHOUT | `Judge_completeness_with` / `Judge_completeness_without` |
| **Guideline adherence** | Databricks patterns, conventions | `Literal["excellent", "acceptable", "poor"]` | WITH only | `Judge_guideline_adherence` |
| **Regression** | What the skill broke (conditional) | `bool` | Conditional | `Regression_Analysis` |

Each judge returns a categorical verdict with detailed rationale. Verdicts are converted to floats: `excellent=1.0`, `acceptable=0.6`, `poor=0.0`.

**Why categorical over numeric?** Categorical `Literal` types produce more reliable, consistent judgments than continuous 0.0–1.0 scores. They're also compatible with [MemAlign](https://mlflow.org/docs/latest/genai/eval-monitor/scorers/llm-judge/custom-judges/#alignment) for judge calibration with human feedback.

**Why three judges (not one, not five)?** The previous single quality judge collapsed 5 criteria into one score. When a mutation improved correctness but hurt completeness, the score barely moved — GEPA couldn't distinguish which dimension improved. Three judges cover core evaluation dimensions:
1. **Correctness** → GEPA can target: fix API errors, update deprecated patterns
2. **Completeness** → GEPA can target: add missing content, cover more question parts
3. **Guideline adherence** → GEPA can target: align with Databricks conventions, `--focus` areas

Five judges would cost 7+ calls/task — too expensive for iterative GEPA.

**Guideline injection:**
- **Correctness judge** receives only correctness-related guidelines (filtered by keywords: api, syntax, correct, deprecated, modern)
- **Guideline adherence judge** receives ALL guidelines: `default_guidelines` from manifest + per-test `guidelines` + `[FOCUS]` guidelines from `--focus`
- This makes `--focus` areas directly evaluable — the judge checks whether the response follows them

### 2. Deterministic assertions (zero LLM cost)

`assertions.py` runs binary pass/fail checks against the response:

| Assertion type | How it works | Example |
|---------------|-------------|---------|
| **Fact** | Case-insensitive substring match | `"MEASURE() function"` → found/missing |
| **Pattern** | Regex with `min_count`/`max_count` | `MEASURE\(` with `min_count: 1` |

`run_all_assertions()` checks both WITH and WITHOUT responses. `summarize_failures()` classifies each assertion:

- **POSITIVE** — fails without skill, passes with (skill is helping)
- **REGRESSION** — passes without skill, fails with (skill is confusing the agent)
- **NEEDS_SKILL** — fails both with and without (skill must add this content)
- **NEUTRAL** — same result either way (agent already knows this)

### Effectiveness scoring

Effectiveness is derived per-dimension: `correctness_delta = correctness_with - correctness_without` and `completeness_delta = completeness_with - completeness_without`, then averaged. This gives GEPA two separate signals about WHERE improvement happened, enabling targeted mutations rather than generic ones.

---

## Adaptive Evaluation Criteria

Judges can adaptively load domain-specific rubrics during scoring. Evaluation criteria are packaged as SKILL.md files in `.test/eval-criteria/` — the same format used by agent skills. This implements the `Skill`/`SkillSet` data model from the [MLflow #21255 design spec](https://github.com/mlflow/mlflow/issues/21255#issuecomment-3997922398).

### Discovery and parsing (`eval_criteria.py`)

`discover_eval_criteria()` scans `.test/eval-criteria/` for subdirectories containing a `SKILL.md` file. Each is parsed into an `EvalCriteriaSkill` dataclass:

```python
@dataclass
class EvalCriteriaSkill:
    name: str                    # From frontmatter (e.g., "sql-correctness")
    description: str             # One-line description for judge prompt
    path: Path                   # Directory path
    metadata: dict[str, Any]     # Full YAML frontmatter metadata
    body: str                    # Markdown body (the actual rubric)
    references: dict[str, str]   # {relative_path: content} from references/
    applies_to: list[str]        # tool_modules filter (from metadata.applies_to)
```

`EvalCriteriaSet` holds all parsed criteria and provides:
- **`filter_by_modules(tool_modules)`** — returns subset matching the skill's `tool_modules`. Criteria with empty `applies_to` are always included (general-purpose).
- **`to_prompt(model)`** — generates a lightweight listing for system-prompt injection. Uses XML format for Claude models, Markdown for others. Only includes name + description (~50-100 tokens per criteria), not the full body.
- **`get_skill(name)`** — lookup by name for tool invocation.

### Tool registration (`judge_tools.py`)

Two tools are registered in MLflow's global `JudgeToolRegistry` via `register_eval_tools()`:

| Tool | Arguments | Returns |
|------|-----------|---------|
| `read_eval_criteria` | `skill_name` | Full rubric body (markdown) |
| `read_eval_reference` | `skill_name`, `file_path` | Reference document content |

These implement `ReadSkillTool` and `ReadSkillReferenceTool` from the MLflow #21255 spec. Both accept a `trace: Trace` parameter (required by the `JudgeTool` interface) but route lookups through the internal `EvalCriteriaSet`. Registration is idempotent — safe to call multiple times per process.

`ReadEvalReferenceTool` includes path traversal protection: normalized paths starting with `..` or absolute paths are rejected.

### System prompt injection

When judges are created, the `EvalCriteriaSet` is passed to each judge factory function (`make_correctness_judge`, `make_completeness_judge`, `make_guideline_adherence_judge`). The criteria listing is injected into the judge's system prompt via `to_prompt()`:

**Claude models (XML):**
```xml
<available_skills>
  <skill>
    <name>sql-correctness</name>
    <description>SQL evaluation criteria for Databricks...</description>
  </skill>
  ...
</available_skills>
```

**Other models (Markdown):**
```markdown
## Available Evaluation Criteria

- **sql-correctness**: SQL evaluation criteria for Databricks...
```

The judge sees the listing and decides whether to call `read_eval_criteria` based on the trace content. This keeps the system prompt small while giving judges access to deep domain rubrics on demand.

### `applies_to` filtering

Criteria are filtered by `tool_modules` from the skill's `manifest.yaml`:

- **`applies_to: [sql]`** — only available when evaluating skills with `tool_modules` containing `sql`
- **`applies_to: []`** (or omitted) — always available (e.g., `general-quality`, `tool-selection`)

Filtering happens at evaluator initialization: `discover_eval_criteria()` loads all criteria, then `filter_by_modules()` narrows the set before tool registration and judge creation.

### Future: MLflow native `make_judge(skills=[...])`

This module is a bridge implementation. When MLflow ships the native `make_judge(skills=[...])` API from the #21255 spec, replace:
- `eval_criteria.py` → `from mlflow.genai.skills import SkillSet`
- `judge_tools.py` → MLflow's built-in skill tools (auto-registered via type annotation)

The SKILL.md files and `references/` directories remain unchanged — only the loading/registration code changes.

---

## MLflow Assessment Injection

The `--mlflow-assessments EXPERIMENT_ID` flag fetches real-world behavioral feedback from MLflow traces and injects it into GEPA's optimization context.

### How it works

1. **Fetch** (`assessment_fetcher.py`): Searches the MLflow experiment for traces with `ToolCallCorrectness` and `ToolCallEfficiency` assessments
2. **Summarize**: Computes pass/fail rates across all traces (e.g., "ToolCallCorrectness: 60% pass (3/5)")
3. **Match**: Maps assessments to training tasks by prompt similarity (using `difflib.SequenceMatcher` with threshold >= 0.6)
4. **Inject**: Matched assessments appear in `side_info` for each task, so GEPA's reflection LM can see real-world failures

### Data flow

```
MLflow Experiment (with assessed traces)
    │
    ▼
assessment_fetcher.fetch_assessments(experiment_id)
    │
    ├─► summarize_assessment_patterns() → background context for GEPA
    │
    └─► match_assessments_to_tasks() → per-task assessment injection
         │
         ▼
    SkillBenchEvaluator receives assessment_by_task
         │
         ▼
    side_info["Real_world_assessments"] per task
         │
         ▼
    GEPA reflection LM reads failures → targeted mutations
```

This allows GEPA to learn from actual agent behavior — if the agent consistently picks the wrong tool or produces inefficient tool call patterns, those failures feed directly into the optimization loop.

---

## MLflow Tracing Integration

### Agent execution tracing

When running with `--agent-eval`, each agent execution produces an MLflow trace:

1. A **Stop hook** is attached to the Claude Agent SDK client
2. When the agent completes, the hook calls `mlflow.claude_code.tracing.process_transcript()` to convert the transcript into an MLflow trace
3. The trace is tagged with `skill_name`, `databricks.requested_model`, and `mlflow.source=skill-test-agent-eval`
4. The trace is returned to the `AgentEvaluator` for scoring with `ToolCallCorrectness` and `ToolCallEfficiency` judges

### Optimization run logging

Each optimization run is logged to MLflow:

```python
with mlflow.start_run(run_name=f"{skill_name}_optimize_{preset}"):
    mlflow.set_tags({
        "optimizer": "gepa",
        "skill_name": skill_name,
        "preset": preset,
        "evaluator_type": "skillbench",
    })
    mlflow.log_metrics({
        "original_score": 0.909,
        "optimized_score": 0.935,
        "improvement": 0.026,
        "original_tokens": 1234,
        "optimized_tokens": 1198,
        "token_reduction_pct": 2.9,
        "total_metric_calls": 30,
    })
```

The experiment name defaults to `/Shared/skill-tests` and is overridable with `--mlflow-experiment`.

---

## Component Scaling

When optimizing multiple components (e.g., SKILL.md + tool modules with `--include-tools`), metric calls scale:

- **Base formula**: `base_calls × num_components`
- **Per-preset caps**: quick → 45, standard → 150, thorough → 300
- **Global cap**: 300 (applied for slower reflection models like Sonnet/Haiku)
- **Round-robin**: GEPA's component selector alternates which component to mutate each iteration

Example: `--include-tools --tool-modules sql serving` (3 components: `skill_md` + `tools_sql` + `tools_serving`), `quick` preset → min(15 × 3, 45) = **45** metric calls per pass.

---

## Scoring Weights

### Proxy evaluator (SkillBench)

| Weight | Dimension | What it measures |
|--------|-----------|-----------------|
| **30%** | Effectiveness Delta | Mean of (correctness_delta + completeness_delta) — per-dimension skill contribution |
| **20%** | Quality Composite | Mean of (correctness + completeness + guideline_adherence) WITH scores |
| **15%** | Fact/Pattern Coverage | Deterministic assertions — `fact_coverage` and `pattern_adherence` |
| **10%** | Guideline Adherence | Dedicated weight for Databricks patterns and conventions |
| **5%** | Structure | Python/SQL syntax validity (deterministic) |
| **10%** | Token Efficiency | Token count vs original — smaller skills save context window |
| **-10%** | Regression Penalty | Explicit penalty when regression_judge detects skill-caused harm |

### Agent evaluator

| Weight | Dimension | What it measures |
|--------|-----------|-----------------|
| **20%** | Content quality | `quality_judge` on final response text |
| **20%** | Skill effectiveness | WITH vs WITHOUT delta |
| **20%** | Tool call correctness | Did the agent use the right tools? |
| **10%** | Tool call efficiency | Did the agent use a reasonable number of calls? |
| **15%** | Behavioral compliance | Required/banned tools, tool sequence |
| **10%** | Execution success | Ratio of successful tool calls |
| **5%** | Token efficiency | Smaller candidates score higher |

---

## Dataset Splitting

Handled by `splitter.py`:

- **< 5 test cases**: All used as training, no validation set (single-task mode)
- **>= 5 test cases**: Stratified train/val split by `metadata.category` (80/20 default)
- **`--tools-only` mode**: Cross-skill dataset — auto-discovers all skills with `ground_truth.yaml`, samples up to 5 tasks per skill
- **No `ground_truth.yaml`**: `generate_bootstrap_tasks()` auto-generates tasks from SKILL.md headers and code blocks

---

## Model Fallback Chain

When a model is rate-limited (`REQUEST_LIMIT_EXCEEDED`), the framework automatically cycles through fallback models:

1. **Primary model**: 3 retries with exponential backoff (2^N seconds, max 30s)
2. **Fallback chain**: GPT-5-2 → Gemini-3-1-Pro → Claude Opus 4.5 → GPT-5 → Claude Sonnet 4.6 → Claude Sonnet 4.5
3. Each fallback model gets 3 retries
4. If all exhausted: returns `JudgeFeedback(value=0.0, rationale="All models rate limited")`

This applies to both judge calls and response generation via `completion_with_fallback()`.

---

## Skills vs Tools Optimization

Skills and tools operate at different layers:

| | Skills | Tools |
|---|--------|-------|
| **What** | Domain knowledge (API syntax, patterns, best practices) | Tool selection (what each MCP tool does, when to use it) |
| **Where** | `databricks-skills/<skill>/SKILL.md` | `databricks-mcp-server/tools/*.py` (`@mcp.tool` docstrings) |
| **Scope** | One skill = one domain | Shared across ALL skills |
| **Risk** | Isolated — only affects one domain | Global — changes affect every agent session |

### Why optimize separately

Optimizing both simultaneously creates a **confounding variable problem**:
- Did the score improve because the skill got better, or because the tool description changed?
- Will the tool description change break other skills?
- GEPA's reflection LM can't distinguish which component caused the improvement.

### Recommended workflow

1. **Tools first** (`--tools-only`): Optimize tool descriptions against a cross-skill dataset so they generalize
2. **Skills second** (default): Optimize each skill with stable tool descriptions as read-only context
3. **Co-optimize** (`--include-tools`): Only for fixing skill/tool interaction edge cases after separate optimization

### Optimization modes

| Mode | Flag | Components mutated | Dataset | Use case |
|------|------|--------------------|---------|----------|
| Skill only | *(default)* | `skill_md` | Single skill's `ground_truth.yaml` | Domain knowledge |
| Tools only | `--tools-only` | `tools_sql`, `tools_serving`, etc. | Cross-skill (all skills sampled) | Universal tool selection |
| Both | `--include-tools` | `skill_md` + tool modules | Single skill's `ground_truth.yaml` | Skill/tool interaction fixes |

---

## Architecture Diagram

```
                                    optimize.py (CLI)
                                         │
                                         ▼
                                    runner.py
                               (multi-pass orchestrator)
                                    │         │
                          ┌─────────┘         └──────────┐
                          ▼                               ▼
                 skillbench_evaluator.py          agent_evaluator.py
                 (fast proxy: litellm +           (real Claude Code via
                  3 focused judges +               Claude Agent SDK +
                  assertions)                      assertions)
                     │         │                       │         │
                     ▼         ▼                       ▼         ▼
                judges.py  assertions.py          executor.py  assertions.py
                (correctness_judge,             (ClaudeSDKClient,
                 completeness_judge,            event streaming,
                 guideline_adherence_judge,     TraceMetrics builder)
                 regression_judge,
                 model fallback)
                     │
                     ├─── eval_criteria.py
                     │    (discover + parse SKILL.md
                     │     rubrics from eval-criteria/)
                     │
                     └─── judge_tools.py
                          (register read_eval_criteria +
                           read_eval_reference as
                           MLflow JudgeTools)
                          │
                          ▼
                  MLflow make_judge              MLflow Tracing
                  (scoring + rationale +         (process_transcript)
                   adaptive criteria tools)
                                                          │
                                                          ▼
                                                assessment_fetcher.py
                                             (fetch + inject real-world
                                              assessments into GEPA)
                                                          │
                          ┌───────────────────────────────┘
                          ▼
                    GEPA optimize_anything
                    (reflection → mutation → evaluation → Pareto selection)
                          │
                          ▼
                    splitter.py              config.py
                    (train/val split,        (presets, model
                     cross-skill dataset)     registration, scaling)
```

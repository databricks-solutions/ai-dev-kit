# Skill Evaluation & Optimization

Automatically evaluate and optimize SKILL.md files using [GEPA](https://github.com/gepa-ai/gepa) `optimize_anything` and MLflow judges.

## How It Works

SKILL.md files teach AI agents (like Claude Code) how to use Databricks features. Every token in a skill consumes the agent's context window, so skills must be **correct** (teach the right patterns) and **concise** (waste no tokens). This framework measures both and uses GEPA to improve them.

### The Core Loop

```
                  ┌──────────────────────────────────────────────────┐
                  │                GEPA optimize_anything             │
                  │                                                   │
                  │  seed_candidate ─► evaluator(candidate, task)     │
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

**GEPA** ([Generalized Evolutionary Prompt Architect](https://github.com/gepa-ai/gepa)) treats the SKILL.md as a text artifact to optimize. Its `optimize_anything` API takes:
- A **seed candidate** (the current SKILL.md text)
- An **evaluator** function: `(candidate, task_example) -> (score, side_info)`
- A **dataset** of test cases from `ground_truth.yaml`

GEPA's reflection LM reads the `side_info` diagnostics, proposes mutations, evaluates them, and selects the best via Pareto frontier. The critical insight: the richer the `side_info` diagnostics, the better GEPA's mutations.

### Evaluation Methodology: How We Measure Skill Quality

Before understanding the judges and scoring, it's important to understand **what we're measuring and why the measurement is trustworthy**.

#### The core question: "Does this skill actually help?"

A SKILL.md is only valuable if an agent produces **better responses with the skill than without it**. This is a testable claim — we can generate responses both ways and compare. That comparison is the foundation of all evaluation and optimization in this framework.

#### Two layers of comparison

There are two distinct comparisons happening — understanding both is key to reading the scores:

1. **Within each evaluation** (WITH vs WITHOUT skill): measures whether a given SKILL.md adds value over a bare LLM. This is what `quality_with` and `quality_without` refer to.
2. **Across the optimization loop** (original vs optimized): measures whether GEPA's mutations improved the SKILL.md. This is what `original_score` vs `optimized_score` refer to.

The first comparison runs inside the evaluator on every iteration. The second comparison runs in the runner to decide whether to keep GEPA's changes.

#### The WITH vs WITHOUT experimental design

Every evaluation follows a controlled experiment that measures whether a specific SKILL.md candidate helps the LLM produce better responses:

1. **WITH-skill trial** (`quality_with`) — An LLM generates a response with the SKILL.md injected as system context. The skill teaches the model Databricks-specific patterns, syntax, and constraints it wouldn't otherwise know.
2. **WITHOUT-skill trial** (`quality_without`) — The **same LLM** generates a response to the **same prompt** with **no SKILL.md in context**. This is the control — it shows what the model already knows on its own. **This is NOT "without optimization"** — it is the bare model with no skill document at all.
3. **Judge both** — An MLflow judge scores each response against the test case's expected facts, patterns, and guidelines, returning a 0.0-1.0 quality score plus a written rationale.

The WITHOUT-skill response is **computed once and cached by prompt hash** — since the model and prompt don't change, the baseline is stable across all GEPA iterations. This means every candidate SKILL.md is compared against the same fixed control (the bare model).

#### What "baseline score" means

Before optimization begins, the runner evaluates the **original SKILL.md** on all training tasks using the WITH/WITHOUT protocol above. This produces:

- A **per-task score** — the composite score (see [Scoring Weights](#scoring-weights)) for each test case
- A **mean baseline score** — the average across all tasks (e.g., `0.909`)
- **Diagnostic labels** — each task is classified:
  - **OK** — skill helped (quality delta > +0.05)
  - **NEEDS_SKILL** — WITH-skill quality is below 0.5 (skill isn't teaching enough)
  - **REGRESSION** — skill actively hurt the response (quality delta < −0.05)

This baseline tells you exactly where the skill stands *before* any optimization.

#### What "improvement" means (the second layer)

This is the **outer comparison** — original SKILL.md vs optimized SKILL.md. After GEPA produces an optimized candidate, it's re-evaluated on all training tasks using the same WITH/WITHOUT protocol. Improvement is the difference between the optimized mean score and the original mean score:

```
improvement = optimized_score - original_score
```

Both scores come from the same evaluator, which internally runs the WITH vs WITHOUT comparison. So "improvement" means the optimized SKILL.md produced a larger quality delta (WITH minus WITHOUT) than the original SKILL.md did — i.e., the optimized skill helps the LLM more than the original skill did.

This is **not** a subjective assessment. Both scores come from the same judges, same prompts, same cached WITHOUT-skill baselines. The only variable is the SKILL.md content.

The composite score itself is a weighted combination of four dimensions (detailed in [Scoring Weights](#scoring-weights)):

| Dimension | What it measures | Why it matters |
|-----------|-----------------|----------------|
| **Skill Effectiveness (40%)** | `quality_with - quality_without` | The skill's unique contribution — what the model gets right *because* of the skill |
| **Absolute Quality (30%)** | `quality_with` score | Overall response quality with the skill present |
| **Structure (5%)** | Python/SQL syntax validity | Code in the skill must be syntactically correct |
| **Token Efficiency (25%)** | Token count vs original | Smaller skills save context window — candidates that shrink get a bonus up to 1.15x |

A skill that scores 0.91 after optimization vs 0.88 at baseline has a measurable, reproducible improvement of +0.03 — driven by higher quality deltas, fewer regressions, or better token efficiency.

#### Why this is rigorous, not made up

- **Same model, same prompts** — the only variable is the skill content, isolating its effect
- **Cached baselines** — WITHOUT-skill responses don't change between iterations, so score deltas are real
- **Judge rationale** — every score comes with a written explanation of which facts were present/missing and which patterns matched/failed, making scores auditable
- **Train/val split** — with 5+ test cases, stratified splitting prevents overfitting to the training set
- **Deterministic structure checks** — syntax validation and pattern adherence use regex/AST parsing, not LLM judgment

### MLflow Judges as the Evaluator

The evaluator uses [MLflow's `make_judge`](https://mlflow.org/docs/latest/llms/llm-evaluate/index.html) to score responses. Two judges run by default during optimization:

| Judge | What it does | Returns |
|-------|-------------|---------|
| **quality_judge** | Scores a single response against expected facts, patterns, and guidelines | `float` (0.0-1.0) + rationale |
| **regression_judge** | Identifies specific ways the skill harms responses | `bool` + rationale of what to fix |

Effectiveness is derived from the quality delta (`quality_with - quality_without`) — no separate LLM call needed. The `effectiveness_judge` is available in `judges.py` for standalone use but is not called during optimization.

Each judge returns **full rationale** — not truncated — so GEPA's reflection LM sees exactly what failed and why:

```python
side_info = {
    "Judge_quality_with": {
        "score": 0.65,
        "rationale": "The response correctly uses CREATE OR REPLACE VIEW but misses "
                     "the MEASURE() wrapping requirement for measure references. "
                     "Pattern adherence: 2/3 found. Fact coverage: 3/5 present."
    },
    "Judge_quality_without": {
        "score": 0.2,
        "rationale": "Without the skill, the model invented a non-existent "
                     "CREATE METRIC VIEW syntax. Only 1/5 expected facts present."
    },
    "Judge_effectiveness": {
        "verdict": "improved",
        "delta": 0.45,
    }
}
```

### How Baseline Evaluation Works

This section walks through how a single test case is evaluated end-to-end, from dataset loading through to the baseline score that GEPA uses for optimization.

#### 1. Dataset Loading (`splitter.py`)

- Loads `ground_truth.yaml` test cases via `create_gepa_datasets()`
- If >= 5 test cases: stratified train/val split by `metadata.category` (80/20 default)
- If < 5: all used as train, no val set (single-task mode)
- If no `ground_truth.yaml` exists: `generate_bootstrap_tasks()` auto-generates tasks from SKILL.md headers

#### 2. Evaluator Construction (`skillbench_evaluator.py`)

`create_skillbench_evaluator()` builds a `SkillBenchEvaluator` with:

| Parameter | Purpose |
|-----------|---------|
| `gen_model` | LLM that generates responses (plays the role of the agent) |
| `original_token_counts` | Token count of the original SKILL.md (for efficiency scoring) |
| `skill_guidelines` | Deduplicated guidelines from all test cases (injected into quality judge) |
| `tool_context` | Read-only MCP tool descriptions (included in generation prompt but not mutated) |

The evaluator instantiates two MLflow judges: `quality_judge` and `regression_judge`.

#### 3. Per-Task Evaluation Flow (the `__call__` method)

Each test case goes through four phases:

1. **Phase 1: WITH-skill generation** -- Sends the SKILL.md + tool descriptions as system context, user prompt as user message, generates response at temperature=0
2. **Phase 2: WITHOUT-skill generation** -- Same prompt, NO skill in context. Result is **cached by prompt hash** -- computed once and reused across all GEPA iterations (the baseline never changes)
3. **Phase 3: Judge scoring** -- `quality_judge` scores both responses against `expected_facts`, `expected_patterns`, and `guidelines` from the test case. WITHOUT-skill judge results are also cached.
4. **Phase 4: Compute composite score** -- Weighted combination of effectiveness delta, absolute quality, structure validation, and token efficiency

#### 4. Baseline Scoring (`runner.py` step 5)

Before optimization starts, `_evaluate_on_tasks()` runs the evaluator on ALL training tasks with the original SKILL.md:

- Collects per-task scores and `side_info` diagnostics
- `build_skillbench_background()` summarizes: mean baseline score, which tasks are NEEDS_SKILL vs REGRESSION
- This baseline context tells GEPA's reflection LM what's already working and what needs improvement

#### 5. Why This Matters for GEPA

- The `side_info` dict returned per-task contains **full judge rationale** (not truncated)
- GEPA's reflection LM reads this rationale to understand exactly what failed
- Better diagnostics lead to more targeted mutations and faster convergence

### Scoring Weights

| Weight | Dimension | Source |
|--------|-----------|--------|
| **40%** | Skill Effectiveness | `quality_with - quality_without` (the delta) |
| **30%** | Absolute Quality | `quality_with` score from judge |
| **5%** | Structure | Python/SQL syntax validation |
| **25%** | Token Efficiency | Smaller = higher score (bonus up to 1.15x) |

### How Multi-Pass Optimization Works

Optimization runs as a multi-pass loop where each pass feeds its best result into the next. This section explains what happens inside a single pass and how the runner decides when to stop.

#### What happens inside a single GEPA pass

GEPA's `optimize_anything` receives the seed candidate (current SKILL.md text), the evaluator, the training dataset, and the preset config. Within a pass, GEPA runs up to `max_metric_calls` iterations — **15** for `quick`, **50** for `standard`, **150** for `thorough`.

Each iteration follows this cycle:

1. **Reflect** — The reflection LM reads `side_info` from the previous evaluation. This includes the full judge rationale: which expected facts were missing, which regex patterns weren't found, which guidelines were violated, and whether regressions occurred.
2. **Mutate** — Based on the rationale, the reflection LM proposes a targeted mutation to the SKILL.md (or tool docstring). Mutations are surgical — informed by exactly what the judges flagged.
3. **Evaluate** — The evaluator scores the mutated candidate on a task from the dataset. This involves generating responses WITH the candidate, running MLflow judges, and computing the composite score.
4. **Select** — GEPA tracks a Pareto frontier of best candidates. If the mutation improves the frontier, it's kept; otherwise, it's discarded.

The key insight: because `side_info` contains **full judge rationale** (not truncated summaries), the reflection LM sees exactly which facts were missed, which patterns were absent, and which regressions occurred — leading to more targeted mutations.

#### How multi-pass works and when it stops

The runner (`runner.py`) wraps GEPA in a multi-pass loop (default: up to 5 passes, controlled by `--max-passes`):

1. **Pass N starts** — The best candidate from pass N-1 (or the original SKILL.md for pass 1) becomes the seed.
2. **GEPA optimizes** — Runs up to `max_metric_calls` iterations within the pass.
3. **Re-evaluate** — After the pass completes, the best candidate is re-evaluated on **all** training tasks to get a stable score.
4. **Compare** — The pass score is compared to the previous best score.
5. **Decision:**
   - If improvement > **0.0005** (the `improvement_threshold`): the best candidate becomes the seed for pass N+1, and optimization continues.
   - If improvement ≤ **0.0005**: early stop — no further passes are run.

This creates a refinement chain: each pass starts from the previous pass's best, allowing incremental improvements that compound across passes. Early stopping prevents wasting compute when the skill has converged.

#### Component scaling

When optimizing multiple components (e.g., SKILL.md + tool modules with `--include-tools`), metric calls scale:

- **Base formula:** `base_calls × num_components`
- **Per-preset caps:** quick → 45, standard → 150, thorough → 300
- **Global cap:** 300 (applied for slower reflection models)
- **Round-robin:** GEPA's component selector alternates which component to mutate each iteration, so all components get roughly equal optimization effort.

For example, with `--include-tools --tool-modules sql serving` (3 components: `skill_md` + `tools_sql` + `tools_serving`), a `quick` preset uses min(15 × 3, 45) = **45** metric calls per pass.

---

## Quick Start

```bash
# Install
uv pip install -e ".test/[all]"

# Auth (pick one)
export DATABRICKS_API_KEY="dapi..."
export DATABRICKS_API_BASE="https://<workspace>.cloud.databricks.com/serving-endpoints"
# OR
export OPENAI_API_KEY="sk-..."
export GEPA_REFLECTION_LM="openai/gpt-4o"
export GEPA_GEN_LM="openai/gpt-4o"

# OR use Databricks AI Gateway (routes through a centralized gateway with rate limits and logging)
export DATABRICKS_API_KEY="dapi..."
export DATABRICKS_API_BASE="https://<account-id>.ai-gateway.cloud.databricks.com/mlflow/v1/serving-endpoints"
# IMPORTANT: When using AI Gateway, OPENAI_API_KEY must also be set to your Databricks API token.
# The MLflow judges and litellm call OpenAI-compatible endpoints, which read OPENAI_API_KEY for auth.
export OPENAI_API_KEY="$DATABRICKS_API_KEY"

# Optimize
uv run python .test/scripts/optimize.py databricks-metric-views --preset quick --apply
```

---

## What Can Be Optimized

GEPA treats any text artifact as a candidate for optimization. Skills and tools are optimized **separately** to avoid cross-skill interference.

### Skills (SKILL.md files) — default mode

SKILL.md files teach agents Databricks patterns — API syntax, code examples, best practices. Each skill is a standalone GEPA component (`skill_md`). Tool descriptions are loaded as **read-only context** — included in the generation prompt so the evaluator sees realistic agent behavior, but not mutated by GEPA.

This means `--preset quick` always uses **1 component / 15 metric calls per pass**, regardless of how many tool modules exist.

```bash
# Optimize a skill (tools loaded as read-only context)
uv run python .test/scripts/optimize.py databricks-metric-views --preset quick

# Optimize all skills that have test cases
uv run python .test/scripts/optimize.py --all --preset quick
```

### MCP Tool Descriptions — `--tools-only` mode

`@mcp.tool` docstrings in `databricks-mcp-server/` are what the agent sees when deciding which tool to call. Concise, accurate descriptions improve tool selection. Each tool module becomes a separate GEPA component (`tools_sql`, `tools_serving`, etc.).

Tool optimization uses a **cross-skill dataset** — tasks are sampled from all skills with `ground_truth.yaml` — so optimized docstrings work well across skills, not just one.

```bash
# Optimize tool descriptions with cross-skill evaluation
uv run python .test/scripts/optimize.py databricks-metric-views --tools-only

# Optimize specific tool modules only
uv run python .test/scripts/optimize.py databricks-metric-views --tools-only --tool-modules sql serving compute
```

When applied (`--apply`), optimized docstrings are written back to the MCP server source files via AST, preserving all surrounding code.

### Skills + Tools Together — `--include-tools` (advanced)

For advanced use: optimize both skill and tool descriptions in a single GEPA run. Both are treated as GEPA components (round-robin mutation). Per-preset metric call caps prevent budget blowup.

```bash
# Skill + specific tool modules
uv run python .test/scripts/optimize.py databricks-metric-views --include-tools --tool-modules sql

# Dry run to see all components and their token counts
uv run python .test/scripts/optimize.py databricks-metric-views --include-tools --dry-run
```

Available tool modules: `agent_bricks`, `aibi_dashboards`, `apps`, `compute`, `file`, `genie`, `jobs`, `lakebase`, `manifest`, `pipelines`, `serving`, `sql`, `unity_catalog`, `user`, `vector_search`, `volume_files`

---

## Example Workflow: `databricks-metric-views`

This walks through the full lifecycle of evaluating and optimizing the metric views skill.

### 1. Inspect the skill and test cases

The skill lives at `databricks-skills/databricks-metric-views/SKILL.md`. Test cases live at `.test/skills/databricks-metric-views/ground_truth.yaml`:

```yaml
test_cases:
  - id: metric-views_create_sql_001
    inputs:
      prompt: "Create a metric view for order analytics with revenue and order count measures"
    outputs:
      response: |
        ```sql
        CREATE OR REPLACE VIEW main.default.order_metrics
        WITH METRICS LANGUAGE YAML
        $$
        source: main.default.orders
        dimensions:
          - name: Order Month
            expr: DATE_TRUNC('MONTH', order_date)
        measures:
          - name: Total Revenue
            expr: SUM(amount)
        $$
        ```
    expectations:
      expected_facts:
        - "Uses CREATE OR REPLACE VIEW with WITH METRICS LANGUAGE YAML"
        - "Defines dimensions with name and expr fields"
        - "Defines measures with name and expr using aggregate functions"
      expected_patterns:
        - pattern: "WITH METRICS LANGUAGE YAML"
          description: "Metric view DDL syntax"
        - pattern: "MEASURE\\("
          description: "MEASURE() function for querying"
      guidelines:
        - "Must use WITH METRICS LANGUAGE YAML syntax"
        - "Must define dimensions and measures in YAML block"

  - id: metric-views_query_measure_002
    inputs:
      prompt: "Query a metric view to get total revenue and order count by month"
    expectations:
      expected_facts:
        - "Uses MEASURE() function to reference measures"
        - "SELECT * is NOT supported on metric views"
      expected_patterns:
        - pattern: "MEASURE\\("
          description: "MEASURE() wrapping for measures"
        - pattern: "GROUP BY ALL"
          description: "GROUP BY ALL for metric view queries"
```

Each test case defines:
- **`inputs.prompt`** — what the user asks
- **`expectations.expected_facts`** — facts the response must mention
- **`expectations.expected_patterns`** — regex patterns the response must contain
- **`expectations.guidelines`** — soft rules for the MLflow quality judge

### 2. Dry run to check baseline

```bash
uv run python .test/scripts/optimize.py databricks-metric-views --dry-run
```

```
=== Dry Run: databricks-metric-views (skillbench) ===
SKILL.md path: databricks-skills/databricks-metric-views/SKILL.md
Components: ['skill_md']
Total original tokens: 1,234
  skill_md: 1,234 tokens
Tool context (read-only): 16,757 tokens
Train tasks: 8
Evaluator: skillbench (judge-driven)
Preset: quick (max_metric_calls=15, scaled for 1 component(s))
Current score: 0.909
  metric-views_create_sql_001:     0.952
  metric-views_query_measure_002:  0.871
  metric-views_create_mcp_003:     0.934
  ...
```

The evaluator runs each test case **twice** — once WITH the skill in context and once WITHOUT — then judges the delta. Test case 002 scores lower because the MEASURE() wrapping example in the skill has a syntax gap.

### 3. Run optimization

```bash
uv run python .test/scripts/optimize.py databricks-metric-views --preset quick
```

GEPA runs 15 iterations per component across up to 5 passes. Each iteration:
1. Mutates the SKILL.md based on judge rationale
2. Generates responses WITH the mutated skill
3. Judges score the responses
4. GEPA keeps mutations that improve the Pareto frontier

```
  Starting multi-pass optimization (up to 5 passes, 1 component(s), 15 metric calls/pass)

  --- Pass 1/5 (best score so far: 0.9090) ---
  Pass 1 score: 0.9350 (delta: +0.0260)

  --- Pass 2/5 (best score so far: 0.9350) ---
  No significant improvement in pass 2 -- stopping early.
```

### 4. Review and apply

```
============================================================
  Optimization Results: databricks-metric-views
============================================================
  Score:              0.909 -> 0.935 (+0.026)
  Skill Effectiveness: 0.42
  Quality (with):      0.78
  Quality (without):   0.36 (baseline)
  Tokens:   1,234 -> 1,198 (-2.9%)

  Per-task:
    metric-views_create_sql_001     WITH 0.85  WITHOUT 0.35  delta +0.50  [OK]
    metric-views_query_measure_002  WITH 0.79  WITHOUT 0.22  delta +0.57  [OK]
    ...

  Saved: .test/skills/databricks-metric-views/optimized_SKILL.md
  Apply: uv run python .test/scripts/optimize.py databricks-metric-views --apply-last
============================================================
```

Review the diff, then apply:

```bash
# Review what changed
diff databricks-skills/databricks-metric-views/SKILL.md \
     .test/skills/databricks-metric-views/optimized_SKILL.md

# Apply
uv run python .test/scripts/optimize.py databricks-metric-views --apply-last
```

---

## CLI Reference

```bash
# Presets
uv run python .test/scripts/optimize.py <skill> --preset quick      # 15 iterations
uv run python .test/scripts/optimize.py <skill> --preset standard   # 50 iterations (default)
uv run python .test/scripts/optimize.py <skill> --preset thorough   # 150 iterations

# Options
--dry-run               # Show scores without optimizing
--apply                 # Run + apply immediately
--apply-last            # Apply saved result without re-running
--gen-model "..."       # Override generation model (default: databricks/databricks-claude-sonnet-4-6)
--reflection-lm "..."   # Override reflection model (default: databricks/databricks-claude-opus-4-6)
--max-passes N          # Max optimization passes (default: 5)
--token-budget N        # Hard token ceiling
--include-tools         # Include MCP tool descriptions as GEPA components (advanced)
--tool-modules sql ...  # Specific tool modules to include
--tools-only            # Optimize only tool descriptions (cross-skill evaluation)
--all                   # Optimize all skills with ground_truth.yaml
--run-dir DIR           # Directory for GEPA checkpoints (resumes if dir exists)

# Test case generation
--generate-from FILE    # Generate test cases from requirements file
--requirement "..."     # Inline requirement (repeatable)
```

### Flag Details

- **`--dry-run`**: Runs baseline evaluation on all training tasks — scores the current SKILL.md WITH and WITHOUT the skill in context, shows per-task scores and a cost estimate, then exits without running optimization. Useful for checking your baseline before committing to a full run.

- **`--apply`**: Runs optimization to completion, then immediately writes the optimized SKILL.md back to `databricks-skills/`. Combines `optimize` + `--apply-last` in one step. Use when you're confident in the preset and want a hands-off workflow.

- **`--apply-last`**: Loads the previously saved `optimized_SKILL.md` and `last_optimization.json` from `.test/skills/<skill>/` and writes the optimized content back to the repo. Does **not** re-run optimization. Use after reviewing a previous run's diff to confirm the changes look good.

- **`--include-tools`**: Makes MCP tool docstrings optimizable GEPA components alongside SKILL.md. Both are mutated by GEPA via round-robin selection. Tool descriptions are no longer read-only context — they become first-class candidates. Metric calls scale with component count (see [Component scaling](#component-scaling)).

- **`--tools-only`**: Drops SKILL.md entirely. Only tool module docstrings become GEPA components. Uses a **cross-skill dataset** (tasks sampled from ALL skills with `ground_truth.yaml`, max 5 per skill) so optimized descriptions generalize across skills rather than overfitting to one.

- **`--tool-modules`**: Filters which tool modules are extracted for optimization. Without this flag, all modules are included. Example: `--tool-modules sql serving` optimizes only the `tools_sql` and `tools_serving` components.

- **`--all`**: Discovers all skills with `ground_truth.yaml` in `.test/skills/`, runs optimization sequentially for each, and prints per-skill results plus a summary table at the end.

- **`--run-dir`**: Enables GEPA checkpointing. Each pass saves state to `{run_dir}/pass_{N}/`. If the same `--run-dir` is passed on a subsequent run, GEPA resumes from the last checkpoint. Use `touch {run_dir}/pass_N/gepa.stop` for graceful mid-pass stop.

- **`--max-passes`**: Maximum number of optimization passes (default 5). Each pass feeds the previous best as seed. Early stops if improvement falls below the threshold (0.0005). Lower values trade potential quality for faster completion.

- **`--token-budget`**: Hard ceiling on candidate token count. The efficiency scorer penalizes candidates that exceed this budget. Also available via `GEPA_TOKEN_BUDGET` env var.

### Model Configuration

| Env Var | Default | Purpose |
|---------|---------|---------|
| `GEPA_GEN_LM` | `databricks/databricks-claude-sonnet-4-6` | Generation model (produces responses from skill) |
| `GEPA_REFLECTION_LM` | `databricks/databricks-claude-opus-4-6` | Reflection model (proposes mutations) |
| `GEPA_TOKEN_BUDGET` | none | Hard token ceiling for candidates |

Model strings use [litellm provider prefixes](https://docs.litellm.ai/docs/providers): `databricks/`, `openai/`, `anthropic/`.

---

## Resuming Long Runs

GEPA saves optimization state to a run directory. If interrupted, resume from where you left off:

```bash
# Start with checkpointing
uv run python .test/scripts/optimize.py databricks-metric-views \
    --preset standard --run-dir ./opt_runs/metric-views

# Resume after interruption (same command)
uv run python .test/scripts/optimize.py databricks-metric-views \
    --preset standard --run-dir ./opt_runs/metric-views

# Graceful stop (GEPA finishes current iteration then exits)
touch ./opt_runs/metric-views/pass_1/gepa.stop
```

Each pass gets its own subdirectory (`pass_1/`, `pass_2/`, ...) so checkpoints are isolated per pass.

---

## Writing Test Cases

Test cases in `ground_truth.yaml` define what each skill should teach. Minimal example:

```yaml
metadata:
  skill_name: my-skill
  version: "1.0"

test_cases:
  - id: basic_001
    inputs:
      prompt: "Show me how to create a streaming table"
    outputs:
      response: |
        ```sql
        CREATE OR REFRESH STREAMING TABLE bronze_events
        AS SELECT * FROM STREAM read_files('s3://bucket/events/')
        ```
    expectations:
      expected_facts:
        - "Uses CREATE OR REFRESH STREAMING TABLE syntax"
      expected_patterns:
        - pattern: "CREATE OR REFRESH STREAMING TABLE"
          description: "SDP DDL syntax"
      guidelines:
        - "Must use SDP syntax, not legacy DLT syntax"
    metadata:
      category: happy_path
```

**Tips:**
- **5+ test cases** enables a train/val split for generalization
- **Cover categories**: happy_path, error_handling, edge cases — the splitter stratifies by `metadata.category`
- **`expected_patterns`** use regex — be specific (`"MEASURE\\("` not `".*MEASURE.*"`)
- **`guidelines`** are evaluated by the MLflow quality judge — use for soft expectations that can't be regex-matched
- **Generate from requirements**: `--requirement "Must explain MEASURE() wrapping"` auto-generates test cases

---

## Test Case & Configuration Files

Each skill under `.test/skills/<skill-name>/` has two configuration files that drive evaluation and optimization.

### `ground_truth.yaml` — What the skill must teach

The evaluation dataset. Each test case represents a user prompt and the expected behavior when the skill is in context.

**Full field schema:**

| Field | Required | Description |
|-------|----------|-------------|
| `metadata.skill_name` | yes | Identifier matching the skill directory name |
| `metadata.version` | yes | Schema version (e.g., `"1.0"`) |
| `metadata.created_at` | no | ISO timestamp of creation |
| `test_cases[].id` | yes | Unique identifier (convention: `<skill>_<action>_<NNN>`) |
| `test_cases[].inputs.prompt` | yes | The user question sent to the generation model |
| `test_cases[].outputs.response` | no | Expected reference answer. Used for judge comparison, **not** exact matching. Omit if you only want pattern/fact checks. |
| `test_cases[].expectations.expected_facts` | yes | List of factual claims the response must contain. The quality judge checks each one. |
| `test_cases[].expectations.expected_patterns` | no | Regex patterns with fields: `pattern`, `description`, and optionally `min_count` / `max_count`. Checked deterministically. |
| `test_cases[].expectations.guidelines` | no | Soft rules evaluated by the quality judge for things regex can't check (e.g., "Should explain why SELECT * doesn't work"). |
| `test_cases[].metadata.category` | recommended | Used for stratified train/val splitting. Common values: `happy_path`, `error_handling`, `advanced`, `conceptual`, `edge_case`. |

**Example with all fields:**

```yaml
metadata:
  skill_name: databricks-metric-views
  version: "1.0"
  created_at: "2025-01-15T10:00:00Z"

test_cases:
  - id: metric-views_create_sql_001
    inputs:
      prompt: "Create a metric view for order analytics"
    outputs:
      response: |
        ```sql
        CREATE OR REPLACE VIEW main.default.order_metrics
        WITH METRICS LANGUAGE YAML
        $$
        source: main.default.orders
        measures:
          - name: Total Revenue
            expr: SUM(amount)
        $$
        ```
    expectations:
      expected_facts:
        - "Uses CREATE OR REPLACE VIEW with WITH METRICS LANGUAGE YAML"
        - "Defines measures with name and expr using aggregate functions"
      expected_patterns:
        - pattern: "WITH METRICS LANGUAGE YAML"
          description: "Metric view DDL syntax"
          min_count: 1
        - pattern: "MEASURE\\("
          description: "MEASURE() function for querying"
          min_count: 0
          max_count: 5
      guidelines:
        - "Must use WITH METRICS LANGUAGE YAML syntax, not CREATE METRIC VIEW"
        - "Should include a complete YAML block between $$ delimiters"
    metadata:
      category: happy_path
```

### `manifest.yaml` — How to evaluate the skill

Configures which scorers run and what quality thresholds apply during evaluation.

**Full field schema:**

| Field | Description |
|-------|-------------|
| `skill_name` | Identifier matching the skill directory name |
| `scorers.enabled` | List of deterministic scorers to run: `python_syntax`, `sql_syntax`, `pattern_adherence`, `no_hallucinated_apis`, `expected_facts_present` |
| `scorers.llm_scorers` | List of LLM-based scorers: `Safety`, `guidelines_from_expectations`, `Guidelines` |
| `scorers.default_guidelines` | Fallback guidelines applied when a test case doesn't specify its own `guidelines` field |
| `quality_gates` | Minimum score thresholds per scorer (e.g., `syntax_valid: 1.0`, `pattern_adherence: 0.9`). Failing a gate flags the test case. |
| `scorers.trace_expectations.tool_limits` | Max number of tool calls allowed (for trace-based scoring) |
| `scorers.trace_expectations.token_budget` | Max tokens allowed in the response |
| `scorers.trace_expectations.required_tools` | Tools that must be called (e.g., `["execute_sql"]`) |
| `scorers.trace_expectations.banned_tools` | Tools that must not be called |

**Example:**

```yaml
skill_name: databricks-metric-views

scorers:
  enabled:
    - sql_syntax
    - pattern_adherence
    - expected_facts_present
  llm_scorers:
    - Safety
    - guidelines_from_expectations
  default_guidelines:
    - "Responses must use Databricks-specific syntax, not generic SQL"
    - "Code examples must be runnable without modification"

quality_gates:
  syntax_valid: 1.0
  pattern_adherence: 0.9
  safety: 1.0
```

---

## Architecture

```
.test/
├── scripts/
│   ├── optimize.py              # CLI entry point
│   ├── generate_examples.py     # Generate test cases from requirements
│   └── trace_to_examples.py     # Extract test cases from MLflow traces
├── src/skill_test/optimize/
│   ├── judges.py                # MLflow make_judge factories (quality, effectiveness, regression)
│   ├── skillbench_evaluator.py  # WITH vs WITHOUT evaluator using judges
│   ├── runner.py                # GEPA optimize_anything orchestrator
│   ├── utils.py                 # Token counting, path resolution
│   ├── asi.py                   # MLflow Feedback → side_info conversion
│   ├── alignment.py             # MemAlign judge alignment (future)
│   ├── config.py                # GEPA presets, model registration
│   ├── splitter.py              # Train/val dataset splitting
│   └── tools.py                 # MCP tool description extraction
├── src/skill_test/scorers/
│   ├── universal.py             # Deterministic: python_syntax, sql_syntax, etc.
│   ├── trace.py                 # Trace-based: tool_count, token_budget, etc.
│   └── routing.py               # Skill routing accuracy (deprecated)
└── skills/<skill-name>/
    ├── ground_truth.yaml        # Test cases
    ├── manifest.yaml            # Scorer configuration
    ├── optimized_SKILL.md       # Last optimization output
    └── last_optimization.json   # Metadata for --apply-last
```

---

## Troubleshooting

### MLflow evaluation not returning results

If `/skill-test <skill-name> mlflow` hangs or doesn't return results, run manually with debug logging:

```bash
MLFLOW_LOG_LEVEL=DEBUG uv run python .test/scripts/mlflow_eval.py <skill-name>
```

This will show detailed MLflow API calls and help identify connection or authentication issues.

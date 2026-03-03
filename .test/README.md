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

### Scoring Weights

| Weight | Dimension | Source |
|--------|-----------|--------|
| **40%** | Skill Effectiveness | `quality_with - quality_without` (the delta) |
| **30%** | Absolute Quality | `quality_with` score from judge |
| **5%** | Structure | Python/SQL syntax validation |
| **25%** | Token Efficiency | Smaller = higher score (bonus up to 1.15x) |

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

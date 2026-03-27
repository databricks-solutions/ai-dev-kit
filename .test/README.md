# Skill Evaluation & Optimization

Evaluate and optimize SKILL.md files using [GEPA](https://github.com/gepa-ai/gepa) and MLflow judges. Skills teach AI agents how to use Databricks features — this framework measures whether they actually help and uses evolutionary optimization to improve them.

For a deep technical explanation of the evaluation methodology, scoring, and architecture, see [TECHNICAL.md](TECHNICAL.md).

---

## Setup

### 1. Install dependencies

```bash
# Core + optimization
uv pip install -e ".test/[all]"

# Agent evaluation only (optional)
uv pip install -e ".test/[agent]"
```

### 2. Configure authentication

Pick one authentication method for the LLM endpoints used by the evaluator (generation, judging, reflection):

**Databricks AI Gateway (recommended)**

```bash
export DATABRICKS_API_KEY="dapi..."
export DATABRICKS_API_BASE="https://<account-id>.ai-gateway.cloud.databricks.com/mlflow/v1/serving-endpoints"
# MLflow judges and litellm read OPENAI_API_KEY for auth
export OPENAI_API_KEY="$DATABRICKS_API_KEY"
```

**Databricks direct**

```bash
export DATABRICKS_API_KEY="dapi..."
export DATABRICKS_API_BASE="https://<workspace>.cloud.databricks.com/serving-endpoints"
```

**OpenAI**

```bash
export OPENAI_API_KEY="sk-..."
export GEPA_REFLECTION_LM="openai/gpt-4o"
export GEPA_GEN_LM="openai/gpt-4o"
```

### 3. Configure the Claude Code agent (for `--agent-eval`)

Agent evaluation runs a real Claude Code instance via the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python). The agent's environment is configured in `.test/claude_agent_settings.json`:

```json
{
    "env": {
        "ANTHROPIC_MODEL": "databricks-claude-opus-4-6",
        "ANTHROPIC_BASE_URL": "https://<account-id>.ai-gateway.cloud.databricks.com/anthropic",
        "ANTHROPIC_AUTH_TOKEN": "${DATABRICKS_TOKEN:-dapi...}",
        "ANTHROPIC_DEFAULT_OPUS_MODEL": "databricks-claude-opus-4-6",
        "ANTHROPIC_DEFAULT_SONNET_MODEL": "databricks-claude-sonnet-4-6",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": "databricks-claude-haiku-4-5",
        "ANTHROPIC_CUSTOM_HEADERS": "x-databricks-use-coding-agent-mode: true",
        "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS": "1",
        "DATABRICKS_CONFIG_PROFILE": "${DATABRICKS_CONFIG_PROFILE:-e2-demo-field-eng}",
        "DATABRICKS_API_KEY": "${DATABRICKS_TOKEN:-dapi...}"
    }
}
```

| Field | Purpose                                                                 |
|-------|-------------------------------------------------------------------------|
| `ANTHROPIC_MODEL` | Default model the agent uses. Currently points to Databricks by default |
| `ANTHROPIC_BASE_URL` | Claude API endpoint (Databricks AI Gateway or direct)                   |
| `ANTHROPIC_AUTH_TOKEN` | Auth token — supports `${VAR:-default}` interpolation                   |
| `ANTHROPIC_CUSTOM_HEADERS` | Extra headers (e.g., coding agent mode for Databricks)                  |
| `DATABRICKS_CONFIG_PROFILE` | Databricks CLI profile for MCP tools                                    |
| `DATABRICKS_API_KEY` | Databricks token for MCP tool calls                                     |

The `${VAR:-default}` syntax lets you reference environment variables with fallbacks. The agent runs with `bypassPermissions` mode so it doesn't prompt for tool approval.

---

## Quick Start

```bash
# Check baseline scores (no optimization)
uv run python .test/scripts/optimize.py databricks-metric-views --dry-run

# Optimize with a quick pass (15 iterations)
uv run python .test/scripts/optimize.py databricks-metric-views --preset quick

# Optimize and immediately apply
uv run python .test/scripts/optimize.py databricks-metric-views --preset quick --apply

# Review a previous run's output, then apply
diff databricks-skills/databricks-metric-views/SKILL.md \
     .test/skills/databricks-metric-views/optimized_SKILL.md
uv run python .test/scripts/optimize.py databricks-metric-views --apply-last
```

### With agent evaluation

```bash
# Hybrid: agent for baseline + validation, proxy for GEPA iterations
uv run python .test/scripts/optimize.py databricks-metric-views --agent-eval --preset quick

# Dry run with agent baseline scoring
uv run python .test/scripts/optimize.py databricks-metric-views --agent-eval --dry-run

# Full agent mode (agent for ALL iterations — slow but most accurate)
uv run python .test/scripts/optimize.py databricks-metric-views --agent-eval-full --preset quick
```

### With MLflow assessment feedback

```bash
# Inject real-world behavioral feedback from an MLflow experiment
uv run python .test/scripts/optimize.py databricks-metric-views \
    --mlflow-assessments <EXPERIMENT_ID> --preset quick
```

### Tool optimization

`--tools-only` runs a single global optimization pass using a cross-skill dataset. No per-skill loop is needed — tool descriptions are shared across all skills.

```bash
# Optimize all tool descriptions (single global pass)
uv run python .test/scripts/optimize.py --tools-only --preset quick

# Optimize specific tool modules only
uv run python .test/scripts/optimize.py --tools-only --tool-modules sql serving --preset quick

# Limit tasks per skill (useful with --agent-eval to reduce cost)
uv run python .test/scripts/optimize.py --tools-only --tool-modules sql --max-per-skill 2 --preset quick

# Dry run — score baseline without optimizing
uv run python .test/scripts/optimize.py --tools-only --preset quick --dry-run

# --all is accepted but has no effect (tools-only always runs a single pass)
uv run python .test/scripts/optimize.py --tools-only --all --preset quick

# Co-optimize skill + tool descriptions (per-skill, not global)
uv run python .test/scripts/optimize.py databricks-metric-views --include-tools \
    --tool-modules sql --preset quick
```

#### Cross-skill dataset filtering with `--tool-modules`

When `--tool-modules` is specified, both tool stats and the cross-skill dataset are filtered:

- **Tool stats** report only the requested modules (e.g., `Tool modules: 1, tools: 5` for `--tool-modules sql`).
- **Cross-skill dataset** includes only skills whose `tool_modules` in `manifest.yaml` overlap with the requested modules. Skills that *don't declare* `tool_modules` are always included as a safe fallback (e.g., `databricks-config`, `databricks-docs`). This means the dataset won't shrink to *only* SQL skills — general-purpose skills without the field are kept so the evaluator still has broad coverage.

To reduce the dataset further, add `tool_modules` to any remaining skills that should be excluded for certain module filters. Without `--tool-modules`, all skills are included regardless (no regression).

### Optimize all skills

```bash
uv run python .test/scripts/optimize.py --all --preset quick
```

---

## CLI Reference

```
uv run python .test/scripts/optimize.py <skill_name> [options]
```

### Core Options

| Flag | Description |
|------|-------------|
| `--preset quick\|standard\|thorough` | Optimization budget: 15 / 50 / 150 iterations per pass (default: `standard`) |
| `--dry-run` | Score baseline without optimizing |
| `--apply` | Optimize and immediately apply the result |
| `--apply-last` | Apply a previously saved result without re-running |
| `--all` | Optimize all skills that have `ground_truth.yaml` |
| `--max-passes N` | Max optimization passes (default: 5). Early stops if improvement < 0.0005 |
| `--max-metric-calls N` | Override auto-scaled metric calls per pass |
| `--token-budget N` | Hard token ceiling — candidates over this are penalized |
| `--run-dir DIR` | Checkpoint directory. Resumes from last state if dir exists |

### Model Selection

| Flag | Env Var | Default | Purpose |
|------|---------|---------|---------|
| `--gen-model` | `GEPA_GEN_LM` | `databricks/databricks-claude-sonnet-4-6` | Generates responses in proxy evaluator |
| `--reflection-lm` | `GEPA_REFLECTION_LM` | `databricks/databricks-claude-opus-4-6` | GEPA's reflection/mutation model |
| `--judge-model` | `GEPA_JUDGE_LM` | `databricks/databricks-claude-sonnet-4-6` | MLflow quality judge |

Proxy evaluator models use [litellm provider prefixes](https://docs.litellm.ai/docs/providers): `databricks/`, `openai/`, `anthropic/`.

### Tool Optimization

| Flag | Description |
|------|-------------|
| `--include-tools` | Include MCP tool docstrings as GEPA components alongside SKILL.md |
| `--tools-only` | Optimize only tool descriptions in a single global pass (no per-skill loop) |
| `--tool-modules sql serving ...` | Limit which tool modules are optimized (default: all) |
| `--max-per-skill N` | Max tasks per skill in the cross-skill dataset for `--tools-only` (default: 5) |

Available modules: `agent_bricks`, `aibi_dashboards`, `apps`, `compute`, `file`, `genie`, `jobs`, `lakebase`, `manifest`, `pipelines`, `serving`, `sql`, `unity_catalog`, `user`, `vector_search`, `volume_files`

### Agent Evaluation

| Flag | Description |
|------|-------------|
| `--agent-eval` | Hybrid mode: real agent for baseline + validation, proxy for GEPA |
| `--agent-eval-full` | Real agent for ALL GEPA iterations (slow but most accurate) |
| `--agent-model MODEL` | Model for agent (default: `ANTHROPIC_MODEL` env var) |
| `--agent-timeout N` | Timeout per agent run in seconds (default: 300) |
| `--mlflow-experiment NAME` | MLflow experiment for agent traces (default: `/Shared/skill-tests`) |

### MLflow Feedback

| Flag | Description |
|------|-------------|
| `--mlflow-assessments EXPERIMENT_ID` | Fetch `ToolCallCorrectness` / `ToolCallEfficiency` assessments from an MLflow experiment and inject them into GEPA's reflection context |

### Test Case Generation

| Flag | Description |
|------|-------------|
| `--generate-from FILE` | Generate test cases from a requirements file before optimizing |
| `--requirement "..."` | Inline requirement (repeatable) |

---

## Writing Test Cases

Test cases live at `.test/skills/<skill-name>/ground_truth.yaml`. Each test case defines what the skill should teach.

```yaml
metadata:
  skill_name: databricks-metric-views
  version: "1.0"

test_cases:
  - id: metric-views_create_sql_001
    inputs:
      prompt: "Create a metric view for order analytics with revenue measures"
    outputs:
      response: |  # Optional reference answer (not exact-matched)
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
        - pattern: "MEASURE\\("
          description: "MEASURE() function for querying"
      guidelines:
        - "Must use WITH METRICS LANGUAGE YAML syntax"
      trace_expectations:  # Only used with --agent-eval
        required_tools:
          - mcp__databricks__execute_sql
        banned_tools:
          - Bash
        tool_limits:
          mcp__databricks__execute_sql: 3
    metadata:
      category: happy_path  # Used for stratified train/val splitting
```

| Field | Required | Description |
|-------|----------|-------------|
| `inputs.prompt` | Yes | The user question |
| `expectations.expected_facts` | Yes | Facts the response must contain (checked by quality judge + deterministic substring match) |
| `expectations.expected_patterns` | No | Regex patterns checked deterministically (feeds `fact_coverage`/`pattern_adherence` scores) |
| `expectations.guidelines` | No | Soft rules for the quality judge |
| `expectations.trace_expectations` | No | Agent behavioral validation (only with `--agent-eval`) |
| `outputs.response` | No | Reference answer for judge comparison |
| `metadata.category` | Recommended | Stratified splitting (5+ test cases enables train/val split) |

### `manifest.yaml` — Scorer configuration

```yaml
skill_name: databricks-metric-views
tool_modules: [sql]  # Optional: MCP tool modules this skill uses

scorers:
  enabled: [sql_syntax, pattern_adherence, expected_facts_present]
  llm_scorers: [Safety, guidelines_from_expectations]
  default_guidelines:
    - "Responses must use Databricks-specific syntax"

quality_gates:
  syntax_valid: 1.0
  pattern_adherence: 0.9
```

The `tool_modules` field lists which MCP tool modules are relevant to the skill. When `--tools-only --tool-modules` is used, only skills whose `tool_modules` overlap with the requested modules are included in the cross-skill dataset. Behavior by value:

- **`tool_modules: [sql, compute]`** — included when `--tool-modules` contains `sql` or `compute`
- **`tool_modules: []`** — excluded from all `--tool-modules` filtered runs (no MCP tool dependency)
- **Field omitted** — always included (backward compatible fallback)

Without `--tool-modules`, all skills are included regardless. Available modules: `agent_bricks`, `aibi_dashboards`, `apps`, `compute`, `file`, `genie`, `jobs`, `lakebase`, `manifest`, `pipelines`, `serving`, `sql`, `unity_catalog`, `user`, `vector_search`, `volume_files`, `workspace`.

---

## Evaluation Criteria

Evaluation criteria are domain-specific rubrics that judges can load on demand when scoring traces. They live in `.test/eval-criteria/` as SKILL.md files — the same format used by agent skills.

### Directory structure

Each criteria is a folder containing a `SKILL.md` (YAML frontmatter + markdown body) and an optional `references/` directory with detailed rubrics:

```
eval-criteria/
├── general-quality/          # Always loaded (applies_to: [])
│   └── SKILL.md
├── sql-correctness/          # Loaded for SQL-related skills (applies_to: [sql])
│   ├── SKILL.md
│   └── references/
│       └── DATABRICKS_SQL_PATTERNS.md
└── tool-selection/           # Always loaded (applies_to: [])
    ├── SKILL.md
    └── references/
        └── MCP_TOOL_GUIDE.md
```

### How it works

`discover_skill_paths()` in `judges.py` scans `.test/eval-criteria/` for subdirectories containing a `SKILL.md` file, filtering by `applies_to` metadata against the skill's `tool_modules`. The discovered paths are passed to `make_judge(skills=[...])` when MLflow supports the native `skills=` parameter, enabling on-demand loading of domain-specific rubrics during scoring.

### `applies_to` filtering

The `applies_to` metadata field controls which criteria are available based on the skill's `tool_modules`:

- **`applies_to: [sql]`** — loaded only when the skill declares `tool_modules: [sql]`
- **`applies_to: []`** (or omitted) — always loaded (general-purpose criteria)

### Adding a new criteria

1. Create a folder: `.test/eval-criteria/<criteria-name>/`
2. Add `SKILL.md` with YAML frontmatter:
   ```yaml
   ---
   name: my-criteria
   description: >
     One-line description of when this criteria applies.
   metadata:
     category: evaluation
     version: "1.0"
     applies_to: [sql, compute]  # Empty list = always loaded
   ---

   ## Rubric content here...
   ```
3. Optionally add `references/` with detailed `.md` files
4. The criteria will be auto-discovered on the next evaluation run

For technical details on how criteria are loaded and injected, see [TECHNICAL.md — Adaptive Evaluation Criteria](TECHNICAL.md#adaptive-evaluation-criteria).

---

## Evaluation & Scoring

### SkillBench evaluator (default)

Each candidate skill is evaluated per-task using a WITH vs WITHOUT comparison:

1. **Generate WITH-skill response** — LLM generates with SKILL.md in context
2. **Generate WITHOUT-skill response** — LLM generates without skill (cached)
3. **Three focused field-based judges** — each makes 1 LLM call and returns binary `"yes"` / `"no"` verdicts:
   - **Correctness judge** (WITH + WITHOUT) — facts, API references, code syntax accuracy
   - **Completeness judge** (WITH + WITHOUT) — all parts addressed, expected info present
   - **Guideline adherence judge** (WITH only) — Databricks-specific patterns and practices
   - **Regression judge** (conditional) — fires only when effectiveness delta < -0.05
4. **Deterministic assertions** (0 LLM calls) — `assertions.py` checks `expected_facts` (substring match) and `expected_patterns` (regex match) against both responses

**Cost per task:** 5 LLM calls (correctness×2 + completeness×2 + guideline_adherence×1). WITHOUT calls are cached, so subsequent iterations cost only 3 calls.

**Scoring weights:**

| Component | Weight | Source |
|-----------|--------|--------|
| Effectiveness delta | 30% | Mean of (correctness_delta + completeness_delta) |
| Quality composite | 20% | Mean of (correctness + completeness + guideline_adherence) WITH scores |
| Fact/pattern coverage | 15% | Deterministic assertions from `assertions.py` |
| Guideline adherence | 10% | Dedicated weight for Databricks patterns |
| Token efficiency | 10% | Smaller candidates score higher |
| Structure | 5% | Syntax validation (Python, SQL, no hallucinated APIs) |
| Regression penalty | -10% | Explicit penalty when regression_judge detects harm |

**Binary-to-float conversion:** `yes=1.0`, `no=0.0`. Binary verdicts produce more reliable, consistent judgments than categorical or continuous scales.

### How GEPA uses evaluation feedback

GEPA's reflection LM reads `side_info` rendered as markdown headers. Key fields:

- **`Judge_correctness_with`** / **`Judge_correctness_without`** — per-dimension accuracy feedback with categorical verdicts
- **`Judge_completeness_with`** / **`Judge_completeness_without`** — per-dimension coverage feedback
- **`Judge_guideline_adherence`** — pattern compliance feedback (WITH only)
- **`Judge_effectiveness`** — per-dimension deltas (`correctness_delta`, `completeness_delta`, `overall_delta`)
- **`Regression_Analysis`** — specific "what to fix" guidance (only when regression detected)
- **`Missing_Facts`** / **`Missing_Patterns`** — exact list of what the skill should add (from assertions)
- **`Passed_Facts`** / **`Passed_Patterns`** — what the skill already covers
- **`scores`** — feeds GEPA's multi-objective Pareto frontier (`correctness_with`, `completeness_with`, `guideline_adherence`, `quality_composite`, etc.)

This gives GEPA three independent, actionable signals. A mutation that fixes correctness but doesn't help completeness shows clear movement on one dimension, guiding the next mutation.

### Why three judges (not one, not five)?

The previous single quality judge collapsed 5 criteria into one 0.0–1.0 score. When a mutation improved correctness but hurt completeness, the score barely moved — GEPA couldn't distinguish which dimension improved. Three judges cover the core evaluation dimensions without excessive cost:

1. **Correctness** → fix errors (API syntax, deprecated patterns)
2. **Completeness** → add missing content
3. **Guideline adherence** → align with Databricks patterns + `--focus` areas

Deterministic assertions in `assertions.py` remain for precise, structured `Missing_Facts` lists at zero LLM cost.

### Agent evaluator (`--agent-eval`)

Runs a real Claude Code agent and adds tool-call scoring:

| Component | Weight |
|-----------|--------|
| Effectiveness delta | 20% |
| Correctness | 20% |
| Completeness | 15% |
| Guideline adherence | 15% |
| Assertion coverage | 15% |
| Execution success | 5% |
| Token efficiency | 5% |
| Regression penalty | -5% |

The agent evaluator uses the same focused field-based judges as the proxy evaluator, plus `assertions.py` for structured `Missing_Facts`/`Missing_Patterns` feedback and deterministic trace scorers for behavioral compliance.

---

## Project Structure

```
.test/
├── eval-criteria/                  # Domain-specific judge rubrics
│   ├── general-quality/
│   │   └── SKILL.md
│   ├── sql-correctness/
│   │   ├── SKILL.md
│   │   └── references/
│   │       └── DATABRICKS_SQL_PATTERNS.md
│   └── tool-selection/
│       ├── SKILL.md
│       └── references/
│           └── MCP_TOOL_GUIDE.md
├── scripts/
│   └── optimize.py              # CLI entry point
├── claude_agent_settings.json   # Claude Code agent environment config
├── src/skill_test/
│   ├── agent/
│   │   └── executor.py          # Claude Agent SDK wrapper + MLflow tracing
│   └── optimize/
│       ├── runner.py            # Multi-pass GEPA orchestrator
│       ├── skillbench_evaluator.py  # Fast proxy evaluator (WITH vs WITHOUT)
│       ├── agent_evaluator.py   # Real Claude Code agent evaluator
│       ├── assertions.py        # Deterministic fact/pattern assertions (zero LLM cost)
│       ├── assessment_fetcher.py # MLflow assessment injection
│       ├── judges.py            # MLflow quality judge factory + fallback chain
│       ├── config.py            # Presets, model registration
│       ├── splitter.py          # Train/val dataset splitting
│       ├── tools.py             # MCP tool description extraction
│       └── utils.py             # Token counting, path resolution
└── skills/<skill-name>/
    ├── ground_truth.yaml        # Test cases
    ├── manifest.yaml            # Scorer configuration
    ├── optimized_SKILL.md       # Last optimization output
    └── last_optimization.json   # Metadata for --apply-last
```

---

## Troubleshooting

**MLflow evaluation hangs**: Run with debug logging:
```bash
MLFLOW_LOG_LEVEL=DEBUG uv run python .test/scripts/mlflow_eval.py <skill-name>
```

**Rate limits**: The framework automatically falls back through alternative models (GPT-5-2, Gemini-3-1-Pro, Claude Opus 4.5, etc.) with exponential backoff when rate-limited.

**Agent eval fails**: Check that `.test/claude_agent_settings.json` has valid credentials and the model endpoint is accessible. The agent runs with a 300s default timeout — increase with `--agent-timeout`.

**Resuming interrupted runs**: Use `--run-dir` for checkpointing:
```bash
# Start with checkpointing
uv run python .test/scripts/optimize.py databricks-metric-views --preset standard --run-dir ./opt_runs/mv

# Resume after interruption (same command)
uv run python .test/scripts/optimize.py databricks-metric-views --preset standard --run-dir ./opt_runs/mv

# Graceful stop mid-pass
touch ./opt_runs/mv/pass_1/gepa.stop
```

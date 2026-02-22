# Skill Testing & Optimization Framework

Evaluate and optimize Databricks SKILL.md files using automated scorers and [GEPA](https://github.com/gepa-ai/gepa)-powered optimization.

## Quick Start: Optimize a Skill

One command evaluates a skill's current quality, runs GEPA optimization, and shows the results:

```bash
uv run python .test/scripts/optimize.py databricks-model-serving --preset quick --apply
```

This will:
1. Load the SKILL.md and its test cases from `ground_truth.yaml`
2. Score the current skill against deterministic scorers (syntax, patterns, APIs, facts)
3. Run GEPA's optimization loop (reflect on failures, propose mutations, select via Pareto frontier)
4. Show a diff with quality improvement and token reduction
5. Apply the optimized SKILL.md back to disk

## Setup

```bash
# Install with optimization dependencies
uv pip install -e ".test/[all]"

# Authentication for the reflection model (pick one)
# Option A: Databricks Model Serving (default)
export DATABRICKS_API_KEY="dapi..."
export DATABRICKS_API_BASE="https://<workspace>.cloud.databricks.com"

# Option B: OpenAI
export OPENAI_API_KEY="sk-..."
export GEPA_REFLECTION_LM="openai/gpt-4o"
```

---

## Optimization Commands

### Evaluate + Optimize a Skill

```bash
# Standard optimization (50 iterations)
uv run python .test/scripts/optimize.py <skill-name>

# Quick pass (15 iterations, good for initial check)
uv run python .test/scripts/optimize.py <skill-name> --preset quick

# Thorough optimization (150 iterations, production quality)
uv run python .test/scripts/optimize.py <skill-name> --preset thorough

# Dry run: see scores and config without calling GEPA
uv run python .test/scripts/optimize.py <skill-name> --dry-run

# Optimize and apply the result
uv run python .test/scripts/optimize.py <skill-name> --apply

# Optimize all skills that have test cases
uv run python .test/scripts/optimize.py --all --preset quick
```

### Optimize MCP Tool Descriptions

GEPA can also optimize the `@mcp.tool` docstrings in `databricks-mcp-server/`. Tool descriptions are what the AI agent sees when deciding which tool to call -- concise, accurate descriptions lead to better tool selection.

```bash
# Optimize a skill AND its related tool modules together
uv run python .test/scripts/optimize.py databricks-model-serving --include-tools --tool-modules serving sql

# Optimize specific tool modules alongside a skill
uv run python .test/scripts/optimize.py databricks-model-serving --include-tools --tool-modules serving compute jobs

# Optimize ALL tool modules alongside a skill
uv run python .test/scripts/optimize.py databricks-model-serving --include-tools

# Optimize ONLY tool descriptions (no SKILL.md)
uv run python .test/scripts/optimize.py databricks-model-serving --tools-only --tool-modules serving

# Dry run to see components and token counts
uv run python .test/scripts/optimize.py databricks-model-serving --include-tools --dry-run
```

When `--include-tools` is used, GEPA creates one component per tool module (e.g., `tools_sql`, `tools_serving`) and round-robins through them alongside `skill_md`. The `--apply` flag writes optimized docstrings back to the MCP server source files.

Available tool modules (88 tools across 16 modules):
`agent_bricks`, `aibi_dashboards`, `apps`, `compute`, `file`, `genie`, `jobs`, `lakebase`, `manifest`, `pipelines`, `serving`, `sql`, `unity_catalog`, `user`, `vector_search`, `volume_files`

### Changing the Reflection Model

GEPA uses a reflection LM to analyze scorer failures and propose skill improvements. The default is **Databricks Model Serving** (`databricks-gpt-5-2`).

| Method | Example |
|--------|---------|
| Environment variable | `export GEPA_REFLECTION_LM="databricks/databricks-gpt-5-2"` |
| CLI flag | `--reflection-lm "openai/gpt-4o"` |
| Python | `optimize_skill("my-skill", reflection_lm="anthropic/claude-sonnet-4-5-20250514")` |

Model strings use [litellm provider prefixes](https://docs.litellm.ai/docs/providers):

| Provider | Prefix | Example |
|----------|--------|---------|
| Databricks Model Serving | `databricks/` | `databricks/databricks-gpt-5-2` |
| OpenAI | `openai/` | `openai/gpt-4o` |
| Anthropic | `anthropic/` | `anthropic/claude-sonnet-4-5-20250514` |

### Authentication

| Provider | Required Environment Variables |
|----------|-------------------------------|
| Databricks | `DATABRICKS_API_KEY`, `DATABRICKS_API_BASE` |
| OpenAI | `OPENAI_API_KEY` |
| Anthropic | `ANTHROPIC_API_KEY` |

---

## Building Test Cases for a Skill

Skills need test cases before optimization can work well. The workflow:

### 1. Initialize Test Scaffolding

```
/skill-test <skill-name> init
```

Generates `manifest.yaml` with scorer config, empty `ground_truth.yaml`, and `candidates.yaml`.

### 2. Add Test Cases

```
/skill-test <skill-name> add
```

Interactively generates test cases. Passing tests go to `ground_truth.yaml`, failing ones to `candidates.yaml` for review.

### 3. Review Candidates

```
/skill-test <skill-name> review
/skill-test <skill-name> review --batch --filter-success
```

### 4. Configure Scorers (Optional)

Edit `.test/skills/<skill-name>/manifest.yaml` or:
```
/skill-test <skill-name> scorers update --add-guideline "Must use CLUSTER BY"
```

### 5. Run Evaluation

```
/skill-test <skill-name> run
```

### 6. Save Baseline + Check Regressions

```
/skill-test <skill-name> baseline
/skill-test <skill-name> regression
```

---

## Trace Evaluation

Capture Claude Code sessions and evaluate against skill expectations.

### Enable MLflow Tracing

```bash
export DATABRICKS_CONFIG_PROFILE=aws-apps
export MLFLOW_EXPERIMENT_NAME="/Users/<your-email>/Claude Code Skill Traces"

pip install mlflow[databricks]
mlflow autolog claude -u databricks -n "$MLFLOW_EXPERIMENT_NAME" .
```

### Evaluate Traces

```
/skill-test <skill-name> trace-eval --trace ~/.claude/projects/.../session.jsonl
/skill-test <skill-name> trace-eval --run-id abc123
/skill-test <skill-name> list-traces --experiment "$MLFLOW_EXPERIMENT_NAME"
```

---

## Command Reference

| Command    | Description                              |
|------------|------------------------------------------|
| `run`      | Execute tests against ground truth       |
| `init`     | Generate test scaffolding from skill docs|
| `add`      | Add test cases interactively             |
| `review`   | Review and promote candidates            |
| `baseline` | Save current results as baseline         |
| `regression` | Compare against baseline               |
| `mlflow`   | Full evaluation with LLM judges          |
| `optimize` | Optimize skill with GEPA                 |
| `trace-eval` | Evaluate session traces                |
| `list-traces` | List available traces                 |
| `scorers`  | View/update scorer config                |

---

## Files

```
.test/skills/<skill-name>/
├── manifest.yaml       # Scorers, guidelines, trace expectations
├── ground_truth.yaml   # Verified test cases
└── candidates.yaml     # Pending review

.test/baselines/<skill-name>/
└── baseline.yaml       # Regression baseline
```

---

## CI/CD

```bash
uv pip install -e ".test/"
uv run pytest .test/tests/
uv run python .test/scripts/regression.py <skill-name>
```

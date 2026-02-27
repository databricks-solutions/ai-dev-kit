# Skill Testing & Optimization Framework

Evaluate and optimize Databricks SKILL.md files using automated scorers and [GEPA](https://github.com/gepa-ai/gepa)-powered optimization.

## Quick Start: Optimize a Skill

One command evaluates a skill's current quality, runs GEPA optimization, and shows the results:

```bash
uv run python .test/scripts/optimize.py databricks-model-serving --preset quick --apply
```

This will:
1. Load the SKILL.md and its test cases from `ground_truth.yaml`
2. Have a generation model (Sonnet) produce responses using ONLY the skill, then score those responses
3. Also score the SKILL.md itself for pattern/fact coverage
4. Run GEPA's optimization loop (reflect on failures, propose mutations, select via Pareto frontier)
5. Show a diff with quality improvement and token reduction
6. Apply the optimized SKILL.md back to disk

## Setup

```bash
# Install with optimization dependencies
uv pip install -e ".test/[all]"

# Authentication for models (pick one)
# Option A: Databricks Model Serving (default for both gen + reflection)
export DATABRICKS_API_KEY="dapi..."
export DATABRICKS_API_BASE="https://<workspace>.cloud.databricks.com/serving-endpoints"

# Option B: OpenAI
export OPENAI_API_KEY="sk-..."
export GEPA_REFLECTION_LM="openai/gpt-4o"
export GEPA_GEN_LM="openai/gpt-4o"

# Optional: override generation model (default: databricks/databricks-claude-sonnet-4-6)
# export GEPA_GEN_LM="databricks/databricks-claude-sonnet-4-6"

# Optional: set a global token budget ceiling for optimization
# export GEPA_TOKEN_BUDGET=50000
```

---

## Optimization Commands

### Evaluate + Optimize a Skill

```bash
# Standard optimization (50 iterations per component, up to 5 passes)
uv run python .test/scripts/optimize.py <skill-name>

# Quick pass (15 iterations, good for initial check)
uv run python .test/scripts/optimize.py <skill-name> --preset quick

# Thorough optimization (150 iterations, production quality)
uv run python .test/scripts/optimize.py <skill-name> --preset thorough

# Dry run: see scores and config without calling GEPA
uv run python .test/scripts/optimize.py <skill-name> --dry-run

# Apply the last saved result (no re-run!)
uv run python .test/scripts/optimize.py <skill-name> --apply-last

# Run optimization and immediately apply
uv run python .test/scripts/optimize.py <skill-name> --apply

# Use a specific generation model for evaluation
uv run python .test/scripts/optimize.py <skill-name> --gen-model "openai/gpt-4o"

# Control iteration depth (default: 5 passes)
uv run python .test/scripts/optimize.py <skill-name> --max-passes 3

# Set a token budget ceiling (candidates exceeding this are penalized)
uv run python .test/scripts/optimize.py <skill-name> --token-budget 50000

# Optimize all skills that have test cases
uv run python .test/scripts/optimize.py --all --preset quick
```

After each run, the optimized result is automatically saved to `.test/skills/<skill-name>/optimized_SKILL.md`. You can review it, diff it against the original, and apply when ready with `--apply-last` — no need to re-run the optimization.

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

**Note:** The SkillBench evaluator (default) automatically includes tools even without `--include-tools`, since tool descriptions are the primary token consumer (~17K tokens across 88 tools). Use `--tools-only` to optimize only tool descriptions without the SKILL.md.

The iteration budget (`max_metric_calls`) is automatically scaled by the number of components so each one gets the preset's full budget. Additionally, the optimizer runs **up to 5 passes** (configurable with `--max-passes`), re-seeding from the previous best each time. It stops early if a pass produces no improvement.

Available tool modules (88 tools across 16 modules):
`agent_bricks`, `aibi_dashboards`, `apps`, `compute`, `file`, `genie`, `jobs`, `lakebase`, `manifest`, `pipelines`, `serving`, `sql`, `unity_catalog`, `user`, `vector_search`, `volume_files`

### Changing the Generation Model

The evaluator uses a **generation model** to simulate an agent reading the SKILL.md and producing a response. Better skill content leads to better generated responses, which drives GEPA to make meaningful improvements.

The default is `databricks/databricks-claude-sonnet-4-6`.

| Method | Example |
|--------|---------|
| Environment variable | `export GEPA_GEN_LM="databricks/databricks-claude-sonnet-4-6"` |
| CLI flag | `--gen-model "openai/gpt-4o"` |
| Python | `optimize_skill("my-skill", gen_model="anthropic/claude-sonnet-4-5-20250514")` |

### Changing the Reflection Model

GEPA uses a reflection LM to analyze scorer failures and propose skill improvements. The default is **Databricks Model Serving** (`databricks-claude-opus-4-6`, 200K context).

| Method | Example |
|--------|---------|
| Environment variable | `export GEPA_REFLECTION_LM="databricks/databricks-claude-opus-4-6"` |
| CLI flag | `--reflection-lm "openai/gpt-4o"` |
| Python | `optimize_skill("my-skill", reflection_lm="anthropic/claude-sonnet-4-5-20250514")` |

Model strings use [litellm provider prefixes](https://docs.litellm.ai/docs/providers):

| Provider | Prefix | Example | Context |
|----------|--------|---------|---------|
| Databricks Model Serving | `databricks/` | `databricks/databricks-claude-opus-4-6` | 200K |
| OpenAI | `openai/` | `openai/gpt-4o` | 128K |
| Anthropic | `anthropic/` | `anthropic/claude-sonnet-4-5-20250514` | 200K |

**Context window requirement:** The reflection model must have a context window large enough to hold the full candidate (all components) plus GEPA's reflection overhead (~3x the raw candidate tokens). Models with small context windows (e.g., 8K) will fail with `BadRequestError` during reflection. The optimizer validates this upfront and warns if the model is too small.

### Authentication

| Provider | Required Environment Variables |
|----------|-------------------------------|
| Databricks | `DATABRICKS_API_KEY`, `DATABRICKS_API_BASE` (must end with `/serving-endpoints`) |
| OpenAI | `OPENAI_API_KEY` |
| Anthropic | `ANTHROPIC_API_KEY` |

Optional overrides: `GEPA_REFLECTION_LM` (reflection model), `GEPA_GEN_LM` (generation model for evaluation), `GEPA_TOKEN_BUDGET` (token ceiling for optimization).

---

## How Evaluation Works

The evaluation system answers a single question: **does this SKILL.md teach an AI agent the right things?** A skill that scores well means an agent reading it will produce correct code with the right APIs and patterns. A skill that scores poorly means the agent will hallucinate, use deprecated APIs, or miss important patterns.

Understanding evaluation is important because it drives everything else — GEPA uses scores to decide which skill mutations to keep, and you use scores to know if your skill is good enough to ship.

### Why These Files Exist

Each skill under `.test/skills/<skill-name>/` has two key files:

**`ground_truth.yaml`** — The test cases. Each entry is a prompt ("Create a ResponsesAgent") paired with the expected response and expectations (patterns, facts, guidelines). These define *what the skill should teach*. Without test cases, the evaluator has nothing to score against and GEPA has no signal to optimize toward.

**`manifest.yaml`** — The scorer configuration. Controls *which scorers run* and *what thresholds apply*. Think of it as the grading rubric: which checks are enabled, what guidelines the LLM judge enforces, and what trace expectations exist. If you don't provide one, the system uses sensible defaults (syntax + patterns + facts + hallucination checks).

The test cases in `ground_truth.yaml` are also what gets split into train/val sets for GEPA — the optimizer converts each test case into a GEPA dataset instance:

| ground_truth.yaml field | GEPA field | Purpose |
|------------------------|------------|---------|
| `inputs.prompt` | `input` | The task the reflection LM sees |
| `outputs.response` | `answer` | Reference response for sanity-check scoring |
| `expectations.*` | `additional_context` | Encoded as JSON; scorers extract patterns and facts |
| `metadata.category` | (stratification) | Ensures balanced train/val split |

### The Layered Evaluation

Rather than scoring a single static response, the evaluator runs five layers that give GEPA progressively richer signal:

| Layer | Weight | What it does | Source |
|-------|--------|-------------|--------|
| **Generated response quality** | 20% | An LLM reads ONLY the SKILL.md and answers the test prompt. Its response is scored for patterns/facts. | `evaluator.py` → litellm generation |
| **Skill content coverage** | 35% | Checks if the SKILL.md itself contains the patterns and facts needed. If a pattern is missing from the skill, this drops immediately. | `evaluator.py` → `_score_skill_content()` |
| **Reference response check** | 5% | Scores the ground truth response as a sanity baseline. This is mostly static — it ensures the test case itself is valid. | `evaluator.py` → `_run_deterministic_scorers()` |
| **Structure validation** | 10% | Validates Python/SQL syntax in code blocks and checks for hallucinated APIs (deprecated `@dlt.table`, old `mlflow.evaluate`, etc). | `evaluator.py` → `_validate_skill_structure()` |
| **Token efficiency** | 30% | Rewards concise skill content. Shrinking below original size earns a bonus (up to 1.15x), same size = 1.0, linear penalty to 0.0 at 2x original. | `evaluator.py` → token counting |

**Why this works:** The key insight is that Layer 1 (generated response) creates a causal chain — if the SKILL.md is missing a pattern, the generation model cannot produce it, so the pattern scorer fails, so the score drops. This gives GEPA immediate, dynamic signal when content changes, unlike the old approach where ~80% of the score came from an immutable ground truth string.

**Fallback mode:** When no generation model is available (no `GEPA_GEN_LM`), the weights shift to 40% skill content + 20% reference + 10% structure + 30% efficiency.

### SkillBench Evaluator (Default)

The default evaluator (`--evaluator skillbench`) measures **skill effectiveness**: how much does the skill help an agent answer correctly? It runs each test case twice — once WITH the skill and once WITHOUT — then scores the delta.

| Weight | Dimension | What it measures |
|--------|-----------|-----------------|
| **45%** | Skill Effectiveness | `pass_rate_with - pass_rate_without` — the delta. Only rewards content the agent doesn't already know. |
| **25%** | Absolute Quality | `pass_rate_with` — overall correctness with the skill present. |
| **5%** | Structure | Syntax validity (Python/SQL) and no hallucinated APIs. |
| **25%** | Token Efficiency | Smaller candidates score higher. Linear penalty for growth (0.0 at 2x original). Bonus for reduction (up to 1.15 at 0% of original). |

**Key difference from the legacy evaluator:** SkillBench uses binary pass/fail assertions (from `expectations` in `ground_truth.yaml`) rather than fuzzy scorer scores. Assertions are classified as:
- **NEEDS_SKILL** — fails both with and without the skill (the skill must teach this)
- **REGRESSION** — passes without, fails with (the skill confuses the agent — simplify or remove)
- **POSITIVE** — fails without, passes with (the skill is helping — keep it)
- **NEUTRAL** — same result either way (the agent already knows this — adding it wastes tokens)

The reflection LM sees these labels in the `Error` field of each example's side info, guiding it to add NEEDS_SKILL content and remove REGRESSION content.

**Token budget:** Use `--token-budget N` to set a hard ceiling. Candidates exceeding the budget receive a steep penalty on top of the normal efficiency score. Set via CLI or `GEPA_TOKEN_BUDGET` env var.

To use the legacy evaluator instead: `--evaluator legacy`.

### Built-in Scorers

The system ships with four tiers of scorers:

**Tier 1: Deterministic (fast, reliable, ~$0/eval)**

| Scorer | What it checks | Configured via |
|--------|---------------|----------------|
| `python_syntax` | Python code blocks parse with `ast.parse()` | `manifest.yaml` → `scorers.enabled` |
| `sql_syntax` | SQL blocks have valid structure (balanced parens, recognizable statements) | `manifest.yaml` → `scorers.enabled` |
| `pattern_adherence` | Required regex patterns appear in response (e.g., `ResponsesAgent`, `CLUSTER BY`) | `ground_truth.yaml` → `expectations.expected_patterns` |
| `no_hallucinated_apis` | No deprecated/invented APIs (`@dlt.table`, `dlt.read`, `PARTITION BY`, old `mlflow.evaluate`) | `manifest.yaml` → `scorers.enabled` |
| `expected_facts_present` | Required facts mentioned in response (case-insensitive substring match) | `ground_truth.yaml` → `expectations.expected_facts` |

**Tier 2: Trace-based (for session evaluation)**

| Scorer | What it checks |
|--------|---------------|
| `tool_count` | Tool usage within limits (e.g., max 5 Bash calls) |
| `token_budget` | Token usage within budget |
| `required_tools` | Required tools were called |
| `banned_tools` | Banned tools were NOT called |
| `file_existence` | Expected files were created |
| `tool_sequence` | Tools used in expected order |
| `category_limits` | Tool category limits (bash, file_ops, mcp) |

These are configured in `manifest.yaml` under `trace_expectations`.

**Tier 3: LLM judges (expensive, nuanced, ~$0.01/eval)**

| Scorer | What it checks |
|--------|---------------|
| `Safety` | MLflow's built-in safety scorer |
| `Guidelines` | LLM judges response against `default_guidelines` from manifest |
| `guidelines_from_expectations` | Per-test-case guidelines from `expectations.guidelines` in ground_truth.yaml |

### Adding a Custom Scorer

There are three ways to add custom evaluation, from easiest to most flexible:

#### Option 1: Per-test-case guidelines (no code required)

Add `guidelines` to any test case in `ground_truth.yaml`. An LLM judge evaluates the response against these:

```yaml
test_cases:
  - id: my_test_001
    inputs:
      prompt: "Deploy a model to serving"
    expectations:
      guidelines:
        - "Must use Unity Catalog three-level namespace"
        - "Must recommend job-based deployment over synchronous"
        - "Should warn about cold start latency"
      expected_facts:
        - "ResponsesAgent"
```

Then enable the scorer in `manifest.yaml`:

```yaml
scorers:
  enabled:
    - python_syntax
    - pattern_adherence
    - expected_facts_present
  llm_scorers:
    - guidelines_from_expectations
```

#### Option 2: Skill-wide guidelines (no code required)

Set `default_guidelines` in `manifest.yaml` to apply rules to ALL test cases for a skill:

```yaml
scorers:
  enabled:
    - python_syntax
    - pattern_adherence
    - no_hallucinated_apis
    - expected_facts_present
  llm_scorers:
    - Guidelines
  default_guidelines:
    - "Must use ResponsesAgent pattern, not ChatAgent"
    - "Must use self.create_text_output_item() for output"
    - "Code must be deployable to Databricks Model Serving"
```

You can also create multiple named guideline sets:

```yaml
  llm_scorers:
    - Guidelines:api_correctness
    - Guidelines:deployment_quality
  default_guidelines:
    - "Your guidelines here"
```

#### Option 3: Custom Python scorer (full flexibility)

Create a new scorer function in `.test/src/skill_test/scorers/` and register it. Scorers use the MLflow `@scorer` decorator and return `Feedback` objects:

```python
# .test/src/skill_test/scorers/my_custom.py
from mlflow.genai.scorers import scorer
from mlflow.entities import Feedback
from typing import Dict, Any

@scorer
def my_custom_check(outputs: Dict[str, Any], expectations: Dict[str, Any]) -> Feedback:
    """Check for something specific to my use case."""
    response = outputs.get("response", "")

    # Your custom logic here
    issues = []
    if "spark.sql(" in response and "spark.read.table(" not in response:
        issues.append("Should prefer spark.read.table() over spark.sql() for reads")

    if issues:
        return Feedback(
            name="my_custom_check",
            value="no",
            rationale=f"Issues: {'; '.join(issues)}",
        )

    return Feedback(name="my_custom_check", value="yes", rationale="All custom checks passed")
```

Then register it in `runners/evaluate.py` → `build_scorers()`:

```python
SCORER_MAP = {
    # ... existing scorers ...
    "my_custom_check": my_custom_check,
}
```

And enable it in your skill's `manifest.yaml`:

```yaml
scorers:
  enabled:
    - python_syntax
    - pattern_adherence
    - my_custom_check  # your new scorer
```

**Scorer function signatures:** The system auto-detects which parameters your scorer accepts:
- `outputs: Dict[str, Any]` — always available, contains `{"response": "..."}`
- `expectations: Dict[str, Any]` — from ground_truth.yaml `expectations` field
- `inputs: Dict[str, Any]` — contains `{"prompt": "..."}`

Return either a single `Feedback` or a `list[Feedback]` (for scorers that produce multiple checks like `pattern_adherence`).

### Manifest Configuration Examples

Here are manifest patterns for different skill types:

**Python SDK skill** — emphasizes syntax and API correctness:
```yaml
scorers:
  enabled: [python_syntax, pattern_adherence, no_hallucinated_apis, expected_facts_present]
  llm_scorers: [guidelines_from_expectations]
  default_guidelines:
    - "Must use ResponsesAgent pattern for GenAI agents"
quality_gates:
  syntax_valid: 1.0
  pattern_adherence: 0.9
```

**SQL-heavy skill** — adds SQL validation:
```yaml
scorers:
  enabled: [python_syntax, sql_syntax, pattern_adherence, no_hallucinated_apis, expected_facts_present]
  default_guidelines:
    - "Must use SDP syntax (CREATE OR REFRESH STREAMING TABLE)"
```

**Skill with trace expectations** — limits tool usage during session evaluation:
```yaml
scorers:
  enabled: [python_syntax, pattern_adherence, no_hallucinated_apis, expected_facts_present]
  default_guidelines:
    - "Must use correct MCP tools (manage_ka, manage_mas)"
  trace_expectations:
    tool_limits:
      manage_ka: 10
      manage_mas: 10
    required_tools: [Read]
    banned_tools: []
```

---

## Best Practices for Optimization

These practices are derived from the [optimize_anything API guide](https://gepa-ai.github.io/gepa/blog/2026/02/18/introducing-optimize-anything/) and help you get the most out of GEPA-powered optimization.

### 1. Write Rich Evaluators with Actionable Side Information (ASI)

GEPA's reflection LM learns from diagnostic feedback, not just scores. The more context your evaluator surfaces, the better the proposals.

- **Return diagnostics**, not just a number. Use `oa.log()` or return `(score, side_info_dict)` to surface error messages, failing patterns, and missing facts.
- **Break scoring into multiple dimensions**. Rather than a single composite score, provide separate scores for syntax, pattern adherence, API accuracy, and conciseness. GEPA's Pareto-efficient selection preserves candidates that excel in different dimensions.
- Our built-in evaluator already does this -- it returns per-scorer feedback via `feedback_to_asi()`.

### 2. Build a Diverse Dataset of Test Cases

GEPA operates in three modes depending on what data you provide:
- **Single-task** (no dataset): evaluator scores the artifact directly
- **Multi-task** (dataset only): Pareto-efficient search across tasks
- **Generalization** (dataset + valset): trains on tasks, validates on held-out examples

For best results:
- Aim for **5+ test cases** to enable a train/val split (Generalization mode). Fewer than 5 defaults to single-task mode.
- Cover **different categories** of usage (e.g., simple queries, complex joins, error handling). The automatic stratified splitter ensures balanced representation.
- Use `/skill-test <name> add` to interactively generate test cases, then review with `/skill-test <name> review`.

### 3. Tune reflection_minibatch_size for Focused Improvement

GEPA's default `reflection_minibatch_size=2` shows the reflection LM feedback from 2 tasks per iteration. This keeps each reflection focused and prevents the LM from trying to fix everything at once.

- For skills with **many test cases** (10+), the default of 2 works well -- over iterations, all tasks get attention.
- For skills with **few test cases** (3-5), consider increasing to 3 so more context is visible per step.

### 4. Use Multi-Component Optimization for Skills + Tools

When you optimize a SKILL.md alongside tool descriptions (`--include-tools`), GEPA creates separate components and cycles through them with round-robin selection. This means:

- Each component gets its **own** optimization budget (the preset's `max_metric_calls` is multiplied by the component count).
- Up to `--max-passes` full optimization cycles run, re-seeding from the best candidate each time.
- Start with `--tool-modules` to target specific modules rather than optimizing all 16 at once.

### 5. Choose the Right Preset

| Preset | Budget per Component | Use Case |
|--------|---------------------|----------|
| `quick` | 15 calls | Fast feedback loop, initial exploration |
| `standard` | 50 calls | Default, good balance of quality and cost |
| `thorough` | 150 calls | Production-quality optimization |

For multi-component runs, the actual `max_metric_calls` = budget x number of components.

### 6. Leverage the Background Context

The `background` parameter tells the reflection LM domain-specific constraints. Our optimizer automatically provides Databricks-specific context (token budgets, skill structure rules, scorer descriptions). For custom use cases, you can extend `build_optimization_background()` in `evaluator.py`.

### 7. Iterate with Dry Runs First

Always start with `--dry-run` to verify your setup:
```bash
uv run python .test/scripts/optimize.py <skill-name> --include-tools --dry-run
```
This shows the component list, token counts, current score, and config without calling GEPA. Fix any scorer issues or missing test cases before spending optimization budget.

---

## Building Test Cases for a Skill

Skills need test cases before optimization can work well. There are three ways to add them:

### Quick: Extract from MLflow Traces

If you have MLflow traces (from `mlflow autolog claude`), extract test cases directly from them. You can find your traces at your workspace's MLflow experiment page, e.g.:
`https://<workspace>.cloud.databricks.com/ml/experiments/<experiment-id>/traces`

```bash
# Step 1: Set authentication
export DATABRICKS_HOST="https://e2-demo-field-eng.cloud.databricks.com"
export DATABRICKS_TOKEN="dapi..."

# Step 2: List traces in your experiment to see what's available
uv run python .test/scripts/trace_to_examples.py \
  --experiment-id 2452310130108632 --list

# Step 3: Extract examples from all recent traces
uv run python .test/scripts/trace_to_examples.py \
  --experiment-id 2452310130108632 \
  --skill databricks-model-serving

# Or extract from a specific trace ID (from the UI or --list output)
uv run python .test/scripts/trace_to_examples.py \
  --trace-id tr-d416fccdab46e2dea6bad1d0bd8aaaa8 \
  --skill databricks-model-serving

# Or extract from a specific MLflow run ID
uv run python .test/scripts/trace_to_examples.py \
  --run-id abc123def456 \
  --skill databricks-model-serving

# Refine auto-extracted expectations with an LLM
uv run python .test/scripts/trace_to_examples.py \
  --experiment-id 2452310130108632 \
  --skill databricks-model-serving --refine

# Auto-append directly to ground_truth.yaml (skip manual review)
uv run python .test/scripts/trace_to_examples.py \
  --experiment-id 2452310130108632 \
  --skill databricks-model-serving --trust

# Limit how many traces to process
uv run python .test/scripts/trace_to_examples.py \
  --experiment-id 2452310130108632 \
  --skill databricks-model-serving --limit 5
```

You can also extract from local session.jsonl files (Claude Code stores these at `~/.claude/projects/`):

```bash
uv run python .test/scripts/trace_to_examples.py \
  --trace ~/.claude/projects/.../session.jsonl \
  --skill databricks-model-serving
```

The script extracts user prompt / assistant response pairs, auto-generates `expected_patterns` from code blocks and `expected_facts` from API references, and saves to `candidates.yaml` for review (or directly to `ground_truth.yaml` with `--trust`).

#### Workflow: MLflow Traces to Optimized Skill

The end-to-end workflow for turning real agent sessions into skill improvements:

```bash
# 1. Extract examples from your traces
uv run python .test/scripts/trace_to_examples.py \
  --experiment-id 2452310130108632 \
  --skill databricks-model-serving --refine

# 2. Review the extracted candidates
cat .test/skills/databricks-model-serving/candidates.yaml

# 3. Promote good candidates to ground_truth.yaml
# (edit candidates.yaml, keep the good ones, then)
uv run python .test/scripts/trace_to_examples.py \
  --experiment-id 2452310130108632 \
  --skill databricks-model-serving --trust

# 4. Run optimization with the enriched dataset
uv run python .test/scripts/optimize.py databricks-model-serving --preset quick

# 5. If score improves, apply
uv run python .test/scripts/optimize.py databricks-model-serving --preset standard --apply
```

### Quick: Add a Single Example Manually

```bash
# Interactive mode — prompts for each field
uv run python .test/scripts/add_example.py databricks-model-serving

# Inline mode — provide prompt and response directly
uv run python .test/scripts/add_example.py databricks-model-serving \
  --prompt "Create a ChatAgent with tool calling" \
  --response-file /path/to/response.md \
  --facts "Uses ChatAgent class" "Implements predict method" \
  --patterns "ChatAgent" "def predict"

# From clipboard (paste prompt + response separated by ---)
uv run python .test/scripts/add_example.py databricks-model-serving --from-clipboard
```

The script auto-generates an ID, detects code language, extracts patterns from code blocks, and confirms before saving.

### Full Workflow: Initialize + Add + Review

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

## Test Case Examples

Test cases live in `ground_truth.yaml` and tell GEPA what the skill should produce for a given prompt. Each test case has **inputs** (the user prompt), **outputs** (the expected response), and **expectations** (what scorers check). Here are real examples from the repo.

### Example 1: Code Generation Test Case

A test case that checks whether the skill produces correct Python code with the right API calls:

```yaml
test_cases:
  - id: serving_responses_agent_001
    inputs:
      prompt: "Create a ResponsesAgent that uses UC functions for tool calling"
    outputs:
      response: |
        ```python
        from databricks.agents import ResponsesAgent

        agent = ResponsesAgent(
            model="databricks-claude-sonnet-4",
            tools=[{"type": "function", "function": {"name": "catalog.schema.my_function"}}],
            instructions="You are a helpful assistant.",
        )
        ```
      execution_success: true
    expectations:
      expected_facts:
        - "Uses ResponsesAgent from databricks.agents"
        - "Includes tools parameter with UC function reference"
        - "Sets model to a valid Databricks model endpoint"
      expected_patterns:
        - pattern: "ResponsesAgent"
          min_count: 1
          description: "Must use ResponsesAgent class"
        - pattern: "catalog\\.\\w+\\.\\w+"
          min_count: 1
          description: "UC function in three-level namespace"
    metadata:
      category: happy_path
      difficulty: medium
```

**What GEPA sees:** The evaluator scores the skill against this test case. If the skill doesn't teach the agent about `ResponsesAgent` or UC function namespaces, the pattern scorers fail and GEPA's reflection LM learns what to add.

### Example 2: SQL/Pipeline Test Case

A test case for Spark Declarative Pipelines (SDP) with SQL syntax validation:

```yaml
  - id: sdp_bronze_ingestion_001
    inputs:
      prompt: "Create a bronze ingestion streaming table that reads from cloud storage using Auto Loader"
    outputs:
      response: |
        ```sql
        CREATE OR REFRESH STREAMING TABLE bronze_events
        CLUSTER BY (event_date)
        AS SELECT *
        FROM STREAM read_files('s3://bucket/events/', format => 'json')
        ```
      execution_success: null
    expectations:
      expected_facts:
        - "Uses CREATE OR REFRESH STREAMING TABLE syntax"
        - "Uses CLUSTER BY for data layout optimization"
        - "Uses STREAM read_files() for Auto Loader ingestion"
      expected_patterns:
        - pattern: "CREATE OR REFRESH STREAMING TABLE"
          min_count: 1
          description: "SDP streaming table DDL"
        - pattern: "CLUSTER BY"
          min_count: 1
          description: "Liquid clustering"
        - pattern: "read_files\\("
          min_count: 1
          description: "Auto Loader function"
      guidelines:
        - "Must use SDP syntax (CREATE OR REFRESH), not legacy DLT syntax"
    metadata:
      category: happy_path
      difficulty: easy
```

### Example 3: Error Handling Test Case

Test cases don't have to be happy paths. Testing that a skill warns about common mistakes:

```yaml
  - id: serving_error_raw_dict_001
    inputs:
      prompt: "Why does my ChatAgent return raw dicts instead of proper messages?"
    outputs:
      response: |
        The `predict` method must return `ChatAgentResponse` with
        `ChatAgentMessage` objects, not raw dicts. Use
        `self.create_text_output_item(text)` to build response items.
      execution_success: null
    expectations:
      expected_facts:
        - "Explains the raw dict issue"
        - "Mentions self.create_text_output_item()"
      expected_patterns:
        - pattern: "create_text_output_item"
          min_count: 1
          description: "Correct helper method"
    metadata:
      category: error_handling
      difficulty: easy
```

### Example 4: Minimal Test Case

The simplest possible test case -- just a prompt and expected facts:

```yaml
  - id: genie_create_space_001
    inputs:
      prompt: "Create a Genie Space for our sales data"
    outputs:
      response: "I'll create a Genie Space connected to your sales tables."
    expectations:
      expected_facts:
        - "Creates a Genie Space"
        - "Connects to data tables"
    metadata:
      category: happy_path
      difficulty: easy
```

---

## End-to-End Walkthrough

Here's a complete example of adding test cases and running optimization for a new skill.

### Step 1: Initialize scaffolding

```bash
# Creates manifest.yaml, ground_truth.yaml, candidates.yaml
/skill-test my-new-skill init
```

### Step 2: Write test cases

Edit `.test/skills/my-new-skill/ground_truth.yaml`:

```yaml
metadata:
  skill_name: my-new-skill
  version: "1.0"

test_cases:
  - id: basic_001
    inputs:
      prompt: "Show me how to create a Delta table with liquid clustering"
    outputs:
      response: |
        ```sql
        CREATE TABLE catalog.schema.events (
          event_id BIGINT,
          event_date DATE,
          payload STRING
        )
        CLUSTER BY (event_date)
        ```
    expectations:
      expected_facts:
        - "Uses CREATE TABLE with CLUSTER BY"
      expected_patterns:
        - pattern: "CLUSTER BY"
          min_count: 1
          description: "Liquid clustering syntax"
    metadata:
      category: happy_path
      difficulty: easy

  - id: basic_002
    inputs:
      prompt: "How do I read from a Delta table using Spark?"
    outputs:
      response: |
        ```python
        df = spark.read.table("catalog.schema.my_table")
        ```
    expectations:
      expected_facts:
        - "Uses three-level namespace"
      expected_patterns:
        - pattern: "spark\\.read\\.table"
          min_count: 1
          description: "Spark table reader"
    metadata:
      category: happy_path
      difficulty: easy

  # ... add at least 5 test cases for train/val split
```

### Step 3: Verify setup with a dry run

```bash
uv run python .test/scripts/optimize.py my-new-skill --dry-run
```

Output:
```
=== Dry Run: my-new-skill (skillbench) ===
SKILL.md path: .claude/skills/my-new-skill/SKILL.md
[SkillBench] Auto-including tools: 16 modules, 88 tools, 64,675 chars
Components: ['skill_md', 'tools_sql', 'tools_serving', ...]
Total original tokens: 20,147
  skill_md: 2,847 tokens
  tools_sql: 3,200 tokens
  ...
Train tasks: 4
Val tasks: None (single-task mode)
Evaluator type: skillbench
Preset: standard (max_metric_calls=850, scaled for 17 component(s))
Max passes: 5
Reflection LM: databricks/databricks-claude-opus-4-6
Current score: 0.723
```

### Step 4: Run optimization

```bash
# Quick first pass to see if GEPA can improve
uv run python .test/scripts/optimize.py my-new-skill --preset quick

# Review the saved result
cat .test/skills/my-new-skill/optimized_SKILL.md
diff .claude/skills/my-new-skill/SKILL.md .test/skills/my-new-skill/optimized_SKILL.md

# Happy with it? Apply without re-running
uv run python .test/scripts/optimize.py my-new-skill --apply-last

# Or run standard for better results and apply immediately
uv run python .test/scripts/optimize.py my-new-skill --preset standard --apply
```

### Step 5: Save baseline for regression checking

```bash
/skill-test my-new-skill baseline

# Later, after making changes:
/skill-test my-new-skill regression
```

### Tips for Writing Good Test Cases

- **Cover different categories**: happy_path, error_handling, edge cases. The splitter stratifies by `metadata.category` so each category is represented in both train and val sets.
- **Be specific in expected_patterns**: Use regex that captures the essential API call, not surrounding prose. `"ResponsesAgent"` is better than `".*ResponsesAgent.*"`.
- **Include both simple and complex prompts**: Simple prompts test baseline quality; complex prompts stress-test the skill's depth.
- **Set `execution_success`**: `true` if you verified the code runs, `null` if it's theoretical, `false` if it's known to fail. This helps scorers weight results.
- **Use `guidelines` for soft expectations**: Things an LLM judge should check but that can't be captured by regex (e.g., "Should explain why CLUSTER BY is preferred over partitioning").

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
├── manifest.yaml           # Scorers, guidelines, trace expectations
├── ground_truth.yaml       # Verified test cases
├── candidates.yaml         # Pending review
├── optimized_SKILL.md      # Last optimization output (auto-saved)
└── last_optimization.json  # Metadata for --apply-last

.test/baselines/<skill-name>/
└── baseline.yaml       # Regression baseline

.test/scripts/
├── optimize.py             # CLI for GEPA optimization
├── trace_to_examples.py    # Extract test cases from session.jsonl traces
├── add_example.py          # Manually add test cases to ground_truth.yaml
└── _common.py              # Shared CLI utilities
```

---

## CI/CD

```bash
uv pip install -e ".test/"
uv run pytest .test/tests/
uv run python .test/scripts/regression.py <skill-name>
```

---
name: agent-evaluation
description: Use this when you need to EVALUATE OR IMPROVE or OPTIMIZE an existing LLM agent's output quality - including improving tool selection accuracy, answer quality, reducing costs, or fixing issues where the agent gives wrong/incomplete responses. Evaluates agents systematically using MLflow evaluation with datasets, scorers, and tracing. Covers end-to-end evaluation workflow or individual components (tracing setup, dataset creation, scorer definition, evaluation execution).
allowed-tools: Read, Write, Bash, Grep, Glob, WebFetch
---

# Agent Evaluation with MLflow

Comprehensive guide for evaluating GenAI agents with MLflow. Use this skill for the complete evaluation workflow or individual components - tracing setup, environment configuration, dataset creation, scorer definition, or evaluation execution. Each section can be used independently based on your needs.

## ⛔ CRITICAL: Must Use MLflow APIs

**DO NOT create custom evaluation frameworks.** You MUST use MLflow's native APIs:

- **Datasets**: Use `mlflow.genai.datasets.create_dataset()` - NOT custom test case files
- **Scorers**: Use `mlflow.genai.scorers` and `mlflow.genai.judges.make_judge()` - NOT custom scorer functions
- **Evaluation**: Use `mlflow.genai.evaluate()` - NOT custom evaluation loops
- **Scripts**: Use the provided `scripts/` directory templates - NOT custom `evaluation/` directories

**Why?** MLflow tracks everything (datasets, scorers, traces, results) in the experiment. Custom frameworks bypass this and lose all observability.

If you're tempted to create `evaluation/eval_dataset.py` or similar custom files, STOP. Use `scripts/create_dataset_template.py` instead.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Documentation Access Protocol](#documentation-access-protocol)
3. [Setup Overview](#setup-overview)
4. [Evaluation Workflow](#evaluation-workflow)
5. [References](#references)

## Quick Start

**⚠️ REMINDER: Use MLflow APIs from this skill. Do not create custom evaluation frameworks.**

**Setup (prerequisite)**: Install MLflow 3.8+, configure environment, integrate tracing

**Evaluation workflow in 4 steps** (each uses MLflow APIs):

1. **Understand**: Run agent, inspect traces, understand purpose
2. **Scorers**: Select and register scorers for quality criteria
3. **Dataset**: ALWAYS discover existing datasets first, only create new if needed
4. **Evaluate**: Run agent on dataset, apply scorers, analyze results

## Command Conventions

**Always use `uv run` for MLflow and Python commands:**

```bash
uv run mlflow --version          # MLflow CLI commands
uv run python scripts/xxx.py     # Python script execution
uv run python -c "..."           # Python one-liners
```

This ensures commands run in the correct environment with proper dependencies.

**CRITICAL: Separate stderr from stdout when capturing CLI output:**

When saving CLI command output to files for parsing (JSON, CSV, etc.), always redirect stderr separately to avoid mixing logs with structured data:

```bash
# Save both separately for debugging
uv run mlflow traces evaluate ... --output json > results.json 2> evaluation.log
```

## Documentation Access Protocol

**All MLflow documentation must be accessed through llms.txt:**

1. Start at: `https://mlflow.org/docs/latest/llms.txt`
2. Query llms.txt for your topic with specific prompt
3. If llms.txt references another doc, use WebFetch with that URL
4. Do not use WebSearch - use WebFetch with llms.txt first

**This applies to all steps**, especially:

- Dataset creation (read GenAI dataset docs from llms.txt)
- Scorer registration (check MLflow docs for scorer APIs)
- Evaluation execution (understand mlflow.genai.evaluate API)

## Discovering Agent Structure

**Each project has unique structure.** Use dynamic exploration instead of assumptions:

### Find Agent Entry Points
```bash
# Search for main agent functions
grep -r "def.*agent" . --include="*.py"
grep -r "def (run|stream|handle|process)" . --include="*.py"

# Check common locations
ls main.py app.py src/*/agent.py 2>/dev/null

# Look for API routes
grep -r "@app\.(get|post)" . --include="*.py"  # FastAPI/Flask
grep -r "def.*route" . --include="*.py"
```

### Understand Project Structure
```bash
# Check entry points in package config
cat pyproject.toml setup.py 2>/dev/null | grep -A 5 "scripts\|entry_points"

# Read project documentation
cat README.md docs/*.md 2>/dev/null | head -100

# Explore main directories
ls -la src/ app/ agent/ 2>/dev/null
```

## Setup Overview

Before evaluation, complete these three setup steps:

1. **Install MLflow** (version >=3.8.0)
2. **Configure environment** (tracking URI and experiment)
   - **Guide**: Follow `references/setup-guide.md` Steps 1-2
3. **Integrate tracing** (autolog and @mlflow.trace decorators)
   - ⚠️ **MANDATORY**: Follow `references/tracing-integration.md` - the authoritative tracing guide
   - ✓ **VERIFY**: Run `scripts/validate_agent_tracing.py` after implementing

⚠️ **Tracing must work before evaluation.** If tracing fails, stop and troubleshoot.

**Checkpoint - verify before proceeding:**

- [ ] MLflow >=3.8.0 installed
- [ ] MLFLOW_TRACKING_URI and MLFLOW_EXPERIMENT_ID set
- [ ] Autolog enabled and @mlflow.trace decorators added
- [ ] Test run creates a trace (verify trace ID is not None)

**Validation scripts:**
```bash
uv run python scripts/validate_environment.py  # Check MLflow install, env vars, connectivity
uv run python scripts/validate_auth.py         # Test authentication before expensive operations
```

## Evaluation Workflow

### Step 1: Understand Agent Purpose

1. Invoke agent with sample input
2. Inspect MLflow trace (especially LLM prompts describing agent purpose)
3. Print your understanding and ask user for verification
4. **Wait for confirmation before proceeding**

### Step 2: Define Quality Scorers

1. **Check registered scorers in your experiment:**
   ```bash
   uv run mlflow scorers list -x $MLFLOW_EXPERIMENT_ID
   ```

**IMPORTANT: if there are registered scorers in the experiment then they must be used for evaluation.**

2. **Select additional built-in scorers that apply to the agent** 

See `references/scorers.md` for the built-in scorers. Select any that are useful for assessing the agent's quality and that are not already registered. 

3. **Create additional custom scorers as needed**

If needed, create additional scorers using the `make_judge()` API. See `references/scorers.md` on how to create custom scorers and `references/scorers-constraints.md` for best practices.

4. **REQUIRED: Register new scorers before evaluation** using Python API:
   
   ```python
   from mlflow.genai.judges import make_judge
   from mlflow.genai.scorers import BuiltinScorerName
   import os

   scorer = make_judge(...)  # Or, scorer = BuiltinScorerName()
   scorer.register()
   ```

** IMPORTANT:  See `references/scorers.md` → "Model Selection for Scorers" to configure the `model` parameter of scorers before registration.

⚠️ **Scorers MUST be registered before evaluation.** Inline scorers that aren't registered won't appear in `mlflow scorers list` and won't be reusable.

5. **Verify registration:**
   ```bash
   uv run mlflow scorers list -x $MLFLOW_EXPERIMENT_ID  # Should show your scorers
   ```

### Step 3: Prepare Evaluation Dataset

**ALWAYS discover existing datasets first** to prevent duplicate work:

1. **Run dataset discovery** (mandatory):

   ```bash
   uv run python scripts/list_datasets.py  # Lists, compares, recommends datasets
   uv run python scripts/list_datasets.py --format json  # Machine-readable output
   uv run python scripts/list_datasets.py --help  # All options
   ```

2. **Present findings to user**:

   - Show all discovered datasets with their characteristics (size, topics covered)
   - If datasets found, highlight most relevant options based on agent type

3. **Ask user about existing datasets**:

   - "I found [N] existing evaluation dataset(s). Do you want to use one of these? (y/n)"
   - If yes: Ask which dataset to use and record the dataset name
   - If no: Proceed to step 4

4. **Create new dataset only if user declined existing ones**:
   ```bash
   # Generates dataset creation script from test cases file
   uv run python scripts/create_dataset_template.py --test-cases-file test_cases.txt
   uv run python scripts/create_dataset_template.py --help  # See all options
   ```
   Generated code uses `mlflow.genai.datasets` APIs - review and execute the script.

**IMPORTANT**: Do not skip dataset discovery. Always run `list_datasets.py` first, even if you plan to create a new dataset. This prevents duplicate work and ensures users are aware of existing evaluation datasets.

**For complete dataset guide:** See `references/dataset-preparation.md`

**Checkpoint - verify before proceeding:**

- [ ] Scorers have been registered
- [ ] Dataset has been created

### Step 4: Run Evaluation

1. Generate and run evaluation script:

   ```bash
   # Generate evaluation script (specify module and entry point)
   uv run python scripts/run_evaluation_template.py \
     --module mlflow_agent.agent \
     --entry-point run_agent

   # Review the generated script, then execute it
   uv run python run_agent_evaluation.py
   ```

   The generated script creates a wrapper function that:
   - Accepts keyword arguments matching the dataset's input keys
   - Provides any additional arguments the agent needs (like `llm_provider`)
   - Runs `mlflow.genai.evaluate(data=df, predict_fn=wrapper, scorers=registered_scorers)`
   - Saves results to `evaluation_results.csv`

⚠️ **CRITICAL: wrapper Signature Must Match Dataset Input Keys**

MLflow calls `predict_fn(**inputs)` - it unpacks the inputs dict as keyword arguments.

| Dataset Record | MLflow Calls | predict_fn Must Be |
|----------------|--------------|-------------------|
| `{"inputs": {"query": "..."}}` | `predict_fn(query="...")` | `def wrapper(query):` |
| `{"inputs": {"question": "...", "context": "..."}}` | `predict_fn(question="...", context="...")` | `def wrapper(question, context):` |

**Common Mistake (WRONG):**
```python
def wrapper(inputs):  # ❌ WRONG - inputs is NOT a dict
    return agent(inputs["query"])
```

2. Analyze results:
   ```bash
   # Pattern detection, failure analysis, recommendations
   uv run python scripts/analyze_results.py evaluation_results.csv
   ```
   Generates `evaluation_report.md` with pass rates and improvement suggestions.

## References

Detailed guides in `references/` (load as needed):

- **setup-guide.md** - Environment setup (MLflow install, tracking URI configuration)
- **tracing-integration.md** - Authoritative tracing guide (autolog, decorators, session tracking, verification)
- **dataset-preparation.md** - Dataset schema, APIs, creation, Unity Catalog
- **scorers.md** - Built-in vs custom scorers, registration, testing
- **scorers-constraints.md** - CLI requirements for custom scorers (yes/no format, templates)
- **troubleshooting.md** - Common errors by phase with solutions

Scripts are self-documenting - run with `--help` for usage details.
